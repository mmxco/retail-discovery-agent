"""
Google Drive Integration Service
Manages Drive folder discovery, validation, creation, and HTTP error diagnostics.
"""

import re
import json
from typing import Optional, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.config import get_logger
from auth.google_oauth import get_google_credentials

logger = get_logger("integrations.drive_service")

__all__ = [
    "extract_folder_id",
    "list_drive_folders",
    "validate_drive_folder",
    "create_drive_folder",
    "diagnose_google_http_error",
]


def extract_folder_id(folder_input: str) -> str:
    """
    Extracts a clean Google Drive folder ID from a raw ID or full browser URL.
    Handles formats like:
      - https://drive.google.com/drive/folders/1a2b3c4d5e...
      - https://drive.google.com/drive/u/0/folders/1a2b3c4d5e...?usp=sharing
      - 1a2b3c4d5e...
    """
    if not folder_input or not isinstance(folder_input, str):
        return ""
    clean = folder_input.strip()
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", clean)
    if match:
        return match.group(1)
    if "?" in clean:
        clean = clean.split("?")[0].strip()
    clean = clean.rstrip("/")
    return clean


def list_drive_folders(
    oauth_credentials: Optional[Any] = None,
    credentials_json: Optional[str] = None,
    service_account_path: Optional[str] = None,
    page_size: int = 100,
) -> Dict[str, Any]:
    """
    Queries Google Drive for folders accessible to the authenticated credentials.
    Includes folders created with/shared with the account and accessible Shared Drives.
    Returns a dict with success flag, list of folder objects, and error message if any.
    """
    creds = get_google_credentials(
        oauth_credentials=oauth_credentials,
        credentials_json=credentials_json,
        service_account_path=service_account_path,
    )
    if not creds:
        return {
            "success": False,
            "error": "Google Cloud credentials not found or unauthenticated.",
            "folders": [],
            "shared_drives": [],
            "total_count": 0,
        }

    client_email = ""
    if credentials_json:
        try:
            c_info = json.loads(credentials_json)
            client_email = c_info.get("client_email", "")
        except Exception:
            pass

    try:
        drive_service = build("drive", "v3", credentials=creds)

        # 1. Query folders (including those in shared drives and shared with me)
        response = drive_service.files().list(
            q="mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            spaces="drive",
            fields="nextPageToken, files(id, name, parents, shared, driveId, capabilities(canAddChildren), webViewLink)",
            pageSize=page_size,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            orderBy="name",
        ).execute()

        raw_folders = response.get("files", [])
        folders = []
        for f in raw_folders:
            folders.append({
                "id": f.get("id"),
                "name": f.get("name", "Untitled Folder"),
                "parents": f.get("parents", []),
                "shared": f.get("shared", False),
                "drive_id": f.get("driveId"),
                "can_add_children": f.get("capabilities", {}).get("canAddChildren", True),
                "web_view_link": f.get("webViewLink") or f"https://drive.google.com/drive/folders/{f.get('id')}",
            })

        # 2. Query Shared Drives
        shared_drives = []
        try:
            drives_resp = drive_service.drives().list(
                pageSize=50,
                fields="nextPageToken, drives(id, name, capabilities(canAddChildren))",
            ).execute()
            for d in drives_resp.get("drives", []):
                shared_drives.append({
                    "id": d.get("id"),
                    "name": d.get("name", "Untitled Drive"),
                    "is_shared_drive_root": True,
                    "can_add_children": d.get("capabilities", {}).get("canAddChildren", True),
                    "web_view_link": f"https://drive.google.com/drive/folders/{d.get('id')}",
                })
        except Exception as de:
            logger.info(f"Shared Drives check note: {de}")

        return {
            "success": True,
            "client_email": client_email,
            "folders": folders,
            "shared_drives": shared_drives,
            "total_count": len(folders) + len(shared_drives),
            "error": None,
        }

    except HttpError as he:
        err_msg = str(he)
        if he.resp.status == 403:
            return {
                "success": False,
                "error": (
                    "Google Drive API is not enabled in your Google Cloud Project or permission is denied. "
                    "Please ensure the Google Drive API is enabled in your Google Cloud Console."
                ),
                "folders": [],
                "shared_drives": [],
                "total_count": 0,
                "client_email": client_email,
            }
        return {
            "success": False,
            "error": f"Drive API Error ({he.resp.status}): {err_msg}",
            "folders": [],
            "shared_drives": [],
            "total_count": 0,
            "client_email": client_email,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to list Drive folders: {str(e)}",
            "folders": [],
            "shared_drives": [],
            "total_count": 0,
            "client_email": client_email,
        }


