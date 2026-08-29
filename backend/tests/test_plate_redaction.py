"""T2-4 tests — Licence Plate Redaction (privacy.py: redact_plates).

Acceptance criteria (T2-4 canonical plan):
  - Image with a detected plate → solid black rectangle applied to plate bbox
  - Image with no plate → image returned unchanged
  - Multiple plates → all plate regions blacked out
  - Model not loaded at import time (lazy loading)
  - Output is always a valid PIL Image
  - Bounding boxes partially/fully outside image bounds are handled safely
  - Input image is not mutated
  - Output size matches input size
  - Non-plate regions are preserved
  - No OCR is performed (T2-4 non-goal — redaction only)
  - redact_privacy() calls redact_faces then redact_plates

Design:
  - All functional tests use a mock detector (deterministic, offline, fast).
  - Two smoke tests use the real pre-cached open-image-models model
    (skipped if model file absent — does not depend on network at test time).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers — fake detection result matching open-image-models API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeBoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class _FakeDetectionResult:
    bounding_box: _FakeBoundingBox
    label: str = "license-plate"
    confidence: float = 0.9


def _fake_detection(x1: int, y1: int, x2: int, y2: int) -> _FakeDetectionResult:
    """Return a minimal fake DetectionResult (xyxy format)."""
    return _FakeDetectionResult(bounding_box=_FakeBoundingBox(x1, y1, x2, y2))


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def _make_image(width: int = 400, height: int = 400, color=(120, 180, 60)) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


def _make_rgba_image(width: int = 400, height: int = 400) -> Image.Image:
    return Image.new("RGBA", (width, height), color=(0, 200, 100, 180))


def _make_gradient_image(width: int = 400, height: int = 400) -> Image.Image:
    """Return a gradient image so that rectangle fill is detectable."""
    img = Image.new("RGB", (width, height))
    px = img.load()
    for x in range(width):
        for y in range(height):
            px[x, y] = (x % 256, y % 256, (x + y) % 256)
    return img


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_plate_singleton():
    """Reset the plate detector singleton before and after each test."""
    from cv import privacy

    privacy.reset_plate_detector_for_testing()
    yield
    privacy.reset_plate_detector_for_testing()


# ---------------------------------------------------------------------------
# Tests: lazy loading
# ---------------------------------------------------------------------------


def test_plate_detector_not_loaded_at_import_time():
    """The plate detector singleton must be None at module import time."""
    import cv.privacy as privacy_mod

    assert privacy_mod._plate_detector is None, (
        "Plate detector must not be loaded at import time (Part A §8)."
    )


def test_plate_detector_loaded_lazily_on_first_call(monkeypatch):
    """The plate detector is only instantiated when redact_plates is first called."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = []  # no plates

    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    assert privacy_mod._plate_detector is None
    img = _make_image()
    privacy_mod.redact_plates(img)
    mock_detector.predict.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: no-plate case
# ---------------------------------------------------------------------------


def test_no_plates_returns_image_unchanged(monkeypatch):
    """When no plates are detected the original image is returned as-is."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = []
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_image(400, 400)
    result = privacy_mod.redact_plates(img)
    assert result is img, "No-plates image must be returned unchanged."


# ---------------------------------------------------------------------------
# Tests: single plate redaction
# ---------------------------------------------------------------------------


def test_plate_region_is_black(monkeypatch):
    """Detected plate bounding box must be filled with black (0, 0, 0)."""
    import cv.privacy as privacy_mod

    px1, py1, px2, py2 = 100, 150, 200, 180  # plate bbox

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(px1, py1, px2, py2)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_gradient_image(400, 400)
    result = privacy_mod.redact_plates(img)

    # Every pixel inside the plate bbox must be black.
    for x in range(px1, px2, 5):  # sample every 5 pixels
        for y in range(py1, py2, 5):
            pixel = result.getpixel((x, y))
            assert pixel == (0, 0, 0), (
                f"Plate pixel at ({x},{y}) should be black (0,0,0), got {pixel}."
            )


def test_plate_region_differs_from_original(monkeypatch):
    """The plate region in output must differ from the input (gradient) region."""
    import cv.privacy as privacy_mod

    px1, py1, px2, py2 = 50, 60, 150, 90

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(px1, py1, px2, py2)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_gradient_image(400, 400)
    original_region = img.crop((px1, py1, px2, py2)).tobytes()
    result = privacy_mod.redact_plates(img)
    result_region = result.crop((px1, py1, px2, py2)).tobytes()

    assert result_region != original_region, "Plate region must be modified (blacked out)."


def test_non_plate_region_preserved(monkeypatch):
    """Pixels outside the plate bbox must remain unchanged."""
    import cv.privacy as privacy_mod

    px1, py1, px2, py2 = 50, 50, 150, 100

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(px1, py1, px2, py2)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_image(400, 400, color=(200, 100, 50))
    result = privacy_mod.redact_plates(img)

    # Check a pixel well outside the plate bbox.
    assert result.getpixel((350, 350)) == img.getpixel((350, 350)), (
        "Pixels outside plate bbox must not be modified."
    )


def test_output_is_pil_image(monkeypatch):
    """redact_plates always returns a PIL Image."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = []
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_plates(_make_image(320, 240))
    assert isinstance(result, Image.Image)


