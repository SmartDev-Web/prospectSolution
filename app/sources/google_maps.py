"""Google Maps scraping through a real Chromium browser driven by Playwright."""
import asyncio
import logging
import random
import re
from typing import AsyncIterator, Callable
from urllib.parse import parse_qs, quote, urlparse

from playwright.async_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeoutError

from app.browser import browser_runtime
from app.config import GOOGLE_MAPS_PROFILE_DIRECTORY
from app.geo import is_within_radius
from app.models import ProspectCandidate, SearchArea
from app.sectors import Sector

logger = logging.getLogger(__name__)
# Google changes its markup regularly: every selector lives here so that a fix is a one-line change
SELECTORS = {
    "consent_reject": 'button:has-text("Tout refuser"), button:has-text("Reject all")',
    "results_feed": 'div[role="feed"]',
    "result_link": 'div[role="feed"] a[href*="/maps/place/"]',
    "end_of_list": "span.HlvSq",
    "place_title": 'div[role="main"] h1',
    "captcha_form": "form#captcha-form",
}
PLACE_PANEL_READY_SCRIPT = """
(expectedName) => [...document.querySelectorAll('div[role="main"]')].some(panel => panel.getAttribute('aria-label') === expectedName && panel.querySelector('h1'))
"""
PLACE_EXTRACTION_SCRIPT = """
(expectedName) => {
    const panels = [...document.querySelectorAll('div[role="main"]')];
    const placePanel = panels.find(panel => expectedName && panel.getAttribute('aria-label') === expectedName)
        || panels.reverse().find(panel => panel.querySelector('h1'))
        || document;
    const findElement = (selector) => placePanel.querySelector(selector);
    const readText = (selector) => { const element = findElement(selector); return element ? element.textContent.trim() : null; };
    const readAttribute = (selector, attributeName) => { const element = findElement(selector); return element ? element.getAttribute(attributeName) : null; };
    const ratingBlock = findElement('div.F7nice');
    const ratingTextElement = ratingBlock ? ratingBlock.querySelector('span[aria-hidden="true"]') : null;
    const reviewElement = ratingBlock ? ratingBlock.querySelector('span[aria-label]') : null;
    const pageText = placePanel.innerText || '';
    return {
        name: readText('h1'),
        category: readText('button[jsaction*="category"]'),
        addressLabel: readAttribute('button[data-item-id="address"]', 'aria-label'),
        website: readAttribute('a[data-item-id="authority"]', 'href'),
        phoneItem: readAttribute('button[data-item-id^="phone:tel:"]', 'data-item-id'),
        ratingText: ratingTextElement ? ratingTextElement.textContent.trim() : null,
        reviewText: reviewElement ? reviewElement.getAttribute('aria-label') : (ratingBlock ? ratingBlock.textContent : null),
        permanentlyClosed: pageText.includes('Définitivement fermé') || pageText.includes('Permanently closed'),
    };
}
"""
COORDINATES_PATTERN = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
VIEWPORT_PATTERN = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
PLACE_KEY_PATTERN = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")
POSTAL_CODE_CITY_PATTERN = re.compile(r"(\d{5})\s+([^,]+?)\s*$")
CAPTCHA_RESOLUTION_TIMEOUT_MS = 5 * 60 * 1000
SCROLL_GROWTH_TIMEOUT_MS = 8000
RESULT_CLICK_TIMEOUT_MS = 6000


class GoogleMapsBlockedError(RuntimeError):
    """Raised when Google requires a CAPTCHA that cannot be solved in headless mode."""


def zoom_level_for_radius(radius_km: float) -> int:
    """Pick a Google Maps zoom level whose viewport roughly covers the search radius."""
    for maximum_radius_km, zoom_level in ((1.5, 16), (3, 15), (6, 14), (12, 13), (25, 12)):
        if radius_km <= maximum_radius_km:
            return zoom_level
    return 11


def build_search_url(query: str, area: SearchArea) -> str:
    """Build the Google Maps search URL centered on the search area."""
    full_query = f"{query} {area.label}".strip() if area.label else query
    return f"https://www.google.com/maps/search/{quote(full_query)}/@{area.latitude},{area.longitude},{zoom_level_for_radius(area.radius_km)}z?hl=fr"


