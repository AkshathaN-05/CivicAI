"""LLM service orchestrator — T2-10.

Provides a transparent Groq → deterministic-fallback provider chain for all
three LLM use cases required by the CivicAI pipeline.

Public API:

    async def generate_complaint_description(
        cv_result: dict, location: str, address: str
    ) -> LLMOutput

    async def generate_rti_draft(
        complaint: dict, rag_context: str
    ) -> LLMOutput

    async def classify_category(image_context: dict) -> IssueCategory

Provider chain (LOCKED — Part A §9):
    1. Try Groq (primary).
    2. On any exception or LLMOutputInvalid → use deterministic fallback.
    3. Log which provider was used (audit).

The caller always receives a valid LLMOutput — the chain is transparent.

Design:
- ``GROQ_API_KEY`` env var drives whether Groq is attempted.
  If the key is absent the fallback is used immediately (no Groq attempt).
- Fallback is also used when GROQ_API_KEY is present but Groq raises any
  exception (network, rate-limit, auth, timeout, schema violation).
- generate_complaint_description uses T2-8 COMPLAINT_DESCRIPTION_PROMPT
  rendered with cv_result + address.
- classify_category uses T2-8 CATEGORY_CLASSIFICATION_PROMPT and returns
  only the IssueCategory from the resulting LLMOutput.
- generate_rti_draft uses T2-8 RTI_DRAFT_PROMPT rendered with complaint
  context + rag_context.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from llm.fallback_provider import (
    fallback_classify_category,
    fallback_complaint_description,
    fallback_rti_draft,
)
from llm.output_validator import LLMOutput, LLMOutputInvalid
from llm.prompts import (
    CATEGORY_CLASSIFICATION_PROMPT,
    COMPLAINT_DESCRIPTION_PROMPT,
    RTI_DRAFT_PROMPT,
    sanitize_for_prompt,
)
from schemas.report import IssueCategory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _groq_available() -> bool:
    """Return True when a GROQ_API_KEY is configured."""
    return bool(os.environ.get("GROQ_API_KEY", "").strip())


async def _try_groq(prompt: str) -> LLMOutput:
    """Attempt a Groq call; propagate LLMOutputInvalid on any failure."""
    from llm.groq_provider import call_groq
    return await call_groq(prompt)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_complaint_description(
    cv_result: dict[str, Any],
    location: str,
    address: str,
) -> LLMOutput:
    """Generate a complaint description from CV results.

    Tries Groq first.  Falls back to the deterministic template on any failure.

    Args:
        cv_result:  Dict with keys ``category`` (IssueCategory or str),
                    ``confidence`` (float), ``yolo_class`` (str).
        location:   Coordinates or location string from the citizen.
        address:    Human-readable address / area_text.

    Returns:
        Validated :class:`~llm.output_validator.LLMOutput`.
    """
    category = str(getattr(cv_result.get("category"), "value", cv_result.get("category", "other")))
    confidence = float(cv_result.get("confidence", 0.0))
    detected_objects = str(cv_result.get("yolo_class", ""))

    safe_address = sanitize_for_prompt(address or location or "Mangaluru")
    safe_objects = sanitize_for_prompt(detected_objects)

    if _groq_available():
        prompt = COMPLAINT_DESCRIPTION_PROMPT.format(
            category=category,
            address=safe_address,
            confidence=confidence,
            detected_objects=safe_objects,
        )
        try:
            result = await _try_groq(prompt)
            logger.info(
                "llm_service.generate_complaint_description: provider=groq "
                "category=%s",
                category,
            )
            return result
        except LLMOutputInvalid as exc:
            logger.warning(
                "llm_service.generate_complaint_description: groq failed (%s) "
                "— falling back to deterministic template.",
                exc,
            )

    result = fallback_complaint_description(
        category=category,
        address=safe_address,
        confidence=confidence,
        detected_objects=safe_objects,
    )
    logger.info(
        "llm_service.generate_complaint_description: provider=fallback "
        "category=%s",
        category,
    )
    return result


async def generate_rti_draft(
    complaint: dict[str, Any],
    rag_context: str = "",
) -> LLMOutput:
    """Generate an RTI draft letter from a complaint dict.

    Tries Groq first.  Falls back to the deterministic template on any failure.

    Args:
        complaint:   Dict with keys ``category``, ``address``, ``submitted_at``,
                     ``authority_name``, ``mock_gov_ref``, ``status``,
                     ``days_elapsed``.
        rag_context: Relevant RTI Act/MCC context retrieved from RAG (T2-12).
                     Empty string when RAG is not yet available.

    Returns:
        Validated :class:`~llm.output_validator.LLMOutput`.
    """
    category = str(complaint.get("category", "other"))
    address = sanitize_for_prompt(str(complaint.get("address", "Mangaluru")))
    submitted_at = str(complaint.get("submitted_at", ""))
    authority_name = sanitize_for_prompt(str(complaint.get("authority_name", "MCC")))
    mock_gov_ref = sanitize_for_prompt(str(complaint.get("mock_gov_ref", "N/A")))
    status = str(complaint.get("status", "SUBMITTED"))
    days_elapsed = int(complaint.get("days_elapsed", 0))
    safe_rag = sanitize_for_prompt(rag_context)

    if _groq_available():
        prompt = RTI_DRAFT_PROMPT.format(
            category=category,
            address=address,
            submitted_at=submitted_at,
            authority_name=authority_name,
            mock_gov_ref=mock_gov_ref,
            status=status,
            days_elapsed=days_elapsed,
            rag_context=safe_rag or "No additional context available.",
        )
        try:
            result = await _try_groq(prompt)
            logger.info(
                "llm_service.generate_rti_draft: provider=groq category=%s",
                category,
            )
            return result
        except LLMOutputInvalid as exc:
            logger.warning(
                "llm_service.generate_rti_draft: groq failed (%s) "
                "— falling back to deterministic template.",
                exc,
            )

    result = fallback_rti_draft(
        category=category,
        address=address,
        submitted_at=submitted_at,
        authority_name=authority_name or "MCC",
        mock_gov_ref=mock_gov_ref,
        status=status,
        days_elapsed=days_elapsed,
    )
    logger.info(
        "llm_service.generate_rti_draft: provider=fallback category=%s",
        category,
    )
    return result


async def classify_category(image_context: dict[str, Any]) -> IssueCategory:
    """Classify the civic category from image context (used when YOLO confidence < 0.5).

    Tries Groq first.  Falls back to the deterministic keyword classifier on
    any failure.

    Args:
        image_context:  Dict with keys ``detected_objects`` (str),
                        ``address`` (str), ``extra_context`` (str).

    Returns:
        :class:`~schemas.report.IssueCategory` best matching the image context.
    """
    detected_objects = sanitize_for_prompt(str(image_context.get("detected_objects", "")))
    address = sanitize_for_prompt(str(image_context.get("address", "Mangaluru")))
    extra_context = sanitize_for_prompt(str(image_context.get("extra_context", "")))

    if _groq_available():
        prompt = CATEGORY_CLASSIFICATION_PROMPT.format(
            detected_objects=detected_objects,
            address=address,
            extra_context=extra_context,
        )
        try:
            result = await _try_groq(prompt)
            logger.info(
                "llm_service.classify_category: provider=groq → %s",
                result.category.value,
            )
            return result.category
        except LLMOutputInvalid as exc:
            logger.warning(
                "llm_service.classify_category: groq failed (%s) "
                "— falling back to deterministic classifier.",
                exc,
            )

    result = fallback_classify_category(
        detected_objects=detected_objects,
        address=address,
    )
    logger.info(
        "llm_service.classify_category: provider=fallback → %s",
        result.category.value,
    )
    return result.category
