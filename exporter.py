"""
Enterprise Google Docs Exporter Module
Takes a DiscoveryDossier instance, formats a styled executive briefing brief,
and creates the document using the Google Docs & Google Drive APIs.
Includes fallback to styled Markdown export if credentials are not configured.
"""

import os
import re
import json
import logging
import threading
import wsgiref.simple_server
from typing import Optional, Dict, Any, Tuple, List, Union
from datetime import datetime

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import (
    InstalledAppFlow,
    _RedirectWSGIApp,
    _ExclusiveWSGIServer,
    _WSGIRequestHandler,
)

from models import DiscoveryDossier

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
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


def validate_service_account(credentials_json: str) -> Dict[str, Any]:
    """
    Validates a Google Service Account JSON payload immediately upon upload.
    Checks JSON syntax, required fields, parses credentials, and verifies the private key.
    Attempts a live token refresh handshake with Google Auth endpoints.
    """
    if not credentials_json or not credentials_json.strip():
        return {
            "valid": False,
            "error": "Uploaded file is empty.",
            "client_email": "",
            "project_id": "",
            "handshake_successful": False,
        }

    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "error": f"Invalid JSON format: {str(e)}",
            "client_email": "",
            "project_id": "",
            "handshake_successful": False,
        }

    if not isinstance(info, dict):
        return {
            "valid": False,
            "error": "JSON payload must be an object/dictionary, not a list or scalar.",
            "client_email": "",
            "project_id": "",
            "handshake_successful": False,
        }

    doc_type = info.get("type")
    if doc_type != "service_account":
        return {
            "valid": False,
            "error": (
                f"Invalid credential type '{doc_type}'. Expected a Google Cloud Service Account "
                "JSON key with 'type': 'service_account'."
            ),
            "client_email": info.get("client_email", ""),
            "project_id": info.get("project_id", ""),
            "handshake_successful": False,
        }

    required_fields = ["project_id", "private_key", "client_email", "token_uri"]
    missing = [f for f in required_fields if f not in info or not info[f]]
    if missing:
        return {
            "valid": False,
            "error": f"Missing required service account fields: {', '.join(missing)}",
            "client_email": info.get("client_email", ""),
            "project_id": info.get("project_id", ""),
            "handshake_successful": False,
        }

    client_email = info.get("client_email", "")
    project_id = info.get("project_id", "")

    # Test key parsing
    try:
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    except Exception as parse_err:
        return {
            "valid": False,
            "error": f"Corrupted or invalid private key: {str(parse_err)}",
            "client_email": client_email,
            "project_id": project_id,
            "handshake_successful": False,
        }

    # Attempt live authentication token handshake
    try:
        import google.auth.transport.requests
        req = google.auth.transport.requests.Request()
        creds.refresh(req)
        return {
            "valid": True,
            "client_email": client_email,
            "project_id": project_id,
            "error": None,
            "handshake_successful": True,
            "message": f"Successfully authenticated as {client_email} (Project: {project_id})",
        }
    except Exception as handshake_err:
        err_msg = str(handshake_err)
        err_lower = err_msg.lower()
        if any(keyword in err_lower for keyword in ["invalid_grant", "unauthorized", "deleted", "revoked"]):
            return {
                "valid": False,
                "error": f"Google authentication failed: {err_msg}",
                "client_email": client_email,
                "project_id": project_id,
                "handshake_successful": False,
            }
        else:
            # Structure and key are valid, but network/proxy had a transient handshake note
            return {
                "valid": True,
                "client_email": client_email,
                "project_id": project_id,
                "error": None,
                "handshake_successful": False,
                "warning": f"Credentials structure valid. Live handshake note: {err_msg}",
                "message": f"Service account {client_email} (Project: {project_id})",
            }


