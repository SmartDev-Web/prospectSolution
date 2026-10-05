"""Discovery of a business website when the data source does not provide one."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

import httpx

from app.config import BROWSER_USER_AGENT
from app.sources.search_engines import SearchEngineRouter
from app.sources.website_verification import (
    GENERIC_NAME_WORDS,
    BusinessIdentity,
    PageEvidence,
    ParsedPage,
    evaluate_pages,
    find_location_subpages,
    is_directory_url,
    parse_page,
    website_root,
)
from app.text_utils import extract_domain, slugify, tokenize_company_name

logger = logging.getLogger(__name__)
CANDIDATE_TOP_LEVEL_DOMAINS = ("fr", "com", "eu", "net", "org", "info")
MAXIMUM_DOMAIN_LABELS = 10
MAXIMUM_SEARCH_RESULTS_CHECKED = 5
SOCIAL_DOMAINS = ("facebook.com", "instagram.com")
CONFIDENCE_RANK = {"high": 2, "medium": 1, None: 0}


@dataclass
class WebsiteDiscovery:
    """Outcome of a website discovery attempt."""
    website_url: str | None = None
    origin: str | None = None
    confidence: str | None = None
    evidence: list[str] = field(default_factory=list)
    social_url: str | None = None
    score: float = 0.0


def build_domain_labels(identity: BusinessIdentity) -> list[str]:
    """Generate plausible domain labels from the business names and city."""
    city_joined = slugify(identity.city or "", "")
    city_hyphenated = slugify(identity.city or "", "-")
    domain_labels: list[str] = []
    for name in identity.all_names()[:3]:
        name_tokens = tokenize_company_name(name)
        distinctive_tokens = [token for token in name_tokens if token not in GENERIC_NAME_WORDS]
        variants = ["".join(name_tokens), "-".join(name_tokens), "".join(distinctive_tokens), "-".join(distinctive_tokens)]
        if city_joined:
            variants += [f"{''.join(name_tokens)}-{city_hyphenated}", f"{''.join(name_tokens)}{city_joined}", f"{''.join(distinctive_tokens)}-{city_hyphenated}"]
        for domain_label in variants:
            if 4 <= len(domain_label) <= 63 and domain_label not in GENERIC_NAME_WORDS and domain_label not in domain_labels:
                domain_labels.append(domain_label)
    return domain_labels[:MAXIMUM_DOMAIN_LABELS]


def build_domain_candidates(identity: BusinessIdentity) -> list[str]:
    """Combine domain labels with the extensions small French businesses use."""
    return [f"{domain_label}.{top_level_domain}" for domain_label in build_domain_labels(identity) for top_level_domain in CANDIDATE_TOP_LEVEL_DOMAINS]


def build_search_queries(identity: BusinessIdentity) -> list[str]:
    """Build the search queries, from the most to the least specific."""
    location = identity.city or identity.postal_code or ""
    queries = [f"{name} {location}".strip() for name in identity.all_names()[:2]]
    return list(dict.fromkeys(queries))


def is_social_url(url: str) -> bool:
    """Tell whether a URL is a Facebook or Instagram page."""
    host_name = extract_domain(url) or ""
    return any(host_name.endswith(social_domain) for social_domain in SOCIAL_DOMAINS)


async def domain_resolves(domain_name: str) -> bool:
    """Tell whether a domain name has a DNS record."""
    try:
        await asyncio.get_running_loop().getaddrinfo(domain_name, 443)
        return True
    except OSError:
        return False


async def fetch_page(client: httpx.AsyncClient, url: str) -> ParsedPage | None:
    """Fetch and parse an HTML page, or return None when it is unreachable."""
    if not url.startswith(("http://", "https://")):
        return None
    try:
        response = await client.get(url)
    except (httpx.HTTPError, httpx.InvalidURL, UnicodeError, ValueError):
        return None
    if response.status_code >= 400 or "html" not in response.headers.get("content-type", ""):
        return None
    return parse_page(str(response.url), response.text)


def create_website_client() -> httpx.AsyncClient:
    """Create the HTTP client used to probe candidate websites."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(12.0),
        follow_redirects=True,
        headers={"User-Agent": BROWSER_USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"},
        verify=False,
        transport=httpx.AsyncHTTPTransport(retries=2, verify=False),
    )


def better_discovery(first: WebsiteDiscovery | None, second: WebsiteDiscovery | None) -> WebsiteDiscovery | None:
    """Keep the discovery with the highest confidence, then the highest score."""
    candidates = [discovery for discovery in (first, second) if discovery and discovery.website_url]
    if not candidates:
        return None
    return max(candidates, key=lambda discovery: (CONFIDENCE_RANK[discovery.confidence], discovery.score))


