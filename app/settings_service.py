"""Persistent user settings stored in the database."""
import json
from pathlib import PureWindowsPath
from typing import Any

from app.database import get_database
from app.events import event_bus
from app.web_safety import is_web_url

DEFAULT_SETTINGS: dict[str, Any] = {
    "freelancer_first_name": "",
    "freelancer_last_name": "",
    "freelancer_company": "",
    "freelancer_city": "",
    "freelancer_phone": "",
    "freelancer_email": "",
    "freelancer_website": "",
    "auto_merge_duplicates": True,
    "custom_chain_brands": "",
    "saved_prospect_views": [],
    "sheet_show_employees": True,
    "sheet_show_contacts": True,
    "sheet_show_synthesis": True,
    "sheet_show_diagnosis": True,
    "sheet_show_script": True,
    "sheet_show_email": True,
    "sheet_show_technical": True,
    "sheet_show_history": True,
    "scan_concurrency": 3,
    "lighthouse_enabled": False,
    "search_engine_duckduckgo": True,
    "search_engine_bing": True,
    "search_engine_google_browser": False,
    "google_search_headless": False,
    "crawl_internal_pages": 4,
    "google_maps_headless": False,
    "google_maps_pause_min_seconds": 1.0,
    "google_maps_pause_max_seconds": 2.5,
    "llm_mode": "disabled",
    "llm_external_url": "http://127.0.0.1:11434",
    "llm_managed_port": 11435,
    "llm_gpu_uuid": "",
    "llm_model": "qwen2.5:7b-instruct",
    "llm_vision_model": "",
    "ollama_executable": "ollama",
}


MAXIMUM_SAVED_VIEWS_BYTES = 200_000
OLLAMA_EXECUTABLE_NAMES = ("ollama", "ollama.exe")


def validate_setting(key: str, value: Any) -> None:
    """Refuse values that would make the application run or contact something else than intended."""
    if key == "ollama_executable":
        executable_text = str(value or "").strip()
        if executable_text.startswith(("\\\\", "//")) or PureWindowsPath(executable_text).name.lower() not in OLLAMA_EXECUTABLE_NAMES:
            raise ValueError("L'exécutable doit être « ollama » ou le chemin local de ollama.exe.")
    elif key == "llm_external_url" and not is_web_url(str(value or "")):
        raise ValueError("L'adresse du serveur Ollama doit commencer par http:// ou https://.")
    elif key == "saved_prospect_views" and len(json.dumps(value)) > MAXIMUM_SAVED_VIEWS_BYTES:
        raise ValueError("Trop de vues enregistrées : supprimez-en quelques-unes.")


def load_settings() -> dict[str, Any]:
    """Return the effective settings, defaults merged with stored values."""
    stored_rows = get_database().fetch_all("SELECT key, value FROM settings")
    effective_settings = dict(DEFAULT_SETTINGS)
    for stored_row in stored_rows:
        if stored_row["key"] in DEFAULT_SETTINGS:
            effective_settings[stored_row["key"]] = json.loads(stored_row["value"])
    return effective_settings


def save_settings(changes: dict[str, Any]) -> dict[str, Any]:
    """Persist known settings, coercing each value to the type of its default."""
    database = get_database()
    for key, value in changes.items():
        if key in DEFAULT_SETTINGS:
            validate_setting(key, value)
    with database.transaction() as connection:
        for key, value in changes.items():
            if key not in DEFAULT_SETTINGS:
                continue
            default_value = DEFAULT_SETTINGS[key]
            coerced_value = type(default_value)(value) if default_value is not None and value is not None else value
            connection.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(coerced_value)),
            )
    effective_settings = load_settings()
    event_bus.publish("settings.updated", effective_settings)
    return effective_settings
