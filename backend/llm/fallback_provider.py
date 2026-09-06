"""Deterministic LLM fallback — T2-9.

Implements a deterministic template engine that produces valid
:class:`~llm.output_validator.LLMOutput` instances without any external API
calls.  This is the fallback activated when the Groq primary provider is
unavailable, rate-limited, or returns an invalid schema.

Four use-case templates (architecture Part A §9):
    1. Complaint description generation
    2. RTI draft generation
    3. Ambiguous category classification
    4. Civic image classification fallback (when Groq vision unavailable)

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

    fallback_civic_classify_image(
        yolo_class: str,
        all_class_names: tuple,
        address: str,
    ) -> CivicClassificationResult

LOCKED decisions (Part A §9):
- No external API calls — purely deterministic.
- Output must satisfy the same Pydantic LLMOutput schema as Groq.
- Used automatically when Groq fails (T2-10 orchestrator decides).
"""
from __future__ import annotations

import logging
from typing import Optional

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
    # Only include the detected object name when the taxonomy produced a
    # meaningful civic category from it.  When category is "other" the YOLO
    # class (e.g. "frisbee") is a spurious COCO detection unrelated to the
    # actual civic issue — including it in the citizen-facing description is
    # confusing and misleading.
    _meaningful_category = category != "other"
    obj_suffix = (
        f" Detected objects in the image: {detected_objects}."
        if detected_objects and _meaningful_category
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
    """Classify civic category from detected objects and address (deterministic, no API).

    First applies keyword matching against the detected objects string.
    If no match is found (e.g. YOLO returned a low-confidence irrelevant class
    like "frisbee" for a pothole image), falls back to scanning the address
    string for civic-issue keywords.  This second pass significantly improves
    accuracy when YOLO cannot identify a known civic object but the address
    text contains descriptive context (e.g. "pothole near MG Road").

    Args:
        detected_objects: Comma-separated string of YOLO-detected class names.
        address:          Free-text location description (used in description
                          and as a secondary classification signal).

    Returns:
        A valid :class:`~llm.output_validator.LLMOutput` instance.
    """
    obj_lower = detected_objects.lower()
    addr_lower = address.lower()

    # Keyword → category mapping for detected objects (order matters; first match wins).
    _OBJ_KEYWORD_MAP: list[tuple[str, IssueCategory]] = [
        ("pothole",             IssueCategory.pothole),
        ("bottle",              IssueCategory.garbage_overflow),
        ("cup",                 IssueCategory.garbage_overflow),
        ("banana",              IssueCategory.garbage_overflow),
        ("food",                IssueCategory.garbage_overflow),
        ("trash",               IssueCategory.garbage_overflow),
        ("garbage",             IssueCategory.garbage_overflow),
        ("suitcase",            IssueCategory.garbage_overflow),
        ("toilet",              IssueCategory.sewage),
        ("sink",                IssueCategory.water_supply),
        ("boat",                IssueCategory.waterlogging),
        ("traffic light",       IssueCategory.broken_streetlight),
        ("fire hydrant",        IssueCategory.broken_streetlight),
        ("car",                 IssueCategory.road_damage),
        ("truck",               IssueCategory.road_damage),
        ("motorcycle",          IssueCategory.road_damage),
        ("bicycle",             IssueCategory.road_damage),
        ("bus",                 IssueCategory.road_damage),
        ("stop sign",           IssueCategory.road_damage),
    ]

    # Address-context keyword → category mapping.
    # Used as a fallback when YOLO detects nothing useful (e.g. low-confidence
    # generic class like "frisbee" returned for a pothole image).
    # The address the citizen typed often contains the issue description.
    _ADDR_KEYWORD_MAP: list[tuple[str, IssueCategory]] = [
        ("pothole",             IssueCategory.pothole),
        ("pot hole",            IssueCategory.pothole),
        ("waterlog",            IssueCategory.waterlogging),
        ("flood",               IssueCategory.waterlogging),
        ("drain",               IssueCategory.open_drain),
        ("sewage",              IssueCategory.sewage),
        ("sewer",               IssueCategory.sewage),
        ("streetlight",         IssueCategory.broken_streetlight),
        ("street light",        IssueCategory.broken_streetlight),
        ("lamp",                IssueCategory.broken_streetlight),
        ("garbage",             IssueCategory.garbage_overflow),
        ("waste",               IssueCategory.garbage_overflow),
        ("litter",              IssueCategory.garbage_overflow),
        ("water supply",        IssueCategory.water_supply),
        ("water pipe",          IssueCategory.water_supply),
        ("road damage",         IssueCategory.road_damage),
        ("road",                IssueCategory.road_damage),
        ("construction",        IssueCategory.illegal_construction),
        ("encroachment",        IssueCategory.illegal_construction),
    ]

    matched_category = IssueCategory.other
    match_source = "none"

    # Pass 1: match against detected objects.
    for keyword, cat in _OBJ_KEYWORD_MAP:
        if keyword in obj_lower:
            matched_category = cat
            match_source = "objects"
            break

    # Pass 2: if no object match, scan the address for civic keywords.
    if matched_category is IssueCategory.other:
        for keyword, cat in _ADDR_KEYWORD_MAP:
            if keyword in addr_lower:
                matched_category = cat
                match_source = "address"
                break

    cat_value = matched_category.value
    description = (
        f"Based on detected objects ({detected_objects or 'none'}) "
        f"at {address}, this appears to be a {_label(cat_value)} issue."
    )[:500]

    logger.debug(
        "fallback_classify_category: objects=%r address=%r → category=%s (source=%s)",
        detected_objects, address, cat_value, match_source,
    )
    return LLMOutput(
        category=matched_category,
        description=description,
        authority_recommendation=_authority(cat_value),
        confidence=0.5,
    )


# ---------------------------------------------------------------------------
# Template: civic image classification fallback (use case 4)
# ---------------------------------------------------------------------------

# Vision-model category strings → IssueCategory mapping.
# Maps the extended civic vocabulary from the vision prompt to the canonical
# IssueCategory enum.  This is used when Groq vision is unavailable and
# the heuristic fallback must guess from YOLO + address context.
_VISION_CATEGORY_MAP: dict[str, IssueCategory] = {
    "pothole":            IssueCategory.pothole,
    "road_damage":        IssueCategory.road_damage,
    "broken_road_marking": IssueCategory.road_damage,  # closest existing enum
    "waterlogging":       IssueCategory.waterlogging,
    "drainage":           IssueCategory.open_drain,
    "sewage":             IssueCategory.sewage,
    "water_leakage":      IssueCategory.water_supply,
    "garbage":            IssueCategory.garbage_overflow,
    "streetlight":        IssueCategory.broken_streetlight,
    "electrical":         IssueCategory.broken_streetlight,
    "other_civic":        IssueCategory.other,
    "invalid":            IssueCategory.other,
}


def map_vision_category_to_issue_category(vision_cat: str) -> IssueCategory:
    """Map a vision-model civic category string to a canonical IssueCategory.

    The vision prompt uses an extended vocabulary (e.g. 'pothole', 'drainage',
    'water_leakage', 'garbage', 'streetlight') which is a superset of the
    existing IssueCategory enum values.  This function maps both exact matches
    and the extended terms to the closest IssueCategory.

    Args:
        vision_cat: Category string from the vision model or fallback.

    Returns:
        Matching :class:`~schemas.report.IssueCategory`.
    """
    key = vision_cat.strip().lower()
    # Try exact IssueCategory enum match first
    try:
        return IssueCategory(key)
    except ValueError:
        pass
    # Fall back to explicit extended vocabulary mapping
    return _VISION_CATEGORY_MAP.get(key, IssueCategory.other)


def fallback_civic_classify_image(
    yolo_class: str,
    all_class_names: tuple,
    address: str,
) -> "CivicClassificationResult":
    """Heuristic civic image classification fallback (no API, no vision model).

    Used when Groq vision is unavailable.  Applies the same keyword-matching
    logic as fallback_classify_category but returns a CivicClassificationResult
    instead of LLMOutput.

    The heuristic logic:
    1. Check all YOLO class names for known civic-context objects.
    2. Fall back to address keyword matching.
    3. If neither matches, return category='other_civic', valid=True, low confidence.
       (We assume the image passed YOLO-based validation already, so it is
       likely civic unless YOLO specifically flagged a person-dominant scene.)

    Args:
        yolo_class:      Top-1 YOLO class name.
        all_class_names: All YOLO-detected class names (tuple).
        address:         Free-text address/location string.

    Returns:
        :class:`CivicClassificationResult`.
    """
    # Deferred import to avoid circular dependency
    from llm.groq_provider import CivicClassificationResult

    obj_str = " ".join(str(n).lower() for n in all_class_names) + " " + yolo_class.lower()
    addr_lower = address.lower()

    # Pass 1: check YOLO classes for civic context objects
    _OBJ_KEYWORD_MAP: list[tuple[str, str, str, float]] = [
        # (keyword, vision_cat, severity, severity_score)
        ("car",          "road_damage",  "medium", 0.5),
        ("truck",        "road_damage",  "medium", 0.5),
        ("motorcycle",   "road_damage",  "medium", 0.5),
        ("bicycle",      "road_damage",  "low",    0.3),
        ("bus",          "road_damage",  "medium", 0.5),
        ("stop sign",    "road_damage",  "low",    0.3),
        ("traffic light","streetlight",  "medium", 0.5),
        ("fire hydrant", "streetlight",  "medium", 0.5),
        ("toilet",       "sewage",       "high",   0.85),
        ("sink",         "water_leakage","medium", 0.5),
        ("boat",         "waterlogging", "high",   0.85),
        ("bottle",       "garbage",      "medium", 0.5),
        ("cup",          "garbage",      "medium", 0.5),
        ("bowl",         "garbage",      "medium", 0.5),
    ]

    matched_cat = None
    matched_severity = "low"
    matched_sev_score = 0.3

    for keyword, vision_cat, sev, sev_score in _OBJ_KEYWORD_MAP:
        if keyword in obj_str:
            matched_cat = vision_cat
            matched_severity = sev
            matched_sev_score = sev_score
            break

    # Pass 2: address keyword matching
    if matched_cat is None:
        _ADDR_KEYWORD_MAP: list[tuple[str, str, str, float]] = [
            ("pothole",     "pothole",      "medium", 0.5),
            ("pot hole",    "pothole",      "medium", 0.5),
            ("waterlog",    "waterlogging", "high",   0.85),
            ("flood",       "waterlogging", "high",   0.85),
            ("drain",       "drainage",     "medium", 0.5),
            ("sewage",      "sewage",       "high",   0.85),
            ("sewer",       "sewage",       "high",   0.85),
            ("streetlight", "streetlight",  "medium", 0.5),
            ("street light","streetlight",  "medium", 0.5),
            ("garbage",     "garbage",      "medium", 0.5),
            ("waste",       "garbage",      "medium", 0.5),
            ("litter",      "garbage",      "low",    0.3),
            ("water pipe",  "water_leakage","medium", 0.5),
            ("water supply","water_leakage","medium", 0.5),
            ("road damage", "road_damage",  "medium", 0.5),
            ("road",        "road_damage",  "low",    0.3),
        ]
        for keyword, vision_cat, sev, sev_score in _ADDR_KEYWORD_MAP:
            if keyword in addr_lower:
                matched_cat = vision_cat
                matched_severity = sev
                matched_sev_score = sev_score
                break

    if matched_cat is None:
        # No recognizable civic context — mark as other_civic with low confidence
        # (the image already passed the YOLO relevance gate so it is likely civic)
        matched_cat = "other_civic"
        matched_severity = "low"
        matched_sev_score = 0.2

    description = (
        f"A potential {_label(map_vision_category_to_issue_category(matched_cat).value)} "
        f"issue has been reported at {address}. "
        "Please inspect and take appropriate action."
    )[:500]

    logger.debug(
        "fallback_civic_classify_image: yolo=%r address=%r → category=%s",
        yolo_class, address, matched_cat,
    )
    return CivicClassificationResult(
        valid=True,
        category=matched_cat,
        category_confidence=0.45,  # heuristic fallback — moderate confidence
        severity=matched_severity,
        severity_score=matched_sev_score,
        description=description,
        reason="heuristic_fallback",
    )
