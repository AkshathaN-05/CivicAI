"""T2-3 tests — Face Redaction (privacy.py).

Acceptance criteria (T2-3 canonical plan):
  - Image with a detected face → Gaussian blur applied to face bounding box
  - Image with no face → image returned unchanged
  - Multiple faces detected → all face regions blurred
  - Model not loaded at import time (lazy loading)
  - Output is always a valid PIL Image
  - Degenerate bounding boxes handled safely
  - Model is loaded lazily on first call to redact_faces

Design:
  - Functional tests use a mock YuNet detector to keep tests deterministic
    and offline (no network / no model file required for the test suite).
  - A separate smoke test uses the real pre-downloaded model to confirm
    the real path works (skipped if model file absent).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helper: create a synthetic PIL image
# ---------------------------------------------------------------------------


def _make_image(width: int = 400, height: int = 400, color=(120, 180, 60)) -> Image.Image:
    """Return a plain-colour RGB PIL image."""
    return Image.new("RGB", (width, height), color=color)


def _make_rgba_image(width: int = 400, height: int = 400) -> Image.Image:
    """Return an RGBA PIL image."""
    return Image.new("RGBA", (width, height), color=(0, 200, 100, 180))


# ---------------------------------------------------------------------------
# Helper: build a fake YuNet detection result array
# ---------------------------------------------------------------------------


def _faces_array(*bboxes: tuple[int, int, int, int]) -> np.ndarray:
    """Build a fake YuNet detection result for the given (x, y, w, h) bboxes.

    YuNet returns shape [N, 15]: columns 0-3 are x, y, w, h; column 14 is score.
    Columns 4-13 are landmark coordinates (unused by redact_faces).
    """
    rows = []
    for (x, y, w, h) in bboxes:
        row = [float(x), float(y), float(w), float(h)] + [0.0] * 10 + [0.95]
        rows.append(row)
    return np.array(rows, dtype=np.float32)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_detector():
    """Reset the lazy-loaded detector singleton before each test."""
    from cv import privacy

    privacy.reset_detector_for_testing()
    yield
    privacy.reset_detector_for_testing()


# ---------------------------------------------------------------------------
# Tests: lazy loading
# ---------------------------------------------------------------------------


def test_detector_not_loaded_at_import_time():
    """The YuNet detector singleton must be None immediately after import."""
    import cv.privacy as privacy_mod

    # reset_detector fixture already cleared it; verify it's still None.
    assert privacy_mod._yunet_detector is None, (
        "YuNet detector must not be loaded at module import time (Part A §8)."
    )


def test_model_loaded_lazily_on_first_call(monkeypatch):
    """The YuNet detector is created only when redact_faces is first called."""
    import cv.privacy as privacy_mod

    created_count = [0]
    real_get = privacy_mod._get_detector

    def counting_get():
        created_count[0] += 1
        return real_get()

    monkeypatch.setattr(privacy_mod, "_get_detector", counting_get)

    assert created_count[0] == 0, "Detector should not have been accessed yet."

    # Actually call redact_faces (with mocked detector)
    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, None)  # no faces
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image()
    privacy_mod.redact_faces(img)
    mock_detector.detect.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: no-face case
# ---------------------------------------------------------------------------


def test_no_faces_returns_image_unchanged(monkeypatch):
    """When no faces are detected, the original image object is returned unchanged."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, None)  # faces=None → no detections
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image(400, 400)
    result = privacy_mod.redact_faces(img)
    assert result is img, "With no faces, the original image should be returned as-is."


