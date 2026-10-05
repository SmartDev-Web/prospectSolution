"""Business search through the French government company registry (Sirene / RNE)."""
import logging
import re
from typing import AsyncIterator

from app.geo import is_within_radius
from app.http_client import RequestPacer, create_open_data_client, request_json_with_retries
from app.models import ProspectCandidate, SearchArea
from app.sectors import Sector, find_sector_by_naf_code, naf_code_in_sections
from app.text_utils import format_place_name

logger = logging.getLogger(__name__)
NEAR_POINT_URL = "https://recherche-entreprises.api.gouv.fr/near_point"
RESULTS_PER_PAGE = 25
# The registry allows 7 requests per second; staying well below avoids any refusal
registry_pacer = RequestPacer(0.4)
LARGE_COMPANY_CATEGORIES = {"GE", "ETI"}
EMPLOYEE_RANGE_MINIMUMS = {
    "NN": 0, "00": 0, "01": 1, "02": 3, "03": 6, "11": 10, "12": 20, "21": 50, "22": 100, "31": 200, "32": 250,
    "41": 500, "42": 1000, "51": 2000, "52": 5000, "53": 10000,
}
EMPLOYEE_RANGE_LABELS = {
    "NN": "Non employeur", "00": "0 salarié", "01": "1-2 salariés", "02": "3-5 salariés", "03": "6-9 salariés",
    "11": "10-19 salariés", "12": "20-49 salariés", "21": "50-99 salariés", "22": "100-199 salariés",
    "31": "200-249 salariés", "32": "250-499 salariés", "41": "500-999 salariés", "42": "1000-1999 salariés",
    "51": "2000-4999 salariés", "52": "5000-9999 salariés", "53": "10000 salariés et plus",
}


def build_establishment_name(company: dict, establishment: dict) -> tuple[str, list[str]]:
    """Choose the public facing name of an establishment and list its other names."""
    signboard_names = establishment.get("liste_enseignes") or []
    trade_name = establishment.get("nom_commercial")
    legal_name = company.get("nom_raison_sociale") or company.get("nom_complet") or ""
    ordered_names = [name for name in (*signboard_names, trade_name, company.get("nom_complet"), legal_name) if name]
    unique_names = list(dict.fromkeys(name.strip() for name in ordered_names))
    return unique_names[0], unique_names[1:]


def format_person_name(first_names: str | None, last_name: str | None) -> str | None:
    """Format a registry person as 'Jean Dupont', keeping only the first given name."""
    if not last_name:
        return None
    first_name = (first_names or "").split(" ")[0]
    # Registry names carry the birth or usage name in parentheses, irrelevant on the phone
    cleaned_last_name = re.sub(r"\s*\(.*?\)", "", last_name).strip()
    return " ".join(part for part in (format_place_name(first_name), format_place_name(cleaned_last_name)) if part)


def find_manager_name(company: dict) -> str | None:
    """Return the name of the person running the company, to ask for them on the phone."""
    for manager in company.get("dirigeants") or []:
        if manager.get("type_dirigeant") == "personne physique" and manager.get("nom"):
            return format_person_name(manager.get("prenoms"), manager.get("nom"))
    if (company.get("complements") or {}).get("est_entrepreneur_individuel"):
        return format_place_name(re.sub(r"\s*\(.*?\)", "", company.get("nom_complet") or "").strip()) or None
    return None


