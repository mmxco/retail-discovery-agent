"""
Unit tests for profile persistence and disk operations (profile_manager.py).
"""

import os
import tempfile
import pytest
import streamlit as st

from profile_manager import save_profile, load_saved_profiles, delete_profile
from core.models import DiscoveryDossier
from exporters.markdown_exporter import export_dossier_to_markdown
from ui.form import auto_save_profile_on_submit


def test_profile_persistence_lifecycle():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        test_file = tf.name

    try:
        # 1. Load empty
        p_empty = load_saved_profiles(test_file)
        assert p_empty == {}

        # 2. Save profile
        p_data = {
            "domain": "https://www.target.com",
            "corporate_url": "https://corporate.target.com",
            "dba": "Target Corporation",
            "careers_url": "https://corporate.target.com/careers",
            "revenue": "$104B",
            "headcount": "400,000",
            "bdr_notes": "Omnichannel allocation tests",
        }
        key = save_profile(p_data, filepath=test_file)
        assert key == "[Saved] Target Corporation"

        # 3. Verify loaded
        p_loaded = load_saved_profiles(test_file)
        assert key in p_loaded
        assert p_loaded[key]["corporate_url"] == "https://corporate.target.com"
        assert p_loaded[key]["domain"] == "https://www.target.com"
        assert p_loaded[key]["revenue"] == "$104B"

        # 4. Verify markdown export with corporate_domain
        dossier = DiscoveryDossier(
            account_name="Target Corporation",
            domain=p_loaded[key]["domain"],
            corporate_domain=p_loaded[key]["corporate_url"],
            retail_segment="Department Store",
            estimated_scale="1900 stores",
            executive_summary="Leading general merchandise retailer.",
            recommended_discovery_strategy="Executive briefing wedge.",
        )
        md = export_dossier_to_markdown(dossier)
        assert "**Corporate Website:** https://corporate.target.com" in md
        assert "**Retail Domain:** https://www.target.com" in md

        # 5. Update profile
        p_data["revenue"] = "$106B"
        save_profile(p_data, profile_key=key, filepath=test_file)
        p_updated = load_saved_profiles(test_file)
        assert p_updated[key]["revenue"] == "$106B"

        # 6. Delete profile
        assert delete_profile(key, filepath=test_file) is True
        assert load_saved_profiles(test_file) == {}
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_auto_save_profile_on_submit_new_prospect(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        test_file = tf.name

    try:
        monkeypatch.setattr("profile_manager.DEFAULT_PROFILES_FILE", test_file)
        monkeypatch.setattr("ui.form.load_saved_profiles", lambda: load_saved_profiles(test_file))
        monkeypatch.setattr("ui.form.save_profile", lambda data, profile_key=None: save_profile(data, profile_key=profile_key, filepath=test_file))

        st.session_state.clear()
        st.session_state["selected_scenario_name"] = "Scenario 1: Target - Regional Assortment & Allocation Misalignment"

        form_data = {
            "domain": "https://newretail.com",
            "corporate_url": "",
            "dba": "New Retail Co",
            "careers_url": "",
            "revenue": "$500M",
            "headcount": "2000",
            "bdr_notes": "ERP notes",
        }

        saved_key = auto_save_profile_on_submit(form_data, "Scenario 1: Target - Regional Assortment & Allocation Misalignment")
        assert saved_key == "[Saved] New Retail Co"
        assert st.session_state["selected_scenario_name"] == "[Saved] New Retail Co"
        assert st.session_state["last_loaded_scenario"] == "[Saved] New Retail Co"
        assert st.session_state["pending_scenario_selection"] == "[Saved] New Retail Co"

        # Ensure Scenario 1 was NOT written to saved_profiles
        persisted = load_saved_profiles(test_file)
        assert "Scenario 1: Target - Regional Assortment & Allocation Misalignment" not in persisted
        assert "[Saved] New Retail Co" in persisted

        # Now update this saved profile
        form_data["revenue"] = "$600M"
        updated_key = auto_save_profile_on_submit(form_data, "[Saved] New Retail Co")
        assert updated_key == "[Saved] New Retail Co"
        persisted_updated = load_saved_profiles(test_file)
        assert persisted_updated["[Saved] New Retail Co"]["revenue"] == "$600M"
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

