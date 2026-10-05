"""Turn raw website observations into business findings, strengths, metrics and contact details."""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from bs4 import BeautifulSoup

from app.scanner.catalog import build_finding, build_strength
from app.scanner.crawler import CrawledPage
from app.scanner.http_probe import CertificateInfo, HttpProbeResult
from app.scanner.renderer import RenderResult
from app.scanner.technologies import LOW_END_BUILDERS, detect_technologies
from app.sectors import Sector
from app.text_utils import find_email_addresses, find_phone_numbers, normalize_phone_number, strip_accents

COPYRIGHT_PATTERN = re.compile(r"(?:©|&copy;|\(c\)|copyright)\D{0,40}?((?:19|20)\d{2})(?:\s*[-–/à]\s*((?:19|20)\d{2}))?", re.IGNORECASE)
GENERATOR_VERSION_PATTERN = re.compile(r"(wordpress|joomla!?|drupal|prestashop|typo3|spip)\s*v?(\d+)(?:\.(\d+))?", re.IGNORECASE)
JQUERY_SOURCE_PATTERN = re.compile(r"jquery[.-]?(\d+\.\d+(?:\.\d+)?)(?:\.min)?\.js", re.IGNORECASE)
OUTDATED_CMS_MAJOR_VERSIONS = {"wordpress": 6, "joomla": 4, "drupal": 9, "prestashop": 8, "typo3": 11, "spip": 4}
CALL_TO_ACTION_KEYWORDS = (
    "contact", "devis", "appel", "réserv", "reserv", "command", "rendez", "rdv", "nous joindre", "téléphone", "telephone",
    "acheter", "boutique", "book", "call", "inscri", "estimation", "itinéraire", "venir", "order", "click", "panier",
)
TRACKER_SIGNATURES = (
    ("googletagmanager.com", "Google Tag Manager"), ("google-analytics.com", "Google Analytics"), ("gtag(", "Google Analytics"),
    ("connect.facebook.net", "Facebook Pixel"), ("hotjar", "Hotjar"), ("clarity.ms", "Microsoft Clarity"),
)
CONSENT_MANAGER_SIGNATURES = (
    "tarteaucitron", "axeptio", "cookiebot", "didomi", "onetrust", "complianz", "cookieyes", "iubenda", "usercentrics",
    "quantcast", "cookie-law-info", "cookie-notice", "gdpr-cookie", "klaro", "orejime", "cookie-script", "termly",
    "consentmanager", "sirdata", "wix-cookie", "cookie consent", "cookieconsent",
)
SOCIAL_NETWORK_DOMAINS = ("facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com", "pinterest.", "x.com/", "twitter.com")
MAP_SIGNATURES = ("google.com/maps", "maps.google", "goo.gl/maps", "maps.app.goo.gl", "openstreetmap", "leaflet", "mapbox", "waze.com", "itineraire", "plan d'acces", "plan d acces")
TESTIMONIAL_KEYWORDS = ("avis", "temoignage", "ils nous font confiance", "trustpilot", "google reviews", "note moyenne", "etoiles", "satisfaits", "nos clients disent", "references")
LEGAL_NOTICE_KEYWORDS = ("mentions legales", "mentions-legales", "mention legale", "informations legales", "legal notice", "imprint", "mentions_legales", "mentionslegales", "/legal", "mentions-l")
UNDER_CONSTRUCTION_KEYWORDS = ("en construction", "under construction", "site en cours de", "bientot disponible", "coming soon", "en cours de creation")
GENERIC_TITLES = {"accueil", "home", "index", "bienvenue", "untitled", "page d'accueil", "home page", "site", "welcome", "mon site"}
DATED_FONT_FAMILIES = {"times new roman": "Times New Roman", "times": "Times", "serif": "police par défaut", "comic sans ms": "Comic Sans", "papyrus": "Papyrus", "courier new": "Courier New"}
BOOKING_FEATURE_CODES = {"missing_online_booking", "missing_appointment_booking", "missing_online_ordering", "missing_quote_request"}
SLOW_PAINT_MAJOR_MILLISECONDS = 4000
SLOW_PAINT_MINOR_MILLISECONDS = 2500
HEAVY_PAGE_MAJOR_BYTES = 6_000_000
HEAVY_PAGE_MINOR_BYTES = 3_500_000


