"""Deterministic LLM fallback — T2-9.

Implements a deterministic template engine that produces valid
:class:`~llm.output_validator.LLMOutput` instances without any external API
calls.  This is the fallback activated when the Groq primary provider is
unavailable, rate-limited, or returns an invalid schema.

Three use-case templates (architecture Part A §9):
    1. Complaint description generation
    2. RTI draft generation  
    3. Ambiguous category classification

Public API:

    fallback_complaint_description(
        category: str,
        address: str,
        confidence: float,
        detected_objects: str = "",
    ) -> LLMOutput

    fallback_rti_draft(
        category: str,
        address: str,
        submitted_at: str,
        authority_name: str,
        mock_gov_ref: str,
        status: str,
        days_elapsed: int,
    ) -> LLMOutput

    fallback_classify_category(
        detected_objects: str,
        address: str,
    ) -> LLMOutput

LOCKED decisions (Part A §9):
- No external API calls — purely deterministic.
- Output must satisfy the same Pydantic LLMOutput schema as Groq.
- Used automatically when Groq fails (T2-10 orchestrator decides).
"""
from __future__ import annotations

import logging

from llm.output_validator import LLMOutput
from schemas.report import IssueCategory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Human-readable category labels used in template text
# ---------------------------------------------------------------------------

_CATEGORY_LABELS: dict[str, str] = {
    "pothole": "pothole",
    "waterlogging": "waterlogging / flooding",
    "broken_streetlight": "broken streetlight",
    "garbage_overflow": "garbage overflow",
    "open_drain": "open drain",
    "illegal_construction": "illegal construction",
    "water_supply": "water supply issue",
    "sewage": "sewage problem",
    "road_damage": "road damage",
    "other": "civic issue",
}

# ---------------------------------------------------------------------------
# Authority name templates — one default per category
# (These are the authority short names from mangaluru_authorities.json)
# ---------------------------------------------------------------------------

_DEFAULT_AUTHORITY: dict[str, str] = {
    "pothole": "MCC",
    "waterlogging": "MCC Drainage",
    "broken_streetlight": "MESCOM",
    "garbage_overflow": "MCC",
    "open_drain": "MCC Drainage",
    "illegal_construction": "MUDA",
    "water_supply": "MWWD",
    "sewage": "MCC Drainage",
    "road_damage": "MCC",
    "other": "MCC",
}


def _label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


def _authority(category: str) -> str:
    return _DEFAULT_AUTHORITY.get(category, "MCC")


# ---------------------------------------------------------------------------
# Template: complaint description (use case 1)
# ---------------------------------------------------------------------------

def fallback_complaint_description(
    category: str,
    address: str,
    confidence: float,
    detected_objects: str = "",
) -> LLMOutput:
    """Generate a deterministic complaint description (no external API).

    Args:
        category:         Civic issue category string (e.g. ``"pothole"``).
        address:          Free-text location description.
        confidence:       Evidence confidence in [0.0, 1.0].
        detected_objects: Comma-separated string of YOLO-detected objects.

    Returns:
        A valid :class:`~llm.output_validator.LLMOutput` instance.
    """
    cat_label = _label(category)
    obj_suffix = (
        f" Detected objects in the image: {detected_objects}."
        if detected_objects
        else ""
    )
    # Build description (max 500 chars — kept well under that by template).
    description = (
        f"A {cat_label} has been reported at {address}. "
        f"The evidence confidence level is {confidence:.0%}.{obj_suffix} "
        f"Please inspect and take appropriate action as soon as possible."
    )[:500]

    authority = _authority(category)
    try:
        cat_enum = IssueCategory(category)
    except ValueError:
        cat_enum = IssueCategory.other
        authority = _authority("other")

    logger.debug(
        "fallback_complaint_description: category=%s address=%s conf=%.2f",
        category, address, confidence,
    )
    return LLMOutput(
        category=cat_enum,
        description=description,
        authority_recommendation=authority,
        confidence=min(max(float(confidence), 0.0), 1.0),
    )


# ---------------------------------------------------------------------------
# Template: RTI draft (use case 2)
# ---------------------------------------------------------------------------

