"""Business search through OpenStreetMap using the Overpass API."""
import logging

import httpx

from app.http_client import OpenDataError, create_open_data_client
from app.models import ProspectCandidate, SearchArea
from app.sectors import Sector, find_sector_by_osm_tags

logger = logging.getLogger(__name__)
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
OVERPASS_TIMEOUT_SECONDS = 90


def build_overpass_query(area: SearchArea, sectors: list[Sector]) -> str | None:
    """Build an Overpass QL query returning named businesses of the sectors around the area center."""
    tag_pairs = sorted({tag_pair for sector in sectors for tag_pair in sector.osm_tags})
    if not tag_pairs:
        return None
    radius_meters = int(area.radius_km * 1000)
    statements = "".join(
        f'nwr(around:{radius_meters},{area.latitude},{area.longitude})["{tag_key}"="{tag_value}"]["name"];'
        for tag_key, tag_value in tag_pairs
    )
    return f"[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];({statements});out center tags;"


def first_tag_value(osm_tags: dict[str, str], *tag_keys: str) -> str | None:
    """Return the first non empty value among several equivalent tags."""
    for tag_key in tag_keys:
        if osm_tags.get(tag_key):
            return osm_tags[tag_key].split(";")[0].strip()
    return None


def parse_overpass_element(element: dict) -> ProspectCandidate | None:
    """Convert an Overpass element into a prospect candidate."""
    osm_tags = element.get("tags") or {}
    name = osm_tags.get("name")
    if not name:
        return None
    coordinates = element.get("center") or element
    matching_sector = find_sector_by_osm_tags(osm_tags)
    street_parts = [osm_tags.get("addr:housenumber"), osm_tags.get("addr:street")]
    street_line = " ".join(part for part in street_parts if part)
    postal_code = osm_tags.get("addr:postcode")
    city = osm_tags.get("addr:city")
    address = ", ".join(part for part in (street_line, " ".join(part for part in (postal_code, city) if part)) if part) or None
    website_url = first_tag_value(osm_tags, "website", "contact:website", "url")
    social_url = first_tag_value(osm_tags, "contact:facebook", "facebook", "contact:instagram")
    brand = osm_tags.get("brand") or (name if osm_tags.get("brand:wikidata") else None)
    return ProspectCandidate(
        name=name,
        source="openstreetmap",
        alternative_names=[value for value in (osm_tags.get("brand"), osm_tags.get("operator")) if value],
        sector_key=matching_sector.key if matching_sector else None,
        category_label=matching_sector.label if matching_sector else None,
        address=address,
        postal_code=postal_code,
        city=city,
        latitude=coordinates.get("lat"),
        longitude=coordinates.get("lon"),
        phone=first_tag_value(osm_tags, "phone", "contact:phone", "contact:mobile"),
        email=first_tag_value(osm_tags, "email", "contact:email"),
        website_url=website_url,
        website_origin="openstreetmap" if website_url else None,
        website_confidence="high" if website_url else None,
        brand=brand,
        social_url=social_url if social_url and social_url.startswith("http") else None,
    )


async def search_openstreetmap(area: SearchArea, sectors: list[Sector]) -> list[ProspectCandidate]:
    """Return named businesses of the sectors found in OpenStreetMap around the area center."""
    overpass_query = build_overpass_query(area, sectors)
    if overpass_query is None:
        return []
    last_error: Exception | None = None
    async with create_open_data_client(timeout_seconds=OVERPASS_TIMEOUT_SECONDS + 30) as client:
        for endpoint_url in OVERPASS_ENDPOINTS:
            try:
                response = await client.post(endpoint_url, data={"data": overpass_query})
                response.raise_for_status()
                elements = response.json().get("elements", [])
                break
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                logger.warning("Overpass endpoint %s failed : %s", endpoint_url, error)
        else:
            raise OpenDataError(f"Every Overpass endpoint failed : {last_error}")
    candidates = [parse_overpass_element(element) for element in elements]
    return [candidate for candidate in candidates if candidate is not None]
