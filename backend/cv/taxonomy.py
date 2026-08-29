"""YOLO → CivicAI taxonomy mapping — T2-5.

Maps YOLOv8n COCO-80 class names to the canonical CivicAI IssueCategory enum.

Public API:

    map_to_category(yolo_class: str) -> IssueCategory

Rules:
- Input is a COCO class name string exactly as returned by ultralytics YOLOv8n.
- Matching is case-insensitive and strips surrounding whitespace.
- Classes with no sensible civic mapping return IssueCategory.other.
- No LLM, no authority routing, no confidence scoring here.
- Mapping is deterministic and fully explicit.

COCO-80 mapping rationale per CivicAI category
───────────────────────────────────────────────
pothole            — no direct COCO class; handled by road_damage proxy (car/truck
                     on damaged surface often co-occurs, but since COCO has no
                     "pothole" class we return other so downstream confidence
                     scoring can down-weight this route).
waterlogging       — "boat", "umbrella" can suggest wet/flooded areas.
broken_streetlight — "traffic light" is the nearest urban-lighting object in COCO.
garbage_overflow   — "bottle", "cup", "bowl", "banana", "apple", "sandwich",
                     "orange", "broccoli", "carrot", "hot dog", "pizza", "donut",
                     "cake", "wine glass", "fork", "knife", "spoon" suggest litter.
                     "backpack", "handbag", "suitcase" could be abandoned waste.
open_drain         — no direct COCO class → other.
illegal_construction — no direct COCO class → other.
water_supply       — "sink", "toilet" are plumbing-related COCO objects.
sewage             — "toilet" is also the closest sewer-related COCO object.
road_damage        — "car", "truck", "motorcycle", "bus", "bicycle", "stop sign",
                     "parking meter", "traffic light" indicate a road context
                     where damage may be relevant. "bench" (roadside furniture)
                     is included too.
other              — everything not explicitly mapped.
"""
from __future__ import annotations

import logging

from schemas.report import IssueCategory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Explicit COCO class → IssueCategory mapping
# ---------------------------------------------------------------------------
# Keys must be the exact lowercase COCO-80 class name strings produced by
# ultralytics YOLOv8n (id→name table shipped with the package).
# Order does not matter — dict lookup is O(1).

_MAPPING: dict[str, IssueCategory] = {
    # ── road_damage ──────────────────────────────────────────────────────
    # Road-context objects that suggest a road surface / signage problem
    "car":           IssueCategory.road_damage,
    "truck":         IssueCategory.road_damage,
    "motorcycle":    IssueCategory.road_damage,
    "bicycle":       IssueCategory.road_damage,
    "bus":           IssueCategory.road_damage,
    "traffic light": IssueCategory.road_damage,
    "stop sign":     IssueCategory.road_damage,
    "parking meter": IssueCategory.road_damage,

    # ── broken_streetlight ───────────────────────────────────────────────
    # "traffic light" also maps here; road_damage wins because road context
    # is stronger; the taxonomy is intentionally deterministic (one winner).
    # We use "fire hydrant" as a streetside fixture → broken_streetlight
    # is the closest civic infrastructure category for urban fixtures.
    "fire hydrant":  IssueCategory.broken_streetlight,

    # ── garbage_overflow ─────────────────────────────────────────────────
    # Food/drink items and containers commonly found as litter
    "bottle":        IssueCategory.garbage_overflow,
    "wine glass":    IssueCategory.garbage_overflow,
    "cup":           IssueCategory.garbage_overflow,
    "fork":          IssueCategory.garbage_overflow,
    "knife":         IssueCategory.garbage_overflow,
    "spoon":         IssueCategory.garbage_overflow,
    "bowl":          IssueCategory.garbage_overflow,
    "banana":        IssueCategory.garbage_overflow,
    "apple":         IssueCategory.garbage_overflow,
    "sandwich":      IssueCategory.garbage_overflow,
    "orange":        IssueCategory.garbage_overflow,
    "broccoli":      IssueCategory.garbage_overflow,
    "carrot":        IssueCategory.garbage_overflow,
    "hot dog":       IssueCategory.garbage_overflow,
    "pizza":         IssueCategory.garbage_overflow,
    "donut":         IssueCategory.garbage_overflow,
    "cake":          IssueCategory.garbage_overflow,
    # Abandoned bags / waste containers
    "backpack":      IssueCategory.garbage_overflow,
    "handbag":       IssueCategory.garbage_overflow,
    "suitcase":      IssueCategory.garbage_overflow,

    # ── water_supply ─────────────────────────────────────────────────────
    # Plumbing-related COCO objects closest to water infrastructure
    "sink":          IssueCategory.water_supply,

    # ── sewage ───────────────────────────────────────────────────────────
    "toilet":        IssueCategory.sewage,

    # ── waterlogging ─────────────────────────────────────────────────────
    "boat":          IssueCategory.waterlogging,
    "umbrella":      IssueCategory.waterlogging,

    # ── illegal_construction ─────────────────────────────────────────────
    # No COCO-80 class maps reliably → falls through to other.

    # ── open_drain ───────────────────────────────────────────────────────
    # No COCO-80 class maps reliably → falls through to other.

    # ── pothole ──────────────────────────────────────────────────────────
    # No COCO-80 class maps reliably → falls through to other.
}


def map_to_category(yolo_class: str) -> IssueCategory:
    """Return the CivicAI IssueCategory for a given YOLO class name.

    Args:
        yolo_class: A COCO-80 class name string as returned by ultralytics
                    YOLOv8n inference (e.g. ``"car"``, ``"bottle"``).

    Returns:
        The matching :class:`~schemas.report.IssueCategory`, or
        :attr:`~schemas.report.IssueCategory.other` when no mapping exists.
    """
    key = yolo_class.strip().lower()
    category = _MAPPING.get(key, IssueCategory.other)
    logger.debug("taxonomy: '%s' → %s", yolo_class, category.value)
    return category
