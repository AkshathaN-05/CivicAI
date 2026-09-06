"""Local road-damage classifier — specialized pothole/crack detector.

Uses a YOLOv8s model fine-tuned on the Road Damage Dataset 2022 (RDD2022) to
detect road-specific damage classes without relying on generic COCO labels.

This module is the primary civic classification stage for road-related issues.
It fires before the remote Groq vision API call, providing accurate pothole and
road-damage detection offline.

Model: keremberke/yolov8s-road-damage-detection (HuggingFace Hub)
- Dataset: RDD2022 (road damage dataset, 47,000+ images, 6 countries)
- Classes:
    D00 — Longitudinal Crack   → IssueCategory.road_damage
    D10 — Transverse Crack     → IssueCategory.road_damage
    D20 — Alligator Crack      → IssueCategory.road_damage
    D40 — Pothole              → IssueCategory.pothole
- License: Apache 2.0
- Size: ~22 MB (YOLOv8s weights)
- Runs on CPU only; no GPU required.

Design decisions:
- Lazy-loaded singleton: model is NOT loaded at import time or FastAPI startup.
  It is downloaded from HuggingFace Hub on first inference call and then cached
  in the HuggingFace default cache (~/.cache/huggingface/hub).  Subsequent calls
  return the already-loaded model instance from the module-level singleton.
- If the model cannot be downloaded (offline, no HF Hub access), the function
  returns a result with confident=False so the caller falls back to the
  existing Groq vision pipeline.
- The raw YOLO COCO model (detection.py) continues to run for the civic
  relevance gate (selfie rejection); only category assignment is overridden
  by this module for road-related results.

Public API:
    classify_road_damage(image: PIL.Image) -> RoadDamageResult

    @dataclass RoadDamageResult:
        detected:    bool    — True if road damage found above threshold
        category:    str     — 'pothole' | 'road_damage' | ''
        confidence:  float   — best detection confidence [0.0, 1.0]
        raw_class:   str     — raw RDD class name (e.g. 'D40') or ''
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HuggingFace model identifier (Road Damage Dataset 2022 / RDD2022)
# ---------------------------------------------------------------------------
# keremberke/yolov8s-road-damage-detection — Apache 2.0, ~22 MB
# Trained on RDD2022; 4 road-specific classes.
_HF_REPO_ID: str = "keremberke/yolov8s-road-damage-detection"
_HF_MODEL_FILE: str = "best.pt"

# ---------------------------------------------------------------------------
# Confidence threshold: minimum detection confidence to trust the road model.
# Detections below this threshold are ignored and the pipeline falls through
# to the vision-based fallback (Groq or heuristic).
# Set conservatively to avoid false positives on non-road images.
# ---------------------------------------------------------------------------
ROAD_MODEL_CONFIDENCE_THRESHOLD: float = 0.35

# ---------------------------------------------------------------------------
# RDD class name → CivicAI category mapping.
# Only classes that are unambiguously a specific road issue are listed.
# D00/D10/D20 are surface cracks → road_damage.
# D40 is a pothole depression → pothole.
# ---------------------------------------------------------------------------
_RDD_CLASS_MAP: dict[str, str] = {
    "D00": "road_damage",   # longitudinal crack
    "D10": "road_damage",   # transverse crack
    "D20": "road_damage",   # alligator / mesh crack
    "D40": "pothole",       # pothole
}

# ---------------------------------------------------------------------------
# Module-level singleton — None until first classify_road_damage() call.
# This follows the same lazy-load pattern as cv/detection.py.
# ---------------------------------------------------------------------------
_road_model: Optional[object] = None  # ultralytics.YOLO instance


# ---------------------------------------------------------------------------
# Public result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RoadDamageResult:
    """Result of local road-damage model inference.

    Attributes:
        detected:   True when road damage is found above the confidence threshold.
        category:   'pothole', 'road_damage', or '' (empty when not detected).
        confidence: Confidence of the best detection in [0.0, 1.0].
        raw_class:  Raw RDD class name (e.g. 'D40') or empty string.
    """
    detected: bool
    category: str
    confidence: float
    raw_class: str = ""


# ---------------------------------------------------------------------------
# Internal model loader
# ---------------------------------------------------------------------------

def _get_road_model() -> object:
    """Return the road-damage model singleton, loading it on first call.

    Downloads from HuggingFace Hub on the very first call and caches in
    ~/.cache/huggingface/hub.  Subsequent calls return the in-memory instance.

    Returns the ultralytics YOLO model object.

    Raises:
        Exception: When the model cannot be loaded (offline, corrupt download,
                   etc.).  The caller must handle this and fall back gracefully.
    """
    global _road_model
    if _road_model is None:
        from huggingface_hub import hf_hub_download
        from ultralytics import YOLO

        logger.info(
            "road_damage: loading road-damage model from HF Hub (%s/%s) …",
            _HF_REPO_ID, _HF_MODEL_FILE,
        )
        local_path = hf_hub_download(
            repo_id=_HF_REPO_ID,
            filename=_HF_MODEL_FILE,
        )
        logger.info("road_damage: model downloaded/cached at %s", local_path)
        _road_model = YOLO(local_path)
        logger.info("road_damage: road-damage model loaded successfully.")
    return _road_model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_road_damage(image: Image.Image) -> RoadDamageResult:
    """Run the specialized road-damage model on *image*.

    Args:
        image: A PIL Image (any mode; converted to RGB internally).

    Returns:
        :class:`RoadDamageResult`.
        - ``detected=True`` with appropriate category when road damage is found
          above :data:`ROAD_MODEL_CONFIDENCE_THRESHOLD`.
        - ``detected=False`` with empty category when no confident detection
          is found or the model is unavailable.

    Notes:
        - Model loads lazily on first call.
        - Any exception from model loading or inference is caught and logged;
          the function returns ``detected=False`` so the pipeline falls back.
        - The original image is never mutated.
        - Inference runs on CPU only (no GPU dependency).
    """
    try:
        model = _get_road_model()
    except Exception as exc:
        logger.warning(
            "road_damage: model unavailable — skipping (will use vision fallback): %s",
            exc,
        )
        return RoadDamageResult(detected=False, category="", confidence=0.0)

    try:
        img_rgb = image.convert("RGB")
        results = model.predict(img_rgb, verbose=False, device="cpu")
    except Exception as exc:
        logger.warning("road_damage: inference failed: %s", exc)
        return RoadDamageResult(detected=False, category="", confidence=0.0)

    if not results:
        return RoadDamageResult(detected=False, category="", confidence=0.0)

    frame = results[0]
    boxes = frame.boxes
    if boxes is None or len(boxes) == 0:
        logger.debug("road_damage: no road damage detected.")
        return RoadDamageResult(detected=False, category="", confidence=0.0)

    # Extract detections: find the highest-confidence one above threshold
    confidences = boxes.conf.tolist()
    class_ids = boxes.cls.tolist()
    names: dict[int, str] = frame.names

    best_conf: float = 0.0
    best_class_name: str = ""

    for conf, cid in zip(confidences, class_ids):
        raw_name = names.get(int(cid), "")
        if conf > best_conf and raw_name in _RDD_CLASS_MAP:
            best_conf = float(conf)
            best_class_name = raw_name

    if best_conf < ROAD_MODEL_CONFIDENCE_THRESHOLD or not best_class_name:
        logger.debug(
            "road_damage: best conf %.3f below threshold %.3f — no confident result",
            best_conf, ROAD_MODEL_CONFIDENCE_THRESHOLD,
        )
        return RoadDamageResult(detected=False, category="", confidence=best_conf)

    civic_category = _RDD_CLASS_MAP[best_class_name]
    logger.info(
        "road_damage: detected %s (conf=%.3f) → category=%s",
        best_class_name, best_conf, civic_category,
    )
    return RoadDamageResult(
        detected=True,
        category=civic_category,
        confidence=best_conf,
        raw_class=best_class_name,
    )


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_road_model_for_testing() -> None:
    """Reset the road-damage model singleton to None.

    Intended for use in tests only.  Allows tests to verify that importing
    this module does not instantiate the model, and to reset between test runs.
    """
    global _road_model
    _road_model = None
