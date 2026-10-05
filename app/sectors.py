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
BASE_SECTORS: tuple[Sector, ...] = (
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
BOOKING_ANY = FeatureExpectation("missing_online_booking", ("réserver", "réservation", "booking", "disponibilités", "book now"))
PORTFOLIO = FeatureExpectation("missing_portfolio", ("réalisations", "nos chantiers", "portfolio", "galerie", "projets", "références", "avant / après", "avant/après"))
CASE_STUDIES = FeatureExpectation("missing_case_studies", ("études de cas", "etude de cas", "case stud", "nos clients", "références", "ils nous font confiance", "portfolio", "projets"))


@dataclass(frozen=True)
class SectorGroupProfile:
    """Sales arguments shared by every sector of a family of trades."""
    expected_features: tuple[FeatureExpectation, ...]
    discovery_questions: tuple[str, ...]
    sector_recommendations: tuple[str, ...]
    pitch_angle: str
    is_local_storefront: bool


GROUP_PROFILES: dict[str, SectorGroupProfile] = {
    "Tech et communication": SectorGroupProfile(
        expected_features=(CASE_STUDIES, QUOTE_REQUEST),
        discovery_questions=(
            "Vos nouveaux clients arrivent surtout par le réseau, LinkedIn ou votre site ?",
            "Votre site génère combien de demandes qualifiées par mois, à peu près ?",
            "Vous avez des études de cas ou des références que vous ne mettez pas assez en avant ?",
        ),
        sector_recommendations=(
            "Créer une page par offre avec un bénéfice client clair et un appel à l'action.",
            "Publier des études de cas chiffrées : c'est ce qui convainc un décideur B2B.",
            "Ajouter une prise de rendez-vous en ligne pour un premier échange de 20 minutes.",
            "Soigner la vitesse et le référencement : un prestataire tech jugé sur son propre site doit être irréprochable.",
        ),
        pitch_angle="générer des demandes B2B qualifiées et crédibiliser votre expertise",
        is_local_storefront=False,
    ),
    "Bâtiment et artisans": SectorGroupProfile(
        expected_features=(QUOTE_REQUEST, PORTFOLIO),
        discovery_questions=(
            "Vos chantiers viennent surtout du bouche-à-oreille ou d'Internet ?",
            "Vous prenez des photos de vos réalisations ? Elles sont visibles quelque part ?",
            "Une demande de devis, vous la recevez comment aujourd'hui ?",
        ),
        sector_recommendations=(
            "Afficher une galerie de réalisations avant / après, classée par type de travaux.",
            "Ajouter un formulaire de devis avec envoi de photos du chantier.",
            "Préciser la zone d'intervention (villes) pour ressortir sur « métier + ville ».",
            "Mettre en avant labels et garanties (RGE, Qualibat, décennale) et les avis clients.",
        ),
        pitch_angle="recevoir des demandes de devis de chantiers dans votre zone d'intervention",
        is_local_storefront=False,
    ),
    "Santé et bien-être": SectorGroupProfile(
        expected_features=(APPOINTMENT_BOOKING, OPENING_HOURS),
        discovery_questions=(
            "Les prises de rendez-vous passent surtout par téléphone ou par Doctolib ?",
            "Le téléphone sonne souvent pendant les consultations ?",
            "Vos patients trouvent facilement vos spécialités et vos tarifs ?",
        ),
        sector_recommendations=(
            "Intégrer la prise de rendez-vous en ligne pour libérer le téléphone.",
            "Présenter clairement spécialités, tarifs, accès et parking.",
            "Rédiger des pages de conseils pour être trouvé sur les recherches santé locales.",
        ),
        pitch_angle="remplir l'agenda et réduire les appels pendant les consultations",
        is_local_storefront=True,
    ),
    "Professions libérales et conseil": SectorGroupProfile(
        expected_features=(APPOINTMENT_BOOKING,),
        discovery_questions=(
            "Vos nouveaux clients viennent surtout de recommandations ou de recherches Google ?",
            "Un prospect qui vous découvre, qu'est-ce qui le convainc de vous appeler plutôt qu'un confrère ?",
        ),
        sector_recommendations=(
            "Détailler chaque domaine d'expertise sur une page dédiée.",
            "Ajouter une prise de rendez-vous ou un formulaire de premier contact.",
            "Présenter l'équipe avec photos : la confiance passe par les visages.",
        ),
        pitch_angle="attirer des clients qui cherchent un expert près de chez eux",
        is_local_storefront=True,
    ),
    "Automobile et mobilité": SectorGroupProfile(
        expected_features=(QUOTE_REQUEST, APPOINTMENT_BOOKING, OPENING_HOURS),
        discovery_questions=(
            "Les clients vous appellent surtout pour un devis ou une prise de rendez-vous ?",
            "Votre planning atelier, il est plein ou il y a des trous dans la semaine ?",
        ),
        sector_recommendations=(
            "Permettre la prise de rendez-vous et la demande de devis en ligne.",
            "Afficher les prestations avec des prix « à partir de ».",
            "Mettre en avant les avis Google et les garanties.",
        ),
        pitch_angle="remplir le planning avec des rendez-vous pris en ligne",
        is_local_storefront=True,
    ),
    "Tourisme, sport et loisirs": SectorGroupProfile(
        expected_features=(BOOKING_ANY, PRICE_LIST),
        discovery_questions=(
            "Quelle part de vos réservations passe par Booking, Airbnb ou d'autres plateformes ?",
            "Ces commissions vous coûtent combien par an, à peu près ?",
        ),
        sector_recommendations=(
            "Proposer la réservation directe sur le site pour économiser les commissions.",
            "Soigner les photos plein écran et les avis : ce sont eux qui déclenchent la réservation.",
            "Publier tarifs, disponibilités et une version anglaise pour les visiteurs étrangers.",
        ),
        pitch_angle="récupérer des réservations en direct, sans commission",
        is_local_storefront=True,
    ),
    "Commerces locaux": SectorGroupProfile(
        expected_features=(OPENING_HOURS,),
        discovery_questions=(
            "Vos clients viennent surtout du quartier ou de plus loin ?",
            "Vous vendez aussi en ligne, ou vous aimeriez le faire ?",
        ),
        sector_recommendations=(
            "Afficher horaires, accès et produits phares dès la page d'accueil.",
            "Proposer la réservation ou le retrait en boutique.",
            "Relier le site au compte Instagram pour montrer les nouveautés.",
        ),
        pitch_angle="faire venir plus de clients en boutique",
        is_local_storefront=True,
    ),
    "Services": SectorGroupProfile(
        expected_features=(QUOTE_REQUEST,),
        discovery_questions=(
            "Vos clients vous trouvent comment aujourd'hui ?",
            "Une demande de devis, elle arrive par téléphone, par mail ou par un formulaire ?",
        ),
        sector_recommendations=(
            "Présenter chaque prestation avec un appel à l'action et un prix indicatif.",
            "Ajouter un formulaire de devis rapide et un bouton d'appel visible.",
            "Préciser la zone d'intervention et afficher les avis clients.",
        ),
        pitch_angle="recevoir plus de demandes de devis sans prospecter",
        is_local_storefront=False,
    ),
}
# Key, label, family, NAF codes, OpenStreetMap tags, Google Maps queries
ADDITIONAL_SECTOR_ROWS: tuple[tuple[str, str, str, tuple[str, ...], tuple[tuple[str, str], ...], tuple[str, ...]], ...] = (
    ("communication_agency", "Agences de communication et marketing", "Tech et communication", ("73.11Z", "73.12Z", "70.21Z"), (("office", "advertising_agency"),), ("agence de communication", "agence marketing", "agence de publicité")),
    ("web_agency", "Agences web et studios digitaux", "Tech et communication", ("62.01Z",), (("office", "it"),), ("agence web", "création site internet")),
    ("software_publisher", "Éditeurs de logiciels", "Tech et communication", ("58.29A", "58.29B", "58.29C", "58.21Z"), (("office", "software"),), ("éditeur de logiciel", "logiciel SaaS")),
    ("it_services", "ESN, conseil et services informatiques", "Tech et communication", ("62.02A", "62.02B", "62.03Z", "62.09Z"), (("office", "it"), ("craft", "computer")), ("société de services informatiques", "infogérance", "maintenance informatique")),
    ("tech_company", "Startups et entreprises tech", "Tech et communication", ("63.11Z", "63.12Z", "72.19Z", "26.20Z", "61.90Z"), (("office", "company"),), ("startup", "entreprise tech", "hébergement web")),
    ("design_studio", "Design, graphisme et photographes", "Tech et communication", ("74.10Z", "74.20Z"), (("craft", "photographer"), ("shop", "photo")), ("graphiste", "photographe", "studio de design")),
    ("events", "Événementiel et organisation de salons", "Tech et communication", ("82.30Z", "90.01Z", "90.02Z"), (("office", "event_management"),), ("agence événementielle", "organisation de mariage")),
    ("printing", "Imprimeries et signalétique", "Tech et communication", ("18.12Z", "18.13Z"), (("shop", "copyshop"), ("craft", "printer")), ("imprimerie", "signalétique enseigne")),
    ("plumber", "Plombiers et chauffagistes", "Bâtiment et artisans", ("43.22A", "43.22B"), (("craft", "plumber"), ("craft", "hvac")), ("plombier", "chauffagiste")),
    ("electrician", "Électriciens", "Bâtiment et artisans", ("43.21A", "43.21B"), (("craft", "electrician"),), ("électricien",)),
    ("mason", "Maçons et gros œuvre", "Bâtiment et artisans", ("43.99C", "41.20A", "41.20B", "43.99A"), (("craft", "builder"), ("craft", "stonemason")), ("maçon", "entreprise de construction")),
    ("carpenter", "Menuisiers et charpentiers", "Bâtiment et artisans", ("43.32A", "43.32B", "16.23Z", "43.91A"), (("craft", "carpenter"), ("craft", "joiner")), ("menuisier", "charpentier")),
    ("painter", "Peintres et plaquistes", "Bâtiment et artisans", ("43.34Z", "43.31Z"), (("craft", "painter"), ("craft", "plasterer")), ("peintre en bâtiment", "plaquiste")),
    ("roofer", "Couvreurs et étanchéité", "Bâtiment et artisans", ("43.91B",), (("craft", "roofer"),), ("couvreur",)),
    ("tiler", "Carreleurs et solutions de sol", "Bâtiment et artisans", ("43.33Z",), (("craft", "tiler"), ("craft", "floorer")), ("carreleur", "parquet")),
    ("pool_builder", "Piscinistes, cuisinistes et aménagement", "Bâtiment et artisans", ("43.29B", "47.59A"), (("shop", "kitchen"), ("shop", "swimming_pool")), ("pisciniste", "cuisiniste", "salle de bain")),
    ("landscaper", "Paysagistes et jardiniers", "Bâtiment et artisans", ("81.30Z",), (("craft", "gardener"), ("shop", "garden_centre")), ("paysagiste", "jardinier")),
    ("locksmith", "Serruriers, vitriers, métalliers", "Bâtiment et artisans", ("43.29A", "25.12Z"), (("craft", "locksmith"), ("shop", "locksmith"), ("craft", "glaziery")), ("serrurier", "vitrier", "métallier")),
    ("dentist", "Dentistes", "Santé et bien-être", ("86.23Z",), (("amenity", "dentist"), ("healthcare", "dentist")), ("dentiste",)),
    ("doctor", "Médecins et centres médicaux", "Santé et bien-être", ("86.21Z", "86.22A", "86.22B", "86.22C"), (("amenity", "doctors"), ("healthcare", "doctor"), ("amenity", "clinic")), ("médecin", "centre médical")),
    ("physiotherapist", "Kinés, ostéopathes, paramédical", "Santé et bien-être", ("86.90E", "86.90F", "86.90D"), (("healthcare", "physiotherapist"), ("healthcare", "alternative")), ("kinésithérapeute", "ostéopathe", "podologue")),
    ("veterinary", "Vétérinaires", "Santé et bien-être", ("75.00Z",), (("amenity", "veterinary"),), ("vétérinaire",)),
    ("pharmacy", "Pharmacies", "Santé et bien-être", ("47.73Z",), (("amenity", "pharmacy"),), ("pharmacie",)),
    ("optician", "Opticiens et audioprothésistes", "Santé et bien-être", ("47.78A", "47.74Z"), (("shop", "optician"), ("shop", "hearing_aids")), ("opticien", "audioprothésiste")),
    ("spa", "Spas, massages et bien-être", "Santé et bien-être", ("96.04Z",), (("leisure", "spa"), ("shop", "massage")), ("spa", "massage bien-être")),
    ("accountant", "Experts-comptables", "Professions libérales et conseil", ("69.20Z",), (("office", "accountant"),), ("expert comptable",)),
    ("lawyer", "Avocats, notaires, huissiers", "Professions libérales et conseil", ("69.10Z",), (("office", "lawyer"), ("office", "notary")), ("avocat", "notaire")),
    ("architect", "Architectes et décorateurs", "Professions libérales et conseil", ("71.11Z",), (("office", "architect"),), ("architecte", "architecte d'intérieur")),
    ("engineering", "Bureaux d'études et géomètres", "Professions libérales et conseil", ("71.12A", "71.12B", "71.20B"), (("office", "engineer"), ("office", "surveyor")), ("bureau d'études", "géomètre")),
    ("real_estate", "Agences immobilières", "Professions libérales et conseil", ("68.31Z", "68.32A"), (("office", "estate_agent"),), ("agence immobilière",)),
    ("insurance", "Courtiers et assurances", "Professions libérales et conseil", ("66.22Z", "66.19B"), (("office", "insurance"), ("office", "financial_advisor")), ("courtier en assurance", "courtier crédit")),
    ("consulting", "Conseil, coaching et formation", "Professions libérales et conseil", ("70.22Z", "85.59A", "85.59B"), (("office", "consulting"), ("office", "educational_institution")), ("cabinet de conseil", "organisme de formation", "coach")),
    ("recruitment", "Recrutement et intérim indépendants", "Professions libérales et conseil", ("78.10Z", "78.20Z"), (("office", "employment_agency"),), ("cabinet de recrutement",)),
    ("car_repair", "Garages et mécanique auto", "Automobile et mobilité", ("45.20A", "45.40Z"), (("shop", "car_repair"), ("shop", "motorcycle_repair")), ("garage automobile", "mécanicien")),
    ("bodywork", "Carrosseries et contrôle technique", "Automobile et mobilité", ("45.20B", "71.20A"), (("craft", "car_body"),), ("carrosserie", "contrôle technique")),
    ("car_dealer", "Concessions et vente de véhicules", "Automobile et mobilité", ("45.11Z", "45.19Z"), (("shop", "car"), ("shop", "motorcycle")), ("concession automobile", "vente voiture occasion")),
    ("driving_school", "Auto-écoles", "Automobile et mobilité", ("85.53Z",), (("amenity", "driving_school"),), ("auto-école",)),
    ("transport", "Taxis, VTC, déménageurs et transporteurs", "Automobile et mobilité", ("49.32Z", "49.42Z", "49.41B", "53.20Z"), (("office", "taxi"), ("office", "moving_company")), ("taxi", "déménageur", "transporteur")),
    ("hotel", "Hôtels et chambres d'hôtes", "Tourisme, sport et loisirs", ("55.10Z", "55.20Z"), (("tourism", "hotel"), ("tourism", "guest_house")), ("hôtel", "chambre d'hôtes")),
    ("camping", "Campings et gîtes", "Tourisme, sport et loisirs", ("55.30Z",), (("tourism", "camp_site"), ("tourism", "chalet")), ("camping", "gîte")),
    ("fitness", "Salles de sport et coachs sportifs", "Tourisme, sport et loisirs", ("93.13Z", "93.12Z", "85.51Z"), (("leisure", "fitness_centre"), ("leisure", "sports_centre")), ("salle de sport", "coach sportif", "crossfit")),
    ("leisure", "Loisirs, escape games, activités", "Tourisme, sport et loisirs", ("93.29Z", "93.21Z", "93.11Z"), (("leisure", "escape_game"), ("leisure", "amusement_arcade"), ("tourism", "attraction")), ("escape game", "activité loisirs", "karting")),
    ("travel_agency", "Agences de voyage", "Tourisme, sport et loisirs", ("79.11Z", "79.12Z"), (("shop", "travel_agency"),), ("agence de voyage",)),
    ("schools", "Écoles de musique, danse, langues", "Tourisme, sport et loisirs", ("85.52Z",), (("amenity", "music_school"), ("amenity", "language_school"), ("leisure", "dance")), ("école de musique", "école de danse", "cours de langues")),
    ("florist", "Fleuristes", "Commerces locaux", ("47.76Z",), (("shop", "florist"),), ("fleuriste",)),
    ("clothing", "Boutiques de vêtements et chaussures", "Commerces locaux", ("47.71Z", "47.72A"), (("shop", "clothes"), ("shop", "shoes"), ("shop", "boutique")), ("boutique vêtements", "magasin de chaussures")),
    ("jewelry", "Bijouteries et horlogeries", "Commerces locaux", ("47.77Z",), (("shop", "jewelry"), ("shop", "watches")), ("bijouterie",)),
    ("bookshop", "Librairies, papeteries, jeux", "Commerces locaux", ("47.61Z", "47.62Z", "47.65Z"), (("shop", "books"), ("shop", "stationery"), ("shop", "toys")), ("librairie", "magasin de jouets")),
    ("pet_shop", "Animaleries et toilettage", "Commerces locaux", ("47.76Z", "96.09Z"), (("shop", "pet"), ("shop", "pet_grooming")), ("animalerie", "toilettage chien")),
    ("furniture", "Meubles, décoration, électroménager", "Commerces locaux", ("47.59B", "47.54Z", "47.53Z"), (("shop", "furniture"), ("shop", "interior_decoration")), ("magasin de meubles", "décoration intérieure")),
    ("sports_shop", "Sport, vélo et outdoor", "Commerces locaux", ("47.64Z", "95.29Z"), (("shop", "bicycle"), ("shop", "sports"), ("shop", "outdoor")), ("magasin de vélo", "magasin de sport")),
    ("hardware", "Quincailleries et matériaux", "Commerces locaux", ("47.52A", "47.52B"), (("shop", "hardware"), ("shop", "doityourself")), ("quincaillerie", "matériaux de construction")),
    ("cleaning", "Nettoyage et entretien", "Services", ("81.21Z", "81.22Z", "81.29A"), (("office", "cleaning"),), ("entreprise de nettoyage",)),
    ("home_services", "Aide à domicile et services à la personne", "Services", ("88.10A", "88.10B", "97.00Z"), (("social_facility", "outreach"),), ("aide à domicile", "services à la personne")),
    ("childcare", "Crèches et garde d'enfants", "Services", ("88.91A", "88.91B"), (("amenity", "kindergarten"), ("amenity", "childcare")), ("crèche", "micro-crèche")),
    ("laundry", "Pressings, cordonniers, retouches", "Services", ("96.01B", "95.23Z"), (("shop", "dry_cleaning"), ("shop", "laundry"), ("craft", "shoemaker"), ("shop", "tailor")), ("pressing", "cordonnier", "retouches")),
    ("funeral", "Pompes funèbres", "Services", ("96.03Z",), (("shop", "funeral_directors"),), ("pompes funèbres",)),
    ("security", "Sécurité, alarme, vidéosurveillance", "Services", ("80.10Z", "80.20Z"), (("office", "security"),), ("société de sécurité", "installation alarme")),
    ("agriculture", "Domaines viticoles et producteurs", "Services", ("01.21Z", "11.02B", "01.13Z"), (("craft", "winery"), ("shop", "farm")), ("domaine viticole", "vente directe producteur")),
)


def build_additional_sector(key: str, label: str, group: str, naf_codes: tuple[str, ...], osm_tags: tuple[tuple[str, str], ...], google_maps_queries: tuple[str, ...]) -> Sector:
    """Create a sector from its identifiers and the sales profile of its family."""
    group_profile = GROUP_PROFILES[group]
    return Sector(
        key=key,
        label=label,
        group=group,
        naf_codes=naf_codes,
        osm_tags=osm_tags,
        google_maps_queries=google_maps_queries,
        is_local_storefront=group_profile.is_local_storefront,
        expected_features=group_profile.expected_features,
        discovery_questions=group_profile.discovery_questions,
        sector_recommendations=group_profile.sector_recommendations,
        pitch_angle=group_profile.pitch_angle,
    )


SECTORS: tuple[Sector, ...] = BASE_SECTORS + tuple(build_additional_sector(*sector_row) for sector_row in ADDITIONAL_SECTOR_ROWS)
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
    exact_match = next((sector for sector in SECTORS if naf_code in sector.naf_codes), None)
    return exact_match or next((sector for sector in SECTORS if naf_code_in_sections(naf_code, sector.naf_sections)), None)


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