def unwrap_google_redirect(url: str | None) -> str | None:
    """Return the destination of a google.com/url redirect link."""
    if not url:
        return None
    parsed_url = urlparse(url)
    if parsed_url.netloc.endswith("google.com") and parsed_url.path == "/url":
        return parse_qs(parsed_url.query).get("q", [url])[0]
    return url


def parse_review_count(review_text: str | None) -> int | None:
    """Extract the review count from strings such as '(1 234)' or '1 234 avis'."""
    if not review_text:
        return None
    digits_groups = re.findall(r"\d[\d\s  .]*", review_text)
    if not digits_groups:
        return None
    return int(re.sub(r"\D", "", digits_groups[-1]) or 0) or None


def parse_place(raw_place: dict, place_url: str, sector: Sector | None) -> ProspectCandidate | None:
    """Convert the raw values read on a place page into a prospect candidate."""
    if not raw_place.get("name") or raw_place.get("permanentlyClosed"):
        return None
    coordinates_match = COORDINATES_PATTERN.search(place_url) or VIEWPORT_PATTERN.search(place_url)
    place_key_match = PLACE_KEY_PATTERN.search(place_url)
    address_label = raw_place.get("addressLabel") or ""
    address = address_label.split(":", 1)[1].strip() if ":" in address_label else address_label.strip() or None
    postal_code_match = POSTAL_CODE_CITY_PATTERN.search(address or "")
    phone_item = raw_place.get("phoneItem") or ""
    rating_text = (raw_place.get("ratingText") or "").replace(",", ".")
    website_url = unwrap_google_redirect(raw_place.get("website"))
    return ProspectCandidate(
        name=raw_place["name"],
        source="google_maps",
        sector_key=sector.key if sector else None,
        category_label=raw_place.get("category") or (sector.label if sector else None),
        address=address,
        postal_code=postal_code_match.group(1) if postal_code_match else None,
        city=postal_code_match.group(2) if postal_code_match else None,
        latitude=float(coordinates_match.group(1)) if coordinates_match else None,
        longitude=float(coordinates_match.group(2)) if coordinates_match else None,
        phone=phone_item.removeprefix("phone:tel:") or None,
        website_url=website_url,
        website_origin="google_maps" if website_url else None,
        google_rating=float(rating_text) if re.fullmatch(r"\d(\.\d)?", rating_text) else None,
        google_review_count=parse_review_count(raw_place.get("reviewText")),
        google_maps_url=place_url.split("?")[0],
        google_place_key=place_key_match.group(1) if place_key_match else None,
    )


async def pause_like_a_human(minimum_seconds: float, maximum_seconds: float) -> None:
    """Wait a random duration between two actions."""
    # Deliberate throttling: a constant, machine-fast rhythm is what anti-bot systems detect first
    await asyncio.sleep(random.uniform(minimum_seconds, maximum_seconds))


