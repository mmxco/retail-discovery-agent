"""
Sidebar UI Controller
Handles Gemini API key, model selection, SSL toggles, Google OAuth 2.0 / Service Account
authentication setup, Drive folder selection, and Playwright browser status.
"""

import os
import streamlit as st
from typing import Dict, Any

from auth.google_oauth import (
    validate_service_account,
    verify_client_secret,
    get_user_oauth_credentials,
    get_authenticated_user_info,
    clear_oauth_token,
    start_oauth_desktop_flow,
)
from integrations.drive_service import (
    extract_folder_id,
    list_drive_folders,
    validate_drive_folder,
    create_drive_folder,
)
from scraper import check_playwright_availability, restart_playwright


def render_sidebar() -> Dict[str, Any]:
    """Renders the discovery studio sidebar controls and returns configuration state."""
    with st.sidebar:
        st.title("⚙️ Discovery Studio Settings")
        st.markdown("---")

        # 1. AI Engine
        st.subheader("1. AI Engine (Gemini)")
        env_key = os.environ.get("GEMINI_API_KEY", "")

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

        # 2. Google Docs Integration
        st.subheader("2. Google Docs Integration")
        oauth_creds = None
        service_account_json_content = None

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
                        f"<span style='color:#65a30d; font-size:12px;'>Documents will be saved in your personal Google Drive.</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button("🔄 Sign Out / Switch Google Account", width='stretch'):
                        clear_oauth_token()
                        if "oauth_user_info" in st.session_state:
                            del st.session_state["oauth_user_info"]
                        st.rerun()
                else:
                    st.warning("⚠️ **Not Authenticated** with Google Drive.")
                    if v_secret and v_secret["valid"]:
                        srv = st.session_state.get("oauth_server_instance")
                        if srv and srv.is_running:
                            st.info(f"🌐 Authentication server running on port `{srv.port}`. Complete sign-in in browser.")
                            st.link_button("🔑 Open Google Sign-In Window ↗", url=srv.auth_url, type="primary", width='stretch')
                            manual_code = st.text_input("Paste Redirect URL / Code manually:", key="oauth_manual_code_input")
                            if st.button("Submit Code", width='stretch'):
                                if srv.manual_exchange(manual_code):
                                    st.success("Authenticated successfully!")
                                    st.rerun()
                                else:
                                    st.error("Failed to exchange authorization code.")
                        else:
                            if st.button("🚀 Sign In with Google", type="primary", width='stretch'):
                                server_inst = start_oauth_desktop_flow(client_secret_data_or_path=raw_cs)
                                st.session_state["oauth_server_instance"] = server_inst
                                st.rerun()

            elif google_creds_option == "Upload Service Account JSON (Legacy)":
                sa_file = st.file_uploader(
                    "Service Account Key File (service_account.json)",
                    type=["json"],
                    help="Upload a Google Cloud service account key JSON.",
                )
                if sa_file:
                    sa_file.seek(0)
                    service_account_json_content = sa_file.read().decode("utf-8")
                    st.session_state["service_account_json_content"] = service_account_json_content
                elif "service_account_json_content" in st.session_state:
                    service_account_json_content = st.session_state["service_account_json_content"]

                if service_account_json_content:
                    v_res = validate_service_account(service_account_json_content)
                    if v_res["valid"]:
                        st.session_state["service_account_client_email"] = v_res["client_email"]
                        st.success(f"✅ Service Account: `{v_res['client_email']}`")
                    else:
                        st.error(f"❌ {v_res['error']}")

            # Drive Destination Folder Browser
            st.markdown("---")
            st.markdown("#### 📁 Drive Destination Folder")
            folder_mode = st.radio(
                "Folder Selection Method",
                options=["📂 Browse Drive Folders", "🔗 Paste Folder Link / ID", "➕ Create New Folder"],
                index=0,
                horizontal=True,
            )

            oauth_active = google_creds_option.startswith("OAuth 2.0") and oauth_creds and oauth_creds.valid

            if folder_mode == "📂 Browse Drive Folders":
                col_ref, col_sel_f = st.columns([1, 4])
                with col_ref:
                    refresh_clicked = st.button("🔄", help="Refresh Drive folder list", width='stretch')
                with col_sel_f:
                    if refresh_clicked or "drive_folders_cache" not in st.session_state:
                        with st.spinner("Fetching folders from Google Drive..."):
                            f_list = list_drive_folders(
                                oauth_credentials=oauth_creds if oauth_active else None,
                                credentials_json=service_account_json_content,
                            )
                            st.session_state["drive_folders_cache"] = f_list

                cached = st.session_state.get("drive_folders_cache", {})
                folder_options = {"[Default] My Drive (Root / No Folder)": ""}
                for f in cached.get("folders", []):
                    folder_options[f"📁 {f['name']}"] = f["id"]
                for d in cached.get("shared_drives", []):
                    folder_options[f"👥 Shared Drive: {d['name']}"] = d["id"]

                sel_folder_label = st.selectbox(
                    "Select Destination Folder",
                    options=list(folder_options.keys()),
                    index=0,
                )
                st.session_state["target_folder_id"] = folder_options[sel_folder_label]
                st.session_state["target_folder_name"] = sel_folder_label

            elif folder_mode == "🔗 Paste Folder Link / ID":
                pasted_val = st.text_input(
                    "Google Drive Folder URL or ID",
                    value=st.session_state.get("target_folder_id", ""),
                    placeholder="https://drive.google.com/drive/folders/... or ID",
                )
                if pasted_val.strip():
                    ext_id = extract_folder_id(pasted_val.strip())
                    st.session_state["target_folder_id"] = ext_id
                    st.session_state["target_folder_name"] = f"📁 ID: {ext_id[:16]}..."

            elif folder_mode == "➕ Create New Folder":
                new_f_name = st.text_input("New Folder Name", placeholder="Retail Discovery Briefs")
                if st.button("📁 Create & Select Folder", type="primary", width='stretch'):
                    if new_f_name.strip():
                        with st.spinner(f"Creating folder '{new_f_name.strip()}'..."):
                            c_res = create_drive_folder(
                                folder_name=new_f_name.strip(),
                                oauth_credentials=oauth_creds if oauth_active else None,
                                credentials_json=service_account_json_content,
                            )
                        if c_res.get("success"):
                            st.session_state["target_folder_id"] = c_res["id"]
                            st.session_state["target_folder_name"] = f"📁 {c_res['name']}"
                            st.session_state["drive_folders_cache"] = None
                            st.success(f"Folder '{c_res['name']}' created and selected!")
                            st.rerun()

            cur_fid = st.session_state.get("target_folder_id", "")
            cur_fname = st.session_state.get("target_folder_name", "")
            if cur_fid:
                st.markdown(f"🎯 **Active Target:** `{cur_fname or cur_fid}`")
            else:
                st.markdown("🎯 **Active Target:** `My Drive (Default Root)`")

            share_email_input = st.text_input(
                "Share Directly with Email (Optional)",
                value=st.session_state.get("share_recipient_email", ""),
                placeholder="you@company.com",
            )
            st.session_state["share_recipient_email"] = share_email_input

        st.markdown("---")

        # 3. Playwright Status
        st.subheader("3. Playwright Headless Browser")
        pw_available, pw_err_msg = check_playwright_availability()

        if pw_available:
            st.success("✅ **Playwright Headless Browser Active**")
        else:
            st.error(f"❌ **Playwright Unavailable:** `{pw_err_msg}`")
            if st.button("🔄 Restart / Install Playwright", type="primary", width="stretch"):
                with st.spinner("Installing and restarting Playwright Chromium binaries..."):
                    p_ok, p_res = restart_playwright()
                if p_ok:
                    st.success(f"✅ {p_res}")
                    st.rerun()
                else:
                    st.error(f"❌ {p_res}")

        st.markdown("---")
        st.caption("Retail Discovery Agent v2.0 • Powered by Google GenAI & Playwright")

        return {
            "api_key": api_key_input.strip(),
            "model_choice": model_choice,
            "disable_ssl": disable_ssl,
            "google_creds_option": google_creds_option,
            "oauth_creds": oauth_creds,
            "service_account_json_content": service_account_json_content,
            "target_folder_id": st.session_state.get("target_folder_id", ""),
            "share_recipient_email": st.session_state.get("share_recipient_email", "").strip(),
            "pw_available": pw_available,
        }
