"""Target business sectors and everything each data source needs to find them."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureExpectation:
    """A feature customers of a sector expect to find on a website."""
    code: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class Sector:
    """Definition of a business sector across every prospecting source."""
    key: str
    label: str
    group: str
    naf_codes: tuple[str, ...] = ()
    naf_sections: tuple[str, ...] = ()
    osm_tags: tuple[tuple[str, str], ...] = ()
    google_maps_queries: tuple[str, ...] = ()
    is_local_storefront: bool = True
    expected_features: tuple[FeatureExpectation, ...] = ()
    discovery_questions: tuple[str, ...] = ()
    sector_recommendations: tuple[str, ...] = ()
    pitch_angle: str = ""


ONLINE_BOOKING = FeatureExpectation("missing_online_booking", ("réserver", "réservation", "book a table", "thefork", "lafourchette", "zenchef", "guestonline", "sevenrooms"))
ONLINE_MENU = FeatureExpectation("missing_menu", ("notre carte", "la carte", "nos menus", "le menu", "menu du jour", "nos plats", "formule", "nos pizzas", "nos burgers"))
CLICK_AND_COLLECT = FeatureExpectation("missing_online_ordering", ("click & collect", "click and collect", "click&collect", "retrait en boutique", "commander", "commande en ligne", "ubereats", "deliveroo", "livraison", "panier"))
APPOINTMENT_BOOKING = FeatureExpectation("missing_appointment_booking", ("rendez-vous", "rendez vous", "rdv", "planity", "treatwell", "kiute", "booksy", "prendre rdv"))
PRICE_LIST = FeatureExpectation("missing_price_list", ("tarif", "prix", "€"))
QUOTE_REQUEST = FeatureExpectation("missing_quote_request", ("devis", "demande de prix", "cahier des charges", "request a quote", "quotation"))
ENGLISH_VERSION = FeatureExpectation("missing_english_version", ("english", "/en/", "hreflang=\"en", "lang=en", "version anglaise"))
CERTIFICATIONS = FeatureExpectation("missing_credentials", ("iso 9001", "iso 14001", "en 9100", "certifié", "certification", "nos références", "nos clients", "ils nous font confiance"))
OPENING_HOURS = FeatureExpectation("missing_opening_hours", ("horaire", "ouvert", "lundi", "mardi", "fermé", "heures d'ouverture"))

FOOD_DISCOVERY_QUESTIONS = (
    "Aujourd'hui, vos clients vous trouvent plutôt par le bouche-à-oreille, Google Maps ou votre site ?",
    "Vous recevez des commandes ou des demandes par téléphone qui pourraient se faire en ligne ?",
    "Les périodes de fêtes, vous gérez comment les commandes spéciales ?",
)
SECTORS: tuple[Sector, ...] = (
    Sector(
        key="restaurant",
        label="Restaurants",
        group="Métiers de bouche",
        naf_codes=("56.10A", "56.10B", "56.10C"),
        osm_tags=(("amenity", "restaurant"), ("amenity", "fast_food")),
        google_maps_queries=("restaurant",),
        expected_features=(ONLINE_MENU, ONLINE_BOOKING, OPENING_HOURS),
        discovery_questions=(
            "Vos réservations arrivent surtout par téléphone, en ligne, ou les clients viennent directement ?",
            "Vous changez souvent votre carte ? Vous la mettez à jour comment sur Internet ?",
            "Les plateformes comme TheFork ou UberEats vous prennent quelle commission aujourd'hui ?",
        ),
        sector_recommendations=(
            "Afficher la carte et les formules en texte lisible sur mobile (pas un PDF ni une photo floue).",
            "Intégrer la réservation en ligne directement sur le site pour éviter les commissions des plateformes.",
            "Mettre en avant les photos des plats et de la salle dès la page d'accueil.",
            "Synchroniser les horaires et les jours de fermeture avec la fiche Google Business.",
        ),
        pitch_angle="remplir les tables en semaine et réduire la dépendance aux plateformes",
    ),
    Sector(
        key="bar_cafe",
        label="Bars et cafés",
        group="Métiers de bouche",
        naf_codes=("56.30Z",),
        osm_tags=(("amenity", "bar"), ("amenity", "cafe"), ("amenity", "pub")),
        google_maps_queries=("bar", "café"),
        expected_features=(OPENING_HOURS, ONLINE_MENU),
        discovery_questions=(
            "Vous organisez des soirées ou des événements ? Comment vous les faites connaître ?",
            "Vous privatisez l'établissement pour des groupes ?",
        ),
        sector_recommendations=(
            "Créer une page événements facile à mettre à jour.",
            "Proposer un formulaire de privatisation pour les groupes et les entreprises.",
        ),
        pitch_angle="faire venir du monde aux soirées et vendre des privatisations",
    ),
    Sector(
        key="bakery",
        label="Boulangeries et pâtisseries",
        group="Métiers de bouche",
        naf_codes=("10.71C", "10.71D", "47.24Z"),
        osm_tags=(("shop", "bakery"), ("shop", "pastry"), ("shop", "confectionery")),
        google_maps_queries=("boulangerie", "pâtisserie"),
        expected_features=(OPENING_HOURS, CLICK_AND_COLLECT),
        discovery_questions=FOOD_DISCOVERY_QUESTIONS,
        sector_recommendations=(
            "Permettre la précommande des gâteaux et pièces montées en ligne.",
            "Présenter les créations en photo, mises à jour facilement.",
            "Afficher clairement horaires et jours de fermeture.",
        ),
        pitch_angle="vendre plus de commandes spéciales (gâteaux, fêtes, entreprises)",
    ),
    Sector(
        key="butcher",
        label="Boucheries et charcuteries",
        group="Métiers de bouche",
        naf_codes=("47.22Z", "10.13B"),
        osm_tags=(("shop", "butcher"), ("shop", "deli")),
        google_maps_queries=("boucherie", "charcuterie"),
        expected_features=(OPENING_HOURS, CLICK_AND_COLLECT),
        discovery_questions=FOOD_DISCOVERY_QUESTIONS,
        sector_recommendations=(
            "Mettre en place le click & collect (colis viande, plateaux, commandes de fêtes).",
            "Valoriser l'origine des viandes et les éleveurs partenaires : c'est votre argument face aux grandes surfaces.",
            "Afficher les produits du moment et les promotions.",
        ),
        pitch_angle="prendre les commandes de fêtes et de barbecue en ligne sans bloquer le téléphone",
    ),
    Sector(
        key="grocery",
        label="Épiceries, primeurs, cavistes, fromageries",
        group="Métiers de bouche",
        naf_codes=("47.11B", "47.11C", "47.21Z", "47.23Z", "47.25Z", "47.29Z"),
        osm_tags=(("shop", "convenience"), ("shop", "greengrocer"), ("shop", "seafood"), ("shop", "wine"), ("shop", "cheese"), ("shop", "health_food"), ("shop", "farm")),
        google_maps_queries=("épicerie", "épicerie fine", "caviste", "fromagerie", "primeur"),
        expected_features=(OPENING_HOURS, CLICK_AND_COLLECT),
        discovery_questions=FOOD_DISCOVERY_QUESTIONS,
        sector_recommendations=(
            "Proposer des paniers ou coffrets commandables en ligne.",
            "Présenter les producteurs et les nouveautés de la semaine.",
        ),
        pitch_angle="vendre des paniers et coffrets cadeaux en ligne",
    ),
    Sector(
        key="caterer",
        label="Traiteurs",
        group="Métiers de bouche",
        naf_codes=("56.21Z",),
        osm_tags=(("craft", "caterer"),),
        google_maps_queries=("traiteur",),
        expected_features=(QUOTE_REQUEST, PRICE_LIST),
        discovery_questions=(
            "Vos clients sont plutôt des particuliers ou des entreprises ?",
            "Une demande de devis, vous la recevez comment aujourd'hui ?",
        ),
        sector_recommendations=(
            "Ajouter un formulaire de demande de devis (date, nombre de convives, budget).",
            "Publier des menus types avec prix indicatifs par personne.",
        ),
        pitch_angle="recevoir des demandes de devis qualifiées pour les événements",
    ),
    Sector(
        key="industry",
        label="Industrie et fabrication",
        group="Industrie",
        naf_sections=("C",),
        osm_tags=(("man_made", "works"), ("craft", "metal_construction"), ("industrial", "factory")),
        google_maps_queries=("usinage", "chaudronnerie", "mécanique de précision", "fabricant", "entreprise industrielle"),
        is_local_storefront=False,
        expected_features=(QUOTE_REQUEST, CERTIFICATIONS, ENGLISH_VERSION),
        discovery_questions=(
            "Vos nouveaux clients, ils arrivent comment aujourd'hui : réseau, salons, commerciaux ?",
            "Quand un acheteur compare plusieurs sous-traitants, qu'est-ce qu'il regarde en premier selon vous ?",
            "Vous avez du mal à recruter ? Votre site vous aide pour ça ?",
        ),
        sector_recommendations=(
            "Présenter le parc machines, les capacités et les tolérances : c'est ce que cherchent les acheteurs.",
            "Ajouter un formulaire de demande de devis avec envoi de plans (PDF, STEP, DXF).",
            "Mettre en avant les certifications (ISO 9001, EN 9100…) et des références clients.",
            "Proposer une version anglaise pour les donneurs d'ordre étrangers.",
            "Créer une page recrutement attractive pour attirer techniciens et opérateurs.",
        ),
        pitch_angle="rassurer les acheteurs et recevoir des demandes de devis qualifiées",
    ),
    Sector(
        key="phone_shop",
        label="Téléphonie, informatique, réparation",
        group="Commerces locaux",
        naf_codes=("47.42Z", "47.41Z", "95.12Z", "95.11Z"),
        osm_tags=(("shop", "mobile_phone"), ("shop", "computer"), ("shop", "electronics"), ("craft", "electronics_repair")),
        google_maps_queries=("magasin téléphone", "réparation téléphone", "réparation ordinateur"),
        expected_features=(PRICE_LIST, OPENING_HOURS, APPOINTMENT_BOOKING),
        discovery_questions=(
            "On vous appelle souvent juste pour demander le prix d'une réparation d'écran ?",
            "Vous vendez aussi des téléphones reconditionnés ou des accessoires ?",
        ),
        sector_recommendations=(
            "Afficher une grille de tarifs de réparation par modèle : c'est la question numéro un des clients.",
            "Permettre la prise de rendez-vous ou le dépôt en ligne.",
            "Mettre en avant les garanties et les délais de réparation.",
        ),
        pitch_angle="transformer les recherches « réparation écran + ville » en clients au comptoir",
    ),
    Sector(
        key="vape_shop",
        label="Cigarette électronique et tabac",
        group="Commerces locaux",
        naf_codes=("47.26Z",),
        osm_tags=(("shop", "e-cigarette"), ("shop", "tobacco")),
        google_maps_queries=("cigarette électronique", "vape shop"),
        expected_features=(OPENING_HOURS, CLICK_AND_COLLECT),
        discovery_questions=(
            "Vos clients réguliers, ils réservent leurs e-liquides ou ils passent au hasard ?",
            "Vous faites face à la concurrence des sites en ligne ?",
        ),
        sector_recommendations=(
            "Proposer la réservation en ligne avec retrait en boutique.",
            "Présenter les marques et les nouveautés pour être trouvé sur Google.",
        ),
        pitch_angle="récupérer les clients qui commandent sur Internet en leur proposant le retrait en boutique",
    ),
    Sector(
        key="hairdresser",
        label="Coiffeurs, barbiers, instituts de beauté",
        group="Commerces locaux",
        naf_codes=("96.02A", "96.02B"),
        osm_tags=(("shop", "hairdresser"), ("shop", "beauty"), ("shop", "cosmetics")),
        google_maps_queries=("coiffeur", "barbier", "institut de beauté"),
        expected_features=(APPOINTMENT_BOOKING, PRICE_LIST, OPENING_HOURS),
        discovery_questions=(
            "Vos rendez-vous, ils se prennent surtout par téléphone pendant que vous coiffez ?",
            "Vous avez des rendez-vous non honorés ? Ça représente combien par semaine ?",
            "Vous utilisez Planity ou un autre outil ? Ça vous coûte combien par mois ?",
        ),
        sector_recommendations=(
            "Intégrer la prise de rendez-vous en ligne 24 h/24 avec rappel SMS.",
            "Afficher les tarifs et une galerie de réalisations (avant/après).",
            "Relier le compte Instagram au site.",
        ),
        pitch_angle="remplir l'agenda sans décrocher le téléphone pendant les prestations",
    ),
)
SECTORS_BY_KEY = {sector.key: sector for sector in SECTORS}
GENERIC_SECTOR = Sector(
    key="generic",
    label="Entreprise locale",
    group="Autre",
    discovery_questions=(
        "Aujourd'hui, vos nouveaux clients vous trouvent comment ?",
        "Votre site, il vous apporte des demandes ou il est plutôt là « pour exister » ?",
    ),
    sector_recommendations=(
        "Clarifier en une phrase ce que fait l'entreprise dès le haut de la page d'accueil.",
        "Mettre un bouton d'appel et un formulaire de contact visibles sur toutes les pages.",
    ),
    pitch_angle="transformer les visiteurs du site en appels et en demandes de devis",
)


def get_sector(sector_key: str | None) -> Sector:
    """Return a sector definition, falling back to the generic profile."""
    return SECTORS_BY_KEY.get(sector_key or "", GENERIC_SECTOR)


NAF_SECTION_DIVISIONS = {"C": range(10, 34)}


def naf_code_in_sections(naf_code: str | None, naf_sections: tuple[str, ...] | set[str]) -> bool:
    """Tell whether an activity code belongs to one of the given NAF sections."""
    if not naf_code or not naf_code[:2].isdigit():
        return False
    division_number = int(naf_code[:2])
    return any(division_number in NAF_SECTION_DIVISIONS.get(section, ()) for section in naf_sections)


def find_sector_by_naf_code(naf_code: str | None) -> Sector | None:
    """Find the sector whose NAF codes or sections contain the given activity code."""
    if not naf_code:
        return None
    for sector in SECTORS:
        if naf_code in sector.naf_codes or naf_code_in_sections(naf_code, sector.naf_sections):
            return sector
    return None


def find_sector_by_osm_tags(osm_tags: dict[str, str]) -> Sector | None:
    """Find the sector matching an OpenStreetMap element's tags."""
    for sector in SECTORS:
        if any(osm_tags.get(tag_key) == tag_value for tag_key, tag_value in sector.osm_tags):
            return sector
    return None


def serialize_sectors() -> list[dict]:
    """Expose sector definitions to the web interface."""
    return [
        {
            "key": sector.key,
            "label": sector.label,
            "group": sector.group,
            "naf_codes": list(sector.naf_codes),
            "naf_sections": list(sector.naf_sections),
            "google_maps_queries": list(sector.google_maps_queries),
        }
        for sector in SECTORS
    ]
