"""Prospecting workflows run as background jobs: searches, website discovery and scans."""
import asyncio
import logging

from app.chains import detect_chain
from app.http_client import OpenDataError
from app.jobs import JobContext, job_manager
from app.models import GoogleMapsSearchRequest, OpenDataSearchRequest, ProspectCandidate, SearchArea
from app.prospects import candidate_names, prospect_repository
from app.scanner.service import scan_prospect
from app.sectors import SECTORS_BY_KEY, Sector
from app.settings_service import load_settings
from app.geo import geocode
from app.sources.google_maps import GoogleMapsScraper, PlaceLookup
from app.sources.government import search_government_registry
from app.sources.openstreetmap import search_openstreetmap
from app.sources.search_engines import SearchEngineRouter, build_search_engines
from app.sources.website_finder import WebsiteFinder, create_website_client
from app.sources.website_verification import BusinessIdentity
from app.text_utils import extract_street_name

logger = logging.getLogger(__name__)
WEBSITE_DISCOVERY_CONCURRENCY = 4


def resolve_sectors(sector_keys: list[str]) -> list[Sector]:
    """Return the sector definitions for the selected keys."""
    return [SECTORS_BY_KEY[sector_key] for sector_key in sector_keys if sector_key in SECTORS_BY_KEY]


CONFIDENCE_LABELS = {"high": "certain", "medium": "à vérifier"}


def build_business_identity(prospect: dict) -> BusinessIdentity:
    """Gather everything that helps recognise the website of a stored prospect."""
    return BusinessIdentity(
        name=prospect["name"],
        alternative_names=[name for name in (prospect.get("legal_name"),) if name and name != prospect["name"]],
        city=prospect.get("city"),
        postal_code=prospect.get("postal_code"),
        phone=prospect.get("phone"),
        siren=(prospect.get("siret") or "")[:9] or None,
        street=extract_street_name(prospect.get("address")),
        rejected_domains=set(prospect.get("rejected_domains") or []),
    )


def build_search_router(log) -> SearchEngineRouter | None:
    """Create the search engine router from the engines enabled in the settings."""
    settings = load_settings()
    engine_keys = [engine_key for engine_key in ("duckduckgo", "bing", "google_browser") if settings[f"search_engine_{engine_key}"]]
    engines = build_search_engines(engine_keys, settings["google_search_headless"])
    return SearchEngineRouter(engines, log) if engines else None


async def discover_missing_websites(context: JobContext, prospect_identifiers: list[int], include_already_checked: bool = False) -> int:
    """Look for the website of every given prospect that has none; return how many were found."""
    prospects_to_check = prospect_repository.list_prospects_needing_website_check(prospect_identifiers, include_already_checked)
    if not prospects_to_check:
        return 0
    context.set_progress(0, len(prospects_to_check), f"Recherche des sites web de {len(prospects_to_check)} entreprises…")
    concurrency_limiter = asyncio.Semaphore(WEBSITE_DISCOVERY_CONCURRENCY)
    found_count = 0
    search_router = build_search_router(context.log)
    async with create_website_client() as client:
        website_finder = WebsiteFinder(client, search_router, context.log)
        async def discover_for_prospect(prospect: dict) -> None:
            nonlocal found_count
            async with concurrency_limiter:
                try:
                    discovery = await website_finder.discover(build_business_identity(prospect))
                except Exception as error:
                    logger.exception("Website discovery failed for prospect %s", prospect["id"])
                    context.advance(f"{prospect['name']} : recherche interrompue ({type(error).__name__})")
                    return
                prospect_repository.record_website_check(
                    prospect["id"], discovery.website_url, discovery.origin, discovery.confidence, discovery.evidence, discovery.social_url,
                )
                if discovery.website_url:
                    found_count += 1
                    context.advance(f"{prospect['name']} : {discovery.website_url} ({CONFIDENCE_LABELS[discovery.confidence]})")
                else:
                    context.advance(f"{prospect['name']} : aucun site trouvé")
        try:
            await asyncio.gather(*(discover_for_prospect(prospect) for prospect in prospects_to_check))
        finally:
            if search_router:
                await search_router.close()
    return found_count


def start_website_discovery_job(prospect_identifiers: list[int]):
    """Start a background job searching again the websites of prospects that have none."""
    async def run(context: JobContext) -> None:
        found_count = await discover_missing_websites(context, prospect_identifiers, include_already_checked=True)
        context.set_result(websites_found=found_count)
        context.log(f"Terminé : {found_count} site(s) trouvé(s) sur {len(prospect_identifiers)} prospect(s).")
    return job_manager.start("website_discovery", f"Recherche de sites ({len(prospect_identifiers)} prospects)", run)


