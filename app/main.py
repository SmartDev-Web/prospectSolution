"""HTTP API, WebSocket event stream and static web interface."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.browser import browser_runtime
from app.config import SCREENSHOT_DIRECTORY, WEB_DIRECTORY, ensure_data_directories
from app.database import get_database
from app.events import event_bus
from app.geo import geocode
from app.http_client import OpenDataError
from app.jobs import JobContext, job_manager
from app.llm.gpu import describe_graphics_cards
from app.llm.ollama import ollama_service
from app.models import (
    ActivityCreate,
    BulkDeleteRequest,
    BulkUpdateRequest,
    DiagnosisOverrides,
    GoogleMapsEnrichmentRequest,
    GoogleMapsSearchRequest,
    MarkChainRequest,
    MergeRequest,
    OpenDataSearchRequest,
    ProspectCandidate,
    ProspectCreate,
    ProspectUpdate,
    ScanRequest,
    WebsiteDiscoveryRequest,
)
from app.prospects import prospect_repository
from app.scanner.lighthouse import find_lighthouse_executable
from app.scanner.service import edit_diagnosis
from app.chains import parse_custom_brands
from app.sectors import get_sector, serialize_sectors
from app.text_utils import normalize_company_name
from app.settings_service import load_settings, save_settings
from app.workflows import start_full_refresh_job, start_google_maps_enrichment, start_google_maps_search, start_open_data_search, start_scan_job, start_website_discovery_job

logger = logging.getLogger(__name__)


@asynccontextmanager
async def application_lifespan(_application: FastAPI):
    """Prepare storage on startup and release every resource on shutdown."""
    ensure_data_directories()
    get_database()
    if load_settings()["llm_mode"] == "managed":
        asyncio.create_task(ollama_service.start_managed_server())
    yield
    await job_manager.shutdown()
    await ollama_service.stop_managed_server()
    await browser_runtime.shutdown()


application = FastAPI(title="Prospect Solution", lifespan=application_lifespan)
ensure_data_directories()
application.mount("/static", StaticFiles(directory=WEB_DIRECTORY), name="static")
application.mount("/screenshots", StaticFiles(directory=SCREENSHOT_DIRECTORY), name="screenshots")


def require_prospect(prospect_identifier: int) -> dict[str, Any]:
    """Return the prospect detail or answer 404."""
    prospect_detail = prospect_repository.get_prospect_detail(prospect_identifier)
    if prospect_detail is None:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    return prospect_detail


@application.get("/")
async def serve_interface() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "index.html")


@application.get("/api/sectors")
async def get_sectors() -> list[dict]:
    return serialize_sectors()


@application.get("/api/geocode")
async def geocode_place(query: str = Query(min_length=2)) -> list[dict]:
    try:
        geocoded_places = await geocode(query)
    except OpenDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return [place.__dict__ for place in geocoded_places]


@application.post("/api/searches/open-data")
async def create_open_data_search(search_request: OpenDataSearchRequest) -> dict:
    if not search_request.sector_keys and not search_request.custom_naf_codes:
        raise HTTPException(status_code=400, detail="Sélectionnez au moins un secteur ou un code NAF.")
    return start_open_data_search(search_request).to_dict()


@application.post("/api/searches/google-maps")
async def create_google_maps_search(search_request: GoogleMapsSearchRequest) -> dict:
    if job_manager.has_running_job("google_maps_search") or job_manager.has_running_job("google_maps_enrichment"):
        raise HTTPException(status_code=409, detail="Une session Google Maps est déjà en cours.")
    try:
        return start_google_maps_search(search_request).to_dict()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def read_prospect_filters(
    status: list[str] = Query(default=[]),
    sector_key: list[str] = Query(default=[]),
    opportunity_level: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    city: list[str] = Query(default=[]),
    website: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    follow_up: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    employees_min: int | None = None,
    rating_min: float | None = None,
    created_after: str | None = None,
    search_text: str | None = None,
    sort: str | None = None,
    sort_direction: str | None = None,
    center_latitude: float | None = None,
    center_longitude: float | None = None,
    radius_km: float | None = None,
    area_city: str | None = None,
) -> dict[str, Any]:
    """Collect the prospect list filters shared by the list and export endpoints; multiple choice filters repeat their parameter."""
    return {
        "status": status, "sector_key": sector_key, "opportunity_level": opportunity_level, "source": source, "city": city,
        "website": website, "phone": phone, "email": email, "follow_up": follow_up,
        "score_min": score_min, "score_max": score_max, "employees_min": employees_min, "rating_min": rating_min, "created_after": created_after,
        "search_text": search_text, "sort": sort, "sort_direction": sort_direction,
        "center_latitude": center_latitude, "center_longitude": center_longitude, "radius_km": radius_km, "area_city": area_city,
    }


@application.get("/api/prospects")
async def list_prospects(prospect_filters: dict = Depends(read_prospect_filters)) -> list[dict]:
    return prospect_repository.list_prospects(prospect_filters)


@application.get("/api/prospects/facets")
async def get_prospect_facets() -> dict:
    return prospect_repository.facets()


@application.post("/api/prospects/bulk-update")
async def bulk_update_prospects(bulk_update_request: BulkUpdateRequest) -> dict:
    changes = bulk_update_request.changes.model_dump(exclude_unset=True)
    return {"updated": prospect_repository.update_prospects(bulk_update_request.prospect_ids, changes)}


@application.post("/api/prospects/bulk-delete")
async def bulk_delete_prospects(bulk_delete_request: BulkDeleteRequest) -> dict:
    return {"deleted": prospect_repository.delete_prospects(bulk_delete_request.prospect_ids)}


@application.get("/api/prospects/export.csv")
async def export_prospects(prospect_filters: dict = Depends(read_prospect_filters)) -> Response:
    csv_content = prospect_repository.export_csv(prospect_filters)
    return Response(
        content=csv_content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="prospects-{date.today().isoformat()}.csv"'},
    )


@application.post("/api/prospects")
async def create_prospect(prospect_create: ProspectCreate) -> dict:
    sector = get_sector(prospect_create.sector_key)
    prospect_identifier, _created = prospect_repository.upsert_prospect(ProspectCandidate(
        name=prospect_create.name,
        source="manual",
        website_url=prospect_create.website_url or None,
        website_origin="manual" if prospect_create.website_url else None,
        city=prospect_create.city or None,
        phone=prospect_create.phone or None,
        sector_key=prospect_create.sector_key or None,
        category_label=sector.label if prospect_create.sector_key else None,
    ))
    if prospect_create.scan_now:
        start_scan_job([prospect_identifier], f"Analyse de {prospect_create.name}")
    return require_prospect(prospect_identifier)


@application.post("/api/prospects/refresh-all")
async def refresh_all_prospects() -> dict:
    if job_manager.has_running_job("full_refresh"):
        raise HTTPException(status_code=409, detail="Une analyse complète est déjà en cours.")
    return start_full_refresh_job().to_dict()


@application.post("/api/prospects/merge")
async def merge_selected_prospects(merge_request: MergeRequest) -> dict:
    merged_prospect = prospect_repository.merge_prospects(merge_request.prospect_ids)
    if merged_prospect is None:
        raise HTTPException(status_code=404, detail="Prospects introuvables")
    return require_prospect(merged_prospect["id"])


@application.post("/api/prospects/merge-duplicates")
async def merge_duplicate_prospects() -> dict:
    return {"merged": prospect_repository.merge_all_duplicates()}


@application.post("/api/prospects/remove-chains")
async def remove_chain_prospects() -> dict:
    removed_names = prospect_repository.remove_chains(parse_custom_brands(load_settings()["custom_chain_brands"]))
    return {"removed": len(removed_names), "names": removed_names}


@application.put("/api/prospects/{prospect_identifier}/diagnosis")
async def update_prospect_diagnosis(prospect_identifier: int, diagnosis_overrides: DiagnosisOverrides) -> dict:
    require_prospect(prospect_identifier)
    overrides = diagnosis_overrides.model_dump()
    overrides["summary"] = (overrides["summary"] or "").strip() or None
    return edit_diagnosis(prospect_identifier, overrides)


@application.post("/api/prospects/{prospect_identifier}/mark-chain")
async def mark_prospect_as_chain(prospect_identifier: int, mark_chain_request: MarkChainRequest) -> dict:
    require_prospect(prospect_identifier)
    custom_brands_text = load_settings()["custom_chain_brands"]
    brand_line = mark_chain_request.brand.strip()
    if normalize_company_name(brand_line) not in parse_custom_brands(custom_brands_text):
        custom_brands_text = "\n".join(line for line in (custom_brands_text.strip(), brand_line) if line)
        save_settings({"custom_chain_brands": custom_brands_text})
    removed_names = prospect_repository.remove_chains(parse_custom_brands(custom_brands_text))
    if prospect_repository.get_prospect(prospect_identifier):
        # The typed brand may not appear in this prospect's names: the user's decision still applies to it
        removed_names.append(prospect_repository.get_prospect(prospect_identifier)["name"])
        prospect_repository.delete_prospect(prospect_identifier)
    return {"brand": brand_line, "removed": len(removed_names), "names": removed_names}


@application.get("/api/prospects/{prospect_identifier}")
async def get_prospect(prospect_identifier: int) -> dict:
    return require_prospect(prospect_identifier)


@application.patch("/api/prospects/{prospect_identifier}")
async def update_prospect(prospect_identifier: int, prospect_update: ProspectUpdate) -> dict:
    require_prospect(prospect_identifier)
    prospect_repository.update_prospect(prospect_identifier, prospect_update.model_dump(exclude_unset=True))
    return require_prospect(prospect_identifier)


@application.delete("/api/prospects/{prospect_identifier}")
async def delete_prospect(prospect_identifier: int) -> dict:
    require_prospect(prospect_identifier)
    prospect_repository.delete_prospect(prospect_identifier)
    return {"deleted": prospect_identifier}


@application.post("/api/prospects/{prospect_identifier}/activities")
async def add_activity(prospect_identifier: int, activity: ActivityCreate) -> dict:
    require_prospect(prospect_identifier)
    prospect_repository.add_activity(prospect_identifier, activity)
    return require_prospect(prospect_identifier)


@application.post("/api/scans")
async def create_scan(scan_request: ScanRequest) -> dict:
    prospect_identifiers = scan_request.prospect_ids or prospect_repository.list_prospect_ids(scan_request.only_unscanned, scan_request.all_with_website)
    if not prospect_identifiers:
        raise HTTPException(status_code=400, detail="Aucun prospect à analyser.")
    return start_scan_job(prospect_identifiers).to_dict()


@application.post("/api/website-discovery")
async def create_website_discovery(discovery_request: WebsiteDiscoveryRequest) -> dict:
    prospect_identifiers = discovery_request.prospect_ids or (prospect_repository.list_ids_without_website() if discovery_request.all_without_website else [])
    if not prospect_identifiers:
        raise HTTPException(status_code=400, detail="Aucun prospect sans site à traiter.")
    return start_website_discovery_job(prospect_identifiers).to_dict()


@application.post("/api/google-maps-enrichment")
async def create_google_maps_enrichment(enrichment_request: GoogleMapsEnrichmentRequest) -> dict:
    if job_manager.has_running_job("google_maps_search") or job_manager.has_running_job("google_maps_enrichment"):
        raise HTTPException(status_code=409, detail="Une session Google Maps est déjà en cours.")
    prospect_identifiers = enrichment_request.prospect_ids or (prospect_repository.list_ids_without_phone(enrichment_request.limit) if enrichment_request.all_without_phone else [])
    if not prospect_identifiers:
        raise HTTPException(status_code=400, detail="Aucun prospect à compléter.")
    return start_google_maps_enrichment(prospect_identifiers).to_dict()


@application.post("/api/prospects/{prospect_identifier}/reject-website")
async def reject_prospect_website(prospect_identifier: int) -> dict:
    require_prospect(prospect_identifier)
    prospect_repository.reject_website(prospect_identifier)
    return require_prospect(prospect_identifier)


@application.get("/api/follow-ups")
async def list_follow_ups(until: str | None = None) -> list[dict]:
    return prospect_repository.list_due_follow_ups(until or date.today().isoformat())


@application.get("/api/statistics")
async def get_statistics() -> dict:
    return prospect_repository.statistics()


@application.get("/api/jobs")
async def list_jobs() -> list[dict]:
    return job_manager.list_jobs()


@application.delete("/api/jobs/{job_identifier}")
async def remove_job(job_identifier: int) -> dict:
    return {"removed": job_manager.remove(job_identifier)}


@application.post("/api/jobs/clear")
async def clear_finished_jobs() -> dict:
    return {"removed": job_manager.clear_finished()}


@application.post("/api/jobs/{job_identifier}/cancel")
async def cancel_job(job_identifier: int) -> dict:
    return {"cancelled": job_manager.cancel(job_identifier)}


@application.get("/api/settings")
async def get_settings() -> dict:
    return load_settings()


@application.put("/api/settings")
async def update_settings(changes: dict[str, Any]) -> dict:
    return save_settings(changes)


@application.get("/api/system")
async def get_system_capabilities() -> dict:
    return {"lighthouse_installed": find_lighthouse_executable() is not None, **await describe_graphics_cards()}


@application.get("/api/llm/status")
async def get_language_model_status() -> dict:
    status_snapshot = ollama_service.status_snapshot()
    status_snapshot["reachable"] = await ollama_service.is_available()
    status_snapshot["installed_models"] = await ollama_service.list_installed_models() if status_snapshot["reachable"] else []
    return status_snapshot


@application.post("/api/llm/start")
async def start_language_model() -> dict:
    return await ollama_service.start_managed_server()


@application.post("/api/llm/stop")
async def stop_language_model() -> dict:
    return await ollama_service.stop_managed_server()


@application.post("/api/llm/pull")
async def pull_language_model() -> dict:
    settings = load_settings()
    model_names = [model_name for model_name in (settings["llm_model"], settings["llm_vision_model"]) if model_name]
    if not await ollama_service.is_available():
        raise HTTPException(status_code=400, detail="Le serveur Ollama ne répond pas : démarrez-le d'abord.")
    async def run(context: JobContext) -> None:
        for model_name in model_names:
            def report_progress(completed_bytes: int, total_bytes: int, status_text: str) -> None:
                context.set_progress(completed_bytes // 1_000_000, total_bytes // 1_000_000 or None, f"{model_name} : {status_text} ({completed_bytes // 1_000_000} / {total_bytes // 1_000_000} Mo)")
            await ollama_service.pull_model(model_name, report_progress)
            context.log(f"Modèle {model_name} prêt.")
    return job_manager.start("llm_pull", f"Téléchargement : {', '.join(model_names)}", run).to_dict()


@application.websocket("/ws")
async def stream_events(websocket: WebSocket) -> None:
    await websocket.accept()
    subscriber_queue = event_bus.subscribe()
    try:
        await websocket.send_json({"type": "jobs.snapshot", "payload": job_manager.list_jobs()})
        while True:
            await websocket.send_json(await subscriber_queue.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        event_bus.unsubscribe(subscriber_queue)
