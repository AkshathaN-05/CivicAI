"""Prompt templates and prompt injection protection — T2-8.

Three prompt templates are provided:

    COMPLAINT_DESCRIPTION_PROMPT  — generate a civic complaint description
    RTI_DRAFT_PROMPT              — draft an RTI letter
    CATEGORY_CLASSIFICATION_PROMPT — classify an ambiguous civic category

Public API:

    sanitize_for_prompt(text: str) -> str
        Strips prompt-injection patterns and enforces a hard length cap.

LOCKED decisions (Part A §9):
- All citizen-supplied text must be sanitized before injection.
- Hard length limit: 2 000 characters per field.
- Injection patterns defined in architecture Part B §LLM Prompt Construction.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Injection patterns (architecture Part B §LLM Prompt Construction)
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: list[str] = [
    r"ignore previous instructions",
    r"system prompt",
    r"\bforget\b.{0,20}\binstructions\b",
    r"<\|.*?\|>",  # special tokens (e.g. <|endoftext|>)
]

_COMPILED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL) for p in INJECTION_PATTERNS
]

_MAX_PROMPT_INPUT_LENGTH: int = 2_000  # hard cap per field (architecture §13)


def sanitize_for_prompt(text: str) -> str:
    """Sanitize citizen-supplied text before injecting it into an LLM prompt.

    1. Replace each injection pattern with the literal token ``[removed]``.
    2. Truncate to :data:`_MAX_PROMPT_INPUT_LENGTH` characters.

    Args:
        text: Raw citizen-supplied string (description, area_text, etc.).

    Returns:
        Sanitized string safe to embed in a prompt.
    """
    for pattern in _COMPILED_PATTERNS:
        text = pattern.sub("[removed]", text)
    return text[:_MAX_PROMPT_INPUT_LENGTH]


# ---------------------------------------------------------------------------
# Prompt templates — architecture Part B §LLM Prompt Construction
# ---------------------------------------------------------------------------

COMPLAINT_DESCRIPTION_PROMPT: str = (
    "You are a civic complaint assistant for Mangaluru, India.\n"
    "Given the following information, generate a clear complaint description.\n"
    "\n"
    "Category: {category}\n"
    "Location: {address}\n"
    "Evidence confidence: {confidence:.0%}\n"
    "Detected objects: {detected_objects}\n"
    "\n"
    "Generate a complaint description in 2-3 sentences.\n"
    "Do not invent information not present above.\n"
    'Return JSON: {{"description": "...", "category": "...", '
    '"authority_recommendation": "...", "confidence": 0.0}}'
)

RTI_DRAFT_PROMPT: str = (
    "You are drafting an RTI (Right to Information) application under the RTI Act 2005.\n"
    "\n"
    "Complaint details:\n"
    "- Category: {category}\n"
    "- Location: {address}\n"
    "- Submitted: {submitted_at}\n"
    "- Authority: {authority_name}\n"
    "- Reference: {mock_gov_ref}\n"
    "- Status: {status} (no resolution for {days_elapsed} days)\n"
    "\n"
    "Relevant RTI context:\n"
    "{rag_context}\n"
    "\n"
    "Draft a formal RTI application addressing:\n"
    "1. Information sought about complaint status\n"
    "2. Actions taken by authority\n"
    "3. Timeline of events\n"
    "\n"
    "Format as a formal letter. Max 500 words.\n"
    'Return JSON: {{"draft_text": "..."}}'
)

CATEGORY_CLASSIFICATION_PROMPT: str = (
    "You are a civic issue classifier for Mangaluru, India.\n"
    "Given the following image context, classify the civic issue category.\n"
    "\n"
    "Detected objects: {detected_objects}\n"
    "Location: {address}\n"
    "Additional context: {extra_context}\n"
    "\n"
    "Valid categories: pothole, waterlogging, broken_streetlight, garbage_overflow, "
    "open_drain, illegal_construction, water_supply, sewage, road_damage, other\n"
    "\n"
    "Pick the single most appropriate category.\n"
    "Do not invent new categories.\n"
    'Return JSON: {{"description": "...", "category": "...", '
    '"authority_recommendation": "...", "confidence": 0.0}}'
)
