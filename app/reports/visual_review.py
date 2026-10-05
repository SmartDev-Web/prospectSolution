"""Optional visual judgement of a homepage screenshot by a local vision model."""
import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import SCREENSHOT_DIRECTORY
from app.llm.ollama import ollama_service
from app.settings_service import load_settings

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = (
    "Tu es directeur artistique web. Tu juges l'apparence d'une page d'accueil de petite entreprise à partir d'une capture d'écran. "
    "Tu réponds uniquement avec un objet JSON valide."
)
USER_PROMPT = (
    "Note la modernité du design de cette page d'accueil de 1 (très daté, style années 2000) à 10 (design actuel et professionnel). "
    "Critères : mise en page, typographie, qualité des visuels, espacement, cohérence des couleurs. "
    'Réponds en JSON avec les clés "design_score" (entier de 1 à 10), "era" (ex. "années 2000", "années 2010", "actuel") '
    'et "verdict" (une phrase en français, 20 mots maximum, qui cite les éléments visuels datés ou réussis).'
)


async def assess_screenshot(screenshot_file_name: str | None) -> dict[str, Any] | None:
    """Return the vision model's opinion on the design, or None when no vision model is configured."""
    vision_model = load_settings()["llm_vision_model"]
    if not vision_model or not screenshot_file_name or not await ollama_service.is_available():
        return None
    screenshot_path = Path(SCREENSHOT_DIRECTORY) / screenshot_file_name
    if not screenshot_path.exists():
        return None
    image_base64 = base64.b64encode(screenshot_path.read_bytes()).decode("ascii")
    try:
        assessment = await ollama_service.generate_json(SYSTEM_PROMPT, USER_PROMPT, vision_model, [image_base64])
    except (httpx.HTTPError, ValueError, KeyError) as error:
        logger.warning("Visual assessment failed for %s : %s", screenshot_file_name, error)
        return None
    design_score = assessment.get("design_score")
    if isinstance(design_score, str) and design_score.strip().isdigit():
        assessment["design_score"] = int(design_score.strip())
    return assessment if isinstance(assessment.get("design_score"), (int, float)) else None
