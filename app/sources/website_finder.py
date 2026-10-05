"""Discovery of a business website when the data source does not provide one."""
import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import BROWSER_USER_AGENT
from app.text_utils import extract_domain, slugify, strip_accents, tokenize_company_name

logger = logging.getLogger(__name__)
SEARCH_ENGINE_URL = "https://html.duckduckgo.com/html/"
CANDIDATE_TOP_LEVEL_DOMAINS = ("fr", "com")
DIRECTORY_DOMAINS = (
    "pagesjaunes.fr", "societe.com", "pappers.fr", "infogreffe.fr", "verif.com", "manageo.fr", "annuaire-entreprises.data.gouv.fr",
    "tripadvisor", "thefork.fr", "lafourchette.com", "ubereats.com", "deliveroo.fr", "google.", "yelp.", "mappy.com", "justacote.com",
    "petitfute.com", "linkedin.com", "wikipedia.org", "planity.com", "treatwell.fr", "kompass.com", "europages", "doctolib.fr",
    "118712.fr", "118000.fr", "bing.com", "duckduckgo.com", "youtube.com", "tiktok.com", "x.com", "twitter.com", "waze.com",
    "restaurantguru", "sortiraparis", "corporama.com", "b-reputation.com", "hoodspot.fr", "cylex", "horaires.lefigaro.fr",
    "pagespro.com", "lexpress.fr", "entreprises.lefigaro.fr", "dirigeant.societe.com", "score3.fr", "infonet.fr", "annuaire.",
)
SOCIAL_DOMAINS = ("facebook.com", "instagram.com")
PARKED_PAGE_MARKERS = (
    "domain is for sale", "ce domaine est a vendre", "this domain is parked", "domaine en vente", "buy this domain", "sedo",
    "parkingcrew", "domain parking", "nom de domaine est disponible", "site en cours de construction par ovh", "hostinger",
    "this domain may be for sale", "godaddy", "default web site page", "it works!",
)
MINIMUM_SEARCH_INTERVAL_SECONDS = 2.5
SEARCH_ENGINE_BLOCKING_STATUS_CODES = {202, 403, 429}


@dataclass
class WebsiteDiscovery:
    """Outcome of a website discovery attempt."""
    website_url: str | None
    origin: str | None
    social_url: str | None = None


@dataclass
class BusinessIdentity:
    """What we know about a business to recognise its website."""
    name: str
    alternative_names: list[str]
    city: str | None
    postal_code: str | None
    phone: str | None


class SearchRateLimiter:
    """Space out search engine requests so that the engine does not ban the user's IP address."""

    def __init__(self, minimum_interval_seconds: float) -> None:
        self._minimum_interval_seconds = minimum_interval_seconds
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def wait_turn(self) -> None:
        """Wait until the next request is allowed by the rate limit."""
        async with self._lock:
            elapsed_seconds = time.monotonic() - self._last_request_time
            remaining_seconds = self._minimum_interval_seconds + random.uniform(0, 1.5) - elapsed_seconds
            if remaining_seconds > 0:
                # Spacing requests is the only way to respect the engine's implicit rate limit
                await asyncio.sleep(remaining_seconds)
            self._last_request_time = time.monotonic()


search_rate_limiter = SearchRateLimiter(MINIMUM_SEARCH_INTERVAL_SECONDS)


def is_directory_url(url: str) -> bool:
    """Tell whether a URL belongs to a directory or platform rather than the business itself."""
    host_name = extract_domain(url) or ""
    return any(directory_domain in host_name for directory_domain in DIRECTORY_DOMAINS)


def is_social_url(url: str) -> bool:
    """Tell whether a URL is a social network page."""
    host_name = extract_domain(url) or ""
    return any(host_name.endswith(social_domain) for social_domain in SOCIAL_DOMAINS)


def build_domain_candidates(identity: BusinessIdentity) -> list[str]:
    """Generate plausible domain names derived from the business names and city."""
    domain_labels: list[str] = []
    city_slug = slugify(identity.city or "")
    for name in [identity.name, *identity.alternative_names][:3]:
        meaningful_tokens = tokenize_company_name(name)
        if not meaningful_tokens:
            continue
        joined_label = "".join(meaningful_tokens)
        hyphenated_label = "-".join(meaningful_tokens)
        for domain_label in (joined_label, hyphenated_label, f"{hyphenated_label}-{city_slug}" if city_slug else ""):
            if 3 <= len(domain_label) <= 63 and domain_label not in domain_labels:
                domain_labels.append(domain_label)
    return [f"{domain_label}.{top_level_domain}" for domain_label in domain_labels[:6] for top_level_domain in CANDIDATE_TOP_LEVEL_DOMAINS]


