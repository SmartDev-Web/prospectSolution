"""Single entry point running a complete website audit for a prospect."""
import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import BROWSER_USER_AGENT
from app.database import get_database, utc_now_iso
from app.events import event_bus
from app.prospects import prospect_repository
from app.reports.llm_writer import enhance_report_with_language_model
from app.reports.rules import build_missing_website_findings, build_rule_based_report
from app.scanner.analyzers import AnalysisInput, analyze_website
from app.scanner.catalog import build_finding, compute_opportunity_level, compute_score
from app.scanner.http_probe import check_http_redirect, fetch_homepage, inspect_certificate
from app.scanner.lighthouse import run_lighthouse
from app.scanner.renderer import render_website
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


async def audit_reachable_website(prospect: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Collect every observation on a website and analyse it."""
    website_url = prospect["website_url"]
    probe = await fetch_homepage(website_url)
    if not probe.reachable:
        unreachable_finding = build_finding("site_unreachable", detail=probe.error or "erreur inconnue")
        return {"reachable": False, "final_url": probe.final_url, "http_status": probe.status_code, "findings": [unreachable_finding], "metrics": {"error": probe.error}, "contacts": {}}
    final_url = probe.final_url or website_url
    parsed_final_url = urlparse(final_url)
    https_alternative_reachable = False
    if parsed_final_url.scheme == "http":
        https_alternative_reachable = await url_answers(f"https://{parsed_final_url.netloc}/")
    else:
        probe.http_redirects_to_https = await check_http_redirect(parsed_final_url.netloc)
    certificate, render, favicon_found = await asyncio.gather(
        inspect_certificate(final_url),
        render_website(final_url, f"{prospect['id']}_{int(time.time())}"),
        url_answers(f"{parsed_final_url.scheme}://{parsed_final_url.netloc}/favicon.ico"),
    )
    lighthouse_scores = await run_lighthouse(final_url) if settings["lighthouse_enabled"] else None
    analysis_output = analyze_website(AnalysisInput(
        website_url=website_url,
        sector=get_sector(prospect.get("sector_key")),
        probe=probe,
        certificate=certificate,
        https_alternative_reachable=https_alternative_reachable,
        render=render if not render.error else None,
        lighthouse_scores=lighthouse_scores,
        favicon_found=favicon_found,
    ))
    if render.error or render.mobile_error:
        analysis_output.metrics["render_error"] = render.error or f"mobile : {render.mobile_error}"
    return {
        "reachable": True,
        "final_url": final_url,
        "http_status": probe.status_code,
        "findings": analysis_output.findings,
        "metrics": analysis_output.metrics,
        "contacts": analysis_output.contacts,
        "desktop_screenshot": render.desktop.screenshot_path,
        "mobile_screenshot": render.mobile.screenshot_path,
    }


async def scan_prospect(prospect_identifier: int) -> dict[str, Any] | None:
    """Audit the prospect website (or its absence), write the sales report and store everything."""
    prospect = prospect_repository.get_prospect(prospect_identifier)
    if prospect is None:
        return None
    settings = load_settings()
    if prospect.get("website_url"):
        scan_values = await audit_reachable_website(prospect, settings)
        score = compute_score(scan_values["findings"]) if scan_values["reachable"] else 0
        opportunity_level = compute_opportunity_level(score, has_website=True, reachable=scan_values["reachable"])
    else:
        scan_values = {"reachable": False, "findings": build_missing_website_findings(prospect), "metrics": {}, "contacts": {}}
        score = None
        opportunity_level = compute_opportunity_level(None, has_website=False)
    scan_values["score"] = score
    report = build_rule_based_report(prospect, scan_values["findings"], score, opportunity_level, settings)
    scan_values["report"] = await enhance_report_with_language_model(prospect, report)
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
