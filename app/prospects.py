"""Central prospect repository: matching, merging, updates and queries."""
import csv
import io
import json
import math
from typing import Any

from app.chains import detect_chain
from app.database import get_database, utc_now_iso
from app.deduplication import SAME_PHONE_SIMILARITY, find_duplicate_groups
from app.events import event_bus
from app.geo import haversine_distance_km
from app.models import CALL_OUTCOME_STATUSES, PROSPECT_STATUSES, ActivityCreate, ProspectCandidate
from app.text_utils import company_name_similarity, extract_domain, normalize_company_name, normalize_phone_number, normalize_website_url

STATUS_ORDER = list(PROSPECT_STATUSES)
KILOMETRES_PER_LATITUDE_DEGREE = 111.32
NEARBY_MATCH_DISTANCE_KM = 0.25
SAME_POSTAL_CODE_SIMILARITY = 0.9
NEARBY_SIMILARITY = 0.78
SAME_DOMAIN_MAX_DISTANCE_KM = 2.0
COORDINATE_SEARCH_MARGIN_DEGREES = 0.004
MERGEABLE_FIELDS = (
    "legal_name", "siret", "naf_code", "sector_key", "category_label", "company_category", "address", "postal_code",
    "city", "latitude", "longitude", "phone", "email", "website_url", "website_origin", "website_confidence", "social_url",
    "manager_name", "brand", "establishment_count", "creation_date", "employee_range", "employee_minimum", "google_rating", "google_review_count", "google_maps_url", "google_place_key",
)
# Values coming from these sources are refreshed on every import because they reflect live data
REFRESHED_FIELDS_BY_SOURCE = {"google_maps": ("google_rating", "google_review_count", "google_maps_url")}
OPPORTUNITY_RANK_SQL = "CASE opportunity_level WHEN 'no_website' THEN 0 WHEN 'hot' THEN 1 WHEN 'warm' THEN 2 WHEN 'cold' THEN 3 END"
STATUS_RANK_SQL = (
    "CASE status WHEN 'new' THEN 0 WHEN 'to_call' THEN 1 WHEN 'called_no_answer' THEN 2 WHEN 'callback' THEN 3 WHEN 'interested' THEN 4 "
    "WHEN 'meeting' THEN 5 WHEN 'quote_sent' THEN 6 WHEN 'won' THEN 7 WHEN 'lost' THEN 8 WHEN 'not_interested' THEN 9 END"
)
# Sort key: (SQL expression, natural direction); empty values always come last
SORTABLE_COLUMNS = {
    "opportunity": (OPPORTUNITY_RANK_SQL, "ASC"),
    "score": ("score", "ASC"),
    "name": ("name COLLATE NOCASE", "ASC"),
    "city": ("city COLLATE NOCASE", "ASC"),
    "phone": ("phone", "ASC"),
    "website": ("website_domain", "ASC"),
    "employees": ("employee_minimum", "DESC"),
    "status": (STATUS_RANK_SQL, "ASC"),
    "follow_up": ("next_follow_up", "ASC"),
    "recent": ("created_at", "DESC"),
}


def build_order_clause(sort_key: str | None, sort_direction: str | None) -> str:
    """Translate a sort request into an ORDER BY clause keeping empty values at the end."""
    expression, natural_direction = SORTABLE_COLUMNS.get(sort_key or "opportunity", SORTABLE_COLUMNS["opportunity"])
    direction = sort_direction.upper() if (sort_direction or "").upper() in ("ASC", "DESC") else natural_direction
    secondary_order = ", score ASC" if (sort_key or "opportunity") == "opportunity" else ""
    return f"({expression}) IS NULL, {expression} {direction}{secondary_order}, id DESC"
CSV_COLUMNS = (
    "id", "name", "legal_name", "category_label", "sector_key", "address", "postal_code", "city", "phone", "email",
    "website_url", "social_url", "employee_range", "manager_name", "distance_km", "score", "opportunity_level", "status", "next_follow_up", "google_rating",
    "google_review_count", "siret", "creation_date", "notes",
)


