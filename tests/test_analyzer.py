"""
Unit tests for the Retail Discovery Analyzer (analyzer.py).
Tests prompt construction and discovery synthesis with mocked Gemini service.
"""

import pytest
from unittest.mock import patch

from analyzer import build_analysis_prompt, analyze_retail_prospect
from core.models import DiscoveryDossier


def test_build_analysis_prompt():
    prompt = build_analysis_prompt(
        account_name="Target",
        domain="https://target.com",
        scraped_markdown="# Target Home",
        tech_signals=["Shopify Plus", "GA4"],
        bdr_notes="Regional store clusters are misaligned.",
        annual_revenue="$104B",
        headcount="400,000",
        corporate_url="https://corporate.target.com",
        press_releases=[{"title": "Q4 Earnings", "source_url": "https://target.com/q4"}],
    )
    assert "Target" in prompt
    assert "https://target.com" in prompt
    assert "Regional store clusters" in prompt
    assert "Q4 Earnings" in prompt


def test_analyze_retail_prospect_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Gemini API key is required"):
        analyze_retail_prospect(
            account_name="Acme",
            domain="https://acme.com",
            scraped_markdown="Storefront",
            api_key="",
        )


def test_analyze_retail_prospect_success(sample_dossier):
    with patch("analyzer.generate_structured_output") as mock_generate:
        mock_generate.return_value = sample_dossier

        result = analyze_retail_prospect(
            account_name="Nordstrom",
            domain="https://www.nordstrom.com",
            scraped_markdown="Nordstrom content",
            tech_signals=["Salesforce Commerce Cloud (Demandware)"],
            corporate_url="https://press.nordstrom.com",
            api_key="mock-api-key",
        )

        assert isinstance(result, DiscoveryDossier)
        assert result.account_name == "Nordstrom"
        assert result.corporate_domain == "https://press.nordstrom.com"
        assert mock_generate.call_count == 1
