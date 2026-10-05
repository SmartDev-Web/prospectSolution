from app.models import SearchArea
from app.sectors import SECTORS_BY_KEY
from app.sources.google_maps import parse_place, parse_review_count, unwrap_google_redirect
from app.sources.government import build_activity_filters, naf_code_matches, parse_establishment
from app.sources.openstreetmap import build_overpass_query, parse_overpass_element
from app.sources.website_finder import BusinessIdentity, build_domain_candidates, extract_search_result_urls, page_belongs_to_business

COMPANY = {"nom_complet": "AL NOUR SARL", "nom_raison_sociale": "AL NOUR SARL", "categorie_entreprise": "PME", "activite_principale": "47.22Z"}
ESTABLISHMENT = {
    "activite_principale": "47.22Z", "adresse": "33 RUE DU FAUBOURG DU COURREAU 34000 MONTPELLIER", "code_postal": "34000",
    "date_creation": "2012-08-10", "etat_administratif": "A", "latitude": "43.6083181796963", "longitude": "3.87074264381336",
    "libelle_commune": "MONTPELLIER", "liste_enseignes": ["LA BOUCHERIE DE KENITRA"], "nom_commercial": None,
    "siret": "44538849900029", "statut_diffusion_etablissement": "O", "tranche_effectif_salarie": "NN",
}


def test_registry_establishment_uses_its_signboard_name():
    candidate = parse_establishment(COMPANY, ESTABLISHMENT)
    assert candidate.name == "LA BOUCHERIE DE KENITRA"
    assert "AL NOUR SARL" in candidate.alternative_names
    assert candidate.sector_key == "butcher"
    assert candidate.employee_range == "Non employeur"


def test_closed_or_non_diffusible_establishments_are_skipped():
    assert parse_establishment(COMPANY, {**ESTABLISHMENT, "etat_administratif": "F"}) is None
    assert parse_establishment(COMPANY, {**ESTABLISHMENT, "statut_diffusion_etablissement": "P"}) is None


def test_activity_filters_and_matching():
    activity_filters = build_activity_filters([SECTORS_BY_KEY["butcher"], SECTORS_BY_KEY["industry"]], ["43.21a"])
    assert {"activite_principale": "10.13B,43.21A,47.22Z"} in activity_filters
    assert {"section_activite_principale": "C"} in activity_filters
    assert naf_code_matches("25.62B", set(), {"C"})
    assert not naf_code_matches("70.10Z", {"47.22Z"}, {"C"})


def test_overpass_query_and_parsing():
    query = build_overpass_query(SearchArea(latitude=43.6, longitude=3.87, radius_km=2), [SECTORS_BY_KEY["butcher"]])
    assert '["shop"="butcher"]' in query and "around:2000,43.6,3.87" in query
    candidate = parse_overpass_element({
        "type": "node", "lat": 43.61, "lon": 3.88,
        "tags": {"name": "Boucherie Brume", "shop": "butcher", "website": "https://boucherie-brume.fr", "phone": "+33 4 67 00 00 00", "addr:postcode": "34000", "addr:city": "Montpellier"},
    })
    assert candidate.sector_key == "butcher"
    assert candidate.website_url == "https://boucherie-brume.fr"
    assert candidate.address == "34000 Montpellier"


def test_google_maps_place_parsing():
    place_url = "https://www.google.com/maps/place/Le+Pascalou/data=!4m7!3m6!1s0x12b6af1234:0xabcdef!8m2!3d43.6373!4d3.9101!16s?hl=fr"
    candidate = parse_place({
        "name": "Le Pascalou", "category": "Pizzeria", "addressLabel": "Adresse: 12 Rue de la Paix, 34170 Castelnau-le-Lez",
        "website": "https://www.google.com/url?q=https://castelnau.lepascalou.fr/&sa=U", "phoneItem": "phone:tel:0467413068",
        "ratingText": "4,5", "reviewText": "(1 234)", "permanentlyClosed": False,
    }, place_url, SECTORS_BY_KEY["restaurant"])
    assert candidate.website_url == "https://castelnau.lepascalou.fr/"
    assert (candidate.postal_code, candidate.city) == ("34170", "Castelnau-le-Lez")
    assert (candidate.latitude, candidate.longitude) == (43.6373, 3.9101)
    assert candidate.google_rating == 4.5 and candidate.google_review_count == 1234
    assert candidate.google_place_key == "0x12b6af1234:0xabcdef"
    assert parse_review_count("1 234 avis") == 1234
    assert unwrap_google_redirect("https://example.fr") == "https://example.fr"


def test_website_finder_helpers():
    identity = BusinessIdentity(name="Boucherie Brume", alternative_names=["EURL BRUME"], city="Castelnau-le-Lez", postal_code="34170", phone=None)
    domain_candidates = build_domain_candidates(identity)
    assert "boucheriebrume.fr" in domain_candidates and "boucherie-brume.com" in domain_candidates
    assert page_belongs_to_business("<html><body>Boucherie Brume, 34170 Castelnau-le-Lez</body></html>", identity)
    assert not page_belongs_to_business("<html><body>Boucherie Brume, 75011 Paris</body></html>", identity)
    results_html = '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fboucherie-brume.fr%2F&rut=x">Brume</a>'
    assert extract_search_result_urls(results_html) == ["https://boucherie-brume.fr/"]