def read_search_area(filters: dict[str, Any]) -> tuple[float, float, float] | None:
    """Return the circle requested by the location filter, when complete."""
    try:
        center_latitude, center_longitude, radius_km = (float(filters[key]) for key in ("center_latitude", "center_longitude", "radius_km"))
    except (KeyError, TypeError, ValueError):
        return None
    return (center_latitude, center_longitude, radius_km) if radius_km > 0 else None


def filter_rows_by_distance(
    prospect_rows: list[dict[str, Any]], center_latitude: float, center_longitude: float, radius_km: float, sort_by_distance: bool, descending: bool,
) -> list[dict[str, Any]]:
    """Keep the prospects inside the circle, annotated with their distance to its center."""
    kept_rows = []
    for prospect_row in prospect_rows:
        if prospect_row["latitude"] is None or prospect_row["longitude"] is None:
            prospect_row["distance_km"] = None
            kept_rows.append(prospect_row)
            continue
        distance_km = haversine_distance_km(center_latitude, center_longitude, prospect_row["latitude"], prospect_row["longitude"])
        if distance_km <= radius_km:
            prospect_row["distance_km"] = round(distance_km, 1)
            kept_rows.append(prospect_row)
    if sort_by_distance:
        located_rows = sorted((row for row in kept_rows if row["distance_km"] is not None), key=lambda row: row["distance_km"], reverse=descending)
        kept_rows = located_rows + [row for row in kept_rows if row["distance_km"] is None]
    return kept_rows


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
            matching_row = database.fetch_one("SELECT * FROM prospects WHERE substr(siret, 1, 9) = ? ORDER BY id LIMIT 1", (candidate.siret[:9],))
            if matching_row:
                return matching_row
        if candidate.phone:
            for prospect_row in database.fetch_all("SELECT * FROM prospects WHERE phone = ?", (candidate.phone,)):
                if best_name_similarity(candidate, prospect_row) >= SAME_PHONE_SIMILARITY:
                    return prospect_row
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
            changes["website_confidence"] = "high" if changes["website_url"] else None
            changes["website_evidence"] = "saisi manuellement" if changes["website_url"] else None
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

    def record_website_check(
        self,
        prospect_identifier: int,
        website_url: str | None,
        website_origin: str | None = None,
        website_confidence: str | None = None,
        website_evidence: list[str] | None = None,
        social_url: str | None = None,
    ) -> None:
        """Store the outcome of an automatic website discovery."""
        changes: dict[str, Any] = {"website_check_done": 1}
        if website_url:
            changes.update({
                "website_url": website_url,
                "website_domain": extract_domain(website_url),
                "website_origin": website_origin,
                "website_confidence": website_confidence,
                "website_evidence": ", ".join(website_evidence or []) or None,
                "opportunity_level": None,
                "score": None,
            })
        else:
            changes["opportunity_level"] = "no_website"
        if social_url:
            changes["social_url"] = social_url
        self._write_changes(prospect_identifier, changes)
        event_bus.publish("prospect.updated", self.get_prospect(prospect_identifier))

    def enrich_from_listing(self, prospect_identifier: int, candidate: ProspectCandidate | None) -> None:
        """Complete a prospect with its Google Maps listing; a listing without website confirms the business has none."""
        prospect_row = self.get_prospect(prospect_identifier)
        if prospect_row is None:
            return
        if candidate is None:
            self._write_changes(prospect_identifier, {"google_maps_checked": 1})
            event_bus.publish("prospect.updated", self.get_prospect(prospect_identifier))
            return
        candidate.website_url = normalize_website_url(candidate.website_url)
        candidate.phone = normalize_phone_number(candidate.phone)
        self._merge_into_prospect(prospect_row, candidate)
        changes: dict[str, Any] = {"google_maps_checked": 1}
        if candidate.website_url and prospect_row["website_confidence"] != "high" and extract_domain(candidate.website_url) not in (prospect_row["rejected_domains"] or []):
            # The listing maintained by the owner is more reliable than an automatic guess
            changes.update({
                "website_url": candidate.website_url,
                "website_domain": extract_domain(candidate.website_url),
                "website_origin": "google_maps",
                "website_confidence": "high",
                "website_evidence": "site affiché sur la fiche Google Maps",
                "opportunity_level": None,
                "score": None,
            })
        elif not candidate.website_url and not prospect_row["website_url"]:
            changes.update({"website_check_done": 1, "opportunity_level": "no_website", "website_evidence": "aucun site sur la fiche Google Maps"})
        self._write_changes(prospect_identifier, changes)
        event_bus.publish("prospect.updated", self.get_prospect(prospect_identifier))

    def list_ids_without_phone(self, limit: int) -> list[int]:
        """Return prospects with no phone number never looked up on Google Maps, best opportunities first."""
        rows = get_database().fetch_all(
            f"SELECT id FROM prospects WHERE phone IS NULL AND google_maps_checked = 0 AND sources NOT LIKE '%google_maps%' ORDER BY {build_order_clause('opportunity', None)} LIMIT ?",
            (limit,),
        )
        return [row["id"] for row in rows]

    def merge_prospects(self, prospect_identifiers: list[int]) -> dict[str, Any] | None:
        """Merge several prospects into the oldest one: fields, sources, notes, pipeline, calls and scans."""
        prospect_rows = [row for row in (self.get_prospect(identifier) for identifier in sorted(set(prospect_identifiers))) if row]
        if len(prospect_rows) < 2:
            return prospect_rows[0] if prospect_rows else None
        target_row, *merged_rows = prospect_rows
        changes: dict[str, Any] = {}
        merged_values = dict(target_row)
        for merged_row in merged_rows:
            for field_name in (*MERGEABLE_FIELDS, "website_domain", "website_evidence"):
                if merged_values.get(field_name) in (None, "") and merged_row.get(field_name) not in (None, ""):
                    merged_values[field_name] = changes[field_name] = merged_row[field_name]
            if (merged_row.get("last_scan_at") or "") > (merged_values.get("last_scan_at") or ""):
                for field_name in ("score", "opportunity_level", "last_scan_at"):
                    merged_values[field_name] = changes[field_name] = merged_row[field_name]
            if STATUS_ORDER.index(merged_row["status"]) > STATUS_ORDER.index(merged_values["status"]):
                merged_values["status"] = changes["status"] = merged_row["status"]
            follow_up_dates = [date for date in (merged_values.get("next_follow_up"), merged_row.get("next_follow_up")) if date]
            if follow_up_dates and min(follow_up_dates) != merged_values.get("next_follow_up"):
                merged_values["next_follow_up"] = changes["next_follow_up"] = min(follow_up_dates)
        changes["sources"] = json.dumps(list(dict.fromkeys(source for row in prospect_rows for source in (row["sources"] or []))))
        changes["rejected_domains"] = json.dumps(list(dict.fromkeys(domain for row in prospect_rows for domain in (row["rejected_domains"] or []))))
        changes["notes"] = "\n".join(dict.fromkeys(row["notes"].strip() for row in prospect_rows if (row["notes"] or "").strip()))
        changes["website_check_done"] = max(row["website_check_done"] for row in prospect_rows)
        changes["google_maps_checked"] = max(row["google_maps_checked"] for row in prospect_rows)
        merged_identifiers = [row["id"] for row in merged_rows]
        placeholders = ", ".join("?" for _ in merged_identifiers)
        database = get_database()
        with database.transaction() as connection:
            connection.execute(f"UPDATE scans SET prospect_id = ? WHERE prospect_id IN ({placeholders})", (target_row["id"], *merged_identifiers))
            connection.execute(f"UPDATE activities SET prospect_id = ? WHERE prospect_id IN ({placeholders})", (target_row["id"], *merged_identifiers))
            connection.execute(f"DELETE FROM prospects WHERE id IN ({placeholders})", tuple(merged_identifiers))
        self._write_changes(target_row["id"], changes)
        for merged_identifier in merged_identifiers:
            event_bus.publish("prospect.deleted", {"id": merged_identifier, "merged_into": target_row["id"]})
        event_bus.publish("prospect.updated", self.get_prospect(target_row["id"]))
        return self.get_prospect(target_row["id"])

    def merge_all_duplicates(self) -> int:
        """Merge every group of prospects describing the same business; return how many prospects disappeared."""
        duplicate_groups = find_duplicate_groups(get_database().fetch_all("SELECT * FROM prospects"))
        for duplicate_group in duplicate_groups:
            self.merge_prospects(duplicate_group)
        return sum(len(duplicate_group) - 1 for duplicate_group in duplicate_groups)

    def save_diagnosis_overrides(self, prospect_identifier: int, overrides: dict[str, Any]) -> dict[str, Any] | None:
        """Store the corrections the user made to the analyzer's diagnosis."""
        if self.get_prospect(prospect_identifier) is None:
            return None
        self._write_changes(prospect_identifier, {"diagnosis_overrides": json.dumps(overrides, ensure_ascii=False)})
        return self.get_prospect(prospect_identifier)

    def reject_website(self, prospect_identifier: int) -> dict[str, Any] | None:
        """Discard a wrongly matched website and remember its domain so that it is never proposed again."""
        prospect_row = self.get_prospect(prospect_identifier)
        rejected_domains = list(prospect_row["rejected_domains"] or [])
        if prospect_row["website_domain"] and prospect_row["website_domain"] not in rejected_domains:
            rejected_domains.append(prospect_row["website_domain"])
        return self.update_prospect(prospect_identifier, {
            "website_url": None,
            "rejected_domains": json.dumps(rejected_domains),
            "website_check_done": 1,
        })

    def remove_chains(self, custom_brands: list[str] | None = None) -> list[str]:
        """Delete every prospect recognised as a chain or franchise and return their names."""
        removed_names = []
        for prospect_row in get_database().fetch_all("SELECT * FROM prospects"):
            names = [name for name in (prospect_row["name"], prospect_row["legal_name"]) if name]
            if detect_chain(names, prospect_row["website_url"], prospect_row["brand"], prospect_row["establishment_count"], custom_brands):
                get_database().execute("DELETE FROM prospects WHERE id = ?", (prospect_row["id"],))
                removed_names.append(prospect_row["name"])
        if removed_names:
            event_bus.publish("prospect.deleted", {"id": None})
        return removed_names

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
        search_area = read_search_area(filters)
        if search_area:
            center_latitude, center_longitude, radius_km = search_area
            latitude_margin = radius_km / KILOMETRES_PER_LATITUDE_DEGREE
            longitude_margin = radius_km / (KILOMETRES_PER_LATITUDE_DEGREE * max(math.cos(math.radians(center_latitude)), 0.1))
            # The bounding box keeps the query fast; prospects without coordinates are matched by their city name
            conditions.append("((latitude BETWEEN :minimum_latitude AND :maximum_latitude AND longitude BETWEEN :minimum_longitude AND :maximum_longitude) OR (latitude IS NULL AND city LIKE :area_city))")
            parameters.update({
                "minimum_latitude": center_latitude - latitude_margin, "maximum_latitude": center_latitude + latitude_margin,
                "minimum_longitude": center_longitude - longitude_margin, "maximum_longitude": center_longitude + longitude_margin,
                "area_city": filters.get("area_city") or "\u0000",
            })
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sort_key = filters.get("sort")
        order_clause = build_order_clause(None if sort_key == "distance" else sort_key, filters.get("sort_direction"))
        prospect_rows = get_database().fetch_all(f"SELECT * FROM prospects {where_clause} ORDER BY {order_clause} LIMIT 5000", parameters)
        if not search_area:
            return prospect_rows
        return filter_rows_by_distance(prospect_rows, *search_area, sort_by_distance=sort_key == "distance", descending=(filters.get("sort_direction") or "").lower() == "desc")

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

    def list_prospects_needing_website_check(self, prospect_identifiers: list[int], include_already_checked: bool = False) -> list[dict[str, Any]]:
        """Return prospects among the given ones that have no website, by default only those never checked."""
        if not prospect_identifiers:
            return []
        placeholders = ", ".join("?" for _ in prospect_identifiers)
        checked_condition = "" if include_already_checked else "AND website_check_done = 0"
        return get_database().fetch_all(
            f"SELECT * FROM prospects WHERE id IN ({placeholders}) AND website_url IS NULL {checked_condition}",
            tuple(prospect_identifiers),
        )

    def list_ids_without_website(self) -> list[int]:
        """Return identifiers of every prospect without a known website."""
        return [row["id"] for row in get_database().fetch_all("SELECT id FROM prospects WHERE website_url IS NULL ORDER BY id")]

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
