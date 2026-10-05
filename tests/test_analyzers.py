from app.scanner.analyzers import AnalysisInput, AnalysisOutput, analyze_website
from app.scanner.catalog import compute_opportunity_level, compute_score
from app.scanner.crawler import CrawledPage
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
        "cookieBannerDetected": False, "largestContentfulPaintMilliseconds": 1100, "flexOrGridCount": 45, "semanticElementCount": 6,
    }
    return RenderResult(
        final_url="https://boucherie-brume.fr/",
        rendered_html=html,
        desktop=ViewportRender(measurements=dict(measurements), transferred_bytes=900_000, request_count=30),
        mobile=ViewportRender(measurements=dict(measurements)),
    )


def run_analysis(html: str, final_url: str, render: RenderResult | None, crawled_pages: list[CrawledPage] | None = None) -> AnalysisOutput:
    return analyze_website(AnalysisInput(
        website_url=final_url,
        sector=get_sector("butcher"),
        probe=HttpProbeResult(requested_url=final_url, final_url=final_url, status_code=200, html=html),
        render=render,
        crawled_pages=crawled_pages or [],
        current_year=2026,
    ))


def finding_codes(analysis_output: AnalysisOutput) -> list[str]:
    return [finding["code"] for finding in analysis_output.findings]


def test_outdated_site_triggers_the_expected_findings():
    analysis_output = run_analysis(OUTDATED_HTML, "http://boucherie-brume.fr/", None)
    expected_codes = {"dated_design",
        "no_https", "outdated_cms", "outdated_javascript", "flash_content", "obsolete_html", "table_layout", "old_doctype",
        "no_viewport", "outdated_copyright", "no_click_to_call", "missing_legal_notice", "missing_cookie_consent", "poor_title",
    }
    assert expected_codes <= set(finding_codes(analysis_output))
    assert compute_score(analysis_output.findings) <= 40


def test_modern_site_scores_well():
    analysis_output = run_analysis(MODERN_HTML, "https://boucherie-brume.fr/", build_render(MODERN_HTML, ["appeler", "contact"], True))
    assert finding_codes(analysis_output) == []
    assert compute_score(analysis_output.findings) == 100
    strength_codes = {strength["code"] for strength in analysis_output.strengths}
    assert {"secure", "responsive", "fast", "click_to_call", "legal_ok", "modern_layout", "online_booking", "recently_updated"} <= strength_codes


def test_internal_pages_are_taken_into_account():
    home_html = MODERN_HTML.replace('<a href="/mentions-legales">Mentions légales</a>', "").replace("click & collect", "")
    without_pages = finding_codes(run_analysis(home_html, "https://boucherie-brume.fr/", build_render(home_html, ["appeler"], True)))
    assert "missing_legal_notice" in without_pages and "missing_online_ordering" in without_pages
    legal_page = CrawledPage(url="https://boucherie-brume.fr/legal", page_type="legal", html="<h1>Mentions légales</h1><p>SIREN 123</p>")
    order_page = CrawledPage(url="https://boucherie-brume.fr/commande", page_type="booking", html="<p>Commandez en click & collect</p>")
    with_pages = finding_codes(run_analysis(home_html, "https://boucherie-brume.fr/", build_render(home_html, ["appeler"], True), [legal_page, order_page]))
    assert "missing_legal_notice" not in with_pages and "missing_online_ordering" not in with_pages


def test_modern_site_with_minor_gaps_stays_cold():
    gaps_html = MODERN_HTML.replace('<script type="application/ld+json">{"@type": "LocalBusiness"}</script>', "").replace('<meta property="og:title" content="Boucherie Brume">', "")
    gaps_html = gaps_html.replace("lisez les avis de nos clients", "").replace('<a href="https://www.facebook.com/boucheriebrume">Facebook</a>', "")
    analysis_output = run_analysis(gaps_html, "https://boucherie-brume.fr/", build_render(gaps_html, ["appeler"], True))
    assert compute_opportunity_level(compute_score(analysis_output.findings), has_website=True) == "cold"


def test_score_and_opportunity_levels():
    critical_finding = {"severity": "critical", "category": "security"}
    assert compute_score([critical_finding]) == 40
    assert compute_opportunity_level(30, has_website=True) == "hot"
    assert compute_opportunity_level(60, has_website=True) == "warm"
    assert compute_opportunity_level(90, has_website=True) == "cold"
    assert compute_opportunity_level(None, has_website=False) == "no_website"
