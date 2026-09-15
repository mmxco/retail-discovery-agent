"""
Automated Pre-Discovery Pipeline: Structured Intelligence Extraction
Role: Senior Solutions Engineer

Uses the shared Gemini client service to extract structured pain points
mapped to Pydantic v2 schemas (PainPoint and DiscoveryBrief).
"""

import os
from typing import Optional, List

from core.config import get_logger, PRE_DISCOVERY_SYSTEM_INSTRUCTION, DEFAULT_MODEL_NAME
from core.models import PainPoint, DiscoveryBrief
from core.gemini import generate_structured_output, create_gemini_client

logger = get_logger("discovery_pipeline")

__all__ = [
    "PainPoint",
    "DiscoveryBrief",
    "extract_discovery_brief",
    "extract_pain_points",
    "create_discovery_client",
]


def create_discovery_client(api_key: Optional[str] = None):
    """Initializes and returns a GenAI client using the shared service."""
    return create_gemini_client(api_key=api_key)


def extract_discovery_brief(
    prospect_notes: str,
    client: Optional[object] = None,
    api_key: Optional[str] = None,
    model_name: str = DEFAULT_MODEL_NAME,
) -> Optional[DiscoveryBrief]:
    """
    Extracts structured pain points from unstructured prospect notes using Gemini.

    Args:
        prospect_notes: Raw discovery text.
        client: Optional pre-configured client.
        api_key: Optional API key.
        model_name: Gemini model name.

    Returns:
        DiscoveryBrief instance, or None if extraction fails or input is empty.
    """
    if not prospect_notes or not prospect_notes.strip():
        logger.error("Input prospect notes are empty.")
        return None

    extraction_prompt = (
        "Extract all distinct technical and business pain points from the following "
        "prospect notes into the required schema:\n\n"
        f"--- PROSPECT NOTES ---\n{prospect_notes.strip()}\n----------------------"
    )

    try:
        logger.info(f"Sending unstructured notes to {model_name} for structured extraction...")
        brief = generate_structured_output(
            prompt=extraction_prompt,
            response_schema=DiscoveryBrief,
            system_instruction=PRE_DISCOVERY_SYSTEM_INSTRUCTION,
            model_name=model_name,
            api_key=api_key,
            temperature=0.1,
            client=client,
        )
        return brief
    except Exception as exc:
        logger.error(f"Error during discovery brief extraction: {exc}")
        return None


def extract_pain_points(
    prospect_notes: str,
    client: Optional[object] = None,
    api_key: Optional[str] = None,
    model_name: str = DEFAULT_MODEL_NAME,
) -> DiscoveryBrief:
    """
    Direct extraction helper matching test_extraction.py interface.
    Returns a DiscoveryBrief directly.
    """
    brief = extract_discovery_brief(
        prospect_notes=prospect_notes,
        client=client,
        api_key=api_key,
        model_name=model_name,
    )
    if brief is None:
        return DiscoveryBrief(pain_points=[])
    return brief
