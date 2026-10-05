"""Detection of national chains and franchises, whose websites are managed by headquarters."""
from app.text_utils import extract_domain, normalize_company_name

# Distinctive brand names, matched anywhere in the business name as whole words
PHRASE_BRANDS = (
    "mcdonald", "mc donald", "burger king", "kfc", "subway", "domino", "pizza hut", "papa john", "five guys", "o tacos",
    "otacos", "tacos avenue", "burger and fries", "big fernand", "bagelstein", "starbucks", "columbus cafe",
    "brioche doree", "la mie caline", "marie blachere", "boulangerie ange", "ange boulangerie", "feuillette", "del arte",
    "buffalo grill", "courtepaille", "hippopotamus", "leon de bruxelles", "flunch", "poivre rouge", "la pataterie",
    "pizza cosy", "le bistrot du boucher", "memphis coffee", "class croute", "sushi shop", "planet sushi", "eat sushi",
    "cote sushi", "pitaya", "nooi", "exki", "pret a manger", "chamas tacos", "fresh burritos", "cojean", "dunkin",
    "krispy kreme", "popeyes", "tim hortons", "black and white burger", "king marcel", "french coffee shop", "max asian",
    "mezzo di pasta", "pizza pai", "speed rabbit", "kiosque a pizzas", "kiosque a pizza", "tutti pizza", "pizza delizia", "basilic and co",
    "basilic & co", "3 brasseurs", "trois brasseurs", "volfoni", "cafe leffe", "wafu",
    "e leclerc", "e.leclerc", "centre leclerc", "carrefour market", "carrefour city", "carrefour express", "carrefour contact",
    "petit casino", "casino shop", "geant casino", "intermarche", "super u", "hyper u", "u express", "systeme u", "auchan", "franprix",
    "monoprix", "vival", "lidl", "aldi", "netto", "leader price", "grand frais", "biocoop", "naturalia", "la vie claire",
    "bio c bon", "v and b", "v&b", "colruyt", "boucherie nivernaise", "promocash", "maison du whisky", "cavavin",
    "repaire de bacchus", "jeff de bruges", "leonidas", "nespresso", "comptoirs richard", "comptoir irlandais",
    "leroy merlin", "castorama", "brico marche", "bricomarche", "brico depot", "bricorama", "mr bricolage", "weldom",
    "point p", "gedimat", "big mat", "bigmat", "ikea", "conforama", "but cosy", "maisons du monde", "gifi",
    "foir fouille", "stokomani", "centrakor", "decathlon", "intersport", "go sport", "sport 2000", "darty", "fnac",
    "cultura", "jardiland", "gamm vert", "botanic", "animalis", "maxi zoo", "tom&co", "tom & co", "norauto", "feu vert",
    "euromaster", "roady", "bouygues telecom", "phone house", "point service mobiles", "wefix", "sephora", "nocibe",
    "marionnaud", "yves rocher", "occitane", "kiko", "franck provost", "jean louis david", "dessange", "saint algue",
    "tchip", "frederic moreno", "camille albane", "coiff&co", "coiff and co", "body minute", "esthetic center",
    "afflelou", "optic 2000", "krys", "general d'optique", "grandvision", "audika", "amplifon", "pharmacie lafayette",
    "la poste", "credit agricole", "banque populaire", "caisse d'epargne", "bnp paribas", "societe generale",
    "credit mutuel", "maaf", "macif", "matmut", "groupama", "allianz", "century 21", "orpi", "guy hoquet",
    "era immobilier", "stephane plaza", "foncia", "nexity", "citya", "adecco", "manpower", "randstad", "temporis",
    "basic fit", "basic-fit", "fitness park", "keep cool", "orange bleue", "neoness", "cigusto", "clopinette",
    "petit vapoteur", "vapostore", "j well", "vapo club", "kiloutou", "loxam",
    # Clothing, shoes and fashion
    "kiabi", "zara", "h&m", "h & m", "primark", "celio", "camaieu", "pimkie", "promod", "gemo", "chaussea", "besson chaussures", "foot locker", "courir", "jd sports", "decimas",
    "bershka", "pull and bear", "pull & bear", "stradivarius", "etam", "undiz", "orcanta", "jennyfer",
    "naf naf", "armand thiery", "cache cache", "bizzbee", "okaidi", "jacadi", "du pareil au meme",
    "sergent major", "tape a l oeil", "vertbaudet", "intimissimi", "calzedonia", "levi s", "superdry", "sostrene grene", "hema", "flying tiger", "babou", "maxi bazar", "la grande recre", "king jouet", "jouet club",
    "pandora", "histoire d or", "marc orian", "julien d orcel", "claire s", "lush", "rituals", "sephora", "nocibe",
    "kiko milano", "mac cosmetics", "body shop", "l occitane",
    # Home, furniture and electronics "zodio", "alinea", "electro depot", "cash express", "cash converters", "easy cash", "mobalpa", "cuisinella", "cuisines schmidt", "cuisines references", "ixina", "la foir fouille", "maisons du monde", "conforama", "darty", "but cosy", "la maison de la literie", "maison de la literie",
    "grand litier", "monsieur meuble", "tediber", "bricomarche", "toolstation", "brico cash",
    # Optics, health and services networks
    "optical center", "grand optical", "alain afflelou", "general d optique", "les opticiens mutualistes",
    "carglass", "france pare brise", "dekra", "autosur", "securitest", "autobacs", "vulco", "carter cash",
    "ibis", "campanile", "kyriad", "b&b hotel", "b & b hotel", "novotel", "mercure", "premiere classe", "formule 1",
    "hotel f1", "best western", "logis hotel", "holiday inn", "appart city", "zenitude",
    "iad france", "safti", "capifrance", "optimhome", "megagence", "proprietes privees", "square habitat",
    "bistro regent", "flam s", "tablapizza", "la croissanterie", "pomme de pain", "bagel corner", "les burgers de papa",
    "o tacos", "tacos king", "pitaya thai street food", "fabio salsa", "esthetic center", "body minute",
    "fitness park", "keep cool", "on air fitness", "magic form", "l appart fitness", "vita liberte",
    "acadomia", "complete formation", "anacours", "o2 care services", "shiva menage", "family sphere",
)
# Brands that are also common words, first names or surnames: they must be the whole business name
EXACT_MATCH_BRANDS = (
    "paul", "quick", "but", "save", "free", "orange", "sfr", "action", "match", "metro", "casino", "spar", "cora",
    "noz", "sumo", "lcl", "cic", "axa", "mma", "o2", "shiva", "nicolas", "picard", "thiriet", "atol", "midas", "speedy",
    "point s", "on air", "laforet", "truffaut", "boulanger", "leclerc", "carrefour", "normal", "casa", "fly", "atlas",
    "jules", "brice", "mango", "adagio", "shampoo", "schmidt", "lapeyre", "devred", "lissac", "bonobo", "la halle",
)
CHAIN_WEBSITE_DOMAINS = (
    "mcdonalds.fr", "burgerking.fr", "quick.fr", "kfc.fr", "subwayfrance.fr", "subway.com", "dominos.fr", "pizzahut.fr",
    "fiveguys.fr", "o-tacos.com", "starbucks.fr", "paul.fr", "briochedoree.fr", "lamiecaline.com", "marieblachere.com",
    "delarte.fr", "buffalo-grill.fr", "courtepaille.com", "hippopotamus.fr", "leon-de-bruxelles.fr", "flunch.fr",
    "e.leclerc", "leclerc.fr", "carrefour.fr", "intermarche.com", "magasins-u.com", "coursesu.com", "auchan.fr",
    "lidl.fr", "aldi.fr", "leroymerlin.fr", "castorama.fr", "bricomarche.com", "bricodepot.fr", "mr-bricolage.fr",
    "weldom.fr", "ikea.com", "conforama.fr", "but.fr", "decathlon.fr", "intersport.fr", "darty.com", "boulanger.com",
    "fnac.com", "orange.fr", "sfr.fr", "bouyguestelecom.fr", "free.fr", "sephora.fr", "nocibe.fr", "franck-provost.com",
    "jeanlouisdavid.com", "tchip.fr", "optic2000.com", "krys.com", "afflelou.com", "basic-fit.com", "fitnesspark.fr",
    "pagesjaunes.fr", "grandfrais.com", "picard.fr", "biocoop.fr", "naturalia.fr", "nicolas.com", "gifi.fr", "action.com",
    "jardiland.com", "truffaut.com", "gammvert.fr", "norauto.fr", "feuvert.fr", "midas.fr", "speedy.fr", "laposte.fr",
)
CHAIN_ESTABLISHMENT_THRESHOLD = 15


