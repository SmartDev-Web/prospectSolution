import asyncio
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import API_VERSION
from app.main import application
from app.models import ProspectCandidate
from app.prospects import neutralize_spreadsheet_formula, prospect_repository
from app.relevance import find_non_business_reason, find_sector_by_category
from app.scanner.lighthouse import build_shell_safe_target
from app.settings_service import validate_setting
from app.sources.google_maps import describe_card_rejection, parse_place
from app.sectors import SECTORS_BY_KEY
from app.text_utils import normalize_website_url
from app.web_safety import is_public_address, is_public_web_url


def test_charging_stations_and_public_places_are_not_prospects():
    assert find_non_business_reason(["Tesla Supercharger"], "Borne de recharge pour véhicules électriques")
    assert find_non_business_reason(["Station Total"], "Station de recharge pour véhicules électriques")
    assert find_non_business_reason(["IZIVIA Lattes"], None)
    assert find_non_business_reason(["Parking Comédie"], "Parking")
    assert find_non_business_reason(["Taxis gare"], "Station de taxis")
    assert find_non_business_reason(["Le Petit Bistrot"], "Restaurant") is None
    assert find_non_business_reason(["Aqualand"], "Parc d'attractions") is None
    assert find_non_business_reason(["Taxi Dupont"], "Service de taxi") is None


def test_google_category_designates_the_sector():
    assert find_sector_by_category("Restaurant italien").key == "restaurant"
    assert find_sector_by_category("Pizzeria").key == "restaurant"
    assert find_sector_by_category("Fleuriste").key == "florist"
    assert find_sector_by_category("Service de taxi").key == "transport"
    assert find_sector_by_category("Boulangerie pâtisserie").key == "bakery"
    assert find_sector_by_category("Fournisseur de satellites") is None


def test_google_listing_takes_the_sector_of_its_category():
    candidate = parse_place(
        {"name": "Fleurs d'Amandine", "category": "Fleuriste", "addressLabel": "Adresse: 1 rue X, 34970 Lattes"},
        "https://www.google.com/maps/place/x/data=!3d43.56!4d3.90!1s0x12b6:0x34",
        SECTORS_BY_KEY["restaurant"],
    )
    assert candidate.sector_key == "florist"
    assert candidate.google_place_key == "0x12b6:0x34"


def test_result_card_of_a_charging_station_is_skipped_without_opening():
    assert describe_card_rejection("Electra Lattes\n4,2(12)\nBorne de recharge pour véhicules électriques · Rue X")
    assert describe_card_rejection("La Table de Jean\n4,6(230)\nRestaurant · 12 rue Y\nOuvert") is None


def test_off_target_places_are_removed_with_chains():
    prospect_repository.upsert_prospect(ProspectCandidate(name="Borne Freshmile", source="google_maps", category_label="Borne de recharge pour véhicules électriques"))
    prospect_repository.upsert_prospect(ProspectCandidate(name="Fleurs de Lattes", source="google_maps", category_label="Fleuriste"))
    assert prospect_repository.remove_off_target_prospects([]) == ["Borne Freshmile"]


def test_only_web_addresses_are_stored_as_links():
    assert normalize_website_url("javascript://%0aalert(1)") is None
    assert normalize_website_url("file:///C:/Windows/win.ini") is None
    assert normalize_website_url("fleurs-lattes.fr") == "http://fleurs-lattes.fr"
    prospect_identifier, _created = prospect_repository.upsert_prospect(ProspectCandidate(name="Piège", source="openstreetmap", website_url="javascript:alert(1)", social_url="javascript:alert(2)"))
    stored_prospect = prospect_repository.get_prospect(prospect_identifier)
    assert stored_prospect["website_url"] is None and stored_prospect["social_url"] is None


def test_private_and_local_destinations_are_refused():
    assert not is_public_address("127.0.0.1")
    assert not is_public_address("192.168.1.10")
    assert not is_public_address("169.254.169.254")
    assert not is_public_address("::ffff:10.0.0.1")
    assert is_public_address("8.8.8.8")
    assert not asyncio.run(is_public_web_url("http://127.0.0.1:8765/api/settings"))
    assert not asyncio.run(is_public_web_url("file:///etc/passwd"))


def test_csv_cells_cannot_run_formulas():
    assert neutralize_spreadsheet_formula('=HYPERLINK("http://x")') == "'=HYPERLINK(\"http://x\")"
    assert neutralize_spreadsheet_formula("Boulangerie") == "Boulangerie"
    assert neutralize_spreadsheet_formula(12) == 12


def test_lighthouse_only_receives_shell_safe_urls():
    assert build_shell_safe_target("https://a.fr/page?x=1&y=2") == "https://a.fr/page"
    assert build_shell_safe_target("https://evil.com/&\\\\evil\\s") is None


def test_settings_refuse_foreign_executables():
    validate_setting("ollama_executable", "ollama")
    for refused_value in ("\\\\evil\\share\\ollama.exe", "C:\\Temp\\calc.exe"):
        try:
            validate_setting("ollama_executable", refused_value)
        except ValueError:
            continue
        raise AssertionError(f"{refused_value} was accepted")


def test_api_refuses_foreign_hosts_and_origins():
    client = TestClient(application, base_url="http://127.0.0.1:8765")
    assert client.get("/api/health").json() == {"api_version": API_VERSION}
    assert TestClient(application, base_url="http://attacker.example").get("/api/health").status_code == 400
    assert client.post("/api/prospects/merge-duplicates", headers={"Origin": "http://attacker.example"}).status_code == 403
    assert client.post("/api/prospects/merge-duplicates", headers={"Origin": "http://127.0.0.1:8765"}).status_code == 200
    assert client.get("/").headers["cache-control"] == "no-cache"


def test_page_and_server_share_the_same_contract_version():
    version_source = (Path(__file__).resolve().parent.parent / "web" / "js" / "version.js").read_text(encoding="utf-8")
    assert int(re.search(r"API_VERSION = (\d+)", version_source).group(1)) == API_VERSION


def test_statistics_count_missing_phones_and_due_follow_ups():
    prospect_repository.upsert_prospect(ProspectCandidate(name="Sans Téléphone", source="manual"))
    prospect_identifier, _created = prospect_repository.upsert_prospect(ProspectCandidate(name="Avec Téléphone", source="manual", phone="0467000000", website_url="https://avec.fr"))
    prospect_repository.update_prospect(prospect_identifier, {"next_follow_up": "2000-01-01"})
    statistics = prospect_repository.statistics()
    assert (statistics["total"], statistics["without_phone"], statistics["follow_ups_due"]) == (2, 1, 1)
