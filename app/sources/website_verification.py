"""Evidence based verification that a web page is the official website of a given business."""
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.text_utils import extract_domain, strip_accents, tokenize_company_name

# Activity words shared by thousands of businesses: they never identify one on their own
GENERIC_NAME_WORDS = {
    "le", "la", "les", "l", "de", "du", "des", "d", "et", "a", "au", "aux", "en", "chez", "the", "o", "s", "sur",
    "restaurant", "resto", "pizzeria", "pizza", "pizzas", "boulangerie", "patisserie", "boucherie", "charcuterie",
    "epicerie", "bar", "cafe", "brasserie", "bistrot", "bistro", "snack", "traiteur", "coiffure", "coiffeur", "salon",
    "institut", "beaute", "barbier", "garage", "maison", "atelier", "cuisine", "food", "burger", "burgers", "sushi",
    "kebab", "tacos", "grill", "cave", "vins", "fromagerie", "primeur", "marche", "comptoir", "table", "street",
    "shop", "store", "boutique", "magasin", "services", "service", "france", "sud", "groupe", "group", "holding",
    "international", "industrie", "industries", "mecanique", "precision", "fabrication", "usinage", "technologies",
    "telephone", "telephonie", "reparation", "mobile", "smartphone", "vape", "cigarette", "electronique", "montpellier",
}
DIRECTORY_DOMAINS = (
    "pagesjaunes.fr", "societe.com", "pappers.fr", "infogreffe.fr", "verif.com", "manageo.fr", "annuaire-entreprises.data.gouv.fr",
    "tripadvisor", "thefork.", "lafourchette.com", "ubereats.com", "deliveroo.", "google.", "yelp.", "mappy.com", "justacote.com",
    "petitfute.com", "linkedin.com", "wikipedia.org", "planity.com", "treatwell.fr", "kompass.com", "europages", "doctolib.fr",
    "118712.fr", "118000.fr", "bing.com", "duckduckgo.com", "youtube.com", "tiktok.com", "x.com", "twitter.com", "waze.com",
    "restaurantguru", "sortiraparis", "corporama.com", "b-reputation.com", "hoodspot.fr", "cylex", "horaires.lefigaro.fr",
    "pagespro.com", "lexpress.fr", "entreprises.lefigaro.fr", "score3.fr", "infonet.fr", "annuaire.", "facebook.com",
    "instagram.com", "pinterest.", "zenchef.com", "zenchef.", "covermanager", "privateaser", "just-eat", "justeat",
    "infobel", "lesbonnesadresses", "frenchweb", "bilansgratuits", "entreprises.lesechos.fr", "societeinfo", "firmania",
    "118218", "mapstr", "wanderlog", "foursquare", "apple.com", "uber.com", "linternaute.com", "michelin.", "gaultmillau",
    "ouest-france", "midilibre", "lagazettedemontpellier", "actu.fr", "francebleu", "leboncoin", "indeed", "welcometothejungle",
)
PARKED_PAGE_MARKERS = (
    "domain is for sale", "ce domaine est a vendre", "this domain is parked", "domaine en vente", "buy this domain",
    "parkingcrew", "domain parking", "nom de domaine est disponible", "site en cours de construction", "this domain may be for sale",
    "default web site page", "it works!", "index of /", "account suspended", "compte suspendu", "domaine reserve",
    "ce nom de domaine a ete reserve", "this site can't be reached", "future home of something quite cool",
)
LOCATION_SUBPAGE_KEYWORDS = ("contact", "mentions", "legal", "acces", "nous-trouver", "plan", "coordonnees", "infos-pratiques", "a-propos")
# A postal code is followed by a town name, which tells it apart from amounts or quantities
POSTAL_CODE_PATTERN = re.compile(r"\b(\d{5})\s+(?!euros?\b|eur\b|habitants\b|clients\b|visiteurs\b|personnes\b|km\b|m2\b|exemplaires\b|produits\b)[a-z][a-z'\-]{2,}")
HIGH_CONFIDENCE_SCORE = 8
MEDIUM_CONFIDENCE_SCORE = 5


