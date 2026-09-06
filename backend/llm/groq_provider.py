"""Groq API integration for CivicAI — T2-8.

Provides async functions that call Groq LLM models with structured prompts
and return validated outputs.

Public API:

    async def call_groq(prompt: str, *, api_key: str | None = None,
                        timeout: float = 30.0) -> LLMOutput

    async def civic_classify_image(
        image_bytes: bytes,
        address: str = "",
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> CivicClassificationResult

Design decisions (LOCKED — Part A §9):
- Text model: ``llama-3.1-8b-instant`` on Groq API.
- Vision model: ``meta-llama/llama-4-scout-17b-16e-instruct`` on Groq API.
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

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import groq

from llm.output_validator import LLMOutput, LLMOutputInvalid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LOCKED: model identifiers (Part A §9)
# ---------------------------------------------------------------------------
GROQ_MODEL: str = "llama-3.1-8b-instant"
# Vision model — supports image input via base64 URL
GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

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
# CivicClassificationResult — result of vision-based civic image classification
# ---------------------------------------------------------------------------

@dataclass
class CivicClassificationResult:
    """Result of vision-based civic image classification.

    Attributes:
        valid:               True when the image shows a genuine civic issue.
        category:            Civic category string (e.g. 'pothole', 'sewage',
                             'invalid'). Uses the vision-model vocabulary which
                             is then mapped to IssueCategory by the caller.
        category_confidence: Model confidence in the category (0.0–1.0).
        severity:            'low', 'medium', 'high', or None.
        severity_score:      Numeric severity in [0.0, 1.0].
        description:         Specific, evidence-based description of what is
                             visible in the image.
        reason:              Brief reason for the validity decision.
    """
    valid: bool
    category: str
    category_confidence: float
    severity: Optional[str]
    severity_score: float
    description: str
    reason: str


def _parse_civic_classification(raw: dict) -> CivicClassificationResult:
    """Parse and validate a raw dict into a CivicClassificationResult.

    Raises LLMOutputInvalid on missing / invalid fields.
    """
    try:
        valid = bool(raw.get("valid", False))
        category = str(raw.get("category", "invalid")).strip().lower()
        cat_conf = float(raw.get("category_confidence", 0.0))
        cat_conf = max(0.0, min(1.0, cat_conf))
        severity_raw = raw.get("severity")
        severity = str(severity_raw).lower() if severity_raw and severity_raw != "null" else None
        if severity not in ("low", "medium", "high", None):
            severity = None
        sev_score = float(raw.get("severity_score", 0.0))
        sev_score = max(0.0, min(1.0, sev_score))
        description = str(raw.get("description", ""))[:500]
        reason = str(raw.get("reason", ""))[:200]
    except (TypeError, ValueError) as exc:
        raise LLMOutputInvalid(
            f"CivicClassificationResult parse error: {exc}"
        ) from exc

    return CivicClassificationResult(
        valid=valid,
        category=category,
        category_confidence=cat_conf,
        severity=severity,
        severity_score=sev_score,
        description=description,
        reason=reason,
    )


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


async def civic_classify_image(
    image_bytes: bytes,
    address: str = "",
    *,
    api_key: str | None = None,
    timeout: float = 30.0,
) -> CivicClassificationResult:
    """Classify a civic image using Groq's vision model.

    Encodes the image as a base64 data URL and sends it to the Groq vision
    model with the CIVIC_IMAGE_CLASSIFICATION_PROMPT.  Returns a structured
    :class:`CivicClassificationResult`.

    This is called when:
    - YOLO detects nothing (no objects) or maps to ``other`` with low confidence
    - The raw YOLO detection confidence is below the threshold (< 0.5)

    Args:
        image_bytes: JPEG bytes of the validated image (after T2-2 validation).
                     The image has already been resized to max 1024px.
        address:     Human-readable address/location string (may be empty).
        api_key:     Groq API key. Defaults to GROQ_API_KEY env var.
        timeout:     Maximum seconds to wait for the Groq API response.

    Returns:
        :class:`CivicClassificationResult` with classification details.

    Raises:
        :class:`~llm.output_validator.LLMOutputInvalid`: On any failure
            (network, auth, timeout, bad JSON).  Callers MUST catch this
            and activate the deterministic fallback.
    """
    from llm.prompts import CIVIC_IMAGE_CLASSIFICATION_PROMPT, sanitize_for_prompt

    resolved_key: str | None = api_key or os.environ.get("GROQ_API_KEY")
    if not resolved_key:
        raise LLMOutputInvalid(
            "GROQ_API_KEY is not set — cannot call Groq vision API."
        )

    safe_address = sanitize_for_prompt(address or "")

    # Encode image as base64 data URL
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    image_url = f"data:image/jpeg;base64,{b64_image}"

    prompt_text = CIVIC_IMAGE_CLASSIFICATION_PROMPT.format(address=safe_address)

    try:
        client = groq.AsyncGroq(api_key=resolved_key, timeout=timeout)
        response = await client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_text,
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
            temperature=0.1,  # very low temperature for deterministic classification
            max_tokens=512,
        )
    except groq.GroqError as exc:
        logger.warning("Groq vision API error: %s", exc)
        raise LLMOutputInvalid(f"Groq vision API error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("Groq vision call failed: %s", exc)
        raise LLMOutputInvalid(f"Groq vision call failed: {exc}") from exc

    try:
        content: str = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise LLMOutputInvalid(
            f"Unexpected Groq vision response structure: {exc}"
        ) from exc

    if not content.strip():
        raise LLMOutputInvalid("Groq vision returned an empty response.")

    logger.debug(
        "Groq vision raw response (%d chars): %.300s", len(content), content
    )

    raw_dict = _extract_json(content)
    return _parse_civic_classification(raw_dict)


# ---------------------------------------------------------------------------
# Import helper so callers can use a single import
# ---------------------------------------------------------------------------
from llm.output_validator import validate_output  # noqa: E402 — intentional re-export
