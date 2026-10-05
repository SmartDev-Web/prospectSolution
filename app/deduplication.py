"""Detection of stored prospects describing the same business, so that they can be merged."""
from collections import defaultdict
from typing import Any

from app.geo import haversine_distance_km
from app.text_utils import company_name_similarity

SAME_PLACE_DISTANCE_KM = 0.25
SAME_PLACE_SIMILARITY = 0.78
SAME_POSTAL_CODE_SIMILARITY = 0.9
SAME_DOMAIN_DISTANCE_KM = 2.0
SAME_PHONE_SIMILARITY = 0.5
GRID_CELL_DEGREES = 0.01


def row_names(prospect_row: dict[str, Any]) -> list[str]:
    return [name for name in (prospect_row.get("name"), prospect_row.get("legal_name")) if name]


def name_similarity(first_row: dict[str, Any], second_row: dict[str, Any]) -> float:
    """Return the highest similarity between the names of two prospects."""
    return max((company_name_similarity(first_name, second_name) for first_name in row_names(first_row) for second_name in row_names(second_row)), default=0.0)


def distance_between_km(first_row: dict[str, Any], second_row: dict[str, Any]) -> float | None:
    """Return the distance between two located prospects."""
    coordinates = (first_row.get("latitude"), first_row.get("longitude"), second_row.get("latitude"), second_row.get("longitude"))
    return None if None in coordinates else haversine_distance_km(*coordinates)


def rows_describe_same_business(first_row: dict[str, Any], second_row: dict[str, Any]) -> bool:
    """Tell whether two stored prospects are the same business, from identifiers first, then from name and place."""
    if first_row.get("siret") and second_row.get("siret"):
        # Establishments of one company share a website and a decision maker: the SIREN identifies the prospect
        return first_row["siret"][:9] == second_row["siret"][:9]
    if first_row.get("google_place_key") and first_row.get("google_place_key") == second_row.get("google_place_key"):
        return True
    distance_km = distance_between_km(first_row, second_row)
    similarity = name_similarity(first_row, second_row)
    if first_row.get("website_domain") and first_row.get("website_domain") == second_row.get("website_domain"):
        if distance_km is None or distance_km <= SAME_DOMAIN_DISTANCE_KM:
            return True
    if first_row.get("phone") and first_row.get("phone") == second_row.get("phone") and similarity >= SAME_PHONE_SIMILARITY:
        return True
    if distance_km is not None and distance_km <= SAME_PLACE_DISTANCE_KM and similarity >= SAME_PLACE_SIMILARITY:
        return True
    same_postal_code = first_row.get("postal_code") and first_row.get("postal_code") == second_row.get("postal_code")
    return bool(same_postal_code) and similarity >= SAME_POSTAL_CODE_SIMILARITY


def blocking_keys(prospect_row: dict[str, Any]) -> list[str]:
    """Return the buckets a prospect belongs to, so that only plausible pairs are compared."""
    keys = [f"{key_name}:{prospect_row[key_name]}" for key_name in ("google_place_key", "website_domain", "phone", "postal_code") if prospect_row.get(key_name)]
    if prospect_row.get("siret"):
        keys.append(f"siren:{prospect_row['siret'][:9]}")
    if prospect_row.get("latitude") is not None and prospect_row.get("longitude") is not None:
        cell_latitude = int(prospect_row["latitude"] // GRID_CELL_DEGREES)
        cell_longitude = int(prospect_row["longitude"] // GRID_CELL_DEGREES)
        # A business near a cell border is also compared with the neighbouring cells
        keys += [f"cell:{cell_latitude + latitude_offset}:{cell_longitude + longitude_offset}" for latitude_offset in (-1, 0, 1) for longitude_offset in (-1, 0, 1)]
    return keys


def find_duplicate_groups(prospect_rows: list[dict[str, Any]]) -> list[list[int]]:
    """Group the identifiers of prospects describing the same business, oldest first."""
    parent_by_identifier = {prospect_row["id"]: prospect_row["id"] for prospect_row in prospect_rows}
    def find_root(identifier: int) -> int:
        while parent_by_identifier[identifier] != identifier:
            parent_by_identifier[identifier] = parent_by_identifier[parent_by_identifier[identifier]]
            identifier = parent_by_identifier[identifier]
        return identifier
    rows_by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prospect_row in prospect_rows:
        for bucket_key in blocking_keys(prospect_row):
            rows_by_bucket[bucket_key].append(prospect_row)
    compared_pairs: set[tuple[int, int]] = set()
    for bucket_rows in rows_by_bucket.values():
        for first_index, first_row in enumerate(bucket_rows):
            for second_row in bucket_rows[first_index + 1:]:
                pair = (min(first_row["id"], second_row["id"]), max(first_row["id"], second_row["id"]))
                if pair in compared_pairs:
                    continue
                compared_pairs.add(pair)
                if rows_describe_same_business(first_row, second_row):
                    first_root, second_root = find_root(pair[0]), find_root(pair[1])
                    parent_by_identifier[max(first_root, second_root)] = min(first_root, second_root)
    groups: dict[int, list[int]] = defaultdict(list)
    for identifier in sorted(parent_by_identifier):
        groups[find_root(identifier)].append(identifier)
    return [group for group in groups.values() if len(group) > 1]