@dataclass
class AnalysisInput:
    """Everything observed about a website during a scan."""
    website_url: str
    sector: Sector
    probe: HttpProbeResult
    certificate: CertificateInfo | None = None
    https_alternative_reachable: bool = False
    render: RenderResult | None = None
    crawled_pages: list[CrawledPage] = field(default_factory=list)
    lighthouse_scores: dict[str, int] | None = None
    visual_assessment: dict[str, Any] | None = None
    favicon_found: bool = True
    google_rating: float | None = None
    google_review_count: int | None = None
    current_year: int = field(default_factory=lambda: date.today().year)


@dataclass
class PageView:
    """Pre-computed views of one or several pages shared by every check."""
    soup: BeautifulSoup
    html_lower: str
    text: str
    text_plain: str
    link_targets: list[str]
    link_texts_plain: list[str]

    @property
    def link_haystack(self) -> str:
        return " ".join([*self.link_texts_plain, *(target.lower() for target in self.link_targets)])


@dataclass
class AnalysisState:
    """Findings, strengths and metrics accumulated while the checks run."""
    findings: list[dict[str, Any]] = field(default_factory=list)
    strengths: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    design_signals: list[str] = field(default_factory=list)

    def add_finding(self, code: str, severity: str | None = None, **evidence: Any) -> None:
        self.findings.append(build_finding(code, severity, **evidence))

    def add_strength(self, code: str, **evidence: Any) -> None:
        self.strengths.append(build_strength(code, **evidence))

    def has_finding(self, *codes: str) -> bool:
        return any(finding["code"] in codes for finding in self.findings)


@dataclass
class AnalysisOutput:
    """Findings, strengths, metrics and contacts extracted from a website."""
    findings: list[dict[str, Any]]
    strengths: list[dict[str, str]]
    metrics: dict[str, Any]
    contacts: dict[str, Any]


def build_page_view(html_pages: list[str]) -> PageView:
    """Parse one or several pages and prepare normalized combined views."""
    visible_texts, link_targets, link_texts, html_parts = [], [], [], []
    first_soup = None
    for html in html_pages:
        full_soup = BeautifulSoup(html or "", "lxml")
        first_soup = first_soup or full_soup
        for anchor in full_soup.find_all("a"):
            link_targets.append((anchor.get("href") or "").strip())
            link_texts.append(strip_accents(anchor.get_text(" ", strip=True)).lower())
        text_soup = BeautifulSoup(html or "", "lxml")
        for invisible_element in text_soup(["script", "style", "noscript", "template"]):
            invisible_element.extract()
        visible_texts.append(text_soup.get_text(" ", strip=True))
        html_parts.append((html or "").lower())
    visible_text = " ".join(visible_texts)
    return PageView(
        soup=first_soup or BeautifulSoup("", "lxml"),
        html_lower=" ".join(html_parts),
        text=visible_text,
        text_plain=strip_accents(visible_text).lower(),
        link_targets=link_targets,
        link_texts_plain=link_texts,
    )


def desktop_measurements(analysis_input: AnalysisInput) -> dict[str, Any]:
    return analysis_input.render.desktop.measurements if analysis_input.render else {}


def mobile_measurements(analysis_input: AnalysisInput) -> dict[str, Any]:
    return analysis_input.render.mobile.measurements if analysis_input.render else {}


