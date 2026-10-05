"""Single entry point running a complete website audit for a prospect."""
import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import BROWSER_USER_AGENT
from app.database import get_database, utc_now_iso
from app.events import event_bus
from app.prospects import prospect_repository
from app.reports.llm_writer import enhance_report_with_language_model
from app.reports.diagnosis import finalize_diagnosis
from app.reports.rules import build_missing_website_findings
from app.reports.visual_review import assess_screenshot
from app.scanner.analyzers import AnalysisInput, analyze_website
from app.scanner.catalog import build_finding
from app.scanner.crawler import crawl_internal_pages
from app.scanner.http_probe import HttpProbeResult, check_http_redirect, fetch_homepage, inspect_certificate
from app.scanner.lighthouse import run_lighthouse
from app.scanner.renderer import RenderResult, render_website
from app.sectors import get_sector
from app.settings_service import load_settings

logger = logging.getLogger(__name__)


async def url_answers(url: str) -> bool:
    """Tell whether a URL responds without error."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=True, headers={"User-Agent": BROWSER_USER_AGENT}, transport=httpx.AsyncHTTPTransport(retries=2)) as client:
            response = await client.get(url)
        return response.status_code < 400
    except httpx.HTTPError:
        return False


def store_scan(prospect_identifier: int, scan_values: dict[str, Any]) -> int:
    """Persist a scan and return its identifier."""
    cursor = get_database().execute(
        """
        INSERT INTO scans (prospect_id, scanned_at, final_url, http_status, reachable, score, metrics, findings, contacts, desktop_screenshot, mobile_screenshot, report)
        VALUES (:prospect_id, :scanned_at, :final_url, :http_status, :reachable, :score, :metrics, :findings, :contacts, :desktop_screenshot, :mobile_screenshot, :report)
        """,
        {
            "prospect_id": prospect_identifier,
            "scanned_at": utc_now_iso(),
            "final_url": scan_values.get("final_url"),
            "http_status": scan_values.get("http_status"),
            "reachable": int(scan_values.get("reachable", False)),
            "score": scan_values.get("score"),
            "metrics": json.dumps(scan_values.get("metrics", {}), ensure_ascii=False),
            "findings": json.dumps(scan_values.get("findings", []), ensure_ascii=False),
            "contacts": json.dumps(scan_values.get("contacts", {}), ensure_ascii=False),
            "desktop_screenshot": scan_values.get("desktop_screenshot"),
            "mobile_screenshot": scan_values.get("mobile_screenshot"),
            "report": json.dumps(scan_values.get("report", {}), ensure_ascii=False),
        },
    )
    return cursor.lastrowid


MINIMUM_BROWSER_WORDS = 20


async def return_value(value: Any) -> Any:
    """Wrap an already known value so that it can join an asyncio.gather call."""
    return value


BLOCKED_PAGE_MARKERS = ("just a moment", "checking your browser", "attention required", "access denied", "verifier que vous etes humain", "vérifiez que vous êtes humain", "captcha")


def visible_word_count(html: str) -> int:
    """Count the visible words of a page."""
    soup = BeautifulSoup(html or "", "lxml")
    for invisible_element in soup(["script", "style", "noscript", "template"]):
        invisible_element.extract()
    return len(soup.get_text(" ", strip=True).split())


def find_render_problem(render: RenderResult, probe_html: str) -> str | None:
    """Explain why a browser render cannot be trusted, or return None when it shows the real site."""
    if render.error:
        return render.error
    if (render.final_url or "").startswith("chrome-error://"):
        return "page d'erreur du navigateur"
    rendered_text = BeautifulSoup(render.rendered_html or "", "lxml").get_text(" ", strip=True).lower()
    if len(rendered_text) < 600 and any(marker in rendered_text for marker in BLOCKED_PAGE_MARKERS):
        return "page bloquée par une protection anti-robot"
    probe_word_count = visible_word_count(probe_html)
    if probe_word_count >= 100 and visible_word_count(render.rendered_html) < probe_word_count * 0.2:
        return "page affichée quasiment vide par rapport au code source"
    return None


async def confirm_with_browser(probe: HttpProbeResult, website_url: str, file_prefix: str) -> RenderResult | None:
    """Open a site that refused the raw request in a real browser; return the render when visitors do see the site."""
    render = await render_website(probe.final_url or website_url, file_prefix)
    browser_status = render.desktop.status_code
    if render.error or (browser_status is not None and browser_status >= 400) or find_render_problem(render, "") is not None:
        return None
    if visible_word_count(render.rendered_html) < MINIMUM_BROWSER_WORDS:
        return None
    probe.final_url = render.final_url or probe.final_url or website_url
    probe.status_code = browser_status or 200
    probe.html = render.rendered_html
    probe.error = None
    return render


async def audit_reachable_website(prospect: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Collect every observation on a website and analyse it."""
    website_url = prospect["website_url"]
    file_prefix = f"{prospect['id']}_{int(time.time())}"
    probe = await fetch_homepage(website_url)
    browser_confirmed_render = None
    raw_request_refusal = None
    if not probe.reachable:
        # Hosting protections often refuse scripted requests while serving real browsers: only a browser failure proves an outage
        raw_request_refusal = probe.error
        browser_confirmed_render = await confirm_with_browser(probe, website_url, file_prefix)
        if browser_confirmed_render is None:
            unreachable_finding = build_finding("site_unreachable", detail=probe.error or "erreur inconnue")
            return {"reachable": False, "final_url": probe.final_url, "http_status": probe.status_code, "findings": [unreachable_finding], "strengths": [], "metrics": {"error": probe.error}, "contacts": {}}
    final_url = probe.final_url or website_url
    parsed_final_url = urlparse(final_url)
    https_alternative_reachable = False
    if parsed_final_url.scheme == "http":
        https_alternative_reachable = await url_answers(f"https://{parsed_final_url.netloc}/")
    else:
        probe.http_redirects_to_https = await check_http_redirect(parsed_final_url.netloc)
    certificate, render, favicon_found, crawled_pages = await asyncio.gather(
        inspect_certificate(final_url),
        return_value(browser_confirmed_render) if browser_confirmed_render else render_website(final_url, file_prefix),
        url_answers(f"{parsed_final_url.scheme}://{parsed_final_url.netloc}/favicon.ico"),
        crawl_internal_pages(final_url, probe.html, int(settings["crawl_internal_pages"])),
    )
    lighthouse_scores = await run_lighthouse(final_url) if settings["lighthouse_enabled"] else None
    render_problem = find_render_problem(render, probe.html)
    trusted_render = render if render_problem is None else None
    visual_assessment = await assess_screenshot(render.desktop.screenshot_path) if trusted_render else None
    analysis_output = analyze_website(AnalysisInput(
        website_url=website_url,
        sector=get_sector(prospect.get("sector_key")),
        probe=probe,
        certificate=certificate,
        https_alternative_reachable=https_alternative_reachable,
        render=trusted_render,
        crawled_pages=crawled_pages,
        lighthouse_scores=lighthouse_scores,
        visual_assessment=visual_assessment,
        favicon_found=favicon_found,
        google_rating=prospect.get("google_rating"),
        google_review_count=prospect.get("google_review_count"),
    ))
    if visual_assessment:
        analysis_output.metrics["visual_assessment"] = visual_assessment
    if raw_request_refusal:
        analysis_output.metrics["raw_request_refused"] = f"{raw_request_refusal} : le site a été vérifié avec un vrai navigateur"
    if render_problem or render.mobile_error:
        analysis_output.metrics["render_error"] = render_problem or f"mobile : {render.mobile_error}"
    return {
        "reachable": True,
        "final_url": final_url,
        "http_status": probe.status_code,
        "findings": analysis_output.findings,
        "strengths": analysis_output.strengths,
        "metrics": analysis_output.metrics,
        "contacts": analysis_output.contacts,
        "desktop_screenshot": render.desktop.screenshot_path if trusted_render else None,
        "mobile_screenshot": render.mobile.screenshot_path if trusted_render else None,
    }


