"""
Unit tests for the Legacy ERP & Inventory Sync Extractor (legacy_erp_extractor.py).
Tests positive detection, negative detection, and strict empty-raising with mocked LLM.
"""

import pytest
from unittest.mock import patch

from legacy_erp_extractor import (
    extract_legacy_erp_pain_points,
    LegacyERPPainPoints,
    TargetSystemDetection,
    LegacyERPPainPointItem,
    LegacyDomainCategory,
    NoLegacyERPPainPointsFoundError,
)


def test_extract_legacy_erp_empty_payload():
    with pytest.raises(ValueError, match="cannot be empty"):
        extract_legacy_erp_pain_points("")


def test_extract_legacy_erp_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Gemini API key is required"):
        extract_legacy_erp_pain_points("AS400 notes", api_key="")


def test_extract_legacy_erp_positive():
    mock_payload = LegacyERPPainPoints(
        has_legacy_systems=True,
        detected_systems=[
            TargetSystemDetection(
                domain=LegacyDomainCategory.AS400_ISERIES,
                detected_system_name="IBM AS/400 (RPG)",
                confidence="HIGH",
                evidence_quote="core inventory backbone is hosted on IBM AS/400",
            )
        ],
        pain_points=[
            LegacyERPPainPointItem(
                target_domain=LegacyDomainCategory.MULTI_CHANNEL_INVENTORY_SYNC,
                specific_system="Nightly SFTP Batch",
                verbatim_evidence="BOPIS cancellation rate spiked to 21%",
                technical_bottleneck="Nightly batch sync latency",
                operational_friction="Store associates cancel phantom stock orders",
                financial_impact="$1.8M lost sales",
                affected_stakeholders=["VP Supply Chain"],
            )
        ],
        extraction_summary="Detected AS400 and inventory sync bottlenecks.",
    )

    with patch("legacy_erp_extractor.generate_structured_output", return_value=mock_payload):
        result = extract_legacy_erp_pain_points("Sample AS400 transcript", api_key="dummy-key")
        assert result.has_legacy_systems is True
        assert len(result.detected_systems) == 1
        assert len(result.pain_points) == 1
        assert result.pain_points[0].target_domain == LegacyDomainCategory.MULTI_CHANNEL_INVENTORY_SYNC


def test_extract_legacy_erp_negative_and_raise_if_empty():
    mock_empty = LegacyERPPainPoints(
        has_legacy_systems=False,
        detected_systems=[],
        pain_points=[],
        extraction_summary="No targeted legacy ERP systems detected.",
    )

    with patch("legacy_erp_extractor.generate_structured_output", return_value=mock_empty):
        # Without raise_if_empty
        res = extract_legacy_erp_pain_points("Modern shopify notes", api_key="dummy-key", raise_if_empty=False)
        assert res.has_legacy_systems is False
        assert len(res.pain_points) == 0

        # With raise_if_empty=True
        with pytest.raises(NoLegacyERPPainPointsFoundError):
            extract_legacy_erp_pain_points("Modern shopify notes", api_key="dummy-key", raise_if_empty=True)
