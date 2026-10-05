"""Real browser rendering of a website: screenshots, layout and performance measurements."""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeoutError

from app.browser import browser_runtime
from app.config import BROWSER_USER_AGENT, MOBILE_USER_AGENT, SCREENSHOT_DIRECTORY

logger = logging.getLogger(__name__)
NAVIGATION_TIMEOUT_MS = 45000
LOAD_EVENT_TIMEOUT_MS = 20000
NETWORK_IDLE_TIMEOUT_MS = 6000
NAVIGATION_ATTEMPTS = 2
DESKTOP_VIEWPORT = {"width": 1366, "height": 768}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
COOKIE_BANNER_SELECTORS = (
    "#tarteaucitronRoot", "#tarteaucitronAlertBig", "#axeptio_overlay", ".axeptio_mount", "#CybotCookiebotDialog",
    "#onetrust-banner-sdk", "#onetrust-consent-sdk", ".cmplz-cookiebanner", "#cookie-notice", "#cookie-law-info-bar",
    ".cc-window", "#didomi-host", "#didomi-notice", ".iubenda-cs-container", "#usercentrics-root", "#cmplz-cookiebanner-container",
    "#moove_gdpr_cookie_info_bar", ".cookie-banner", "#cookie-banner", ".wpcc-container", "#qc-cmp2-container", "#sp_message_container",
)
PAGE_MEASUREMENT_SCRIPT = """
(cookieBannerSelectors) => {
    const isInFirstViewport = (element) => {
        const rectangle = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rectangle.width > 0 && rectangle.height > 0 && rectangle.top < window.innerHeight && rectangle.bottom > 0
            && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const bodyElement = document.body || document.documentElement;
    const bodyStyle = getComputedStyle(bodyElement);
    const paragraphs = [...document.querySelectorAll('p, li, td')].filter(element => element.innerText && element.innerText.trim().length > 40);
    const paragraphFontSizes = paragraphs.slice(0, 30).map(element => parseFloat(getComputedStyle(element).fontSize)).filter(Boolean).sort((first, second) => first - second);
    const navigationEntry = performance.getEntriesByType('navigation')[0];
    const firstViewportActions = [...document.querySelectorAll('a, button, input[type=submit], input[type=button]')]
        .filter(isInFirstViewport)
        .map(element => (element.innerText || element.value || element.getAttribute('aria-label') || element.getAttribute('title') || '').trim().toLowerCase())
        .filter(Boolean)
        .slice(0, 80);
    const headingElement = document.querySelector('h1, h2');
    return {
        viewportWidth: window.innerWidth,
        documentWidth: Math.max(document.documentElement.scrollWidth, bodyElement.scrollWidth),
        bodyFontSize: parseFloat(bodyStyle.fontSize),
        bodyFontFamily: bodyStyle.fontFamily,
        headingFontFamily: headingElement ? getComputedStyle(headingElement).fontFamily : null,
        medianParagraphFontSize: paragraphFontSizes.length ? paragraphFontSizes[Math.floor(paragraphFontSizes.length / 2)] : null,
        jqueryVersion: window.jQuery && window.jQuery.fn ? window.jQuery.fn.jquery : null,
        domContentLoadedMilliseconds: navigationEntry ? Math.round(navigationEntry.domContentLoadedEventEnd) : null,
        loadMilliseconds: navigationEntry && navigationEntry.loadEventEnd > 0 ? Math.round(navigationEntry.loadEventEnd) : null,
        firstViewportActions: firstViewportActions,
        clickToCallInFirstViewport: [...document.querySelectorAll('a[href^="tel:"]')].some(isInFirstViewport),
        cookieBannerDetected: cookieBannerSelectors.some(selector => document.querySelector(selector) !== null)
            || /cookie|traceur|consentement/i.test([...document.querySelectorAll('[class*=cookie], [id*=cookie], [class*=consent], [id*=consent]')].map(element => element.innerText).join(' ')),
        visibleTextLength: (bodyElement.innerText || '').length,
    };
}
"""


@dataclass
class ViewportRender:
    """Measurements and screenshot captured for one viewport."""
    screenshot_path: str | None = None
    measurements: dict[str, Any] = field(default_factory=dict)
    console_error_count: int = 0
    request_count: int = 0
    transferred_bytes: int = 0
    http_resource_urls: list[str] = field(default_factory=list)