@dataclass
class BusinessIdentity:
    """What we know about a business to recognise its website."""
    name: str
    alternative_names: list[str] = field(default_factory=list)
    city: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    siren: str | None = None
    street: str | None = None
    rejected_domains: set[str] = field(default_factory=set)

    def all_names(self) -> list[str]:
        return [name for name in (self.name, *self.alternative_names) if name]

    def distinctive_tokens(self) -> set[str]:
        """Return the name words able to identify this business, ignoring generic activity words."""
        all_tokens = {token for name in self.all_names() for token in tokenize_company_name(name) if len(token) >= 3}
        distinctive_tokens = {token for token in all_tokens if token not in GENERIC_NAME_WORDS}
        return distinctive_tokens or all_tokens


@dataclass
class PageEvidence:
    """Facts linking a page to a business, with the resulting confidence."""
    score: float = 0.0
    name_matched: bool = False
    found_by_search: bool = False
    identifier_matched: bool = False
    exact_location_matched: bool = False
    department_matched: bool = False
    location_conflict: bool = False
    full_name_in_domain: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> str | None:
        """High needs an identifier or the exact address; an address elsewhere in France disqualifies the page."""
        if not self.name_matched or (self.location_conflict and not self.identifier_matched):
            return None
        if self.score >= HIGH_CONFIDENCE_SCORE and (self.identifier_matched or self.exact_location_matched):
            return "high"
        if self.score >= MEDIUM_CONFIDENCE_SCORE and (self.identifier_matched or self.exact_location_matched or self.department_matched or self.found_by_search):
            return "medium"
        return None

    def add(self, points: float, reason: str) -> None:
        self.score += points
        self.reasons.append(reason)


@dataclass
class ParsedPage:
    """Normalized views of a fetched page."""
    url: str
    title_plain: str
    text_plain: str
    digits: str
    link_targets: list[str]


def parse_page(url: str, page_html: str) -> ParsedPage:
    """Extract the normalized title, visible text and links of a page."""
    soup = BeautifulSoup(page_html or "", "lxml")
    link_targets = [
        urljoin(url, anchor.get("href").strip())
        for anchor in soup.find_all("a")
        if anchor.get("href") and not anchor.get("href").strip().lower().startswith(("mailto:", "tel:", "javascript:", "#"))
    ]
    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    for invisible_element in soup(["script", "style", "noscript", "template"]):
        invisible_element.extract()
    text_plain = strip_accents(soup.get_text(" ", strip=True)).lower()
    return ParsedPage(url=url, title_plain=strip_accents(title_text).lower(), text_plain=text_plain, digits=re.sub(r"\D", "", text_plain), link_targets=link_targets)


def is_directory_url(url: str) -> bool:
    """Tell whether a URL belongs to a directory, a platform or a social network rather than the business itself."""
    host_name = extract_domain(url) or ""
    return any(directory_domain in host_name for directory_domain in DIRECTORY_DOMAINS)


def is_parked_page(parsed_page: ParsedPage) -> bool:
    """Detect parking, default hosting and suspended pages."""
    return len(parsed_page.text_plain) < 4000 and any(marker in parsed_page.text_plain for marker in PARKED_PAGE_MARKERS)


def domain_label(url: str) -> str:
    """Return the domain without its extension and separators, for example 'ledukestreetcantine'."""
    host_name = extract_domain(url) or ""
    registrable_part = host_name.rsplit(".", 1)[0] if "." in host_name else host_name
    return re.sub(r"[^a-z0-9]", "", registrable_part.split(".")[-1])


def collect_name_evidence(parsed_page: ParsedPage, identity: BusinessIdentity, evidence: PageEvidence) -> None:
    """Score how strongly the page and its domain carry the business name."""
    distinctive_tokens = identity.distinctive_tokens()
    if not distinctive_tokens:
        return
    label = domain_label(parsed_page.url)
    multi_word_names = [tokenize_company_name(name) for name in identity.all_names()]
    joined_names = {"".join(name_tokens) for name_tokens in multi_word_names if len(name_tokens) >= 2}
    if any(len(joined_name) >= 5 and joined_name in label for joined_name in joined_names):
        evidence.add(4, "nom complet dans le nom de domaine")
        evidence.name_matched = True
        evidence.full_name_in_domain = True
    elif any(len(token) >= 4 and token in label for token in distinctive_tokens):
        evidence.add(3, "nom dans le nom de domaine")
        evidence.name_matched = True
    best_fraction, best_matched_tokens = 0.0, []
    for name in identity.all_names():
        name_tokens = {token for token in tokenize_company_name(name) if token in distinctive_tokens}
        if not name_tokens:
            continue
        matched_tokens = [token for token in name_tokens if re.search(rf"\b{re.escape(token)}", parsed_page.text_plain)]
        if len(matched_tokens) / len(name_tokens) > best_fraction:
            best_fraction, best_matched_tokens = len(matched_tokens) / len(name_tokens), matched_tokens
    if best_fraction >= 0.5:
        evidence.add(3 * best_fraction, f"nom présent dans la page ({', '.join(sorted(best_matched_tokens))})")
        evidence.name_matched = True
    if any(token in parsed_page.title_plain for token in distinctive_tokens):
        evidence.add(1.5, "nom dans le titre de la page")
        evidence.name_matched = True


