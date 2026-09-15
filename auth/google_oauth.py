"""
Google OAuth 2.0 & Credentials Lifecycle Management
Handles OAuth 2.0 Desktop App authorization server, token refresh and storage,
service account validation, and Google credentials resolution.
"""

import os
import json
import threading
import wsgiref.simple_server
from typing import Optional, Dict, Any, List, Union

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from googleapiclient.discovery import build
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

from core.config import get_logger, SCOPES

logger = get_logger("auth.google_oauth")

__all__ = [
    "SCOPES",
    "validate_service_account",
    "verify_client_secret",
    "OAuthDesktopServer",
    "start_oauth_desktop_flow",
    "get_user_oauth_credentials",
    "get_authenticated_user_info",
    "clear_oauth_token",
    "get_google_credentials",
]


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
    Manages OAuth 2.0 User Credentials lifecycle for Desktop App flow.
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
    scopes: Optional[List[str]] = None,
) -> Optional[Any]:
    """Resolves Google Cloud credentials with priority: OAuth 2.0 User Credentials > Service Account > ADC."""
    target_scopes = scopes or SCOPES

    # 1. Direct OAuth Credentials object
    if oauth_credentials and getattr(oauth_credentials, "valid", False):
        return oauth_credentials

    # 2. Check local token.json for valid OAuth 2.0 User Credentials
    user_creds = get_user_oauth_credentials(token_path=token_path, run_flow_if_needed=False, scopes=target_scopes)
    if user_creds and user_creds.valid:
        return user_creds

    # 3. From direct Service Account JSON string
    if credentials_json:
        try:
            info = json.loads(credentials_json)
            return service_account.Credentials.from_service_account_info(info, scopes=target_scopes)
        except Exception as e:
            logger.warning(f"Failed to load credentials from JSON string: {e}")

    # 4. From file path
    file_path = service_account_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if file_path and os.path.isfile(file_path):
        try:
            return service_account.Credentials.from_service_account_file(file_path, scopes=target_scopes)
        except Exception as e:
            logger.warning(f"Failed to load credentials from file '{file_path}': {e}")

    # 5. From Application Default Credentials (ADC)
    try:
        creds, _ = google_auth_default(scopes=target_scopes)
        return creds
    except Exception as e:
        logger.info(f"ADC not available: {e}")

    return None
