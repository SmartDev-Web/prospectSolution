"""Rule based sales report: diagnosis, improvement plan, phone script and follow-up email."""
from typing import Any

from app.scanner.catalog import build_finding, sort_findings
from app.sectors import Sector, get_sector
from app.text_utils import format_place_name

OPPORTUNITY_VERDICTS = {
    "no_website": "L'entreprise n'a pas de site web : c'est le prospect le plus simple à convaincre, le besoin est évident.",
    "hot": "Le site présente des défauts graves qui font fuir les visiteurs : une refonte est clairement justifiée.",
    "warm": "Le site est fonctionnel mais vieillissant : plusieurs améliorations rapides augmenteraient les contacts.",
    "cold": "Le site est globalement correct : l'angle d'approche sera l'optimisation (vitesse, référencement, conversion) plutôt que la refonte.",
}
COMMON_OBJECTIONS = (
    ("« Je n'ai pas le temps. »", "Je comprends, c'est justement pour ça que je vous appelle maintenant et pas en pleine heure de rush : je vous envoie un résumé par mail et on en reparle quand ça vous arrange ?"),
    ("« J'ai déjà quelqu'un qui s'occupe du site. »", "Très bien. Je peux quand même vous envoyer l'audit gratuitement, vous pourrez le transmettre à votre prestataire : ce sont des points concrets à corriger."),
    ("« C'est trop cher / pas de budget. »", "Je comprends. Combien vous rapporte un nouveau client en moyenne ? Si le site en apporte deux ou trois de plus par mois, il est remboursé très vite. Et on peut commencer par les corrections les plus urgentes."),
    ("« J'ai assez de clients, le bouche-à-oreille suffit. »", "Tant mieux ! Aujourd'hui, même les clients recommandés vérifient sur Google avant d'appeler. Un site daté peut leur faire changer d'avis au dernier moment."),
    ("« Envoyez-moi un mail. »", "Avec plaisir. Je vous envoie l'audit avec les captures de votre site. Je vous rappelle jeudi pour en parler cinq minutes, ça vous va ?"),
)


def freelancer_display_name(settings: dict[str, Any]) -> str:
    """Return how the freelancer introduces themself."""
    full_name = " ".join(part for part in (settings.get("freelancer_first_name"), settings.get("freelancer_last_name")) if part)
    return full_name or "[votre prénom]"


def build_signature(settings: dict[str, Any]) -> str:
    """Build the email signature from the freelancer settings."""
    signature_lines = [
        freelancer_display_name(settings),
        settings.get("freelancer_company") or "Développeur web indépendant",
        settings.get("freelancer_phone") or "",
        settings.get("freelancer_email") or "",
        settings.get("freelancer_website") or "",
    ]
    return "\n".join(line for line in signature_lines if line)


