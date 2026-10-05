from app.scanner.analyzers import AnalysisInput, analyze_website
from app.scanner.catalog import compute_opportunity_level, compute_score
from app.scanner.http_probe import HttpProbeResult
from app.scanner.renderer import RenderResult, ViewportRender
from app.sectors import get_sector

OUTDATED_HTML = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><title>Accueil</title><meta name="generator" content="WordPress 4.9.8"></head>
<body><table width="900" bgcolor="#ffffff"><tr><td><table><tr><td>
<center><font face="Comic Sans MS">Bienvenue à la boucherie</font></center>
<font>Viandes</font><font>Volailles</font>
<embed src="intro.swf">
<p>Téléphone : 04 67 41 30 68</p>
<p>© 2014 Boucherie Brume</p>
</td></tr></table></td></tr></table>
<table width="900" cellpadding="0"><tr><td>Pied de page</td></tr></table>
<script src="/js/jquery-1.7.2.min.js"></script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>
</body></html>"""

MODERN_HTML = """<!doctype html><html lang="fr"><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Boucherie Brume, boucher à Castelnau-le-Lez</title>
<meta name="description" content="Boucherie artisanale à Castelnau-le-Lez : viandes locales, click & collect.">
<meta property="og:title" content="Boucherie Brume">
<link rel="icon" href="/favicon.svg">
<script type="application/ld+json">{"@type": "LocalBusiness"}</script>
</head><body>
<header><a href="tel:+33467413068">Appeler</a> <a href="/contact">Contact</a></header>
<h1>Boucherie artisanale à Castelnau-le-Lez</h1>
<p>Horaires : du mardi au samedi. Commandez en click & collect.</p>
<p>Ils nous font confiance : lisez les avis de nos clients.</p>
<iframe src="https://www.google.com/maps/embed?pb=1"></iframe>
<a href="https://www.facebook.com/boucheriebrume">Facebook</a>
<a href="/mentions-legales">Mentions légales</a>
<p>© 2026 Boucherie Brume</p>
""" + "<p>Viande locale de qualité. </p>" * 60 + "</body></html>"


def build_render(html: str, first_viewport_actions: list[str], click_to_call: bool) -> RenderResult:
    measurements = {
        "viewportWidth": 390, "documentWidth": 390, "bodyFontSize": 16, "bodyFontFamily": "Inter, sans-serif",
        "loadMilliseconds": 1200, "firstViewportActions": first_viewport_actions, "clickToCallInFirstViewport": click_to_call,
        "cookieBannerDetected": False,
    }
    return RenderResult(
        final_url="https://boucherie-brume.fr/",
        rendered_html=html,
        desktop=ViewportRender(measurements=dict(measurements), transferred_bytes=900_000, request_count=30),
        mobile=ViewportRender(measurements=dict(measurements)),
    )


def run_analysis(html: str, final_url: str, render: RenderResult | None) -> list[str]:
    analysis_output = analyze_website(AnalysisInput(
        website_url=final_url,
        sector=get_sector("butcher"),
        probe=HttpProbeResult(requested_url=final_url, final_url=final_url, status_code=200, html=html),
        render=render,
        current_year=2026,
    ))
    return [finding["code"] for finding in analysis_output.findings]


def test_outdated_site_triggers_the_expected_findings():
    finding_codes = run_analysis(OUTDATED_HTML, "http://boucherie-brume.fr/", None)
    expected_codes = {
        "no_https", "outdated_cms", "outdated_javascript", "flash_content", "obsolete_html", "table_layout", "old_doctype",
        "no_viewport", "outdated_copyright", "no_click_to_call", "missing_legal_notice", "missing_cookie_consent", "poor_title",
    }
    assert expected_codes <= set(finding_codes)


def test_modern_site_scores_well():
    findings_codes = run_analysis(MODERN_HTML, "https://boucherie-brume.fr/", build_render(MODERN_HTML, ["appeler", "contact"], True))
    assert findings_codes == []


def test_score_and_opportunity_levels():
    critical_finding = {"severity": "critical"}
    assert compute_score([critical_finding] * 6) == 0
    assert compute_opportunity_level(30, has_website=True) == "hot"
    assert compute_opportunity_level(60, has_website=True) == "warm"
    assert compute_opportunity_level(90, has_website=True) == "cold"
    assert compute_opportunity_level(None, has_website=False) == "no_website"
