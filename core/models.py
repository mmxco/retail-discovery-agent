"""
Enterprise Pre-Sales Discovery Data Models & Contracts
Single source of truth for all Pydantic V2 schemas across retail account
intelligence, architectural signals, Value Triangle pain points,
discovery questions, legacy ERP extraction, and scraper contracts.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Literal, Optional, Dict, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, ConfigDict


# ==============================================================================
# DISCOVERY & DOSSIER SCHEMAS
# ==============================================================================

class TechStackIndicators(BaseModel):
    """Detected or inferred technology stack components across the retail IT landscape."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ecommerce_platform: Optional[str] = Field(
        default=None,
        description="Identified digital commerce engine (e.g., Salesforce Commerce Cloud, Shopify Plus, SAP Commerce, Adobe Commerce, commercetools)."
    )
    point_of_sale: Optional[str] = Field(
        default=None,
        description="In-store Point of Sale (POS) architecture (e.g., Oracle Retail Xstore, Aptos, NCR Voyix, Manhattan Associates POS, Toshiba, GK Software)."
    )
    erp_core: Optional[str] = Field(
        default=None,
        description="Core enterprise resource planning or merchandising financial system (e.g., SAP S/4HANA Retail, Oracle Retail / NetSuite, Microsoft Dynamics 365)."
    )
    order_management: Optional[str] = Field(
        default=None,
        description="Distributed order management (DOM / OMS) engine (e.g., Manhattan Active Omni, IBM Sterling OMS, Fluent Commerce, Blue Yonder)."
    )
    warehouse_supply_chain: Optional[str] = Field(
        default=None,
        description="Supply chain and warehouse management systems (e.g., Manhattan WMS, Blue Yonder, HighJump/Körber)."
    )
    analytics_and_marketing: List[str] = Field(
        default_factory=list,
        description="Detected customer data platform, marketing automation, or web analytics tools (e.g., GA4, Segment, Klaviyo, Adobe Experience Platform)."
    )
    detected_technologies: List[str] = Field(
        default_factory=list,
        description="Comprehensive list of specific software, SDKs, and third-party services detected from page signatures and scripts."
    )
    architecture_signals: List[str] = Field(
        default_factory=list,
        description="Inferred architectural traits (e.g., 'Monolithic legacy ERP', 'Headless frontend with legacy backend', 'Batch sync indicators')."
    )


class ExecutivePainPoints(BaseModel):
    """
    Synthesizes retail enterprise friction using the Value Triangle:
    Technical Gap -> Operational Friction -> Financial Impact.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    category: str = Field(
        ...,
        description="Operational retail pillar (e.g., 'Unified Inventory Visibility', 'Store-as-a-Hub Fulfillment', 'POS-to-ERP Sync Latency', 'Markdown & Inventory Misallocation')."
    )
    technical_gap: str = Field(
        ...,
        description="The architectural bottleneck or legacy constraint (e.g., nightly batch sync between POS and central ERP, lack of unified real-time ATP service)."
    )
    operational_friction: str = Field(
        ...,
        description="The frontline business friction (e.g., phantom store stock, cancelled BOPIS orders, store associates inability to view regional stock)."
    )
    financial_impact: str = Field(
        ...,
        description="Quantified business cost or risk (e.g., $50M+ margin erosion from emergency clearance markdowns, high inter-store freight transfers)."
    )
    affected_executives: List[str] = Field(
        default_factory=list,
        description="Executive personas most impacted (e.g., 'VP of Merchandising', 'Chief Information Officer', 'VP of Supply Chain', 'Head of Retail Ops')."
    )


class DiscoveryQuestions(BaseModel):
    """Tailored pre-sales discovery questions targeted at specific retail personas."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    target_persona: str = Field(
        ...,
        description="Executive role to engage (e.g., 'Chief Information Officer', 'VP of Retail Operations', 'VP of Merchandising & Allocation')."
    )
    theme: str = Field(
        ...,
        description="Core discovery subject area (e.g., 'Real-time Stock Accuracy', 'Unified Store Returns', 'Legacy POS Scalability')."
    )
    question: str = Field(
        ...,
        description="High-impact, open-ended question designed to uncover architectural compromises and operational pain."
    )
    what_to_listen_for: str = Field(
        ...,
        description="Specific responses, vendor mentions, or pain symptoms that signal a high-probability opportunity."
    )
    value_wedge: str = Field(
        ...,
        description="The competitive angle or differentiator against legacy ERP and monolithic architectures."
    )


