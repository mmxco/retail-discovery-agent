"""
Enterprise Google Docs Exporter Module
Takes a DiscoveryDossier instance, formats a styled executive briefing brief,
and creates the document using the Google Docs & Google Drive APIs.
Includes fallback to styled Markdown export if credentials are not configured.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

from googleapiclient.discovery import build
from google.auth import default as google_auth_default
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials

from models import DiscoveryDossier

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


class GoogleDocsBriefBuilder:
    """Manages text assembly, character indexing, and style ranges for Google Docs."""

    def __init__(self):
        self.text_parts: List[str] = []
        self.current_index: int = 1  # Google Docs body index starts at 1
        self.title_range: Optional[Tuple[int, int]] = None
        self.subtitle_range: Optional[Tuple[int, int]] = None
        self.h1_ranges: List[Tuple[int, int]] = []
        self.h2_ranges: List[Tuple[int, int]] = []
        self.bold_ranges: List[Tuple[int, int]] = []

    def add_line(self, text: str = "", style: str = "NORMAL"):
        """Appends a line of text and records style ranges."""
        line = text + "\n"
        start = self.current_index
        end = start + len(text)
        self.text_parts.append(line)
        self.current_index += len(line)

        if style == "TITLE" and text:
            self.title_range = (start, end)
        elif style == "SUBTITLE" and text:
            self.subtitle_range = (start, end)
        elif style == "HEADING_1" and text:
            self.h1_ranges.append((start, end))
        elif style == "HEADING_2" and text:
            self.h2_ranges.append((start, end))

    def add_labeled_line(self, label: str, value: str):
        """Adds a bold label followed by regular text."""
        start_label = self.current_index
        self.text_parts.append(label + ": ")
        end_label = self.current_index + len(label) + 2
        self.current_index = end_label
        self.bold_ranges.append((start_label, end_label))

        self.text_parts.append(value + "\n")
        self.current_index += len(value) + 1

    def get_full_text(self) -> str:
        return "".join(self.text_parts)

    def generate_style_requests(self) -> List[Dict[str, Any]]:
        """Generates Google Docs batchUpdate style requests."""
        requests = []

        # 1. Document Title style
        if self.title_range:
            start, end = self.title_range
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": "TITLE"},
                    "fields": "namedStyleType",
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {
                        "fontSize": {"magnitude": 22, "unit": "PT"},
                        "bold": True,
                        "foregroundColor": {
                            "color": {"rgbColor": {"red": 0.1, "green": 0.2, "blue": 0.45}}  # Navy #1A3673
                        },
                    },
                    "fields": "fontSize,bold,foregroundColor",
                }
            })

        # 2. Subtitle style
        if self.subtitle_range:
            start, end = self.subtitle_range
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": "SUBTITLE"},
                    "fields": "namedStyleType",
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {
                        "fontSize": {"magnitude": 11, "unit": "PT"},
                        "italic": True,
                        "foregroundColor": {
                            "color": {"rgbColor": {"red": 0.35, "green": 0.4, "blue": 0.48}}
                        },
                    },
                    "fields": "fontSize,italic,foregroundColor",
                }
            })

        # 3. Heading 1 styles
        for start, end in self.h1_ranges:
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {
                        "fontSize": {"magnitude": 15, "unit": "PT"},
                        "bold": True,
                        "foregroundColor": {
                            "color": {"rgbColor": {"red": 0.12, "green": 0.25, "blue": 0.55}}
                        },
                    },
                    "fields": "fontSize,bold,foregroundColor",
                }
            })

        # 4. Heading 2 styles
        for start, end in self.h2_ranges:
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType",
                }
            })
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {
                        "fontSize": {"magnitude": 12, "unit": "PT"},
                        "bold": True,
                        "foregroundColor": {
                            "color": {"rgbColor": {"red": 0.18, "green": 0.35, "blue": 0.6}}
                        },
                    },
                    "fields": "fontSize,bold,foregroundColor",
                }
            })

        # 5. Bold labels
        for start, end in self.bold_ranges:
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            })

        return requests


def get_google_credentials(
    credentials_json: Optional[str] = None,
    service_account_path: Optional[str] = None,
) -> Optional[Any]:
    """Resolves Google Cloud credentials from path, raw json, or ADC."""
    # 1. From direct JSON string (e.g. from Streamlit secrets)
    if credentials_json:
        try:
            info = json.loads(credentials_json)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load credentials from JSON string: {e}")

    # 2. From file path
    file_path = service_account_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if file_path and os.path.isfile(file_path):
        try:
            return service_account.Credentials.from_service_account_file(file_path, scopes=SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load credentials from file '{file_path}': {e}")

    # 3. From Application Default Credentials (ADC)
    try:
        creds, _ = google_auth_default(scopes=SCOPES)
        return creds
    except Exception as e:
        logger.info(f"ADC not available: {e}")

    return None


def export_dossier_to_google_doc(
    dossier: DiscoveryDossier,
    credentials_json: Optional[str] = None,
    service_account_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates and styles an executive pre-discovery briefing in Google Docs.
    Returns a dictionary with document_id and view/edit URL.
    """
    creds = get_google_credentials(
        credentials_json=credentials_json,
        service_account_path=service_account_path,
    )

    if not creds:
        raise PermissionError(
            "Google Docs API credentials not found. Please provide a Service Account JSON "
            "file path, credentials string, or configure Google Application Default Credentials (ADC)."
        )

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # 1. Build document text and style requests
    builder = GoogleDocsBriefBuilder()

    builder.add_line(f"Executive Pre-Discovery Briefing: {dossier.account_name}", style="TITLE")
    builder.add_line(f"Retail ERP & Omnichannel Modernization Dossier | Generated {dossier.generated_at[:10]}", style="SUBTITLE")
    builder.add_line("—" * 50)
    builder.add_line()

    # Section 1: Firmographics & Executive Summary
    builder.add_line("1. Executive Overview & Account Context", style="HEADING_1")
    builder.add_labeled_line("Target Account", dossier.account_name)
    builder.add_labeled_line("Primary Domain", dossier.domain)
    builder.add_labeled_line("Retail Segment", dossier.retail_segment)
    builder.add_labeled_line("Scale & Footprint", dossier.estimated_scale)
    builder.add_line()
    builder.add_line(dossier.executive_summary)
    builder.add_line()

    # Section 2: Tech Stack Footprint
    builder.add_line("2. Enterprise Technology Stack Indicators", style="HEADING_1")
    ts = dossier.tech_stack
    builder.add_labeled_line("E-Commerce Platform", ts.ecommerce_platform or "Undetected / Custom Headless")
    builder.add_labeled_line("Point of Sale (POS)", ts.point_of_sale or "Legacy In-Store Architecture")
    builder.add_labeled_line("Core ERP / Merchandising", ts.erp_core or "Tier-1 Legacy Suite")
    builder.add_labeled_line("Order Management (DOM/OMS)", ts.order_management or "Distributed / Monolithic")
    builder.add_labeled_line("Warehouse / Supply Chain", ts.warehouse_supply_chain or "Legacy WMS")
    if ts.analytics_and_marketing:
        builder.add_labeled_line("Analytics & Marketing", ", ".join(ts.analytics_and_marketing))
    if ts.detected_technologies:
        builder.add_labeled_line("Detected Footprints", ", ".join(ts.detected_technologies))
    if ts.architecture_signals:
        builder.add_labeled_line("Architecture Signals", "; ".join(ts.architecture_signals))
    builder.add_line()

    # Section 3: Executive Pain Points (The Value Triangle)
    builder.add_line("3. Executive Pain Points (The Value Triangle)", style="HEADING_1")
    for i, p in enumerate(dossier.pain_points, start=1):
        builder.add_line(f"Pain Point {i}: {p.category}", style="HEADING_2")
        builder.add_labeled_line("Technical Gap", p.technical_gap)
        builder.add_labeled_line("Operational Friction", p.operational_friction)
        builder.add_labeled_line("Financial Impact", p.financial_impact)
        if p.affected_executives:
            builder.add_labeled_line("Impacted Stakeholders", ", ".join(p.affected_executives))
        builder.add_line()

    # Section 4: Persona Discovery Questions
    builder.add_line("4. Persona-Specific Discovery Questions", style="HEADING_1")
    for i, q in enumerate(dossier.discovery_questions, start=1):
        builder.add_line(f"Persona: {q.target_persona} — {q.theme}", style="HEADING_2")
        builder.add_labeled_line("Discovery Question", f'"{q.question}"')
        builder.add_labeled_line("What to Listen For", q.what_to_listen_for)
        builder.add_labeled_line("Value Wedge", q.value_wedge)
        builder.add_line()

    # Section 5: Recommended Pre-Sales Strategy
    builder.add_line("5. Recommended Pre-Sales Discovery Strategy", style="HEADING_1")
    builder.add_line(dossier.recommended_discovery_strategy)
    builder.add_line()

    full_text = builder.get_full_text()

    # 2. Create blank Google Doc
    doc_title = f"Pre-Discovery Executive Brief - {dossier.account_name}"
    created_doc = docs_service.documents().create(body={"title": doc_title}).execute()
    document_id = created_doc.get("documentId")
    logger.info(f"Created Google Doc ID: {document_id}")

    # 3. Populate text
    insert_request = [{
        "insertText": {
            "location": {"index": 1},
            "text": full_text,
        }
    }]
    docs_service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": insert_request}
    ).execute()

    # 4. Apply styles
    style_requests = builder.generate_style_requests()
    if style_requests:
        try:
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": style_requests}
            ).execute()
        except Exception as se:
            logger.warning(f"Applied partial styles due to Google Docs API note: {se}")

    # 5. Make accessible via link if possible
    try:
        drive_service.permissions().create(
            fileId=document_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()
    except Exception as pe:
        logger.info(f"Drive permissions note (standard domain restriction): {pe}")

    doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
    return {
        "document_id": document_id,
        "document_url": doc_url,
        "title": doc_title,
        "success": True,
    }


def export_dossier_to_markdown(dossier: DiscoveryDossier) -> str:
    """Generates a styled Markdown executive briefing representation of the dossier."""
    lines = [
        f"# Executive Pre-Discovery Briefing: {dossier.account_name}",
        f"**Target Account:** {dossier.account_name} | **Domain:** {dossier.domain} | **Generated:** {dossier.generated_at[:10]}",
        f"**Retail Segment:** {dossier.retail_segment} | **Scale:** {dossier.estimated_scale}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        dossier.executive_summary,
        "",
        "---",
        "",
        "## 2. Technology Stack Footprint",
        f"- **E-Commerce Platform:** {dossier.tech_stack.ecommerce_platform or 'Undetected / Custom Headless'}",
        f"- **Point of Sale (POS):** {dossier.tech_stack.point_of_sale or 'Legacy In-Store Architecture'}",
        f"- **Core ERP / Merchandising:** {dossier.tech_stack.erp_core or 'Tier-1 Legacy Suite'}",
        f"- **Order Management (DOM/OMS):** {dossier.tech_stack.order_management or 'Distributed / Monolithic'}",
        f"- **Warehouse / Supply Chain:** {dossier.tech_stack.warehouse_supply_chain or 'Legacy WMS'}",
    ]

    if dossier.tech_stack.analytics_and_marketing:
        lines.append(f"- **Analytics & Marketing:** {', '.join(dossier.tech_stack.analytics_and_marketing)}")
    if dossier.tech_stack.detected_technologies:
        lines.append(f"- **Detected Footprints:** {', '.join(dossier.tech_stack.detected_technologies)}")
    if dossier.tech_stack.architecture_signals:
        lines.append(f"- **Architecture Signals:** {'; '.join(dossier.tech_stack.architecture_signals)}")

    lines.extend(["", "---", "", "## 3. Executive Pain Points (The Value Triangle)"])
    for i, p in enumerate(dossier.pain_points, start=1):
        lines.extend([
            f"### {i}. {p.category}",
            f"- **Technical Gap:** {p.technical_gap}",
            f"- **Operational Friction:** {p.operational_friction}",
            f"- **Financial Impact:** {p.financial_impact}",
            f"- **Affected Stakeholders:** {', '.join(p.affected_executives)}",
            "",
        ])

    lines.extend(["---", "", "## 4. Persona-Specific Discovery Questions"])
    for i, q in enumerate(dossier.discovery_questions, start=1):
        lines.extend([
            f"### {i}. {q.target_persona} — *{q.theme}*",
            f"> **Question:** \"{q.question}\"",
            f"- **What to Listen For:** {q.what_to_listen_for}",
            f"- **Value Wedge:** {q.value_wedge}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## 5. Recommended Pre-Sales Discovery Strategy",
        dossier.recommended_discovery_strategy,
        "",
    ])

    return "\n".join(lines)
