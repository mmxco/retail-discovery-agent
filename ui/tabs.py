"""
Tabs UI Controller
Handles executive brief presentation, Google Docs upload/retry actions,
and tabbed rendering of dossier sections.
"""

import streamlit as st
from typing import Optional, Any

from core.models import DiscoveryDossier
from exporters.gdocs_exporter import export_dossier_to_google_doc
from integrations.drive_service import extract_folder_id


def render_dossier_view(
    dossier: DiscoveryDossier,
    google_doc_url: Optional[str] = None,
    doc_export_error: Optional[str] = None,
    markdown_brief: str = "",
    raw_scrape: Optional[Any] = None,
    google_creds_option: str = "Skip Google Docs (Local Markdown Only)",
    oauth_creds: Optional[Any] = None,
    service_account_json_content: Optional[str] = None,
):
    """Renders the executive brief presentation header, CTA bar, and the 6 discovery tabs."""
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
            st.info("ℹ️ Google Doc export omitted or awaiting credentials. Download the executive Markdown brief below, or retry uploading to Google Docs.")
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
        active_oauth = oauth_creds if (is_oauth_mode and oauth_creds and getattr(oauth_creds, "valid", False)) else None
        creds_payload = service_account_json_content or st.session_state.get("service_account_json_content")
        raw_pasted_retry = (st.session_state.get("pasted_folder_input") or st.session_state.get("raw_pasted_folder_input") or "").strip()
        t_folder = (
            st.session_state.get("target_folder_id", "").strip()
            or (extract_folder_id(raw_pasted_retry) if raw_pasted_retry else "")
            or None
        )
        s_email = st.session_state.get("share_recipient_email", "").strip() or None

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
        if dossier.corporate_domain:
            ov_col1, ov_col2, ov_col3, ov_col4 = st.columns(4)
            with ov_col1:
                st.metric("Retail Segment", dossier.retail_segment)
            with ov_col2:
                st.metric("Estimated Scale", dossier.estimated_scale)
            with ov_col3:
                st.metric("Retail Domain", dossier.domain)
            with ov_col4:
                st.metric("Corporate Site", dossier.corporate_domain)
        else:
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
                st.markdown("#### Question:")
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

            with st.expander("👥 **Executive Leadership Notes**", expanded=True):
                lead = getattr(raw_scrape, "leadership_content", {}) or {}
                if lead.get("source_url"):
                    st.caption(f"Source: [{lead['source_url']}]({lead['source_url']})")
                if lead.get("markdown_text"):
                    st.markdown(lead["markdown_text"][:4000])
                else:
                    st.info("No dedicated Leadership/Executive sub-page resolved for this domain.")

            with st.expander("📰 **Corporate Press Releases & Newsroom Digest**", expanded=True):
                press_list = getattr(raw_scrape, "press_releases", []) or []
                if press_list:
                    for pr in press_list:
                        st.markdown(f"#### [{pr.get('title', 'Corporate Release')}]({pr.get('source_url', '#')})")
                        st.markdown(pr.get("markdown_text", "")[:1000])
                        st.markdown("---")
                else:
                    st.info("No corporate press releases or newsroom articles resolved for this domain.")

            with st.expander("🌐 **Storefront DOM (Clean Markdown)**", expanded=False):
                st.text_area("Storefront Cleaned Content", value=raw_scrape.markdown[:10000], height=350)
