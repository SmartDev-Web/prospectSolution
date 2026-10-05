"""Catalog of every website issue the scanner can report, written for business owners."""
from dataclasses import dataclass
from typing import Any

SEVERITY_PENALTIES = {"critical": 18, "major": 9, "minor": 3}
SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}
CATEGORY_LABELS = {
    "availability": "Disponibilité",
    "security": "Sécurité",
    "mobile": "Mobile",
    "performance": "Vitesse",
    "conversion": "Conversion",
    "seo": "Référencement Google",
    "legal": "Légal",
    "design": "Design",
    "technology": "Technique",
    "content": "Contenu",
    "sector": "Métier",
}


@dataclass(frozen=True)
class FindingDefinition:
    """Business oriented description of a website issue."""
    code: str
    category: str
    severity: str
    title: str
    impact: str
    recommendation: str
    call_hook: str = ""


FINDING_DEFINITIONS: tuple[FindingDefinition, ...] = (
    FindingDefinition(
        "no_website", "availability", "critical", "Aucun site web",
        "Quand un client cherche « {category} {city} » sur Google, ce sont les concurrents qui ont un site qui récupèrent l'appel. Sans site, l'entreprise dépend uniquement du bouche-à-oreille et des plateformes.",
        "Créer un site vitrine simple et rapide, optimisé pour Google et pour mobile, avec un bouton d'appel bien visible.",
        "En cherchant {category_lower} sur {city}, je suis tombé sur votre fiche, mais vous n'avez pas de site : les clients qui comparent sur Internet appellent forcément quelqu'un d'autre.",
    ),
    FindingDefinition(
        "social_only", "availability", "major", "Présence uniquement sur les réseaux sociaux",
        "Une page Facebook ou Instagram n'apparaît presque pas dans Google et ne rassure pas autant qu'un vrai site. Vous ne maîtrisez ni la visibilité, ni les règles de la plateforme.",
        "Créer un site relié aux réseaux sociaux pour récupérer le trafic Google.",
        "J'ai vu votre page {social_network}, elle est sympa, mais sur Google on ne vous trouve pas.",
    ),
    FindingDefinition(
        "site_unreachable", "availability", "critical", "Site inaccessible",
        "Les visiteurs tombent sur une erreur ({detail}) : chaque visite est un client perdu, et Google finit par retirer le site de ses résultats.",
        "Rétablir l'hébergement au plus vite et mettre en place une surveillance de disponibilité.",
        "J'ai voulu aller sur votre site et il ne s'affiche pas du tout, vous étiez au courant ?",
    ),
    FindingDefinition(
        "site_under_construction", "content", "critical", "Site « en construction »",
        "Une page « en construction » donne l'image d'une entreprise pas sérieuse ou inactive, et n'apporte aucun client.",
        "Publier un vrai site vitrine, même de quelques pages.",
        "Votre site affiche toujours une page « en construction », c'est voulu ?",
    ),
    FindingDefinition(
        "no_https", "security", "critical", "Site non sécurisé (pas de HTTPS)",
        "Chrome affiche « Non sécurisé » à côté de l'adresse : une bonne partie des visiteurs fait demi-tour, et Google pénalise le référencement des sites sans HTTPS.",
        "Installer un certificat SSL (gratuit avec Let's Encrypt) et rediriger tout le trafic vers HTTPS.",
        "Quand on ouvre votre site, Chrome affiche « Non sécurisé » en haut de l'écran, ça fait fuir pas mal de visiteurs.",
    ),
    FindingDefinition(
        "invalid_certificate", "security", "critical", "Certificat de sécurité invalide",
        "Le navigateur affiche une page d'alerte rouge avant même d'afficher le site ({detail}) : quasiment tous les visiteurs repartent.",
        "Renouveler le certificat SSL et automatiser son renouvellement.",
        "En allant sur votre site, le navigateur affiche une grosse alerte de sécurité rouge, vous l'aviez remarqué ?",
    ),
    FindingDefinition(
        "certificate_expiring", "security", "major", "Certificat de sécurité bientôt expiré",
        "Le certificat expire dans {days} jours : ensuite, les visiteurs verront une alerte de sécurité au lieu du site.",
        "Renouveler le certificat et activer le renouvellement automatique.",
        "Le certificat de sécurité de votre site expire dans {days} jours, après ça les visiteurs auront une alerte rouge.",
    ),
    FindingDefinition(
        "http_not_redirected", "security", "minor", "La version non sécurisée reste accessible",
        "Le site répond aussi en HTTP sans rediriger vers HTTPS : certains visiteurs naviguent sans chiffrement et Google voit deux sites en double.",
        "Forcer la redirection permanente (301) de HTTP vers HTTPS.",
    ),
    FindingDefinition(
        "mixed_content", "security", "minor", "Contenu non sécurisé sur une page sécurisée",
        "Certaines ressources ({count}) sont chargées en HTTP : le cadenas disparaît et certains éléments sont bloqués par le navigateur.",
        "Charger toutes les images, scripts et styles en HTTPS.",
    ),
    FindingDefinition(
        "outdated_cms", "security", "major", "CMS obsolète ({detail})",
        "Les anciennes versions de CMS ont des failles connues et exploitées automatiquement : risque de piratage, de redirection vers des sites frauduleux et de mise sur liste noire par Google.",
        "Mettre à jour le CMS et ses extensions, ou refondre le site sur une base moderne et maintenue.",
        "Votre site tourne sur une version de {detail} qui n'est plus maintenue, c'est le genre de site qui se fait pirater automatiquement.",
    ),
    FindingDefinition(
        "outdated_javascript", "technology", "minor", "Bibliothèques JavaScript obsolètes (jQuery {detail})",
        "Cette version de jQuery contient des failles de sécurité connues et ralentit le site.",
        "Mettre à jour ou supprimer les bibliothèques obsolètes.",
    ),
    FindingDefinition(
        "no_viewport", "mobile", "critical", "Site non adapté aux mobiles",
        "Plus de 60 % des visites se font sur smartphone : le site s'y affiche en miniature et il faut zoomer pour lire. Google classe moins bien les sites non adaptés aux mobiles.",
        "Refondre le site en « responsive » : mise en page adaptée à chaque taille d'écran.",
        "J'ai regardé votre site sur mon téléphone, il faut zoomer pour lire quoi que ce soit, alors que la majorité de vos visiteurs sont sur mobile.",
    ),
    FindingDefinition(
        "mobile_horizontal_scroll", "mobile", "major", "Mise en page cassée sur mobile",
        "Sur smartphone, le contenu déborde de l'écran ({overflow} px de trop) : le visiteur doit faire défiler horizontalement, ce qui donne une impression de site cassé.",
        "Corriger la mise en page mobile (éléments à largeur fixe, images non redimensionnées).",
        "Sur téléphone, votre site déborde de l'écran, on doit le faire glisser de gauche à droite pour lire.",
    ),
    FindingDefinition(
        "mobile_small_text", "mobile", "minor", "Texte trop petit sur mobile",
        "Le texte principal fait {size} px sur mobile : il est difficile à lire sans zoomer.",
        "Utiliser une taille de texte d'au moins 16 px sur mobile.",
    ),
    FindingDefinition(
        "flash_content", "technology", "critical", "Contenu Flash",
        "Flash n'est plus lu par aucun navigateur depuis 2021 : ces parties du site s'affichent comme des zones vides.",
        "Remplacer les animations Flash par du contenu moderne (HTML, vidéo, images).",
        "Une partie de votre site utilise Flash, une technologie qui ne s'affiche plus du tout depuis 2021.",
    ),
    FindingDefinition(
        "obsolete_html", "technology", "major", "Technologies web obsolètes ({detail})",
        "Le site utilise des techniques abandonnées depuis plus de 15 ans : affichage aléatoire selon les navigateurs, maintenance difficile et image vieillissante.",
        "Reconstruire le site avec des technologies actuelles.",
        "Techniquement votre site date un peu, il utilise des techniques des années 2000.",
    ),
    FindingDefinition(
        "table_layout", "design", "major", "Mise en page en tableaux (technique des années 2000)",
        "La structure du site repose sur des tableaux : impossible à adapter au mobile et visuellement daté.",
        "Refaire la mise en page avec des techniques modernes (CSS Grid, Flexbox).",
    ),
    FindingDefinition(
        "old_doctype", "technology", "minor", "Code HTML ancien ({detail})",
        "Le site est déclaré dans une ancienne norme HTML : signe d'un site jamais refondu.",
        "Migrer vers HTML5 lors de la refonte.",
    ),
    FindingDefinition(
        "javascript_errors", "technology", "minor", "Erreurs techniques sur la page",
        "{count} erreurs JavaScript se produisent au chargement : certaines fonctionnalités (menus, formulaires, sliders) peuvent ne pas marcher.",
        "Corriger les scripts en erreur.",
    ),
    FindingDefinition(
        "site_builder", "technology", "minor", "Site réalisé avec un constructeur grand public ({detail})",
        "Ces outils produisent des sites lents, au design générique et mal référencés. L'abonnement est payé chaque mois sans jamais être propriétaire du site.",
        "Passer sur un site sur mesure, rapide et dont l'entreprise est propriétaire.",
        "Votre site est fait avec {detail} : c'est pratique pour démarrer, mais c'est lent et Google le met rarement en avant.",
    ),
    FindingDefinition(
        "outdated_copyright", "content", "major", "Site non mis à jour depuis {years} ans (© {year})",
        "Un copyright ancien en bas de page donne l'impression que l'entreprise n'est plus active : le visiteur doute et appelle un concurrent.",
        "Mettre à jour le contenu régulièrement et afficher l'année en cours.",
        "En bas de votre site, il est écrit © {year} : pour un client qui découvre l'entreprise, ça donne l'impression que le site est abandonné.",
    ),
    FindingDefinition(
        "dated_design", "design", "major", "Design daté ({detail})",
        "Au premier coup d'œil, le site paraît ancien. Le visiteur en déduit que l'entreprise est dépassée, voire fermée, et va voir un concurrent dont le site inspire confiance.",
        "Refondre le design : mise en page aérée, typographie moderne, grandes photos, palette cohérente avec l'identité de l'entreprise.",
        "Honnêtement, votre site donne l'impression d'avoir une dizaine d'années : pour un client qui vous découvre, il ne reflète pas la qualité de votre travail.",
    ),
    FindingDefinition(
        "outdated_framework", "technology", "minor", "Bibliothèques de mise en page anciennes ({detail})",
        "Ces versions ne sont plus maintenues : affichage moins soigné sur les écrans récents et failles de sécurité non corrigées.",
        "Mettre à jour les bibliothèques lors d'une modernisation du site.",
    ),
    FindingDefinition(
        "no_phone_on_homepage", "conversion", "minor", "Numéro absent de la page d'accueil",
        "Le téléphone n'apparaît que sur une page secondaire : le visiteur pressé ne le trouve pas tout de suite.",
        "Afficher le numéro en haut de chaque page, cliquable sur mobile.",
    ),
    FindingDefinition(
        "dated_typography", "design", "minor", "Typographie datée ({detail})",
        "Les polices par défaut ou fantaisie donnent immédiatement un aspect amateur ou ancien au site.",
        "Choisir une typographie moderne et lisible, cohérente avec l'image de l'entreprise.",
    ),
    FindingDefinition(
        "thin_content", "content", "minor", "Contenu trop pauvre ({count} mots)",
        "Avec si peu de texte, Google ne sait pas pour quels services ni quelle ville afficher le site.",
        "Rédiger des pages décrivant chaque service, avec la zone d'intervention.",
    ),
    FindingDefinition(
        "missing_images_alt", "seo", "minor", "Images sans description ({percentage} %)",
        "Les images sans texte alternatif sont invisibles pour Google Images et pour les personnes malvoyantes.",
        "Ajouter une description (attribut alt) à chaque image.",
    ),
    FindingDefinition(
        "slow_loading", "performance", "major", "Chargement lent ({seconds} s)",
        "Plus de la moitié des visiteurs mobiles quittent une page qui met plus de 3 secondes à s'afficher. Google pénalise aussi les sites lents.",
        "Optimiser les images, l'hébergement et le code pour viser moins de 2 secondes.",
        "Votre site met {seconds} secondes à s'afficher, la plupart des gens sur mobile n'attendent pas autant.",
    ),
    FindingDefinition(
        "heavy_page", "performance", "major", "Page trop lourde ({megabytes} Mo)",
        "La page d'accueil pèse {megabytes} Mo : en 4G moyenne, c'est lent et ça consomme le forfait des visiteurs.",
        "Compresser les images (WebP/AVIF) et supprimer les scripts inutiles.",
    ),
    FindingDefinition(
        "too_many_requests", "performance", "minor", "Trop de fichiers chargés ({count})",
        "La page charge {count} fichiers différents, ce qui ralentit l'affichage, surtout sur mobile.",
        "Regrouper et alléger les ressources chargées.",
    ),
    FindingDefinition(
        "lighthouse_performance", "performance", "major", "Score de performance Google faible ({score}/100)",
        "L'outil d'audit de Google (Lighthouse) note la vitesse du site {score}/100 : c'est un critère de classement dans les résultats.",
        "Optimiser les performances pour dépasser 90/100.",
        "J'ai passé votre site dans l'outil de Google, il obtient {score} sur 100 en vitesse.",
    ),
    FindingDefinition(
        "lighthouse_accessibility", "content", "minor", "Accessibilité insuffisante ({score}/100)",
        "Contrastes, tailles de boutons, libellés : le site est difficile à utiliser pour une partie des visiteurs.",
        "Corriger les points d'accessibilité relevés par l'audit.",
    ),
    FindingDefinition(
        "lighthouse_seo", "seo", "minor", "Référencement technique perfectible ({score}/100)",
        "L'audit SEO de Google relève des erreurs de base qui limitent la visibilité du site.",
        "Corriger les points SEO relevés par l'audit.",
    ),
    FindingDefinition(
        "missing_title", "seo", "major", "Titre de page absent",
        "Le titre est ce qui s'affiche en bleu dans les résultats Google : sans lui, le site est quasiment invisible.",
        "Rédiger un titre unique par page incluant le métier et la ville.",
    ),
    FindingDefinition(
        "poor_title", "seo", "minor", "Titre de page peu efficace (« {detail} »)",
        "Le titre affiché dans Google ne mentionne pas clairement le métier et la ville : le site sort moins bien sur les recherches locales.",
        "Utiliser un titre du type « Métier à Ville – Nom de l'entreprise ».",
    ),
    FindingDefinition(
        "missing_meta_description", "seo", "minor", "Description Google absente",
        "Google affiche un extrait choisi au hasard sous le titre : le résultat donne moins envie de cliquer.",
        "Rédiger une description incitative de 150 caractères par page.",
    ),
    FindingDefinition(
        "missing_h1", "seo", "minor", "Pas de titre principal (H1)",
        "Google ne sait pas quel est le sujet principal de la page.",
        "Ajouter un titre principal décrivant l'activité.",
    ),
    FindingDefinition(
        "missing_structured_data", "seo", "minor", "Pas de données structurées",
        "Les données structurées aident Google à afficher horaires, avis et adresse directement dans les résultats.",
        "Ajouter le balisage Schema.org LocalBusiness.",
    ),
    FindingDefinition(
        "missing_social_preview", "seo", "minor", "Aperçu de partage absent",
        "Quand quelqu'un partage le site sur Facebook ou WhatsApp, aucun visuel ni titre propre n'apparaît.",
        "Ajouter les balises Open Graph (titre, description, image).",
    ),
    FindingDefinition(
        "missing_favicon", "design", "minor", "Pas d'icône de site (favicon)",
        "L'onglet du navigateur affiche une icône générique : détail qui fait amateur.",
        "Ajouter une favicon reprenant le logo.",
    ),
    FindingDefinition(
        "no_click_to_call", "conversion", "major", "Numéro de téléphone non cliquable",
        "Sur mobile, le client doit recopier le numéro à la main : beaucoup abandonnent. Un bouton « Appeler » augmente directement le nombre d'appels.",
        "Rendre le numéro cliquable et ajouter un bouton d'appel fixe sur mobile.",
        "Sur mobile, on ne peut pas cliquer sur votre numéro pour vous appeler, il faut le recopier : vous perdez forcément des appels.",
    ),
    FindingDefinition(
        "no_phone_visible", "conversion", "major", "Aucun numéro de téléphone sur la page d'accueil",
        "Le visiteur prêt à appeler doit chercher le numéro : une partie abandonne avant de le trouver.",
        "Afficher le numéro en haut de chaque page.",
        "Sur votre page d'accueil, je n'ai pas trouvé votre numéro de téléphone.",
    ),
    FindingDefinition(
        "no_call_to_action", "conversion", "major", "Aucun appel à l'action en haut de page",
        "En arrivant sur le site, rien n'invite à appeler, réserver ou demander un devis : le visiteur regarde puis repart.",
        "Ajouter un bouton clair et visible dès l'arrivée (« Appeler », « Réserver », « Demander un devis »).",
    ),
    FindingDefinition(
        "no_contact_form", "conversion", "minor", "Pas de formulaire de contact",
        "Les clients qui n'osent pas appeler, ou qui cherchent le soir, n'ont aucun moyen simple de vous contacter.",
        "Ajouter un formulaire de contact court sur chaque page clé.",
    ),
    FindingDefinition(
        "no_map", "conversion", "minor", "Pas de plan d'accès",
        "Pour un commerce, le plan est l'un des éléments les plus consultés : son absence fait perdre des visites en boutique.",
        "Intégrer une carte Google Maps et les informations d'accès et de stationnement.",
    ),
    FindingDefinition(
        "no_social_links", "conversion", "minor", "Pas de lien vers les réseaux sociaux",
        "Les visiteurs ne peuvent pas suivre l'actualité de l'entreprise ni voir les avis récents.",
        "Relier le site aux réseaux sociaux actifs de l'entreprise.",
    ),
    FindingDefinition(
        "no_testimonials", "conversion", "minor", "Aucun avis client mis en avant",
        "Les avis rassurent plus que n'importe quel argument commercial : sans eux, le visiteur hésite.",
        "Afficher les avis Google et des témoignages clients.",
    ),
    FindingDefinition(
        "missing_legal_notice", "legal", "major", "Mentions légales absentes",
        "Les mentions légales sont obligatoires pour tout site professionnel (loi LCEN) : jusqu'à 75 000 € d'amende pour un entrepreneur individuel et 375 000 € pour une société.",
        "Ajouter une page de mentions légales complète.",
        "Je n'ai pas trouvé de mentions légales sur votre site : c'est obligatoire et l'amende peut être lourde.",
    ),
    FindingDefinition(
        "missing_cookie_consent", "legal", "major", "Traceurs sans bandeau de consentement ({detail})",
        "Le site dépose des traceurs publicitaires ou statistiques sans demander l'accord du visiteur : non conforme au RGPD, et la CNIL sanctionne régulièrement les petites entreprises.",
        "Mettre en place un bandeau de consentement conforme.",
    ),
    FindingDefinition(
        "missing_online_booking", "sector", "major", "Pas de réservation en ligne",
        "Une grande partie des clients réserve le soir ou au dernier moment sur leur téléphone : sans réservation en ligne, ils choisissent un établissement qui la propose.",
        "Intégrer un module de réservation en ligne directement sur le site.",
        "Pour réserver chez vous, il faut forcément appeler : beaucoup de gens réservent le soir sur leur téléphone, quand vous êtes fermé.",
    ),
    FindingDefinition(
        "missing_menu", "sector", "major", "Carte ou menu introuvable",
        "La carte est la page la plus consultée d'un site de restaurant : sans elle, le visiteur passe au suivant.",
        "Publier la carte en texte, lisible sur mobile et facile à mettre à jour.",
        "Je n'ai pas trouvé votre carte sur le site, c'est pourtant ce que les gens regardent en premier.",
    ),
    FindingDefinition(
        "missing_online_ordering", "sector", "minor", "Pas de commande en ligne",
        "Les clients ne peuvent pas commander ou réserver leurs produits à l'avance : ventes perdues aux heures d'affluence et pendant les fêtes.",
        "Ajouter du click & collect ou un formulaire de commande.",
    ),
    FindingDefinition(
        "missing_appointment_booking", "sector", "major", "Pas de prise de rendez-vous en ligne",
        "Les clients doivent appeler pendant les heures d'ouverture, souvent au moment où vous êtes occupé : une partie ne rappelle jamais.",
        "Intégrer la prise de rendez-vous en ligne 24 h/24.",
        "Pour prendre rendez-vous chez vous il faut appeler, et j'imagine que vous ne pouvez pas toujours décrocher pendant une prestation.",
    ),
    FindingDefinition(
        "missing_price_list", "sector", "minor", "Tarifs non affichés",
        "Les clients comparent les prix avant d'appeler : sans tarifs, ils appellent les concurrents qui les affichent.",
        "Afficher une grille de tarifs ou des prix « à partir de ».",
    ),
    FindingDefinition(
        "missing_quote_request", "sector", "major", "Pas de demande de devis en ligne",
        "Les acheteurs veulent envoyer leur besoin en deux minutes : sans formulaire de devis, ils sollicitent un autre fournisseur.",
        "Ajouter un formulaire de demande de devis avec envoi de fichiers.",
        "Sur votre site, il n'y a pas de moyen simple de demander un devis : les acheteurs pressés passent au fournisseur suivant.",
    ),
    FindingDefinition(
        "missing_english_version", "sector", "minor", "Pas de version anglaise",
        "Les donneurs d'ordre étrangers ne peuvent pas évaluer l'entreprise.",
        "Proposer au minimum les pages clés en anglais.",
    ),
    FindingDefinition(
        "missing_credentials", "sector", "minor", "Références et certifications peu visibles",
        "Un acheteur industriel cherche d'abord à être rassuré : certifications, références et parc machines doivent sauter aux yeux.",
        "Créer une section références, certifications et moyens de production.",
    ),
    FindingDefinition(
        "missing_opening_hours", "sector", "minor", "Horaires introuvables",
        "Les horaires sont l'une des informations les plus recherchées : si elles manquent, le client n'ose pas se déplacer.",
        "Afficher les horaires sur la page d'accueil et les synchroniser avec Google.",
    ),
)
FINDING_DEFINITIONS_BY_CODE = {definition.code: definition for definition in FINDING_DEFINITIONS}


