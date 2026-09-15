"""
Pytest configuration and shared test fixtures.
Ensures external network, LLM calls, and credentials are mocked safely.
"""

import os
import sys
import pytest

# Ensure root workspace is in sys.path
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from core.models import (
    DiscoveryDossier,
    TechStackIndicators,
    ExecutivePainPoints,
    DiscoveryQuestions,
    PainPoint,
    DiscoveryBrief,
)


@pytest.fixture(autouse=True)
def mock_env_credentials(monkeypatch):
    """Provides a dummy GEMINI_API_KEY environment variable if not already set."""
    if not os.environ.get("GEMINI_API_KEY"):
        monkeypatch.setenv("GEMINI_API_KEY", "test-mock-api-key-12345")


@pytest.fixture
def sample_dossier():
    """Returns a fully populated DiscoveryDossier for export and presentation testing."""
    return DiscoveryDossier(
        account_name="Nordstrom",
        domain="https://www.nordstrom.com",
        corporate_domain="https://press.nordstrom.com",
        retail_segment="Apparel & Luxury Department Store",
        estimated_scale="350+ stores, 60k employees, $14.8B revenue",
        executive_summary="Nordstrom is a leading American luxury department store chain.",
        tech_stack=TechStackIndicators(
            ecommerce_platform="Salesforce Commerce Cloud (Demandware)",
            point_of_sale="Oracle Retail Xstore",
            erp_core="SAP S/4HANA Retail",
            order_management="Manhattan Active Omni",
            warehouse_supply_chain="Manhattan WMS",
            analytics_and_marketing=["Google Tag Manager", "Adobe Analytics"],
            detected_technologies=["React", "Next.js"],
            architecture_signals=["Headless digital commerce", "Batch POS sync"],
        ),
        pain_points=[
            ExecutivePainPoints(
                category="Unified Inventory Visibility",
                technical_gap="Nightly batch sync between stores and central SAP ERP.",
                operational_friction="Store associates face phantom inventory and cancelled BOPIS.",
                financial_impact="$25M+ lost revenue from cancelled omnichannel orders.",
                affected_executives=["VP of Supply Chain", "Chief Information Officer"],
            )
        ],
        discovery_questions=[
            DiscoveryQuestions(
                target_persona="Chief Information Officer",
                theme="Real-time Inventory ATP",
                question="How does your POS update Available-To-Promise stock during peak sales?",
                what_to_listen_for="Batch transfers, 4-hour delay, flat files",
                value_wedge="Event-driven real-time streaming eliminates phantom stock.",
            )
        ],
        recommended_discovery_strategy="Enter through VP of Store Operations with BOPIS demo.",
    )


@pytest.fixture
def sample_discovery_brief():
    """Returns a sample DiscoveryBrief for extraction testing."""
    return DiscoveryBrief(
        company_name="Acme Retail",
        pain_points=[
            PainPoint(
                category="Technical",
                description="The legacy database takes 4 hours to sync inventory.",
                impact="Fulfillment team misses same-day shipping cutoffs.",
            ),
            PainPoint(
                category="Business",
                description="Cancelled orders cause customer churn.",
                impact="Estimated $1.2M revenue loss annually.",
            ),
        ],
    )
