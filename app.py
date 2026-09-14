"""
Retail Enterprise Pre-Sales Discovery Studio
Streamlit dashboard orchestrating the end-to-end Pre-Sales Discovery Pipeline:
1. Playwright DOM Scraping & Clean Markdown Conversion (scraper.py)
2. Gemini 2.5 Flash B.R.I.E.F. Retail Architecture Synthesis (analyzer.py)
3. Google Docs Executive Briefing Export (exporter.py)
"""

import os
import time
import json
from datetime import datetime

# Inject native OS certificate store to eliminate Windows SSL verification errors
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import streamlit as st

from models import DiscoveryDossier
from scraper import scrape_retail_site
from analyzer import analyze_retail_prospect
from exporter import (
    export_dossier_to_google_doc,
    export_dossier_to_markdown,
    validate_service_account,
    get_google_credentials,
)

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Retail Pre-Sales Discovery Studio",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .value-wedge {
        background-color: #eff6ff;
        border-left: 4px solid #2563eb;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        margin-top: 8px;
    }
    .pain-card {
        background-color: #fffaf0;
        border: 1px solid #feebc8;
        border-left: 4px solid #dd6b20;
        border-radius: 6px;
        padding: 14px;
        margin-bottom: 12px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PRESET SCENARIOS
# -----------------------------------------------------------------------------
SCENARIOS = {
    "New Prospect / Blank Canvas": {
        "domain": "", "dba": "", "revenue": "", 
        "headcount": "", "careers_url": "", "bdr_notes": ""
    },
    "Scenario 1: Target - Regional Assortment & Allocation Misalignment": {
        "domain": "https://target.com",
        "dba": "Target",
        "revenue": "$104,780,000,000",
        "headcount": "440,000",
        "careers_url": "https://corporate.target.com/careers",
        "bdr_notes": "Director of Merchandising mentioned regional store clusters are too broad. Southern stores receive heavy winter apparel allocations meant for Northern stores, causing $150.2M in inter-store transfer freight and localized stockouts."
    },
    "Scenario 2: Nordstrom - Omnichannel Fulfillment & Stock Accuracy": {
        "domain": "https://www.nordstrom.com",
        "dba": "Nordstrom",
        "revenue": "$14,800,000,000",
        "headcount": "60,000",
        "careers_url": "https://careers.nordstrom.com",
        "bdr_notes": "VP of Store Operations flagged high BOPIS cancellation rates due to phantom inventory in department stores. Store associates spend ~45 minutes per shift searching backrooms for online pickup items."
    },
    "Scenario 3: Williams-Sonoma - High-AOV Specialty Logistics": {
        "domain": "https://www.williams-sonoma.com",
        "dba": "Williams-Sonoma",
        "revenue": "$8,670,000,000",
        "headcount": "28,000",
        "careers_url": "https://careers.williams-sonomainc.com",
        "bdr_notes": "Head of Omnichannel Logistics reported that high-AOV cookware and furniture orders frequently split into 3+ shipments from disparate fulfillment centers, causing high freight costs and customer dissatisfaction."
    }
}

# -----------------------------------------------------------------------------
# SIDEBAR CONFIGURATION
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Discovery Studio Settings")
    st.markdown("---")

    st.subheader("1. AI Engine (Gemini)")
    env_key = os.environ.get("GEMINI_API_KEY", "")
    has_env_key = bool(env_key)

    api_key_input = st.text_input(
        "Gemini API Key:",
        value=env_key,
        type="password",
        help="Required for Gemini 2.5 Flash B.R.I.E.F. analysis. Can also be set as GEMINI_API_KEY env var."
    )

    if api_key_input:
        st.caption("✅ Gemini API Key provided")
    else:
        st.caption("⚠️ API Key required to run the pipeline")

    model_choice = st.selectbox(
        "Gemini Model",
        options=["gemini-2.5-flash", "gemini-2.5-pro"],
        index=0,
        help="gemini-2.5-flash is optimized for fast, structured discovery generation."
    )

    disable_ssl = st.checkbox(
        "Bypass SSL Verification",
        value=False,
        help="Enable if your corporate proxy, firewall, or antivirus intercepts HTTPS traffic with custom certificates."
    )

    st.markdown("---")
    st.subheader("2. Google Docs Integration")
    google_creds_option = st.radio(
        "Credentials Source",
        options=["Application Default (ADC) / Environment", "Upload Service Account JSON", "Skip Google Docs (Local Markdown Only)"],
        index=0,
    )

    service_account_json_content = None
    if google_creds_option == "Upload Service Account JSON":
        uploaded_sa = st.file_uploader("Service Account JSON", type=["json"], help="Upload GCP Service Account JSON key.")
        if uploaded_sa:
            uploaded_sa.seek(0)
            raw_content = uploaded_sa.read().decode("utf-8")
            with st.spinner("Validating Service Account credentials..."):
                val = validate_service_account(raw_content)

            if val["valid"]:
                service_account_json_content = raw_content
                st.session_state["service_account_json_content"] = raw_content
                if val.get("handshake_successful"):
                    st.success(
                        f"✅ **Authenticated & Verified**\n\n"
                        f"• **Account:** `{val['client_email']}`\n\n"
                        f"• **Project:** `{val['project_id']}`"
                    )
                else:
                    st.info(
                        f"ℹ️ **Credentials Structure Valid**\n\n"
                        f"• **Account:** `{val['client_email']}`\n\n"
                        f"• **Project:** `{val['project_id']}`"
                    )
                    if val.get("warning"):
                        st.caption(f"Note: {val['warning']}")
            else:
                service_account_json_content = None
                if "service_account_json_content" in st.session_state:
                    del st.session_state["service_account_json_content"]
                st.error(f"❌ **Invalid Service Account:**\n\n{val['error']}")
        else:
            if "service_account_json_content" in st.session_state:
                del st.session_state["service_account_json_content"]
    elif google_creds_option == "Application Default (ADC) / Environment":
        adc = get_google_credentials()
        if adc:
            st.caption("✅ Google Cloud credentials detected in environment.")
        else:
            st.caption("ℹ️ No default GCP credentials detected. Upload a Service Account JSON above or use local Markdown export.")

    st.markdown("---")
    st.subheader("3. Scraper Settings")
    prefer_playwright = st.checkbox(
        "Use Playwright Headless Browser",
        value=True,
        help="Renders dynamic client-side JS storefronts. Automatically falls back to HTTP requests if needed."
    )

    st.markdown("---")
    st.caption("Retail Discovery Agent v2.0 • Powered by Google GenAI & Playwright")

# -----------------------------------------------------------------------------
# MAIN DASHBOARD INTERFACE
# -----------------------------------------------------------------------------
st.title("🛍️ Retail Enterprise Pre-Sales Discovery Studio")
st.markdown(
    "Automate retail pre-sales account intelligence by scraping prospect storefronts, "
    "synthesizing ERP/POS **Value Triangle** pain points with **Gemini 2.5 Flash**, "
    "and exporting an executive brief to **Google Docs**."
)

st.markdown("---")

# Scenario Selector
selected_scenario_name = st.selectbox(
    "Load Preset Demo Scenario:",
    options=list(SCENARIOS.keys()),
    index=1,
)
scenario_data = SCENARIOS[selected_scenario_name]

# Context Form
with st.form("discovery_pipeline_form"):
    st.subheader("Target Account Profile")
    col1, col2 = st.columns(2)

    with col1:
        domain_input = st.text_input(
            "Retailer Website / Domain *",
            value=scenario_data.get("domain", ""),
            placeholder="https://target.com"
        )
        dba_input = st.text_input(
            "Brand / Account Name *",
            value=scenario_data.get("dba", ""),
            placeholder="Target"
        )
        careers_input = st.text_input(
            "Careers or Corporate URL (Optional)",
            value=scenario_data.get("careers_url", ""),
            placeholder="https://corporate.target.com/careers"
        )

    with col2:
        revenue_input = st.text_input(
            "Estimated Annual Revenue",
            value=scenario_data.get("revenue", ""),
            placeholder="$1,000,000,000"
        )
        headcount_input = st.text_input(
            "Employee Headcount / Store Count",
            value=scenario_data.get("headcount", ""),
            placeholder="10,000 employees / 250 stores"
        )
        bdr_notes_input = st.text_area(
            "Initial CRM / BDR Call Notes (Optional)",
            value=scenario_data.get("bdr_notes", ""),
            placeholder="Key notes from initial call with prospect merchandising or IT leads...",
            height=100
        )

    submitted = st.form_submit_button("🚀 Run Pre-Sales Discovery Pipeline", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# PIPELINE ORCHESTRATION & EXECUTION
# -----------------------------------------------------------------------------
if submitted:
    if not domain_input.strip():
        st.error("Please provide a target retailer website domain.")
        st.stop()

    if not api_key_input.strip():
        st.error("A Gemini API Key is required. Please enter it in the sidebar.")
        st.stop()

    status_container = st.status("Executing Retail Pre-Sales Discovery Pipeline...", expanded=True)

    try:
        # Step 1: Scrape storefront
        status_container.write(f"🌐 Scraping storefront DOM and extracting retail tech signals from {domain_input}...")
        scrape_result = scrape_retail_site(
            url=domain_input.strip(),
            prefer_playwright=prefer_playwright,
            timeout_ms=30000,
        )

        careers_content = ""
        if careers_input.strip():
            status_container.write(f"💼 Scraping careers & job signals from {careers_input}...")
            careers_res = scrape_retail_site(
                url=careers_input.strip(),
                prefer_playwright=False,  # Fast HTTP for careers
                timeout_ms=15000,
            )
            if careers_res.success:
                careers_content = careers_res.markdown[:10000]

        status_container.write(
            f"✅ Scraped {len(scrape_result.markdown):,} chars of cleaned Markdown. "
            f"Detected signals: {', '.join(scrape_result.tech_signals) or 'None'}"
        )

        # Step 2: Run Gemini 2.5 Flash B.R.I.E.F. analysis
        status_container.write(f"🧠 Synthesizing Retail ERP & POS Value Triangle Intelligence with {model_choice}...")
        dossier: DiscoveryDossier = analyze_retail_prospect(
            account_name=dba_input.strip() or domain_input.strip(),
            domain=domain_input.strip(),
            scraped_markdown=scrape_result.markdown,
            tech_signals=scrape_result.tech_signals,
            bdr_notes=bdr_notes_input.strip(),
            annual_revenue=revenue_input.strip(),
            headcount=headcount_input.strip(),
            careers_content=careers_content,
            api_key=api_key_input.strip(),
            model_name=model_choice,
            disable_ssl_verify=disable_ssl,
        )
        status_container.write("✅ Structured DiscoveryDossier successfully generated!")

        # Step 3: Google Docs Export
        google_doc_url = None
        doc_export_error = None
        markdown_brief = export_dossier_to_markdown(dossier)

        if google_creds_option != "Skip Google Docs (Local Markdown Only)":
            status_container.write("📄 Exporting styled executive brief to Google Docs API...")
            try:
                doc_res = export_dossier_to_google_doc(
                    dossier=dossier,
                    credentials_json=service_account_json_content,
                )
                google_doc_url = doc_res.get("document_url")
                status_container.write(f"✅ Google Doc created: {google_doc_url}")
            except Exception as doc_err:
                doc_export_error = str(doc_err)
                status_container.write(f"⚠️ Google Docs export note: {doc_export_error}")

        status_container.update(label="🎉 Pre-Sales Discovery Pipeline Complete!", state="complete", expanded=False)

        # Save to session state for persistence
        st.session_state["latest_dossier"] = dossier
        st.session_state["google_doc_url"] = google_doc_url
        st.session_state["doc_export_error"] = doc_export_error
        st.session_state["markdown_brief"] = markdown_brief
        st.session_state["raw_scrape"] = scrape_result

    except Exception as e:
        status_container.update(label="❌ Pipeline Execution Failed", state="error", expanded=True)
        st.error(f"Error during discovery execution: {e}")
        st.stop()

# -----------------------------------------------------------------------------
# DOSSIER PRESENTATION & ACTIONS
# -----------------------------------------------------------------------------
if "latest_dossier" in st.session_state:
    dossier: DiscoveryDossier = st.session_state["latest_dossier"]
    google_doc_url = st.session_state.get("google_doc_url")
    doc_export_error = st.session_state.get("doc_export_error")
    markdown_brief = st.session_state.get("markdown_brief", "")
    raw_scrape = st.session_state.get("raw_scrape")

    st.markdown("---")
    st.header(f"Executive Discovery Brief for {dossier.account_name}")

    # Top CTA Bar
    cta_col1, cta_col2 = st.columns([3, 1])
    retry_upload_clicked = False

    with cta_col1:
        if google_doc_url:
            st.success("📄 **Live Google Doc Generated Successfully!**")
            btn_col1, btn_col2 = st.columns([2, 1])
            with btn_col1:
                st.link_button(
                    label="🚀 Open Formatted Google Doc Brief ↗",
                    url=google_doc_url,
                    type="primary",
                    use_container_width=True,
                )
            with btn_col2:
                retry_upload_clicked = st.button(
                    "🔄 Retry Google Docs Upload",
                    use_container_width=True,
                    help="Re-upload or update the Google Doc brief.",
                )
        else:
            st.info("ℹ️ Google Doc export omitted or awaiting service account. Download the executive Markdown brief below, or retry uploading to Google Docs.")
            if doc_export_error:
                st.caption(f"Google Docs API note: {doc_export_error}")
            retry_upload_clicked = st.button(
                "🔄 Retry Google Docs Upload",
                type="primary",
                use_container_width=False,
                help="Attempt to export the brief to Google Docs with current credentials.",
            )

    with cta_col2:
        safe_name = dossier.account_name.replace(" ", "_")
        st.download_button(
            label="⬇️ Download Markdown Brief",
            data=markdown_brief,
            file_name=f"{safe_name}_Executive_Discovery_Brief.md",
            mime="text/markdown",
            use_container_width=True,
        )

    # Handle Retry Google Docs Upload action
    if retry_upload_clicked:
        with st.spinner(f"Exporting Executive Discovery Brief for {dossier.account_name} to Google Docs..."):
            try:
                creds_payload = service_account_json_content or st.session_state.get("service_account_json_content")
                doc_res = export_dossier_to_google_doc(
                    dossier=dossier,
                    credentials_json=creds_payload,
                )
                st.session_state["google_doc_url"] = doc_res.get("document_url")
                st.session_state["doc_export_error"] = None
                st.rerun()
            except Exception as retry_err:
                st.session_state["doc_export_error"] = str(retry_err)
                st.error(f"❌ Google Docs upload failed: {retry_err}")

    # Tabbed Dossier View
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Executive Overview",
        "🛠️ Tech Stack & Architecture",
        "🔥 Value Triangle Pain Points",
        "❓ Discovery Questions",
        "🎯 Recommended Strategy",
        "🌐 Scraped Signals & DOM",
    ])

    # Tab 1: Executive Overview
    with tab1:
        st.subheader("Account Positioning & Scope")
        ov_col1, ov_col2, ov_col3 = st.columns(3)
        with ov_col1:
            st.metric("Retail Segment", dossier.retail_segment)
        with ov_col2:
            st.metric("Estimated Scale", dossier.estimated_scale)
        with ov_col3:
            st.metric("Domain", dossier.domain)

        st.markdown("### Strategic Executive Summary")
        st.write(dossier.executive_summary)

    # Tab 2: Tech Stack
    with tab2:
        st.subheader("Identified Enterprise Footprint")
        ts = dossier.tech_stack

        tc1, tc2 = st.columns(2)
        with tc1:
            st.markdown(f"**E-Commerce Platform:** `{ts.ecommerce_platform or 'Undetected / Custom'}`")
            st.markdown(f"**Point of Sale (POS):** `{ts.point_of_sale or 'Legacy Architecture'}`")
            st.markdown(f"**Core ERP / Merchandising:** `{ts.erp_core or 'Tier-1 Legacy Suite'}`")
        with tc2:
            st.markdown(f"**Order Management (DOM/OMS):** `{ts.order_management or 'Distributed Monolith'}`")
            st.markdown(f"**Warehouse & Supply Chain (WMS):** `{ts.warehouse_supply_chain or 'Legacy WMS'}`")
            st.markdown(f"**Analytics & Customer:** `{', '.join(ts.analytics_and_marketing) or 'Not detected'}`")

        if ts.detected_technologies:
            st.markdown("#### Detected Technology Footprints")
            st.write(", ".join([f"`{t}`" for t in ts.detected_technologies]))

        if ts.architecture_signals:
            st.markdown("#### Architectural Insights")
            for sig in ts.architecture_signals:
                st.markdown(f"- {sig}")

    # Tab 3: Value Triangle Pain Points
    with tab3:
        st.subheader("Executive Pain Points: The Value Triangle")
        st.caption("Mapping Technical Gaps directly to Operational Friction and Financial Impact.")

        for i, p in enumerate(dossier.pain_points, start=1):
            with st.container():
                st.markdown(f"### {i}. {p.category}")
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    st.markdown("**🔧 Technical Gap**")
                    st.write(p.technical_gap)
                with pc2:
                    st.markdown("**⚡ Operational Friction**")
                    st.write(p.operational_friction)
                with pc3:
                    st.markdown("**💰 Financial Impact**")
                    st.write(f"*{p.financial_impact}*")

                if p.affected_executives:
                    st.caption(f"**Impacted Stakeholders:** {', '.join(p.affected_executives)}")
                st.markdown("---")

    # Tab 4: Discovery Questions
    with tab4:
        st.subheader("Persona-Specific Discovery Questions")
        st.caption("Strategic questions engineered for pre-sales discovery calls.")

        for i, q in enumerate(dossier.discovery_questions, start=1):
            with st.expander(f"**{q.target_persona}** — *{q.theme}*", expanded=True):
                st.markdown(f"#### Question:")
                st.info(f'"{q.question}"')

                q_col1, q_col2 = st.columns(2)
                with q_col1:
                    st.markdown("**👂 What to Listen For:**")
                    st.write(q.what_to_listen_for)
                with q_col2:
                    st.markdown("**⚔️ Value Wedge (Differentiation):**")
                    st.write(q.value_wedge)

    # Tab 5: Recommended Strategy
    with tab5:
        st.subheader("Pre-Sales Engagement Blueprint")
        st.write(dossier.recommended_discovery_strategy)

    # Tab 6: Scraped Signals
    with tab6:
        st.subheader("Scraped Signals & DOM Summary")
        if raw_scrape:
            st.markdown(f"- **Title:** {raw_scrape.title}")
            st.markdown(f"- **Engine Used:** `{raw_scrape.engine_used}`")
            st.markdown(f"- **Meta Description:** {raw_scrape.meta_description}")
            st.markdown(f"- **Detected Signatures:** `{', '.join(raw_scrape.tech_signals)}`")
            st.text_area("Cleaned Markdown Content", value=raw_scrape.markdown[:10000], height=400)
