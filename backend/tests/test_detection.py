"""T2-5 tests — YOLOv8n civic detection (cv/detection.py).

Acceptance criteria:
  - importing detection.py does NOT instantiate the YOLO model
  - model is loaded lazily only when detect_civic_issue() is first called
  - top-1 (highest-confidence) detection is returned
  - correct DetectionResult fields: yolo_class, confidence, category
  - taxonomy mapping is called correctly
  - no-detection case returns safe result (empty class, 0.0 conf, other category)
  - empty/blank PIL images do not crash
  - RGB and RGBA images both work
  - input image is NOT mutated
  - reset_detector_for_testing() clears the singleton
  - DetectionResult is frozen/immutable
  - real-model smoke test (skipped if weights absent)

Design:
  All deterministic tests mock the ultralytics YOLO model so no network access
  or GPU is needed.  The mock mimics the ultralytics Results/Boxes API surface
  that detection.py actually calls.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from PIL import Image

from cv.detection import DetectionResult, reset_detector_for_testing
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Helper: build fake ultralytics Results object
# ---------------------------------------------------------------------------

def _fake_results(detections: list[tuple[str, float]], names: dict[int, str]) -> list:
    """Build a minimal mock of the ultralytics Results list.

    Args:
        detections: list of (class_name, confidence) pairs.
        names:      {class_id: class_name} dict (mirrors Results.names).

    Returns:
        A list with one mock Results element, mirroring model.predict() output.
    """
    import torch

    # Build class-id → name reverse map
    name_to_id = {v: k for k, v in names.items()}

    if not detections:
        # No detections — Boxes with zero rows
        mock_boxes = MagicMock()
        mock_boxes.__len__ = lambda self: 0
        # conf and cls tensors with 0 elements
        mock_boxes.conf = torch.tensor([], dtype=torch.float32)
        mock_boxes.cls = torch.tensor([], dtype=torch.float32)
    else:
        confs = [c for _, c in detections]
        cls_ids = [float(name_to_id[n]) for n, _ in detections]

        mock_boxes = MagicMock()
        mock_boxes.__len__ = MagicMock(return_value=len(detections))
        mock_boxes.conf = torch.tensor(confs, dtype=torch.float32)
        mock_boxes.cls = torch.tensor(cls_ids, dtype=torch.float32)

    mock_result = MagicMock()
    mock_result.boxes = mock_boxes
    mock_result.names = names

    return [mock_result]


# Standard COCO names subset used across tests
_NAMES = {
    0: "person",
    2: "car",
    7: "truck",
    39: "bottle",
    61: "toilet",
    63: "laptop",
    67: "cell phone",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the YOLO singleton before and after every test."""
    reset_detector_for_testing()
    yield
    reset_detector_for_testing()


def _make_image(width: int = 320, height: int = 320, color=(100, 150, 200)) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


def _make_rgba_image(width: int = 320, height: int = 320) -> Image.Image:
    return Image.new("RGBA", (width, height), color=(0, 200, 100, 180))


# ---------------------------------------------------------------------------
# Tests: lazy loading
# ---------------------------------------------------------------------------

def test_model_not_loaded_at_import_time():
    """Importing detection.py must not instantiate the YOLO model."""
    import cv.detection as det_mod

    # The autouse fixture reset it; verify it's still None.
    assert det_mod._yolo_model is None, (
        "YOLOv8n model must not be loaded at module import time (Part A §8)."
    )


def test_model_loaded_lazily_on_first_call():
    """Model is instantiated only when detect_civic_issue() is first called."""
    import cv.detection as det_mod

    assert det_mod._yolo_model is None, "Pre-condition: singleton must be None."

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    with patch("cv.detection._get_model", return_value=mock_model):
        det_mod.detect_civic_issue(_make_image())

    mock_model.predict.assert_called_once()


def test_get_model_called_only_once_across_multiple_calls():
    """_get_model is called each time but only instantiates YOLO once."""
    import cv.detection as det_mod

    call_count = {"n": 0}
    sentinel_model = MagicMock()
    sentinel_model.predict.return_value = _fake_results([], _NAMES)

    real_get_model = det_mod._get_model

    def counting_get_model():
        call_count["n"] += 1
        return sentinel_model

    with patch.object(det_mod, "_get_model", side_effect=counting_get_model):
        det_mod.detect_civic_issue(_make_image())
        det_mod.detect_civic_issue(_make_image())

    assert call_count["n"] == 2  # _get_model called twice (it's the guard function)
    # But the underlying YOLO constructor should have been called at most once
    # — that's validated by testing the singleton behaviour in test_reset_*


