"""
Unit tests for the centralized Gemini client service (core/gemini.py).
Tests client instantiation, SSL retry fallback, rate limit backoff, and structured output parsing.
"""

import pytest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel

from core.gemini import (
    create_gemini_client,
    generate_structured_output,
    GeminiClientService,
)


class DummySchema(BaseModel):
    name: str
    score: int


def test_create_gemini_client_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Gemini API key is required"):
        create_gemini_client(api_key="")


def test_create_gemini_client_success():
    client = create_gemini_client(api_key="test-key", disable_ssl_verify=True)
    assert client is not None


def test_generate_structured_output_from_parsed():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = DummySchema(name="Retail Co", score=95)
    mock_client.models.generate_content.return_value = mock_response

    result = generate_structured_output(
        prompt="Analyze retail account",
        response_schema=DummySchema,
        api_key="test-key",
        client=mock_client,
    )

    assert isinstance(result, DummySchema)
    assert result.name == "Retail Co"
    assert result.score == 95
    assert mock_client.models.generate_content.call_count == 1


def test_generate_structured_output_from_text():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = '{"name": "Apparel Brand", "score": 88}'
    mock_client.models.generate_content.return_value = mock_response

    result = generate_structured_output(
        prompt="Analyze retail account",
        response_schema=DummySchema,
        api_key="test-key",
        client=mock_client,
    )

    assert result.name == "Apparel Brand"
    assert result.score == 88


def test_generate_structured_output_ssl_retry():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = DummySchema(name="SSL Success", score=100)

    # First call raises SSLCertVerificationError / certificate_verify_failed, second call succeeds
    mock_client.models.generate_content.side_effect = [
        Exception("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"),
        mock_response,
    ]

    with patch("core.gemini.genai.Client") as mock_client_cls:
        fallback_client = MagicMock()
        fallback_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = fallback_client

        result = generate_structured_output(
            prompt="Analyze retail account",
            response_schema=DummySchema,
            api_key="test-key",
            client=mock_client,
            disable_ssl_verify=False,
        )

        assert result.name == "SSL Success"


def test_generate_structured_output_rate_limit_backoff():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = DummySchema(name="Rate Limit Handled", score=90)

    # First call fails with 429 Resource Exhausted, second succeeds
    mock_client.models.generate_content.side_effect = [
        Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded"),
        mock_response,
    ]

    with patch("core.gemini.time.sleep") as mock_sleep:
        result = generate_structured_output(
            prompt="Analyze",
            response_schema=DummySchema,
            api_key="test-key",
            client=mock_client,
            max_retries=2,
            base_delay=0.1,
        )
        assert result.name == "Rate Limit Handled"
        assert mock_sleep.call_count == 1


def test_gemini_client_service():
    service = GeminiClientService(api_key="dummy-key", model_name="gemini-2.5-flash")
    with patch.object(service, "generate") as mock_gen:
        mock_gen.return_value = DummySchema(name="From Service", score=75)
        res = service.generate("prompt", DummySchema)
        assert res.name == "From Service"


def test_generate_structured_output_markdown_fenced_json():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = None
    # Simulate LLM response wrapped in markdown code fence
    mock_response.text = '```json\n{"name": "Apparel Brand", "score": 99}\n```'
    mock_client.models.generate_content.return_value = mock_response

    result = generate_structured_output(
        prompt="Analyze retail account",
        response_schema=DummySchema,
        api_key="test-key",
        client=mock_client,
    )

    assert result.name == "Apparel Brand"
    assert result.score == 99


def test_generate_structured_output_markdown_with_conversational_preamble_and_bom():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = None
    # Simulate LLM response with conversational preamble, BOM, and postamble enclosing JSON code fence
    mock_response.text = (
        "\ufeffHere is your extracted discovery analysis in JSON format:\n\n"
        "```json\n"
        "{\"name\": \"Luxury Fashion Retailer\", \"score\": 95}\n"
        "```\n\n"
        "Please let me know if you need further clarifications!"
    )
    mock_client.models.generate_content.return_value = mock_response

    result = generate_structured_output(
        prompt="Analyze retail account",
        response_schema=DummySchema,
        api_key="test-key",
        client=mock_client,
    )

    assert result.name == "Luxury Fashion Retailer"
    assert result.score == 95

