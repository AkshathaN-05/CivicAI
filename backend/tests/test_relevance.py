"""Tests for the civic-relevance gate — cv/relevance.py.

Acceptance criteria:
  1. A selfie/portrait-style image (person-dominant, no civic objects) is rejected.
  2. A person-only image never becomes a low-confidence normal civic report.
  3. A valid pothole/road image (no person) remains valid.
  4. A road image with pedestrians (person + road objects) remains valid.
  5. A civic-issue image containing a person remains valid.
  6. An invalid-image result contains a clear rejection reason.
  7. Existing valid AI categories and confidence behaviour are unchanged.
  8. No detections at all → passes through (not rejected).
  9. Person detected below threshold → passes through.
 10. Non-person top class with no civic indicators → passes through
     (graceful: we only reject definitively person-dominant images).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from cv.detection import DetectionResult
from cv.image_validator import ImageValidationError
from cv.relevance import (
    PERSON_DOMINANCE_THRESHOLD,
    check_civic_relevance,
)
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Helpers — build DetectionResult with controlled all_class_names
# ---------------------------------------------------------------------------


def _result(
    yolo_class: str,
    confidence: float,
    all_class_names: tuple = (),
    category: IssueCategory = IssueCategory.other,
) -> DetectionResult:
    return DetectionResult(
        yolo_class=yolo_class,
        confidence=confidence,
        category=category,
        all_class_names=all_class_names,
    )


# ---------------------------------------------------------------------------
# Tests: selfie / portrait rejection
# ---------------------------------------------------------------------------


def test_selfie_rejected():
    """A person-dominant image with no civic objects is rejected."""
    det = _result("person", confidence=0.85, all_class_names=("person",))
    with pytest.raises(ImageValidationError, match="civic issue"):
        check_civic_relevance(det)


def test_portrait_multiple_persons_rejected():
    """Multiple person detections and nothing else → rejected."""
    det = _result("person", confidence=0.90, all_class_names=("person", "person", "person"))
    with pytest.raises(ImageValidationError, match="civic issue"):
        check_civic_relevance(det)


def test_selfie_rejection_message_is_clear():
    """Rejection error message must be a clear, human-readable reason."""
    det = _result("person", confidence=0.75, all_class_names=("person",))
    with pytest.raises(ImageValidationError) as exc_info:
        check_civic_relevance(det)
    message = str(exc_info.value)
    # Must contain actionable guidance
    assert "civic issue" in message.lower() or "portrait" in message.lower()
    assert len(message) > 20


def test_selfie_is_not_accepted_as_low_confidence_civic():
    """A selfie must NOT silently become a low-confidence civic report."""
    det = _result("person", confidence=0.60, all_class_names=("person",))
    with pytest.raises(ImageValidationError):
        check_civic_relevance(det)


# ---------------------------------------------------------------------------
# Tests: valid civic scenes containing people → must NOT be rejected
# ---------------------------------------------------------------------------


def test_road_with_pedestrian_accepted():
    """Pothole/road scene: person + car detected → valid civic evidence."""
    det = _result(
        "car", confidence=0.80,
        all_class_names=("car", "person"),
        category=IssueCategory.road_damage,
    )
    # Must not raise
    check_civic_relevance(det)


def test_civic_issue_with_bystander_accepted():
    """Garbage pile: bottle + person detected → valid civic evidence."""
    det = _result(
        "bottle", confidence=0.70,
        all_class_names=("bottle", "person", "person"),
        category=IssueCategory.garbage_overflow,
    )
    check_civic_relevance(det)


def test_road_scene_with_multiple_people_accepted():
    """Road scene with multiple people and vehicles → valid."""
    det = _result(
        "truck", confidence=0.85,
        all_class_names=("truck", "person", "person", "car"),
        category=IssueCategory.road_damage,
    )
    check_civic_relevance(det)


def test_traffic_light_scene_with_person_accepted():
    """Traffic light (streetlight) + person → valid civic scene."""
    det = _result(
        "traffic light", confidence=0.72,
        all_class_names=("traffic light", "person"),
        category=IssueCategory.road_damage,
    )
    check_civic_relevance(det)


def test_waterlogging_boat_with_person_accepted():
    """Waterlogging scene: boat + person → valid."""
    det = _result(
        "boat", confidence=0.65,
        all_class_names=("boat", "person"),
        category=IssueCategory.waterlogging,
    )
    check_civic_relevance(det)


# ---------------------------------------------------------------------------
# Tests: civic images with NO person → must pass through
# ---------------------------------------------------------------------------


def test_pothole_road_no_person_accepted():
    """Pure road damage scene (car, truck) with no person → accepted."""
    det = _result(
        "car", confidence=0.80,
        all_class_names=("car", "truck"),
        category=IssueCategory.road_damage,
    )
    check_civic_relevance(det)


def test_garbage_image_no_person_accepted():
    """Garbage overflow scene → accepted."""
    det = _result(
        "bottle", confidence=0.75,
        all_class_names=("bottle", "cup"),
        category=IssueCategory.garbage_overflow,
    )
    check_civic_relevance(det)


def test_no_detections_passes_through():
    """Empty detection (no objects at all) passes the gate without error."""
    det = _result("", confidence=0.0, all_class_names=())
    check_civic_relevance(det)  # must not raise


# ---------------------------------------------------------------------------
# Tests: person below confidence threshold → not treated as dominant
# ---------------------------------------------------------------------------


def test_person_below_threshold_passes_through():
    """Person detected at very low confidence (faint hit) → not rejected."""
    det = _result(
        "person",
        confidence=PERSON_DOMINANCE_THRESHOLD - 0.01,
        all_class_names=("person",),
    )
    check_civic_relevance(det)  # must not raise


def test_person_exactly_at_threshold_rejected():
    """Person at exactly the threshold IS rejected (boundary: >= threshold)."""
    det = _result(
        "person",
        confidence=PERSON_DOMINANCE_THRESHOLD,
        all_class_names=("person",),
    )
    with pytest.raises(ImageValidationError):
        check_civic_relevance(det)


# ---------------------------------------------------------------------------
# Tests: non-person top class with no civic indicators
# ---------------------------------------------------------------------------


def test_non_person_no_civic_no_person_anywhere_passes_through():
    """Top class is not person and no civic indicator AND no person detected — pass through.

    This is the case where YOLO detects something unusual that is not in
    the civic taxonomy and no person is present (e.g. 'kite' alone).
    We do not reject because we cannot be sure it is a selfie.
    """
    det = _result(
        "kite", confidence=0.55,
        all_class_names=("kite",),
    )
    check_civic_relevance(det)  # must not raise


def test_non_person_top_but_person_in_all_classes_rejected():
    """Bug B regression: top-1 is 'tie' (selfie with tie visible) but person
    is in all_class_names at meaningful confidence — must be rejected.

    Previously this passed through because top_class != 'person'.
    """
    # Selfie with a tie visible: YOLO top-1 = 'tie' at 0.42, but person also detected
    det = _result(
        "tie", confidence=0.42,
        all_class_names=("tie", "person"),
    )
    with pytest.raises(ImageValidationError, match="civic issue"):
        check_civic_relevance(det)


def test_non_person_top_person_in_all_below_threshold_passes():
    """Person in all_class_names but top confidence is below threshold — pass through.

    Low-confidence detections should not cause rejection.
    """
    det = _result(
        "tie", confidence=PERSON_DOMINANCE_THRESHOLD - 0.01,
        all_class_names=("tie", "person"),
    )
    check_civic_relevance(det)  # must not raise


def test_selfie_with_handbag_now_rejected():
    """Bug A regression: handbag was previously in _CIVIC_INDICATOR_CLASSES,
    causing a selfie with a visible handbag to pass as 'civic garbage evidence'.
    After the fix, handbag is NOT a civic indicator, so the person dominance
    check applies and the image is correctly rejected.
    """
    from cv.relevance import _CIVIC_INDICATOR_CLASSES
    assert "handbag" not in _CIVIC_INDICATOR_CLASSES, (
        "handbag must NOT be in _CIVIC_INDICATOR_CLASSES — it appears in selfies "
        "and causes false civic acceptance."
    )
    # A selfie with a person + visible handbag: top-1 is person, no civic indicators
    det = _result(
        "person", confidence=0.78,
        all_class_names=("person", "handbag"),
    )
    with pytest.raises(ImageValidationError):
        check_civic_relevance(det)


def test_selfie_with_backpack_now_rejected():
    """Bug A regression: backpack was previously in _CIVIC_INDICATOR_CLASSES."""
    from cv.relevance import _CIVIC_INDICATOR_CLASSES
    assert "backpack" not in _CIVIC_INDICATOR_CLASSES
    det = _result(
        "person", confidence=0.72,
        all_class_names=("person", "backpack"),
    )
    with pytest.raises(ImageValidationError):
        check_civic_relevance(det)


def test_civic_classes_are_reliably_outdoor():
    """Spot-check that key personal/indoor items are NOT civic indicators."""
    from cv.relevance import _CIVIC_INDICATOR_CLASSES
    disallowed = {"handbag", "backpack", "suitcase", "umbrella", "chair",
                  "couch", "bird", "dog", "cat", "sports ball", "kite",
                  "bench", "clock", "potted plant", "horse", "cow", "sheep"}
    overlap = disallowed & _CIVIC_INDICATOR_CLASSES
    assert not overlap, (
        f"These personal/indoor items should NOT be in _CIVIC_INDICATOR_CLASSES: {overlap}"
    )


def test_civic_classes_contain_vehicles():
    """Key road-context classes must remain in _CIVIC_INDICATOR_CLASSES."""
    from cv.relevance import _CIVIC_INDICATOR_CLASSES
    required = {"car", "truck", "motorcycle", "bus", "bicycle",
                "traffic light", "stop sign", "fire hydrant",
                "sink", "toilet", "boat", "train"}
    missing = required - _CIVIC_INDICATOR_CLASSES
    assert not missing, f"Required civic indicators missing: {missing}"


def test_rejection_message_is_clear_and_actionable():
    """Rejection message must be user-friendly and mention civic issue types."""
    from cv.relevance import _REJECTION_MESSAGE
    msg_lower = _REJECTION_MESSAGE.lower()
    assert "civic issue" in msg_lower or "civic" in msg_lower
    # Must mention some concrete civic issue types
    civic_terms = ["road", "pothole", "garbage", "drainage", "streetlight",
                   "water", "infrastructure"]
    matched = [t for t in civic_terms if t in msg_lower]
    assert len(matched) >= 3, (
        f"Rejection message should mention at least 3 civic issue types. "
        f"Found: {matched}"
    )


# ---------------------------------------------------------------------------
# Tests: ImageValidationError is the correct exception type
# ---------------------------------------------------------------------------


def test_rejection_is_image_validation_error():
    """check_civic_relevance raises ImageValidationError (not a plain Exception)."""
    det = _result("person", confidence=0.80, all_class_names=("person",))
    with pytest.raises(ImageValidationError):
        check_civic_relevance(det)


def test_image_validation_error_is_value_error():
    """ImageValidationError is a ValueError subclass (router compatibility)."""
    det = _result("person", confidence=0.80, all_class_names=("person",))
    with pytest.raises(ValueError):
        check_civic_relevance(det)


# ---------------------------------------------------------------------------
# Regression tests added for Bug 2 fix (PERSON_DOMINANCE_THRESHOLD lowered
# from 0.40 → 0.20 so typical selfie YOLOv8n detections are correctly rejected)
# ---------------------------------------------------------------------------


def test_selfie_at_low_confidence_now_rejected():
    """Person-only image at confidence 0.25 (typical YOLOv8n selfie range)
    must be rejected now that the threshold is 0.20.

    Before the fix (threshold=0.40) this passed through silently.
    """
    det = _result("person", confidence=0.25, all_class_names=("person",))
    with pytest.raises(ImageValidationError, match="civic issue"):
        check_civic_relevance(det)


def test_selfie_at_confidence_0_30_rejected():
    """Person-only image at 0.30 confidence — another typical selfie range."""
    det = _result("person", confidence=0.30, all_class_names=("person",))
    with pytest.raises(ImageValidationError):
        check_civic_relevance(det)


def test_very_low_confidence_person_still_passes():
    """A person detected at very low confidence (0.15, near-noise) still
    passes — the threshold is 0.20, so 0.15 should not trigger rejection.
    """
    det = _result("person", confidence=0.15, all_class_names=("person",))
    check_civic_relevance(det)  # must not raise


def test_civic_issue_with_low_confidence_person_accepted():
    """Civic scene: car (civic indicator) + person at 0.25 confidence →
    accepted because a civic indicator is present, regardless of person confidence.
    """
    det = _result(
        "car", confidence=0.25,
        all_class_names=("car", "person"),
        category=IssueCategory.road_damage,
    )
    check_civic_relevance(det)  # must not raise


def test_civic_issue_vehicle_and_person_accepted():
    """Road scene with vehicle + person → accepted (civic indicator present)."""
    det = _result(
        "truck", confidence=0.60,
        all_class_names=("truck", "car", "person"),
        category=IssueCategory.road_damage,
    )
    check_civic_relevance(det)  # must not raise
