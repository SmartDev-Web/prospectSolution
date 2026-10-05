"""Shared Playwright runtime used by the website scanner and the Google Maps scraper."""
import asyncio
import logging
import os

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

logger = logging.getLogger(__name__)
CHROMIUM_EXECUTABLE_OVERRIDE = os.environ.get("PROSPECT_CHROMIUM_PATH") or None


def read_proxy_settings() -> dict | None:
    """Reuse the system HTTP proxy for Chromium, which ignores proxy environment variables on its own."""
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    if not proxy_url:
        return None
    bypass_hosts = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    return {"server": proxy_url, "bypass": bypass_hosts} if bypass_hosts else {"server": proxy_url}


class BrowserRuntime:
    """Own a single Playwright driver and lazily started browsers."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._scanner_browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def get_playwright(self) -> Playwright:
        """Start the Playwright driver on first use."""
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            return self._playwright

    async def get_scanner_browser(self) -> Browser:
        """Return the headless browser shared by every website scan."""
        playwright = await self.get_playwright()
        async with self._lock:
            if self._scanner_browser is None or not self._scanner_browser.is_connected():
                self._scanner_browser = await playwright.chromium.launch(headless=True, executable_path=CHROMIUM_EXECUTABLE_OVERRIDE, proxy=read_proxy_settings())
            return self._scanner_browser

    async def launch_persistent_context(self, profile_directory: str, headless: bool) -> BrowserContext:
        """Open a browser keeping cookies between sessions, so it behaves like a returning visitor."""
        playwright = await self.get_playwright()
        return await playwright.chromium.launch_persistent_context(
            profile_directory,
            headless=headless,
            executable_path=CHROMIUM_EXECUTABLE_OVERRIDE,
            proxy=read_proxy_settings(),
            locale="fr-FR",
            timezone_id="Europe/Paris",
            viewport={"width": 1366, "height": 850},
            args=["--disable-blink-features=AutomationControlled"],
        )

    def chromium_executable_path(self) -> str | None:
        """Return the Chromium binary path, used by external tools such as Lighthouse."""
        if CHROMIUM_EXECUTABLE_OVERRIDE:
            return CHROMIUM_EXECUTABLE_OVERRIDE
        if self._playwright is None:
            return None
        return self._playwright.chromium.executable_path

    async def shutdown(self) -> None:
        """Close every browser and stop the driver."""
        async with self._lock:
            if self._scanner_browser is not None:
                await self._scanner_browser.close()
                self._scanner_browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None


browser_runtime = BrowserRuntime()