def test_output_is_new_object_when_plates_detected(monkeypatch):
    """When plates are detected, a new image object is returned (input not reused)."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(10, 10, 80, 40)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_image(400, 400)
    result = privacy_mod.redact_plates(img)
    assert result is not img, "redact_plates must return a new image when plates found."


# ---------------------------------------------------------------------------
# Tests: multiple plates
# ---------------------------------------------------------------------------


def test_multiple_plates_all_blacked_out(monkeypatch):
    """All detected plate bboxes must be filled with black."""
    import cv.privacy as privacy_mod

    plates = [
        (20, 30, 100, 60),
        (200, 150, 300, 180),
        (310, 10, 380, 40),
    ]

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(*p) for p in plates]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_gradient_image(400, 400)
    result = privacy_mod.redact_plates(img)

    for (px1, py1, px2, py2) in plates:
        centre_x = (px1 + px2) // 2
        centre_y = (py1 + py2) // 2
        pixel = result.getpixel((centre_x, centre_y))
        assert pixel == (0, 0, 0), (
            f"Centre of plate bbox ({px1},{py1},{px2},{py2}) at ({centre_x},{centre_y}) "
            f"should be black, got {pixel}."
        )


def test_multiple_plates_outside_regions_unchanged(monkeypatch):
    """Pixels outside all plate bboxes must be unchanged."""
    import cv.privacy as privacy_mod

    plates = [(10, 10, 60, 40), (300, 300, 370, 330)]
    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(*p) for p in plates]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_image(400, 400, color=(77, 88, 99))
    result = privacy_mod.redact_plates(img)

    assert result.getpixel((200, 200)) == img.getpixel((200, 200))


# ---------------------------------------------------------------------------
# Tests: RGBA input
# ---------------------------------------------------------------------------


def test_rgba_image_accepted(monkeypatch):
    """redact_plates must accept RGBA images without raising."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = []
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_plates(_make_rgba_image())
    assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# Tests: boundary / degenerate bounding boxes
# ---------------------------------------------------------------------------


def test_degenerate_bbox_zero_width_skipped(monkeypatch):
    """A bbox where x1==x2 (zero width) must be skipped without raising."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(100, 100, 100, 140)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_plates(_make_image())
    assert isinstance(result, Image.Image)


def test_degenerate_bbox_zero_height_skipped(monkeypatch):
    """A bbox where y1==y2 (zero height) must be skipped without raising."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(100, 100, 180, 100)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_plates(_make_image())
    assert isinstance(result, Image.Image)


def test_bbox_extending_beyond_right_edge_clamped(monkeypatch):
    """A bbox extending past the right/bottom edge is clamped safely."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(350, 350, 600, 600)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_plates(_make_image(400, 400))
    assert isinstance(result, Image.Image)


def test_negative_bbox_coords_clamped(monkeypatch):
    """Negative bbox coordinates are clamped to 0 without raising."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(-50, -50, 80, 40)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_plates(_make_image())
    assert isinstance(result, Image.Image)


