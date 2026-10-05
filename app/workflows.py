"""Prospecting workflows run as background jobs: searches, website discovery and scans."""
import asyncio
import logging

from app.http_client import OpenDataError
from app.jobs import JobContext, job_manager
from app.models import GoogleMapsSearchRequest, OpenDataSearchRequest
from app.prospects import prospect_repository
from app.scanner.service import scan_prospect
from app.sectors import SECTORS_BY_KEY, Sector
from app.settings_service import load_settings
from app.sources.google_maps import GoogleMapsScraper
from app.sources.government import search_government_registry
from app.sources.openstreetmap import search_openstreetmap
from app.sources.website_finder import BusinessIdentity, WebsiteFinder, create_website_client

logger = logging.getLogger(__name__)
WEBSITE_DISCOVERY_CONCURRENCY = 4


def resolve_sectors(sector_keys: list[str]) -> list[Sector]:
    """Return the sector definitions for the selected keys."""
    return [SECTORS_BY_KEY[sector_key] for sector_key in sector_keys if sector_key in SECTORS_BY_KEY]


async def discover_missing_websites(context: JobContext, prospect_identifiers: list[int]) -> int:
    """Look for the website of every given prospect that has none yet; return how many were found."""
    prospects_to_check = prospect_repository.list_prospects_needing_website_check(prospect_identifiers)
    if not prospects_to_check:
        return 0
    use_search_engine = load_settings()["website_discovery_use_search_engine"]
    context.set_progress(0, len(prospects_to_check), f"Recherche des sites web de {len(prospects_to_check)} entreprises…")
    concurrency_limiter = asyncio.Semaphore(WEBSITE_DISCOVERY_CONCURRENCY)
    found_count = 0
    async with create_website_client() as client:
        website_finder = WebsiteFinder(client, use_search_engine, context.log)
        async def discover_for_prospect(prospect: dict) -> None:
            nonlocal found_count
            async with concurrency_limiter:
                identity = BusinessIdentity(
                    name=prospect["name"],
                    alternative_names=[name for name in (prospect.get("legal_name"),) if name and name != prospect["name"]],
                    city=prospect.get("city"),
                    postal_code=prospect.get("postal_code"),
                    phone=prospect.get("phone"),
                )
                discovery = await website_finder.discover(identity)
                prospect_repository.record_website_check(prospect["id"], discovery.website_url, discovery.origin, discovery.social_url)
                if discovery.website_url:
                    found_count += 1
                context.advance(f"{prospect['name']} : {discovery.website_url or 'aucun site trouvé'}")
        await asyncio.gather(*(discover_for_prospect(prospect) for prospect in prospects_to_check))
    return found_count


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
        if search_request.use_government_registry:
            context.log("Interrogation du registre des entreprises (INSEE / Sirene)…")
            registry_count = 0
            try:
                async for candidate in search_government_registry(
                    search_request.area, sectors, search_request.custom_naf_codes, search_request.exclude_large_companies,
                    search_request.created_after, search_request.max_results,
                ):
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
            for candidate in osm_candidates:
                prospect_identifier, created = prospect_repository.upsert_prospect(candidate)
                touched_identifiers.append(prospect_identifier)
                created_count += int(created)
            context.log(f"OpenStreetMap : {len(osm_candidates)} commerces trouvés.")
        touched_identifiers = list(dict.fromkeys(touched_identifiers))
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
        scraper = GoogleMapsScraper(headless=headless, pause_range_seconds=pause_range, log=context.log)
        context.set_progress(0, 0, f"{len(queries)} recherches Google Maps à effectuer")
        async for candidate in scraper.scrape(search_request.area, queries, search_request.max_results_per_query):
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
                prospect_repository.record_website_check(prospect_identifier, None, None, None)
        context.set_result(prospects=len(touched_identifiers), created=created_count)
        context.log(f"Terminé : {len(touched_identifiers)} fiches ({created_count} nouvelles).")
        if search_request.auto_scan and touched_identifiers:
            start_scan_job(touched_identifiers, f"Analyse automatique Google Maps ({search_request.area.label or 'recherche'})")
    if not queries:
        raise ValueError("Sélectionnez au moins un secteur ou saisissez une recherche personnalisée.")
    return job_manager.start("google_maps_search", f"Google Maps : {search_request.area.label or 'zone'} ({len(queries)} recherches)", run)
