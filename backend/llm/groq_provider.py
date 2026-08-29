"""Groq API integration for CivicAI — T2-8.

Provides an async function that calls the Groq ``llama-3.1-8b-instant``
model with a structured prompt and returns a validated :class:`LLMOutput`.

Public API:

    async def call_groq(prompt: str, *, api_key: str | None = None,
                        timeout: float = 30.0) -> LLMOutput

Design decisions (LOCKED — Part A §9):
- Model: ``llama-3.1-8b-instant`` on Groq API.
- Output is expected as JSON embedded in the model's text response.
- Every response is validated with :func:`~llm.output_validator.validate_output`.
- Any error (network, timeout, bad JSON, schema violation) raises
  :class:`~llm.output_validator.LLMOutputInvalid` so callers can fall back
  to the deterministic template engine (T2-9).
- API key is read from the ``GROQ_API_KEY`` environment variable if not
  supplied explicitly.  It is NEVER logged or exposed to the frontend.
- A sane default timeout of 30 seconds is enforced.

Failure modes handled:
- :class:`groq.GroqError` (auth, rate-limit, server error)
- :class:`TimeoutError` / ``httpx.TimeoutException``
- JSON parse failure (model returned non-JSON text)
- Schema validation failure (:class:`LLMOutputInvalid` from output_validator)
- Empty / missing response content
"""
from __future__ import annotations

import json
import logging
import os
import re

import groq

from llm.output_validator import LLMOutput, LLMOutputInvalid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LOCKED: model identifier (Part A §9)
# ---------------------------------------------------------------------------
GROQ_MODEL: str = "llama-3.1-8b-instant"

# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

# Matches a JSON object that may be surrounded by markdown code fences or
# plain text.  The model often wraps its JSON in ```json ... ``` fences.
_JSON_BLOCK_RE: re.Pattern[str] = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL
)
_JSON_BARE_RE: re.Pattern[str] = re.compile(r"\{.*?\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from *text*.

    Tries markdown-fenced block first, then any bare ``{...}`` block.

    Args:
        text: Raw string from the LLM completion.

    Returns:
        Parsed Python dict.

    Raises:
        :class:`~llm.output_validator.LLMOutputInvalid`: If no valid JSON
            object is found or JSON parsing fails.
    """
    # Try fenced block first
    match = _JSON_BLOCK_RE.search(text)
    if match:
        raw_json = match.group(1)
    else:
        # Fall back to first bare {...} block
        match = _JSON_BARE_RE.search(text)
        if not match:
            raise LLMOutputInvalid(
                f"No JSON object found in LLM response: {text[:200]!r}"
            )
        raw_json = match.group(0)

    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise LLMOutputInvalid(
            f"Failed to parse JSON from LLM response: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def call_groq(
    prompt: str,
    *,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> LLMOutput:
    """Call the Groq API with *prompt* and return a validated :class:`LLMOutput`.

    The prompt must already have citizen text sanitized via
    :func:`~llm.prompts.sanitize_for_prompt` before being passed here.

    Args:
        prompt:  A fully rendered prompt string.  Must not contain
                 unsanitized citizen-supplied text.
        api_key: Groq API key.  Defaults to the ``GROQ_API_KEY`` environment
                 variable.  Never log or expose this value.
        timeout: Maximum seconds to wait for the Groq API response.
                 Defaults to 30 seconds.

    Returns:
        A validated :class:`~llm.output_validator.LLMOutput` instance.

    Raises:
        :class:`~llm.output_validator.LLMOutputInvalid`: On any failure
            (network, auth, timeout, bad JSON, schema violation, empty
            response).  Callers MUST catch this and activate the
            deterministic fallback (T2-9).
    """
    resolved_key: str | None = api_key or os.environ.get("GROQ_API_KEY")
    if not resolved_key:
        raise LLMOutputInvalid(
            "GROQ_API_KEY is not set — cannot call Groq API."
        )

    try:
        client = groq.AsyncGroq(api_key=resolved_key, timeout=timeout)
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a civic complaint assistant for Mangaluru, India. "
                        "Always respond with valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,  # low temperature for deterministic, factual output
            max_tokens=512,
        )
    except groq.GroqError as exc:
        logger.warning("Groq API error: %s", exc)
        raise LLMOutputInvalid(f"Groq API error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — network, timeout, etc.
        logger.warning("Groq call failed with unexpected error: %s", exc)
        raise LLMOutputInvalid(f"Groq call failed: {exc}") from exc

    # Extract text content from the response
    try:
        content: str = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise LLMOutputInvalid(
            f"Unexpected Groq response structure: {exc}"
        ) from exc

    if not content.strip():
        raise LLMOutputInvalid("Groq returned an empty response.")

    logger.debug("Groq raw response (%d chars): %.200s", len(content), content)

    # Parse JSON and validate against LLMOutput schema
    raw_dict = _extract_json(content)
    return validate_output(raw_dict)


# ---------------------------------------------------------------------------
# Import helper so callers can use a single import
# ---------------------------------------------------------------------------
from llm.output_validator import validate_output  # noqa: E402 — intentional re-export
