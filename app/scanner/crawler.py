"""Fetch the few internal pages that matter for an audit: contact, legal notice, menu, prices, booking."""
import asyncio
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.text_utils import extract_domain, strip_accents
from app.web_safety import create_public_web_client, fetch_page_text

# Ordered by usefulness: the first matching links are crawled first
PAGE_KEYWORDS = (
    ("contact", ("contact", "nous-joindre", "nous-contacter", "coordonnees")),
    ("legal", ("mentions", "legal", "informations-legales", "cgu")),
    ("booking", ("reserv", "booking", "rendez-vous", "rdv", "prendre-rendez")),
    ("menu", ("carte", "menu", "nos-plats", "formules")),
    ("prices", ("tarif", "prix", "prestations", "services")),
    ("quote", ("devis", "demande")),
    ("about", ("a-propos", "qui-sommes-nous", "notre-histoire", "entreprise", "about")),
    ("access", ("acces", "plan", "nous-trouver", "infos-pratiques")),
)
SKIPPED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip", ".doc", ".docx", ".mp4")


@dataclass
class CrawledPage:
    """An internal page fetched during an audit."""
    url: str
    page_type: str
    html: str


def select_internal_links(home_url: str, home_html: str, limit: int) -> list[tuple[str, str]]:
    """Pick the most useful internal links of the homepage, at most one per page type."""
    home_host = extract_domain(home_url)
    anchors = BeautifulSoup(home_html or "", "lxml").find_all("a")
    selected_links: list[tuple[str, str]] = []
    selected_urls: set[str] = set()
    for page_type, keywords in PAGE_KEYWORDS:
        for anchor in anchors:
            raw_target = (anchor.get("href") or "").strip()
            if not raw_target or raw_target.lower().startswith(("mailto:", "tel:", "javascript:")) or "@" in raw_target:
                continue
            link_target = urljoin(home_url, raw_target.split("#")[0])
            parsed_target = urlparse(link_target)
            if parsed_target.scheme not in ("http", "https") or extract_domain(link_target) != home_host:
                continue
            if parsed_target.path.lower().endswith(SKIPPED_EXTENSIONS) or link_target.rstrip("/") == home_url.rstrip("/") or link_target in selected_urls:
                continue
            link_haystack = strip_accents(f"{parsed_target.path} {anchor.get_text(' ', strip=True)}").lower().replace(" ", "-")
            if any(keyword in link_haystack for keyword in keywords):
                selected_links.append((link_target, page_type))
                selected_urls.add(link_target)
                break
        if len(selected_links) >= limit:
            break
    return selected_links


async def crawl_internal_pages(home_url: str, home_html: str, limit: int) -> list[CrawledPage]:
    """Fetch the selected internal pages concurrently, ignoring the ones that fail."""
    selected_links = select_internal_links(home_url, home_html, limit)
    if not selected_links:
        return []
    async with create_public_web_client(15.0, verify_certificates=False) as client:
        async def fetch(link_target: str, page_type: str) -> CrawledPage | None:
            try:
                fetched_page = await fetch_page_text(client, link_target)
            except (httpx.HTTPError, httpx.InvalidURL, UnicodeError, ValueError):
                return None
            if fetched_page.status_code >= 400 or "html" not in fetched_page.content_type:
                return None
            return CrawledPage(url=fetched_page.url, page_type=page_type, html=fetched_page.text)
        crawled_pages = await asyncio.gather(*(fetch(link_target, page_type) for link_target, page_type in selected_links))
    return [crawled_page for crawled_page in crawled_pages if crawled_page]
