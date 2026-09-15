"""
Retail Discovery Agent - Unified Gemini Client Service
Centralized LLM client service providing client instantiation, SSL injection & fallback,
rate-limit exponential backoff, and schema-constrained structured output generation.
"""

import os
import re
import time
import random
from typing import Optional, Type, TypeVar, Any
from pydantic import BaseModel, ValidationError

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from google import genai
from google.genai import types
from google.genai.errors import APIError

from core.config import get_logger, DEFAULT_MODEL_NAME

logger = get_logger("core.gemini")

T = TypeVar("T", bound=BaseModel)


def create_gemini_client(
    api_key: Optional[str] = None,
    disable_ssl_verify: bool = False,
) -> genai.Client:
    """
    Initializes and returns an official Google GenAI client with SSL options.

    Args:
        api_key: Optional API key; falls back to GEMINI_API_KEY environment variable.
        disable_ssl_verify: If True, bypasses SSL verification for corporate proxies.

    Returns:
        genai.Client instance.

    Raises:
        ValueError: If no API key is provided or found in environment.
    """
    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "Gemini API key is required. Set GEMINI_API_KEY environment variable or pass api_key."
        )

    http_opts = None
    if disable_ssl_verify:
        http_opts = types.HttpOptions(client_args={"verify": False})

    return genai.Client(api_key=resolved_api_key, http_options=http_opts)


def generate_structured_output(
    prompt: str,
    response_schema: Type[T],
    system_instruction: Optional[str] = None,
    model_name: str = DEFAULT_MODEL_NAME,
    api_key: Optional[str] = None,
    disable_ssl_verify: bool = False,
    temperature: float = 0.0,
    max_retries: int = 3,
    base_delay: float = 2.0,
    client: Optional[genai.Client] = None,
) -> T:
    """
    Executes a structured output generation call with automated retry,
    SSL verification fallback, and rate limit backoff.

    Args:
        prompt: The input user prompt.
        response_schema: The target Pydantic model class to constrain output to.
        system_instruction: Optional system instruction prompt.
        model_name: Gemini model name.
        api_key: Optional Gemini API key.
        disable_ssl_verify: If True, bypasses SSL verification.
        temperature: Sampling temperature (default 0.0 for deterministic extraction).
        max_retries: Maximum backoff retries.
        base_delay: Initial exponential backoff delay in seconds.
        client: Optional pre-configured client.

    Returns:
        An instance of response_schema.
    """
    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    active_client = client or create_gemini_client(
        api_key=resolved_api_key,
        disable_ssl_verify=disable_ssl_verify,
    )

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
        system_instruction=system_instruction,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    response = None
    ssl_bypassed = disable_ssl_verify

    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Invoking {model_name} with structured output for {response_schema.__name__} (attempt {attempt + 1})...")
            response = active_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            break
        except Exception as e:
            err_msg = str(e).lower()

            # Handle SSL certificate verification failure
            if ("certificate_verify_failed" in err_msg or "certificate verify failed" in err_msg or "ssl" in err_msg) and not ssl_bypassed:
                logger.warning("SSL verification failed (%s). Retrying with SSL verification bypass...", e)
                ssl_bypassed = True
                active_client = genai.Client(
                    api_key=resolved_api_key,
                    http_options=types.HttpOptions(client_args={"verify": False})
                )
                continue

            # Check for Rate Limit (429, RESOURCE_EXHAUSTED) or Temporary Unavailable (503)
            is_rate_limit = ("429" in err_msg or "resource_exhausted" in err_msg or "rate limit" in err_msg or "quota" in err_msg)
            is_transient = ("503" in err_msg or "unavailable" in err_msg or "overloaded" in err_msg)

            if (is_rate_limit or is_transient) and attempt < max_retries:
                backoff_delay = (base_delay * (2 ** attempt)) + random.uniform(0.1, 0.5)
                reason = "Rate limit / quota exceeded (429)" if is_rate_limit else "Service temporarily unavailable (503)"
                logger.warning(
                    f"{reason} on attempt {attempt + 1}/{max_retries + 1}. Backing off for {backoff_delay:.2f}s before retry..."
                )
                time.sleep(backoff_delay)
                continue

            logger.error(f"Gemini API generation failed after {attempt + 1} attempts: {e}")
            raise

    # Deserialize and validate into response_schema
    if hasattr(response, "parsed") and isinstance(response.parsed, response_schema):
        return response.parsed
    elif hasattr(response, "parsed") and isinstance(response.parsed, dict):
        return response_schema.model_validate(response.parsed)
    elif getattr(response, "text", None) and response.text.strip():
        raw_text = response.text.strip().lstrip("\ufeff")
        # Strip markdown code fences if LLM wrapped JSON in ```json ... ``` or included surrounding preamble/postamble
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text, flags=re.I)
        if fence_match:
            raw_text = fence_match.group(1).strip()
        elif raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.I)
            raw_text = re.sub(r"\s*```$", "", raw_text)
            raw_text = raw_text.strip()
        try:
            return response_schema.model_validate_json(raw_text)
        except ValidationError as ve:
            logger.error(f"Pydantic schema validation failed: {ve}")
            raise
    else:
        raise RuntimeError(f"Gemini returned an empty response with no parsed object or text content for {response_schema.__name__}.")


class GeminiClientService:
    """Service wrapper for interacting with Google GenAI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        disable_ssl_verify: bool = False,
        model_name: str = DEFAULT_MODEL_NAME,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.disable_ssl_verify = disable_ssl_verify
        self.model_name = model_name
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = create_gemini_client(
                api_key=self.api_key,
                disable_ssl_verify=self.disable_ssl_verify,
            )
        return self._client

    def generate(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 3,
    ) -> T:
        """Generates structured output constrained to response_schema."""
        return generate_structured_output(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
            model_name=model_name or self.model_name,
            api_key=self.api_key,
            disable_ssl_verify=self.disable_ssl_verify,
            temperature=temperature,
            max_retries=max_retries,
            client=self.client,
        )