def page_belongs_to_business(page_html: str, identity: BusinessIdentity) -> bool:
    """Check that a page mentions the business name and its location or phone number."""
    page_text = strip_accents(BeautifulSoup(page_html, "lxml").get_text(" ", strip=True)).lower()
    if any(parked_marker in page_text for parked_marker in PARKED_PAGE_MARKERS) and len(page_text) < 3000:
        return False
    name_tokens = {token for name in [identity.name, *identity.alternative_names] for token in tokenize_company_name(name) if len(token) >= 3}
    if not name_tokens:
        return False
    matched_name_tokens = sum(1 for token in name_tokens if token in page_text)
    name_matches = matched_name_tokens >= max(1, min(2, len(name_tokens)))
    page_digits = re.sub(r"\D", "", page_text)
    phone_digits = re.sub(r"\D", "", identity.phone or "")
    location_matches = any((
        bool(identity.postal_code) and identity.postal_code in page_text,
        bool(identity.city) and strip_accents(identity.city).lower() in page_text,
        len(phone_digits) >= 9 and phone_digits[-9:] in page_digits,
    ))
    return name_matches and location_matches


async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """Fetch a page and return its final URL and HTML, or None when unreachable."""
    try:
        response = await client.get(url)
    except (httpx.HTTPError, UnicodeError):
        return None
    if response.status_code >= 400 or "html" not in response.headers.get("content-type", ""):
        return None
    return str(response.url), response.text


async def domain_resolves(domain_name: str) -> bool:
    """Tell whether a domain name has a DNS record."""
    try:
        await asyncio.get_running_loop().getaddrinfo(domain_name, 443)
        return True
    except OSError:
        return False


async def discover_by_domain_guess(client: httpx.AsyncClient, identity: BusinessIdentity) -> str | None:
    """Try domains derived from the business name and keep the first one that describes the business."""
    for domain_name in build_domain_candidates(identity):
        if not await domain_resolves(domain_name):
            continue
        fetched_page = await fetch_page(client, f"https://{domain_name}") or await fetch_page(client, f"http://{domain_name}")
        if fetched_page and page_belongs_to_business(fetched_page[1], identity):
            return fetched_page[0]
    return None


def extract_search_result_urls(results_html: str) -> list[str]:
    """Extract destination URLs from a DuckDuckGo HTML results page."""
    result_urls: list[str] = []
    for result_link in BeautifulSoup(results_html, "lxml").select("a.result__a"):
        link_target = result_link.get("href", "")
        if "uddg=" in link_target:
            link_target = unquote(parse_qs(urlparse(link_target).query).get("uddg", [""])[0])
        if link_target.startswith("http") and link_target not in result_urls:
            result_urls.append(link_target)
    return result_urls


class SearchEngineBlockedError(RuntimeError):
    """Raised when the search engine answers with an anti-bot challenge instead of results."""


async def discover_by_search_engine(client: httpx.AsyncClient, identity: BusinessIdentity) -> tuple[str | None, str | None]:
    """Search the business on DuckDuckGo and verify the first plausible official website."""
    await search_rate_limiter.wait_turn()
    search_query = f"{identity.name} {identity.city or identity.postal_code or ''}".strip()
    try:
        response = await client.post(SEARCH_ENGINE_URL, data={"q": search_query, "kl": "fr-fr"})
    except httpx.HTTPError as error:
        logger.warning("Search engine request failed for %s : %s", search_query, error)
        return None, None
    if response.status_code in SEARCH_ENGINE_BLOCKING_STATUS_CODES:
        raise SearchEngineBlockedError(f"HTTP {response.status_code}")
    if response.status_code != 200:
        logger.warning("Search engine answered HTTP %s for %s", response.status_code, search_query)
        return None, None
    social_url = None
    for result_url in extract_search_result_urls(response.text)[:6]:
        if is_social_url(result_url):
            social_url = social_url or result_url
            continue
        if is_directory_url(result_url):
            continue
        fetched_page = await fetch_page(client, result_url)
        if fetched_page and page_belongs_to_business(fetched_page[1], identity):
            parsed_url = urlparse(fetched_page[0])
            return f"{parsed_url.scheme}://{parsed_url.netloc}/", social_url
    return None, social_url


def create_website_client() -> httpx.AsyncClient:
    """Create the HTTP client used to probe candidate websites."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        follow_redirects=True,
        headers={"User-Agent": BROWSER_USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"},
        verify=False,
        transport=httpx.AsyncHTTPTransport(retries=2, verify=False),
    )


class WebsiteFinder:
    """Website discovery for one job, disabling the search engine as soon as it starts blocking."""

    def __init__(self, client: httpx.AsyncClient, use_search_engine: bool, log: Callable[[str], None]) -> None:
        self._client = client
        self._search_engine_enabled = use_search_engine
        self._log = log

    async def discover(self, identity: BusinessIdentity) -> WebsiteDiscovery:
        """Find the official website of a business, first by guessing its domain, then through a search engine."""
        guessed_url = await discover_by_domain_guess(self._client, identity)
        if guessed_url:
            return WebsiteDiscovery(website_url=guessed_url, origin="domain_guess")
        if not self._search_engine_enabled:
            return WebsiteDiscovery(website_url=None, origin=None)
        try:
            found_url, social_url = await discover_by_search_engine(self._client, identity)
        except SearchEngineBlockedError as error:
            # Insisting after a challenge extends the ban, so the engine is skipped for the rest of the job
            self._search_engine_enabled = False
            self._log(f"⚠️ DuckDuckGo bloque temporairement les recherches ({error}) : la suite utilise uniquement la déduction du nom de domaine.")
            return WebsiteDiscovery(website_url=None, origin=None)
        return WebsiteDiscovery(website_url=found_url, origin="search_engine" if found_url else None, social_url=social_url)
