"""Text normalization helpers used to compare and deduplicate businesses."""
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

LEGAL_FORM_WORDS = {
    "sarl", "sas", "sasu", "eurl", "sa", "sci", "snc", "scop", "selarl", "sca", "ei", "eirl",
    "earl", "gaec", "scea", "scp", "selas", "micro", "entreprise", "ets", "etablissements", "societe", "ste",
}
STOP_WORDS = {"le", "la", "les", "l", "de", "du", "des", "d", "et", "a", "au", "aux", "en", "chez", "the"}
FRENCH_PHONE_PATTERN = re.compile(r"(?:\+33\s?\(?0?\)?\s?|0033\s?|\b0)[1-9](?:[\s.\-]?\d{2}){4}\b")
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
IGNORED_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
IGNORED_EMAIL_DOMAINS = ("example.com", "domain.com", "sentry.io", "wixpress.com", "sentry.wixpress.com")
LOWERCASE_PLACE_WORDS = {"le", "la", "les", "de", "du", "des", "d", "l", "sur", "sous", "en", "et", "aux", "au", "lès", "lez"}


def strip_accents(text: str) -> str:
    """Remove diacritics so that comparisons ignore accents."""
    decomposed_text = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed_text if not unicodedata.combining(character))


def tokenize_company_name(name: str) -> list[str]:
    """Split a business name into meaningful lowercase tokens."""
    plain_text = strip_accents(name or "").lower().replace("&", " et ")
    raw_tokens = re.split(r"[^a-z0-9]+", plain_text)
    return [token for token in raw_tokens if token and token not in LEGAL_FORM_WORDS]


def normalize_company_name(name: str) -> str:
    """Build the canonical form of a business name used for matching."""
    return " ".join(token for token in tokenize_company_name(name) if token not in STOP_WORDS)


def company_name_similarity(first_name: str, second_name: str) -> float:
    """Score how likely two business names designate the same company (0 to 1)."""
    return normalized_name_similarity(normalize_company_name(first_name), normalize_company_name(second_name))


def normalized_name_similarity(first_normalized: str, second_normalized: str, minimum_useful_score: float = 0.0) -> float:
    """Compare two already normalized names; scores that cannot reach the useful minimum are returned as 0 without full computation."""
    if not first_normalized or not second_normalized:
        return 0.0
    if first_normalized == second_normalized:
        return 1.0
    shorter_name, longer_name = sorted((first_normalized, second_normalized), key=len)
    if len(shorter_name) >= 5 and f" {shorter_name} " in f" {longer_name} ":
        return 0.9
    sequence_matcher = SequenceMatcher(None, first_normalized, second_normalized)
    # The quick ratios are upper bounds of the real ratio: most unrelated pairs stop here
    if sequence_matcher.real_quick_ratio() < minimum_useful_score or sequence_matcher.quick_ratio() < minimum_useful_score:
        return 0.0
    return sequence_matcher.ratio()


def format_place_name(place_name: str | None) -> str | None:
    """Format a French municipality name, for example CASTELNAU-LE-LEZ becomes Castelnau-le-Lez."""
    if not place_name:
        return place_name
    words = re.split(r"([\s\-'’])", place_name.strip().lower())
    formatted_words = []
    for word_index, word in enumerate(words):
        is_inner_particle = word_index > 0 and word in LOWERCASE_PLACE_WORDS and word_index < len(words) - 1
        formatted_words.append(word if is_inner_particle else word[:1].upper() + word[1:])
    return "".join(formatted_words)


def extract_street_name(address: str | None) -> str | None:
    """Return the street part of a French address, for example 'rue du faubourg du courreau'."""
    if not address:
        return None
    street_match = re.match(r"^\s*\d+\s*(?:bis|ter|[a-c])?\s*,?\s*(.+?)(?:,|\s+\d{5}\b)", address, re.IGNORECASE)
    return street_match.group(1).strip().lower() if street_match else None


def slugify(text: str, separator: str = "-") -> str:
    """Convert free text to a lowercase ASCII slug."""
    plain_text = strip_accents(text or "").lower()
    return re.sub(r"[^a-z0-9]+", separator, plain_text).strip(separator)


def extract_domain(url: str | None) -> str | None:
    """Return the registrable host of a URL without the www prefix."""
    if not url:
        return None
    parsed_url = urlparse(url if "://" in url else f"http://{url}")
    host_name = (parsed_url.hostname or "").lower()
    if host_name.startswith("www."):
        host_name = host_name[4:]
    return host_name or None


def normalize_website_url(url: str | None) -> str | None:
    """Return a web address with an http or https scheme, or None for anything else (javascript:, file:, mailto:…)."""
    if not url:
        return None
    cleaned_url = url.strip()
    if not cleaned_url:
        return None
    if "://" not in cleaned_url and not cleaned_url.lower().startswith(("javascript:", "data:", "vbscript:", "file:", "mailto:", "tel:")):
        cleaned_url = f"http://{cleaned_url}"
    parsed_url = urlparse(cleaned_url)
    if parsed_url.scheme.lower() not in ("http", "https") or not parsed_url.hostname or any(character.isspace() for character in cleaned_url):
        return None
    return cleaned_url


def normalize_phone_number(phone: str | None) -> str | None:
    """Format a French phone number as 0X XX XX XX XX when possible."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0033"):
        digits = "0" + digits[4:]
    elif digits.startswith("330") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("33") and len(digits) == 11:
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("0"):
        return " ".join(digits[index:index + 2] for index in range(0, 10, 2))
    return phone.strip()


def find_phone_numbers(text: str) -> list[str]:
    """Extract unique French phone numbers from free text."""
    phone_numbers: list[str] = []
    for match in FRENCH_PHONE_PATTERN.finditer(text or ""):
        normalized_phone = normalize_phone_number(match.group(0))
        if normalized_phone and normalized_phone not in phone_numbers:
            phone_numbers.append(normalized_phone)
    return phone_numbers


def find_email_addresses(text: str) -> list[str]:
    """Extract plausible unique email addresses from free text."""
    email_addresses: list[str] = []
    for match in EMAIL_PATTERN.finditer(text or ""):
        email_address = match.group(0).strip(".").lower()
        if email_address.endswith(IGNORED_EMAIL_SUFFIXES):
            continue
        if any(email_address.endswith("@" + ignored_domain) or email_address.endswith("." + ignored_domain) for ignored_domain in IGNORED_EMAIL_DOMAINS):
            continue
        if email_address not in email_addresses:
            email_addresses.append(email_address)
    return email_addresses
