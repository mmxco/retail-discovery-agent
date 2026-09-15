"""
Unit tests for Google Docs and Markdown exporters (exporters/).
Tests brief styling, batchUpdate requests, Markdown generation, and document publishing.
Zero live Google API credentials required.
"""

from unittest.mock import MagicMock, patch

from exporters.gdocs_exporter import GoogleDocsBriefBuilder, export_dossier_to_google_doc
from exporters.markdown_exporter import export_dossier_to_markdown


def test_google_docs_brief_builder():
    builder = GoogleDocsBriefBuilder()
    builder.add_line("Executive Discovery Brief for Target", style="TITLE")
    builder.add_line("Subtitle Text", style="SUBTITLE")
    builder.add_line("Section 1", style="HEADING_1")
    builder.add_line("Sub-section A", style="HEADING_2")
    builder.add_labeled_line("Retail Segment", "Department Store")

    full_text = builder.get_full_text()
    assert "Executive Discovery Brief for Target" in full_text
    assert "Retail Segment: Department Store" in full_text

    requests = builder.generate_style_requests()
    assert len(requests) > 0
    # Has updateParagraphStyle and updateTextStyle
    req_types = [list(r.keys())[0] for r in requests]
    assert "updateParagraphStyle" in req_types
    assert "updateTextStyle" in req_types


def test_export_dossier_to_markdown(sample_dossier):
    md = export_dossier_to_markdown(sample_dossier)
    assert md.startswith(f"# Executive Discovery Brief for {sample_dossier.account_name}")
    assert "## 1. Executive Summary" in md
    assert "## 2. Technology Stack Footprint" in md
    assert "## 3. Executive Pain Points (The Value Triangle)" in md
    assert "## 4. Persona-Specific Discovery Questions" in md
    assert "## 5. Recommended Pre-Sales Discovery Strategy" in md
    assert "**Corporate Website:** https://press.nordstrom.com" in md


def test_export_dossier_to_google_doc_mocked(sample_dossier):
    mock_drive_service = MagicMock()
    mock_docs_service = MagicMock()

    mock_drive_service.files().create().execute.return_value = {"id": "doc_12345"}
    mock_docs_service.documents().batchUpdate().execute.return_value = {}
    mock_drive_service.permissions().create().execute.return_value = {}

    with patch("exporters.gdocs_exporter.get_google_credentials") as mock_get_creds, \
         patch("exporters.gdocs_exporter.build") as mock_build:
        mock_get_creds.return_value = MagicMock()

        def build_side_effect(service_name, version, **kwargs):
            if service_name == "drive":
                return mock_drive_service
            elif service_name == "docs":
                return mock_docs_service
            return MagicMock()

        mock_build.side_effect = build_side_effect

        result = export_dossier_to_google_doc(
            dossier=sample_dossier,
            folder_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
            share_with_email="presales@retail.com",
        )

        assert result["success"] is True
        assert result["document_id"] == "doc_12345"
        assert "https://docs.google.com/document/d/doc_12345/edit" in result["document_url"]

        # Verify parents parameter was passed to create call
        call_kwargs = mock_drive_service.files().create.call_args[1]
        assert call_kwargs["body"]["parents"] == ["1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"]
