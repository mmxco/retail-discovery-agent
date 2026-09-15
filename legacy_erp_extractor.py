"""
Legacy Retail ERP & Inventory Synchronization Extraction Module
Role: Senior AI Solutions Architect & Retail ERP Subject Matter Expert

Extracts deterministic legacy retail ERP pain points (Epicor on-premise,
AS400/IBM iSeries, and multi-channel inventory synchronization bottlenecks)
from unstructured prospect data using the google-genai SDK and structured outputs.
"""

import os
import json
import logging
from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, ValidationError

# Inject native OS certificate store (Windows/macOS) to resolve SSL verification issues
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from google import genai
from google.genai import types
from google.genai.errors import APIError

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("LegacyERPExtractor")


# ==============================================================================
# EXCEPTIONS
# ==============================================================================
class NoLegacyERPPainPointsFoundError(Exception):
    """Raised when strict extraction mode is active and no legacy ERP pain points are detected."""
    def __init__(self, message: str = "No target legacy ERP systems or pain points identified in payload."):
        super().__init__(message)


# ==============================================================================
# PYDANTIC SCHEMAS (STRUCTURED DATA CONTRACTS)
# ==============================================================================
class LegacyDomainCategory(str, Enum):
    """Target architectural domains constrained to specific legacy retail bottlenecks."""
    EPICOR_ON_PREMISE = "EPICOR_ON_PREMISE"
    AS400_ISERIES = "AS400_ISERIES"
    MULTI_CHANNEL_INVENTORY_SYNC = "MULTI_CHANNEL_INVENTORY_SYNC"


class TargetSystemDetection(BaseModel):
    """Detected legacy system signature identified within the source text."""
    model_config = ConfigDict(extra="ignore")

    domain: LegacyDomainCategory = Field(
        ...,
        description="Target domain category (EPICOR_ON_PREMISE, AS400_ISERIES, or MULTI_CHANNEL_INVENTORY_SYNC)."
    )
    detected_system_name: str = Field(
        ...,
        description="Specific system identifier identified in text (e.g., 'Epicor 9', 'Epicor Vantage', 'IBM AS/400', 'iSeries RPG', 'Custom FTP Inventory Batch')."
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        ...,
        description="Confidence score based on direct explicit mention ('HIGH') vs contextual inference ('MEDIUM'/'LOW')."
    )
    evidence_quote: str = Field(
        ...,
        description="Exact verbatim excerpt from the source text verifying the presence of this legacy footprint."
    )


class LegacyERPPainPointItem(BaseModel):
    """
    Granular, evidence-grounded pain point mapped directly to source text.
    Strictly restricted to Epicor on-premise, AS400/iSeries, or inventory synchronization bottlenecks.
    """
    model_config = ConfigDict(extra="ignore")

    target_domain: LegacyDomainCategory = Field(
        ...,
        description="The specific target domain of the identified bottleneck."
    )
    specific_system: str = Field(
        ...,
        description="The specific legacy software, hardware, or integration layer involved (e.g., 'Epicor Progress OpenEdge DB', 'AS400 RPG Batch Job', 'Nightly POS-to-Web Inventory Sync')."
    )
    verbatim_evidence: str = Field(
        ...,
        description="Direct, word-for-word quote from the source text confirming the technical or operational bottleneck. Must not be paraphrased or fabricated."
    )
    technical_bottleneck: str = Field(
        ...,
        description="Architectural root cause (e.g., monolithic batch processing, lack of REST/JSON endpoints, table locks during ODBC queries, 5250 terminal limitations, 4-hour batch sync latency)."
    )
    operational_friction: str = Field(
        ...,
        description="Day-to-day workflow consequence (e.g., store associates unable to see warehouse ATP, cancelled BOPIS orders, phantom inventory on digital storefront, manual CSV exports)."
    )
    financial_impact: str = Field(
        ...,
        description="Quantified monetary loss, margin erosion, or quantifiable business exposure (e.g., 18% order cancellation rate, $2M inventory buffer write-offs, 20 hours/week manual reconciliation)."
    )
    affected_stakeholders: List[str] = Field(
        default_factory=list,
        description="Executive and operational roles impacted (e.g., 'VP of Supply Chain', 'Chief Information Officer', 'Director of Store Operations', 'E-Commerce Merchandiser')."
    )