def fallback_rti_draft(
    category: str,
    address: str,
    submitted_at: str,
    authority_name: str,
    mock_gov_ref: str,
    status: str,
    days_elapsed: int,
) -> LLMOutput:
    """Generate a deterministic RTI draft letter (no external API).

    The RTI draft is stored in ``description``.
    ``category``, ``authority_recommendation``, and ``confidence`` are set to
    meaningful values so the output satisfies the LLMOutput schema.

    Returns:
        A valid :class:`~llm.output_validator.LLMOutput` instance.
    """
    cat_label = _label(category)
    draft = (
        f"To,\n"
        f"The Public Information Officer,\n"
        f"{authority_name},\n"
        f"Mangaluru, Karnataka.\n\n"
        f"Subject: RTI Application regarding civic complaint (Ref: {mock_gov_ref})\n\n"
        f"I hereby request, under Section 6 of the Right to Information Act 2005, "
        f"the following information regarding my civic complaint:\n\n"
        f"Complaint Reference: {mock_gov_ref}\n"
        f"Issue Type: {cat_label}\n"
        f"Location: {address}\n"
        f"Submitted On: {submitted_at}\n"
        f"Current Status: {status}\n"
        f"Days Elapsed Without Resolution: {days_elapsed}\n\n"
        f"Information Sought:\n"
        f"1. Current status of the complaint and actions taken.\n"
        f"2. Name and designation of the officer responsible.\n"
        f"3. Timeline of inspections and repair work (if any).\n"
        f"4. Reason for delay if unresolved after {days_elapsed} days.\n\n"
        f"I request a response within 30 days as mandated by the RTI Act 2005.\n\n"
        f"Yours sincerely,\n[Applicant Name]\n[Contact Details]"
    )[:500]

    try:
        cat_enum = IssueCategory(category)
    except ValueError:
        cat_enum = IssueCategory.other

    logger.debug(
        "fallback_rti_draft: category=%s authority=%s days=%d",
        category, authority_name, days_elapsed,
    )
    return LLMOutput(
        category=cat_enum,
        description=draft,
        authority_recommendation=authority_name or _authority(category),
        confidence=0.7,
    )


# ---------------------------------------------------------------------------
# Template: category classification (use case 3)
# ---------------------------------------------------------------------------

def fallback_classify_category(
    detected_objects: str,
    address: str,
) -> LLMOutput:
    """Classify civic category from detected objects (deterministic, no API).

    Applies simple keyword matching against the detected objects string to
    select the most likely IssueCategory.  Falls back to ``other`` when no
    match is found.

    Args:
        detected_objects: Comma-separated string of YOLO-detected class names.
        address:          Free-text location description (used in description).

    Returns:
        A valid :class:`~llm.output_validator.LLMOutput` instance.
    """
    obj_lower = detected_objects.lower()

    # Keyword → category mapping (order matters; first match wins).
    _KEYWORD_MAP: list[tuple[str, IssueCategory]] = [
        ("pothole",             IssueCategory.pothole),
        ("bottle",              IssueCategory.garbage_overflow),
        ("cup",                 IssueCategory.garbage_overflow),
        ("banana",              IssueCategory.garbage_overflow),
        ("food",                IssueCategory.garbage_overflow),
        ("trash",               IssueCategory.garbage_overflow),
        ("garbage",             IssueCategory.garbage_overflow),
        ("backpack",            IssueCategory.garbage_overflow),
        ("suitcase",            IssueCategory.garbage_overflow),
        ("toilet",              IssueCategory.sewage),
        ("sink",                IssueCategory.water_supply),
        ("boat",                IssueCategory.waterlogging),
        ("umbrella",            IssueCategory.waterlogging),
        ("traffic light",       IssueCategory.broken_streetlight),
        ("fire hydrant",        IssueCategory.broken_streetlight),
        ("car",                 IssueCategory.road_damage),
        ("truck",               IssueCategory.road_damage),
        ("motorcycle",          IssueCategory.road_damage),
        ("bicycle",             IssueCategory.road_damage),
        ("bus",                 IssueCategory.road_damage),
        ("stop sign",           IssueCategory.road_damage),
    ]

    matched_category = IssueCategory.other
    for keyword, cat in _KEYWORD_MAP:
        if keyword in obj_lower:
            matched_category = cat
            break

    cat_value = matched_category.value
    description = (
        f"Based on detected objects ({detected_objects or 'none'}) "
        f"at {address}, this appears to be a {_label(cat_value)} issue."
    )[:500]

    logger.debug(
        "fallback_classify_category: objects=%r → category=%s",
        detected_objects, cat_value,
    )
    return LLMOutput(
        category=matched_category,
        description=description,
        authority_recommendation=_authority(cat_value),
        confidence=0.5,
    )
