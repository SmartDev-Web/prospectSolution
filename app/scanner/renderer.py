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
STYLES_READY_TIMEOUT_MS = 20000
STYLES_READY_SCRIPT = """
() => [...document.querySelectorAll('link[rel="stylesheet"]')].every(link => link.sheet !== null || link.disabled)
    && (!document.fonts || document.fonts.status === 'loaded')
"""
DESKTOP_VIEWPORT = {"width": 1366, "height": 768}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
COOKIE_BANNER_SELECTORS = (
    "#tarteaucitronRoot", "#tarteaucitronAlertBig", "#axeptio_overlay", ".axeptio_mount", "#CybotCookiebotDialog",
    "#onetrust-banner-sdk", "#onetrust-consent-sdk", ".cmplz-cookiebanner", "#cookie-notice", "#cookie-law-info-bar",
    ".cc-window", "#didomi-host", "#didomi-notice", ".iubenda-cs-container", "#usercentrics-root", "#cmplz-cookiebanner-container",
    "#moove_gdpr_cookie_info_bar", ".cookie-banner", "#cookie-banner", ".wpcc-container", "#qc-cmp2-container", "#sp_message_container",
)
# Registered before any page script runs, so that the largest paint is captured as it happens
LARGEST_PAINT_OBSERVER_SCRIPT = """
window.__prospectLargestPaint = null;
try {
    new PerformanceObserver((entryList) => {
        const paintEntries = entryList.getEntries();
        if (paintEntries.length) window.__prospectLargestPaint = paintEntries[paintEntries.length - 1].startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (error) {}
"""
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
    const mostCommonValue = (values) => {
        const counts = new Map();
        values.forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
        return [...counts.entries()].sort((first, second) => second[1] - first[1]).map(entry => entry[0])[0] || null;
    };
    const firstPaintEntry = performance.getEntriesByType('paint').find(paintEntry => paintEntry.name === 'first-contentful-paint');
    const measureLayoutModernity = () => {
        let flexOrGridCount = 0;
        let floatCount = 0;
        for (const element of [...document.querySelectorAll('body *')].slice(0, 3000)) {
            const elementStyle = getComputedStyle(element);
            if (elementStyle.display.includes('flex') || elementStyle.display.includes('grid')) flexOrGridCount += 1;
            if (elementStyle.float === 'left' || elementStyle.float === 'right') floatCount += 1;
        }
        const images = [...document.images];
        return {
            flexOrGridCount,
            floatCount,
            semanticElementCount: document.querySelectorAll('header, nav, main, section, article, footer, aside').length,
            imageCount: images.length,
            modernImageCount: images.filter(image => /\\.(webp|avif)(\\?|$)/i.test(image.currentSrc || image.src)).length
                + document.querySelectorAll('source[type="image/webp"], source[type="image/avif"]').length,
            lazyImageCount: document.querySelectorAll('img[loading="lazy"]').length,
            loadedWebFonts: document.fonts ? [...new Set([...document.fonts].filter(font => font.status === 'loaded').map(font => font.family.replace(/["']/g, '')))].slice(0, 8) : [],
        };
    };
    return {
        viewportWidth: window.innerWidth,
        documentWidth: Math.max(document.documentElement.scrollWidth, bodyElement.scrollWidth),
        bodyFontSize: parseFloat(bodyStyle.fontSize),
        bodyFontFamily: bodyStyle.fontFamily,
        paragraphFontFamily: mostCommonValue(paragraphs.slice(0, 30).map(element => getComputedStyle(element).fontFamily)),
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
        ...measureLayoutModernity(),
        largestContentfulPaintMilliseconds: window.__prospectLargestPaint ? Math.round(window.__prospectLargestPaint) : null,
        firstContentfulPaintMilliseconds: firstPaintEntry ? Math.round(firstPaintEntry.startTime) : null,
    };
}
"""


@dataclass
class ViewportRender:
    """Measurements and screenshot captured for one viewport."""
    screenshot_path: str | None = None
    measurements: dict[str, Any] = field(default_factory=dict)
    console_error_count: int = 0
    page_error_count: int = 0
    status_code: int | None = None
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
    """Wait for the load event, the stylesheets, the web fonts and network quiet, tolerating pages that never settle."""
    for load_state, timeout_milliseconds in (("load", LOAD_EVENT_TIMEOUT_MS), ("networkidle", NETWORK_IDLE_TIMEOUT_MS)):
        try:
            await page.wait_for_load_state(load_state, timeout=timeout_milliseconds)
        except PlaywrightTimeoutError:
            logger.debug("Page %s did not reach %s state", page.url, load_state)
    try:
        # Measuring before the stylesheets apply would describe an unstyled page: default fonts and no layout
        await page.wait_for_function(STYLES_READY_SCRIPT, timeout=STYLES_READY_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        logger.debug("Stylesheets or fonts of %s never finished loading", page.url)


async def navigate(page: Page, url: str) -> int | None:
    """Open a URL and return the HTTP status, retrying once when the network fails before any response."""
    for attempt_number in range(1, NAVIGATION_ATTEMPTS + 1):
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            return response.status if response else None
        except PlaywrightError as error:
            if attempt_number == NAVIGATION_ATTEMPTS or not any(marker in str(error) for marker in ("net::", "chrome-error://")):
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
        await browser_context.add_init_script(LARGEST_PAINT_OBSERVER_SCRIPT)
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
            viewport_render.page_error_count += 1
        devtools_session.on("Network.loadingFinished", record_transferred_bytes)
        page.on("request", record_request)
        page.on("console", record_console_message)
        page.on("pageerror", record_page_error)
        viewport_render.status_code = await navigate(page, url)
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
