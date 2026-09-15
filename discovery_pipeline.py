"""
Automated Pre-Discovery Pipeline: Structured Intelligence Extraction
Role: Senior Solutions Engineer

This module connects to Google Gemini 2.5 Flash using the official `google-genai` SDK.
It enforces structured JSON output mapped directly to Pydantic v2 schemas (`PainPoint` 
and `DiscoveryBrief`), transforming messy, unstructured discovery transcripts and prospect
notes into validated, actionable sales engineering intelligence.
"""

import os
import sys
import json
import time
import random
import logging
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ValidationError

# Inject native OS certificate store (Windows/macOS) to resolve SSL verification issues in corporate environments
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from google import genai
from google.genai import types
from google.genai.errors import APIError

# Configure structured logging for production observability
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PreDiscoveryPipeline")


# =====================================================================
# Step 1 & 2: Pydantic Schema Definitions (Pre-Sales Domain Models)
# =====================================================================

class PainPoint(BaseModel):
    """
    Granular prospect pain point capturing the friction point, classification,
    and business/operational consequences.
    """
    category: Literal["Technical", "Business"] = Field(
        ...,
        description=(
            "Categorization of the friction: 'Technical' indicates architectural debt, "
            "legacy tech, API latency, batch processing, or data sync limits; 'Business' "
            "indicates margin degradation, customer churn, executive risk, or staff inefficiency."
        )
    )
    description: str = Field(
        ...,
        description=(
            "Precise, objective description of the challenge or operational hurdle described by the prospect."
        )
    )
    impact: str = Field(
        ...,
        description=(
            "Quantifiable or strategic business impact (e.g., lost revenue, SLA penalties, "
            "customer dissatisfaction, high manual hours, conversion drop-off)."
        )
    )


class DiscoveryBrief(BaseModel):
    """
    Parent discovery document aggregating all synthesized pain points from prospect notes.
    """
    pain_points: List[PainPoint] = Field(
        ...,
        description="Comprehensive collection of all technical and business pain points extracted from the text."
    )


# =====================================================================
# Step 3 & 4: Client & Generation Configuration Setup
# =====================================================================

