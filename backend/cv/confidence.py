"""Evidence confidence scoring — T2-6.

Computes a final evidence confidence score by combining the raw YOLOv8n
detection confidence with a per-category relevance weight.

Public API:

    compute_confidence(
        detection_confidence: float,
        category: IssueCategory,
    ) -> float

Formula (locked):

    score = detection_confidence × category_relevance_weight

The result is always clamped to [0.0, 1.0].

This module is a pure advisory utility.  It contains no model loading,
no network calls, no database calls, and no LLM calls.
"""
from __future__ import annotations

import math

from schemas.report import IssueCategory

# ---------------------------------------------------------------------------
# Category relevance weight table
# ---------------------------------------------------------------------------
# Weights reflect how reliably YOLOv8n COCO-80 detections signal the
# corresponding civic issue category.
#
# Rationale:
#   pothole (1.0)             — locked by spec; high specificity when detected
#   road_damage (0.9)         — road-context objects (car/truck) strongly indicate
#                               road issues; slightly below pothole since a car
#                               alone doesn't confirm damage
#   garbage_overflow (0.8)    — litter objects (bottle, food, bags) are reliable
#                               indicators of garbage accumulation
#   broken_streetlight (0.75) — fire hydrant is a plausible street-fixture signal;
#                               lower than garbage because the mapping is indirect
#   sewage (0.7)              — toilet is a plausible sewer signal in context
#   waterlogging (0.65)       — boat/umbrella suggest flooding but are ambiguous
#   water_supply (0.6)        — sink is a plausible plumbing signal but indirect
#   open_drain (0.5)          — no direct COCO class; moderate default
#   illegal_construction (0.5)— no direct COCO class; moderate default
#   other (0.4)               — locked by spec; catch-all, low relevance
# ---------------------------------------------------------------------------

_CATEGORY_WEIGHTS: dict[IssueCategory, float] = {
    IssueCategory.pothole:              1.0,
    IssueCategory.road_damage:          0.9,
    IssueCategory.garbage_overflow:     0.8,
    IssueCategory.broken_streetlight:   0.75,
    IssueCategory.sewage:               0.7,
    IssueCategory.waterlogging:         0.65,
    IssueCategory.water_supply:         0.6,
    IssueCategory.open_drain:           0.5,
    IssueCategory.illegal_construction: 0.5,
    IssueCategory.other:                0.4,
}

# Verify at module load that every IssueCategory has a weight entry.
# This is a cheap sanity check — not model loading.
_missing = [c for c in IssueCategory if c not in _CATEGORY_WEIGHTS]
if _missing:  # pragma: no cover
    raise RuntimeError(
        f"confidence.py: missing weight entries for {[c.value for c in _missing]}. "
        "Update _CATEGORY_WEIGHTS to cover every IssueCategory."
    )


def compute_confidence(
    detection_confidence: float,
    category: IssueCategory,
) -> float:
    """Return the evidence confidence score for a detection.

    Formula:
        score = detection_confidence × category_relevance_weight

    The result is clamped to [0.0, 1.0].  Non-finite inputs (NaN, ±inf)
    are treated as 0.0 before the multiplication so the function never
    returns a non-finite value.

    Args:
        detection_confidence: Raw YOLOv8n confidence for the top detection.
                              Expected range [0.0, 1.0]; out-of-range values
                              are clamped safely.
        category:             Mapped :class:`~schemas.report.IssueCategory`.

    Returns:
        Evidence confidence score as a :class:`float` in [0.0, 1.0].
    """
    # Sanitise: replace non-finite values with 0.0
    if not math.isfinite(detection_confidence):
        detection_confidence = 0.0

    # Clamp detection confidence to [0.0, 1.0] in case caller passes
    # an out-of-range value (e.g. -0.1 or 1.5).
    det_conf = max(0.0, min(1.0, float(detection_confidence)))

    weight: float = _CATEGORY_WEIGHTS[category]

    score = det_conf * weight

    # Final clamp — weight is already in [0,1] and det_conf in [0,1] so
    # this is a defensive belt-and-suspenders guarantee.
    return max(0.0, min(1.0, score))