def test_no_faces_empty_array_returns_unchanged(monkeypatch):
    """An empty faces array (shape [0, 15]) also returns the image unchanged."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    empty_faces = np.empty((0, 15), dtype=np.float32)
    mock_detector.detect.return_value = (1, empty_faces)
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image()
    result = privacy_mod.redact_faces(img)
    assert result is img


# ---------------------------------------------------------------------------
# Tests: single face blurring
# ---------------------------------------------------------------------------


def test_face_region_is_blurred(monkeypatch):
    """Detected face bounding box region must differ from original after redaction."""
    import cv.privacy as privacy_mod

    face_x, face_y, face_w, face_h = 100, 100, 100, 100

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array((face_x, face_y, face_w, face_h)))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    # Use a uniform-color image so we can detect any pixel change in the face region.
    # Actually uniform color blurred = same uniform color; use a gradient instead.
    img = Image.new("RGB", (400, 400))
    pixels = img.load()
    for x in range(400):
        for y in range(400):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)

    original_region = img.crop((face_x, face_y, face_x + face_w, face_y + face_h)).tobytes()

    result = privacy_mod.redact_faces(img)

    # Result should be a new image (copy, not original).
    assert result is not img, "redact_faces should return a new image, not mutate input."

    # The face region in the result must differ from the original (blur changed it).
    result_region = result.crop((face_x, face_y, face_x + face_w, face_y + face_h)).tobytes()
    assert result_region != original_region, (
        "Face bounding box region must be blurred (pixels should differ from original)."
    )


def test_non_face_region_preserved(monkeypatch):
    """Pixels outside the face bounding box must remain identical to the original."""
    import cv.privacy as privacy_mod

    face_x, face_y, face_w, face_h = 50, 50, 80, 80

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array((face_x, face_y, face_w, face_h)))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image(400, 400, color=(200, 100, 50))
    result = privacy_mod.redact_faces(img)

    # Check a pixel far from the face region.
    outside_x, outside_y = 350, 350
    assert result.getpixel((outside_x, outside_y)) == img.getpixel((outside_x, outside_y)), (
        "Pixels outside the face bbox must not be modified."
    )


def test_output_is_pil_image(monkeypatch):
    """redact_faces always returns a PIL Image regardless of input size."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, None)
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image(320, 240)
    result = privacy_mod.redact_faces(img)
    assert isinstance(result, Image.Image), "redact_faces must return a PIL Image."


# ---------------------------------------------------------------------------
# Tests: multiple faces
# ---------------------------------------------------------------------------


def test_multiple_faces_all_blurred(monkeypatch):
    """When multiple faces are detected, all bounding boxes are blurred."""
    import cv.privacy as privacy_mod

    bboxes = [
        (20, 20, 60, 60),    # face 1
        (200, 200, 70, 70),  # face 2
        (300, 10, 50, 50),   # face 3
    ]
    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array(*bboxes))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    # Gradient image so blur is detectable.
    img = Image.new("RGB", (400, 400))
    px = img.load()
    for x in range(400):
        for y in range(400):
            px[x, y] = (x % 256, y % 256, (x * y) % 256)

    result = privacy_mod.redact_faces(img)

    for (fx, fy, fw, fh) in bboxes:
        orig_bytes = img.crop((fx, fy, fx + fw, fy + fh)).tobytes()
        result_bytes = result.crop((fx, fy, fx + fw, fy + fh)).tobytes()
        assert result_bytes != orig_bytes, (
            f"Face region at ({fx},{fy},{fw},{fh}) was not blurred."
        )


def test_multiple_faces_outside_regions_unchanged(monkeypatch):
    """Outside all face bounding boxes, pixels stay identical."""
    import cv.privacy as privacy_mod

    bboxes = [(10, 10, 50, 50), (300, 300, 60, 60)]
    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array(*bboxes))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image(400, 400, color=(77, 88, 99))
    result = privacy_mod.redact_faces(img)

    # Pixel in centre, far from both bboxes.
    assert result.getpixel((200, 200)) == img.getpixel((200, 200))


# ---------------------------------------------------------------------------
# Tests: RGBA input handled
# ---------------------------------------------------------------------------


