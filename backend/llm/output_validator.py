"""LLM output schema validation — T2-8.

Defines the :class:`LLMOutput` Pydantic model that every LLM response must
conform to, and the :func:`validate_output` helper that converts a raw
``dict`` to a validated :class:`LLMOutput` instance.

Public API:

    class LLMOutput(BaseModel)
        category: IssueCategory
        description: str  (max 500 chars)
        authority_recommendation: str
        confidence: float  (0.0–1.0)

    class LLMOutputInvalid(Exception)
        Raised when the raw LLM response fails Pydantic validation.

    def validate_output(raw: dict) -> LLMOutput
        Convert raw dict → LLMOutput; raise LLMOutputInvalid on failure.

LOCKED decisions (Part A §9):
- Output schema is fixed: {category, description, authority_recommendation, confidence}.
- description max_length = 500.
- confidence range [0.0, 1.0].
- category must be a member of IssueCategory (no arbitrary model-created strings).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class LLMOutputInvalid(Exception):
    """Raised when the raw LLM response does not conform to :class:`LLMOutput`.

    Callers should catch this and fall back to the deterministic template
    engine (T2-9) rather than surfacing the error to the citizen.
    """


# ---------------------------------------------------------------------------
# Output schema — architecture Part A §9 / Part B §LLM Output Validation
# ---------------------------------------------------------------------------

class LLMOutput(BaseModel):
    """Validated LLM response for CivicAI complaint and RTI workflows.

    Fields:
        category:                 Civic issue category (must be a valid
                                  :class:`~schemas.report.IssueCategory`).
        description:              Human-readable complaint description.
                                  Maximum 500 characters.
        authority_recommendation: Name of the recommended Mangaluru authority.
        confidence:               Model confidence in the classification,
                                  in the range [0.0, 1.0].
    """

    category: IssueCategory
    description: str = Field(max_length=500)
    authority_recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Validator helper
# ---------------------------------------------------------------------------

def validate_output(raw: dict) -> LLMOutput:
    """Validate a raw LLM response dict against :class:`LLMOutput`.

    Args:
        raw: A ``dict`` parsed from the LLM's JSON response.

    Returns:
        A fully validated :class:`LLMOutput` instance.

    Raises:
        :class:`LLMOutputInvalid`: When *raw* fails Pydantic validation
            (missing field, wrong type, out-of-range value, unknown category,
            description too long, etc.).  Callers must catch this and
            activate the deterministic fallback (T2-9).
    """
    try:
        return LLMOutput(**raw)
    except (ValidationError, TypeError) as exc:
        raise LLMOutputInvalid(
            f"LLM response failed schema validation: {exc}"
        ) from exc
