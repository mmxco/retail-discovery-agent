"""
Legacy Retail ERP & Inventory Synchronization Extraction Module
Role: Senior AI Solutions Architect & Retail ERP Subject Matter Expert

Extracts deterministic legacy retail ERP pain points (Epicor on-premise,
AS400/IBM iSeries, and multi-channel inventory synchronization bottlenecks)
from unstructured prospect data using the shared Gemini client service.
"""

import os
from typing import Optional

from core.config import get_logger, LEGACY_ERP_SYSTEM_INSTRUCTION, DEFAULT_MODEL_NAME
from core.models import (
    LegacyDomainCategory,
    TargetSystemDetection,
    LegacyERPPainPointItem,
    LegacyERPPainPoints,
    NoLegacyERPPainPointsFoundError,
)
from core.gemini import generate_structured_output

logger = get_logger("legacy_erp_extractor")

__all__ = [
    "LegacyDomainCategory",
    "TargetSystemDetection",
    "LegacyERPPainPointItem",
    "LegacyERPPainPoints",
    "NoLegacyERPPainPointsFoundError",
    "LEGACY_ERP_SYSTEM_INSTRUCTION",
    "extract_legacy_erp_pain_points",
]


def extract_legacy_erp_pain_points(
    payload_text: str,
    api_key: Optional[str] = None,
    model_name: str = DEFAULT_MODEL_NAME,
    raise_if_empty: bool = False,
    disable_ssl_verify: bool = False,
) -> LegacyERPPainPoints:
    """
    Extracts legacy ERP and inventory sync bottlenecks from unstructured prospect text
    via the centralized core.gemini service.

    Args:
        payload_text: Raw prospect text (transcripts, 10-Ks, scraper notes).
        api_key: Optional Google Gemini API key. Defaults to GEMINI_API_KEY environment variable.
        model_name: Target Gemini model identifier (default: "gemini-2.5-flash").
        raise_if_empty: If True, raises NoLegacyERPPainPointsFoundError when no bottlenecks are found.
        disable_ssl_verify: If True, bypasses SSL certificate verification.

    Returns:
        LegacyERPPainPoints: Validated Pydantic model containing structured findings.

    Raises:
        ValueError: If API key is missing or payload text is empty.
        NoLegacyERPPainPointsFoundError: If raise_if_empty is True and no pain points/systems are detected.
    """
    if not payload_text or not payload_text.strip():
        raise ValueError("Input payload_text cannot be empty.")

    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "Gemini API key is required. Set GEMINI_API_KEY environment variable or pass api_key."
        )

    user_prompt = f"""
Analyze the following enterprise retail payload for targeted legacy ERP and inventory synchronization pain points:

--- BEGIN PROSPECT PAYLOAD ---
{payload_text.strip()}
--- END PROSPECT PAYLOAD ---
"""

    logger.info(f"Submitting payload ({len(payload_text)} chars) to {model_name} with structured output...")

    result = generate_structured_output(
        prompt=user_prompt,
        response_schema=LegacyERPPainPoints,
        system_instruction=LEGACY_ERP_SYSTEM_INSTRUCTION,
        model_name=model_name,
        api_key=resolved_api_key,
        disable_ssl_verify=disable_ssl_verify,
        temperature=0.0,
    )

    if raise_if_empty and (not result.has_legacy_systems or len(result.pain_points) == 0):
        logger.info("Zero legacy pain points detected with raise_if_empty=True. Raising NoLegacyERPPainPointsFoundError.")
        raise NoLegacyERPPainPointsFoundError(
            f"Extraction completed but yielded no pain points: {result.extraction_summary}"
        )

    return result
