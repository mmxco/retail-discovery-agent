"""
Retail Enterprise Pre-Sales Discovery Studio
Thin routing coordinator for the Pre-Sales Discovery Pipeline.
Delegates to modular UI controllers:
- ui/sidebar.py: Auth settings, API keys, credentials management
- ui/form.py: Account profile inputs and profile load/save actions
- ui/tabs.py: Tabbed rendering of dossier sections
"""

import streamlit as st

from core.models import DiscoveryDossier
from scraper import scrape_retail_site
from analyzer import analyze_retail_prospect
from exporters.gdocs_exporter import export_dossier_to_google_doc
from exporters.markdown_exporter import export_dossier_to_markdown
from integrations.drive_service import extract_folder_id

from ui.sidebar import render_sidebar
from ui.form import render_account_form, auto_save_profile_on_submit
from ui.tabs import render_dossier_view


def main():
    st.set_page_config(
        page_title="Retail Pre-Sales Discovery Studio",
        page_icon="🛍️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
        .metric-card { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
        .value-wedge { background-color: #eff6ff; border-left: 4px solid #2563eb; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-top: 8px; }
        .pain-card { background-color: #fffaf0; border: 1px solid #feebc8; border-left: 4px solid #dd6b20; border-radius: 6px; padding: 14px; margin-bottom: 12px; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        [data-testid="stMetricLabel"] { font-size: 0.85rem !important; font-weight: 500 !important; }
        [data-testid="stMetricValue"] { font-size: 1.15rem !important; line-height: 1.35 !important; }
        [data-testid="stMetricValue"] > div, [data-testid="stMetricValue"] * {
            font-size: 1.15rem !important; line-height: 1.35 !important; white-space: normal !important;
            overflow: visible !important; text-overflow: unset !important; word-break: break-word !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # 1. Sidebar Configuration
    sidebar_cfg = render_sidebar()

    # 2. Main Header
    st.title("🛍️ Retail Enterprise Pre-Sales Discovery Studio")
    st.markdown(
        "Automate retail pre-sales account intelligence by scraping prospect storefronts, "
        "synthesizing ERP/POS **Value Triangle** pain points with **Gemini 2.5 Flash**, "
        "and exporting an executive brief to **Google Docs**."
    )
    st.markdown("---")

    # 3. Account Form
    submitted, form_data = render_account_form()

    # 4. Pipeline Execution
    if submitted:
        if not sidebar_cfg["pw_available"]:
            st.error("❌ Playwright Headless Browser is unavailable. Click 'Restart / Install Playwright' in sidebar.")
            st.stop()

        if not form_data["domain"]:
            st.error("Please provide a target retailer website domain.")
            st.stop()

        if not sidebar_cfg["api_key"]:
            st.error("A Gemini API Key is required. Please enter it in the sidebar.")
            st.stop()

        auto_save_profile_on_submit(form_data, selected_scenario_name=st.session_state.get("selected_scenario_name"))
        status_container = st.status("Executing Retail Pre-Sales Discovery Pipeline...", expanded=True)

        try:
            # Step 1: Deep crawl storefront
            status_container.write(f"🌐 Scraping storefront at {form_data['domain']}...")
            scrape_result = scrape_retail_site(url=form_data["domain"], prefer_playwright=True, timeout_ms=30000, deep_crawl=True)

            # Step 1b: Optional corporate crawl
            corp_url = form_data["corporate_url"]
            if corp_url and corp_url.rstrip('/') != form_data["domain"].rstrip('/'):
                status_container.write(f"🏢 Scraping corporate portal from {corp_url}...")
                try:
                    corp_res = scrape_retail_site(url=corp_url, prefer_playwright=True, timeout_ms=25000, deep_crawl=True)
                    if corp_res.success:
                        if corp_res.about_us_content.get("markdown_text"):
                            scrape_result.about_us_content = corp_res.about_us_content
                        if corp_res.leadership_content.get("markdown_text"):
                            scrape_result.leadership_content = corp_res.leadership_content
                        if corp_res.press_releases:
                            scrape_result.press_releases = (corp_res.press_releases + scrape_result.press_releases)[:8]
                        if corp_res.tech_signals:
                            scrape_result.tech_signals = sorted(list(set(scrape_result.tech_signals + corp_res.tech_signals)))
                except Exception as c_err:
                    status_container.write(f"⚠️ Corporate crawl note: {c_err}")

            # Step 1c: Optional careers crawl
            careers_content = ""
            if form_data["careers_url"]:
                status_container.write(f"💼 Scraping careers signals from {form_data['careers_url']}...")
                car_res = scrape_retail_site(url=form_data["careers_url"], prefer_playwright=True, timeout_ms=15000, deep_crawl=False)
                if car_res.success:
                    careers_content = car_res.markdown[:10000]

            # Step 2: Gemini B.R.I.E.F. synthesis
            status_container.write(f"🧠 Synthesizing Retail Value Triangle with {sidebar_cfg['model_choice']}...")
            dossier: DiscoveryDossier = analyze_retail_prospect(
                account_name=form_data["dba"] or form_data["domain"],
                domain=form_data["domain"],
                scraped_markdown=scrape_result.markdown,
                tech_signals=scrape_result.tech_signals,
                bdr_notes=form_data["bdr_notes"],
                annual_revenue=form_data["revenue"],
                headcount=form_data["headcount"],
                careers_content=careers_content,
                about_us_content=scrape_result.about_us_content,
                leadership_content=scrape_result.leadership_content,
                press_releases=scrape_result.press_releases,
                corporate_url=corp_url,
                api_key=sidebar_cfg["api_key"],
                model_name=sidebar_cfg["model_choice"],
                disable_ssl_verify=sidebar_cfg["disable_ssl"],
            )

            # Step 3: Google Docs & Markdown export
            google_doc_url, doc_export_error = None, None
            markdown_brief = export_dossier_to_markdown(dossier)

            if sidebar_cfg["google_creds_option"] != "Skip Google Docs (Local Markdown Only)":
                status_container.write("📄 Exporting executive brief to Google Docs...")
                try:
                    active_oauth = sidebar_cfg["oauth_creds"] if getattr(sidebar_cfg["oauth_creds"], "valid", False) else None
                    doc_res = export_dossier_to_google_doc(
                        dossier=dossier,
                        oauth_credentials=active_oauth,
                        credentials_json=sidebar_cfg["service_account_json_content"],
                        folder_id=extract_folder_id(sidebar_cfg["target_folder_id"]),
                        share_with_email=sidebar_cfg["share_recipient_email"] or None,
                    )
                    google_doc_url = doc_res.get("document_url")
                except Exception as doc_err:
                    doc_export_error = str(doc_err)

            status_container.update(label="🎉 Pre-Sales Discovery Pipeline Complete!", state="complete", expanded=False)

            st.session_state["latest_dossier"] = dossier
            st.session_state["google_doc_url"] = google_doc_url
            st.session_state["doc_export_error"] = doc_export_error
            st.session_state["markdown_brief"] = markdown_brief
            st.session_state["raw_scrape"] = scrape_result

        except Exception as e:
            status_container.update(label="❌ Pipeline Execution Failed", state="error", expanded=True)
            st.error(f"Error during discovery execution: {e}")
            st.stop()

    # 5. Dossier Presentation Tabs
    if "latest_dossier" in st.session_state:
        render_dossier_view(
            dossier=st.session_state["latest_dossier"],
            google_doc_url=st.session_state.get("google_doc_url"),
            doc_export_error=st.session_state.get("doc_export_error"),
            markdown_brief=st.session_state.get("markdown_brief", ""),
            raw_scrape=st.session_state.get("raw_scrape"),
            google_creds_option=sidebar_cfg["google_creds_option"],
            oauth_creds=sidebar_cfg["oauth_creds"],
            service_account_json_content=sidebar_cfg["service_account_json_content"],
        )


if __name__ == "__main__":
    main()
