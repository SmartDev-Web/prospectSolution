"""Turn raw website observations into business findings, metrics and contact details."""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from bs4 import BeautifulSoup

from app.scanner.catalog import build_finding
from app.scanner.http_probe import CertificateInfo, HttpProbeResult
from app.scanner.renderer import RenderResult
from app.sectors import Sector
from app.text_utils import find_email_addresses, find_phone_numbers, normalize_phone_number, strip_accents

COPYRIGHT_PATTERN = re.compile(r"(?:©|&copy;|\(c\)|copyright)\D{0,40}?((?:19|20)\d{2})(?:\s*[-–/à]\s*((?:19|20)\d{2}))?", re.IGNORECASE)
GENERATOR_VERSION_PATTERN = re.compile(r"(wordpress|joomla!?|drupal|prestashop|typo3|spip)\s*v?(\d+)(?:\.(\d+))?", re.IGNORECASE)
JQUERY_SOURCE_PATTERN = re.compile(r"jquery[.-]?(\d+\.\d+(?:\.\d+)?)(?:\.min)?\.js", re.IGNORECASE)
OUTDATED_CMS_MAJOR_VERSIONS = {"wordpress": 6, "joomla": 4, "drupal": 9, "prestashop": 8, "typo3": 11, "spip": 4}
SITE_BUILDER_SIGNATURES = (
    ("wixstatic.com", "Wix"), ("wix.com", "Wix"), ("jimdo", "Jimdo"), ("webnode", "Webnode"), ("e-monsite", "e-monsite"),
    ("site123", "SITE123"), ("weebly", "Weebly"), ("img1.wsimg.com", "GoDaddy"), ("simplesite", "SimpleSite"),
    ("solocal", "Solocal (PagesJaunes)"), ("webself", "Webself"), ("mozello", "Mozello"), ("strikingly", "Strikingly"),
    ("websitex5", "WebSite X5"), ("website x5", "WebSite X5"), ("sitew.com", "SiteW"),
)
CALL_TO_ACTION_KEYWORDS = (
    "contact", "devis", "appel", "réserv", "reserv", "command", "rendez", "rdv", "nous joindre", "téléphone", "telephone",
    "acheter", "boutique", "book", "call", "inscri", "estimation", "itinéraire", "venir",
)
TRACKER_SIGNATURES = (
    ("googletagmanager.com", "Google Tag Manager"), ("google-analytics.com", "Google Analytics"), ("gtag(", "Google Analytics"),
    ("connect.facebook.net", "Facebook Pixel"), ("hotjar", "Hotjar"), ("clarity.ms", "Microsoft Clarity"),
)
CONSENT_MANAGER_SIGNATURES = (
    "tarteaucitron", "axeptio", "cookiebot", "didomi", "onetrust", "complianz", "cookieyes", "iubenda", "usercentrics",
    "quantcast", "cookie-law-info", "cookie-notice", "gdpr-cookie", "klaro", "orejime", "cookie-script", "termly",
)
SOCIAL_NETWORK_DOMAINS = ("facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com", "pinterest.", "x.com/", "twitter.com")
MAP_SIGNATURES = ("google.com/maps", "maps.google", "goo.gl/maps", "maps.app.goo.gl", "openstreetmap", "leaflet", "mapbox", "waze.com")
TESTIMONIAL_KEYWORDS = ("avis", "temoignage", "ils nous font confiance", "trustpilot", "google reviews", "note moyenne", "etoiles", "satisfaits")
LEGAL_NOTICE_KEYWORDS = ("mentions legales", "mentions-legales", "mention legale", "informations legales", "legal notice", "imprint", "mentions_legales", "mentionslegales")
UNDER_CONSTRUCTION_KEYWORDS = ("en construction", "under construction", "site en cours de", "bientot disponible", "coming soon", "en cours de creation")
GENERIC_TITLES = {"accueil", "home", "index", "bienvenue", "untitled", "page d'accueil", "home page", "site", "welcome"}
DATED_FONT_FAMILIES = {"times new roman": "Times New Roman", "times": "Times", "serif": "police par défaut", "comic sans ms": "Comic Sans", "papyrus": "Papyrus", "courier new": "Courier New"}


@dataclass
class AnalysisInput:
    """Everything observed about a website during a scan."""
    website_url: str
    sector: Sector
    probe: HttpProbeResult
    certificate: CertificateInfo | None = None
    https_alternative_reachable: bool = False
    render: RenderResult | None = None
    lighthouse_scores: dict[str, int] | None = None
    favicon_found: bool = True
    current_year: int = field(default_factory=lambda: date.today().year)


