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
from app.llm.gpu import list_graphics_cards
from app.llm.ollama import ollama_service
from app.models import ActivityCreate, GoogleMapsSearchRequest, OpenDataSearchRequest, ProspectCandidate, ProspectCreate, ProspectUpdate, ScanRequest
from app.prospects import prospect_repository
from app.scanner.lighthouse import find_lighthouse_executable
from app.sectors import get_sector, serialize_sectors
from app.settings_service import load_settings, save_settings
from app.workflows import start_google_maps_search, start_open_data_search, start_scan_job

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
    if job_manager.has_running_job("google_maps_search"):
        raise HTTPException(status_code=409, detail="Une session Google Maps est déjà en cours.")
    try:
        return start_google_maps_search(search_request).to_dict()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def read_prospect_filters(
    status: str | None = None,
    sector_key: str | None = None,
    opportunity_level: str | None = None,
    website: str | None = None,
    search_text: str | None = None,
    source: str | None = None,
    sort: str | None = None,
) -> dict[str, str | None]:
    """Collect the prospect list filters shared by the list and export endpoints."""
    return {
        "status": status, "sector_key": sector_key, "opportunity_level": opportunity_level, "website": website,
        "search_text": search_text, "source": source, "sort": sort,
    }


@application.get("/api/prospects")
async def list_prospects(prospect_filters: dict = Depends(read_prospect_filters)) -> list[dict]:
    return prospect_repository.list_prospects(prospect_filters)


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


@application.get("/api/follow-ups")
async def list_follow_ups(until: str | None = None) -> list[dict]:
    return prospect_repository.list_due_follow_ups(until or date.today().isoformat())


@application.get("/api/statistics")
async def get_statistics() -> dict:
    return prospect_repository.statistics()


@application.get("/api/jobs")
async def list_jobs() -> list[dict]:
    return job_manager.list_jobs()


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
    return {"lighthouse_installed": find_lighthouse_executable() is not None, "graphics_cards": await list_graphics_cards()}


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
    model_name = load_settings()["llm_model"]
    if not await ollama_service.is_available():
        raise HTTPException(status_code=400, detail="Le serveur Ollama ne répond pas : démarrez-le d'abord.")
    async def run(context: JobContext) -> None:
        def report_progress(completed_bytes: int, total_bytes: int, status_text: str) -> None:
            context.set_progress(completed_bytes // 1_000_000, total_bytes // 1_000_000 or None, f"{status_text} ({completed_bytes // 1_000_000} / {total_bytes // 1_000_000} Mo)")
        await ollama_service.pull_model(model_name, report_progress)
        context.log(f"Modèle {model_name} prêt.")
    return job_manager.start("llm_pull", f"Téléchargement du modèle {model_name}", run).to_dict()


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
