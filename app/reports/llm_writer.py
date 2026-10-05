"""Optional rewriting of the sales report by the local language model."""
import json
import logging
from typing import Any

import httpx

from app.llm.ollama import ollama_service
from app.reports.rules import build_signature
from app.sectors import get_sector
from app.settings_service import load_settings

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = (
    "Tu es un commercial expert en création de sites web pour TPE et PME françaises. "
    "Tu écris en français, de façon concrète, chaleureuse et sans jargon technique. "
    "Tu parles des conséquences business (appels, clients, chiffre d'affaires), jamais de technique pure. "
    "Tu n'inventes aucun fait : tu t'appuies uniquement sur les constats fournis. "
    "Tu réponds uniquement avec un objet JSON valide."
)


def build_user_prompt(prospect: dict[str, Any], report: dict[str, Any]) -> str:
    """Describe the prospect and the detected problems to the model."""
    sector = get_sector(prospect.get("sector_key"))
    facts = {
        "entreprise": prospect["name"],
        "activite": prospect.get("category_label") or sector.label,
        "ville": prospect.get("city"),
        "site_web": prospect.get("website_url"),
        "note_google": prospect.get("google_rating"),
        "nombre_avis_google": prospect.get("google_review_count"),
        "objectif_business_du_secteur": sector.pitch_angle,
        "constats": [
            {"gravite": problem["severity"], "titre": problem["title"], "impact": problem["impact"]}
            for problem in report["problems"][:8]
        ],
    }
    return (
        "Voici les faits sur un prospect :\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=1)}\n\n"
        "Rédige un JSON avec exactement ces clés :\n"
        '- "summary" : 3 à 4 phrases qui résument ce qui ne va pas et ce que l\'entreprise perd concrètement ;\n'
        '- "call_hook" : une seule phrase d\'accroche naturelle à dire au téléphone dans les 20 premières secondes, basée sur le constat le plus parlant ;\n'
        '- "email_body" : le corps d\'un e-mail de suite après un appel téléphonique positif (sans signature, vouvoiement, 120 mots maximum, termine par une proposition de rendez-vous de 20 minutes).'
    )


async def enhance_report_with_language_model(prospect: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Rewrite the summary, hook and email with the local model when it is available."""
    if not await ollama_service.is_available():
        return report
    settings = load_settings()
    try:
        generated_content = await ollama_service.generate_json(SYSTEM_PROMPT, build_user_prompt(prospect, report))
    except (httpx.HTTPError, ValueError, KeyError) as error:
        logger.warning("Language model generation failed for %s : %s", prospect["name"], error)
        return report
    if isinstance(generated_content.get("summary"), str) and generated_content["summary"].strip():
        report["summary"] = generated_content["summary"].strip()
    if isinstance(generated_content.get("call_hook"), str) and generated_content["call_hook"].strip():
        report["call_script"][1]["lines"].insert(0, generated_content["call_hook"].strip())
    if isinstance(generated_content.get("email_body"), str) and generated_content["email_body"].strip():
        report["email"]["body"] = f"{generated_content['email_body'].strip()}\n\nBien cordialement,\n{build_signature(settings)}"
    report["generator"] = f"llm:{settings['llm_model']}"
    return report
