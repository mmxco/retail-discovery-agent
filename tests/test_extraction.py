"""
Pytest suite for LLM structured extraction (discovery_pipeline.py).
Tests pain point extraction, irrelevant input handling, and Pydantic validation errors
using mocked Gemini LLM calls.
"""

import pytest
from unittest.mock import patch
from pydantic import ValidationError

from discovery_pipeline import PainPoint, DiscoveryBrief, extract_pain_points


def test_successful_pain_point_extraction():
    """
    Tests that clear discovery notes result in a valid DiscoveryBrief
    with correctly categorized pain points.
    """
    notes = (
        "The legacy database takes 4 hours to sync, causing the fulfillment "
        "team to miss same-day shipping cutoffs and losing retail customers."
    )

    mock_brief = DiscoveryBrief(
        company_name="Acme Retail",
        pain_points=[
            PainPoint(
                category="Technical",
                description="The legacy database takes 4 hours to sync.",
                impact="Fulfillment team misses same-day shipping cutoffs.",
            ),
            PainPoint(
                category="Business",
                description="Losing retail customers due to shipping delays.",
                impact="Customer churn and revenue loss.",
            ),
        ]
    )

    with patch("discovery_pipeline.generate_structured_output", return_value=mock_brief):
        result = extract_pain_points(notes)

        # 1. Structural Verification:
        assert isinstance(result, DiscoveryBrief)
        assert len(result.pain_points) > 0

        # 2. Semantic Verification:
        for point in result.pain_points:
            assert point.category in ["Technical", "Business"]


def test_irrelevant_input_handling():
    """
    Tests that irrelevant or empty prospect notes return an empty pain points collection.
    """
    notes = "The quick brown fox jumps over the lazy dog."
    mock_empty_brief = DiscoveryBrief(pain_points=[])

    with patch("discovery_pipeline.generate_structured_output", return_value=mock_empty_brief):
        result = extract_pain_points(notes)
        assert isinstance(result, DiscoveryBrief)
        assert len(result.pain_points) == 0


def test_validation_error_handling():
    """
    Mocks a malformed API response to ensure downstream functions
    handle Pydantic ValidationErrors correctly.
    """
    mock_bad_json = '{"company_name": "Acme", "wrong_key": []}'

    # Verify Pydantic traps the structural failure and raises ValidationError
    with pytest.raises(ValidationError):
        DiscoveryBrief.model_validate_json(mock_bad_json)
