"""Central prospect repository: matching, merging, updates and queries."""
import csv
import io
import json
from typing import Any

from app.database import get_database, utc_now_iso
from app.events import event_bus
from app.geo import haversine_distance_km
from app.models import CALL_OUTCOME_STATUSES, ActivityCreate, ProspectCandidate
from app.text_utils import company_name_similarity, extract_domain, normalize_company_name, normalize_phone_number, normalize_website_url

NEARBY_MATCH_DISTANCE_KM = 0.25
SAME_POSTAL_CODE_SIMILARITY = 0.9
NEARBY_SIMILARITY = 0.78
SAME_DOMAIN_MAX_DISTANCE_KM = 2.0
COORDINATE_SEARCH_MARGIN_DEGREES = 0.004
MERGEABLE_FIELDS = (
    "legal_name", "siret", "naf_code", "sector_key", "category_label", "company_category", "address", "postal_code",
    "city", "latitude", "longitude", "phone", "email", "website_url", "website_origin", "social_url", "creation_date",
    "employee_range", "google_rating", "google_review_count", "google_maps_url", "google_place_key",
)
# Values coming from these sources are refreshed on every import because they reflect live data
REFRESHED_FIELDS_BY_SOURCE = {"google_maps": ("google_rating", "google_review_count", "google_maps_url")}
SORTABLE_COLUMNS = {
    "opportunity": "CASE opportunity_level WHEN 'no_website' THEN 0 WHEN 'hot' THEN 1 WHEN 'warm' THEN 2 WHEN 'cold' THEN 3 ELSE 4 END, score ASC",
    "score": "score IS NULL, score ASC",
    "name": "name COLLATE NOCASE ASC",
    "recent": "created_at DESC",
    "follow_up": "next_follow_up IS NULL, next_follow_up ASC",
}
CSV_COLUMNS = (
    "id", "name", "legal_name", "category_label", "sector_key", "address", "postal_code", "city", "phone", "email",
    "website_url", "social_url", "score", "opportunity_level", "status", "next_follow_up", "google_rating",
    "google_review_count", "siret", "creation_date", "notes",
)


def candidate_names(candidate: ProspectCandidate) -> list[str]:
    """List every name under which a candidate may already be known."""
    return [name for name in (candidate.name, candidate.legal_name, *candidate.alternative_names) if name]


def best_name_similarity(candidate: ProspectCandidate, prospect_row: dict[str, Any]) -> float:
    """Return the highest similarity between any candidate name and any stored name."""
    stored_names = [name for name in (prospect_row["name"], prospect_row["legal_name"]) if name]
    return max((company_name_similarity(first_name, second_name) for first_name in candidate_names(candidate) for second_name in stored_names), default=0.0)


def distance_to_row_km(candidate: ProspectCandidate, prospect_row: dict[str, Any]) -> float | None:
    """Return the distance between a candidate and a stored prospect when both are located."""
    if None in (candidate.latitude, candidate.longitude, prospect_row["latitude"], prospect_row["longitude"]):
        return None
    return haversine_distance_km(candidate.latitude, candidate.longitude, prospect_row["latitude"], prospect_row["longitude"])


