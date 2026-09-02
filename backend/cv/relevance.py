"""Civic-relevance gate — rejects personal/portrait images as non-civic evidence.

Public API:

    check_civic_relevance(detection: DetectionResult) -> None

Raises ImageValidationError when the image is determined to be a personal or
portrait photograph with no meaningful civic-issue content.

Design rationale
----------------
The gate uses the full set of YOLO-detected COCO class names from the
``DetectionResult.all_class_names`` field, rather than only the top-1 class.
This lets it distinguish two very different situations:

  1. "person"-dominated image (selfie / portrait / personal photo):
     YOLO detects only person(s) — no civic-infrastructure objects anywhere.
     → REJECTED as personal/portrait photo.

  2. Civic scene containing people:
     YOLO detects person(s) PLUS at least one civic-context object such as a
     car, truck, traffic light, road surface indicator, or any class that maps
     to a non-"other" IssueCategory in the taxonomy.
     → ACCEPTED — the civic evidence is present; the person is incidental.

The gate does NOT reject simply because YOLO sees a "person" class. It only
rejects when persons are the only meaningful detected objects.

Thresholds
----------
- PERSON_DOMINANCE_THRESHOLD (0.40): minimum person-detection confidence
  required before the gate considers "person" as a significant subject.
  Below this threshold a faint person detection is not treated as dominant.
- At least one CIVIC_INDICATOR class must appear in all_class_names at any
  confidence for the image to be considered civic evidence.

CIVIC_INDICATOR classes are COCO-80 classes that appear in the taxonomy
mapping or otherwise indicate a road/infrastructure/public-space context.
They are defined explicitly so the gate is deterministic and transparent.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cv.image_validator import ImageValidationError

if TYPE_CHECKING:
    from cv.detection import DetectionResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum person-detection confidence before treating person as dominant.
# Lowered to 0.20 so that typical portrait/selfie YOLO detections (which
# often score 0.25–0.35 for a frontal face) are correctly rejected when no
# civic-infrastructure objects are present alongside the person.
# A value of 0.20 still lets genuinely noisy / near-zero confidence hits
# (e.g. 0.10–0.15) pass through without triggering rejection.
# ---------------------------------------------------------------------------
PERSON_DOMINANCE_THRESHOLD: float = 0.20

# ---------------------------------------------------------------------------
# COCO-80 class names that indicate a civic / public-infrastructure context.
# An image containing ANY of these (at any confidence) alongside a person is
# treated as a valid civic scene.
#
# NARROWED to only classes that are reliably associated with outdoor public
# infrastructure.  Classes that commonly appear in selfies, indoor photos, or
# personal settings have been REMOVED:
#
#   REMOVED: backpack, handbag, suitcase  — carried items, appear in selfies
#   REMOVED: umbrella                      — handheld; person context not civic
#   REMOVED: chair, couch, potted plant   — indoor furniture
#   REMOVED: clock                         — indoor/personal
#   REMOVED: bird, dog, cat               — pet context in portraits
#   REMOVED: horse, cow, sheep            — may appear in personal rural photos
#   REMOVED: sports ball, kite            — personal outdoor recreation
#   REMOVED: bench                         — can appear next to a person/selfie
#
# Only classes that strongly indicate a road/public-infrastructure context
# (e.g. vehicles, traffic infrastructure, plumbing, watercraft) remain.
# ---------------------------------------------------------------------------
_CIVIC_INDICATOR_CLASSES: frozenset[str] = frozenset({
    # Road-context (from taxonomy road_damage mapping) — strong outdoor public signals
    "car", "truck", "motorcycle", "bicycle", "bus",
    "traffic light", "stop sign", "parking meter",
    # Fixed urban infrastructure (not portable, not personal)
    "fire hydrant",
    # Litter / waste COCO classes — food/drink items that signal garbage overflow
    # (Only items that are unlikely to appear as deliberate food in a selfie/indoor photo)
    "bottle", "cup", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake",
    # Note: wine glass, fork, knife, spoon are too common indoors/at restaurants
    # Water / plumbing fixtures — fixed infrastructure, not handheld
    "sink", "toilet",
    # Waterlogging — boat strongly indicates flooding in a public context
    "boat",
    # Large public transport — unambiguous outdoor/infrastructure context
    "train", "airplane",
})

# Person-related COCO classes that identify a personal/portrait subject.
_PERSON_CLASSES: frozenset[str] = frozenset({"person"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_REJECTION_MESSAGE = (
    "This image does not appear to show a civic issue. "
    "Please upload a photo of a road, pothole, garbage, drainage, streetlight, "
    "water issue, public infrastructure problem, or similar civic matter."
)


def check_civic_relevance(detection: "DetectionResult") -> None:
    """Raise ImageValidationError if the image is a personal/portrait photo.

    Args:
        detection: The :class:`~cv.detection.DetectionResult` from
                   ``detect_civic_issue()``.  Must have ``all_class_names``
                   populated (added in the T-relevance update to DetectionResult).

    Raises:
        :class:`~cv.image_validator.ImageValidationError`:
            When the image is dominated by person detections and contains no
            civic-infrastructure objects — i.e. it is a selfie, portrait, or
            personal photograph unrelated to a civic issue.

    Notes:
        - Does NOT raise when persons appear alongside civic objects.
        - Does NOT raise when no persons are detected at all.
        - The gate fires when EITHER:
            (A) The top-1 detection is a person above the confidence threshold
                AND no civic indicators are anywhere in all_class_names, OR
            (B) A person appears ANYWHERE in all_class_names (any confidence)
                AND the top-1 class is not a civic indicator AND no civic
                indicator appears anywhere in all_class_names.
          Case B catches selfies where a non-person item (e.g. 'tie', 'cell
          phone') is the highest-confidence detection but a person is also
          detected — the image is still person-dominated with no civic content.
    """
    all_names_lower = [n.lower().strip() for n in detection.all_class_names]

    # If no detections at all, pass through — nothing to reject here.
    if not all_names_lower:
        logger.debug("relevance: no detections — passing through.")
        return

    # Check if there is any civic-indicator class anywhere in the detections.
    has_civic_indicator = any(n in _CIVIC_INDICATOR_CLASSES for n in all_names_lower)

    if has_civic_indicator:
        # At least one civic object present — the image is valid civic evidence
        # regardless of whether a person is also detected.
        logger.debug("relevance: civic indicator(s) present — image accepted.")
        return

    # No civic indicator found.
    # Check (A): top-1 is person above confidence threshold.
    top_class = detection.yolo_class.lower().strip()
    if top_class in _PERSON_CLASSES and detection.confidence >= PERSON_DOMINANCE_THRESHOLD:
        logger.info(
            "relevance: image rejected (A) — person top-1 (top=%s conf=%.2f), "
            "no civic indicators detected.",
            detection.yolo_class,
            detection.confidence,
        )
        raise ImageValidationError(_REJECTION_MESSAGE)

    # Check (B): person appears anywhere in all detections, AND top-1 is not a
    # civic indicator.  This catches selfies where a secondary item (tie, phone,
    # handbag, etc.) is the highest-confidence hit but a person is still visible.
    # We only apply this check when confidence is meaningful (>= threshold) to
    # avoid rejecting noisy detections.
    has_person_anywhere = any(n in _PERSON_CLASSES for n in all_names_lower)
    if has_person_anywhere and detection.confidence >= PERSON_DOMINANCE_THRESHOLD:
        logger.info(
            "relevance: image rejected (B) — person in detections (top=%s conf=%.2f), "
            "no civic indicators detected.",
            detection.yolo_class,
            detection.confidence,
        )
        raise ImageValidationError(_REJECTION_MESSAGE)

    # Top class is not person, or confidence is too low — pass through.
    logger.debug(
        "relevance: top='%s' conf=%.2f, no civic indicators — "
        "passing through (low confidence or non-person top class).",
        detection.yolo_class,
        detection.confidence,
    )