def collect_location_evidence(parsed_pages: list[ParsedPage], identity: BusinessIdentity, evidence: PageEvidence) -> None:
    """Score identifiers and location details found on the site pages."""
    combined_text = " ".join(parsed_page.text_plain for parsed_page in parsed_pages)
    combined_digits = "".join(parsed_page.digits for parsed_page in parsed_pages)
    if identity.siren and identity.siren in combined_digits:
        evidence.add(8, "SIREN de l'entreprise dans les mentions légales")
        evidence.identifier_matched = True
    phone_digits = re.sub(r"\D", "", identity.phone or "")
    if len(phone_digits) >= 9 and phone_digits[-9:] in combined_digits:
        evidence.add(5, "même numéro de téléphone")
        evidence.identifier_matched = True
    location_points = 0.0
    if identity.postal_code and identity.postal_code in combined_text:
        location_points += 3
        evidence.reasons.append(f"code postal {identity.postal_code}")
    city_plain = strip_accents(identity.city or "").lower()
    if city_plain and city_plain in combined_text:
        location_points += 2
        evidence.reasons.append(f"ville {identity.city}")
    street_plain = strip_accents(identity.street or "").lower()
    if len(street_plain) >= 6 and street_plain in combined_text:
        location_points += 2
        evidence.reasons.append("même rue")
    evidence.exact_location_matched = location_points > 0
    page_postal_codes = POSTAL_CODE_PATTERN.findall(combined_text)
    if location_points == 0 and identity.postal_code and page_postal_codes:
        department_prefix = identity.postal_code[:2]
        if any(postal_code.startswith(department_prefix) for postal_code in page_postal_codes):
            location_points = 1
            evidence.department_matched = True
            evidence.reasons.append(f"même département ({department_prefix})")
        elif any(postal_code[:2].isdigit() and 1 <= int(postal_code[:2]) <= 98 for postal_code in page_postal_codes):
            evidence.location_conflict = True
            evidence.reasons.append("adresse dans un autre département")
    evidence.score += min(location_points, 5)


def find_location_subpages(parsed_page: ParsedPage, limit: int = 2) -> list[str]:
    """Return the internal contact or legal pages most likely to show the address and identifiers."""
    home_host = extract_domain(parsed_page.url)
    subpage_urls: list[str] = []
    for link_target in parsed_page.link_targets:
        lowered_target = strip_accents(link_target).lower()
        if extract_domain(link_target) != home_host or link_target.rstrip("/") == parsed_page.url.rstrip("/"):
            continue
        if any(keyword in lowered_target for keyword in LOCATION_SUBPAGE_KEYWORDS) and link_target not in subpage_urls:
            subpage_urls.append(link_target.split("#")[0])
    return subpage_urls[:limit]


def evaluate_pages(home_page: ParsedPage, subpages: list[ParsedPage], identity: BusinessIdentity, found_by_search: bool) -> PageEvidence:
    """Combine the evidence of a homepage and its subpages."""
    evidence = PageEvidence()
    if is_parked_page(home_page) or is_directory_url(home_page.url):
        return evidence
    if found_by_search:
        evidence.add(1, "proposé par le moteur de recherche pour ce nom et cette ville")
        evidence.found_by_search = True
    collect_name_evidence(home_page, identity, evidence)
    collect_location_evidence([home_page, *subpages], identity, evidence)
    return evidence


def website_root(url: str) -> str:
    """Return the homepage URL of a site."""
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}/"
