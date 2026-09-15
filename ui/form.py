"""
Form UI Controller
Handles preset scenario selection, saved profile persistence/deletion,
and target retailer account profile form rendering.
"""

import streamlit as st
from typing import Tuple, Dict, Any, Optional

from profile_manager import load_saved_profiles, save_profile, delete_profile


def auto_save_profile_on_submit(
    form_data: Dict[str, str],
    selected_scenario_name: Optional[str] = None,
) -> str:
    """
    Safely auto-saves profile on pipeline execution without overwriting built-in templates.
    Updates Streamlit session state to reflect the persisted profile key.
    """
    saved_profiles = load_saved_profiles()
    current_key = selected_scenario_name or st.session_state.get("selected_scenario_name")
    is_saved = current_key in saved_profiles
    target_key = current_key if is_saved else None
    saved_key = save_profile(form_data, profile_key=target_key)
    st.session_state["pending_scenario_selection"] = saved_key
    st.session_state["selected_scenario_name"] = saved_key
    st.session_state["last_loaded_scenario"] = saved_key
    return saved_key

SCENARIOS = {
    "New Prospect / Blank Canvas": {
        "domain": "", "corporate_url": "", "dba": "", "revenue": "",
        "headcount": "", "careers_url": "", "bdr_notes": ""
    },
    "Scenario 1: Target - Regional Assortment & Allocation Misalignment": {
        "domain": "https://target.com",
        "corporate_url": "https://corporate.target.com",
        "dba": "Target",
        "revenue": "$104,780,000,000",
        "headcount": "440,000",
        "careers_url": "https://corporate.target.com/careers",
        "bdr_notes": "Director of Merchandising mentioned regional store clusters are too broad. Southern stores receive heavy winter apparel allocations meant for Northern stores, causing $150.2M in inter-store transfer freight and localized stockouts."
    },
    "Scenario 2: Nordstrom - Omnichannel Fulfillment & Stock Accuracy": {
        "domain": "https://www.nordstrom.com",
        "corporate_url": "https://press.nordstrom.com",
        "dba": "Nordstrom",
        "revenue": "$14,800,000,000",
        "headcount": "60,000",
        "careers_url": "https://careers.nordstrom.com",
        "bdr_notes": "VP of Store Operations flagged high BOPIS cancellation rates due to phantom inventory in department stores. Store associates spend ~45 minutes per shift searching backrooms for online pickup items."
    },
    "Scenario 3: Williams-Sonoma - High-AOV Specialty Logistics": {
        "domain": "https://www.williams-sonoma.com",
        "corporate_url": "https://www.williams-sonomainc.com",
        "dba": "Williams-Sonoma",
        "revenue": "$8,670,000,000",
        "headcount": "28,000",
        "careers_url": "https://careers.williams-sonomainc.com",
        "bdr_notes": "Head of Omnichannel Logistics reported that high-AOV cookware and furniture orders frequently split into 3+ shipments from disparate fulfillment centers, causing high freight costs and customer dissatisfaction."
    }
}


