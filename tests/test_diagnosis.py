import asyncio

from app.models import ProspectCandidate
from app.prospects import prospect_repository
from app.scanner import service
from app.scanner.catalog import build_finding
from app.scanner.http_probe import HttpProbeResult
from app.scanner.renderer import RenderResult, ViewportRender
from app.scanner.service import edit_diagnosis, store_scan


def create_scanned_prospect(findings):
    prospect_identifier = prospect_repository._insert_prospect(ProspectCandidate(name="Allo Artisans 34", source="manual", website_url="https://alloartisans34.com/"))
    store_scan(prospect_identifier, {"reachable": True, "score": 0, "findings": findings, "metrics": {}, "contacts": {}, "report": {"strengths": []}})
    return prospect_identifier


def test_dismissing_a_wrong_finding_rebuilds_score_and_report():
    prospect_identifier = create_scanned_prospect([build_finding("no_viewport"), build_finding("missing_legal_notice")])
    detail = edit_diagnosis(prospect_identifier, {"dismissed_codes": ["no_viewport"], "custom_findings": [], "summary": None})
    report = detail["latest_scan"]["report"]
    assert [problem["code"] for problem in report["problems"]] == ["missing_legal_notice"]
    assert [finding["code"] for finding in report["dismissed_findings"]] == ["no_viewport"]
    assert report["manually_edited"] is True
    assert detail["score"] > 40 and detail["opportunity_level"] == "cold"


def test_custom_points_and_summary_are_kept():
    prospect_identifier = create_scanned_prospect([])
    overrides = {
        "dismissed_codes": [],
        "custom_findings": [{"title": "Quelques défauts d'affichage sur mobile", "impact": "", "recommendation": "", "severity": "minor", "category": "mobile"}],
        "summary": "Site plutôt joli, à peaufiner sur mobile.",
    }
    report = edit_diagnosis(prospect_identifier, overrides)["latest_scan"]["report"]
    assert report["summary"] == "Site plutôt joli, à peaufiner sur mobile."
    assert report["problems"][0]["title"] == "Quelques défauts d'affichage sur mobile" and report["problems"][0]["custom"] is True
    assert prospect_repository.get_prospect(prospect_identifier)["diagnosis_overrides"]["summary"] == overrides["summary"]


def test_site_refusing_scripted_requests_is_confirmed_by_the_browser(monkeypatch):
    async def fake_render(url, file_prefix):
        rendered_html = "<html><title>Allo Artisans 34</title><body>" + "Rénovation et dépannage à Saint-Aunès. " * 20 + "</body></html>"
        return RenderResult(final_url=url, rendered_html=rendered_html, desktop=ViewportRender(status_code=200, measurements={"viewportWidth": 1366}))
    monkeypatch.setattr(service, "render_website", fake_render)
    probe = HttpProbeResult(requested_url="https://alloartisans34.com/", final_url="https://alloartisans34.com/", status_code=503, error="code HTTP 503")
    render = asyncio.run(service.confirm_with_browser(probe, "https://alloartisans34.com/", "test"))
    assert render is not None and probe.reachable and "Saint-Aunès" in probe.html


def test_site_really_down_stays_unreachable(monkeypatch):
    async def fake_render(url, file_prefix):
        return RenderResult(final_url=url, error="net::ERR_CONNECTION_REFUSED")
    monkeypatch.setattr(service, "render_website", fake_render)
    probe = HttpProbeResult(requested_url="https://down.example/", status_code=503, error="code HTTP 503")
    assert asyncio.run(service.confirm_with_browser(probe, "https://down.example/", "test")) is None and not probe.reachable
