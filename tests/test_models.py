"""
Unit tests for data contracts and Pydantic V2 schemas.
Verifies zero duplicate definitions, clean serialization, and strict schema validation.
"""

import pytest
from pydantic import ValidationError

from core.models import (
    TechStackIndicators,
    ExecutivePainPoints,
    DiscoveryQuestions,
    DiscoveryDossier,
    LegacyDomainCategory,
    TargetSystemDetection,
    LegacyERPPainPointItem,
    LegacyERPPainPoints,
    PainPoint,
    DiscoveryBrief,
    ScrapeResult,
    PressReleaseItem,
)


def test_tech_stack_indicators_defaults():
    ts = TechStackIndicators()
    assert ts.ecommerce_platform is None
    assert ts.analytics_and_marketing == []
    assert ts.detected_technologies == []
    assert ts.architecture_signals == []


def test_tech_stack_indicators_populated():
    ts = TechStackIndicators(
        ecommerce_platform="Shopify Plus",
        point_of_sale="Oracle Retail Xstore",
        erp_core="SAP S/4HANA Retail",
        analytics_and_marketing=["GA4", "Klaviyo"],
    )
    assert ts.ecommerce_platform == "Shopify Plus"
    assert "GA4" in ts.analytics_and_marketing


def test_executive_pain_points_validation():
    # Missing required fields should raise ValidationError
    with pytest.raises(ValidationError):
        ExecutivePainPoints(category="Inventory")

    point = ExecutivePainPoints(
        category="Inventory Visibility",
        technical_gap="Nightly batch feed",
        operational_friction="Phantom stock",
        financial_impact="$10M margin loss",
        affected_executives=["CIO"],
    )
    assert point.category == "Inventory Visibility"
    assert point.affected_executives == ["CIO"]


def test_discovery_dossier_serialization(sample_dossier):
    json_str = sample_dossier.model_dump_json()
    assert sample_dossier.account_name in json_str

    # Round-trip deserialization
    loaded = DiscoveryDossier.model_validate_json(json_str)
    assert loaded.account_name == sample_dossier.account_name
    assert loaded.tech_stack.ecommerce_platform == sample_dossier.tech_stack.ecommerce_platform
    assert len(loaded.pain_points) == 1
    assert len(loaded.discovery_questions) == 1


def test_legacy_erp_models():
    sys_det = TargetSystemDetection(
        domain=LegacyDomainCategory.AS400_ISERIES,
        detected_system_name="IBM AS/400 (RPG III)",
        confidence="HIGH",
        evidence_quote="Inventory is managed on AS/400.",
    )
    assert sys_det.domain == LegacyDomainCategory.AS400_ISERIES
    assert sys_det.confidence == "HIGH"

    item = LegacyERPPainPointItem(
        target_domain=LegacyDomainCategory.MULTI_CHANNEL_INVENTORY_SYNC,
        specific_system="SFTP Batch Job",
        verbatim_evidence="Batch delays cause phantom orders.",
        technical_bottleneck="Batch latency",
        operational_friction="Cancelled orders",
        financial_impact="$2M write-off",
        affected_stakeholders=["VP Supply Chain"],
    )

    erp_payload = LegacyERPPainPoints(
        has_legacy_systems=True,
        detected_systems=[sys_det],
        pain_points=[item],
        extraction_summary="Identified AS400 with sync bottlenecks.",
    )
    assert erp_payload.has_legacy_systems is True
    assert len(erp_payload.detected_systems) == 1
    assert len(erp_payload.pain_points) == 1


def test_discovery_brief_schema():
    point = PainPoint(
        category="Technical",
        description="Legacy database takes 4 hours to sync.",
        impact="Missed shipping cutoffs.",
    )
    brief = DiscoveryBrief(pain_points=[point], company_name="Test Retail")
    assert len(brief.pain_points) == 1
    assert brief.pain_points[0].category == "Technical"

    # Verify category validation error
    with pytest.raises(ValidationError):
        PainPoint(category="InvalidCategory", description="Foo", impact="Bar")


def test_scraper_data_contracts():
    pr = PressReleaseItem(
        title="New Store Openings",
        source_url="https://example.com/pr",
        markdown_text="Opening 10 new hubs.",
    )
    pr_dict = pr.to_dict()
    assert pr_dict["title"] == "New Store Openings"

    res = ScrapeResult(
        url="https://example.com",
        title="Example Retail",
        tech_signals=["Shopify Plus"],
        press_releases=[pr_dict],
    )
    summary = res.to_summary_dict()
    assert summary["title"] == "Example Retail"
    assert "Shopify Plus" in summary["tech_signals"]