@dataclass
class RenderResult:
    """Desktop and mobile renders of a homepage."""
    final_url: str | None = None
    rendered_html: str = ""
    desktop: ViewportRender = field(default_factory=ViewportRender)
    mobile: ViewportRender = field(default_factory=ViewportRender)
    error: str | None = None
    mobile_error: str | None = None


async def wait_for_page_settled(page: Page) -> None:
    """Wait for the load event then for network quiet, tolerating pages that never settle."""
    for load_state, timeout_milliseconds in (("load", LOAD_EVENT_TIMEOUT_MS), ("networkidle", NETWORK_IDLE_TIMEOUT_MS)):
        try:
            await page.wait_for_load_state(load_state, timeout=timeout_milliseconds)
        except PlaywrightTimeoutError:
            logger.debug("Page %s did not reach %s state", page.url, load_state)


async def navigate(page: Page, url: str) -> None:
    """Open a URL, retrying once when the network fails before any response."""
    for attempt_number in range(1, NAVIGATION_ATTEMPTS + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            return
        except PlaywrightError as error:
            if attempt_number == NAVIGATION_ATTEMPTS or "net::" not in str(error):
                raise
            logger.info("Navigation to %s failed (%s), retrying", url, str(error).splitlines()[0])


async def render_viewport(browser: Browser, url: str, viewport: dict, is_mobile: bool, screenshot_path: Path) -> tuple[ViewportRender, str, str]:
    """Load a page in a dedicated context, measure it and capture a screenshot."""
    browser_context = await browser.new_context(
        viewport=viewport,
        is_mobile=is_mobile,
        has_touch=is_mobile,
        user_agent=MOBILE_USER_AGENT if is_mobile else BROWSER_USER_AGENT,
        locale="fr-FR",
        ignore_https_errors=True,
    )
    viewport_render = ViewportRender()
    try:
        page = await browser_context.new_page()
        devtools_session = await browser_context.new_cdp_session(page)
        await devtools_session.send("Network.enable")
        def record_transferred_bytes(network_event: dict) -> None:
            viewport_render.transferred_bytes += int(network_event.get("encodedDataLength", 0))
        def record_request(request) -> None:
            viewport_render.request_count += 1
            if request.url.startswith("http://"):
                viewport_render.http_resource_urls.append(request.url)
        def record_console_message(console_message) -> None:
            if console_message.type == "error":
                viewport_render.console_error_count += 1
        def record_page_error(_page_error) -> None:
            viewport_render.console_error_count += 1
        devtools_session.on("Network.loadingFinished", record_transferred_bytes)
        page.on("request", record_request)
        page.on("console", record_console_message)
        page.on("pageerror", record_page_error)
        await navigate(page, url)
        await wait_for_page_settled(page)
        viewport_render.measurements = await page.evaluate(PAGE_MEASUREMENT_SCRIPT, list(COOKIE_BANNER_SELECTORS))
        await page.add_style_tag(content=", ".join(COOKIE_BANNER_SELECTORS) + " { display: none !important; }")
        await page.screenshot(path=str(screenshot_path), type="jpeg", quality=70)
        viewport_render.screenshot_path = screenshot_path.name
        return viewport_render, await page.content(), page.url
    finally:
        await browser_context.close()


async def render_website(url: str, file_prefix: str) -> RenderResult:
    """Render a homepage on desktop then on mobile, keeping the desktop render if only mobile fails."""
    render_result = RenderResult()
    browser = await browser_runtime.get_scanner_browser()
    try:
        render_result.desktop, render_result.rendered_html, render_result.final_url = await render_viewport(
            browser, url, DESKTOP_VIEWPORT, False, SCREENSHOT_DIRECTORY / f"{file_prefix}_desktop.jpg",
        )
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        logger.warning("Desktop rendering of %s failed : %s", url, error)
        render_result.error = str(error).splitlines()[0]
        return render_result
    try:
        render_result.mobile, _mobile_html, _mobile_url = await render_viewport(
            browser, render_result.final_url or url, MOBILE_VIEWPORT, True, SCREENSHOT_DIRECTORY / f"{file_prefix}_mobile.jpg",
        )
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        logger.warning("Mobile rendering of %s failed : %s", url, error)
        render_result.mobile_error = str(error).splitlines()[0]
    return render_result
