"""Application paths and runtime constants."""
import os
from pathlib import Path

APPLICATION_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = Path(os.environ.get("PROSPECT_DATA_DIR", APPLICATION_ROOT / "data"))
DATABASE_PATH = DATA_DIRECTORY / "prospects.sqlite3"
SCREENSHOT_DIRECTORY = DATA_DIRECTORY / "screenshots"
GOOGLE_MAPS_PROFILE_DIRECTORY = DATA_DIRECTORY / "google_maps_profile"
GOOGLE_SEARCH_PROFILE_DIRECTORY = DATA_DIRECTORY / "google_search_profile"
WEB_DIRECTORY = APPLICATION_ROOT / "web"
SERVER_HOST = os.environ.get("PROSPECT_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("PROSPECT_PORT", "8765"))
# Browser-like identity used when visiting prospect websites
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
# Honest identity used for public open data APIs, as their usage policies require
OPEN_DATA_USER_AGENT = "ProspectSolution/1.0 (local prospecting tool)"


def ensure_data_directories() -> None:
    """Create every runtime directory used to persist data."""
    for directory in (DATA_DIRECTORY, SCREENSHOT_DIRECTORY, GOOGLE_MAPS_PROFILE_DIRECTORY, GOOGLE_SEARCH_PROFILE_DIRECTORY):
        directory.mkdir(parents=True, exist_ok=True)
