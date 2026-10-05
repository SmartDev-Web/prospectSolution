"""Recognition of map places that are not prospects, and of the sector designated by a Google Maps category."""
import re

from app.sectors import SECTORS, Sector
from app.text_utils import strip_accents

# Google Maps categories of places that are equipment, public services or landmarks rather than businesses to call
NON_BUSINESS_CATEGORY_PHRASES = (
    "borne de recharge", "station de recharge", "recharge pour vehicules electriques", "recharge de vehicules electriques",
    "chargeur de vehicule electrique", "electric vehicle charging", "charging station",
    "distributeur automatique de billets", "distributeur de billets", "guichet automatique", "atm",
    "parking", "parc de stationnement", "aire de stationnement", "station de taxis", "station de taxi", "arret de bus",
    "station de bus", "gare routiere", "gare", "station de metro", "station de tramway", "arret de tramway", "aeroport",
    "boite aux lettres", "toilettes publiques", "point d eau", "fontaine", "aire de jeux", "aire de pique nique",
    "aire de repos", "parc", "jardin public", "square", "monument", "monument historique", "statue", "memorial",
    "eglise", "cathedrale", "chapelle", "mosquee", "synagogue", "temple", "cimetiere",
    "mairie", "hotel de ville", "prefecture", "tribunal", "commissariat", "gendarmerie", "caserne de pompiers",
    "bureau de poste", "ecole primaire", "ecole maternelle", "ecole elementaire", "college", "lycee", "universite",
    "bibliotheque", "mediatheque", "piscine municipale", "stade", "gymnase", "complexe sportif",
    "point de collecte", "conteneur", "dechetterie", "centre de recyclage", "relais colis", "point relais", "consigne automatique",
    "station de lavage automatique", "aspirateur", "station de gonflage", "pont", "rond point", "quartier", "zone industrielle",
    "zone d activites", "lotissement", "residence", "immeuble", "logement social", "batiment",
)
# Names of public charging networks and generic equipment names, recognised whatever the data source
NON_BUSINESS_NAME_PHRASES = (
    "borne de recharge", "bornes de recharge", "station de recharge", "recharge vehicule electrique", "recharge vehicules electriques",
    "irve", "supercharger", "tesla supercharger", "ionity", "freshmile", "izivia", "powerdot", "fastned", "allego", "zunder",
    "electra recharge", "totalenergies recharge", "engie vianeo", "e totem", "chargepoint", "wattpark", "reveo",
    "distributeur de billets", "parking", "toilettes publiques",
)
# Category wordings that name a sector without using its search query
ADDITIONAL_CATEGORY_KEYWORDS = {
    "restaurant": (
        "restaurant", "restauration", "pizzeria", "pizza", "brasserie", "bistrot", "bistro", "creperie", "kebab", "sushi",
        "burger", "trattoria", "snack", "tacos", "fast food", "friterie", "rotisserie", "grill", "steakhouse", "poke", "ramen", "food truck",
    ),
    "bar_cafe": ("bar", "bar a vin", "bar a cocktails", "pub", "cafe", "salon de the", "coffee shop", "brasserie artisanale"),
    "bakery": ("boulangerie", "patisserie", "chocolaterie", "confiserie", "viennoiserie"),
    "butcher": ("boucherie", "charcuterie", "volailler", "triperie"),
    "grocery": ("epicerie", "primeur", "fromagerie", "caviste", "magasin de vins", "poissonnerie", "magasin bio", "supermarche", "superette", "alimentation"),
    "caterer": ("traiteur",),
    "florist": ("fleuriste", "magasin de fleurs", "artisan fleuriste"),
    "transport": ("taxi", "service de taxi", "vtc", "chauffeur", "demenageur", "demenagement", "transporteur", "transport routier", "coursier", "ambulance"),
    "hairdresser": ("coiffeur", "salon de coiffure", "barbier", "institut de beaute", "estheticienne", "onglerie", "manucure"),
    "electrician": ("electricien", "entreprise d electricite", "electricite generale"),
    "plumber": ("plombier", "chauffagiste", "climatisation", "pompe a chaleur"),
    "car_repair": ("garage automobile", "mecanique automobile", "reparation automobile", "atelier de reparation automobile", "garage moto"),
    "real_estate": ("agence immobiliere", "immobilier"),
    "fitness": ("salle de sport", "salle de fitness", "centre de fitness", "crossfit", "coach sportif", "yoga", "pilates"),
}


def normalize_category_text(text: str | None) -> str:
    """Lowercase, remove accents and punctuation so that phrases match on whole words."""
    return " ".join(re.split(r"[^a-z0-9]+", strip_accents(text or "").lower())).strip()


def contains_phrase(normalized_text: str, phrase: str) -> bool:
    """Tell whether a normalized phrase appears as whole words in a normalized text."""
    return bool(phrase) and f" {phrase} " in f" {normalized_text} "


NORMALIZED_NON_BUSINESS_CATEGORIES = tuple(normalize_category_text(phrase) for phrase in NON_BUSINESS_CATEGORY_PHRASES)
NORMALIZED_NON_BUSINESS_NAMES = tuple(normalize_category_text(phrase) for phrase in NON_BUSINESS_NAME_PHRASES)


def build_category_keywords() -> list[tuple[str, Sector]]:
    """Index every keyword that designates a sector in a Google Maps category, longest first."""
    keyword_index: dict[str, Sector] = {}
    for sector in SECTORS:
        for keyword in (*ADDITIONAL_CATEGORY_KEYWORDS.get(sector.key, ()), *sector.google_maps_queries):
            normalized_keyword = normalize_category_text(keyword)
            if normalized_keyword and normalized_keyword not in keyword_index:
                keyword_index[normalized_keyword] = sector
    return sorted(keyword_index.items(), key=lambda keyword_entry: -len(keyword_entry[0]))


CATEGORY_KEYWORDS = build_category_keywords()


def find_non_business_reason(names: list[str], category_label: str | None) -> str | None:
    """Return why a place is not a business worth calling (charging station, parking…), or None."""
    normalized_category = normalize_category_text(category_label)
    for category_phrase in NORMALIZED_NON_BUSINESS_CATEGORIES:
        # Single words ("parc", "gare") only match a whole category, so that "Parc d'attractions" stays a business
        phrase_is_specific = " " in category_phrase
        if normalized_category == category_phrase or (phrase_is_specific and normalized_category.startswith(f"{category_phrase} ")):
            return f"lieu hors cible « {category_label} »"
    for name in names:
        normalized_name = normalize_category_text(name)
        matched_phrase = next((name_phrase for name_phrase in NORMALIZED_NON_BUSINESS_NAMES if contains_phrase(normalized_name, name_phrase)), None)
        if matched_phrase:
            return f"équipement « {name} »"
    return None


def find_sector_by_category(category_label: str | None) -> Sector | None:
    """Return the sector named by a Google Maps category, preferring the keyword that appears first."""
    normalized_category = normalize_category_text(category_label)
    if not normalized_category:
        return None
    padded_category = f" {normalized_category} "
    matches = [(padded_category.find(f" {keyword} "), -len(keyword), sector) for keyword, sector in CATEGORY_KEYWORDS if f" {keyword} " in padded_category]
    return min(matches, key=lambda match: (match[0], match[1]))[2] if matches else None