class LegacyERPPainPoints(BaseModel):
    """
    Parent extraction payload containing all identified legacy retail ERP constraints.
    Enforces deterministic representation of both positive detections and negative/empty cases.
    """
    model_config = ConfigDict(extra="ignore")

    has_legacy_systems: bool = Field(
        ...,
        description="Boolean flag indicating whether any targeted legacy systems (Epicor, AS400, or inventory sync bottlenecks) were detected."
    )
    detected_systems: List[TargetSystemDetection] = Field(
        default_factory=list,
        description="List of detected legacy systems with confidence ratings and verbatim textual evidence."
    )
    pain_points: List[LegacyERPPainPointItem] = Field(
        default_factory=list,
        description="Evidence-grounded legacy bottlenecks extracted strictly from the input payload. Empty if none detected."
    )
    extraction_summary: str = Field(
        ...,
        description="Factual, objective summary of the extraction findings. If no target legacy systems exist, must explicitly state: 'No targeted legacy ERP systems (Epicor, AS400) or multi-channel inventory sync bottlenecks detected.'"
    )


# ==============================================================================
# SYSTEM INSTRUCTION & GROUNDING PROMPT
# ==============================================================================
LEGACY_ERP_SYSTEM_INSTRUCTION = """
You are a Principal Solutions Architect and Retail ERP Modernization SME.
Your sole mission is to extract deterministic architectural bottlenecks and business pain points from unstructured retail prospect text (e.g., discovery call notes, RFP transcripts, 10-K filings, architecture reviews).

TARGET SCOPE RESTRICTIONS:
You must STRICTLY restrict your analysis and extraction to these three categories:
1. EPICOR_ON_PREMISE:
   - On-premise Epicor deployments (e.g., Epicor Vantage, Vista, Enterprise, Prophet 21 on-prem, Epicor 9/10 client-server).
   - Architectural constraints: Progress OpenEdge database lockups, thick-client latency, ODBC reporting freezes, custom 4GL extensions blocking upgrades, brittle direct database integrations.
2. AS400_ISERIES:
   - IBM AS/400, iSeries, System i architectures.
   - Architectural constraints: Green-screen 5250 emulators, RPG/COBOL custom logic, DB2/400 flat-file batch extractions, lack of modern REST/JSON microservices, SNA/terminal drops, retiring internal workforce skill sets.
3. MULTI_CHANNEL_INVENTORY_SYNC:
   - Multi-channel inventory synchronization bottlenecks between central ERP/merchandising and selling channels (e-commerce, physical POS, marketplace).
   - Architectural constraints: Nightly or hourly batch feeds, phantom inventory, high safety buffer stock, cancelled Buy-Online-Pick-Up-In-Store (BOPIS) orders, store associates blind to cross-channel Available-To-Promise (ATP) inventory.

STRICT GROUNDING & ANTI-HALLUCINATION RULES:
1. VERBATIM EVIDENCE MANDATE: For every item extracted, the `verbatim_evidence` and `evidence_quote` fields MUST contain an exact, word-for-word excerpt from the source text. NEVER paraphrase, summarize, or fabricate quotes. If you cannot quote direct text evidence, DO NOT extract the pain point.
2. NO SPECULATIVE EXTRAPOLATION: If the prospect text merely mentions having an "AS400" or "Epicor" system without mentioning operational pain, document it in `detected_systems` with appropriate confidence, but LEAVE `pain_points` EMPTY for that system. Do NOT fabricate or assume pain points that are not explicitly evidenced.
3. NEGATIVE CONSTRAINT (UNMATCHED PAYLOADS): If the input text contains NO mentions of Epicor on-premise, AS400/iSeries, or multi-channel inventory synchronization bottlenecks, you MUST return:
   - `has_legacy_systems`: false
   - `detected_systems`: []
   - `pain_points`: []
   - `extraction_summary`: "No targeted legacy ERP systems (Epicor, AS400) or multi-channel inventory sync bottlenecks detected."
4. EXCLUDE UNRELATED ENTERPRISE SYSTEMS: Do not extract pain points related to generic web marketing, modern cloud microservices, HR/payroll software, or modern SaaS ERPs (e.g., NetSuite SuiteCloud, Workday) unless they directly connect to an on-premise Epicor, AS400, or legacy inventory batch sync bottleneck.
"""