def render_account_form() -> Tuple[bool, Dict[str, str]]:
    """
    Renders account scenario selector, persistence actions, and context inputs.
    Returns (submitted: bool, form_data: Dict[str, str]).
    """
    saved_profiles = load_saved_profiles()
    all_scenarios = {**SCENARIOS, **saved_profiles}
    all_scenario_keys = list(all_scenarios.keys())

    if "pending_scenario_selection" in st.session_state:
        st.session_state["scenario_selector_widget"] = st.session_state.pop("pending_scenario_selection")
    elif "last_saved_key" in st.session_state and st.session_state["last_saved_key"] in all_scenario_keys:
        st.session_state["scenario_selector_widget"] = st.session_state.pop("last_saved_key")
    elif "scenario_selector_widget" not in st.session_state or st.session_state["scenario_selector_widget"] not in all_scenario_keys:
        curr = st.session_state.get("selected_scenario_name")
        if curr in all_scenario_keys:
            st.session_state["scenario_selector_widget"] = curr
        else:
            st.session_state["scenario_selector_widget"] = all_scenario_keys[1] if len(all_scenario_keys) > 1 else all_scenario_keys[0]

    col_sel, col_action = st.columns([5, 1])
    with col_sel:
        selected_scenario_name = st.selectbox(
            "Select Target Account Profile:",
            options=all_scenario_keys,
            key="scenario_selector_widget",
            help="Choose a pre-configured demo scenario, a persistent saved profile, or Blank Canvas to create a new prospect.",
        )
        st.session_state["selected_scenario_name"] = selected_scenario_name

    is_saved_profile = selected_scenario_name in saved_profiles

    with col_action:
        st.write("")
        st.write("")
        if is_saved_profile:
            if st.button("🗑️ Delete", help=f"Delete saved profile '{selected_scenario_name}'", type="secondary", width="stretch"):
                delete_profile(selected_scenario_name)
                fallback_key = list(SCENARIOS.keys())[0]
                st.session_state["pending_scenario_selection"] = fallback_key
                st.session_state["selected_scenario_name"] = fallback_key
                for k in ["domain", "corporate_url", "dba", "careers", "revenue", "headcount", "bdr_notes"]:
                    st.session_state[f"target_form_{k}"] = ""
                st.session_state["last_loaded_scenario"] = fallback_key
                st.toast(f"Deleted profile '{selected_scenario_name}'", icon="🗑️")
                st.rerun()

    scenario_data = all_scenarios.get(selected_scenario_name, {})

    if st.session_state.get("last_loaded_scenario") != selected_scenario_name:
        st.session_state["target_form_domain"] = scenario_data.get("domain", "")
        st.session_state["target_form_corporate_url"] = scenario_data.get("corporate_url", "")
        st.session_state["target_form_dba"] = scenario_data.get("dba", "")
        st.session_state["target_form_careers"] = scenario_data.get("careers_url", "")
        st.session_state["target_form_revenue"] = scenario_data.get("revenue", "")
        st.session_state["target_form_headcount"] = scenario_data.get("headcount", "")
        st.session_state["target_form_bdr_notes"] = scenario_data.get("bdr_notes", "")
        st.session_state["last_loaded_scenario"] = selected_scenario_name

    with st.form("discovery_pipeline_form"):
        st.subheader("Target Account Profile")
        col1, col2 = st.columns(2)

        with col1:
            domain_input = st.text_input(
                "Retail / E-Commerce Website *",
                key="target_form_domain",
                placeholder="https://target.com",
                help="Primary customer-facing digital storefront or e-commerce website."
            )
            corporate_url_input = st.text_input(
                "Corporate Website (Optional)",
                key="target_form_corporate_url",
                placeholder="https://corporate.target.com",
                help="Parent corporate entity, investor relations, or corporate leadership site."
            )
            dba_input = st.text_input(
                "Brand / Account Name *",
                key="target_form_dba",
                placeholder="Target"
            )
            careers_input = st.text_input(
                "Careers URL (Optional)",
                key="target_form_careers",
                placeholder="https://corporate.target.com/careers"
            )

        with col2:
            revenue_input = st.text_input(
                "Estimated Annual Revenue",
                key="target_form_revenue",
                placeholder="$1,000,000,000"
            )
            headcount_input = st.text_input(
                "Employee Headcount / Store Count",
                key="target_form_headcount",
                placeholder="10,000 employees / 250 stores"
            )
            bdr_notes_input = st.text_area(
                "Initial CRM / BDR Call Notes (Optional)",
                key="target_form_bdr_notes",
                placeholder="Key notes from initial call with prospect merchandising or IT leads...",
                height=100
            )

        btn_col1, btn_col2 = st.columns([3, 1])
        with btn_col1:
            submitted = st.form_submit_button("🚀 Run Pre-Sales Discovery Pipeline", type="primary", width='stretch')
        with btn_col2:
            save_only = st.form_submit_button("💾 Save Profile", type="secondary", width='stretch')

    form_data = {
        "domain": domain_input.strip(),
        "corporate_url": corporate_url_input.strip(),
        "dba": dba_input.strip(),
        "careers_url": careers_input.strip(),
        "revenue": revenue_input.strip(),
        "headcount": headcount_input.strip(),
        "bdr_notes": bdr_notes_input.strip(),
    }

    if save_only:
        if not (dba_input.strip() or domain_input.strip()):
            st.warning("⚠️ Please provide at least a Brand / Account Name or Retail Website before saving.")
        else:
            target_key = selected_scenario_name if is_saved_profile else None
            saved_key = save_profile(form_data, profile_key=target_key)
            st.session_state["pending_scenario_selection"] = saved_key
            st.session_state["selected_scenario_name"] = saved_key
            st.session_state["last_loaded_scenario"] = saved_key
            st.toast(f"Profile '{saved_key}' saved to disk!", icon="💾")
            st.rerun()

    return submitted, form_data
