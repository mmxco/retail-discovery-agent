"""
Unit tests for OAuth 2.0 flow and credentials lifecycle (auth/google_oauth.py).
Tests client secret verification, token management, and service account validation.
"""

import os
import json
import tempfile
from unittest.mock import patch, MagicMock, PropertyMock
import pytest

from auth.google_oauth import (
    SCOPES,
    verify_client_secret,
    validate_service_account,
    get_user_oauth_credentials,
    clear_oauth_token,
    get_google_credentials,
    OAuthDesktopServer,
    start_oauth_desktop_flow,
)


def test_scopes_configuration():
    assert SCOPES == ["https://www.googleapis.com/auth/drive.file"], f"Strict drive.file scope required, got {SCOPES}"


def test_verify_client_secret_valid():
    valid_installed = {
        "installed": {
            "client_id": "test-client-123.apps.googleusercontent.com",
            "project_id": "my-retail-project",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "GOCSPX-secret123",
        }
    }
    res = verify_client_secret(valid_installed)
    assert res["valid"] is True
    assert res["app_type"] == "Desktop App (installed)"
    assert res["client_id"] == "test-client-123.apps.googleusercontent.com"
    assert res["project_id"] == "my-retail-project"

    # From JSON string
    res_str = verify_client_secret(json.dumps(valid_installed))
    assert res_str["valid"] is True


def test_verify_client_secret_invalid():
    # Missing required client_id
    invalid_cfg = {"installed": {"project_id": "proj"}}
    res = verify_client_secret(invalid_cfg)
    assert res["valid"] is False
    assert "Missing 'client_id'" in res["error"]

    # Missing installed or web root key
    res_no_root = verify_client_secret({"other": {}})
    assert res_no_root["valid"] is False
    assert "Expected a JSON file with an 'installed' or 'web' root key" in res_no_root["error"]


def test_validate_service_account_errors():
    # Empty
    assert validate_service_account("")["valid"] is False

    # Invalid JSON
    assert validate_service_account("{not-json}")["valid"] is False

    # Wrong type
    assert validate_service_account(json.dumps({"type": "authorized_user"}))["valid"] is False

    # Missing required fields
    incomplete = {"type": "service_account", "project_id": "test"}
    res_inc = validate_service_account(json.dumps(incomplete))
    assert res_inc["valid"] is False
    assert "Missing required service account fields" in res_inc["error"]


def test_token_lifecycle():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
        token_tmp = tf.name

    try:
        # Non-existent token returns None when flow not requested
        creds = get_user_oauth_credentials(token_path=token_tmp + "_nonexistent", run_flow_if_needed=False)
        assert creds is None

        # Clear existing token
        with open(token_tmp, "w") as f:
            f.write("{}")
        assert os.path.exists(token_tmp)
        assert clear_oauth_token(token_tmp) is True
        assert not os.path.exists(token_tmp)

        # Clear non-existent file returns False
        assert clear_oauth_token(token_tmp) is False
    finally:
        if os.path.exists(token_tmp):
            os.remove(token_tmp)


def test_get_google_credentials_fallback():
    # When no creds available and no token file, returns None gracefully
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
        dummy_path = tf.name

    try:
        creds = get_google_credentials(token_path=dummy_path + "_none")
        # May return ADC if machine has ADC, or None
        assert creds is None or hasattr(creds, "token")
    finally:
        if os.path.exists(dummy_path):
            os.remove(dummy_path)


def test_oauth_desktop_server_lifecycle():
    cfg = {
        "installed": {
            "client_id": "test.apps.googleusercontent.com",
            "project_id": "test-proj",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "secret123",
        }
    }
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
        tmp_token = tf.name

    server = None
    try:
        with patch.object(OAuthDesktopServer, "_run"):
            server = OAuthDesktopServer(cfg, token_path=tmp_token, timeout_seconds=5)
            assert server.port > 0
            assert "https://accounts.google.com" in server.auth_url
            assert server.state is not None
            assert server.is_running is True
            server.shutdown()
            assert server.is_running is False
    finally:
        if server:
            server.shutdown()
        if os.path.exists(tmp_token):
            os.remove(tmp_token)


def test_oauth_desktop_server_manual_exchange():
    cfg = {
        "installed": {
            "client_id": "test.apps.googleusercontent.com",
            "project_id": "test-proj",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "secret123",
        }
    }
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
        tmp_token = tf.name

    server = None
    try:
        with patch.object(OAuthDesktopServer, "_run"):
            server = OAuthDesktopServer(cfg, token_path=tmp_token, timeout_seconds=5)
            assert server.manual_exchange("") is False

            mock_creds = MagicMock()
            mock_creds.to_json.return_value = '{"token": "xyz"}'

            with patch.object(type(server.flow), "credentials", new_callable=PropertyMock, return_value=mock_creds), \
                 patch.object(server.flow, "fetch_token") as mock_fetch:
                ok = server.manual_exchange("4/0AY0e-test-code")
                assert ok is True
                assert server.is_authenticated is True
                mock_fetch.assert_called_once_with(code="4/0AY0e-test-code")
    finally:
        if server:
            server.shutdown()
        if os.path.exists(tmp_token):
            os.remove(tmp_token)

