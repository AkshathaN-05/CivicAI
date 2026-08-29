"""T2-6 tests — evidence confidence scoring (cv/confidence.py).

Acceptance criteria (locked spec):
  1.  High-confidence pothole: conf=0.9 → score > 0.7
  2.  Low-confidence other:    conf=0.2 → score < 0.5
  3.  Pothole weight:          compute_confidence(0.8, pothole) == 0.8
  4.  Other weight:            compute_confidence(0.8, other)   == 0.32
  5.  Zero confidence:         result == 0.0
  6.  Maximum confidence:      result <= 1.0
  7.  Every IssueCategory:     valid float in [0.0, 1.0]
  8.  Boundary values:         0.0 and 1.0
  9.  Result type:             float
  10. Determinism:             same inputs → same output
  11. Invalid/out-of-range:    result always in [0.0, 1.0]
  12. Weight table completeness: every IssueCategory has a weight
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from cv.confidence import compute_confidence, _CATEGORY_WEIGHTS
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Locked spec tests (numbered 1–12)
# ---------------------------------------------------------------------------

def test_spec_1_high_confidence_pothole():
    """Spec 1: detection_confidence=0.9, pothole → score > 0.7."""
    score = compute_confidence(0.9, IssueCategory.pothole)
    assert score > 0.7, f"Expected > 0.7, got {score}"


def test_spec_2_low_confidence_other():
    """Spec 2: detection_confidence=0.2, other → score < 0.5."""
    score = compute_confidence(0.2, IssueCategory.other)
    assert score < 0.5, f"Expected < 0.5, got {score}"


def test_spec_3_pothole_weight():
    """Spec 3: compute_confidence(0.8, pothole) == 0.8  (weight=1.0)."""
    score = compute_confidence(0.8, IssueCategory.pothole)
    assert score == pytest.approx(0.8), f"Expected 0.8, got {score}"


def test_spec_4_other_weight():
    """Spec 4: compute_confidence(0.8, other) == 0.32  (weight=0.4)."""
    score = compute_confidence(0.8, IssueCategory.other)
    assert score == pytest.approx(0.32), f"Expected 0.32, got {score}"


def test_spec_5_zero_confidence():
    """Spec 5: detection_confidence=0.0 → score == 0.0 for any category."""
    for cat in IssueCategory:
        score = compute_confidence(0.0, cat)
        assert score == pytest.approx(0.0), (
            f"Expected 0.0 for category {cat.value}, got {score}"
        )


def test_spec_6_maximum_confidence_stays_leq_1():
    """Spec 6: detection_confidence=1.0 → score <= 1.0 for every category."""
    for cat in IssueCategory:
        score = compute_confidence(1.0, cat)
        assert score <= 1.0, f"Score {score} exceeds 1.0 for {cat.value}"


def test_spec_7_every_category_valid_range():
    """Spec 7: every IssueCategory returns a float in [0.0, 1.0]."""
    for cat in IssueCategory:
        score = compute_confidence(0.75, cat)
        assert isinstance(score, float), f"Result is not float for {cat.value}"
        assert 0.0 <= score <= 1.0, (
            f"Score {score} out of [0,1] for {cat.value}"
        )


def test_spec_8_boundary_zero():
    """Spec 8a: boundary value 0.0 works."""
    score = compute_confidence(0.0, IssueCategory.pothole)
    assert score == pytest.approx(0.0)


def test_spec_8_boundary_one():
    """Spec 8b: boundary value 1.0 works."""
    score = compute_confidence(1.0, IssueCategory.pothole)
    assert score == pytest.approx(1.0)


def test_spec_9_result_is_float():
    """Spec 9: compute_confidence always returns a plain float."""
    result = compute_confidence(0.5, IssueCategory.garbage_overflow)
    assert type(result) is float, f"Expected float, got {type(result)}"


def test_spec_10_determinism():
    """Spec 10: identical inputs always produce identical outputs."""
    inputs = [
        (0.5, IssueCategory.pothole),
        (0.3, IssueCategory.other),
        (1.0, IssueCategory.road_damage),
        (0.0, IssueCategory.sewage),
    ]
    for conf, cat in inputs:
        first  = compute_confidence(conf, cat)
        second = compute_confidence(conf, cat)
        assert first == second, (
            f"Non-deterministic result for ({conf}, {cat.value}): "
            f"{first} != {second}"
        )


def test_spec_11_negative_confidence_clamped():
    """Spec 11a: negative detection confidence is clamped to 0.0."""
    score = compute_confidence(-0.5, IssueCategory.pothole)
    assert 0.0 <= score <= 1.0, f"Score {score} out of range for negative input"
    assert score == pytest.approx(0.0)


def test_spec_11_above_one_confidence_clamped():
    """Spec 11b: detection confidence > 1.0 is clamped to 1.0 * weight."""
    score = compute_confidence(1.5, IssueCategory.pothole)
    assert 0.0 <= score <= 1.0, f"Score {score} out of range for input > 1.0"
    assert score == pytest.approx(1.0)  # pothole weight = 1.0, clamped det = 1.0


def test_spec_11_nan_input_safe():
    """Spec 11c: NaN detection confidence does not propagate — returns 0.0."""
    score = compute_confidence(float("nan"), IssueCategory.pothole)
    assert math.isfinite(score), "NaN must not propagate to output"
    assert score == pytest.approx(0.0)


def test_spec_11_positive_inf_input_clamped():
    """Spec 11d: +inf detection confidence is clamped, result in [0,1]."""
    score = compute_confidence(float("inf"), IssueCategory.pothole)
    assert math.isfinite(score)
    assert 0.0 <= score <= 1.0


def test_spec_11_negative_inf_input_clamped():
    """Spec 11e: -inf detection confidence is clamped, result in [0,1]."""
    score = compute_confidence(float("-inf"), IssueCategory.garbage_overflow)
    assert math.isfinite(score)
    assert 0.0 <= score <= 1.0


def test_spec_12_weight_table_covers_every_category():
    """Spec 12: _CATEGORY_WEIGHTS contains an entry for every IssueCategory."""
    for cat in IssueCategory:
        assert cat in _CATEGORY_WEIGHTS, (
            f"No weight entry found for IssueCategory.{cat.value}. "
            "Update _CATEGORY_WEIGHTS in confidence.py."
        )


# ---------------------------------------------------------------------------
# Formula correctness for every category
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cat", list(IssueCategory))
def test_formula_det_times_weight(cat: IssueCategory):
    """score == detection_confidence × weight, clamped to [0,1]."""
    det = 0.6
    expected = det * _CATEGORY_WEIGHTS[cat]
    score = compute_confidence(det, cat)
    assert score == pytest.approx(expected), (
        f"Category {cat.value}: expected {expected}, got {score}"
    )


# ---------------------------------------------------------------------------
# Specific category weight spot-checks
# ---------------------------------------------------------------------------

def test_pothole_weight_is_1_0():
    assert _CATEGORY_WEIGHTS[IssueCategory.pothole] == pytest.approx(1.0)


def test_other_weight_is_0_4():
    assert _CATEGORY_WEIGHTS[IssueCategory.other] == pytest.approx(0.4)


def test_all_weights_in_valid_range():
    """Every weight in the table must itself be in [0.0, 1.0]."""
    for cat, w in _CATEGORY_WEIGHTS.items():
        assert 0.0 <= w <= 1.0, (
            f"Weight {w} for {cat.value} is outside [0, 1]."
        )


# ---------------------------------------------------------------------------
# Additional edge-case confidence values
# ---------------------------------------------------------------------------

def test_midpoint_confidence_road_damage():
    score = compute_confidence(0.5, IssueCategory.road_damage)
    expected = 0.5 * _CATEGORY_WEIGHTS[IssueCategory.road_damage]
    assert score == pytest.approx(expected)


def test_full_confidence_other_stays_within_range():
    score = compute_confidence(1.0, IssueCategory.other)
    assert score == pytest.approx(0.4)
    assert 0.0 <= score <= 1.0