# ==============================================================================
# PIPELINE IMPLEMENTATION
# ==============================================================================
def extract_legacy_erp_pain_points(
    payload_text: str,
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
    raise_if_empty: bool = False,
    disable_ssl_verify: bool = False,
) -> LegacyERPPainPoints:
    """
    Extracts legacy ERP and inventory sync bottlenecks from unstructured prospect text.

    Args:
        payload_text: Raw prospect text (transcripts, 10-Ks, scraper notes).
        api_key: Optional Google Gemini API key. Defaults to GEMINI_API_KEY environment variable.
        model_name: Target Gemini model identifier (default: "gemini-2.5-flash", or "gemini-2.5-pro").
        raise_if_empty: If True, raises NoLegacyERPPainPointsFoundError when no bottlenecks are found.
        disable_ssl_verify: If True, bypasses SSL certificate verification for corporate proxies.

    Returns:
        LegacyERPPainPoints: Validated Pydantic model containing structured findings.

    Raises:
        ValueError: If API key is missing or payload text is empty.
        NoLegacyERPPainPointsFoundError: If raise_if_empty is True and no pain points/systems are detected.
        APIError: If the Gemini API returns an unhandled upstream error.
    """
    if not payload_text or not payload_text.strip():
        raise ValueError("Input payload_text cannot be empty.")

    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "Gemini API key is required. Set GEMINI_API_KEY environment variable or pass api_key."
        )

    http_opts = None
    if disable_ssl_verify:
        http_opts = types.HttpOptions(client_args={"verify": False})

    client = genai.Client(api_key=resolved_api_key, http_options=http_opts)

    # Enforce deterministic extraction with temperature=0.0 and Pydantic response_schema
    config = types.GenerateContentConfig(
        system_instruction=LEGACY_ERP_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=LegacyERPPainPoints,
        temperature=0.0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    user_prompt = f"""
Analyze the following enterprise retail payload for targeted legacy ERP and inventory synchronization pain points:

--- BEGIN PROSPECT PAYLOAD ---
{payload_text.strip()}
--- END PROSPECT PAYLOAD ---
"""

    logger.info(f"Submitting payload ({len(payload_text)} chars) to {model_name} with structured output...")

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=config,
        )
    except Exception as e:
        err_msg = str(e).lower()
        if ("certificate_verify_failed" in err_msg or "ssl" in err_msg) and not disable_ssl_verify:
            logger.warning("SSL verification failed. Retrying with SSL verification bypass...")
            fallback_client = genai.Client(
                api_key=resolved_api_key,
                http_options=types.HttpOptions(client_args={"verify": False})
            )
            response = fallback_client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=config,
            )
        else:
            logger.error(f"Gemini API generation failed: {e}")
            raise

    # Parse and validate response against Pydantic schema
    result: Optional[LegacyERPPainPoints] = None
    if hasattr(response, "parsed") and isinstance(response.parsed, LegacyERPPainPoints):
        result = response.parsed
    elif hasattr(response, "parsed") and isinstance(response.parsed, dict):
        result = LegacyERPPainPoints.model_validate(response.parsed)
    elif response.text:
        try:
            result = LegacyERPPainPoints.model_validate_json(response.text)
        except ValidationError as ve:
            logger.error(f"Pydantic schema validation error: {ve}")
            raise
    else:
        raise RuntimeError("Gemini returned an empty response with no parsed object or text content.")

    # Apply strict error gating if requested by caller
    if raise_if_empty and (not result.has_legacy_systems or len(result.pain_points) == 0):
        logger.info("Zero legacy pain points detected with raise_if_empty=True. Raising NoLegacyERPPainPointsFoundError.")
        raise NoLegacyERPPainPointsFoundError(
            f"Extraction completed but yielded no pain points: {result.extraction_summary}"
        )

    return result