def build_call_script(prospect: dict[str, Any], sector: Sector, hooks: list[str], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a structured phone script for a first cold call."""
    freelancer_city = settings.get("freelancer_city") or prospect.get("city") or "[votre ville]"
    hook_lines = hooks[:2] or [f"Je travaille avec des entreprises comme la vôtre pour {sector.pitch_angle}."]
    return [
        {
            "title": "1. Ouverture (10 secondes)",
            "lines": [
                f"Bonjour, {freelancer_display_name(settings)}, développeur web à {freelancer_city}. Je suis bien chez {prospect['name']} ?",
                "Je ne vous dérange pas longtemps, j'ai une question rapide au sujet de votre site Internet." if prospect.get("website_url") else "Je ne vous dérange pas longtemps, j'ai une question rapide au sujet de votre visibilité sur Internet.",
            ],
        },
        {"title": "2. Accroche personnalisée", "lines": hook_lines},
        {"title": "3. Questions de découverte", "lines": list(sector.discovery_questions)},
        {
            "title": "4. Proposition",
            "lines": [
                f"Mon métier, c'est d'aider les entreprises comme la vôtre à {sector.pitch_angle}.",
                "Je vous propose de vous envoyer gratuitement un petit audit avec des captures de votre site et les points à corriger en priorité." if prospect.get("website_url") else "Je vous propose de vous montrer en 20 minutes à quoi pourrait ressembler votre site, sans engagement.",
                "On pourrait en parler 20 minutes cette semaine, chez vous ou par téléphone : plutôt mardi ou jeudi ?",
            ],
        },
        {"title": "5. Objections fréquentes", "lines": [f"{objection} → {answer}" for objection, answer in COMMON_OBJECTIONS]},
    ]


def build_follow_up_email(prospect: dict[str, Any], sector: Sector, problems: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, str]:
    """Write the email sent after a positive first call."""
    if prospect.get("website_url"):
        subject = f"Suite à notre échange : 3 pistes concrètes pour le site de {prospect['name']}"
        highlighted_problems = "\n".join(f"• {problem['title']} : {problem['impact']}" for problem in problems[:3])
        body = (
            "Bonjour,\n\n"
            "Merci pour votre temps au téléphone. Comme convenu, voici les points que j'ai relevés sur votre site :\n\n"
            f"{highlighted_problems}\n\n"
            f"Corriger ces points vous aiderait directement à {sector.pitch_angle}.\n\n"
            "Je peux vous présenter une proposition chiffrée et une maquette en 20 minutes. Quel créneau vous arrangerait cette semaine ?\n\n"
            f"Bien cordialement,\n{build_signature(settings)}"
        )
    else:
        subject = f"Suite à notre échange : la présence en ligne de {prospect['name']}"
        body = (
            "Bonjour,\n\n"
            "Merci pour votre temps au téléphone. Comme évoqué, aujourd'hui un client qui vous cherche sur Google ne trouve pas de site : "
            "il compare avec des concurrents qui en ont un, et c'est souvent eux qu'il appelle.\n\n"
            f"Un site simple, rapide et pensé pour mobile vous aiderait à {sector.pitch_angle}.\n\n"
            "Je peux vous montrer une maquette adaptée à votre activité en 20 minutes. Quel créneau vous arrangerait cette semaine ?\n\n"
            f"Bien cordialement,\n{build_signature(settings)}"
        )
    return {"subject": subject, "body": body}


def build_improvement_plan(sector: Sector, problems: list[dict[str, Any]]) -> list[str]:
    """Combine the fixes for detected problems with the sector best practices."""
    improvement_lines = [problem["recommendation"] for problem in problems if problem["severity"] in ("critical", "major")]
    improvement_lines += list(sector.sector_recommendations)
    improvement_lines += [problem["recommendation"] for problem in problems if problem["severity"] == "minor"]
    return list(dict.fromkeys(improvement_lines))


def build_summary(prospect: dict[str, Any], score: int | None, opportunity_level: str, problems: list[dict[str, Any]]) -> str:
    """Write the opening paragraph of the prospect sheet."""
    verdict = OPPORTUNITY_VERDICTS.get(opportunity_level, "")
    if not prospect.get("website_url"):
        return verdict
    critical_titles = [problem["title"].lower() for problem in problems if problem["severity"] == "critical"]
    major_titles = [problem["title"].lower() for problem in problems if problem["severity"] == "major"]
    worst_titles = (critical_titles + major_titles)[:3]
    summary = f"Le site de {prospect['name']} obtient {score}/100. {verdict}"
    if worst_titles:
        summary += f" Points les plus pénalisants : {', '.join(worst_titles)}."
    return summary


def build_rule_based_report(prospect: dict[str, Any], findings: list[dict[str, Any]], score: int | None, opportunity_level: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Assemble the full sales report for a prospect."""
    sector = get_sector(prospect.get("sector_key"))
    problems = sort_findings(findings)
    hooks = [problem["call_hook"] for problem in problems if problem["call_hook"]]
    return {
        "generator": "rules",
        "summary": build_summary(prospect, score, opportunity_level, problems),
        "problems": problems,
        "improvements": build_improvement_plan(sector, problems),
        "call_script": build_call_script(prospect, sector, hooks, settings),
        "email": build_follow_up_email(prospect, sector, problems, settings),
    }


def build_missing_website_findings(prospect: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe the situation of a business without any website."""
    sector = get_sector(prospect.get("sector_key"))
    category_label = prospect.get("category_label") or sector.label
    city = prospect.get("city") or "votre ville"
    findings = [build_finding("no_website", category=category_label, category_lower=category_label.lower(), city=format_place_name(city))]
    social_url = prospect.get("social_url") or ""
    if social_url:
        social_network = "Instagram" if "instagram" in social_url else "Facebook"
        findings.append(build_finding("social_only", social_network=social_network))
    return findings