class SafeFormatDictionary(dict):
    """Keep unknown placeholders visible instead of raising during formatting."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def format_text(template: str, evidence: dict[str, Any]) -> str:
    """Fill a catalog template with evidence values."""
    return template.format_map(SafeFormatDictionary(evidence))


def build_finding(code: str, severity: str | None = None, **evidence: Any) -> dict[str, Any]:
    """Create a finding dictionary from its catalog definition and the measured evidence."""
    definition = FINDING_DEFINITIONS_BY_CODE[code]
    return {
        "code": code,
        "category": definition.category,
        "category_label": CATEGORY_LABELS[definition.category],
        "severity": severity or definition.severity,
        "title": format_text(definition.title, evidence),
        "impact": format_text(definition.impact, evidence),
        "recommendation": format_text(definition.recommendation, evidence),
        "call_hook": format_text(definition.call_hook, evidence),
        "evidence": evidence,
    }


def sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order findings from the most to the least severe."""
    return sorted(findings, key=lambda finding: SEVERITY_ORDER[finding["severity"]])


SCORE_BUCKETS = {
    "security": ("Sécurité", 15),
    "mobile": ("Mobile", 20),
    "performance": ("Vitesse", 15),
    "design": ("Design et technique", 20),
    "conversion": ("Conversion", 20),
    "seo": ("Référencement", 7),
    "legal": ("Légal", 3),
}
CATEGORY_TO_BUCKET = {
    "availability": "security", "security": "security", "mobile": "mobile", "performance": "performance",
    "design": "design", "technology": "design", "content": "design", "conversion": "conversion", "sector": "conversion",
    "seo": "seo", "legal": "legal",
}
SEVERITY_BUCKET_SHARE = {"critical": 0.8, "major": 0.4, "minor": 0.12}
CRITICAL_SCORE_CAP = 40
STRENGTH_LABELS = {
    "secure": "Site sécurisé (HTTPS valide)",
    "responsive": "Bien adapté au mobile",
    "fast": "Affichage rapide ({seconds} s)",
    "modern_stack": "Technologie récente ({detail})",
    "modern_layout": "Mise en page moderne",
    "click_to_call": "Numéro cliquable sur mobile",
    "online_booking": "Réservation ou commande en ligne",
    "recently_updated": "Site tenu à jour (© {year})",
    "legal_ok": "Mentions légales présentes",
    "good_reputation": "Très bonne réputation Google ({rating} ★, {count} avis)",
    "rich_content": "Contenu riche ({count} mots)",
}