def create_discovery_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Initializes and returns the official Google GenAI client.
    
    Args:
        api_key: Optional Gemini API key. Defaults to GEMINI_API_KEY environment variable.
        
    Returns:
        genai.Client: Configured client instance.
    """
    effective_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not effective_key:
        logger.warning(
            "GEMINI_API_KEY is not set in the environment or passed directly. "
            "The client may fail unless running with Application Default Credentials (ADC)."
        )
    return genai.Client(api_key=effective_key)


def get_discovery_generation_config() -> types.GenerateContentConfig:
    """
    Configures generation parameters for deterministic structured data extraction.
    Enforces response_mime_type='application/json' and supplies the Pydantic schema
    to `response_schema` using the B.R.I.E.F. prompt framework.
    """
    brief_system_instruction = (
        "You are an expert Senior Solutions Engineer conducting technical pre-discovery using the B.R.I.E.F. prompt framework:\n\n"
        "1. B - BACKGROUND & CONTEXT:\n"
        "   Ground yourself as an Enterprise Retail Solutions Architect analyzing raw prospect call notes, transcripts, or architecture reviews.\n\n"
        "2. R - RETAIL GAPS & FRICTION:\n"
        "   Identify legacy monolithic systems, batch processing latencies, inventory sync gaps, and operational bottlenecks.\n\n"
        "3. I - IMPACT (VALUE TRIANGLE):\n"
        "   Connect every technical limitation (Technical Gap) to frontline business pain (Operational Friction) and financial or strategic consequences (Financial Impact).\n\n"
        "4. E - EVIDENCE & EXTRACTION:\n"
        "   Extract objective, grounded facts from the notes without hallucinating details not supported by prospect statements.\n\n"
        "5. F - FORMAT & CONSTRAINTS:\n"
        "   Output strictly valid JSON matching the DiscoveryBrief schema."
    )
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=DiscoveryBrief,
        temperature=0.1,  # Low temperature to minimize hallucinations and prioritize fidelity to notes
        system_instruction=brief_system_instruction,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


# =====================================================================
# Step 5: Core Extraction Function
# =====================================================================

def extract_discovery_brief(
    prospect_notes: str,
    client: Optional[genai.Client] = None
) -> Optional[DiscoveryBrief]:
    """
    Extracts structured pain points from unstructured prospect notes using Gemini 2.5 Flash.
    
    Args:
        prospect_notes: Raw discovery text (e.g., AE transcript, customer email, call notes).
        client: Optional pre-configured genai.Client.
        
    Returns:
        DiscoveryBrief: Validated Pydantic model containing extracted pain points, or None if failed.
    """
    if not prospect_notes or not prospect_notes.strip():
        logger.error("Input prospect notes are empty.")
        return None

    # Default to a new client instance if not provided
    active_client = client or create_discovery_client()
    config = get_discovery_generation_config()

    extraction_prompt = (
        "Extract all distinct technical and business pain points from the following "
        "prospect notes into the required schema:\n\n"
        f"--- PROSPECT NOTES ---\n{prospect_notes}\n----------------------"
    )

    try:
        logger.info("Sending unstructured notes to gemini-2.5-flash for structured extraction...")
        
        # Invoke the official google-genai SDK with rate limit backoff
        max_retries = 3
        base_delay = 2.0
        response = None

        for attempt in range(max_retries + 1):
            try:
                response = active_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=extraction_prompt,
                    config=config,
                )
                break
            except Exception as call_err:
                err_str = str(call_err).lower()
                
                # SSL Verification Fallback
                if "certificate_verify_failed" in err_str or "certificate verify failed" in err_str or "ssl" in err_str:
                    logger.warning("SSL verification failed (%s). Retrying with SSL verification bypass...", call_err)
                    fallback_opts = types.HttpOptions(client_args={"verify": False})
                    effective_key = os.environ.get("GEMINI_API_KEY")
                    active_client = genai.Client(api_key=effective_key, http_options=fallback_opts)
                    continue

                # Rate Limit (429 / RESOURCE_EXHAUSTED) & 503 Transient Handling
                is_rate_limit = ("429" in err_str or "resource_exhausted" in err_str or "rate limit" in err_str or "quota" in err_str)
                is_transient = ("503" in err_str or "unavailable" in err_str or "overloaded" in err_str)

                if (is_rate_limit or is_transient) and attempt < max_retries:
                    backoff_delay = (base_delay * (2 ** attempt)) + random.uniform(0.1, 0.5)
                    reason = "Rate limit / quota exceeded (429)" if is_rate_limit else "Service temporarily unavailable (503)"
                    logger.warning(
                        f"{reason} on attempt {attempt + 1}/{max_retries + 1}. Backing off for {backoff_delay:.2f}s before retry..."
                    )
                    time.sleep(backoff_delay)
                    continue

                raise

        raw_json_str = response.text
        logger.debug("Received raw response from Gemini: %s", raw_json_str)

        # Validate against the Pydantic schema
        validated_brief = DiscoveryBrief.model_validate_json(raw_json_str)
        logger.info(
            "Successfully extracted and validated %d pain points.",
            len(validated_brief.pain_points)
        )
        return validated_brief

    except APIError as api_err:
        logger.error("Gemini API call failed with an upstream error: %s", api_err)
        return None
    except ValidationError as val_err:
        logger.error("Pydantic schema validation failed on model output: %s", val_err)
        return None
    except Exception as exc:
        logger.error("An unexpected error occurred during discovery brief extraction: %s", exc)
        return None


# =====================================================================
# Execution & Demonstration Routine
# =====================================================================

if __name__ == "__main__":
    # Sample real-world unstructured sales discovery notes
    sample_prospect_notes = """
    Met with Acme Retail's VP of E-Commerce and VP of Supply Chain:
    - Current core ERP is on an on-prem SAP ECC 6.0 instance, syncs inventory to Salesforce Commerce Cloud (SFCC) 
      via nightly batch FTP.
    - Result: Over 12% of BOPIS (Buy Online Pick Up In Store) orders get cancelled because physical stores sell the 
      inventory before the digital storefront updates, costing ~$4.2M in refunded GMV last year.
    - In-store POS terminals run on a 15-year-old legacy client that crashes when associates attempt multi-tender 
      returns or cross-store stock lookups.
    - Store associates are forced to call neighboring stores on the phone to verify stock, dragging average customer 
      checkout times from 90 seconds to over 4 minutes, causing long holiday lines and walkouts.
    - Cloud migration project is currently 6 months behind schedule because their internal engineering team lacks 
      event-driven architectural patterns (Kafka/PubSub) expertise.
    """

    print("=" * 80)
    print("AUTOMATED PRE-DISCOVERY PIPELINE: EXTRACTION RUN")
    print("=" * 80)
    
    # Run pipeline
    brief = extract_discovery_brief(sample_prospect_notes)

    if brief:
        # Output formatted JSON representation
        formatted_json = brief.model_dump_json(indent=2)
        print("\nExtracted & Validated DiscoveryBrief (JSON):")
        print(formatted_json)
        
        # Summary for the Solutions Engineering team
        print("\nExecutive Summary for Account Team:")
        for idx, pt in enumerate(brief.pain_points, 1):
            print(f"  {idx}. [{pt.category.upper()}] {pt.description}")
            print(f"     -> Impact: {pt.impact}")
    else:
        print("\n[!] Extraction failed. Check log outputs above.")
        sys.exit(1)