class DiscoveryDossier(BaseModel):
    """Comprehensive executive pre-sales discovery briefing dossier."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    account_name: str = Field(
        ...,
        description="Brand name or commercial operating entity of the retail prospect (e.g., Target, Nordstrom)."
    )
    domain: str = Field(
        ...,
        description="Primary domain or website URL (e.g., https://target.com)."
    )
    corporate_domain: Optional[str] = Field(
        default=None,
        description="Corporate website, parent company, or investor relations URL (e.g., https://corporate.target.com)."
    )
    retail_segment: str = Field(
        ...,
        description="Retail segment (e.g., 'Apparel & Specialty', 'Department Store', 'Grocery & Convenience', 'Luxury & Beauty', 'Hardlines')."
    )
    estimated_scale: str = Field(
        ...,
        description="Estimated business scale including store count, headcount, and revenue bracket (e.g., '1,900+ stores, 400k employees, $100B+ revenue')."
    )
    executive_summary: str = Field(
        ...,
        description="2-3 paragraph executive summary synthesizing the prospect's market position, strategic challenges, and modern ERP/POS modernization opportunity."
    )
    tech_stack: TechStackIndicators = Field(
        default_factory=TechStackIndicators,
        description="Detected or inferred enterprise technology stack footprint."
    )
    pain_points: List[ExecutivePainPoints] = Field(
        default_factory=list,
        description="List of prioritized pain points mapped to the Value Triangle."
    )
    discovery_questions: List[DiscoveryQuestions] = Field(
        default_factory=list,
        description="Prioritized discovery questions categorized by executive persona."
    )
    recommended_discovery_strategy: str = Field(
        ...,
        description="Tactical pre-sales strategy for the account team (e.g., which persona to enter through, initial demo wedge, proof-of-value focus)."
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of dossier generation."
    )


# ==============================================================================
# TARGETED LEGACY ERP & INVENTORY SYNC PAIN POINT SCHEMAS
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


class NoLegacyERPPainPointsFoundError(Exception):
    """Raised when strict extraction mode is active and no legacy ERP pain points are detected."""
    def __init__(self, message: str = "No target legacy ERP systems or pain points identified in payload."):
        super().__init__(message)


# ==============================================================================
# DISCOVERY BRIEF (EXTRACTION PIPELINE CONTRACTS)
# ==============================================================================

class PainPoint(BaseModel):
    """
    Granular prospect pain point capturing friction, category, and impact.
    """
    model_config = ConfigDict(extra="ignore")

    category: Literal["Technical", "Business"] = Field(
        ...,
        description=(
            "Categorization of friction: 'Technical' indicates architectural debt, "
            "legacy tech, API latency, batch processing, or data sync limits; 'Business' "
            "indicates margin degradation, customer churn, executive risk, or staff inefficiency."
        )
    )
    description: str = Field(
        ...,
        description="Precise, objective description of the challenge or operational hurdle described by the prospect."
    )
    impact: str = Field(
        ...,
        description="Quantifiable or strategic business impact (e.g., lost revenue, SLA penalties, customer dissatisfaction)."
    )


class DiscoveryBrief(BaseModel):
    """
    Parent discovery document aggregating all synthesized pain points from prospect notes.
    """
    model_config = ConfigDict(extra="ignore")

    company_name: Optional[str] = Field(
        default=None,
        description="Optional company or brand name."
    )
    pain_points: List[PainPoint] = Field(
        ...,
        description="Comprehensive collection of all technical and business pain points extracted from the text."
    )


# ==============================================================================
# SCRAPER & CRAWLER DATA CONTRACTS
# ==============================================================================

@dataclass
class PressReleaseItem:
    """Structured press release or corporate announcement entry."""
    title: str
    source_url: str
    markdown_text: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "source_url": self.source_url,
            "markdown_text": self.markdown_text,
        }


@dataclass
class ScrapeResult:
    """Structured result returned by the scraping bridge."""
    url: str
    title: str = ""
    markdown: str = ""
    meta_description: str = ""
    meta_keywords: str = ""
    tech_signals: List[str] = field(default_factory=list)
    about_us_content: Dict[str, Any] = field(default_factory=dict)
    leadership_content: Dict[str, Any] = field(default_factory=dict)
    press_releases: List[Dict[str, str]] = field(default_factory=list)
    crawl_payload: Dict[str, Any] = field(default_factory=dict)
    engine_used: str = "playwright"
    success: bool = True
    error_message: Optional[str] = None

    def to_summary_dict(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "title": self.title,
            "meta_description": self.meta_description,
            "tech_signals": self.tech_signals,
            "markdown_char_count": len(self.markdown),
            "markdown_content": self.markdown,
            "about_us_content": self.about_us_content,
            "leadership_content": self.leadership_content,
            "press_releases": self.press_releases,
            "engine_used": self.engine_used,
            "success": self.success,
        }
