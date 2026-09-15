"""
Enterprise Retail Discovery Analyzer
Uses the google-genai SDK with gemini-2.5-flash and structured outputs
(response_schema=DiscoveryDossier) utilizing the B.R.I.E.F. prompt framework
specialized in detecting retail ERP, POS, and omnichannel inventory pain points.
"""

import os
import json
import time
import random
import logging
from typing import Optional, List, Dict, Any

# Inject native OS certificate store (Windows/macOS) to resolve SSL verification issues
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from google import genai
from google.genai import types


from models import (
    DiscoveryDossier,
    TechStackIndicators,
    ExecutivePainPoints,
    DiscoveryQuestions,
)

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_INSTRUCTION = """
You are a Principal Solutions Engineer and Enterprise Retail Architect specializing in modern retail enterprise systems, including Tier-1 Retail ERP, modern Point of Sale (POS), Distributed Order Management (DOM), and Unified Commerce architectures.

Analyze the provided retailer domain, scraped website content, detected technology stack indicators, company About Us intelligence, executive leadership profiles, corporate press releases, and CRM context using the B.R.I.E.F. Framework:

1. B - BASELINE & EXECUTIVE SUMMARY FORMULA:
   - Identify the retailer's commercial identity, market tier, retail segment, and estimated business scale (store count, employee headcount, revenue bracket).
   - Synthesize an authoritative 2-3 paragraph Executive Summary strictly following this 3-part formula:
     * Paragraph 1 (Heritage, Mission & Operational Scale): Ground in the provided About Us intelligence (founding context, brand heritage, core mission, physical store footprint, and retail operating model).
     * Paragraph 2 (Strategic Trajectory, Hard Numbers & Initiatives): Directly cite recent quarterly/annual results, financial metrics, DTC growth rates, or logistics/store fulfillment rollouts extracted from Corporate Press Releases and earnings announcements.
     * Paragraph 3 (Architectural Urgency & Named Leadership Mandate): Bridge the identified technology stack compromises (e.g., monolithic legacy ERP, batch POS sync latency, disconnected OMS) to the explicit operational remit of named executives from the Leadership Notes (e.g., CIO, VP of Merchandising, VP of Supply Chain), articulating why enterprise modernization is an immediate pre-sales priority.

2. R - RETAIL GAPS (ERP, POS, OMS, Inventory):
   - Scrutinize the technical footprint and public signals for common enterprise friction points:
     * In-store POS to Central ERP data latency (nightly batch processing vs real-time event streaming).
     * Unified Inventory Visibility & Available-to-Promise (ATP) inaccuracies across physical stores and digital channels.
     * Omnichannel fulfillment friction: BOPIS (Buy Online, Pick Up In Store) cancellation rates, curbside friction, inefficient Ship-from-Store routing.
     * Merchandising Allocation & Margin Erosion: Regional assortment misalignments causing heavy clearance markdowns and expensive inter-store transfer freight.
     * Store associate enablement: Associates lacking real-time cross-store stock lookups, causing lost sales.

3. I - IMPACT (The Value Triangle):
   - For every executive pain point, you MUST strictly structure your analysis using the Value Triangle:
     * Technical Gap: The architectural bottleneck or legacy monolithic limitation.
     * Operational Friction: The day-to-day pain for store associates, merchandisers, supply chain, and shoppers.
     * Financial Impact: Quantifiable business loss (e.g., "$25M-$100M in margin erosion from emergency clearance markdowns", "15% BOPIS cancellation rate", "$50M in avoidable inter-store freight").
     * Affected Executives: List specific titles (e.g., "VP of Merchandising", "CIO", "Head of Store Operations").

4. E - ENGAGEMENT QUESTIONS:
   - Provide persona-specific discovery questions tailored for pre-sales conversations with:
     * Chief Information Officer (CIO) / Enterprise Architect
     * VP of Merchandising & Inventory Planning
     * VP / Head of Retail Operations & Store Experience
     * VP of Supply Chain & Omnichannel Logistics
   - For each question:
     * State the open-ended discovery question.
     * Explain "What to listen for" (keywords, operational admissions, or architectural compromises).
     * Detail the "Value Wedge" (how modern real-time composable solutions defeat legacy monolithic suites like Oracle Retail, SAP S/4HANA, or legacy Aptos/NCR).

5. F - FORWARD STRATEGY:
   - Deliver clear, actionable discovery guidance for the Account Executive (AE) and Solution Engineer (SE).
   - Recommend the initial entry persona, the highest-probability demo wedge, and proof-of-concept focus.

Strictly adhere to the output schema. Output valid structured JSON matching the DiscoveryDossier schema.
"""


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
    # Truncate markdown to ~25,000 characters if exceptionally large to preserve token focus
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
    model_name: str = "gemini-2.5-flash",
    disable_ssl_verify: bool = False,
) -> DiscoveryDossier:
    """
    Executes the Gemini 2.5 Flash B.R.I.E.F. analysis pipeline with structured output.
    Returns a validated DiscoveryDossier instance.
    """
    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "Gemini API key is required. Please set the GEMINI_API_KEY environment variable "
            "or pass api_key directly."
        )

    signals = tech_signals or []
    
    http_opts = None
    if disable_ssl_verify:
        http_opts = types.HttpOptions(client_args={"verify": False})

    client = genai.Client(api_key=resolved_api_key, http_options=http_opts)

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

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=DiscoveryDossier,
        temperature=0.2,
        system_instruction=BRIEF_SYSTEM_INSTRUCTION,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    max_retries = 3
    base_delay = 2.0
    active_client = client
    response = None

    for attempt in range(max_retries + 1):
        try:
            response = active_client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=config,
            )
            break
        except Exception as e:
            err_msg = str(e).lower()

            # Handle SSL certificate verification failure
            if ("certificate_verify_failed" in err_msg or "certificate verify failed" in err_msg or "ssl" in err_msg) and not disable_ssl_verify:
                logger.warning(f"SSL certificate verification failed ({e}). Retrying with SSL verification bypass...")
                fallback_opts = types.HttpOptions(client_args={"verify": False})
                active_client = genai.Client(api_key=resolved_api_key, http_options=fallback_opts)
                continue

            # Check for Rate Limit (429, RESOURCE_EXHAUSTED) or Temporary Unavailable (503)
            is_rate_limit = ("429" in err_msg or "resource_exhausted" in err_msg or "rate limit" in err_msg or "quota" in err_msg)
            is_transient = ("503" in err_msg or "unavailable" in err_msg or "overloaded" in err_msg)

            if (is_rate_limit or is_transient) and attempt < max_retries:
                backoff_delay = (base_delay * (2 ** attempt)) + random.uniform(0.1, 0.5)
                reason = "Rate limit / quota exceeded (429)" if is_rate_limit else "Service temporarily unavailable (503)"
                logger.warning(
                    f"{reason} on attempt {attempt + 1}/{max_retries + 1}. Backing off for {backoff_delay:.2f}s before retry..."
                )
                time.sleep(backoff_delay)
                continue

            logger.error(f"Gemini generation failed after {attempt + 1} attempts: {e}")
            raise

    # Validate and deserialize response into DiscoveryDossier
    dossier = None
    if hasattr(response, "parsed") and isinstance(response.parsed, DiscoveryDossier):
        dossier = response.parsed
    elif hasattr(response, "parsed") and isinstance(response.parsed, dict):
        dossier = DiscoveryDossier.model_validate(response.parsed)
    elif response.text:
        dossier = DiscoveryDossier.model_validate_json(response.text)
    else:
        raise RuntimeError("Gemini returned an empty response with no parsed object or text.")

    if corporate_url and not dossier.corporate_domain:
        dossier.corporate_domain = corporate_url

    return dossier

