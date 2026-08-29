"""YOLOv8n object detection — T2-5.

Wraps the ultralytics YOLOv8n model for civic-issue detection and maps the
top-1 COCO detection to the CivicAI issue taxonomy.

Public API:

    detect_civic_issue(image: PIL.Image) -> DetectionResult

Design:
- YOLOv8n is loaded lazily on the first call (NOT at import time). (Part A §8)
- CPU-only inference; no GPU required.
- Input PIL Image is never mutated.
- Returns the highest-confidence detection across all classes.
- If no objects are detected, returns a DetectionResult with
  yolo_class="", confidence=0.0, category=IssueCategory.other.
- RGBA images are safely converted to RGB before inference.
- The module-level singleton ``_yolo_model`` is None until first call.

Usage:
    from cv.detection import detect_civic_issue, DetectionResult

    result = detect_civic_issue(pil_image)
    print(result.yolo_class, result.confidence, result.category)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from cv.taxonomy import map_to_category
from schemas.report import IssueCategory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model name — YOLOv8n (nano, smallest COCO model, CPU-compatible)
# ---------------------------------------------------------------------------
_YOLO_MODEL_NAME: str = "yolov8n.pt"

# ---------------------------------------------------------------------------
# Lazy-loaded singleton — None until first detect_civic_issue() call (Part A §8)
# ---------------------------------------------------------------------------
_yolo_model: Optional[object] = None  # ultralytics.YOLO instance


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DetectionResult:
    """Top-1 YOLO detection with taxonomy-mapped civic category.

    Attributes:
        yolo_class:  COCO class name of the top detection (empty string if none).
        confidence:  Raw YOLOv8n confidence score for the top detection [0.0, 1.0].
                     0.0 when no objects are detected.
        category:    CivicAI IssueCategory mapped from ``yolo_class`` by the
                     taxonomy module.  Always IssueCategory.other when no
                     detection is made.
    """
    yolo_class: str
    confidence: float
    category: IssueCategory


# ---------------------------------------------------------------------------
# Lazy loader
# ---------------------------------------------------------------------------

def _get_model():
    """Return the singleton YOLOv8n model, instantiating it on first call.

    The model is downloaded to the standard ultralytics cache on first use
    (~/.cache/ultralytics or %LOCALAPPDATA%/Ultralytics on Windows).
    Subsequent calls return the cached instance without re-loading.
    """
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO  # deferred import — keeps import-time clean

        logger.info("Loading YOLOv8n model (%s) …", _YOLO_MODEL_NAME)
        _yolo_model = YOLO(_YOLO_MODEL_NAME)
        logger.info("YOLOv8n model loaded.")
    return _yolo_model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_civic_issue(image: Image.Image) -> DetectionResult:
    """Run YOLOv8n inference on *image* and return the top-1 DetectionResult.

    The model is loaded lazily on the first call.

    Args:
        image: A PIL Image (any mode accepted; converted to RGB internally).

    Returns:
        :class:`DetectionResult` with the highest-confidence COCO detection
        and its mapped :class:`~schemas.report.IssueCategory`.  When no
        objects are detected the result has ``yolo_class=""``,
        ``confidence=0.0``, and ``category=IssueCategory.other``.

    Notes:
        - The input *image* is never modified.
        - Inference runs on CPU; no GPU is required.
        - Multiple detections are reduced to the single top-1 by confidence.
    """
    model = _get_model()

    # Work on a copy converted to RGB so the original PIL image is untouched
    # and RGBA / palette modes don't cause inference errors.
    img_rgb: Image.Image = image.convert("RGB")

    # Run inference — verbose=False suppresses console output;
    # device="cpu" forces CPU to avoid GPU dependency.
    results = model.predict(img_rgb, verbose=False, device="cpu")

    if not results:
        logger.debug("detect_civic_issue: no results returned by model.")
        return DetectionResult(yolo_class="", confidence=0.0, category=IssueCategory.other)

    # ultralytics returns a list[Results]; take the first frame.
    frame_result = results[0]
    boxes = frame_result.boxes  # Boxes object (may have 0 rows)

    if boxes is None or len(boxes) == 0:
        logger.debug("detect_civic_issue: no objects detected.")
        return DetectionResult(yolo_class="", confidence=0.0, category=IssueCategory.other)

    # Extract confidence scores and class indices as Python lists.
    # boxes.conf is a tensor of shape (N,); boxes.cls is a tensor of shape (N,).
    confidences = boxes.conf.tolist()  # [float, ...]
    class_ids = boxes.cls.tolist()     # [float, ...]  (float because tensor dtype)
    names: dict[int, str] = frame_result.names  # {int: str} COCO class names

    # Select top-1 by highest confidence.
    best_idx = int(max(range(len(confidences)), key=lambda i: confidences[i]))
    best_conf: float = float(confidences[best_idx])
    best_class_id: int = int(class_ids[best_idx])
    best_class_name: str = names.get(best_class_id, "")

    category = map_to_category(best_class_name)

    logger.debug(
        "detect_civic_issue: top-1 '%s' (id=%d) conf=%.3f → %s",
        best_class_name, best_class_id, best_conf, category.value,
    )
    return DetectionResult(
        yolo_class=best_class_name,
        confidence=best_conf,
        category=category,
    )


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_detector_for_testing() -> None:
    """Reset the lazy-loaded YOLOv8n singleton to None.

    Intended for use in tests only.  Allows tests to verify that importing
    this module does not instantiate the model, and to reset state between
    test runs without reloading the entire module.
    """
    global _yolo_model
    _yolo_model = None