NORMALIZED_PHRASE_BRANDS = tuple(dict.fromkeys(filter(None, (normalize_company_name(brand) for brand in PHRASE_BRANDS))))
NORMALIZED_EXACT_MATCH_BRANDS = frozenset(filter(None, (normalize_company_name(brand) for brand in EXACT_MATCH_BRANDS)))


def find_brand_in_name(name: str) -> str | None:
    """Return the chain brand designated by a business name, if any."""
    normalized_name = normalize_company_name(name or "")
    if not normalized_name:
        return None
    if normalized_name in NORMALIZED_EXACT_MATCH_BRANDS:
        return normalized_name
    padded_name = f" {normalized_name} "
    return next((brand for brand in NORMALIZED_PHRASE_BRANDS if f" {brand} " in padded_name), None)


def parse_custom_brands(custom_brands_text: str | None) -> list[str]:
    """Normalize the chain names entered by the user, one per line."""
    return [normalized_brand for normalized_brand in (normalize_company_name(line) for line in (custom_brands_text or "").splitlines()) if normalized_brand]


def detect_chain(
    names: list[str],
    website_url: str | None = None,
    brand: str | None = None,
    establishment_count: int | None = None,
    custom_brands: list[str] | None = None,
) -> str | None:
    """Return the reason why a business belongs to a chain, or None for an independent business."""
    if brand:
        return f"marque nationale « {brand} »"
    for name in names:
        padded_name = f" {normalize_company_name(name or '')} "
        matched_custom_brand = next((custom_brand for custom_brand in custom_brands or [] if f" {custom_brand} " in padded_name), None)
        if matched_custom_brand:
            return f"chaîne ajoutée manuellement « {matched_custom_brand.title()} »"
    website_domain = extract_domain(website_url) or ""
    for chain_domain in CHAIN_WEBSITE_DOMAINS:
        if website_domain == chain_domain or website_domain.endswith(f".{chain_domain}"):
            return f"site national {chain_domain}"
    for name in names:
        matched_brand = find_brand_in_name(name)
        if matched_brand:
            return f"enseigne {matched_brand.title()}"
    if establishment_count is not None and establishment_count >= CHAIN_ESTABLISHMENT_THRESHOLD:
        return f"réseau de {establishment_count} établissements"
    return None
