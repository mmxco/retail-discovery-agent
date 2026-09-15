"""
Enterprise Google Docs & Drive Exporter
Compatibility bridge re-exporting decomposed modules:
- auth.google_oauth: OAuth 2.0 flow, server, and credential lifecycle
- integrations.drive_service: Drive folder CRUD, validation, and diagnostics
- exporters.gdocs_exporter: Google Docs brief builder and publishing
- exporters.markdown_exporter: Markdown executive brief export
"""

from googleapiclient.discovery import build

from auth.google_oauth import (
    SCOPES,
    validate_service_account,
    verify_client_secret,
    OAuthDesktopServer,
    start_oauth_desktop_flow,
    get_user_oauth_credentials,
    get_authenticated_user_info,
    clear_oauth_token,
    get_google_credentials,
)

from integrations.drive_service import (
    extract_folder_id,
    list_drive_folders,
    validate_drive_folder,
    create_drive_folder,
    diagnose_google_http_error,
)

from exporters.gdocs_exporter import (
    GoogleDocsBriefBuilder,
    export_dossier_to_google_doc,
)

from exporters.markdown_exporter import (
    export_dossier_to_markdown,
)

__all__ = [
    "build",
    "SCOPES",
    "validate_service_account",
    "verify_client_secret",
    "OAuthDesktopServer",
    "start_oauth_desktop_flow",
    "get_user_oauth_credentials",
    "get_authenticated_user_info",
    "clear_oauth_token",
    "get_google_credentials",
    "extract_folder_id",
    "list_drive_folders",
    "validate_drive_folder",
    "create_drive_folder",
    "diagnose_google_http_error",
    "GoogleDocsBriefBuilder",
    "export_dossier_to_google_doc",
    "export_dossier_to_markdown",
]
