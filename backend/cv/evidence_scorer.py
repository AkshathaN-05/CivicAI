"""Evidence scorer — pure mathematics, no I/O (cv/evidence_scorer.py).

Computes a weighted multi-signal evidence score from four confidence dimensions.

Architecture:
    visual    = 0.35   (image-only AI confidence)
    category  = 0.20   (model certainty about the category)
    location  = 0.30   (GPS quality + plausibility)
    freshness = 0.15   (temporal recency)

    evidence_score = sum(dimension * weight), clamped to [0.0, 1.0]

This module contains NO database calls, NO model loading, and NO network calls.
It is independently unit-testable and deterministic.

The DB-dependent decision logic (duplicate detection, reopen detection,
admin_priority assignment) lives in cv/decision_engine.py.

Public API:
    compute_evidence_score(
        visual_confidence: float,
        category_confidence: float,
        location_confidence: float,
        freshness_confidence: float,
    ) -> float

    EvidenceWeights (dataclass)   — approved weight constants
    VALID_THRESHOLD      = 0.65
    REVIEW_THRESHOLD     = 0.35
    GEO_DUPLICATE_FLOOR  = 0.30
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Approved weight constants (canonical — must match architecture decision)
# ---------------------------------------------------------------------------

EVIDENCE_WEIGHT_VISUAL    = 0.35
EVIDENCE_WEIGHT_CATEGORY  = 0.20
EVIDENCE_WEIGHT_LOCATION  = 0.30
EVIDENCE_WEIGHT_FRESHNESS = 0.15

# Sum guard (defensive — caught at import time)
_WEIGHT_SUM = (
    EVIDENCE_WEIGHT_VISUAL
    + EVIDENCE_WEIGHT_CATEGORY
    + EVIDENCE_WEIGHT_LOCATION
    + EVIDENCE_WEIGHT_FRESHNESS
)
if abs(_WEIGHT_SUM - 1.0) > 1e-9:  # pragma: no cover
    raise RuntimeError(
        f"evidence_scorer: weights do not sum to 1.0 (got {_WEIGHT_SUM}). "
        "Check EVIDENCE_WEIGHT_* constants."
    )


# ---------------------------------------------------------------------------
# Decision thresholds
# ---------------------------------------------------------------------------

VALID_THRESHOLD: float = 0.65     # evidence_score >= this → VALID_CIVIC_REPORT
REVIEW_THRESHOLD: float = 0.35    # evidence_score >= this → NEEDS_ADMIN_REVIEW
GEO_DUPLICATE_FLOOR: float = 0.30 # geo-proximity duplicate requires score >= this


# ---------------------------------------------------------------------------
# Weight dataclass (for introspection / tests)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceWeights:
    visual:    float = EVIDENCE_WEIGHT_VISUAL
    category:  float = EVIDENCE_WEIGHT_CATEGORY
    location:  float = EVIDENCE_WEIGHT_LOCATION
    freshness: float = EVIDENCE_WEIGHT_FRESHNESS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _safe_float(v: float) -> float:
    """Replace non-finite float with 0.0 and clamp to [0.0, 1.0]."""
    if not math.isfinite(v):
        return 0.0
    return max(0.0, min(1.0, float(v)))


def compute_evidence_score(
    visual_confidence: float,
    category_confidence: float,
    location_confidence: float,
    freshness_confidence: float,
) -> float:
    """Return the weighted evidence score, clamped to [0.0, 1.0].

    Formula:
        score = visual    * 0.35
              + category  * 0.20
              + location  * 0.30
              + freshness * 0.15

    All inputs are sanitised: non-finite values become 0.0; out-of-range
    values are clamped to [0.0, 1.0] before weighting.

    Args:
        visual_confidence:    Image-only AI detection confidence.
        category_confidence:  Model certainty about the civic category.
        location_confidence:  GPS quality and plausibility score.
        freshness_confidence: Temporal recency (EXIF + corroboration).

    Returns:
        Evidence score as a float in [0.0, 1.0].
    """
    v = _safe_float(visual_confidence)
    c = _safe_float(category_confidence)
    l = _safe_float(location_confidence)
    f = _safe_float(freshness_confidence)

    raw = (
        v * EVIDENCE_WEIGHT_VISUAL
        + c * EVIDENCE_WEIGHT_CATEGORY
        + l * EVIDENCE_WEIGHT_LOCATION
        + f * EVIDENCE_WEIGHT_FRESHNESS
    )

    # Final clamp (defensive — inputs already clamped so raw ∈ [0,1])
    return max(0.0, min(1.0, raw))