class ChainFilter:
    """Skip chains and franchises during an import, counting what was left out."""

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled
        self.skipped_names: list[str] = []

    def accepts(self, candidate: ProspectCandidate) -> bool:
        if not self._enabled:
            return True
        if detect_chain(candidate_names(candidate), candidate.website_url, candidate.brand, candidate.establishment_count):
            self.skipped_names.append(candidate.name)
            return False
        return True

    def summary(self) -> str:
        unique_names = sorted(set(self.skipped_names))
        preview = ", ".join(unique_names[:8]) + ("…" if len(unique_names) > 8 else "")
        return f"Chaînes et franchises ignorées : {len(self.skipped_names)}" + (f" ({preview})" if unique_names else "")


async def scan_prospects(context: JobContext, prospect_identifiers: list[int]) -> None:
    """Scan several prospects concurrently, reporting progress."""
    concurrency_limiter = asyncio.Semaphore(max(1, int(load_settings()["scan_concurrency"])))
    context.set_progress(0, len(prospect_identifiers), f"Analyse de {len(prospect_identifiers)} prospects…")
    async def scan_with_limit(prospect_identifier: int) -> None:
        async with concurrency_limiter:
            try:
                scanned_prospect = await scan_prospect(prospect_identifier)
            except Exception as error:
                logger.exception("Scan of prospect %s failed", prospect_identifier)
                context.advance(f"Échec de l'analyse du prospect #{prospect_identifier} : {error}")
                return
            if scanned_prospect:
                score_label = f"{scanned_prospect['score']}/100" if scanned_prospect["score"] is not None else "pas de site"
                context.advance(f"{scanned_prospect['name']} : {score_label}")
    await asyncio.gather(*(scan_with_limit(prospect_identifier) for prospect_identifier in prospect_identifiers))
    context.set_result(scanned=len(prospect_identifiers))


def start_scan_job(prospect_identifiers: list[int], label: str | None = None):
    """Start a background job scanning the given prospects."""
    async def run(context: JobContext) -> None:
        await scan_prospects(context, prospect_identifiers)
    return job_manager.start("scan", label or f"Analyse de {len(prospect_identifiers)} sites", run)


def start_open_data_search(search_request: OpenDataSearchRequest):
    """Start a background search through the government registry and OpenStreetMap."""
    sectors = resolve_sectors(search_request.sector_keys)
    async def run(context: JobContext) -> None:
        touched_identifiers: list[int] = []
        created_count = 0
        chain_filter = ChainFilter(search_request.exclude_chains)
        if search_request.use_government_registry:
            context.log("Interrogation du registre des entreprises (INSEE / Sirene)…")
            registry_count = 0
            try:
                async for candidate in search_government_registry(
                    search_request.area, sectors, search_request.custom_naf_codes, search_request.exclude_large_companies,
                    search_request.created_after, search_request.max_results,
                ):
                    if not chain_filter.accepts(candidate):
                        continue
                    prospect_identifier, created = prospect_repository.upsert_prospect(candidate)
                    touched_identifiers.append(prospect_identifier)
                    created_count += int(created)
                    registry_count += 1
                    if registry_count % 25 == 0:
                        context.log(f"Registre : {registry_count} établissements récupérés…")
            except OpenDataError as error:
                context.log(f"⚠️ Registre indisponible : {error}")
            context.log(f"Registre : {registry_count} établissements actifs dans la zone.")
        if search_request.use_openstreetmap:
            context.log("Interrogation d'OpenStreetMap…")
            try:
                osm_candidates = await search_openstreetmap(search_request.area, sectors)
            except OpenDataError as error:
                context.log(f"⚠️ OpenStreetMap indisponible : {error}")
                osm_candidates = []
            osm_candidates = [candidate for candidate in osm_candidates if chain_filter.accepts(candidate)]
            for candidate in osm_candidates:
                prospect_identifier, created = prospect_repository.upsert_prospect(candidate)
                touched_identifiers.append(prospect_identifier)
                created_count += int(created)
            context.log(f"OpenStreetMap : {len(osm_candidates)} commerces trouvés.")
        touched_identifiers = list(dict.fromkeys(touched_identifiers))
        context.log(chain_filter.summary())
        found_websites = 0
        if search_request.discover_websites:
            found_websites = await discover_missing_websites(context, touched_identifiers)
            context.log(f"Sites web découverts automatiquement : {found_websites}.")
        context.set_result(prospects=len(touched_identifiers), created=created_count, websites_found=found_websites)
        context.log(f"Terminé : {len(touched_identifiers)} prospects ({created_count} nouveaux).")
        if search_request.auto_scan and touched_identifiers:
            start_scan_job(touched_identifiers, f"Analyse automatique ({search_request.area.label or 'recherche'})")
    area_label = search_request.area.label or f"{search_request.area.latitude:.3f}, {search_request.area.longitude:.3f}"
    return job_manager.start("open_data_search", f"Open data : {area_label} ({search_request.area.radius_km:g} km)", run)


