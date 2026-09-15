"""
Unit tests for Google Drive integrations (integrations/drive_service.py).
Tests folder ID extraction, folder listing, validation, creation, and HTTP error diagnostics.
Zero live Google API credentials required.
"""

from unittest.mock import MagicMock, patch
from googleapiclient.errors import HttpError
from httplib2 import Response

from integrations.drive_service import (
    extract_folder_id,
    list_drive_folders,
    validate_drive_folder,
    create_drive_folder,
    diagnose_google_http_error,
)


def test_extract_folder_id():
    # 1. Plain ID
    assert extract_folder_id("1a2b3c4d5e") == "1a2b3c4d5e"

    # 2. Standard Google Drive URL
    url1 = "https://drive.google.com/drive/folders/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
    assert extract_folder_id(url1) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"

    # 3. Google Drive URL with user index and query params
    url2 = "https://drive.google.com/drive/u/0/folders/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs?usp=sharing"
    assert extract_folder_id(url2) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"

    # 4. Trailing slashes and spaces
    url3 = "  https://drive.google.com/drive/folders/abc123XYZ-9/  "
    assert extract_folder_id(url3) == "abc123XYZ-9"

    # 5. Empty or None
    assert extract_folder_id("") == ""
    assert extract_folder_id(None) == ""


def test_drive_helpers_empty_inputs():
    val_empty = validate_drive_folder("")
    assert val_empty["valid"] is False

    create_empty = create_drive_folder("")
    assert create_empty["success"] is False


def test_list_drive_folders_mocked():
    mock_files_resp = {
        "files": [
            {
                "id": "folder_123",
                "name": "Retail Briefs 2026",
                "mimeType": "application/vnd.google-apps.folder",
                "capabilities": {"canAddChildren": True},
                "webViewLink": "https://drive.google.com/drive/folders/folder_123",
            }
        ]
    }
    mock_drives_resp = {
        "drives": [
            {
                "id": "drive_789",
                "name": "Retail Shared Drive",
                "capabilities": {"canAddChildren": True},
            }
        ]
    }

    with patch("integrations.drive_service.get_google_credentials") as mock_get_creds, \
         patch("integrations.drive_service.build") as mock_build:
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds

        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        mock_drive.files().list().execute.return_value = mock_files_resp
        mock_drive.drives().list().execute.return_value = mock_drives_resp

        res = list_drive_folders(credentials_json='{"client_email": "sa@test.com"}')
        assert res["success"] is True
        assert len(res["folders"]) == 1
        assert len(res["shared_drives"]) == 1
        assert res["total_count"] == 2


def test_validate_drive_folder_mocked():
    mock_meta = {
        "id": "f_123",
        "name": "Target Account Dossiers",
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False,
        "capabilities": {"canAddChildren": True},
        "webViewLink": "https://drive.google.com/drive/folders/f_123",
    }

    with patch("integrations.drive_service.get_google_credentials") as mock_get_creds, \
         patch("integrations.drive_service.build") as mock_build:
        mock_get_creds.return_value = MagicMock()
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive
        mock_drive.files().get().execute.return_value = mock_meta

        res = validate_drive_folder("f_123")
        assert res["valid"] is True
        assert res["name"] == "Target Account Dossiers"
        assert res["can_add_children"] is True


def test_diagnose_google_http_error():
    # Quota error
    resp = Response({"status": 403})
    content = b'{"error": {"message": "The user storage quota limit has been exceeded", "details": [{"reason": "storageQuotaExceeded"}]}}'
    he = HttpError(resp, content)
    diag = diagnose_google_http_error(he, project_id="test-proj")
    assert "Storage Quota Limit" in str(diag)

    # API disabled error
    content_disabled = b'{"error": {"message": "Google Docs API has not been used in project test-proj before or it is disabled.", "details": [{"reason": "SERVICE_DISABLED"}]}}'
    he_disabled = HttpError(resp, content_disabled)
    diag_disabled = diagnose_google_http_error(he_disabled, project_id="test-proj")
    assert "is Disabled" in str(diag_disabled)


def test_create_drive_folder_mocked():
    mock_created_meta = {
        "id": "new_folder_999",
        "name": "Retail Discovery Briefs",
        "webViewLink": "https://drive.google.com/drive/folders/new_folder_999",
    }

    with patch("integrations.drive_service.get_google_credentials") as mock_get_creds, \
         patch("integrations.drive_service.build") as mock_build:
        mock_get_creds.return_value = MagicMock()
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive
        mock_drive.files().create().execute.return_value = mock_created_meta
        mock_drive.permissions().create().execute.return_value = {}

        # 1. Create with parent folder and sharing
        res = create_drive_folder(
            folder_name="Retail Discovery Briefs",
            parent_folder_id="parent_123",
            credentials_json='{"client_email": "sa@test.com"}',
            share_with_email="rep@company.com",
        )

        assert res["success"] is True
        assert res["id"] == "new_folder_999"
        assert res["name"] == "Retail Discovery Briefs"
        assert "new_folder_999" in res["web_view_link"]

        # Verify parent parameter
        create_kwargs = mock_drive.files().create.call_args[1]
        assert create_kwargs["body"]["parents"] == ["parent_123"]

        # Verify permission sharing
        perm_kwargs = mock_drive.permissions().create.call_args[1]
        assert perm_kwargs["fileId"] == "new_folder_999"
        assert perm_kwargs["body"]["emailAddress"] == "rep@company.com"