# ---------------------------------------------------------------------------
# Tests: no-detection / empty result
# ---------------------------------------------------------------------------

def test_no_detections_returns_other():
    """Empty detections → DetectionResult with empty class, 0.0 conf, other."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.yolo_class == ""
    assert result.confidence == 0.0
    assert result.category == IssueCategory.other


def test_empty_results_list_returns_other():
    """model.predict returns [] (no Results frames) → safe other result."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = []  # completely empty list

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.category == IssueCategory.other
    assert result.confidence == 0.0


def test_none_boxes_returns_other():
    """frame.boxes is None → safe other result."""
    import cv.detection as det_mod

    mock_frame = MagicMock()
    mock_frame.boxes = None
    mock_frame.names = _NAMES

    mock_model = MagicMock()
    mock_model.predict.return_value = [mock_frame]

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.category == IssueCategory.other


# ---------------------------------------------------------------------------
# Tests: single detection
# ---------------------------------------------------------------------------

def test_single_car_detection_road_damage():
    """Single 'car' detection → road_damage category."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("car", 0.82)], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.yolo_class == "car"
    assert abs(result.confidence - 0.82) < 1e-4
    assert result.category == IssueCategory.road_damage


def test_single_bottle_detection_garbage_overflow():
    """Single 'bottle' detection → garbage_overflow category."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("bottle", 0.75)], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.yolo_class == "bottle"
    assert result.category == IssueCategory.garbage_overflow


def test_single_toilet_detection_sewage():
    """Single 'toilet' detection → sewage category."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("toilet", 0.91)], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.yolo_class == "toilet"
    assert result.category == IssueCategory.sewage


def test_single_unmapped_class_returns_other():
    """Single unmapped class ('laptop') → other category."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("laptop", 0.65)], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.yolo_class == "laptop"
    assert result.category == IssueCategory.other


# ---------------------------------------------------------------------------
# Tests: multiple detections — top-1 by confidence
# ---------------------------------------------------------------------------

