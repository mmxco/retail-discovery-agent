"""
Enterprise Retail Discovery Analyzer
Uses the centralized Gemini client service with gemini-2.5-flash and structured outputs
(response_schema=DiscoveryDossier) utilizing the B.R.I.E.F. prompt framework
specialized in detecting retail ERP, POS, and omnichannel inventory pain points.
"""

import os
import json
from typing import Optional, List, Dict, Any

from core.config import get_logger, BRIEF_SYSTEM_INSTRUCTION, DEFAULT_MODEL_NAME
from core.models import (
    DiscoveryDossier,
    TechStackIndicators,
    ExecutivePainPoints,
    DiscoveryQuestions,
)
from core.gemini import generate_structured_output

logger = get_logger("analyzer")


def build_analysis_prompt(
    account_name: str,
    domain: str,
    scraped_markdown: str,
    tech_signals: List[str],
    bdr_notes: Optional[str] = "",
    annual_revenue: Optional[str] = "",
    headcount: Optional[str] = "",
    careers_content: Optional[str] = "",
    about_us_content: Optional[Dict[str, Any]] = None,
    leadership_content: Optional[Dict[str, Any]] = None,
    press_releases: Optional[List[Dict[str, str]]] = None,
    corporate_url: Optional[str] = "",
) -> str:
    """Constructs the comprehensive prompt payload for Gemini 2.5 Flash."""
    truncated_markdown = scraped_markdown[:30000] if scraped_markdown else "No scraped markdown available."
    truncated_careers = careers_content[:15000] if careers_content else ""

    payload = {
        "target_account": {
            "account_name": account_name or "Retail Prospect",
            "domain": domain,
            "corporate_website": corporate_url or "Not provided (same as retail domain)",
            "annual_revenue": annual_revenue or "Undisclosed / Publicly traded estimate",
            "headcount": headcount or "Undisclosed",
        },
        "preliminary_crm_bdr_notes": bdr_notes or "No BDR notes provided.",
        "detected_technology_signals": tech_signals,
        "scraped_storefront_markdown": truncated_markdown,
    }

    if about_us_content and (about_us_content.get("markdown_text") or about_us_content.get("key_facts")):
        payload["company_about_us_intelligence"] = {
            "source_url": about_us_content.get("source_url", ""),
            "key_facts_and_milestones": about_us_content.get("key_facts", []),
            "narrative_markdown": (about_us_content.get("markdown_text", "")[:10000]),
        }

    if leadership_content and leadership_content.get("markdown_text"):
        payload["executive_leadership_profiles"] = {
            "source_url": leadership_content.get("source_url", ""),
            "profiles_markdown": leadership_content.get("markdown_text", "")[:10000],
        }

    if press_releases:
        payload["corporate_press_releases_and_earnings"] = press_releases[:5]

    if truncated_careers:
        payload["careers_job_postings_signals"] = truncated_careers

    return (
        "Please conduct a comprehensive Pre-Sales Discovery Analysis for the following retail prospect "
        "and generate a fully populated DiscoveryDossier:\n\n"
        f"{json.dumps(payload, indent=2)}"
    )


def analyze_retail_prospect(
    account_name: str,
    domain: str,
    scraped_markdown: str,
    tech_signals: Optional[List[str]] = None,
    bdr_notes: Optional[str] = "",
    annual_revenue: Optional[str] = "",
    headcount: Optional[str] = "",
    careers_content: Optional[str] = "",
    about_us_content: Optional[Dict[str, Any]] = None,
    leadership_content: Optional[Dict[str, Any]] = None,
    press_releases: Optional[List[Dict[str, str]]] = None,
    corporate_url: Optional[str] = "",
    api_key: Optional[str] = None,
    model_name: str = DEFAULT_MODEL_NAME,
    disable_ssl_verify: bool = False,
) -> DiscoveryDossier:
    """
    Executes the Gemini 2.5 Flash B.R.I.E.F. analysis pipeline with structured output
    via the shared core.gemini client service.
    Returns a validated DiscoveryDossier instance.
    """
    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "Gemini API key is required. Please set the GEMINI_API_KEY environment variable "
            "or pass api_key directly."
        )

    signals = tech_signals or []
    user_prompt = build_analysis_prompt(
        account_name=account_name,
        domain=domain,
        scraped_markdown=scraped_markdown,
        tech_signals=signals,
        bdr_notes=bdr_notes,
        annual_revenue=annual_revenue,
        headcount=headcount,
        careers_content=careers_content,
        about_us_content=about_us_content,
        leadership_content=leadership_content,
        press_releases=press_releases,
        corporate_url=corporate_url,
    )

    logger.info(f"Invoking {model_name} with structured output for {account_name or domain}...")

    dossier = generate_structured_output(
        prompt=user_prompt,
        response_schema=DiscoveryDossier,
        system_instruction=BRIEF_SYSTEM_INSTRUCTION,
        model_name=model_name,
        api_key=resolved_api_key,
        disable_ssl_verify=disable_ssl_verify,
        temperature=0.2,
    )

    if corporate_url and not dossier.corporate_domain:
        dossier.corporate_domain = corporate_url

    return dossier
