"""
Google Docs Executive Briefing Exporter
Builds styled pre-sales discovery briefs in Google Docs using Docs & Drive APIs.
"""

import json
from typing import Optional, Dict, Any, Tuple, List

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.config import get_logger
from core.models import DiscoveryDossier
from auth.google_oauth import get_google_credentials
from integrations.drive_service import extract_folder_id, diagnose_google_http_error

logger = get_logger("exporters.gdocs_exporter")

__all__ = [
    "GoogleDocsBriefBuilder",
    "export_dossier_to_google_doc",
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
                            "color": {"rgbColor": {"red": 0.1, "green": 0.2, "blue": 0.45}}
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
                            "color": {"rgbColor": {"red": 0.12, "green": 0.25, "blue": 0.5}}
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
                            "color": {"rgbColor": {"red": 0.2, "green": 0.3, "blue": 0.4}}
                        },
                    },
                    "fields": "fontSize,bold,foregroundColor",
                }
            })

        # 5. Bold labeled fields
        for start, end in self.bold_ranges:
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            })

        return requests


def export_dossier_to_google_doc(
    dossier: DiscoveryDossier,
    oauth_credentials: Optional[Any] = None,
    credentials_json: Optional[str] = None,
    service_account_path: Optional[str] = None,
    folder_id: Optional[str] = None,
    share_with_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates and styles an executive pre-discovery briefing in Google Docs.
    Supports OAuth 2.0 User Credentials or Service Accounts, optional Google Drive folder targeting,
    and direct user email sharing. Returns a dictionary with document_id and view/edit URL.
    """
    creds = get_google_credentials(
        oauth_credentials=oauth_credentials,
        credentials_json=credentials_json,
        service_account_path=service_account_path,
    )

    if not creds:
        raise PermissionError(
            "Google API credentials not found. Please authenticate via Google OAuth 2.0 User Credentials, "
            "provide a Service Account JSON, or configure Google Application Default Credentials (ADC)."
        )

    # Extract metadata for actionable diagnostic hints
    project_id = ""
    client_email = ""
    if credentials_json:
        try:
            c_info = json.loads(credentials_json)
            project_id = c_info.get("project_id", "")
            client_email = c_info.get("client_email", "")
        except Exception:
            pass

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # 1. Build document text and style requests
    builder = GoogleDocsBriefBuilder()

    builder.add_line(f"Executive Discovery Brief for {dossier.account_name}", style="TITLE")
    builder.add_line(f"Retail ERP & Omnichannel Modernization Dossier | Generated {dossier.generated_at[:10]}", style="SUBTITLE")
    builder.add_line("—" * 50)
    builder.add_line()

    # Section 1: Firmographics & Executive Summary
    builder.add_line("1. Executive Overview & Account Context", style="HEADING_1")
    builder.add_labeled_line("Target Account", dossier.account_name)
    builder.add_labeled_line("Primary Domain", dossier.domain)
    if dossier.corporate_domain:
        builder.add_labeled_line("Corporate Website", dossier.corporate_domain)
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

    # 2. Create the document via Drive API with explicit parents metadata
    doc_title = f"Executive Discovery Brief for {dossier.account_name}"
    clean_folder = extract_folder_id(folder_id) if folder_id else ""
    try:
        file_metadata: Dict[str, Any] = {
            "name": doc_title,
            "mimeType": "application/vnd.google-apps.document",
        }
        if clean_folder:
            logger.info(f"Creating Google Doc inside specified Drive folder: {clean_folder}")
            file_metadata["parents"] = [clean_folder]
        elif client_email and client_email.endswith(".gserviceaccount.com"):
            raise PermissionError(
                f"A destination Google Drive folder is required for Service Account '{client_email}'. "
                f"Standalone Google Service Accounts have 0 MB of Drive storage quota and cannot create files at root. "
                f"Please specify a folder_id so the document can be created with the 'parents': [folder_id] parameter."
            )

        created_file = drive_service.files().create(
            body=file_metadata,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        document_id = created_file.get("id")
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

        # 5. Share with specified user email or open link
        if share_with_email and share_with_email.strip():
            try:
                clean_email = share_with_email.strip()
                drive_service.permissions().create(
                    fileId=document_id,
                    body={"role": "writer", "type": "user", "emailAddress": clean_email},
                    supportsAllDrives=True,
                ).execute()
                logger.info(f"Directly shared Google Doc with {clean_email}")
            except Exception as share_err:
                logger.warning(f"Direct user share note for {share_with_email}: {share_err}")

        try:
            drive_service.permissions().create(
                fileId=document_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True,
            ).execute()
        except Exception as pe:
            logger.info(f"Drive permissions note (standard domain restriction): {pe}")

        doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
        logger.info(f"Published Google Doc successfully: {doc_url}")

        return {
            "document_id": document_id,
            "document_url": doc_url,
            "title": doc_title,
            "folder_id": clean_folder,
            "success": True,
        }

    except HttpError as he:
        raise diagnose_google_http_error(
            he=he,
            project_id=project_id,
            client_email=client_email,
            folder_id=clean_folder,
        ) from he