class GoogleMapsScraper:
    """Drive a persistent Chromium profile through Google Maps searches."""

    def __init__(self, headless: bool, pause_range_seconds: tuple[float, float], log: Callable[[str], None]) -> None:
        self._headless = headless
        self._pause_range_seconds = pause_range_seconds
        self._log = log

    async def _accept_consent_if_needed(self, page: Page) -> None:
        if "consent.google" not in page.url:
            return
        self._log("Page de consentement Google détectée : refus des cookies.")
        await page.click(SELECTORS["consent_reject"])
        await page.wait_for_url(lambda url: "consent.google" not in url, timeout=30000)

    async def _ensure_not_blocked(self, page: Page) -> None:
        captcha_displayed = "/sorry/" in page.url or await page.locator(SELECTORS["captcha_form"]).count() > 0
        if not captcha_displayed:
            return
        if self._headless:
            raise GoogleMapsBlockedError("Google demande un CAPTCHA. Relancez en mode visible pour le résoudre, ou attendez quelques heures.")
        self._log("⚠️ CAPTCHA Google : résolvez-le dans la fenêtre du navigateur, le scraping reprendra automatiquement.")
        await page.wait_for_url(lambda url: "/sorry/" not in url, timeout=CAPTCHA_RESOLUTION_TIMEOUT_MS)

    async def _collect_place_urls(self, page: Page, search_url: str, max_results: int) -> list[str]:
        await page.goto(search_url, wait_until="domcontentloaded")
        await self._accept_consent_if_needed(page)
        await self._ensure_not_blocked(page)
        await page.wait_for_selector(f'{SELECTORS["results_feed"]}, {SELECTORS["place_title"]}', timeout=30000)
        if await page.locator(SELECTORS["results_feed"]).count() == 0:
            return [page.url]
        place_urls: list[str] = []
        while True:
            link_targets = await page.eval_on_selector_all(SELECTORS["result_link"], "links => links.map(link => link.href)")
            place_urls = list(dict.fromkeys(link_targets))
            if len(place_urls) >= max_results or await page.locator(SELECTORS["end_of_list"]).count() > 0:
                break
            await page.eval_on_selector(SELECTORS["results_feed"], "feed => feed.scrollTo(0, feed.scrollHeight)")
            try:
                await page.wait_for_function(
                    "([selector, previousCount]) => document.querySelectorAll(selector).length > previousCount",
                    arg=[SELECTORS["result_link"], len(link_targets)],
                    timeout=SCROLL_GROWTH_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError:
                break
        return place_urls[:max_results]

    async def _open_place(self, page: Page, place_url: str) -> str | None:
        """Open a place panel by clicking its result like a visitor would, or by URL when it left the list."""
        escaped_place_url = place_url.replace("\\", "\\\\").replace('"', '\\"')
        result_link = page.locator(f'{SELECTORS["results_feed"]} a[href="{escaped_place_url}"]')
        if await result_link.count() > 0:
            expected_name = await result_link.first.get_attribute("aria-label")
            try:
                await result_link.first.click(timeout=RESULT_CLICK_TIMEOUT_MS)
                await page.wait_for_function(PLACE_PANEL_READY_SCRIPT, arg=expected_name, timeout=20000)
                return expected_name
            except PlaywrightError as error:
                logger.info("Clicking %s failed (%s), opening it by URL", expected_name, str(error).splitlines()[0])
        await page.goto(place_url, wait_until="domcontentloaded")
        await self._ensure_not_blocked(page)
        await page.wait_for_selector(SELECTORS["place_title"], timeout=20000)
        return None

    async def _extract_place(self, page: Page, place_url: str, sector: Sector | None) -> ProspectCandidate | None:
        expected_name = await self._open_place(page, place_url)
        try:
            await page.wait_for_url(COORDINATES_PATTERN, timeout=5000)
        except PlaywrightTimeoutError:
            logger.debug("No coordinates in URL for %s", place_url)
        raw_place = await page.evaluate(PLACE_EXTRACTION_SCRIPT, expected_name)
        return parse_place(raw_place, page.url if COORDINATES_PATTERN.search(page.url) else place_url, sector)

    async def scrape(self, area: SearchArea, queries: list[tuple[str, Sector | None]], max_results_per_query: int) -> AsyncIterator[ProspectCandidate]:
        """Yield businesses found for every query inside the search area."""
        browser_context = await browser_runtime.launch_persistent_context(str(GOOGLE_MAPS_PROFILE_DIRECTORY), self._headless)
        try:
            page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()
            visited_place_urls: set[str] = set()
            for query_index, (query, sector) in enumerate(queries, start=1):
                self._log(f"Recherche {query_index}/{len(queries)} : « {query} »")
                place_urls = await self._collect_place_urls(page, build_search_url(query, area), max_results_per_query)
                self._log(f"{len(place_urls)} fiches trouvées pour « {query} »")
                for place_url in place_urls:
                    canonical_place_url = place_url.split("?")[0]
                    if canonical_place_url in visited_place_urls:
                        continue
                    visited_place_urls.add(canonical_place_url)
                    await pause_like_a_human(*self._pause_range_seconds)
                    try:
                        candidate = await self._extract_place(page, place_url, sector)
                    except GoogleMapsBlockedError:
                        raise
                    except PlaywrightError as error:
                        self._log(f"Fiche ignorée ({str(error).splitlines()[0][:80]}).")
                        continue
                    if candidate and is_within_radius(area.latitude, area.longitude, area.radius_km, candidate.latitude, candidate.longitude):
                        yield candidate
                await pause_like_a_human(self._pause_range_seconds[0] * 2, self._pause_range_seconds[1] * 2)
        finally:
            await browser_context.close()
