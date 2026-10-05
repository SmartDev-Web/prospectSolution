"""Geocoding and distance helpers."""
import math
from dataclasses import dataclass

from app.http_client import create_open_data_client, request_json_with_retries

GEOCODING_URL = "https://data.geopf.fr/geocodage/search"
EARTH_RADIUS_KM = 6371.0


@dataclass
class GeocodedPlace:
    """A place resolved from a free text search."""
    label: str
    latitude: float
    longitude: float
    postal_code: str | None
    city: str | None
    place_type: str


def haversine_distance_km(first_latitude: float, first_longitude: float, second_latitude: float, second_longitude: float) -> float:
    """Return the great-circle distance between two coordinates in kilometres."""
    latitude_delta = math.radians(second_latitude - first_latitude)
    longitude_delta = math.radians(second_longitude - first_longitude)
    haversine_term = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(math.radians(first_latitude)) * math.cos(math.radians(second_latitude)) * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(haversine_term))


def is_within_radius(center_latitude: float, center_longitude: float, radius_km: float, latitude: float | None, longitude: float | None) -> bool:
    """Tell whether a coordinate lies inside the search circle (unknown coordinates are kept)."""
    if latitude is None or longitude is None:
        return True
    return haversine_distance_km(center_latitude, center_longitude, latitude, longitude) <= radius_km


async def geocode(query: str, limit: int = 6) -> list[GeocodedPlace]:
    """Resolve a French address or municipality using the national geocoding service."""
    async with create_open_data_client() as client:
        response_body = await request_json_with_retries(client, "GET", GEOCODING_URL, params={"q": query, "limit": limit, "index": "address"})
    geocoded_places = []
    for feature in response_body.get("features", []):
        longitude, latitude = feature["geometry"]["coordinates"]
        properties = feature.get("properties", {})
        geocoded_places.append(GeocodedPlace(
            label=properties.get("label", query),
            latitude=latitude,
            longitude=longitude,
            postal_code=properties.get("postcode"),
            city=properties.get("city"),
            place_type=properties.get("type", ""),
        ))
    return geocoded_places