async def scan_prospect(prospect_identifier: int) -> dict[str, Any] | None:
    """Audit the prospect website (or its absence), write the sales report and store everything."""
    prospect = prospect_repository.get_prospect(prospect_identifier)
    if prospect is None:
        return None
    settings = load_settings()
    if prospect.get("website_url"):
        scan_values = await audit_reachable_website(prospect, settings)
    else:
        scan_values = {"reachable": False, "findings": build_missing_website_findings(prospect), "strengths": [], "metrics": {}, "contacts": {}}
    score, opportunity_level, report = finalize_diagnosis(prospect, scan_values["findings"], scan_values["strengths"], scan_values["metrics"], scan_values["reachable"], settings)
    scan_values["score"] = score
    scan_values["report"] = await enhance_report_with_language_model(prospect, report)
    if (prospect.get("diagnosis_overrides") or {}).get("summary"):
        scan_values["report"]["summary"] = prospect["diagnosis_overrides"]["summary"]
    store_scan(prospect_identifier, scan_values)
    contacts = scan_values.get("contacts") or {}
    contact_changes = {
        "phone": (contacts.get("phones") or [None])[0],
        "email": (contacts.get("emails") or [None])[0],
        "social_url": next((profile for profile in contacts.get("social_profiles", []) if "facebook" in profile or "instagram" in profile), None),
    }
    prospect_repository.apply_scan_result(prospect_identifier, score, opportunity_level, contact_changes)
    event_bus.publish("scan.completed", {"prospect_id": prospect_identifier, "score": score, "opportunity_level": opportunity_level})
    return prospect_repository.get_prospect_detail(prospect_identifier)


def edit_diagnosis(prospect_identifier: int, overrides: dict[str, Any]) -> dict[str, Any] | None:
    """Store the user's corrections and rebuild the latest diagnosis, score and report from them."""
    prospect = prospect_repository.save_diagnosis_overrides(prospect_identifier, overrides)
    if prospect is None:
        return None
    latest_scan = get_database().fetch_one("SELECT * FROM scans WHERE prospect_id = ? ORDER BY scanned_at DESC, id DESC LIMIT 1", (prospect_identifier,))
    if latest_scan is None:
        return prospect_repository.get_prospect_detail(prospect_identifier)
    previous_report = latest_scan["report"] or {}
    score, opportunity_level, report = finalize_diagnosis(
        prospect, latest_scan["findings"] or [], previous_report.get("strengths") or [], latest_scan["metrics"] or {}, bool(latest_scan["reachable"]), load_settings(),
    )
    get_database().execute(
        "UPDATE scans SET score = ?, report = ? WHERE id = ?",
        (score, json.dumps(report, ensure_ascii=False), latest_scan["id"]),
    )
    prospect_repository.apply_scan_result(prospect_identifier, score, opportunity_level, {})
    return prospect_repository.get_prospect_detail(prospect_identifier)
