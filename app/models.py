"""Shared data structures exchanged between sources, services and the API."""
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

PROSPECT_STATUSES = ("new", "to_call", "called_no_answer", "callback", "interested", "meeting", "quote_sent", "won", "lost", "not_interested")
ProspectStatus = Literal["new", "to_call", "called_no_answer", "callback", "interested", "meeting", "quote_sent", "won", "lost", "not_interested"]
CALL_OUTCOME_STATUSES = {
    "no_answer": "called_no_answer",
    "callback": "callback",
    "interested": "interested",
    "meeting": "meeting",
    "not_interested": "not_interested",
}


@dataclass
class ProspectCandidate:
    """A business found by a source, before being merged into the prospect base."""
    name: str
    source: str
    alternative_names: list[str] = field(default_factory=list)
    legal_name: str | None = None
    siret: str | None = None
    naf_code: str | None = None
    sector_key: str | None = None
    category_label: str | None = None
    company_category: str | None = None
    address: str | None = None
    postal_code: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    email: str | None = None
    website_url: str | None = None
    website_origin: str | None = None
    website_confidence: str | None = None
    social_url: str | None = None
    manager_name: str | None = None
    brand: str | None = None
    establishment_count: int | None = None
    creation_date: str | None = None
    employee_range: str | None = None
    google_rating: float | None = None
    google_review_count: int | None = None
    google_maps_url: str | None = None
    google_place_key: str | None = None


class SearchArea(BaseModel):
    """Circle in which businesses are searched."""
    label: str = ""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=50)


class OpenDataSearchRequest(BaseModel):
    """Parameters of a search through the government registry and OpenStreetMap."""
    area: SearchArea
    sector_keys: list[str] = []
    custom_naf_codes: list[str] = []
    use_government_registry: bool = True
    use_openstreetmap: bool = True
    discover_websites: bool = True
    exclude_large_companies: bool = True
    exclude_chains: bool = True
    created_after: str | None = None
    max_results: int = Field(default=500, ge=1, le=5000)
    auto_scan: bool = False


class GoogleMapsSearchRequest(BaseModel):
    """Parameters of a Google Maps scraping session."""
    area: SearchArea
    sector_keys: list[str] = []
    custom_queries: list[str] = []
    max_results_per_query: int = Field(default=40, ge=1, le=200)
    headless: bool | None = None
    exclude_chains: bool = True
    auto_scan: bool = False


class ScanRequest(BaseModel):
    """Selection of prospects to analyse."""
    prospect_ids: list[int] = []
    only_unscanned: bool = False
    all_with_website: bool = False


class WebsiteDiscoveryRequest(BaseModel):
    """Selection of prospects whose website must be searched again."""
    prospect_ids: list[int] = []
    all_without_website: bool = False


class GoogleMapsEnrichmentRequest(BaseModel):
    """Prospects to complete with their Google Maps listing."""
    prospect_ids: list[int] = []
    all_without_phone: bool = False
    limit: int = Field(default=30, ge=1, le=200)


class ProspectCreate(BaseModel):
    """A prospect entered by hand."""
    name: str = Field(min_length=1)
    website_url: str | None = None
    city: str | None = None
    phone: str | None = None
    sector_key: str | None = None
    scan_now: bool = True


class ProspectUpdate(BaseModel):
    """Fields of a prospect editable from the interface."""
    name: str | None = None
    status: ProspectStatus | None = None
    notes: str | None = None
    next_follow_up: str | None = None
    website_url: str | None = None
    phone: str | None = None
    email: str | None = None
    sector_key: str | None = None


class ActivityCreate(BaseModel):
    """A logged interaction with a prospect (call, email, meeting, note)."""
    kind: Literal["call", "email", "meeting", "note"]
    outcome: str | None = None
    content: str = ""
    next_follow_up: str | None = None
