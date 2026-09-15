"""
End-to-end headless UI tests for app.py using Streamlit AppTest.
Tests view orchestration, scenario switching, account profile persistence,
form validations, pipeline execution, and tabbed dossier presentation.
Zero live browser, server, network, or external Google/Gemini dependencies.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from streamlit.testing.v1 import AppTest

from core.models import (
    DiscoveryDossier,
    TechStackIndicators,
    ExecutivePainPoints,
    DiscoveryQuestions,
    ScrapeResult,
)

APP_PATH = str(Path(__file__).parent.parent / "app.py")


@pytest.fixture
def mock_external_ui_dependencies(tmp_path, monkeypatch):
    """Patches all external network, browser, and persistence calls during Streamlit UI execution."""
    mock_folders = {"success": True, "folders": [], "shared_drives": [], "total_count": 0}
    test_profiles = tmp_path / "test_saved_profiles.json"
    monkeypatch.setattr("profile_manager.DEFAULT_PROFILES_FILE", str(test_profiles))
    with patch("auth.google_oauth.get_user_oauth_credentials", return_value=None), \
         patch("integrations.drive_service.list_drive_folders", return_value=mock_folders), \
         patch("ui.sidebar.check_playwright_availability", return_value=(True, "OK")), \
         patch("scraper.check_playwright_availability", return_value=(True, "OK")):
        yield


def test_ui_initial_render(mock_external_ui_dependencies):
    """Verifies that app.py initializes cleanly with all UI components and defaults."""
    at = AppTest.from_file(APP_PATH, default_timeout=10)
    at.run()

    # 1. No unhandled exceptions
    assert len(at.exception) == 0

    # 2. Main title exists
    assert any("Retail Enterprise Pre-Sales Discovery Studio" in t.value for t in at.title)

    # 3. Scenario selector exists and defaults to Scenario 1 (Target)
    scenario_sb = [sb for sb in at.selectbox if "Select Target Account Profile" in sb.label][0]
    assert "Target" in scenario_sb.value

    # 4. Form inputs initialized with Target scenario defaults
    domain_input = [ti for ti in at.text_input if ti.key == "target_form_domain"][0]
    assert domain_input.value == "https://target.com"

    dba_input = [ti for ti in at.text_input if ti.key == "target_form_dba"][0]
    assert dba_input.value == "Target"


def test_ui_scenario_switching(mock_external_ui_dependencies):
    """Tests switching between preset scenarios and Blank Canvas."""
    at = AppTest.from_file(APP_PATH, default_timeout=10)
    at.run()

    # Switch to Nordstrom
    scenario_sb = [sb for sb in at.selectbox if "Select Target Account Profile" in sb.label][0]
    scenario_sb.select("Scenario 2: Nordstrom - Omnichannel Fulfillment & Stock Accuracy").run()
    assert len(at.exception) == 0
    domain_nord = [ti for ti in at.text_input if ti.key == "target_form_domain"][0]
    assert domain_nord.value == "https://www.nordstrom.com"

    # Switch to Williams-Sonoma
    scenario_sb = [sb for sb in at.selectbox if "Select Target Account Profile" in sb.label][0]
    scenario_sb.select("Scenario 3: Williams-Sonoma - High-AOV Specialty Logistics").run()
    assert len(at.exception) == 0
    domain_ws = [ti for ti in at.text_input if ti.key == "target_form_domain"][0]
    assert domain_ws.value == "https://www.williams-sonoma.com"

    # Switch to Blank Canvas
    scenario_sb = [sb for sb in at.selectbox if "Select Target Account Profile" in sb.label][0]
    scenario_sb.select("New Prospect / Blank Canvas").run()
    assert len(at.exception) == 0
    domain_blank = [ti for ti in at.text_input if ti.key == "target_form_domain"][0]
    assert domain_blank.value == ""


def test_ui_validation_missing_domain(mock_external_ui_dependencies):
    """Tests that submitting without a domain triggers validation error."""
    at = AppTest.from_file(APP_PATH, default_timeout=10)
    at.run()

    # Select Blank Canvas
    scenario_sb = [sb for sb in at.selectbox if "Select Target Account Profile" in sb.label][0]
    scenario_sb.select("New Prospect / Blank Canvas").run()

    # Submit pipeline
    submit_btn = [b for b in at.button if "Run Pre-Sales Discovery Pipeline" in b.label][0]
    submit_btn.click().run()

    # Error message should be rendered
    assert len(at.error) > 0
    assert any("Please provide a target retailer website domain" in err.value for err in at.error)


def test_ui_validation_missing_api_key(mock_external_ui_dependencies, monkeypatch):
    """Tests that submitting without a Gemini API key triggers validation error."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    at = AppTest.from_file(APP_PATH, default_timeout=10)
    at.run()

    # Clear api key input
    api_input = [ti for ti in at.text_input if "Gemini API Key" in ti.label][0]
    api_input.input("").run()

    # Submit pipeline
    submit_btn = [b for b in at.button if "Run Pre-Sales Discovery Pipeline" in b.label][0]
    submit_btn.click().run()

    assert len(at.error) > 0
    assert any("A Gemini API Key is required" in err.value for err in at.error)


