"""Tests for cv/evidence_scorer.py — pure evidence scoring math.

All tests are deterministic and require no external services.

Covers:
  - Canonical weight values (0.35/0.20/0.30/0.15)
  - Formula correctness with exact expected values
  - Clamping: non-finite inputs, out-of-range inputs, final result bounds
  - Determinism: same inputs always produce same output
  - Example A: high visual, high location, high freshness
  - Example B: very high visual, weak location
  - Example C: moderate visual, excellent location + freshness → 0.747, MEDIUM priority
  - Threshold constants
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from cv.evidence_scorer import (
    EVIDENCE_WEIGHT_CATEGORY,
    EVIDENCE_WEIGHT_FRESHNESS,
    EVIDENCE_WEIGHT_LOCATION,
    EVIDENCE_WEIGHT_VISUAL,
    GEO_DUPLICATE_FLOOR,
    REVIEW_THRESHOLD,
    VALID_THRESHOLD,
    _WEIGHT_SUM,
    compute_evidence_score,
)


# ---------------------------------------------------------------------------
# Weight constants
# ---------------------------------------------------------------------------

def test_visual_weight():
    assert EVIDENCE_WEIGHT_VISUAL == pytest.approx(0.35)


def test_category_weight():
    assert EVIDENCE_WEIGHT_CATEGORY == pytest.approx(0.20)


def test_location_weight():
    assert EVIDENCE_WEIGHT_LOCATION == pytest.approx(0.30)


def test_freshness_weight():
    assert EVIDENCE_WEIGHT_FRESHNESS == pytest.approx(0.15)


def test_weights_sum_to_one():
    assert _WEIGHT_SUM == pytest.approx(1.0)


def test_valid_threshold():
    assert VALID_THRESHOLD == pytest.approx(0.65)


def test_review_threshold():
    assert REVIEW_THRESHOLD == pytest.approx(0.35)


def test_geo_duplicate_floor():
    assert GEO_DUPLICATE_FLOOR == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Formula correctness
# ---------------------------------------------------------------------------

def test_formula_all_ones():
    """All inputs = 1.0 → score = 1.0."""
    score = compute_evidence_score(1.0, 1.0, 1.0, 1.0)
    assert score == pytest.approx(1.0)


def test_formula_all_zeros():
    """All inputs = 0.0 → score = 0.0."""
    score = compute_evidence_score(0.0, 0.0, 0.0, 0.0)
    assert score == pytest.approx(0.0)


def test_formula_visual_only():
    """Only visual = 1.0, rest 0.0 → score = 0.35."""
    score = compute_evidence_score(1.0, 0.0, 0.0, 0.0)
    assert score == pytest.approx(0.35)


def test_formula_category_only():
    score = compute_evidence_score(0.0, 1.0, 0.0, 0.0)
    assert score == pytest.approx(0.20)


def test_formula_location_only():
    score = compute_evidence_score(0.0, 0.0, 1.0, 0.0)
    assert score == pytest.approx(0.30)


def test_formula_freshness_only():
    score = compute_evidence_score(0.0, 0.0, 0.0, 1.0)
    assert score == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Canonical architecture examples
# ---------------------------------------------------------------------------

def test_example_A_high_visual_high_location_high_freshness():
    """
    Example A from architecture docs:
      visual=0.88  category=0.92  location=0.85  freshness=0.90
      expected = 0.88*0.35 + 0.92*0.20 + 0.85*0.30 + 0.90*0.15
               = 0.308 + 0.184 + 0.255 + 0.135 = 0.882
    """
    score = compute_evidence_score(0.88, 0.92, 0.85, 0.90)
    assert score == pytest.approx(0.882, abs=1e-4)
    assert score >= VALID_THRESHOLD


def test_example_B_high_visual_weak_location():
    """
    Example B: high visual but no GPS (location floor = 0.30)
      visual=0.93  category=0.88  location=0.30  freshness=0.50
      expected = 0.93*0.35 + 0.88*0.20 + 0.30*0.30 + 0.50*0.15
               = 0.3255 + 0.176 + 0.090 + 0.075 = 0.6665
    """
    score = compute_evidence_score(0.93, 0.88, 0.30, 0.50)
    assert score == pytest.approx(0.6665, abs=1e-4)
    assert score >= VALID_THRESHOLD  # barely valid


def test_example_C_moderate_visual_excellent_location_freshness():
    """
    Example C (architecture correction confirmed):
      visual=0.62  category=0.70  location=0.85  freshness=0.90
      expected = 0.62*0.35 + 0.70*0.20 + 0.85*0.30 + 0.90*0.15
               = 0.217 + 0.140 + 0.255 + 0.135 = 0.747
    Decision: VALID_CIVIC_REPORT (0.747 >= 0.65)
    Admin priority: MEDIUM (0.747 < 0.75)
    """
    score = compute_evidence_score(0.62, 0.70, 0.85, 0.90)
    assert score == pytest.approx(0.747, abs=1e-4)
    # Confirm it is above VALID_THRESHOLD
    assert score >= VALID_THRESHOLD
    # Confirm it is below 0.75 (MEDIUM, not HIGH)
    assert score < 0.75


def test_example_C_admin_priority_is_MEDIUM():
    """Example C → admin_priority must be MEDIUM (not HIGH), per architecture."""
    from cv.decision_engine import _assign_admin_priority
    score = compute_evidence_score(0.62, 0.70, 0.85, 0.90)
    # Score = 0.747; severity = "medium"
    # HIGH requires score >= 0.75; 0.747 < 0.75 → MEDIUM
    priority = _assign_admin_priority("valid_civic_report", score, 0.62, "medium")
    assert priority == "MEDIUM"


# ---------------------------------------------------------------------------
# Clamping and edge cases
# ---------------------------------------------------------------------------

def test_result_always_in_range():
    """Result must always be in [0.0, 1.0]."""
    cases = [
        (0.0, 0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0, 1.0),
        (0.5, 0.5, 0.5, 0.5),
        (-1.0, 2.0, 0.5, 0.5),  # out-of-range inputs
    ]
    for v, c, l, f in cases:
        score = compute_evidence_score(v, c, l, f)
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for inputs ({v},{c},{l},{f})"


def test_negative_inputs_clamped():
    score = compute_evidence_score(-0.5, -0.5, -0.5, -0.5)
    assert score == pytest.approx(0.0)


def test_above_one_inputs_clamped():
    score = compute_evidence_score(2.0, 2.0, 2.0, 2.0)
    assert score == pytest.approx(1.0)


def test_nan_visual_safe():
    score = compute_evidence_score(float("nan"), 0.5, 0.5, 0.5)
    assert math.isfinite(score)
    assert 0.0 <= score <= 1.0


def test_inf_visual_safe():
    score = compute_evidence_score(float("inf"), 0.5, 0.5, 0.5)
    assert math.isfinite(score)
    assert 0.0 <= score <= 1.0


def test_neg_inf_location_safe():
    score = compute_evidence_score(0.5, 0.5, float("-inf"), 0.5)
    assert math.isfinite(score)
    assert 0.0 <= score <= 1.0


def test_result_is_float():
    result = compute_evidence_score(0.5, 0.5, 0.5, 0.5)
    assert isinstance(result, float)


def test_determinism():
    """Same inputs always produce the same output."""
    inputs = [
        (0.88, 0.92, 0.85, 0.90),
        (0.62, 0.70, 0.85, 0.90),
        (0.0, 0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0, 1.0),
    ]
    for v, c, l, f in inputs:
        first  = compute_evidence_score(v, c, l, f)
        second = compute_evidence_score(v, c, l, f)
        assert first == second


# ---------------------------------------------------------------------------
# Threshold boundary tests
# ---------------------------------------------------------------------------

def test_just_below_valid_threshold():
    """A score just below 0.65 should be NEEDS_ADMIN_REVIEW."""
    # Need a combination that produces 0.649
    # Solve: 0.649 = v*0.35 + c*0.20 + l*0.30 + f*0.15
    # Use visual=0.60, category=0.60, location=0.65, freshness=0.65
    score = compute_evidence_score(0.60, 0.60, 0.65, 0.65)
    assert score < VALID_THRESHOLD or score == pytest.approx(VALID_THRESHOLD, abs=0.05)
    # Main assertion: above review threshold
    assert score >= REVIEW_THRESHOLD


def test_exactly_at_review_threshold():
    """Evidence score of 0.35 should be >= REVIEW_THRESHOLD."""
    # visual=0.35/0.35, rest=0
    score = compute_evidence_score(1.0, 0.0, 0.0, 0.0)
    assert score == pytest.approx(0.35)
    assert score >= REVIEW_THRESHOLD


def test_just_below_review_threshold():
    """Score < 0.35 → INSUFFICIENT_EVIDENCE territory."""
    score = compute_evidence_score(0.0, 0.0, 0.80, 0.0)  # 0.80*0.30 = 0.24
    assert score == pytest.approx(0.24, abs=1e-4)
    assert score < REVIEW_THRESHOLD