def validate_drive_folder(
    folder_id_or_url: str,
    oauth_credentials: Optional[Any] = None,
    credentials_json: Optional[str] = None,
    service_account_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validates a Google Drive folder by ID or browser URL.
    Checks:
      1. Clean folder ID extraction.
      2. Resource existence & not trashed.
      3. MIME type is 'application/vnd.google-apps.folder'.
      4. Write/editor permissions ('canAddChildren').
    """
    clean_id = extract_folder_id(folder_id_or_url)
    if not clean_id:
        return {
            "valid": False,
            "id": "",
            "name": "",
            "error": "No valid folder ID or URL provided.",
        }

    creds = get_google_credentials(
        oauth_credentials=oauth_credentials,
        credentials_json=credentials_json,
        service_account_path=service_account_path,
    )
    if not creds:
        return {
            "valid": False,
            "id": clean_id,
            "name": "",
            "error": "Google Cloud credentials not found or unauthenticated.",
        }

    client_email = ""
    if credentials_json:
        try:
            c_info = json.loads(credentials_json)
            client_email = c_info.get("client_email", "")
        except Exception:
            pass

    try:
        drive_service = build("drive", "v3", credentials=creds)
        meta = drive_service.files().get(
            fileId=clean_id,
            fields="id, name, mimeType, trashed, capabilities(canAddChildren), webViewLink, shared",
            supportsAllDrives=True,
        ).execute()

        if meta.get("trashed"):
            return {
                "valid": False,
                "id": clean_id,
                "name": meta.get("name", ""),
                "error": f"The folder '{meta.get('name')}' is in the Google Drive trash.",
            }

        mime = meta.get("mimeType", "")
        if mime != "application/vnd.google-apps.folder":
            return {
                "valid": False,
                "id": clean_id,
                "name": meta.get("name", ""),
                "error": f"The ID belongs to a '{mime}' file, not a Google Drive folder.",
            }

        can_add = meta.get("capabilities", {}).get("canAddChildren", True)
        web_link = meta.get("webViewLink") or f"https://drive.google.com/drive/folders/{clean_id}"

        return {
            "valid": True,
            "id": clean_id,
            "name": meta.get("name", "Untitled Folder"),
            "can_add_children": can_add,
            "web_view_link": web_link,
            "error": None if can_add else f"Warning: Service account may have view-only access to '{meta.get('name')}'.",
        }

    except HttpError as he:
        sa_hint = f" ({client_email})" if client_email else ""
        if he.resp.status == 404:
            return {
                "valid": False,
                "id": clean_id,
                "name": "",
                "error": (
                    f"Folder not found (HTTP 404). Either the folder does not exist, or the Service Account{sa_hint} "
                    f"has not been granted access. Share the folder in Google Drive with '{client_email or 'your service account'}' as Editor."
                ),
            }
        elif he.resp.status == 403:
            return {
                "valid": False,
                "id": clean_id,
                "name": "",
                "error": (
                    f"Permission Denied (HTTP 403). Service Account{sa_hint} does not have access to this folder, "
                    f"or the Google Drive API is disabled. Ensure the folder is shared with '{client_email or 'your service account'}' as Editor."
                ),
            }
        return {
            "valid": False,
            "id": clean_id,
            "name": "",
            "error": f"Google Drive API Error (HTTP {he.resp.status}): {str(he)}",
        }
    except Exception as e:
        return {
            "valid": False,
            "id": clean_id,
            "name": "",
            "error": f"Folder validation failed: {str(e)}",
        }


def create_drive_folder(
    folder_name: str,
    parent_folder_id: Optional[str] = None,
    oauth_credentials: Optional[Any] = None,
    credentials_json: Optional[str] = None,
    service_account_path: Optional[str] = None,
    share_with_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a new Google Drive folder using the authenticated credentials.
    Optionally nests under parent_folder_id, and optionally shares with share_with_email as Editor.
    """
    clean_name = (folder_name or "").strip()
    if not clean_name:
        return {"success": False, "error": "Folder name cannot be empty.", "id": "", "name": ""}

    creds = get_google_credentials(
        oauth_credentials=oauth_credentials,
        credentials_json=credentials_json,
        service_account_path=service_account_path,
    )
    if not creds:
        return {"success": False, "error": "Google credentials not found or unauthenticated.", "id": "", "name": clean_name}

    try:
        drive_service = build("drive", "v3", credentials=creds)

        file_metadata: Dict[str, Any] = {
            "name": clean_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        clean_parent = extract_folder_id(parent_folder_id) if parent_folder_id else ""
        if clean_parent:
            file_metadata["parents"] = [clean_parent]

        created = drive_service.files().create(
            body=file_metadata,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()

        folder_id = created.get("id")
        web_link = created.get("webViewLink") or f"https://drive.google.com/drive/folders/{folder_id}"

        # If share_with_email is provided, share the created folder directly
        if share_with_email and share_with_email.strip():
            try:
                drive_service.permissions().create(
                    fileId=folder_id,
                    body={"role": "writer", "type": "user", "emailAddress": share_with_email.strip()},
                    supportsAllDrives=True,
                ).execute()
                logger.info(f"Directly shared newly created folder with {share_with_email.strip()}")
            except Exception as pe:
                logger.warning(f"Note sharing newly created folder with {share_with_email}: {pe}")

        return {
            "success": True,
            "id": folder_id,
            "name": clean_name,
            "web_view_link": web_link,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create Google Drive folder: {str(e)}",
            "id": "",
            "name": clean_name,
        }


def diagnose_google_http_error(
    he: HttpError,
    project_id: str = "",
    client_email: str = "",
    folder_id: str = "",
) -> PermissionError:
    """
    Decodes Google API HttpError content to provide an exact, pinpoint root-cause explanation
    rather than a generic assumption.
    """
    raw_bytes = getattr(he, "content", b"") or b""
    parsed_json: Dict[str, Any] = {}
    try:
        parsed_json = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        pass

    err_data = parsed_json.get("error", {})
    message = err_data.get("message", str(he))
    status_code = getattr(he.resp, "status", 403)
    reasons = []
    for d in err_data.get("details", []):
        if isinstance(d, dict) and d.get("reason"):
            reasons.append(d.get("reason"))
    for e in err_data.get("errors", []):
        if isinstance(e, dict) and e.get("reason"):
            reasons.append(e.get("reason"))

    p_str = f" for project '{project_id}'" if project_id else ""
    p_param = f"?project={project_id}" if project_id else ""
    sa_str = f"`{client_email}`" if client_email else "your service account"

    # Case 1: Actually disabled API
    if any(r in ["SERVICE_DISABLED", "accessNotConfigured"] for r in reasons) or "has not been used in project" in message.lower() or "is not enabled" in message.lower():
        api_name = "Google Docs API" if "docs" in message.lower() else "Google Drive API"
        return PermissionError(
            f"🔒 **{api_name} is Disabled in Google Cloud Project{p_str}**\n\n"
            f"Google Cloud returned: *\"{message}\"*\n\n"
            f"**Resolution:**\n"
            f"1. 🔗 [Enable Google Docs API](https://console.cloud.google.com/apis/library/docs.googleapis.com{p_param})\n"
            f"2. 🔗 [Enable Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com{p_param})"
        )

    # Case 2: Storage Quota Exceeded
    if any("storagequotaexceeded" in r.lower() for r in reasons) or "quota" in message.lower():
        return PermissionError(
            f"💾 **Google Drive Storage Quota Limit (0 MB Service Account Storage)**\n\n"
            f"Google Cloud returned: *\"{message}\"*\n\n"
            f"**Why this occurs:** Google Cloud Service Accounts have **0 MB** of personal Google Drive storage. "
            f"Google blocks a Service Account from owning files directly in personal Google Drive.\n\n"
            f"**Resolution (Pick one):**\n"
            f"1. **Google Workspace Shared Drive**: In the sidebar, select or paste an existing folder in a **Shared Drive** where {sa_str} is added as Contributor/Content Manager.\n"
            f"2. **Personal Drive Folder**: Open your personal Google Drive, create a folder, click **Share**, add {sa_str} as **Editor**, then select that folder in the sidebar."
        )

    # Case 3: Folder Permission Denied or Not Found
    if folder_id:
        if status_code == 404 or "not found" in message.lower():
            return PermissionError(
                f"📁 **Google Drive Folder Not Found or Inaccessible**\n\n"
                f"Target folder ID: `{folder_id}`\n\n"
                f"Google Drive returned: *\"{message}\"*\n\n"
                f"**Resolution:** Open Google Drive, locate this folder, click **Share**, and grant {sa_str} **Editor** permissions."
            )
        if status_code == 403 or "permission" in message.lower():
            return PermissionError(
                f"🔒 **Access Denied to Target Folder**\n\n"
                f"Target folder ID: `{folder_id}`\n\n"
                f"Google Drive returned: *\"{message}\"*\n\n"
                f"**Resolution:** Ensure that {sa_str} has been added as an **Editor** to the target folder in Google Drive."
            )

    # Case 4: No folder selected and creating file at root
    if not folder_id and (status_code == 403 or "caller does not have permission" in message.lower()):
        return PermissionError(
            f"📁 **Target Folder Required for Service Account**\n\n"
            f"Google Cloud returned: *\"{message}\"* when creating document at Drive root.\n\n"
            f"**Why this occurs:** Standalone Google Service Accounts do not have personal Google Drive storage (quota = 0 MB). "
            f"Google rejects creating documents at the root of a Service Account's drive.\n\n"
            f"**Resolution:** In the sidebar under **'📁 Drive Destination & Folder Browser'**, please select an accessible folder or Shared Drive, "
            f"or create a folder in your Google Drive, share it with {sa_str} as **Editor**, and select it."
        )

    # Case 5: Fallback generic permission error
    return PermissionError(
        f"⚠️ **Google API Permission Error (HTTP {status_code})**\n\n"
        f"**Google Error Message:** {message}\n\n"
        f"**Raw Error Details:** `{json.dumps(err_data or message)}`\n\n"
        f"**Troubleshooting:**\n"
        f"• Verify {sa_str} is added to the target folder as Editor.\n"
        f"• Verify Google Docs API and Google Drive API are enabled for project `{project_id}`."
    )