def verify_client_secret(client_secret_data_or_path: Union[str, dict]) -> Dict[str, Any]:
    """
    Validates a Google OAuth 2.0 client_secret configuration.
    Accepts a filepath, JSON string, or dictionary.
    Verifies that the configuration has an 'installed' or 'web' block with client_id and client_secret.
    """
    info = None
    if isinstance(client_secret_data_or_path, dict):
        info = client_secret_data_or_path
    elif isinstance(client_secret_data_or_path, str):
        content = client_secret_data_or_path.strip()
        if os.path.isfile(content):
            try:
                with open(content, "r", encoding="utf-8") as f:
                    info = json.load(f)
            except Exception as e:
                return {
                    "valid": False,
                    "error": f"Failed to read client_secret file '{content}': {str(e)}",
                    "client_id": "",
                    "project_id": "",
                    "app_type": "",
                }
        else:
            try:
                info = json.loads(content)
            except Exception as e:
                return {
                    "valid": False,
                    "error": f"Invalid JSON format for client_secret: {str(e)}",
                    "client_id": "",
                    "project_id": "",
                    "app_type": "",
                }
    else:
        return {
            "valid": False,
            "error": "client_secret must be a dictionary, JSON string, or valid file path.",
            "client_id": "",
            "project_id": "",
            "app_type": "",
        }

    if not isinstance(info, dict):
        return {
            "valid": False,
            "error": "client_secret payload must be a JSON object.",
            "client_id": "",
            "project_id": "",
            "app_type": "",
        }

    # Desktop app secrets have 'installed', web apps have 'web'
    app_type = ""
    client_block = None
    if "installed" in info and isinstance(info["installed"], dict):
        app_type = "Desktop App (installed)"
        client_block = info["installed"]
    elif "web" in info and isinstance(info["web"], dict):
        app_type = "Web App (web)"
        client_block = info["web"]
    else:
        return {
            "valid": False,
            "error": "Invalid client_secret format. Expected a JSON file with an 'installed' or 'web' root key from Google Cloud Console.",
            "client_id": "",
            "project_id": "",
            "app_type": "",
        }

    client_id = client_block.get("client_id", "").strip()
    client_secret = client_block.get("client_secret", "").strip()
    project_id = client_block.get("project_id", "").strip()

    if not client_id:
        return {
            "valid": False,
            "error": "Missing 'client_id' inside client_secret.",
            "client_id": "",
            "project_id": project_id,
            "app_type": app_type,
        }

    if not client_secret:
        return {
            "valid": False,
            "error": "Missing 'client_secret' inside client_secret.",
            "client_id": client_id,
            "project_id": project_id,
            "app_type": app_type,
        }

    is_installed = "installed" in info
    return {
        "valid": True,
        "error": None,
        "client_id": client_id,
        "project_id": project_id,
        "app_type": app_type,
        "is_installed_type": is_installed,
        "client_config": info,
        "message": f"Valid OAuth 2.0 {app_type} Client Secret (Project: {project_id or 'unknown'})",
    }


class OAuthDesktopServer:
    """
    Non-blocking local redirect server for OAuth 2.0 InstalledAppFlow (Desktop App flow).
    Runs the local WSGI server in a background daemon thread so Streamlit's web interface
    never freezes or dims while awaiting authorization.
    Generates an auth_url that can be directly opened in Google Chrome via st.link_button.
    """

    def __init__(
        self,
        client_config: dict,
        scopes: Optional[List[str]] = None,
        token_path: str = "token.json",
        timeout_seconds: int = 300,
    ):
        self.scopes = scopes or SCOPES
        self.token_path = token_path
        self.timeout_seconds = timeout_seconds
        self.client_config = client_config
        self.flow = InstalledAppFlow.from_client_config(client_config, self.scopes)

        success_message = (
            "<!DOCTYPE html><html><head><title>Authentication Successful</title>"
            "<meta charset='utf-8'>"
            "<style>"
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; "
            "text-align: center; padding: 60px 20px; background: #f8fafc; color: #1e293b; margin: 0; }"
            ".card { background: white; border-radius: 12px; padding: 40px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); display: inline-block; max-width: 520px; border: 1px solid #e2e8f0; }"
            "h2 { color: #15803d; margin-top: 0; font-size: 24px; }"
            "p { line-height: 1.6; color: #475569; font-size: 15px; }"
            ".pill { background: #dcfce7; color: #166534; font-weight: 600; padding: 6px 14px; border-radius: 9999px; display: inline-block; margin-bottom: 16px; font-size: 13px; }"
            "</style></head><body>"
            "<div class='card'>"
            "<div class='pill'>Google Drive API Connected</div>"
            "<h2>Authentication Successful!</h2>"
            "<p>Your Google account has been authorized for Retail Discovery Agent exports.</p>"
            "<p><strong>You can safely close this browser tab</strong> and return to the application.</p>"
            "</div></body></html>"
        )
        self.wsgi_app = _RedirectWSGIApp(success_message)
        self.server = wsgiref.simple_server.make_server(
            "127.0.0.1",
            0,
            self.wsgi_app,
            server_class=_ExclusiveWSGIServer,
            handler_class=_WSGIRequestHandler,
        )
        self.port = self.server.server_port
        self.flow.redirect_uri = f"http://localhost:{self.port}/"

        self.auth_url, self.state = self.flow.authorization_url(
            prompt="consent",
            access_type="offline",
        )

        self.is_authenticated = False
        self.error: Optional[str] = None
        self.credentials: Optional[Credentials] = None
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.server.timeout = self.timeout_seconds
            self.server.handle_request()
            if self.wsgi_app.last_request_uri:
                auth_resp = self.wsgi_app.last_request_uri.replace("http://", "https://", 1)
                self.flow.fetch_token(authorization_response=auth_resp)
                self.credentials = self.flow.credentials
                with open(self.token_path, "w", encoding="utf-8") as f:
                    f.write(self.credentials.to_json())
                self.is_authenticated = True
                logger.info(f"OAuth 2.0 user credentials obtained and saved to {self.token_path}")
        except Exception as e:
            self.error = str(e)
            logger.warning(f"OAuth background server note: {e}")
        finally:
            self.is_running = False
            try:
                self.server.server_close()
            except Exception:
                pass

    def manual_exchange(self, response_or_code: str) -> bool:
        """Fallback for manually pasting authorization code or redirect URL."""
        try:
            clean = response_or_code.strip()
            if not clean:
                return False
            if clean.startswith("http://") or clean.startswith("https://"):
                auth_resp = clean.replace("http://", "https://", 1)
                self.flow.fetch_token(authorization_response=auth_resp)
            else:
                self.flow.fetch_token(code=clean)
            self.credentials = self.flow.credentials
            with open(self.token_path, "w", encoding="utf-8") as f:
                f.write(self.credentials.to_json())
            self.is_authenticated = True
            self.is_running = False
            try:
                self.server.server_close()
            except Exception:
                pass
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def shutdown(self):
        """Terminates the background redirect listener."""
        self.is_running = False
        try:
            self.server.server_close()
        except Exception:
            pass


