"""Lightweight detection of the technologies a website is built with, and of their age."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TechnologySignature:
    """How to recognise a technology and how to judge it."""
    name: str
    patterns: tuple[str, ...]
    kind: str
    modern: bool = False
    consumer_builder: bool = False


TECHNOLOGY_SIGNATURES: tuple[TechnologySignature, ...] = (
    TechnologySignature("Wix", ("static.wixstatic.com", "wix.com website builder", "_wixcss"), "builder", consumer_builder=True),
    TechnologySignature("Jimdo", ("jimdo", "jimcdn.com"), "builder", consumer_builder=True),
    TechnologySignature("Webnode", ("webnode",), "builder", consumer_builder=True),
    TechnologySignature("e-monsite", ("e-monsite",), "builder", consumer_builder=True),
    TechnologySignature("SITE123", ("site123",), "builder", consumer_builder=True),
    TechnologySignature("Weebly", ("weebly",), "builder", consumer_builder=True),
    TechnologySignature("GoDaddy", ("img1.wsimg.com",), "builder", consumer_builder=True),
    TechnologySignature("SimpleSite", ("simplesite",), "builder", consumer_builder=True),
    TechnologySignature("Solocal (PagesJaunes)", ("solocal",), "builder", consumer_builder=True),
    TechnologySignature("Webself", ("webself",), "builder", consumer_builder=True),
    TechnologySignature("WebSite X5", ("websitex5", "website x5"), "builder", consumer_builder=True),
    TechnologySignature("SiteW", ("sitew.com",), "builder", consumer_builder=True),
    TechnologySignature("Squarespace", ("squarespace",), "builder", modern=True),
    TechnologySignature("Webflow", ("webflow",), "builder", modern=True),
    TechnologySignature("Shopify", ("cdn.shopify.com",), "builder", modern=True),
    TechnologySignature("Framer", ("framerusercontent.com", "framer.com"), "builder", modern=True),
    TechnologySignature("WordPress", ("/wp-content/", "/wp-includes/"), "cms"),
    TechnologySignature("Elementor", ("/plugins/elementor/", "elementor-kit-", "elementor-element"), "page_builder", modern=True),
    TechnologySignature("Divi", ("et_pb_section", "/themes/divi/"), "page_builder", modern=True),
    TechnologySignature("Joomla", ("/media/jui/", "/media/system/js/", 'content="joomla'), "cms"),
    TechnologySignature("Drupal", ("drupal-settings-json", "/sites/default/files/", 'content="drupal'), "cms"),
    TechnologySignature("PrestaShop", ("/modules/ps_", "prestashop.com", 'content="prestashop'), "cms"),
    TechnologySignature("Next.js", ("/_next/", "__next_data__"), "framework", modern=True),
    TechnologySignature("Nuxt", ("/_nuxt/", "__nuxt"), "framework", modern=True),
    TechnologySignature("Gatsby", ("___gatsby",), "framework", modern=True),
    TechnologySignature("Astro", ("astro-island", "/_astro/"), "framework", modern=True),
    TechnologySignature("React", ("data-reactroot", "react-dom.production"), "framework", modern=True),
    TechnologySignature("Vue.js", ("vue.runtime", "vue.global", "data-v-app"), "framework", modern=True),
    TechnologySignature("Angular", ("ng-version=",), "framework", modern=True),
    TechnologySignature("Tailwind CSS", ("tailwindcss",), "css", modern=True),
    TechnologySignature("Bootstrap", ("bootstrap.min.css", "bootstrap.css", "bootstrap.bundle", "bootstrap.min.js", "/bootstrap/"), "css"),
    TechnologySignature("Font Awesome", ("font-awesome", "fontawesome"), "icons"),
)
# Only core files are versioned with the WordPress release, bundled libraries carry their own numbers
WORDPRESS_VERSION_PATTERNS = (
    re.compile(r"wordpress\s+(\d+\.\d+(?:\.\d+)?)"),
    re.compile(r"/wp-includes/css/dist/block-library/style(?:\.min)?\.css\?ver=(\d+\.\d+(?:\.\d+)?)"),
    re.compile(r"wp-emoji-release\.min\.js\?ver=(\d+\.\d+(?:\.\d+)?)"),
    re.compile(r"/wp-includes/js/(?:wp-embed|comment-reply)(?:\.min)?\.js\?ver=(\d+\.\d+(?:\.\d+)?)"),
)
# Desktop or budget builders whose sites typically look dated
LOW_END_BUILDERS = {"WebSite X5", "Solocal (PagesJaunes)", "SiteW", "Webself", "SimpleSite", "GoDaddy", "e-monsite", "Jimdo", "Webnode", "SITE123"}
BOOTSTRAP_VERSION_PATTERN = re.compile(r"bootstrap(?:\.min)?\.(?:css|js)\?ver=(\d+)\.|bootstrap[/@-](\d+)\.\d+|bootstrap v(\d+)\.")
FONT_AWESOME_VERSION_PATTERN = re.compile(r"font-?awesome[/@-](\d+)\.|font-awesome/(\d+)\.")
MINIMUM_CURRENT_WORDPRESS_MAJOR = 6


@dataclass
class TechnologyReport:
    """Technologies found on a site, with the outdated ones."""
    names: list[str]
    consumer_builder: str | None
    modern_names: list[str]
    outdated: list[str]
    wordpress_version: str | None


def first_group(match: re.Match | None) -> str | None:
    """Return the first non empty group of a regex match."""
    if match is None:
        return None
    return next((group for group in match.groups() if group), None)


def detect_technologies(html_lower: str, generator: str | None) -> TechnologyReport:
    """Detect the CMS, builders, frameworks and libraries of a page."""
    haystack = f"{html_lower} {(generator or '').lower()}"
    detected_signatures = [signature for signature in TECHNOLOGY_SIGNATURES if any(pattern in haystack for pattern in signature.patterns)]
    if any(signature.kind == "builder" for signature in detected_signatures):
        # Hosted builders ship their own scripts: framework and plugin markers inside them describe the builder, not the site
        detected_signatures = [signature for signature in detected_signatures if signature.kind in ("builder", "icons")]
    outdated: list[str] = []
    wordpress_version = None
    if any(signature.name == "WordPress" for signature in detected_signatures):
        wordpress_version = next((first_group(pattern.search(haystack)) for pattern in WORDPRESS_VERSION_PATTERNS if pattern.search(haystack)), None)
        if wordpress_version and int(wordpress_version.split(".")[0]) < MINIMUM_CURRENT_WORDPRESS_MAJOR:
            outdated.append(f"WordPress {wordpress_version}")
    bootstrap_major = first_group(BOOTSTRAP_VERSION_PATTERN.search(haystack))
    if bootstrap_major and int(bootstrap_major) <= 3:
        outdated.append(f"Bootstrap {bootstrap_major}")
    font_awesome_major = first_group(FONT_AWESOME_VERSION_PATTERN.search(haystack))
    if font_awesome_major and int(font_awesome_major) <= 4:
        outdated.append(f"Font Awesome {font_awesome_major}")
    names = [signature.name + (f" {wordpress_version}" if signature.name == "WordPress" and wordpress_version else "") for signature in detected_signatures]
    return TechnologyReport(
        names=names,
        consumer_builder=next((signature.name for signature in detected_signatures if signature.consumer_builder), None),
        modern_names=[signature.name for signature in detected_signatures if signature.modern],
        outdated=outdated,
        wordpress_version=wordpress_version,
    )