class ProspectRepository:
    """Every read and write on prospects goes through this class."""

    def find_matching_prospect(self, candidate: ProspectCandidate) -> dict[str, Any] | None:
        """Find an existing prospect describing the same business as the candidate."""
        database = get_database()
        if candidate.google_place_key:
            matching_row = database.fetch_one("SELECT * FROM prospects WHERE google_place_key = ?", (candidate.google_place_key,))
            if matching_row:
                return matching_row
        if candidate.siret:
            matching_row = database.fetch_one("SELECT * FROM prospects WHERE siret = ?", (candidate.siret,))
            if matching_row:
                return matching_row
        website_domain = extract_domain(candidate.website_url)
        if website_domain:
            for prospect_row in database.fetch_all("SELECT * FROM prospects WHERE website_domain = ?", (website_domain,)):
                distance_km = distance_to_row_km(candidate, prospect_row)
                if distance_km is None or distance_km <= SAME_DOMAIN_MAX_DISTANCE_KM:
                    return prospect_row
        if candidate.latitude is not None and candidate.longitude is not None:
            nearby_rows = database.fetch_all(
                "SELECT * FROM prospects WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?",
                (
                    candidate.latitude - COORDINATE_SEARCH_MARGIN_DEGREES, candidate.latitude + COORDINATE_SEARCH_MARGIN_DEGREES,
                    candidate.longitude - COORDINATE_SEARCH_MARGIN_DEGREES * 1.5, candidate.longitude + COORDINATE_SEARCH_MARGIN_DEGREES * 1.5,
                ),
            )
            scored_rows = [
                (best_name_similarity(candidate, prospect_row), prospect_row)
                for prospect_row in nearby_rows
                if (distance_to_row_km(candidate, prospect_row) or 0.0) <= NEARBY_MATCH_DISTANCE_KM
            ]
            scored_rows = [scored_row for scored_row in scored_rows if scored_row[0] >= NEARBY_SIMILARITY]
            if scored_rows:
                return max(scored_rows, key=lambda scored_row: scored_row[0])[1]
        if candidate.postal_code:
            for prospect_row in database.fetch_all("SELECT * FROM prospects WHERE postal_code = ?", (candidate.postal_code,)):
                if best_name_similarity(candidate, prospect_row) >= SAME_POSTAL_CODE_SIMILARITY:
                    return prospect_row
        return None

    def upsert_prospect(self, candidate: ProspectCandidate) -> tuple[int, bool]:
        """Insert a new prospect or enrich the matching one; return its id and whether it was created."""
        candidate.website_url = normalize_website_url(candidate.website_url)
        candidate.phone = normalize_phone_number(candidate.phone)
        existing_row = self.find_matching_prospect(candidate)
        if existing_row is None:
            prospect_identifier = self._insert_prospect(candidate)
            created = True
        else:
            prospect_identifier = existing_row["id"]
            self._merge_into_prospect(existing_row, candidate)
            created = False
        event_bus.publish("prospect.upserted", {"id": prospect_identifier, "created": created})
        return prospect_identifier, created

    def _insert_prospect(self, candidate: ProspectCandidate) -> int:
        current_time = utc_now_iso()
        values = {field_name: getattr(candidate, field_name) for field_name in MERGEABLE_FIELDS}
        values.update({
            "name": candidate.name.strip(),
            "normalized_name": normalize_company_name(candidate.name),
            "website_domain": extract_domain(candidate.website_url),
            "sources": json.dumps([candidate.source]),
            "opportunity_level": None if candidate.website_url else "unknown_website",
            "created_at": current_time,
            "updated_at": current_time,
        })
        column_names = ", ".join(values)
        placeholders = ", ".join(f":{column_name}" for column_name in values)
        cursor = get_database().execute(f"INSERT INTO prospects ({column_names}) VALUES ({placeholders})", values)
        return cursor.lastrowid

    def _merge_into_prospect(self, existing_row: dict[str, Any], candidate: ProspectCandidate) -> None:
        refreshed_fields = REFRESHED_FIELDS_BY_SOURCE.get(candidate.source, ())
        changes: dict[str, Any] = {}
        for field_name in MERGEABLE_FIELDS:
            candidate_value = getattr(candidate, field_name)
            if candidate_value in (None, ""):
                continue
            if existing_row[field_name] in (None, "") or field_name in refreshed_fields:
                changes[field_name] = candidate_value
        if "website_url" in changes:
            changes["website_domain"] = extract_domain(changes["website_url"])
            if existing_row["opportunity_level"] in ("unknown_website", "no_website"):
                changes["opportunity_level"] = None
        merged_sources = list(dict.fromkeys([*(existing_row["sources"] or []), candidate.source]))
        if merged_sources != existing_row["sources"]:
            changes["sources"] = json.dumps(merged_sources)
        if changes:
            self._write_changes(existing_row["id"], changes)

    def _write_changes(self, prospect_identifier: int, changes: dict[str, Any]) -> None:
        changes["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{column_name} = :{column_name}" for column_name in changes)
        get_database().execute(f"UPDATE prospects SET {assignments} WHERE id = :identifier", {**changes, "identifier": prospect_identifier})

    def update_prospect(self, prospect_identifier: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        """Apply user edits to a prospect and broadcast the new state."""
        if "name" in changes and changes["name"]:
            changes["normalized_name"] = normalize_company_name(changes["name"])
        if "website_url" in changes:
            changes["website_url"] = normalize_website_url(changes["website_url"])
            changes["website_domain"] = extract_domain(changes["website_url"])
            changes["website_origin"] = "manual" if changes["website_url"] else None
            changes["opportunity_level"] = None if changes["website_url"] else "no_website"
            changes["score"] = None
        if "phone" in changes:
            changes["phone"] = normalize_phone_number(changes["phone"])
        if changes:
            self._write_changes(prospect_identifier, changes)
        updated_prospect = self.get_prospect(prospect_identifier)
        if updated_prospect:
            event_bus.publish("prospect.updated", updated_prospect)
        return updated_prospect

    def record_website_check(self, prospect_identifier: int, website_url: str | None, website_origin: str | None, social_url: str | None) -> None:
        """Store the outcome of an automatic website discovery."""
        changes: dict[str, Any] = {"website_check_done": 1}
        if website_url:
            changes.update({"website_url": website_url, "website_domain": extract_domain(website_url), "website_origin": website_origin, "opportunity_level": None})
        else:
            changes["opportunity_level"] = "no_website"
        if social_url:
            changes["social_url"] = social_url
        self._write_changes(prospect_identifier, changes)
        event_bus.publish("prospect.updated", self.get_prospect(prospect_identifier))

    def apply_scan_result(self, prospect_identifier: int, score: int | None, opportunity_level: str, contact_changes: dict[str, Any]) -> None:
        """Copy the outcome of a website scan onto the prospect."""
        prospect_row = self.get_prospect(prospect_identifier)
        changes: dict[str, Any] = {"score": score, "opportunity_level": opportunity_level, "last_scan_at": utc_now_iso()}
        for field_name, field_value in contact_changes.items():
            if field_value and not prospect_row.get(field_name):
                changes[field_name] = field_value
        self._write_changes(prospect_identifier, changes)
        event_bus.publish("prospect.updated", self.get_prospect(prospect_identifier))

    def get_prospect(self, prospect_identifier: int) -> dict[str, Any] | None:
        """Return a single prospect row."""
        return get_database().fetch_one("SELECT * FROM prospects WHERE id = ?", (prospect_identifier,))

    def get_prospect_detail(self, prospect_identifier: int) -> dict[str, Any] | None:
        """Return a prospect with its latest scan and its activity history."""
        prospect_row = self.get_prospect(prospect_identifier)
        if prospect_row is None:
            return None
        database = get_database()
        prospect_row["latest_scan"] = database.fetch_one("SELECT * FROM scans WHERE prospect_id = ? ORDER BY scanned_at DESC, id DESC LIMIT 1", (prospect_identifier,))
        prospect_row["activities"] = database.fetch_all("SELECT * FROM activities WHERE prospect_id = ? ORDER BY created_at DESC, id DESC", (prospect_identifier,))
        return prospect_row

    def list_prospects(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Query prospects with optional filters and ordering."""
        conditions: list[str] = []
        parameters: dict[str, Any] = {}
        if filters.get("status"):
            conditions.append("status = :status")
            parameters["status"] = filters["status"]
        if filters.get("sector_key"):
            conditions.append("sector_key = :sector_key")
            parameters["sector_key"] = filters["sector_key"]
        if filters.get("opportunity_level"):
            conditions.append("opportunity_level = :opportunity_level")
            parameters["opportunity_level"] = filters["opportunity_level"]
        if filters.get("website") == "with":
            conditions.append("website_url IS NOT NULL")
        elif filters.get("website") == "without":
            conditions.append("website_url IS NULL")
        if filters.get("search_text"):
            conditions.append("(name LIKE :search_text OR legal_name LIKE :search_text OR city LIKE :search_text OR website_url LIKE :search_text)")
            parameters["search_text"] = f"%{filters['search_text']}%"
        if filters.get("source"):
            conditions.append("sources LIKE :source")
            parameters["source"] = f'%"{filters["source"]}"%'
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order_clause = SORTABLE_COLUMNS.get(filters.get("sort") or "opportunity", SORTABLE_COLUMNS["opportunity"])
        return get_database().fetch_all(f"SELECT * FROM prospects {where_clause} ORDER BY {order_clause}, id DESC LIMIT 5000", parameters)

    def list_due_follow_ups(self, until_date: str) -> list[dict[str, Any]]:
        """Return prospects whose follow-up date is due, plus fresh hot prospects to call."""
        return get_database().fetch_all(
            """
            SELECT * FROM prospects
            WHERE (next_follow_up IS NOT NULL AND next_follow_up <= :until_date AND status NOT IN ('won', 'lost', 'not_interested'))
            ORDER BY next_follow_up ASC, id ASC
            """,
            {"until_date": until_date},
        )

    def list_prospect_ids(self, only_unscanned: bool, all_with_website: bool) -> list[int]:
        """Return identifiers of prospects eligible for a bulk scan."""
        conditions = ["website_url IS NOT NULL"] if all_with_website else []
        if only_unscanned:
            conditions.append("last_scan_at IS NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return [row["id"] for row in get_database().fetch_all(f"SELECT id FROM prospects {where_clause} ORDER BY id")]

    def list_prospects_needing_website_check(self, prospect_identifiers: list[int]) -> list[dict[str, Any]]:
        """Return prospects among the given ones without a website that were never checked."""
        if not prospect_identifiers:
            return []
        placeholders = ", ".join("?" for _ in prospect_identifiers)
        return get_database().fetch_all(
            f"SELECT * FROM prospects WHERE id IN ({placeholders}) AND website_url IS NULL AND website_check_done = 0",
            tuple(prospect_identifiers),
        )

    def delete_prospect(self, prospect_identifier: int) -> None:
        """Delete a prospect with its scans and activities."""
        get_database().execute("DELETE FROM prospects WHERE id = ?", (prospect_identifier,))
        event_bus.publish("prospect.deleted", {"id": prospect_identifier})

    def add_activity(self, prospect_identifier: int, activity: ActivityCreate) -> dict[str, Any] | None:
        """Log an interaction and move the prospect forward in the pipeline accordingly."""
        get_database().execute(
            "INSERT INTO activities (prospect_id, created_at, kind, outcome, content) VALUES (?, ?, ?, ?, ?)",
            (prospect_identifier, utc_now_iso(), activity.kind, activity.outcome, activity.content),
        )
        changes: dict[str, Any] = {}
        if activity.kind == "call" and activity.outcome in CALL_OUTCOME_STATUSES:
            changes["status"] = CALL_OUTCOME_STATUSES[activity.outcome]
        if activity.next_follow_up is not None:
            changes["next_follow_up"] = activity.next_follow_up or None
        elif activity.outcome in ("not_interested",):
            changes["next_follow_up"] = None
        return self.update_prospect(prospect_identifier, changes)

    def export_csv(self, filters: dict[str, Any]) -> str:
        """Export filtered prospects as a semicolon separated CSV readable by Excel."""
        output_buffer = io.StringIO()
        csv_writer = csv.DictWriter(output_buffer, fieldnames=CSV_COLUMNS, delimiter=";", extrasaction="ignore")
        csv_writer.writeheader()
        for prospect_row in self.list_prospects(filters):
            csv_writer.writerow({column_name: prospect_row.get(column_name) for column_name in CSV_COLUMNS})
        return "﻿" + output_buffer.getvalue()

    def statistics(self) -> dict[str, Any]:
        """Return pipeline counters displayed on the dashboard."""
        database = get_database()
        status_rows = database.fetch_all("SELECT status, COUNT(*) AS total FROM prospects GROUP BY status")
        opportunity_rows = database.fetch_all("SELECT COALESCE(opportunity_level, 'unscanned') AS level, COUNT(*) AS total FROM prospects GROUP BY level")
        total_row = database.fetch_one("SELECT COUNT(*) AS total FROM prospects")
        return {
            "total": total_row["total"],
            "by_status": {row["status"]: row["total"] for row in status_rows},
            "by_opportunity": {row["level"]: row["total"] for row in opportunity_rows},
        }


prospect_repository = ProspectRepository()