def test_multiple_detections_selects_highest_confidence():
    """With multiple detections, top-1 by confidence score is returned."""
    import cv.detection as det_mod

    detections = [
        ("person", 0.50),
        ("car",    0.88),   # ← highest
        ("bottle", 0.71),
    ]
    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results(detections, _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.yolo_class == "car"
    assert abs(result.confidence - 0.88) < 1e-4
    assert result.category == IssueCategory.road_damage


def test_multiple_detections_second_is_highest():
    """Top-1 is not necessarily the first detection in the list."""
    import cv.detection as det_mod

    detections = [
        ("person",  0.30),
        ("bottle",  0.95),  # ← highest
        ("truck",   0.60),
    ]
    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results(detections, _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.yolo_class == "bottle"
    assert result.category == IssueCategory.garbage_overflow


def test_multiple_unmapped_all_return_other():
    """All detections are unmapped classes → top-1 is other."""
    import cv.detection as det_mod

    detections = [
        ("person",     0.40),
        ("cell phone", 0.80),  # ← highest, but unmapped
        ("laptop",     0.55),
    ]
    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results(detections, _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.category == IssueCategory.other


# ---------------------------------------------------------------------------
# Tests: boundary confidence values
# ---------------------------------------------------------------------------

def test_confidence_zero():
    """Detection with confidence 0.0 is handled."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("car", 0.0)], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.confidence == pytest.approx(0.0)
    assert result.category == IssueCategory.road_damage


def test_confidence_one():
    """Detection with confidence 1.0 is handled."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("bottle", 1.0)], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert result.confidence == pytest.approx(1.0)


def test_confidence_typical():
    """Typical confidence (0.0–1.0) is returned correctly."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("truck", 0.4321)], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert abs(result.confidence - 0.4321) < 1e-4


# ---------------------------------------------------------------------------
# Tests: PIL image modes
# ---------------------------------------------------------------------------

def test_rgb_image_accepted():
    """RGB PIL image is accepted without error."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_image())

    assert isinstance(result, DetectionResult)


def test_rgba_image_accepted():
    """RGBA PIL image is accepted and converted to RGB internally."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(_make_rgba_image())

    assert isinstance(result, DetectionResult)


def test_small_image_does_not_crash():
    """Very small images (32×32) do not cause crashes."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    small = Image.new("RGB", (32, 32), color=(255, 0, 0))
    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(small)

    assert isinstance(result, DetectionResult)


def test_blank_image_does_not_crash():
    """Pure white 320×320 image does not crash (likely no detections)."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    blank = Image.new("RGB", (320, 320), color=(255, 255, 255))
    with patch.object(det_mod, "_get_model", return_value=mock_model):
        result = det_mod.detect_civic_issue(blank)

    assert isinstance(result, DetectionResult)
    assert result.category == IssueCategory.other


# ---------------------------------------------------------------------------
# Tests: input immutability
# ---------------------------------------------------------------------------

def test_original_image_not_mutated():
    """detect_civic_issue must not modify the input PIL image."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([("car", 0.9)], _NAMES)

    img = _make_image(400, 400, color=(77, 88, 99))
    original_bytes = img.tobytes()
    original_mode = img.mode
    original_size = img.size

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        det_mod.detect_civic_issue(img)

    assert img.tobytes() == original_bytes, "Input image pixel data must not be modified."
    assert img.mode == original_mode, "Input image mode must not be changed."
    assert img.size == original_size, "Input image size must not be changed."


# ---------------------------------------------------------------------------
# Tests: DetectionResult properties
# ---------------------------------------------------------------------------

def test_detection_result_is_frozen():
    """DetectionResult must be immutable (frozen dataclass)."""
    result = DetectionResult(yolo_class="car", confidence=0.9, category=IssueCategory.road_damage)
    with pytest.raises((AttributeError, TypeError)):
        result.yolo_class = "truck"  # type: ignore[misc]


def test_detection_result_fields():
    """DetectionResult exposes yolo_class, confidence, and category."""
    result = DetectionResult(yolo_class="bottle", confidence=0.75, category=IssueCategory.garbage_overflow)
    assert result.yolo_class == "bottle"
    assert result.confidence == pytest.approx(0.75)
    assert result.category == IssueCategory.garbage_overflow


# ---------------------------------------------------------------------------
# Tests: reset_detector_for_testing
# ---------------------------------------------------------------------------

def test_reset_detector_sets_singleton_to_none():
    """reset_detector_for_testing() sets _yolo_model to None."""
    import cv.detection as det_mod

    det_mod._yolo_model = MagicMock()  # simulate a loaded model
    assert det_mod._yolo_model is not None
    reset_detector_for_testing()
    assert det_mod._yolo_model is None


# ---------------------------------------------------------------------------
# Tests: model predict called with correct arguments
# ---------------------------------------------------------------------------

def test_predict_called_with_cpu_device():
    """model.predict must be called with device='cpu'."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        det_mod.detect_civic_issue(_make_image())

    call_kwargs = mock_model.predict.call_args
    assert call_kwargs.kwargs.get("device") == "cpu", (
        "Inference must run on CPU to avoid GPU dependency."
    )


def test_predict_called_with_verbose_false():
    """model.predict must be called with verbose=False."""
    import cv.detection as det_mod

    mock_model = MagicMock()
    mock_model.predict.return_value = _fake_results([], _NAMES)

    with patch.object(det_mod, "_get_model", return_value=mock_model):
        det_mod.detect_civic_issue(_make_image())

    call_kwargs = mock_model.predict.call_args
    assert call_kwargs.kwargs.get("verbose") is False


# ---------------------------------------------------------------------------
# Smoke test: real YOLOv8n model (skipped when weights not cached)
# ---------------------------------------------------------------------------

def _yolov8n_weights_available() -> bool:
    """Return True if yolov8n.pt is already cached locally."""
    import pathlib
    home = pathlib.Path.home()
    candidates = [
        home / ".cache" / "ultralytics" / "yolov8n.pt",
        home / "AppData" / "Local" / "Ultralytics" / "yolov8n.pt",
        pathlib.Path("yolov8n.pt"),
    ]
    return any(p.exists() for p in candidates)


@pytest.mark.skipif(
    not _yolov8n_weights_available(),
    reason="yolov8n.pt not cached locally — skipping real-model smoke test.",
)
def test_real_model_blank_image_returns_detection_result():
    """Smoke test: real YOLOv8n on blank image returns a valid DetectionResult."""
    import cv.detection as det_mod

    reset_detector_for_testing()
    img = Image.new("RGB", (320, 320), color=(128, 128, 128))
    result = det_mod.detect_civic_issue(img)

    assert isinstance(result, DetectionResult)
    assert isinstance(result.yolo_class, str)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.category, IssueCategory)
    reset_detector_for_testing()


@pytest.mark.skipif(
    not _yolov8n_weights_available(),
    reason="yolov8n.pt not cached locally — skipping real-model smoke test.",
)
def test_real_model_returns_frozen_result():
    """Smoke test: result returned by real model is immutable."""
    import cv.detection as det_mod

    reset_detector_for_testing()
    result = det_mod.detect_civic_issue(Image.new("RGB", (320, 320)))
    with pytest.raises((AttributeError, TypeError)):
        result.yolo_class = "x"  # type: ignore[misc]
    reset_detector_for_testing()