def test_fully_outside_bbox_skipped(monkeypatch):
    """A bbox entirely outside the image produces no crash (clamped to empty)."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    # bbox completely outside a 400x400 image
    mock_detector.predict.return_value = [_fake_detection(500, 500, 700, 600)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_plates(_make_image(400, 400))
    assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# Tests: output size and input immutability
# ---------------------------------------------------------------------------


def test_output_size_matches_input(monkeypatch):
    """The output image dimensions must match the input."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(100, 100, 200, 130)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_image(640, 480)
    result = privacy_mod.redact_plates(img)
    assert result.size == (640, 480)


def test_original_image_not_mutated(monkeypatch):
    """redact_plates must not modify the input PIL image's pixels."""
    import cv.privacy as privacy_mod

    mock_detector = MagicMock()
    mock_detector.predict.return_value = [_fake_detection(50, 50, 150, 90)]
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    img = _make_gradient_image(400, 400)
    original_bytes = img.tobytes()
    privacy_mod.redact_plates(img)
    assert img.tobytes() == original_bytes, "Input image must not be mutated."


# ---------------------------------------------------------------------------
# Tests: reset_plate_detector_for_testing
# ---------------------------------------------------------------------------


def test_reset_plate_detector_for_testing():
    """reset_plate_detector_for_testing() sets _plate_detector to None."""
    from cv import privacy
    from unittest.mock import MagicMock

    privacy._plate_detector = MagicMock()
    assert privacy._plate_detector is not None
    privacy.reset_plate_detector_for_testing()
    assert privacy._plate_detector is None


# ---------------------------------------------------------------------------
# Tests: redact_privacy() combined pipeline
# ---------------------------------------------------------------------------


def test_redact_privacy_calls_both(monkeypatch):
    """redact_privacy() must call both redact_faces and redact_plates."""
    import cv.privacy as privacy_mod

    called = {"faces": False, "plates": False}
    sentinel = object()

    def fake_redact_faces(img):
        called["faces"] = True
        return img

    def fake_redact_plates(img):
        called["plates"] = True
        return img

    monkeypatch.setattr(privacy_mod, "redact_faces", fake_redact_faces)
    monkeypatch.setattr(privacy_mod, "redact_plates", fake_redact_plates)

    result = privacy_mod.redact_privacy(_make_image())
    assert called["faces"], "redact_privacy must call redact_faces."
    assert called["plates"], "redact_privacy must call redact_plates."


def test_redact_privacy_returns_pil_image(monkeypatch):
    """redact_privacy() must return a PIL Image."""
    import cv.privacy as privacy_mod

    monkeypatch.setattr(privacy_mod, "redact_faces", lambda img: img)

    mock_detector = MagicMock()
    mock_detector.predict.return_value = []
    monkeypatch.setattr(privacy_mod, "_get_plate_detector", lambda: mock_detector)

    result = privacy_mod.redact_privacy(_make_image())
    assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# Smoke tests: real model (skipped if model file absent)
# ---------------------------------------------------------------------------

_CACHE_DIR = Path.home() / ".cache" / "open-image-models"


def _real_model_available() -> bool:
    """Check if any plate detection ONNX file is cached locally."""
    if not _CACHE_DIR.exists():
        return False
    return any(_CACHE_DIR.rglob("*license-plate*.onnx"))


@pytest.mark.skipif(
    not _real_model_available(),
    reason="open-image-models cache not present — skipping real-model smoke test.",
)
def test_real_model_no_plate_on_blank_image():
    """Smoke test: real plate detector on blank image returns image unchanged."""
    from cv import privacy

    privacy.reset_plate_detector_for_testing()
    img = _make_image(320, 320)
    result = privacy.redact_plates(img)
    assert result is img, "Blank image with no plates must be returned unchanged."
    privacy.reset_plate_detector_for_testing()


@pytest.mark.skipif(
    not _real_model_available(),
    reason="open-image-models cache not present — skipping real-model smoke test.",
)
def test_real_model_returns_pil_image():
    """Smoke test: real plate detector always returns a PIL Image."""
    from cv import privacy

    privacy.reset_plate_detector_for_testing()
    result = privacy.redact_plates(_make_image(400, 300))
    assert isinstance(result, Image.Image)
    privacy.reset_plate_detector_for_testing()