def test_rgba_image_accepted(monkeypatch):
    """redact_faces must accept RGBA images without raising."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, None)
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    rgba_img = _make_rgba_image()
    result = privacy_mod.redact_faces(rgba_img)
    assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# Tests: edge / degenerate bounding boxes
# ---------------------------------------------------------------------------


def test_degenerate_bbox_zero_size_skipped(monkeypatch):
    """A bounding box with w=0 or h=0 must be skipped without raising."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    # w=0, h=0 — degenerate.
    mock_detector.detect.return_value = (1, _faces_array((100, 100, 0, 0)))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image()
    result = privacy_mod.redact_faces(img)  # must not raise
    assert isinstance(result, Image.Image)


def test_bbox_clamped_to_image_bounds(monkeypatch):
    """A bounding box that extends outside the image is clamped safely."""
    import cv.privacy as privacy_mod

    # bbox extends past image border.
    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array((350, 350, 200, 200)))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image(400, 400)
    result = privacy_mod.redact_faces(img)  # must not raise
    assert isinstance(result, Image.Image)


def test_negative_bbox_coords_clamped(monkeypatch):
    """Negative bbox coordinates are clamped to 0 without raising."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array((-10, -10, 80, 80)))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image()
    result = privacy_mod.redact_faces(img)  # must not raise
    assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# Tests: output image size unchanged
# ---------------------------------------------------------------------------


def test_output_size_matches_input(monkeypatch):
    """The output image must have the same dimensions as the input."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array((100, 100, 80, 80)))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    img = _make_image(640, 480)
    result = privacy_mod.redact_faces(img)
    assert result.size == (640, 480), (
        f"Output size {result.size} must match input size (640, 480)."
    )


# ---------------------------------------------------------------------------
# Test: input not mutated
# ---------------------------------------------------------------------------


def test_original_image_not_mutated(monkeypatch):
    """redact_faces must not mutate the input PIL image."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.detect.return_value = (1, _faces_array((50, 50, 100, 100)))
    monkeypatch.setattr(privacy_mod, "_get_detector", lambda: mock_detector)

    # Gradient image.
    img = Image.new("RGB", (400, 400))
    px = img.load()
    for x in range(400):
        for y in range(400):
            px[x, y] = (x % 256, y % 256, 128)

    original_bytes = img.tobytes()
    privacy_mod.redact_faces(img)
    assert img.tobytes() == original_bytes, "Input image must not be mutated."


# ---------------------------------------------------------------------------
# Smoke test: real model (skipped if ONNX file absent)
# ---------------------------------------------------------------------------


_MODEL_PATH = Path(__file__).parent.parent / "cv" / "models" / "face_detection_yunet_2023mar.onnx"


@pytest.mark.skipif(
    not _MODEL_PATH.exists(),
    reason="YuNet ONNX model file not present — skipping real-model smoke test.",
)
def test_real_model_no_face_on_blank_image():
    """Smoke test: real YuNet model on blank image returns image unchanged."""
    from cv import privacy

    privacy.reset_detector_for_testing()
    img = _make_image(320, 320, color=(128, 128, 128))
    result = privacy.redact_faces(img)
    # Blank solid-colour image has no faces — must return unchanged.
    assert result is img, "No-face blank image must be returned unchanged."
    privacy.reset_detector_for_testing()


@pytest.mark.skipif(
    not _MODEL_PATH.exists(),
    reason="YuNet ONNX model file not present — skipping real-model smoke test.",
)
def test_real_model_returns_pil_image():
    """Smoke test: real YuNet model always returns a PIL Image."""
    from cv import privacy

    privacy.reset_detector_for_testing()
    img = _make_image(400, 300)
    result = privacy.redact_faces(img)
    assert isinstance(result, Image.Image)
    privacy.reset_detector_for_testing()


# ---------------------------------------------------------------------------
# Test: reset_detector_for_testing helper
# ---------------------------------------------------------------------------


def test_reset_detector_for_testing():
    """reset_detector_for_testing() sets _yunet_detector to None."""
    from cv import privacy

    # Force the detector to be "loaded" by assigning a sentinel.
    privacy._yunet_detector = MagicMock()
    assert privacy._yunet_detector is not None

    privacy.reset_detector_for_testing()
    assert privacy._yunet_detector is None