@dataclass
class PageView:
    """Pre-computed views of the page shared by every check."""
    soup: BeautifulSoup
    html_lower: str
    text: str
    text_plain: str
    link_targets: list[str]
    link_texts_plain: list[str]


@dataclass
class AnalysisOutput:
    """Findings, metrics and contacts extracted from a website."""
    findings: list[dict[str, Any]]
    metrics: dict[str, Any]
    contacts: dict[str, Any]


def build_page_view(html: str) -> PageView:
    """Parse the page once and prepare normalized views."""
    soup = BeautifulSoup(html or "", "lxml")
    for invisible_element in soup(["script", "style", "noscript", "template"]):
        invisible_element.extract()
    visible_text = soup.get_text(" ", strip=True)
    full_soup = BeautifulSoup(html or "", "lxml")
    anchors = full_soup.find_all("a")
    return PageView(
        soup=full_soup,
        html_lower=(html or "").lower(),
        text=visible_text,
        text_plain=strip_accents(visible_text).lower(),
        link_targets=[(anchor.get("href") or "").strip() for anchor in anchors],
        link_texts_plain=[strip_accents(anchor.get_text(" ", strip=True)).lower() for anchor in anchors],
    )


def check_availability_and_security(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Check HTTPS, certificate validity and redirections."""
    findings = []
    final_url = analysis_input.probe.final_url or analysis_input.website_url
    metrics["https"] = final_url.startswith("https://")
    if analysis_input.probe.certificate_error:
        findings.append(build_finding("invalid_certificate", detail=analysis_input.probe.certificate_error[:120]))
    elif analysis_input.certificate is not None:
        metrics["certificate_days_remaining"] = analysis_input.certificate.days_remaining
        if not analysis_input.certificate.valid:
            findings.append(build_finding("invalid_certificate", detail=(analysis_input.certificate.error or "")[:120]))
        elif analysis_input.certificate.days_remaining is not None and analysis_input.certificate.days_remaining < 15:
            findings.append(build_finding("certificate_expiring", days=analysis_input.certificate.days_remaining))
    if not metrics["https"] and not analysis_input.probe.certificate_error:
        findings.append(build_finding("http_not_redirected") if analysis_input.https_alternative_reachable else build_finding("no_https"))
    if analysis_input.probe.http_redirects_to_https is False and metrics["https"]:
        findings.append(build_finding("http_not_redirected"))
    if analysis_input.render and metrics["https"]:
        insecure_resources = [url for url in analysis_input.render.desktop.http_resource_urls if not url.startswith("http://localhost")]
        if insecure_resources:
            findings.append(build_finding("mixed_content", count=len(insecure_resources)))
    if len(page_view.text) < 1500 and any(keyword in page_view.text_plain for keyword in UNDER_CONSTRUCTION_KEYWORDS):
        findings.append(build_finding("site_under_construction"))
    return findings


def check_technology(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Detect outdated CMS, libraries, markup and site builders."""
    findings = []
    generator_tag = page_view.soup.find("meta", attrs={"name": re.compile("^generator$", re.IGNORECASE)})
    generator_content = generator_tag.get("content", "") if generator_tag else ""
    metrics["generator"] = generator_content or None
    generator_match = GENERATOR_VERSION_PATTERN.search(generator_content)
    if generator_match:
        cms_name = generator_match.group(1).lower().rstrip("!")
        major_version = int(generator_match.group(2))
        if major_version < OUTDATED_CMS_MAJOR_VERSIONS.get(cms_name, 0):
            version_label = f"{generator_match.group(2)}.{generator_match.group(3)}" if generator_match.group(3) else generator_match.group(2)
            findings.append(build_finding("outdated_cms", detail=f"{generator_match.group(1).capitalize()} {version_label}"))
    site_builder = next((builder_name for signature, builder_name in SITE_BUILDER_SIGNATURES if signature in page_view.html_lower), None)
    metrics["site_builder"] = site_builder
    if site_builder:
        findings.append(build_finding("site_builder", detail=site_builder))
    measured_jquery_version = analysis_input.render.desktop.measurements.get("jqueryVersion") if analysis_input.render else None
    jquery_source_match = JQUERY_SOURCE_PATTERN.search(page_view.html_lower)
    jquery_version = measured_jquery_version or (jquery_source_match.group(1) if jquery_source_match else None)
    metrics["jquery_version"] = jquery_version
    if jquery_version:
        version_numbers = [int(part) for part in re.findall(r"\d+", jquery_version)[:2]] + [0, 0]
        if version_numbers[0] < 3:
            severity = "major" if (version_numbers[0], version_numbers[1]) < (1, 9) else "minor"
            findings.append(build_finding("outdated_javascript", severity=severity, detail=jquery_version))
    if page_view.soup.select('embed[src$=".swf"], object[data$=".swf"], param[value$=".swf"]') or ".swf\"" in page_view.html_lower:
        findings.append(build_finding("flash_content"))
    obsolete_tag_counts = {tag_name: len(page_view.soup.find_all(tag_name)) for tag_name in ("font", "center", "marquee", "blink", "frameset", "frame")}
    obsolete_tags = [f"<{tag_name}>" for tag_name, tag_count in obsolete_tag_counts.items() if tag_count and (tag_name in ("marquee", "blink", "frameset", "frame") or tag_count >= 3)]
    if obsolete_tags:
        findings.append(build_finding("obsolete_html", detail=", ".join(obsolete_tags)))
    layout_tables = [
        table for table in page_view.soup.find_all("table")
        if table.find("table") or ((table.get("width") or table.get("cellpadding") or table.get("bgcolor")) and not table.find("th"))
    ]
    if len(layout_tables) >= 2:
        findings.append(build_finding("table_layout"))
    doctype_area = page_view.html_lower.lstrip()[:300]
    for doctype_signature, doctype_label in (("html 4.01", "HTML 4.01"), ("xhtml 1.0", "XHTML 1.0"), ("xhtml 1.1", "XHTML 1.1"), ("html 3.2", "HTML 3.2")):
        if doctype_signature in doctype_area:
            findings.append(build_finding("old_doctype", detail=doctype_label))
            break
    if analysis_input.render and analysis_input.render.desktop.console_error_count >= 5:
        findings.append(build_finding("javascript_errors", count=analysis_input.render.desktop.console_error_count))
    return findings


def check_mobile(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Check that the site is usable on a smartphone."""
    findings = []
    viewport_tag = page_view.soup.find("meta", attrs={"name": re.compile("^viewport$", re.IGNORECASE)})
    metrics["has_viewport"] = viewport_tag is not None
    if viewport_tag is None:
        findings.append(build_finding("no_viewport"))
    if analysis_input.render is None or not analysis_input.render.mobile.measurements:
        return findings
    mobile_measurements = analysis_input.render.mobile.measurements
    overflow_pixels = int(mobile_measurements.get("documentWidth", 0) - mobile_measurements.get("viewportWidth", 0))
    metrics["mobile_overflow_pixels"] = overflow_pixels
    if viewport_tag is not None and overflow_pixels > 20:
        findings.append(build_finding("mobile_horizontal_scroll", overflow=overflow_pixels))
    reading_font_size = mobile_measurements.get("medianParagraphFontSize") or mobile_measurements.get("bodyFontSize")
    metrics["mobile_font_size"] = reading_font_size
    if viewport_tag is not None and reading_font_size and reading_font_size < 14:
        findings.append(build_finding("mobile_small_text", size=round(reading_font_size)))
    return findings


def check_content_and_design(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Detect signs of an abandoned or amateur looking site."""
    findings = []
    copyright_years = []
    for copyright_match in COPYRIGHT_PATTERN.finditer(page_view.text):
        copyright_years.extend(int(year) for year in copyright_match.groups() if year)
    plausible_years = [year for year in copyright_years if 1995 <= year <= analysis_input.current_year]
    if plausible_years:
        latest_year = max(plausible_years)
        metrics["copyright_year"] = latest_year
        years_since_update = analysis_input.current_year - latest_year
        if years_since_update >= 2:
            findings.append(build_finding("outdated_copyright", severity="major" if years_since_update >= 3 else "minor", years=years_since_update, year=latest_year))
    if analysis_input.render and analysis_input.render.desktop.measurements:
        font_family_text = analysis_input.render.desktop.measurements.get("bodyFontFamily") or ""
        primary_font_family = font_family_text.split(",")[0].strip().strip("\"'").lower()
        metrics["font_family"] = primary_font_family or None
        if primary_font_family in DATED_FONT_FAMILIES:
            findings.append(build_finding("dated_typography", detail=DATED_FONT_FAMILIES[primary_font_family]))
    word_count = len(page_view.text.split())
    metrics["word_count"] = word_count
    if word_count < 150:
        findings.append(build_finding("thin_content", count=word_count))
    images = page_view.soup.find_all("img")
    if len(images) >= 5:
        images_without_alt = sum(1 for image in images if not (image.get("alt") or "").strip())
        missing_percentage = round(100 * images_without_alt / len(images))
        if missing_percentage >= 50:
            findings.append(build_finding("missing_images_alt", percentage=missing_percentage))
    if not analysis_input.favicon_found and not page_view.soup.select('link[rel*="icon"]'):
        findings.append(build_finding("missing_favicon"))
    return findings


def check_performance(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Check loading speed, page weight and the optional Lighthouse audit."""
    findings = []
    if analysis_input.render and analysis_input.render.desktop.measurements:
        desktop_render = analysis_input.render.desktop
        load_milliseconds = desktop_render.measurements.get("loadMilliseconds") or desktop_render.measurements.get("domContentLoadedMilliseconds")
        metrics["load_seconds"] = round(load_milliseconds / 1000, 1) if load_milliseconds else None
        metrics["page_weight_megabytes"] = round(desktop_render.transferred_bytes / 1_000_000, 1)
        metrics["request_count"] = desktop_render.request_count
        if load_milliseconds and load_milliseconds > 3500:
            findings.append(build_finding("slow_loading", severity="major" if load_milliseconds > 6000 else "minor", seconds=metrics["load_seconds"]))
        if desktop_render.transferred_bytes > 3_000_000:
            findings.append(build_finding("heavy_page", severity="major" if desktop_render.transferred_bytes > 5_000_000 else "minor", megabytes=metrics["page_weight_megabytes"]))
        if desktop_render.request_count > 120:
            findings.append(build_finding("too_many_requests", count=desktop_render.request_count))
    if analysis_input.lighthouse_scores:
        metrics["lighthouse"] = analysis_input.lighthouse_scores
        performance_score = analysis_input.lighthouse_scores.get("performance")
        if performance_score is not None and performance_score < 50:
            findings.append(build_finding("lighthouse_performance", score=performance_score))
        accessibility_score = analysis_input.lighthouse_scores.get("accessibility")
        if accessibility_score is not None and accessibility_score < 70:
            findings.append(build_finding("lighthouse_accessibility", score=accessibility_score))
        seo_score = analysis_input.lighthouse_scores.get("seo")
        if seo_score is not None and seo_score < 80:
            findings.append(build_finding("lighthouse_seo", score=seo_score))
    return findings


def check_search_engine_optimization(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Check the basic on-page signals used by Google."""
    findings = []
    title_text = page_view.soup.title.get_text(" ", strip=True) if page_view.soup.title else ""
    metrics["title"] = title_text or None
    if not title_text:
        findings.append(build_finding("missing_title"))
    elif len(title_text) < 15 or title_text.strip().lower() in GENERIC_TITLES:
        findings.append(build_finding("poor_title", detail=title_text[:60]))
    description_tag = page_view.soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    if description_tag is None or not (description_tag.get("content") or "").strip():
        findings.append(build_finding("missing_meta_description"))
    if page_view.soup.find("h1") is None:
        findings.append(build_finding("missing_h1"))
    structured_data_blocks = " ".join(script.get_text() for script in page_view.soup.find_all("script", attrs={"type": "application/ld+json"}))
    if not structured_data_blocks.strip():
        findings.append(build_finding("missing_structured_data"))
    if page_view.soup.find("meta", attrs={"property": "og:title"}) is None:
        findings.append(build_finding("missing_social_preview"))
    return findings


def check_conversion(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Check everything that turns a visitor into a call or a request."""
    findings = []
    click_to_call_links = [target for target in page_view.link_targets if target.lower().startswith("tel:")]
    visible_phone_numbers = find_phone_numbers(page_view.text)
    metrics["click_to_call"] = bool(click_to_call_links)
    if not click_to_call_links and visible_phone_numbers:
        findings.append(build_finding("no_click_to_call"))
    elif not click_to_call_links and not visible_phone_numbers:
        findings.append(build_finding("no_phone_visible"))
    if analysis_input.render:
        first_viewport_actions = [
            *analysis_input.render.desktop.measurements.get("firstViewportActions", []),
            *analysis_input.render.mobile.measurements.get("firstViewportActions", []),
        ]
        has_call_to_action = any(keyword in action_text for action_text in first_viewport_actions for keyword in CALL_TO_ACTION_KEYWORDS)
        has_call_to_action = has_call_to_action or analysis_input.render.mobile.measurements.get("clickToCallInFirstViewport", False)
        metrics["call_to_action_above_fold"] = has_call_to_action
        if analysis_input.render.desktop.measurements and not has_call_to_action:
            findings.append(build_finding("no_call_to_action"))
    has_contact_form = any(form.find(["textarea"]) or form.select('input[type="email"]') for form in page_view.soup.find_all("form"))
    links_to_contact_page = any("contact" in target.lower() for target in page_view.link_targets) or any("contact" in text for text in page_view.link_texts_plain)
    has_mailto = any(target.lower().startswith("mailto:") for target in page_view.link_targets)
    if not has_contact_form and not links_to_contact_page and not has_mailto:
        findings.append(build_finding("no_contact_form"))
    if analysis_input.sector.is_local_storefront and not any(signature in page_view.html_lower for signature in MAP_SIGNATURES):
        findings.append(build_finding("no_map"))
    if not any(domain in target.lower() for target in page_view.link_targets for domain in SOCIAL_NETWORK_DOMAINS):
        findings.append(build_finding("no_social_links"))
    if not any(keyword in page_view.text_plain for keyword in TESTIMONIAL_KEYWORDS):
        findings.append(build_finding("no_testimonials"))
    return findings


def check_legal_compliance(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Check the French legal notice and cookie consent obligations."""
    findings = []
    legal_haystack = " ".join([page_view.text_plain, *page_view.link_texts_plain, *(target.lower() for target in page_view.link_targets)])
    if not any(keyword in legal_haystack for keyword in LEGAL_NOTICE_KEYWORDS):
        findings.append(build_finding("missing_legal_notice"))
    trackers = sorted({tracker_name for signature, tracker_name in TRACKER_SIGNATURES if signature in page_view.html_lower})
    metrics["trackers"] = trackers
    consent_banner_seen = bool(analysis_input.render) and any(
        viewport_render.measurements.get("cookieBannerDetected") for viewport_render in (analysis_input.render.desktop, analysis_input.render.mobile)
    )
    consent_manager_present = any(signature in page_view.html_lower for signature in CONSENT_MANAGER_SIGNATURES)
    metrics["cookie_consent"] = consent_banner_seen or consent_manager_present
    if trackers and not metrics["cookie_consent"]:
        findings.append(build_finding("missing_cookie_consent", detail=", ".join(trackers)))
    return findings


def check_sector_expectations(analysis_input: AnalysisInput, page_view: PageView, metrics: dict[str, Any]) -> list[dict]:
    """Check the features customers of this specific sector look for."""
    findings = []
    sector_haystack = " ".join([page_view.text_plain, *page_view.link_texts_plain, *(target.lower() for target in page_view.link_targets), page_view.html_lower[:5000]])
    for feature_expectation in analysis_input.sector.expected_features:
        normalized_keywords = [strip_accents(keyword).lower() for keyword in feature_expectation.keywords]
        if not any(keyword in sector_haystack for keyword in normalized_keywords):
            findings.append(build_finding(feature_expectation.code))
    return findings


def extract_contacts(page_view: PageView) -> dict[str, Any]:
    """Collect phone numbers, emails and social profiles published on the page."""
    phone_numbers = [normalize_phone_number(target[4:]) for target in page_view.link_targets if target.lower().startswith("tel:")]
    phone_numbers += find_phone_numbers(page_view.text)
    email_addresses = [target[7:].split("?")[0].strip().lower() for target in page_view.link_targets if target.lower().startswith("mailto:")]
    email_addresses += find_email_addresses(page_view.text)
    social_profiles = [target for target in page_view.link_targets if any(domain in target.lower() for domain in SOCIAL_NETWORK_DOMAINS) and "share" not in target.lower()]
    return {
        "phones": list(dict.fromkeys(phone for phone in phone_numbers if phone))[:5],
        "emails": list(dict.fromkeys(email for email in email_addresses if "@" in email))[:5],
        "social_profiles": list(dict.fromkeys(social_profiles))[:8],
    }


WEBSITE_CHECKS: tuple[Callable[[AnalysisInput, PageView, dict[str, Any]], list[dict]], ...] = (
    check_availability_and_security,
    check_technology,
    check_mobile,
    check_content_and_design,
    check_performance,
    check_search_engine_optimization,
    check_conversion,
    check_legal_compliance,
    check_sector_expectations,
)


def analyze_website(analysis_input: AnalysisInput) -> AnalysisOutput:
    """Run every check on a reachable website."""
    rendered_html = analysis_input.render.rendered_html if analysis_input.render and analysis_input.render.rendered_html else ""
    page_view = build_page_view(rendered_html or analysis_input.probe.html)
    metrics: dict[str, Any] = {"final_url": analysis_input.probe.final_url, "http_status": analysis_input.probe.status_code}
    findings: list[dict] = []
    for website_check in WEBSITE_CHECKS:
        findings.extend(website_check(analysis_input, page_view, metrics))
    unique_findings = list({finding["code"]: finding for finding in findings}.values())
    return AnalysisOutput(findings=unique_findings, metrics=metrics, contacts=extract_contacts(page_view))
