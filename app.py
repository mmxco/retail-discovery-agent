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
from scraper import scrape_retail_site, check_playwright_availability, restart_playwright
from analyzer import analyze_retail_prospect
from exporter import (
    export_dossier_to_google_doc,
    export_dossier_to_markdown,
    validate_service_account,
    verify_client_secret,
    get_user_oauth_credentials,
    get_authenticated_user_info,
    clear_oauth_token,
    start_oauth_desktop_flow,
    get_google_credentials,
    extract_folder_id,
    list_drive_folders,
    validate_drive_folder,
    create_drive_folder,
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
    /* Dial down st.metric sizing and prevent truncation */
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        font-weight: 500 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
        line-height: 1.35 !important;
    }
    [data-testid="stMetricValue"] > div,
    [data-testid="stMetricValue"] * {
        font-size: 1.15rem !important;
        line-height: 1.35 !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
        word-break: break-word !important;
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

    oauth_creds = None
    service_account_json_content = None
    adc = None

    with st.expander("🔑 Credentials Source & Auth Setup", expanded=False):
        google_creds_option = st.radio(
            "Credentials Source",
            options=[
                "OAuth 2.0 User Credentials (Desktop App) [Recommended]",
                "Upload Service Account JSON (Legacy)",
                "Application Default (ADC) / Environment",
                "Skip Google Docs (Local Markdown Only)",
            ],
            index=0,
            key="google_creds_option_radio",
        )

        if google_creds_option == "OAuth 2.0 User Credentials (Desktop App) [Recommended]":
            local_cs_exists = os.path.isfile("client_secret.json")
            if local_cs_exists and "oauth_client_secret_json" not in st.session_state:
                try:
                    with open("client_secret.json", "r", encoding="utf-8") as cs_file:
                        st.session_state["oauth_client_secret_json"] = cs_file.read()
                except Exception:
                    pass

            uploaded_cs = st.file_uploader(
                "OAuth 2.0 Client Secret (client_secret.json)",
                type=["json"],
                help="Upload your Google Cloud OAuth 2.0 Client Secret JSON (Desktop App configuration).",
            )
            if uploaded_cs:
                uploaded_cs.seek(0)
                st.session_state["oauth_client_secret_json"] = uploaded_cs.read().decode("utf-8")

            raw_cs = st.session_state.get("oauth_client_secret_json")
            v_secret = verify_client_secret(raw_cs) if raw_cs else None

            if v_secret:
                if v_secret["valid"]:
                    st.success(
                        f"✅ **Client Secret Verified ({v_secret['app_type']})**\n\n"
                        f"• **Project:** `{v_secret['project_id'] or 'detected'}`\n\n"
                        f"• **Client ID:** `{v_secret['client_id'][:28]}...`"
                    )
                else:
                    st.error(f"❌ **Invalid Client Secret:**\n\n{v_secret['error']}")
            elif not local_cs_exists:
                st.info("ℹ️ Upload a `client_secret.json` from Google Cloud Console (APIs & Services > Credentials > OAuth Client ID: Desktop App).")

            # Inspect token lifecycle
            oauth_creds = get_user_oauth_credentials(
                client_secret_json=raw_cs,
                run_flow_if_needed=False,
            )

            if oauth_creds and oauth_creds.valid:
                if "oauth_user_info" not in st.session_state or not st.session_state.get("oauth_user_info"):
                    st.session_state["oauth_user_info"] = get_authenticated_user_info(oauth_creds)
                u_info = st.session_state.get("oauth_user_info", {})
                u_email = u_info.get("email") or "Authenticated User"
                u_name = u_info.get("display_name")
                display_str = f"**{u_name}** (`{u_email}`)" if u_name else f"`{u_email}`"
                st.markdown(
                    f"<div style='background-color:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; padding:10px 14px; margin-bottom:10px;'>"
                    f"👤 <strong>Signed In with Google:</strong><br/>"
                    f"<span style='color:#15803d; font-weight:600;'>{display_str}</span><br/>"
                    f"<span style='color:#65a30d; font-size:12px;'>Documents will be saved in your personal Google Drive (15 GB+ quota).</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if st.button("🔄 Sign Out / Switch Google Account", width='stretch'):
                    clear_oauth_token()
                    if "oauth_user_info" in st.session_state:
                        del st.session_state["oauth_user_info"]
                    if "oauth_flow_server" in st.session_state:
                        try:
                            st.session_state["oauth_flow_server"].shutdown()
                        except Exception:
                            pass
                        del st.session_state["oauth_flow_server"]
                    st.rerun()
            else:
                flow_server = st.session_state.get("oauth_flow_server")
                if flow_server is not None:
                    # Check if background thread or manual exchange completed
                    if flow_server.is_authenticated or os.path.isfile("token.json"):
                        fresh_creds = get_user_oauth_credentials(token_path="token.json", run_flow_if_needed=False)
                        if fresh_creds and fresh_creds.valid:
                            st.session_state["oauth_user_info"] = get_authenticated_user_info(fresh_creds)
                            try:
                                flow_server.shutdown()
                            except Exception:
                                pass
                            del st.session_state["oauth_flow_server"]
                            st.success("Successfully authenticated with Google!")
                            st.rerun()
                    elif flow_server.error:
                        st.error(f"❌ **Authentication Note:** {flow_server.error}")
                        if st.button("🔄 Restart Sign-In", width='stretch'):
                            try:
                                flow_server.shutdown()
                            except Exception:
                                pass
                            del st.session_state["oauth_flow_server"]
                            st.rerun()
                    else:
                        # Non-blocking active authorization state
                        st.markdown(
                            "<div style='background-color:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; padding:10px 12px; margin-bottom:12px;'>"
                            "<strong style='color:#1e40af;'>🔐 Google Sign-In Ready</strong><br/>"
                            "<span style='font-size:12px; color:#1e3a8a;'>"
                            "Click below to open Google Sign-In in a new Chrome tab. "
                            "Sign in, allow Drive access, then return here."
                            "</span></div>",
                            unsafe_allow_html=True,
                        )
                        st.link_button(
                            "🌐 Open Google Sign-In in New Tab ↗",
                            url=flow_server.auth_url,
                            type="primary",
                            width='stretch',
                        )

                        c_auth1, c_auth2 = st.columns([1, 1])
                        with c_auth1:
                            if st.button("🔄 Check Login Status", width='stretch', help="Check if sign-in is complete in your browser"):
                                fresh_creds = get_user_oauth_credentials(token_path="token.json", run_flow_if_needed=False)
                                if (flow_server.is_authenticated or os.path.isfile("token.json")) and fresh_creds and fresh_creds.valid:
                                    st.session_state["oauth_user_info"] = get_authenticated_user_info(fresh_creds)
                                    try:
                                        flow_server.shutdown()
                                    except Exception:
                                        pass
                                    del st.session_state["oauth_flow_server"]
                                    st.success("Successfully authenticated!")
                                    st.rerun()
                                else:
                                    st.info("Waiting for Google authorization in browser...")
                        with c_auth2:
                            if st.button("❌ Cancel", width='stretch'):
                                try:
                                    flow_server.shutdown()
                                except Exception:
                                    pass
                                del st.session_state["oauth_flow_server"]
                                st.rerun()

                        with st.expander("Trouble with automatic redirect? Click here"):
                            st.caption(
                                "If your browser cannot connect to `localhost` after signing in, copy the final URL from your "
                                "browser's address bar (or the `code=` parameter value) and paste it below:"
                            )
                            pasted_auth = st.text_input("Redirect URL or Code", key="oauth_pasted_manual_code", placeholder="http://localhost:.../?code=4/0A...")
                            if st.button("Submit Code / URL", width='stretch'):
                                if pasted_auth and flow_server.manual_exchange(pasted_auth):
                                    fresh_creds = get_user_oauth_credentials(token_path="token.json", run_flow_if_needed=False)
                                    if fresh_creds and fresh_creds.valid:
                                        st.session_state["oauth_user_info"] = get_authenticated_user_info(fresh_creds)
                                        try:
                                            flow_server.shutdown()
                                        except Exception:
                                            pass
                                        del st.session_state["oauth_flow_server"]
                                        st.success("Successfully authenticated!")
                                        st.rerun()
                                else:
                                    st.error(f"Failed to exchange code: {flow_server.error or 'Invalid authorization input'}")
                else:
                    if v_secret and v_secret["valid"]:
                        if st.button("🔑 Sign In with Google Account", type="primary", width='stretch'):
                            try:
                                cs_cfg = v_secret.get("client_config") or raw_cs
                                server = start_oauth_desktop_flow(client_secret_data_or_path=cs_cfg)
                                st.session_state["oauth_flow_server"] = server
                                st.rerun()
                            except Exception as flow_err:
                                st.error(f"❌ Failed to start authorization flow: {flow_err}")
                    else:
                        st.caption("ℹ️ Upload and verify a `client_secret.json` to enable Google Sign-In.")

        elif google_creds_option == "Upload Service Account JSON (Legacy)":
            uploaded_sa = st.file_uploader("Service Account JSON", type=["json"], help="Upload GCP Service Account JSON key.")
            if uploaded_sa:
                uploaded_sa.seek(0)
                raw_content = uploaded_sa.read().decode("utf-8")
                if raw_content != st.session_state.get("service_account_json_content"):
                    with st.spinner("Validating Service Account credentials..."):
                        val = validate_service_account(raw_content)

                    if val["valid"]:
                        service_account_json_content = raw_content
                        st.session_state["service_account_json_content"] = raw_content
                        st.session_state["service_account_project_id"] = val.get("project_id", "")
                        st.session_state["service_account_client_email"] = val.get("client_email", "")
                        st.session_state["service_account_handshake"] = val.get("handshake_successful", False)
                    else:
                        service_account_json_content = None
                        if "service_account_json_content" in st.session_state:
                            del st.session_state["service_account_json_content"]
                        st.error(f"❌ **Invalid Service Account:**\n\n{val['error']}")
                else:
                    service_account_json_content = raw_content
            elif "service_account_json_content" in st.session_state:
                service_account_json_content = st.session_state["service_account_json_content"]

            if service_account_json_content:
                sa_email = st.session_state.get("service_account_client_email", "")
                sa_proj = st.session_state.get("service_account_project_id", "")
                is_hs = st.session_state.get("service_account_handshake", True)
                status_text = "Authenticated & Verified" if is_hs else "Credentials Structure Valid"
                st.success(
                    f"✅ **{status_text}**\n\n"
                    f"• **Account:** `{sa_email}`\n\n"
                    f"• **Project:** `{sa_proj}`"
                )
        elif google_creds_option == "Application Default (ADC) / Environment":
            adc = get_google_credentials()
            if adc:
                st.caption("✅ Google Cloud credentials detected in environment.")
            else:
                st.caption("ℹ️ No default GCP credentials detected. Upload a client_secret or Service Account JSON above, or use local Markdown export.")

    target_folder_id = st.session_state.get("target_folder_id", "")
    target_folder_name = st.session_state.get("target_folder_name", "")
    target_folder_url = st.session_state.get("target_folder_url", "")
    share_email_input = ""

    if google_creds_option != "Skip Google Docs (Local Markdown Only)":
        st.markdown("---")
        st.markdown("#### 📁 Drive Destination & Folder Browser")
        active_sa_email = st.session_state.get("service_account_client_email", "")
        is_oauth_mode = google_creds_option.startswith("OAuth 2.0")
        oauth_active = bool(oauth_creds and oauth_creds.valid) if is_oauth_mode else False
        sa_active = bool(service_account_json_content)
        adc_active = bool(adc) if google_creds_option == "Application Default (ADC) / Environment" else False
        creds_available = oauth_active or sa_active or adc_active

        if not creds_available:
            hint_str = "Sign in via OAuth 2.0 or upload Service Account credentials above to browse Google Drive folders."
            st.info(f"ℹ️ {hint_str}")
            manual_id = st.text_input(
                "Target Google Drive Folder ID (Manual)",
                value=target_folder_id,
                help="Paste the Folder ID from your Google Drive URL.",
                placeholder="1a2b3c4d5e...",
            )
            if manual_id != target_folder_id:
                st.session_state["target_folder_id"] = manual_id.strip()
                st.session_state["target_folder_name"] = manual_id.strip()
        else:
            if oauth_active:
                u_info = st.session_state.get("oauth_user_info", {})
                u_email = u_info.get("email") or "Your Google Account"
                st.markdown(
                    f"<div style='background-color:#f0fdf4; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:12px; border: 1px solid #bbf7d0;'>"
                    f"👤 <strong>Active User Account:</strong> <code>{u_email}</code><br/>"
                    f"<span style='color:#15803d;'>Documents created are owned by you with personal storage quota.</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            elif sa_active and active_sa_email:
                st.markdown(
                    f"<div style='background-color:#f1f5f9; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:12px; border: 1px solid #cbd5e1;'>"
                    f"🔑 <strong>Active Service Account:</strong> <code>{active_sa_email}</code><br/>"
                    f"<span style='color:#64748b;'>Share existing Google Drive folders with this address as <strong>Editor</strong>.</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            folder_mode = st.radio(
                "Folder Selection Method",
                options=["📂 Browse Accessible Folders", "🔗 Paste Folder Link / ID", "➕ Create New Folder"],
                index=0,
                key="folder_selection_mode",
            )

            if folder_mode == "📂 Browse Accessible Folders":
                col_b1, col_b2 = st.columns([3, 1])
                with col_b1:
                    st.caption("Select from available folders:")
                with col_b2:
                    if st.button("🔄 Refresh", help="Re-scan Google Drive for accessible folders", width='stretch'):
                        st.session_state["drive_folders_cache"] = None

                if st.session_state.get("drive_folders_cache") is None:
                    with st.spinner("Querying Google Drive API for folders..."):
                        f_data = list_drive_folders(
                            oauth_credentials=oauth_creds if oauth_active else None,
                            credentials_json=service_account_json_content,
                        )
                        st.session_state["drive_folders_cache"] = f_data
                else:
                    f_data = st.session_state.get("drive_folders_cache", {})

                if not f_data.get("success", False):
                    st.error(f"⚠️ {f_data.get('error')}")
                else:
                    folder_options = []
                    for sd in f_data.get("shared_drives", []):
                        folder_options.append((sd["id"], f"🗂️ [Shared Drive] {sd['name']}", sd.get("web_view_link", "")))
                    for f in f_data.get("folders", []):
                        folder_options.append((f["id"], f"📁 {f['name']}", f.get("web_view_link", "")))

                    if folder_options:
                        cur_target = st.session_state.get("target_folder_id", "")
                        id_list = [opt[0] for opt in folder_options]
                        selected_idx = id_list.index(cur_target) if cur_target in id_list else 0

                        chosen_option = st.selectbox(
                            "Target Destination Folder",
                            options=folder_options,
                            index=selected_idx,
                            format_func=lambda x: x[1],
                            help="Select an accessible Google Drive folder or Shared Drive.",
                        )
                        st.session_state["target_folder_id"] = chosen_option[0]
                        st.session_state["target_folder_name"] = chosen_option[1]
                        st.session_state["target_folder_url"] = chosen_option[2]
                    else:
                        if oauth_active:
                            st.info(
                                "ℹ️ **No App Folders Found**\n\n"
                                "Under the `drive.file` scope, Google Drive lists folders created with this app. "
                                "You can create a dedicated 'Retail Discovery Briefs' folder below, or export directly to root 'My Drive'."
                            )
                            if st.button("📁 Create 'Retail Discovery Briefs' Folder in Drive", type="primary", width='stretch'):
                                with st.spinner("Creating 'Retail Discovery Briefs' folder in your Google Drive..."):
                                    c_res = create_drive_folder(
                                        folder_name="Retail Discovery Briefs",
                                        oauth_credentials=oauth_creds,
                                    )
                                if c_res.get("success"):
                                    st.session_state["target_folder_id"] = c_res["id"]
                                    st.session_state["target_folder_name"] = f"📁 {c_res['name']}"
                                    st.session_state["target_folder_url"] = c_res.get("web_view_link", "")
                                    st.session_state["drive_folders_cache"] = None
                                    st.success(f"✅ Folder **{c_res['name']}** created and selected!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {c_res.get('error')}")
                        else:
                            st.warning(
                                f"⚠️ **No Shared Folders Detected**\n\n"
                                f"Google Service Accounts have **0 MB** of personal Drive quota and cannot create files directly at root.\n\n"
                                f"**Quick Resolution:**\n"
                                f"1. In Google Drive, open or create a folder (e.g. *Retail Discovery Briefs*).\n"
                                f"2. Click **Share** and add `{active_sa_email or 'your service account'}` as **Editor**.\n"
                                f"3. Click **'🔄 Refresh'** above to select it!"
                            )
                            st.session_state["target_folder_id"] = ""
                            st.session_state["target_folder_name"] = ""
                            st.session_state["target_folder_url"] = ""

            elif folder_mode == "🔗 Paste Folder Link / ID":
                pasted_val = st.text_input(
                    "Google Drive Folder URL or ID",
                    value=st.session_state.get("raw_pasted_folder_input", st.session_state.get("target_folder_id", "")),
                    placeholder="https://drive.google.com/drive/folders/1a2b... or 1a2b...",
                    help="Paste any Google Drive folder URL or ID.",
                    key="pasted_folder_input",
                )
                # Automatically extract folder ID whenever text is typed/pasted
                if pasted_val.strip():
                    st.session_state["raw_pasted_folder_input"] = pasted_val.strip()
                    extracted_id = extract_folder_id(pasted_val.strip())
                    if extracted_id:
                        st.session_state["target_folder_id"] = extracted_id
                        if not st.session_state.get("target_folder_name") or st.session_state.get("target_folder_name", "").startswith("📁 ID:"):
                            st.session_state["target_folder_name"] = f"📁 ID: {extracted_id[:16]}..."

                if st.button("🔍 Validate & Select Folder", width='stretch'):
                    if pasted_val.strip():
                        with st.spinner("Validating folder permissions with Google Drive API..."):
                            v_res = validate_drive_folder(
                                pasted_val.strip(),
                                oauth_credentials=oauth_creds if oauth_active else None,
                                credentials_json=service_account_json_content,
                            )
                        if v_res.get("valid"):
                            st.session_state["target_folder_id"] = v_res["id"]
                            st.session_state["target_folder_name"] = f"📁 {v_res['name']}"
                            st.session_state["target_folder_url"] = v_res.get("web_view_link", "")
                            st.session_state["folder_val_status"] = {"type": "success", "msg": f"✅ Verified folder: **{v_res['name']}**"}
                            st.rerun()
                        else:
                            st.session_state["folder_val_status"] = {"type": "error", "msg": f"❌ {v_res.get('error')}"}
                    else:
                        st.session_state["target_folder_id"] = ""
                        st.session_state["target_folder_name"] = "📁 [Default] My Drive (Root / No Folder)"
                        st.session_state["target_folder_url"] = ""
                        st.session_state["folder_val_status"] = {"type": "info", "msg": "Defaulting to root My Drive."}
                        st.rerun()

                if "folder_val_status" in st.session_state:
                    f_stat = st.session_state["folder_val_status"]
                    if f_stat["type"] == "success":
                        st.success(f_stat["msg"])
                    elif f_stat["type"] == "error":
                        st.error(f_stat["msg"])
                    else:
                        st.info(f_stat["msg"])

            elif folder_mode == "➕ Create New Folder":
                new_f_name = st.text_input(
                    "New Folder Name",
                    placeholder="e.g. Retail Discovery Briefs 2026",
                    help="Creates a dedicated folder in Google Drive.",
                )
                if st.button("📁 Create & Select Folder", type="primary", width='stretch'):
                    if new_f_name.strip():
                        with st.spinner(f"Creating folder '{new_f_name.strip()}' in Google Drive..."):
                            s_mail = st.session_state.get("share_recipient_email", "").strip() or None
                            c_res = create_drive_folder(
                                folder_name=new_f_name.strip(),
                                oauth_credentials=oauth_creds if oauth_active else None,
                                credentials_json=service_account_json_content,
                                share_with_email=s_mail,
                            )
                        if c_res.get("success"):
                            st.session_state["target_folder_id"] = c_res["id"]
                            st.session_state["target_folder_name"] = f"📁 {c_res['name']}"
                            st.session_state["target_folder_url"] = c_res.get("web_view_link", "")
                            st.session_state["drive_folders_cache"] = None
                            st.success(f"✅ Folder **{c_res['name']}** created and selected as destination!")
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to create folder: {c_res.get('error')}")
                    else:
                        st.warning("Please enter a folder name.")

            # Active Folder Status Card
            cur_id = st.session_state.get("target_folder_id", "")
            cur_name = st.session_state.get("target_folder_name", "")
            cur_url = st.session_state.get("target_folder_url", "")
            st.markdown("---")
            if cur_id:
                link_markup = f" • [Open in Drive ↗]({cur_url})" if cur_url else ""
                st.markdown(f"🎯 **Active Target:** `{cur_name or cur_id}`{link_markup}")
            else:
                st.markdown("🎯 **Active Target:** `My Drive (Default Root)`")

        share_email_input = st.text_input(
            "Share Directly with Email",
            value=st.session_state.get("share_recipient_email", ""),
            help="Enter your Google Workspace or Gmail address to grant edit access to the generated brief.",
            placeholder="you@company.com",
        )
        st.session_state["share_recipient_email"] = share_email_input

    st.markdown("---")
    st.subheader("3. Playwright Headless Browser")
    pw_available, pw_err_msg = check_playwright_availability()

    if pw_available:
        st.success("✅ **Playwright Headless Browser Active**")
    else:
        st.error(
            f"❌ **Playwright Headless Browser Unavailable**\n\n"
            f"The application requires Playwright Headless Browser to execute storefront discovery.\n\n"
            f"**Error Details:** `{pw_err_msg}`"
        )
        if st.button("🔄 Restart / Install Playwright", type="primary", width="stretch"):
            with st.spinner("Installing and restarting Playwright Chromium binaries..."):
                p_ok, p_res = restart_playwright()
            if p_ok:
                st.success(f"✅ {p_res}")
                st.rerun()
            else:
                st.error(f"❌ {p_res}")

    prefer_playwright = pw_available

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

    submitted = st.form_submit_button("🚀 Run Pre-Sales Discovery Pipeline", type="primary", width='stretch')

# -----------------------------------------------------------------------------
# PIPELINE ORCHESTRATION & EXECUTION
# -----------------------------------------------------------------------------
if submitted:
    if not pw_available:
        st.error("❌ Cannot run discovery pipeline: Playwright Headless Browser is unavailable. Please click **'🔄 Restart / Install Playwright'** in the sidebar to fix.")
        st.stop()

    if not domain_input.strip():
        st.error("Please provide a target retailer website domain.")
        st.stop()

    if not api_key_input.strip():
        st.error("A Gemini API Key is required. Please enter it in the sidebar.")
        st.stop()

    status_container = st.status("Executing Retail Pre-Sales Discovery Pipeline...", expanded=True)

    try:
        # Step 1: Deep Crawl storefront, About Us, Leadership & Press Releases
        status_container.write(f"🌐 Executing multi-page retail crawl (Storefront, About Us, Leadership, Press) on {domain_input}...")
        scrape_result = scrape_retail_site(
            url=domain_input.strip(),
            prefer_playwright=True,
            timeout_ms=30000,
            deep_crawl=True,
        )

        careers_content = ""
        if careers_input.strip():
            status_container.write(f"💼 Scraping careers & job signals from {careers_input}...")
            careers_res = scrape_retail_site(
                url=careers_input.strip(),
                prefer_playwright=True,
                timeout_ms=15000,
                deep_crawl=False,
            )
            if careers_res.success:
                careers_content = careers_res.markdown[:10000]

        about_len = len(scrape_result.about_us_content.get("markdown_text", ""))
        lead_len = len(scrape_result.leadership_content.get("markdown_text", ""))
        press_count = len(scrape_result.press_releases)
        status_container.write(
            f"✅ Crawled {len(scrape_result.markdown):,} chars Storefront, "
            f"{about_len:,} chars About Us, {lead_len:,} chars Leadership, and {press_count} Press Releases. "
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
            about_us_content=scrape_result.about_us_content,
            leadership_content=scrape_result.leadership_content,
            press_releases=scrape_result.press_releases,
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
            raw_pasted = (st.session_state.get("pasted_folder_input") or st.session_state.get("raw_pasted_folder_input") or "").strip()
            selected_fid = (
                st.session_state.get("target_folder_id", "").strip()
                or (extract_folder_id(raw_pasted) if raw_pasted else "")
                or None
            )
            selected_email = st.session_state.get("share_recipient_email", "").strip() or None
            sa_email_cur = st.session_state.get("service_account_client_email", "")
            is_oauth_mode = google_creds_option.startswith("OAuth 2.0")
            active_oauth = oauth_creds if (is_oauth_mode and oauth_creds and oauth_creds.valid) else None

            if not selected_fid and not active_oauth and (service_account_json_content or sa_email_cur):
                doc_export_error = (
                    f"📁 **Google Drive Destination Folder Required**\n\n"
                    f"Standalone Google Service Accounts do not have personal Google Drive storage (quota is **0 MB**). "
                    f"Google blocks creating new documents directly at root 'My Drive'.\n\n"
                    f"**How to resolve in 30 seconds:**\n"
                    f"1. Open your [Google Drive](https://drive.google.com), create or open a folder (e.g. *Retail Discovery Briefs*).\n"
                    f"2. Click **Share** and add `{sa_email_cur or 'your service account'}` as **Editor**.\n"
                    f"3. In the sidebar under **'📁 Drive Destination & Folder Browser'**, click **🔄 Refresh** (or paste the folder link).\n"
                    f"4. Click **'🔄 Retry Google Docs Upload'** below!"
                )
                status_container.write("⚠️ Google Docs export: destination folder required for Service Account.")
            else:
                status_container.write("📄 Exporting styled executive brief to Google Docs API...")
                try:
                    doc_res = export_dossier_to_google_doc(
                        dossier=dossier,
                        oauth_credentials=active_oauth,
                        credentials_json=service_account_json_content,
                        folder_id=selected_fid,
                        share_with_email=selected_email,
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
            f_name_disp = st.session_state.get("target_folder_name")
            f_url_disp = st.session_state.get("target_folder_url")
            if f_name_disp and "[Default]" not in f_name_disp:
                dest_str = f" inside folder **[{f_name_disp}]({f_url_disp})**" if f_url_disp else f" inside folder **{f_name_disp}**"
            else:
                dest_str = " in **Google Drive**"
            st.success(f"📄 **Live Google Doc Generated Successfully!** Saved{dest_str}.")
            btn_col1, btn_col2 = st.columns([2, 1])
            with btn_col1:
                st.link_button(
                    label="🚀 Open Formatted Google Doc Brief ↗",
                    url=google_doc_url,
                    type="primary",
                    width='stretch',
                )
            with btn_col2:
                retry_upload_clicked = st.button(
                    "🔄 Retry Google Docs Upload",
                    width='stretch',
                    help="Re-upload or update the Google Doc brief.",
                )
        else:
            st.info("ℹ️ Google Doc export omitted or awaiting service account. Download the executive Markdown brief below, or retry uploading to Google Docs.")
            if doc_export_error:
                st.error(doc_export_error)

            retry_upload_clicked = st.button(
                "🔄 Retry Google Docs Upload",
                type="primary",
                width='content',
                help="Attempt to export the brief to Google Docs with current credentials.",
            )

    with cta_col2:
        safe_name = dossier.account_name.replace(" ", "_")
        st.download_button(
            label="⬇️ Download Markdown Brief",
            data=markdown_brief,
            file_name=f"{safe_name}_Executive_Discovery_Brief.md",
            mime="text/markdown",
            width='stretch',
        )

    # Handle Retry Google Docs Upload action
    if retry_upload_clicked:
        is_oauth_mode = google_creds_option.startswith("OAuth 2.0")
        active_oauth = oauth_creds if (is_oauth_mode and oauth_creds and oauth_creds.valid) else None
        creds_payload = service_account_json_content or st.session_state.get("service_account_json_content")
        raw_pasted_retry = (st.session_state.get("pasted_folder_input") or st.session_state.get("raw_pasted_folder_input") or "").strip()
        t_folder = (
            st.session_state.get("target_folder_id", "").strip()
            or (extract_folder_id(raw_pasted_retry) if raw_pasted_retry else "")
            or None
        )
        s_email = st.session_state.get("share_recipient_email", "").strip() or None

        # Pre-check: Service Accounts have 0 MB Drive quota and cannot create files at root 'My Drive'
        if not t_folder and not active_oauth and (creds_payload or st.session_state.get("service_account_client_email")):
            sa_acc = st.session_state.get("service_account_client_email", "your service account")
            st.session_state["doc_export_error"] = (
                f"📁 **Google Drive Destination Folder Required**\n\n"
                f"Standalone Google Service Accounts do not have personal Google Drive storage (quota is **0 MB**). "
                f"Google blocks creating new documents directly at root 'My Drive'.\n\n"
                f"**How to resolve in 30 seconds:**\n"
                f"1. Open your [Google Drive](https://drive.google.com), create or open a folder (e.g. *Retail Discovery Briefs*).\n"
                f"2. Click **Share** on that folder, add `{sa_acc}` as **Editor**, and save.\n"
                f"3. In the sidebar under **'📁 Drive Destination & Folder Browser'**, click **🔄 Refresh** (or paste the folder URL).\n"
                f"4. Click **'🔄 Retry Google Docs Upload'**!"
            )
            st.rerun()

        with st.spinner(f"Exporting Executive Discovery Brief for {dossier.account_name} to Google Docs..."):
            try:
                doc_res = export_dossier_to_google_doc(
                    dossier=dossier,
                    oauth_credentials=active_oauth,
                    credentials_json=creds_payload,
                    folder_id=t_folder,
                    share_with_email=s_email,
                )
                st.session_state["google_doc_url"] = doc_res.get("document_url")
                st.session_state["doc_export_error"] = None
                st.rerun()
            except Exception as retry_err:
                st.session_state["doc_export_error"] = str(retry_err)
                st.rerun()

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
        st.subheader("Deep Corporate Intelligence & Scraped DOM Signals")
        if raw_scrape:
            st.markdown(
                f"- **Domain Title:** {raw_scrape.title}\n"
                f"- **Engine Used:** `{raw_scrape.engine_used}`\n"
                f"- **Meta Description:** {raw_scrape.meta_description or 'None'}\n"
                f"- **Detected Platform & Tooling Signatures:** `{', '.join(raw_scrape.tech_signals) or 'None'}`"
            )

            # Sub-section 1: About Us & Milestones
            with st.expander("🏢 **Company About Us & Key Milestones**", expanded=True):
                about = getattr(raw_scrape, "about_us_content", {}) or {}
                if about.get("source_url"):
                    st.caption(f"Source: [{about['source_url']}]({about['source_url']})")
                key_facts = about.get("key_facts", [])
                if key_facts:
                    st.markdown("**Structured Key Facts & Operational Metrics:**")
                    for kf in key_facts:
                        st.markdown(f"- {kf}")
                if about.get("markdown_text"):
                    st.markdown("**About Us Narrative:**")
                    st.markdown(about["markdown_text"][:4000])
                elif not key_facts:
                    st.info("No dedicated About Us sub-page resolved for this domain.")

            # Sub-section 2: Executive Leadership Profiles
            with st.expander("👥 **Executive Leadership Notes**", expanded=True):
                lead = getattr(raw_scrape, "leadership_content", {}) or {}
                if lead.get("source_url"):
                    st.caption(f"Source: [{lead['source_url']}]({lead['source_url']})")
                if lead.get("markdown_text"):
                    st.markdown(lead["markdown_text"][:4000])
                else:
                    st.info("No dedicated Leadership/Executive sub-page resolved for this domain.")

            # Sub-section 3: Corporate Press Releases & Earnings
            with st.expander("📰 **Corporate Press Releases & Newsroom Digest**", expanded=True):
                press_list = getattr(raw_scrape, "press_releases", []) or []
                if press_list:
                    for pr in press_list:
                        st.markdown(f"#### [{pr.get('title', 'Corporate Release')}]({pr.get('source_url', '#')})")
                        st.markdown(pr.get("markdown_text", "")[:1000])
                        st.markdown("---")
                else:
                    st.info("No corporate press releases or newsroom articles resolved for this domain.")

            # Sub-section 4: Clean Storefront Markdown
            with st.expander("🌐 **Storefront DOM (Clean Markdown)**", expanded=False):
                st.text_area("Storefront Cleaned Content", value=raw_scrape.markdown[:10000], height=350)