def test_ui_validation_playwright_unavailable(tmp_path, monkeypatch):
    """Tests that pipeline halts if Playwright is unavailable."""
    test_profiles = tmp_path / "test_saved_profiles.json"
    monkeypatch.setattr("profile_manager.DEFAULT_PROFILES_FILE", str(test_profiles))
    with patch("auth.google_oauth.get_user_oauth_credentials", return_value=None), \
         patch("integrations.drive_service.list_drive_folders", return_value={"success": True, "folders": [], "shared_drives": []}), \
         patch("ui.sidebar.check_playwright_availability", return_value=(False, "Playwright browser binaries missing")), \
         patch("scraper.check_playwright_availability", return_value=(False, "Playwright browser binaries missing")):
        at = AppTest.from_file(APP_PATH, default_timeout=10)
        at.run()

        submit_btn = [b for b in at.button if "Run Pre-Sales Discovery Pipeline" in b.label][0]
        submit_btn.click().run()

        assert len(at.error) > 0
        assert any("Playwright Headless Browser is unavailable" in err.value for err in at.error)


def test_ui_save_profile_action(mock_external_ui_dependencies):
    """Tests saving a customized profile from the form."""
    at = AppTest.from_file(APP_PATH, default_timeout=10)
    at.run()

    # Select Blank Canvas
    scenario_sb = [sb for sb in at.selectbox if "Select Target Account Profile" in sb.label][0]
    scenario_sb.select("New Prospect / Blank Canvas").run()

    # Enter custom account details
    domain_input = [ti for ti in at.text_input if ti.key == "target_form_domain"][0]
    domain_input.input("https://customretailer.com")

    dba_input = [ti for ti in at.text_input if ti.key == "target_form_dba"][0]
    dba_input.input("Custom Retailer")

    save_btn = [b for b in at.button if "Save Profile" in b.label][0]
    save_btn.click().run()

    assert at.session_state["selected_scenario_name"] == "[Saved] Custom Retailer"


def test_ui_end_to_end_pipeline_and_tabs(mock_external_ui_dependencies, sample_dossier):
    """Tests full end-to-end pipeline execution and tab rendering via AppTest."""
    mock_scrape = ScrapeResult(
        url="https://target.com",
        success=True,
        markdown="# Storefront\nWelcome to Target",
        tech_signals=["React", "Salesforce Commerce Cloud"],
    )

    with patch("scraper.scrape_retail_site", return_value=mock_scrape) as mock_s, \
         patch("analyzer.analyze_retail_prospect", return_value=sample_dossier) as mock_a, \
         patch("exporters.gdocs_exporter.export_dossier_to_google_doc", return_value={"document_url": "https://docs.google.com/document/d/doc_123"}) as mock_doc:

        at = AppTest.from_file(APP_PATH, default_timeout=10)
        at.run()

        submit_btn = [b for b in at.button if "Run Pre-Sales Discovery Pipeline" in b.label][0]
        submit_btn.click().run()

        # 1. No unhandled exceptions
        assert len(at.exception) == 0

        # 2. Pipeline mocks were called
        assert mock_s.called
        assert mock_a.called

        # 3. Session state holds the completed dossier
        assert "latest_dossier" in at.session_state
        assert at.session_state["latest_dossier"].account_name == sample_dossier.account_name

        # 4. Tab presentation is rendered
        assert len(at.tabs) == 6
        tab_labels = [t.label for t in at.tabs]
        assert any("Executive Overview" in lbl for lbl in tab_labels)
        assert any("Tech Stack" in lbl for lbl in tab_labels)
        assert any("Value Triangle" in lbl for lbl in tab_labels)
        assert any("Discovery Questions" in lbl for lbl in tab_labels)
        assert any("Recommended Strategy" in lbl for lbl in tab_labels)
        assert any("Scraped Signals" in lbl for lbl in tab_labels)


def test_ui_pipeline_execution_error(mock_external_ui_dependencies):
    """Tests that pipeline errors during scraping/analysis are captured and displayed."""
    with patch("scraper.scrape_retail_site", side_effect=RuntimeError("Connection refused by prospect server")):
        at = AppTest.from_file(APP_PATH, default_timeout=10)
        at.run()

        submit_btn = [b for b in at.button if "Run Pre-Sales Discovery Pipeline" in b.label][0]
        submit_btn.click()
        at.run()

        assert len(at.error) > 0
        assert any("Connection refused by prospect server" in err.value for err in at.error)