def parse_establishment(company: dict, establishment: dict) -> ProspectCandidate | None:
    """Convert one registry establishment into a prospect candidate."""
    if establishment.get("etat_administratif") != "A":
        return None
    if establishment.get("statut_diffusion_etablissement") not in (None, "O"):
        # Establishments flagged as non-diffusible asked not to be prospected
        return None
    display_name, alternative_names = build_establishment_name(company, establishment)
    naf_code = establishment.get("activite_principale") or company.get("activite_principale")
    matching_sector = find_sector_by_naf_code(naf_code)
    latitude = establishment.get("latitude")
    longitude = establishment.get("longitude")
    return ProspectCandidate(
        name=display_name,
        source="government_registry",
        alternative_names=alternative_names,
        legal_name=company.get("nom_raison_sociale") or company.get("nom_complet"),
        siret=establishment.get("siret"),
        naf_code=naf_code,
        sector_key=matching_sector.key if matching_sector else None,
        category_label=matching_sector.label if matching_sector else naf_code,
        company_category=company.get("categorie_entreprise"),
        address=establishment.get("adresse"),
        postal_code=establishment.get("code_postal"),
        city=format_place_name(establishment.get("libelle_commune")),
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
        creation_date=establishment.get("date_creation"),
        employee_range=EMPLOYEE_RANGE_LABELS.get(establishment.get("tranche_effectif_salarie") or "", None),
        employee_minimum=EMPLOYEE_RANGE_MINIMUMS.get(establishment.get("tranche_effectif_salarie") or ""),
        manager_name=find_manager_name(company),
        establishment_count=company.get("nombre_etablissements_ouverts"),
    )


def naf_code_matches(naf_code: str | None, accepted_naf_codes: set[str], accepted_sections: set[str]) -> bool:
    """Tell whether an establishment activity belongs to the requested codes or NAF sections."""
    return bool(naf_code) and (naf_code in accepted_naf_codes or naf_code_in_sections(naf_code, accepted_sections))


def build_activity_filters(sectors: list[Sector], custom_naf_codes: list[str]) -> list[dict[str, str]]:
    """Group sector criteria into the query parameter sets accepted by the API."""
    naf_codes = sorted({naf_code for sector in sectors for naf_code in sector.naf_codes} | {code.strip().upper() for code in custom_naf_codes if code.strip()})
    naf_sections = sorted({section for sector in sectors for section in sector.naf_sections})
    activity_filters = []
    if naf_codes:
        activity_filters.append({"activite_principale": ",".join(naf_codes)})
    if naf_sections:
        activity_filters.append({"section_activite_principale": ",".join(naf_sections)})
    return activity_filters


async def search_government_registry(
    area: SearchArea,
    sectors: list[Sector],
    custom_naf_codes: list[str],
    exclude_large_companies: bool,
    created_after: str | None,
    max_results: int,
) -> AsyncIterator[ProspectCandidate]:
    """Yield active establishments located in the search area and matching the sectors."""
    activity_filters = build_activity_filters(sectors, custom_naf_codes)
    if not activity_filters:
        return
    yielded_sirets: set[str] = set()
    accepted_naf_codes = {naf_code for sector in sectors for naf_code in sector.naf_codes} | {code.strip().upper() for code in custom_naf_codes if code.strip()}
    accepted_sections = {section for sector in sectors for section in sector.naf_sections}
    async with create_open_data_client() as client:
        for activity_filter in activity_filters:
            page_number = 1
            total_pages = 1
            while page_number <= total_pages and len(yielded_sirets) < max_results:
                query_parameters = {
                    "lat": area.latitude,
                    "long": area.longitude,
                    "radius": area.radius_km,
                    "per_page": RESULTS_PER_PAGE,
                    "page": page_number,
                    **activity_filter,
                }
                response_body = await request_json_with_retries(client, "GET", NEAR_POINT_URL, pacer=registry_pacer, params=query_parameters)
                total_pages = response_body.get("total_pages") or 1
                for company in response_body.get("results", []):
                    if exclude_large_companies and company.get("categorie_entreprise") in LARGE_COMPANY_CATEGORIES:
                        continue
                    for establishment in company.get("matching_etablissements") or []:
                        candidate = parse_establishment(company, establishment)
                        if candidate is None or candidate.siret in yielded_sirets:
                            continue
                        if not naf_code_matches(candidate.naf_code, accepted_naf_codes, accepted_sections):
                            # Head offices and secondary sites of a matching company often carry another activity
                            continue
                        if created_after and (candidate.creation_date or "") < created_after:
                            continue
                        if not is_within_radius(area.latitude, area.longitude, area.radius_km, candidate.latitude, candidate.longitude):
                            continue
                        yielded_sirets.add(candidate.siret)
                        yield candidate
                        if len(yielded_sirets) >= max_results:
                            return
                page_number += 1