def build_strength(code: str, **evidence: Any) -> dict[str, str]:
    """Create a strength entry, the positive counterpart of a finding."""
    return {"code": code, "label": format_text(STRENGTH_LABELS[code], evidence)}


def compute_score_breakdown(findings: list[dict[str, Any]], unmeasured_buckets: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Score every category of the site, each limited to its own weight; unmeasured categories get no score."""
    penalty_shares = {bucket_key: 0.0 for bucket_key in SCORE_BUCKETS}
    for finding in findings:
        penalty_shares[CATEGORY_TO_BUCKET[finding["category"]]] += SEVERITY_BUCKET_SHARE[finding["severity"]]
    return {
        bucket_key: {
            "label": bucket_label,
            "weight": bucket_weight,
            "measured": bucket_key not in (unmeasured_buckets or []),
            "score": round(bucket_weight * max(0.0, 1 - penalty_shares[bucket_key]), 1),
        }
        for bucket_key, (bucket_label, bucket_weight) in SCORE_BUCKETS.items()
    }


def compute_score(findings: list[dict[str, Any]], unmeasured_buckets: list[str] | None = None) -> int:
    """Compute a 0-100 website quality score from the measured categories, capped when a critical issue exists."""
    measured_buckets = [bucket for bucket in compute_score_breakdown(findings, unmeasured_buckets).values() if bucket["measured"]]
    measured_weight = sum(bucket["weight"] for bucket in measured_buckets)
    total_score = round(100 * sum(bucket["score"] for bucket in measured_buckets) / measured_weight) if measured_weight else 0
    if any(finding["severity"] == "critical" for finding in findings):
        return min(total_score, CRITICAL_SCORE_CAP)
    return total_score


def compute_opportunity_level(score: int | None, has_website: bool, reachable: bool = True) -> str:
    """Translate a score into a prospecting priority."""
    if not has_website:
        return "no_website"
    if not reachable or score is None or score < 50:
        return "hot"
    if score < 70:
        return "warm"
    return "cold"