def check_availability_and_security(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Check HTTPS, certificate validity and redirections."""
    final_url = analysis_input.probe.final_url or analysis_input.website_url
    state.metrics["https"] = final_url.startswith("https://")
    if analysis_input.probe.certificate_error:
        state.add_finding("invalid_certificate", detail=analysis_input.probe.certificate_error[:120])
    elif analysis_input.certificate is not None:
        state.metrics["certificate_days_remaining"] = analysis_input.certificate.days_remaining
        if not analysis_input.certificate.valid:
            state.add_finding("invalid_certificate", detail=(analysis_input.certificate.error or "")[:120])
        elif analysis_input.certificate.days_remaining is not None and analysis_input.certificate.days_remaining < 15:
            state.add_finding("certificate_expiring", days=analysis_input.certificate.days_remaining)
    if not state.metrics["https"] and not analysis_input.probe.certificate_error:
        state.add_finding("http_not_redirected" if analysis_input.https_alternative_reachable else "no_https")
    if analysis_input.probe.http_redirects_to_https is False and state.metrics["https"]:
        state.add_finding("http_not_redirected")
    if analysis_input.render and state.metrics["https"]:
        insecure_resources = [url for url in analysis_input.render.desktop.http_resource_urls if not url.startswith("http://localhost")]
        if insecure_resources:
            state.add_finding("mixed_content", count=len(insecure_resources))
    if len(home.text) < 1500 and any(keyword in home.text_plain for keyword in UNDER_CONSTRUCTION_KEYWORDS):
        state.add_finding("site_under_construction")
    if state.metrics["https"] and not state.has_finding("invalid_certificate", "certificate_expiring", "mixed_content"):
        state.add_strength("secure")


def check_technology(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Detect the technologies of the site, their age, and obsolete markup."""
    generator_tag = home.soup.find("meta", attrs={"name": re.compile("^generator$", re.IGNORECASE)})
    generator_content = generator_tag.get("content", "") if generator_tag else ""
    technology_report = detect_technologies(home.html_lower, generator_content)
    state.metrics["generator"] = generator_content or None
    state.metrics["technologies"] = technology_report.names
    state.metrics["site_builder"] = technology_report.consumer_builder
    generator_match = GENERATOR_VERSION_PATTERN.search(generator_content)
    outdated_cms_label = None
    if generator_match and int(generator_match.group(2)) < OUTDATED_CMS_MAJOR_VERSIONS.get(generator_match.group(1).lower().rstrip("!"), 0):
        outdated_cms_label = f"{generator_match.group(1).capitalize()} {generator_match.group(2)}" + (f".{generator_match.group(3)}" if generator_match.group(3) else "")
    outdated_cms_label = outdated_cms_label or next((label for label in technology_report.outdated if label.startswith("WordPress")), None)
    if outdated_cms_label:
        state.add_finding("outdated_cms", detail=outdated_cms_label)
    outdated_libraries = [label for label in technology_report.outdated if not label.startswith("WordPress")]
    if outdated_libraries:
        state.add_finding("outdated_framework", detail=", ".join(outdated_libraries))
        state.design_signals.append("bibliothèques anciennes")
    if technology_report.consumer_builder:
        state.add_finding("site_builder", detail=technology_report.consumer_builder)
        if technology_report.consumer_builder in LOW_END_BUILDERS:
            state.design_signals.append(f"constructeur bas de gamme ({technology_report.consumer_builder})")
    jquery_source_match = JQUERY_SOURCE_PATTERN.search(home.html_lower)
    jquery_version = desktop_measurements(analysis_input).get("jqueryVersion") or (jquery_source_match.group(1) if jquery_source_match else None)
    state.metrics["jquery_version"] = jquery_version
    if jquery_version:
        version_numbers = [int(part) for part in re.findall(r"\d+", jquery_version)[:2]] + [0, 0]
        if version_numbers[0] < 3:
            state.add_finding("outdated_javascript", severity="major" if (version_numbers[0], version_numbers[1]) < (1, 9) else "minor", detail=jquery_version)
    if home.soup.select('embed[src$=".swf"], object[data$=".swf"], param[value$=".swf"]') or '.swf"' in home.html_lower:
        state.add_finding("flash_content")
    obsolete_tag_counts = {tag_name: len(home.soup.find_all(tag_name)) for tag_name in ("font", "center", "marquee", "blink", "frameset", "frame")}
    obsolete_tags = [f"<{tag_name}>" for tag_name, tag_count in obsolete_tag_counts.items() if tag_count and (tag_name in ("marquee", "blink", "frameset", "frame") or tag_count >= 3)]
    if obsolete_tags:
        state.add_finding("obsolete_html", detail=", ".join(obsolete_tags))
        state.design_signals.append("balises des années 2000")
    layout_tables = [
        table for table in home.soup.find_all("table")
        if table.find("table") or ((table.get("width") or table.get("cellpadding") or table.get("bgcolor")) and not table.find("th"))
    ]
    if len(layout_tables) >= 2:
        state.add_finding("table_layout")
        state.design_signals.append("mise en page en tableaux")
    doctype_area = home.html_lower.lstrip()[:300]
    for doctype_signature, doctype_label in (("html 4.01", "HTML 4.01"), ("xhtml 1.0", "XHTML 1.0"), ("xhtml 1.1", "XHTML 1.1"), ("html 3.2", "HTML 3.2")):
        if doctype_signature in doctype_area:
            state.add_finding("old_doctype", detail=doctype_label)
            state.design_signals.append(f"code {doctype_label}")
            break
    page_error_count = analysis_input.render.desktop.page_error_count if analysis_input.render else 0
    if page_error_count >= 3:
        state.add_finding("javascript_errors", count=page_error_count)
    if technology_report.modern_names and not technology_report.outdated and not technology_report.consumer_builder:
        state.add_strength("modern_stack", detail=", ".join(technology_report.modern_names[:3]))


def check_mobile(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Check that the site is usable on a smartphone."""
    viewport_tag = home.soup.find("meta", attrs={"name": re.compile("^viewport$", re.IGNORECASE)})
    state.metrics["has_viewport"] = viewport_tag is not None
    if viewport_tag is None:
        state.add_finding("no_viewport")
        state.design_signals.append("pas de version mobile")
    measurements = mobile_measurements(analysis_input)
    if not measurements:
        return
    overflow_pixels = int(measurements.get("documentWidth", 0) - measurements.get("viewportWidth", 0))
    state.metrics["mobile_overflow_pixels"] = overflow_pixels
    if viewport_tag is not None and overflow_pixels > 20:
        state.add_finding("mobile_horizontal_scroll", overflow=overflow_pixels)
    reading_font_size = measurements.get("medianParagraphFontSize") or measurements.get("bodyFontSize")
    state.metrics["mobile_font_size"] = reading_font_size
    if viewport_tag is not None and reading_font_size and reading_font_size < 14:
        state.add_finding("mobile_small_text", size=round(reading_font_size))
    if viewport_tag is not None and not state.has_finding("mobile_horizontal_scroll", "mobile_small_text"):
        state.add_strength("responsive")


def check_content(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Detect signs of an abandoned or amateur looking site."""
    copyright_years = [int(year) for copyright_match in COPYRIGHT_PATTERN.finditer(site.text) for year in copyright_match.groups() if year]
    plausible_years = [year for year in copyright_years if 1995 <= year <= analysis_input.current_year]
    if plausible_years:
        latest_year = max(plausible_years)
        state.metrics["copyright_year"] = latest_year
        years_since_update = analysis_input.current_year - latest_year
        if years_since_update >= 2:
            state.add_finding("outdated_copyright", severity="major" if years_since_update >= 3 else "minor", years=years_since_update, year=latest_year)
        if years_since_update >= 5:
            state.design_signals.append(f"contenu figé depuis {years_since_update} ans")
        if years_since_update <= 1:
            state.add_strength("recently_updated", year=latest_year)
    measurements = desktop_measurements(analysis_input)
    if measurements:
        reading_font_family = measurements.get("paragraphFontFamily") or measurements.get("bodyFontFamily") or ""
        primary_font_family = reading_font_family.split(",")[0].strip().strip("\"'").lower()
        state.metrics["font_family"] = primary_font_family or None
        if primary_font_family in DATED_FONT_FAMILIES:
            state.add_finding("dated_typography", detail=DATED_FONT_FAMILIES[primary_font_family])
            state.design_signals.append(f"police {DATED_FONT_FAMILIES[primary_font_family]}")
        desktop_font_size = measurements.get("medianParagraphFontSize")
        if desktop_font_size and desktop_font_size <= 12:
            state.design_signals.append(f"texte minuscule ({round(desktop_font_size)} px)")
    word_count = len(home.text.split())
    state.metrics["word_count"] = word_count
    if word_count < 150:
        state.add_finding("thin_content", count=word_count)
    elif len(site.text.split()) >= 600:
        state.add_strength("rich_content", count=len(site.text.split()))
    if not analysis_input.favicon_found and not home.soup.select('link[rel*="icon"]'):
        state.add_finding("missing_favicon")


def check_design_age(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Judge whether the site looks dated, from the visual model when available, otherwise from layout signals."""
    measurements = desktop_measurements(analysis_input)
    if measurements:
        state.metrics["layout"] = {
            "flex_grid": measurements.get("flexOrGridCount"),
            "floats": measurements.get("floatCount"),
            "semantic_tags": measurements.get("semanticElementCount"),
            "modern_images": measurements.get("modernImageCount"),
            "web_fonts": measurements.get("loadedWebFonts"),
        }
        if (measurements.get("flexOrGridCount") or 0) <= 3:
            state.design_signals.append("mise en page sans techniques modernes (flexbox/grid)")
        if (measurements.get("semanticElementCount") or 0) == 0:
            state.design_signals.append("structure HTML ancienne")
    state.metrics["design_signals"] = state.design_signals
    visual_assessment = analysis_input.visual_assessment
    if visual_assessment and isinstance(visual_assessment.get("design_score"), (int, float)):
        design_score = visual_assessment["design_score"]
        state.metrics["visual_design_score"] = design_score
        verdict = (visual_assessment.get("verdict") or "jugé daté par l'analyse visuelle")[:140]
        if design_score <= 4:
            state.add_finding("dated_design", severity="critical", detail=verdict)
        elif design_score <= 6:
            state.add_finding("dated_design", severity="major", detail=verdict)
        else:
            state.add_strength("modern_layout")
        return
    signal_count = len(state.design_signals)
    if signal_count >= 4:
        state.add_finding("dated_design", severity="critical", detail=", ".join(state.design_signals[:4]))
    elif signal_count == 3:
        state.add_finding("dated_design", severity="major", detail=", ".join(state.design_signals))
    elif signal_count == 0 and (measurements.get("flexOrGridCount") or 0) >= 20 and (measurements.get("semanticElementCount") or 0) >= 3:
        state.add_strength("modern_layout")


def check_performance(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Check display speed, page weight and the optional Lighthouse audit."""
    measurements = desktop_measurements(analysis_input)
    if not measurements:
        state.metrics["unmeasured_categories"] = ["performance"]
    if measurements:
        desktop_render = analysis_input.render.desktop
        largest_paint = measurements.get("largestContentfulPaintMilliseconds")
        first_paint = measurements.get("firstContentfulPaintMilliseconds")
        load_milliseconds = measurements.get("loadMilliseconds") or measurements.get("domContentLoadedMilliseconds")
        display_milliseconds = largest_paint or first_paint or load_milliseconds
        state.metrics["largest_paint_seconds"] = round(largest_paint / 1000, 1) if largest_paint else None
        state.metrics["load_seconds"] = round(load_milliseconds / 1000, 1) if load_milliseconds else None
        state.metrics["page_weight_megabytes"] = round(desktop_render.transferred_bytes / 1_000_000, 1)
        state.metrics["request_count"] = desktop_render.request_count
        if display_milliseconds and display_milliseconds > SLOW_PAINT_MINOR_MILLISECONDS:
            state.add_finding("slow_loading", severity="major" if display_milliseconds > SLOW_PAINT_MAJOR_MILLISECONDS else "minor", seconds=round(display_milliseconds / 1000, 1))
        elif display_milliseconds:
            state.add_strength("fast", seconds=round(display_milliseconds / 1000, 1))
        if desktop_render.transferred_bytes > HEAVY_PAGE_MINOR_BYTES:
            state.add_finding("heavy_page", severity="major" if desktop_render.transferred_bytes > HEAVY_PAGE_MAJOR_BYTES else "minor", megabytes=state.metrics["page_weight_megabytes"])
        if desktop_render.request_count > 150:
            state.add_finding("too_many_requests", count=desktop_render.request_count)
    if analysis_input.lighthouse_scores:
        state.metrics["lighthouse"] = analysis_input.lighthouse_scores
        lighthouse_thresholds = (("performance", 50, "lighthouse_performance"), ("accessibility", 70, "lighthouse_accessibility"), ("seo", 80, "lighthouse_seo"))
        for category_key, threshold, finding_code in lighthouse_thresholds:
            category_score = analysis_input.lighthouse_scores.get(category_key)
            if category_score is not None and category_score < threshold:
                state.add_finding(finding_code, score=category_score)


def check_search_engine_optimization(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Check the basic on-page signals used by Google."""
    title_text = home.soup.title.get_text(" ", strip=True) if home.soup.title else ""
    state.metrics["title"] = title_text or None
    if not title_text:
        state.add_finding("missing_title")
    elif len(title_text) < 10 or title_text.strip().lower() in GENERIC_TITLES:
        state.add_finding("poor_title", detail=title_text[:60])
    description_tag = home.soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    if description_tag is None or not (description_tag.get("content") or "").strip():
        state.add_finding("missing_meta_description")
    if home.soup.find("h1") is None:
        state.add_finding("missing_h1")
    if not home.soup.find_all("script", attrs={"type": "application/ld+json"}):
        state.add_finding("missing_structured_data")
    if home.soup.find("meta", attrs={"property": "og:title"}) is None:
        state.add_finding("missing_social_preview")
    images = home.soup.find_all("img")
    if len(images) >= 5:
        # An empty alt attribute is the correct markup for decorative images, only a missing attribute is an error
        missing_percentage = round(100 * sum(1 for image in images if image.get("alt") is None) / len(images))
        if missing_percentage >= 50:
            state.add_finding("missing_images_alt", percentage=missing_percentage)


def check_conversion(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Check everything that turns a visitor into a call or a request, across the crawled pages."""
    home_click_to_call = [target for target in home.link_targets if target.lower().startswith("tel:")]
    home_phone_numbers = find_phone_numbers(home.text)
    site_has_phone = bool(find_phone_numbers(site.text)) or any(target.lower().startswith("tel:") for target in site.link_targets)
    state.metrics["click_to_call"] = bool(home_click_to_call)
    if home_click_to_call:
        state.add_strength("click_to_call")
    elif home_phone_numbers:
        state.add_finding("no_click_to_call")
    elif site_has_phone:
        state.add_finding("no_phone_on_homepage")
    else:
        state.add_finding("no_phone_visible")
    if analysis_input.render and desktop_measurements(analysis_input):
        first_viewport_actions = [*desktop_measurements(analysis_input).get("firstViewportActions", []), *mobile_measurements(analysis_input).get("firstViewportActions", [])]
        has_call_to_action = any(keyword in action_text for action_text in first_viewport_actions for keyword in CALL_TO_ACTION_KEYWORDS)
        has_call_to_action = has_call_to_action or mobile_measurements(analysis_input).get("clickToCallInFirstViewport", False)
        state.metrics["call_to_action_above_fold"] = has_call_to_action
        if not has_call_to_action:
            state.add_finding("no_call_to_action")
    has_contact_form = any(form.find("textarea") or form.select('input[type="email"]') for form in BeautifulSoup(site.html_lower, "lxml").find_all("form"))
    has_contact_route = has_contact_form or "contact" in site.link_haystack or any(target.lower().startswith("mailto:") for target in site.link_targets)
    if not has_contact_route:
        state.add_finding("no_contact_form")
    if analysis_input.sector.is_local_storefront and not any(signature in site.html_lower or signature in site.text_plain for signature in MAP_SIGNATURES):
        state.add_finding("no_map")
    if not any(domain in target.lower() for target in site.link_targets for domain in SOCIAL_NETWORK_DOMAINS):
        state.add_finding("no_social_links")
    if not any(keyword in site.text_plain for keyword in TESTIMONIAL_KEYWORDS):
        state.add_finding("no_testimonials")
    if analysis_input.google_rating and analysis_input.google_rating >= 4.5 and (analysis_input.google_review_count or 0) >= 30:
        state.add_strength("good_reputation", rating=str(analysis_input.google_rating).replace(".", ","), count=analysis_input.google_review_count)


def check_legal_compliance(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Check the French legal notice and cookie consent obligations."""
    legal_haystack = f"{site.text_plain} {site.link_haystack}"
    if any(keyword in legal_haystack for keyword in LEGAL_NOTICE_KEYWORDS):
        state.add_strength("legal_ok")
    else:
        state.add_finding("missing_legal_notice")
    trackers = sorted({tracker_name for signature, tracker_name in TRACKER_SIGNATURES if signature in home.html_lower})
    state.metrics["trackers"] = trackers
    consent_banner_seen = bool(analysis_input.render) and any(
        viewport_render.measurements.get("cookieBannerDetected") for viewport_render in (analysis_input.render.desktop, analysis_input.render.mobile)
    )
    state.metrics["cookie_consent"] = consent_banner_seen or any(signature in home.html_lower for signature in CONSENT_MANAGER_SIGNATURES)
    if trackers and not state.metrics["cookie_consent"]:
        state.add_finding("missing_cookie_consent", detail=", ".join(trackers))


def check_sector_expectations(analysis_input: AnalysisInput, home: PageView, site: PageView, state: AnalysisState) -> None:
    """Check the features customers of this specific sector look for, anywhere on the crawled pages."""
    sector_haystack = f"{site.text_plain} {site.link_haystack} {site.html_lower}"
    for feature_expectation in analysis_input.sector.expected_features:
        normalized_keywords = [strip_accents(keyword).lower() for keyword in feature_expectation.keywords]
        if any(keyword in sector_haystack for keyword in normalized_keywords):
            if feature_expectation.code in BOOKING_FEATURE_CODES:
                state.add_strength("online_booking")
        else:
            state.add_finding(feature_expectation.code)


def extract_contacts(page_view: PageView) -> dict[str, Any]:
    """Collect phone numbers, emails and social profiles published on the pages."""
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


WEBSITE_CHECKS: tuple[Callable[[AnalysisInput, PageView, PageView, AnalysisState], None], ...] = (
    check_availability_and_security,
    check_technology,
    check_mobile,
    check_content,
    check_design_age,
    check_performance,
    check_search_engine_optimization,
    check_conversion,
    check_legal_compliance,
    check_sector_expectations,
)


def analyze_website(analysis_input: AnalysisInput) -> AnalysisOutput:
    """Run every check on a reachable website, using the homepage and the crawled internal pages."""
    rendered_html = analysis_input.render.rendered_html if analysis_input.render and analysis_input.render.rendered_html else ""
    home_html = rendered_html or analysis_input.probe.html
    home = build_page_view([home_html])
    site = build_page_view([home_html, *(crawled_page.html for crawled_page in analysis_input.crawled_pages)])
    state = AnalysisState(metrics={
        "final_url": analysis_input.probe.final_url,
        "http_status": analysis_input.probe.status_code,
        "crawled_pages": [crawled_page.url for crawled_page in analysis_input.crawled_pages],
    })
    for website_check in WEBSITE_CHECKS:
        website_check(analysis_input, home, site, state)
    unique_findings = list({finding["code"]: finding for finding in state.findings}.values())
    unique_strengths = list({strength["code"]: strength for strength in state.strengths}.values())
    return AnalysisOutput(findings=unique_findings, strengths=unique_strengths, metrics=state.metrics, contacts=extract_contacts(site))
