"""
Enterprise Pre-Sales Discovery Data Models
Pydantic V2 schemas for retail account intelligence, architectural signals,
Value Triangle pain point analysis, and executive discovery questions.
"""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


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