def start_oauth_desktop_flow(
    client_secret_data_or_path: Union[str, dict],
    scopes: Optional[List[str]] = None,
    token_path: str = "token.json",
    timeout_seconds: int = 300,
) -> OAuthDesktopServer:
    """
    Starts a non-blocking OAuth 2.0 InstalledAppFlow server on a dynamic port in a background daemon thread.
    Returns the OAuthDesktopServer instance containing auth_url, port, state, and background listener.
    """
    client_config = None
    if isinstance(client_secret_data_or_path, dict):
        client_config = client_secret_data_or_path
    elif isinstance(client_secret_data_or_path, str):
        content = client_secret_data_or_path.strip()
        if os.path.isfile(content):
            with open(content, "r", encoding="utf-8") as f:
                client_config = json.load(f)
        else:
            client_config = json.loads(content)
    else:
        raise ValueError("client_secret_data_or_path must be a dictionary, JSON string, or file path.")

    return OAuthDesktopServer(
        client_config=client_config,
        scopes=scopes or SCOPES,
        token_path=token_path,
        timeout_seconds=timeout_seconds,
    )


def get_user_oauth_credentials(
    client_secret_path: Optional[str] = None,
    client_secret_json: Optional[str] = None,
    token_path: str = "token.json",
    run_flow_if_needed: bool = False,
    scopes: Optional[List[str]] = None,
) -> Optional[Credentials]:
    """
    Manages OAuth 2.0 User Credentials lifecycle for Desktop App flow:
    1. Inspects local token.json.
    2. Validates token; if expired and has refresh_token, automatically refreshes with Request().
    3. Saves refreshed token back to token.json.
    4. If no valid token and run_flow_if_needed is True, launches InstalledAppFlow.run_local_server(port=0).
    5. Saves newly obtained credentials to token.json and returns Credentials.
    """
    target_scopes = scopes or SCOPES
    creds = None

    # Step 1: Check existing token file
    if os.path.isfile(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, target_scopes)
        except Exception as e:
            logger.warning(f"Could not load authorized user credentials from {token_path}: {e}")
            creds = None

    # Step 2: Validate or Refresh existing token
    if creds:
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            try:
                req = Request()
                creds.refresh(req)
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                logger.info(f"Successfully refreshed and updated OAuth 2.0 user credentials in {token_path}")
                return creds
            except Exception as e:
                logger.warning(f"Failed to refresh OAuth 2.0 token: {e}")
                creds = None

    # Step 3: Run interactive InstalledAppFlow if needed and requested
    if not run_flow_if_needed:
        return None

    # Resolve client configuration
    flow = None
    if client_secret_json:
        try:
            client_config = json.loads(client_secret_json) if isinstance(client_secret_json, str) else client_secret_json
            flow = InstalledAppFlow.from_client_config(client_config, target_scopes)
        except Exception as e:
            raise ValueError(f"Invalid client_secret JSON configuration: {e}") from e
    elif client_secret_path and os.path.isfile(client_secret_path):
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, target_scopes)
    elif os.path.isfile("client_secret.json"):
        flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", target_scopes)
    else:
        raise FileNotFoundError(
            "OAuth 2.0 client_secret file or JSON not found. Please provide client_secret.json to authenticate."
        )

    logger.info("Starting local OAuth redirect server on dynamic port (run_local_server)...")
    creds = flow.run_local_server(port=0, prompt="consent")

    # Persist token.json
    try:
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info(f"Saved authorized OAuth 2.0 user token to {token_path}")
    except Exception as e:
        logger.warning(f"Could not save token to {token_path}: {e}")

    return creds