def start_google_maps_search(search_request: GoogleMapsSearchRequest):
    """Start a background Google Maps scraping session."""
    settings = load_settings()
    sectors = resolve_sectors(search_request.sector_keys)
    queries: list[tuple[str, Sector | None]] = [(query, sector) for sector in sectors for query in sector.google_maps_queries]
    queries += [(custom_query.strip(), None) for custom_query in search_request.custom_queries if custom_query.strip()]
    headless = settings["google_maps_headless"] if search_request.headless is None else search_request.headless
    pause_range = (float(settings["google_maps_pause_min_seconds"]), float(settings["google_maps_pause_max_seconds"]))
    async def run(context: JobContext) -> None:
        touched_identifiers: list[int] = []
        created_count = 0
        chain_filter = ChainFilter(search_request.exclude_chains)
        scraper = GoogleMapsScraper(headless=headless, pause_range_seconds=pause_range, log=context.log)
        context.set_progress(0, 0, f"{len(queries)} recherches Google Maps à effectuer")
        async for candidate in scraper.scrape(search_request.area, queries, search_request.max_results_per_query):
            if not chain_filter.accepts(candidate):
                context.log(f"{candidate.name} : chaîne ignorée")
                continue
            prospect_identifier, created = prospect_repository.upsert_prospect(candidate)
            touched_identifiers.append(prospect_identifier)
            created_count += int(created)
            website_label = candidate.website_url or "pas de site"
            context.advance(f"{candidate.name} : {website_label}")
        touched_identifiers = list(dict.fromkeys(touched_identifiers))
        for prospect_identifier in touched_identifiers:
            prospect = prospect_repository.get_prospect(prospect_identifier)
            if prospect and not prospect["website_url"] and not prospect["website_check_done"]:
                # Google Maps is authoritative: a listing without website means the business has none
                prospect_repository.record_website_check(prospect_identifier, None)
        context.log(chain_filter.summary())
        context.set_result(prospects=len(touched_identifiers), created=created_count)
        context.log(f"Terminé : {len(touched_identifiers)} fiches ({created_count} nouvelles).")
        if search_request.auto_scan and touched_identifiers:
            start_scan_job(touched_identifiers, f"Analyse automatique Google Maps ({search_request.area.label or 'recherche'})")
    if not queries:
        raise ValueError("Sélectionnez au moins un secteur ou saisissez une recherche personnalisée.")
    return job_manager.start("google_maps_search", f"Google Maps : {search_request.area.label or 'zone'} ({len(queries)} recherches)", run)


LOOKUP_RADIUS_KM = 5.0


async def build_place_lookup(prospect: dict) -> PlaceLookup | None:
    """Prepare the targeted Google Maps search of a stored prospect."""
    latitude, longitude = prospect.get("latitude"), prospect.get("longitude")
    if latitude is None or longitude is None:
        location_query = prospect.get("city") or prospect.get("postal_code")
        geocoded_places = await geocode(location_query, limit=1) if location_query else []
        if not geocoded_places:
            return None
        latitude, longitude = geocoded_places[0].latitude, geocoded_places[0].longitude
    names = [name for name in (prospect["name"], prospect.get("legal_name")) if name]
    query = " ".join(part for part in (prospect["name"], prospect.get("city") or prospect.get("postal_code")) if part)
    return PlaceLookup(reference=prospect["id"], query=query, names=names, area=SearchArea(latitude=latitude, longitude=longitude, radius_km=LOOKUP_RADIUS_KM))


def start_google_maps_enrichment(prospect_identifiers: list[int]):
    """Start a background job completing prospects with their Google Maps listing."""
    settings = load_settings()
    pause_range = (float(settings["google_maps_pause_min_seconds"]), float(settings["google_maps_pause_max_seconds"]))
    async def run(context: JobContext) -> None:
        prospects = [prospect for prospect in (prospect_repository.get_prospect(identifier) for identifier in prospect_identifiers) if prospect]
        lookups = [lookup for lookup in [await build_place_lookup(prospect) for prospect in prospects] if lookup]
        context.set_progress(0, len(lookups), f"Recherche de {len(lookups)} fiche(s) sur Google Maps…")
        completed_count = 0
        scraper = GoogleMapsScraper(headless=settings["google_maps_headless"], pause_range_seconds=pause_range, log=context.log)
        async for lookup, candidate in scraper.lookup(lookups):
            prospect_repository.enrich_from_listing(lookup.reference, candidate)
            completed_count += int(candidate is not None)
            context.advance(f"{lookup.query} : " + (f"trouvé ({candidate.phone or 'sans téléphone'}, {candidate.website_url or 'sans site'})" if candidate else "aucune fiche correspondante"))
        context.set_result(completed=completed_count)
        context.log(f"Terminé : {completed_count} fiche(s) complétée(s) sur {len(lookups)}.")
    return job_manager.start("google_maps_enrichment", f"Complétion Google Maps ({len(prospect_identifiers)} prospects)", run)