# ==============================================================================
# SAMPLE VERIFICATION & EXECUTION DEMO
# ==============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("DEMO 1: POSITIVE DETECTION - LEGACY ERP & INVENTORY SYNC BOTTLENECKS")
    print("=" * 80)

    sample_legacy_transcript = """
    Prospect: Mid-Atlantic Department Stores Inc.
    Participants: VP Supply Chain, Director of Retail Operations, Presales Architect
    
    Notes:
    The client operates 85 regional specialty stores and an e-commerce storefront.
    Their core inventory backbone is still hosted on an on-premise IBM AS/400 running custom RPG III 
    programs written in 1997. Because the AS/400 cannot expose REST APIs, store inventory updates 
    are exported via a nightly batch CSV file sent over SFTP at 2:00 AM to their web store.
    
    During peak holiday weekends, this batch lag causes severe multi-channel inventory synchronization 
    bottlenecks: the digital commerce platform sells items that were purchased in physical stores 4 hours 
    prior. The VP of Supply Chain reported: 'Our BOPIS cancellation rate spiked to 21% last December, 
    costing us over $1.8M in lost sales and customer concessions because store associates couldn't fulfill 
    orders for phantom stock.'
    
    Furthermore, their distribution centers run an aging on-premise Epicor 9 installation with Progress 
    OpenEdge. When the warehouse team runs large allocation queries via ODBC during picking shifts, the entire 
    database locks up, freezing warehouse RF scanners for up to 45 minutes and halting all truck dispatches.
    """

    sample_irrelevant_payload = """
    Acme Modern Apparel implemented Shopify Plus and Klaviyo marketing automation in Q2 2024. 
    They have 10 boutique showrooms with cloud-native POS running on iPads. Their customer NPS 
    is 78 and marketing click-through rates increased by 14% year-over-year.
    """

    api_key_env = os.environ.get("GEMINI_API_KEY")
    if not api_key_env:
        print("[INFO] GEMINI_API_KEY not found in environment. Demonstrating schema serialization.")
        mock_detection = LegacyERPPainPoints(
            has_legacy_systems=True,
            detected_systems=[
                TargetSystemDetection(
                    domain=LegacyDomainCategory.AS400_ISERIES,
                    detected_system_name="IBM AS/400 (RPG III)",
                    confidence="HIGH",
                    evidence_quote="Their core inventory backbone is still hosted on an on-premise IBM AS/400 running custom RPG III programs"
                )
            ],
            pain_points=[
                LegacyERPPainPointItem(
                    target_domain=LegacyDomainCategory.MULTI_CHANNEL_INVENTORY_SYNC,
                    specific_system="Nightly SFTP Batch CSV from AS/400",
                    verbatim_evidence="Our BOPIS cancellation rate spiked to 21% last December, costing us over $1.8M in lost sales and customer concessions",
                    technical_bottleneck="Nightly batch CSV export causes 4+ hour inventory data latency between physical stores and digital web store.",
                    operational_friction="E-commerce sells units already bought in-store, causing store associates to cancel customer BOPIS orders due to phantom inventory.",
                    financial_impact="21% BOPIS cancellation rate resulting in $1.8M in lost revenue and customer concession credits.",
                    affected_stakeholders=["VP of Supply Chain", "Director of Retail Operations"]
                )
            ],
            extraction_summary="Identified on-premise IBM AS/400 and Epicor 9 with severe multi-channel inventory synchronization latency."
        )
        print("\nSerialized Pydantic JSON Output:")
        print(mock_detection.model_dump_json(indent=2))
    else:
        print("\n1. Executing live extraction on legacy prospect transcript...")
        try:
            result_positive = extract_legacy_erp_pain_points(
                payload_text=sample_legacy_transcript,
                raise_if_empty=False
            )
            print(f"\nDetection Flag: {result_positive.has_legacy_systems}")
            print(f"Summary: {result_positive.extraction_summary}")
            print(f"Detected Systems: {len(result_positive.detected_systems)}")
            for sys in result_positive.detected_systems:
                print(f"  - [{sys.domain.value}] {sys.detected_system_name} (Confidence: {sys.confidence})")
                print(f"    Evidence: \"{sys.evidence_quote}\"")

            print(f"\nExtracted Pain Points: {len(result_positive.pain_points)}")
            for idx, pt in enumerate(result_positive.pain_points, 1):
                print(f"\n  [{idx}] Domain: {pt.target_domain.value} | System: {pt.specific_system}")
                print(f"      Verbatim Quote: \"{pt.verbatim_evidence}\"")
                print(f"      Technical Gap: {pt.technical_bottleneck}")
                print(f"      Operational Friction: {pt.operational_friction}")
                print(f"      Financial Impact: {pt.financial_impact}")
                print(f"      Stakeholders: {', '.join(pt.affected_stakeholders)}")

        except Exception as e:
            print(f"Error during positive extraction: {e}")

        print("\n" + "=" * 80)
        print("DEMO 2: NEGATIVE DETECTION - IRRELEVANT / CLOUD-NATIVE PAYLOAD")
        print("=" * 80)
        try:
            result_negative = extract_legacy_erp_pain_points(
                payload_text=sample_irrelevant_payload,
                raise_if_empty=False
            )
            print(f"Detection Flag: {result_negative.has_legacy_systems}")
            print(f"Summary: {result_negative.extraction_summary}")
            print(f"Systems Found: {len(result_negative.detected_systems)}")
            print(f"Pain Points Found: {len(result_negative.pain_points)}")
        except Exception as e:
            print(f"Error during negative extraction: {e}")