def get_authenticated_user_info(creds: Credentials) -> Dict[str, Any]:
    """Retrieves user profile (email, name) for authenticated OAuth credentials."""
    try:
        drive_service = build("drive", "v3", credentials=creds)
        about = drive_service.about().get(fields="user(displayName, emailAddress, photoLink)").execute()
        user = about.get("user", {})
        return {
            "success": True,
            "email": user.get("emailAddress", ""),
            "display_name": user.get("displayName", ""),
            "photo_link": user.get("photoLink", ""),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "email": "",
            "display_name": "",
            "photo_link": "",
            "error": str(e),
        }


def clear_oauth_token(token_path: str = "token.json") -> bool:
    """Safely removes local token.json for signing out or switching accounts."""
    try:
        if os.path.isfile(token_path):
            os.remove(token_path)
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed to remove token file {token_path}: {e}")
        return False


def get_google_credentials(
    oauth_credentials: Optional[Any] = None,
    credentials_json: Optional[str] = None,
    service_account_path: Optional[str] = None,
    token_path: str = "token.json",
) -> Optional[Any]:
    """Resolves Google Cloud credentials with priority: OAuth 2.0 User Credentials > Service Account > ADC."""
    # 1. Direct OAuth Credentials object
    if oauth_credentials and getattr(oauth_credentials, "valid", False):
        return oauth_credentials

    # 2. Check local token.json for valid OAuth 2.0 User Credentials
    user_creds = get_user_oauth_credentials(token_path=token_path, run_flow_if_needed=False)
    if user_creds and user_creds.valid:
        return user_creds

    # 3. From direct Service Account JSON string
    if credentials_json:
        try:
            info = json.loads(credentials_json)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load credentials from JSON string: {e}")

    # 4. From file path
    file_path = service_account_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if file_path and os.path.isfile(file_path):
        try:
            return service_account.Credentials.from_service_account_file(file_path, scopes=SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load credentials from file '{file_path}': {e}")

    # 5. From Application Default Credentials (ADC)
    try:
        creds, _ = google_auth_default(scopes=SCOPES)
        return creds
    except Exception as e:
        logger.info(f"ADC not available: {e}")

    return None


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

    # Case 2: Storage Quota Exceeded (Common with Service Accounts creating files in personal Drive)
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

    # Case 4: No folder selected and caller does not have permission (creating file at root)
    if not folder_id and (status_code == 403 or "caller does not have permission" in message.lower()):
        return PermissionError(
            f"📁 **Target Folder Required for Service Account**\n\n"
            f"Google Cloud returned: *\"{message}\"* when creating document at Drive root.\n\n"
            f"**Why this occurs:** Standalone Google Service Accounts do not have personal Google Drive storage (quota = 0 MB). "
            f"Google rejects creating documents at the root of a Service Account's drive.\n\n"
            f"**Resolution:** In the sidebar under **'📁 Drive Destination & Folder Browser'**, please select an accessible folder or Shared Drive, "
            f"or create a folder in your Google Drive, share it with {sa_str} as **Editor**, and select it."
        )

    # Case 5: Fallback generic permission error with raw details preserved
    return PermissionError(
        f"⚠️ **Google API Permission Error (HTTP {status_code})**\n\n"
        f"**Google Error Message:** {message}\n\n"
        f"**Raw Error Details:** `{json.dumps(err_data or message)}`\n\n"
        f"**Troubleshooting:**\n"
        f"• Verify {sa_str} is added to the target folder as Editor.\n"
        f"• Verify Google Docs API and Google Drive API are enabled for project `{project_id}`."
    )


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



def export_dossier_to_markdown(dossier: DiscoveryDossier) -> str:
    """Generates a styled Markdown executive briefing representation of the dossier."""
    lines = [
        f"# Executive Discovery Brief for {dossier.account_name}",
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
