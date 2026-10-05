"""Web search engines used to find business websites, each with its own pacing and circuit breaker."""
import asyncio
import base64
import logging
from typing import Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Error as PlaywrightError

from app.browser import browser_runtime
from app.config import GOOGLE_SEARCH_PROFILE_DIRECTORY
from app.http_client import RequestPacer

logger = logging.getLogger(__name__)
BLOCKING_STATUS_CODES = {202, 403, 429, 503}


class SearchEngineBlockedError(RuntimeError):
    """Raised when an engine answers with an anti-bot challenge instead of results."""


def decode_bing_redirect(url: str) -> str:
    """Return the destination of a Bing click-tracking link."""
    parsed_url = urlparse(url)
    if "bing.com" not in parsed_url.netloc or not parsed_url.path.startswith("/ck/"):
        return url
    encoded_target = parse_qs(parsed_url.query).get("u", [""])[0]
    if not encoded_target.startswith("a1"):
        return url
    padded_target = encoded_target[2:] + "=" * (-len(encoded_target[2:]) % 4)
    try:
        return base64.urlsafe_b64decode(padded_target).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return url


def parse_duckduckgo_results(results_html: str) -> list[str]:
    """Extract destination URLs from a DuckDuckGo HTML results page."""
    result_urls: list[str] = []
    for result_link in BeautifulSoup(results_html, "lxml").select("a.result__a"):
        link_target = result_link.get("href", "")
        if "uddg=" in link_target:
            link_target = unquote(parse_qs(urlparse(link_target).query).get("uddg", [""])[0])
        if link_target.startswith("http") and link_target not in result_urls:
            result_urls.append(link_target)
    return result_urls


def parse_bing_results(results_html: str) -> list[str]:
    """Extract destination URLs from a Bing results page."""
    result_urls: list[str] = []
    for result_link in BeautifulSoup(results_html, "lxml").select("li.b_algo h2 a"):
        link_target = decode_bing_redirect(result_link.get("href", ""))
        if link_target.startswith("http") and link_target not in result_urls:
            result_urls.append(link_target)
    return result_urls


def parse_google_results(results_html: str) -> list[str]:
    """Extract organic result URLs from a Google results page."""
    result_urls: list[str] = []
    for heading in BeautifulSoup(results_html, "lxml").select("a h3"):
        link_target = heading.find_parent("a").get("href", "")
        if link_target.startswith("/url?"):
            link_target = parse_qs(urlparse(link_target).query).get("q", [""])[0]
        if link_target.startswith("http") and "google." not in urlparse(link_target).netloc and link_target not in result_urls:
            result_urls.append(link_target)
    return result_urls


class SearchEngine:
    """Common behaviour: pacing and blocking detection."""
    key = ""
    label = ""
    minimum_interval_seconds = 3.0

    def __init__(self) -> None:
        self.pacer = RequestPacer(self.minimum_interval_seconds, jitter_seconds=1.0)
        self.blocked = False

    async def search(self, client: httpx.AsyncClient, query: str) -> list[str]:
        raise NotImplementedError

    async def close(self) -> None:
        """Release resources held by the engine."""


class DuckDuckGoEngine(SearchEngine):
    key = "duckduckgo"
    label = "DuckDuckGo"
    minimum_interval_seconds = 2.5

    async def search(self, client: httpx.AsyncClient, query: str) -> list[str]:
        await self.pacer.wait_turn()
        response = await client.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "fr-fr"})
        if response.status_code in BLOCKING_STATUS_CODES:
            raise SearchEngineBlockedError(f"HTTP {response.status_code}")
        return parse_duckduckgo_results(response.text) if response.status_code == 200 else []


class BingEngine(SearchEngine):
    key = "bing"
    label = "Bing"
    minimum_interval_seconds = 3.0

    async def search(self, client: httpx.AsyncClient, query: str) -> list[str]:
        await self.pacer.wait_turn()
        response = await client.get(f"https://www.bing.com/search?q={quote_plus(query)}&setlang=fr&cc=FR&count=10")
        if response.status_code in BLOCKING_STATUS_CODES or "/challenge" in str(response.url):
            raise SearchEngineBlockedError(f"HTTP {response.status_code}")
        return parse_bing_results(response.text) if response.status_code == 200 else []


class GoogleBrowserEngine(SearchEngine):
    """Google results read in a real browser profile: the most relevant engine, and the most sensitive to scraping."""
    key = "google_browser"
    label = "Google (navigateur)"
    minimum_interval_seconds = 8.0

    def __init__(self, headless: bool) -> None:
        super().__init__()
        self._headless = headless
        self._browser_context: BrowserContext | None = None
        self._context_lock = asyncio.Lock()

    async def _get_page(self):
        async with self._context_lock:
            if self._browser_context is None:
                self._browser_context = await browser_runtime.launch_persistent_context(str(GOOGLE_SEARCH_PROFILE_DIRECTORY), self._headless)
            return self._browser_context.pages[0] if self._browser_context.pages else await self._browser_context.new_page()

    async def search(self, client: httpx.AsyncClient, query: str) -> list[str]:
        await self.pacer.wait_turn()
        page = await self._get_page()
        try:
            await page.goto(f"https://www.google.com/search?q={quote_plus(query)}&hl=fr&gl=fr", wait_until="domcontentloaded", timeout=30000)
            if "consent.google" in page.url:
                await page.click('button:has-text("Tout refuser"), button:has-text("Reject all")', timeout=10000)
                await page.wait_for_url(lambda url: "consent.google" not in url, timeout=20000)
            if "/sorry/" in page.url:
                raise SearchEngineBlockedError("CAPTCHA")
            await page.wait_for_selector("#search, #rso", timeout=15000)
            return parse_google_results(await page.content())
        except PlaywrightError as error:
            logger.warning("Google search failed for %s : %s", query, str(error).splitlines()[0])
            return []

    async def close(self) -> None:
        if self._browser_context is not None:
            await self._browser_context.close()
            self._browser_context = None


class SearchEngineRouter:
    """Query the enabled engines in order, skipping those that started blocking."""

    def __init__(self, engines: list[SearchEngine], log: Callable[[str], None]) -> None:
        self._engines = engines
        self._log = log

    @property
    def has_available_engine(self) -> bool:
        return any(not engine.blocked for engine in self._engines)

    async def search(self, client: httpx.AsyncClient, query: str) -> tuple[list[str], str | None]:
        """Return the results of the first engine that answers, with its key."""
        for engine in self._engines:
            if engine.blocked:
                continue
            try:
                result_urls = await engine.search(client, query)
            except SearchEngineBlockedError as error:
                # Insisting after a challenge extends the ban, so the engine is skipped for the rest of the job
                engine.blocked = True
                self._log(f"⚠️ {engine.label} bloque temporairement les recherches ({error}) : moteur désactivé pour cette tâche.")
                continue
            except httpx.HTTPError as error:
                logger.warning("%s request failed for %s : %s", engine.label, query, error)
                continue
            if result_urls:
                return result_urls, engine.key
        return [], None

    async def close(self) -> None:
        for engine in self._engines:
            await engine.close()


def build_search_engines(engine_keys: list[str], google_headless: bool) -> list[SearchEngine]:
    """Instantiate the engines selected in the settings, in their configured order."""
    engine_factories: dict[str, Callable[[], SearchEngine]] = {
        "duckduckgo": DuckDuckGoEngine,
        "bing": BingEngine,
        "google_browser": lambda: GoogleBrowserEngine(google_headless),
    }
    return [engine_factories[engine_key]() for engine_key in engine_keys if engine_key in engine_factories]
