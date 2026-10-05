"""Shared data structures exchanged between sources, services and the API."""
from dataclasses import dataclass, field
from typing import Annotated, Literal

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
    employee_minimum: int | None = None
    google_rating: float | None = None
    google_review_count: int | None = None
    google_maps_url: str | None = None
    google_place_key: str | None = None


# Bounds keeping every request body small: a selection, a list of choices and free texts all have a ceiling
MAXIMUM_SELECTION = 20000
MAXIMUM_CHOICES = 300
ShortText = Annotated[str, Field(max_length=200)]
UrlText = Annotated[str, Field(max_length=2000)]
LongText = Annotated[str, Field(max_length=50000)]


class SearchArea(BaseModel):
    """Circle in which businesses are searched."""
    label: str = Field(default="", max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=50)


class OpenDataSearchRequest(BaseModel):
    """Parameters of a search through the government registry and OpenStreetMap."""
    area: SearchArea
    sector_keys: list[ShortText] = Field(default=[], max_length=MAXIMUM_CHOICES)
    custom_naf_codes: list[ShortText] = Field(default=[], max_length=MAXIMUM_CHOICES)
    use_government_registry: bool = True
    use_openstreetmap: bool = True
    discover_websites: bool = True
    exclude_large_companies: bool = True
    exclude_chains: bool = True
    created_after: ShortText | None = None
    max_results: int = Field(default=500, ge=1, le=5000)
    auto_scan: bool = False


class GoogleMapsSearchRequest(BaseModel):
    """Parameters of a Google Maps scraping session."""
    area: SearchArea
    sector_keys: list[ShortText] = Field(default=[], max_length=MAXIMUM_CHOICES)
    custom_queries: list[ShortText] = Field(default=[], max_length=MAXIMUM_CHOICES)
    max_results_per_query: int = Field(default=40, ge=1, le=200)
    headless: bool | None = None
    exclude_chains: bool = True
    auto_scan: bool = False


class ScanRequest(BaseModel):
    """Selection of prospects to analyse."""
    prospect_ids: list[int] = Field(default=[], max_length=MAXIMUM_SELECTION)
    only_unscanned: bool = False
    all_with_website: bool = False


class WebsiteDiscoveryRequest(BaseModel):
    """Selection of prospects whose website must be searched again."""
    prospect_ids: list[int] = Field(default=[], max_length=MAXIMUM_SELECTION)
    all_without_website: bool = False


class GoogleMapsEnrichmentRequest(BaseModel):
    """Prospects to complete with their Google Maps listing."""
    prospect_ids: list[int] = Field(default=[], max_length=MAXIMUM_SELECTION)
    all_without_phone: bool = False
    limit: int = Field(default=30, ge=1, le=200)


class CustomFinding(BaseModel):
    """A problem written by the user in a diagnosis."""
    title: str = Field(min_length=2, max_length=200)
    impact: str = Field(default="", max_length=2000)
    recommendation: str = Field(default="", max_length=1000)
    severity: Literal["critical", "major", "minor"] = "major"
    category: Literal["availability", "security", "mobile", "performance", "conversion", "seo", "legal", "design", "technology", "content", "sector"] = "design"


class DiagnosisOverrides(BaseModel):
    """Corrections applied by the user on top of the analyzer's diagnosis, kept across new analyses."""
    dismissed_codes: list[ShortText] = Field(default=[], max_length=MAXIMUM_CHOICES)
    custom_findings: list[CustomFinding] = Field(default=[], max_length=MAXIMUM_CHOICES)
    summary: str | None = Field(default=None, max_length=4000)


class MarkChainRequest(BaseModel):
    """Chain name typed by the user for a prospect that the automatic detection missed."""
    brand: str = Field(min_length=2, max_length=80)


class MergeRequest(BaseModel):
    """Prospects to merge into the oldest of them."""
    prospect_ids: list[int] = Field(min_length=2, max_length=MAXIMUM_SELECTION)


class ProspectCreate(BaseModel):
    """A prospect entered by hand."""
    name: str = Field(min_length=1, max_length=200)
    website_url: UrlText | None = None
    city: ShortText | None = None
    phone: ShortText | None = None
    sector_key: ShortText | None = None
    scan_now: bool = True


class ProspectUpdate(BaseModel):
    """Fields of a prospect editable from the interface."""
    name: str | None = Field(default=None, max_length=200)
    status: ProspectStatus | None = None
    notes: LongText | None = None
    next_follow_up: ShortText | None = None
    website_url: UrlText | None = None
    phone: ShortText | None = None
    email: UrlText | None = None
    sector_key: ShortText | None = None


class BulkUpdateRequest(BaseModel):
    """Same edit applied to a selection of prospects."""
    prospect_ids: list[int] = Field(min_length=1, max_length=MAXIMUM_SELECTION)
    changes: ProspectUpdate


class BulkDeleteRequest(BaseModel):
    """Selection of prospects to delete."""
    prospect_ids: list[int] = Field(min_length=1, max_length=MAXIMUM_SELECTION)


class ActivityCreate(BaseModel):
    """A logged interaction with a prospect (call, email, meeting, note)."""
    kind: Literal["call", "email", "meeting", "note"]
    outcome: ShortText | None = None
    content: LongText = ""
    next_follow_up: ShortText | None = None