class WebsiteFinder:
    """Find and verify official websites for one job, sharing engines and their circuit breakers."""

    def __init__(self, client: httpx.AsyncClient, search_router: SearchEngineRouter | None, log: Callable[[str], None]) -> None:
        self._client = client
        self._search_router = search_router
        self._log = log

    async def verify_site(self, url: str, identity: BusinessIdentity, found_by_search: bool) -> tuple[PageEvidence, str] | None:
        """Score a candidate site, reading its contact and legal pages when the homepage is not conclusive."""
        if extract_domain(url) in identity.rejected_domains:
            return None
        home_page = await fetch_page(self._client, url)
        if home_page is None or is_directory_url(home_page.url) or extract_domain(home_page.url) in identity.rejected_domains:
            return None
        evidence = evaluate_pages(home_page, [], identity, found_by_search)
        if evidence.name_matched and evidence.confidence != "high":
            subpages = await asyncio.gather(*(fetch_page(self._client, subpage_url) for subpage_url in find_location_subpages(home_page)))
            evidence = evaluate_pages(home_page, [subpage for subpage in subpages if subpage], identity, found_by_search)
        return evidence, website_root(home_page.url)

    async def discover_by_domain_guess(self, identity: BusinessIdentity) -> WebsiteDiscovery | None:
        """Try domains derived from the business name, resolving them all in parallel."""
        domain_candidates = build_domain_candidates(identity)
        resolution_results = await asyncio.gather(*(domain_resolves(domain_name) for domain_name in domain_candidates))
        best_discovery: WebsiteDiscovery | None = None
        for domain_name in [domain_name for domain_name, resolves in zip(domain_candidates, resolution_results) if resolves]:
            verification = await self.verify_site(f"https://{domain_name}", identity, False) or await self.verify_site(f"http://{domain_name}", identity, False)
            if verification is None or verification[0].confidence is None:
                continue
            if verification[0].confidence == "medium" and not verification[0].full_name_in_domain:
                # A guessed domain matching a single word ("littoral.com") is too ambiguous without hard proof
                continue
            evidence, root_url = verification
            discovery = WebsiteDiscovery(website_url=root_url, origin="domain_guess", confidence=evidence.confidence, evidence=evidence.reasons, score=evidence.score)
            best_discovery = better_discovery(best_discovery, discovery)
            if evidence.confidence == "high":
                break
        return best_discovery

    async def discover_by_search(self, identity: BusinessIdentity) -> WebsiteDiscovery:
        """Search the business name and city, then verify the first plausible results."""
        social_url = None
        checked_roots: set[str] = set()
        for query in build_search_queries(identity):
            if not self._search_router.has_available_engine:
                break
            result_urls, engine_key = await self._search_router.search(self._client, query)
            best_discovery: WebsiteDiscovery | None = None
            for result_url in result_urls:
                if is_social_url(result_url):
                    social_url = social_url or result_url
                    continue
                root_url = website_root(result_url)
                if is_directory_url(result_url) or root_url in checked_roots or len(checked_roots) >= MAXIMUM_SEARCH_RESULTS_CHECKED:
                    continue
                checked_roots.add(root_url)
                verification = await self.verify_site(root_url, identity, True)
                if verification and verification[0].confidence:
                    evidence, verified_root = verification
                    best_discovery = better_discovery(best_discovery, WebsiteDiscovery(
                        website_url=verified_root, origin=engine_key, confidence=evidence.confidence, evidence=evidence.reasons, score=evidence.score,
                    ))
                    if evidence.confidence == "high":
                        break
            if best_discovery:
                best_discovery.social_url = social_url
                return best_discovery
        return WebsiteDiscovery(social_url=social_url)

    async def discover(self, identity: BusinessIdentity) -> WebsiteDiscovery:
        """Find the official website: domain guessing first, then search engines when the guess is not certain."""
        guessed_discovery = await self.discover_by_domain_guess(identity)
        if guessed_discovery and guessed_discovery.confidence == "high":
            return guessed_discovery
        searched_discovery = await self.discover_by_search(identity) if self._search_router else WebsiteDiscovery()
        best_discovery = better_discovery(guessed_discovery, searched_discovery) or WebsiteDiscovery()
        best_discovery.social_url = best_discovery.social_url or searched_discovery.social_url
        return best_discovery
