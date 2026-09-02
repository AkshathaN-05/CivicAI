"""Privacy redaction module — T2-3 (face detection) + T2-4 (licence-plate redaction).

T2-3: `redact_faces(image: PIL.Image) -> PIL.Image`
    Uses YuNet ONNX face detection (cv2.FaceDetectorYN) with lazy loading.
    Applies Gaussian blur (radius=20) to each detected face bounding box.
    Returns original image unchanged when no faces detected.

T2-4: `redact_plates(image: PIL.Image) -> PIL.Image`
    Uses open-image-models YOLOv9 licence-plate detector (via fast-alpr) with
    lazy loading.  Applies a solid black rectangle over each detected plate
    bounding box (Gaussian blur, radius=20).  Returns original image
    unchanged when no plates detected.

Combined pipeline helper:
    `redact_privacy(image)` => redact_faces => redact_plates => return

Per Part A §8 (lazy loading), §14 (redaction before storage), T2-3 and T2-4 spec.

Usage:
    from cv.privacy import redact_faces, redact_plates, redact_privacy

    redacted = redact_privacy(pil_image)
    # Returns PIL.Image with all faces blurred and all plates blacked out.

Notes:
    - YuNet ONNX: backend/cv/models/face_detection_yunet_2023mar.onnx
      Auto-downloaded on first call if absent.
    - Plate detector: open-image-models YOLOv9 model cached in
      ~/.cache/open-image-models/ -- auto-downloaded on first call if absent.
    - Neither model is loaded at module import time (Part A §8).
"""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration (T2-3, Part A §8)
# ---------------------------------------------------------------------------

#: Directory that contains ONNX model files.
_MODELS_DIR: Path = Path(__file__).parent / "models"

#: YuNet ONNX model filename.
_YUNET_FILENAME: str = "face_detection_yunet_2023mar.onnx"

#: Remote URL — used to auto-download on first call if file is missing.
_YUNET_URL: str = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)

# Detection thresholds (OpenCV defaults are conservative; these are tuned
# for typical civic-photo resolution images).
_SCORE_THRESHOLD: float = 0.6
_NMS_THRESHOLD: float = 0.3
_TOP_K: int = 5000

# Default input size used when instantiating the detector; `setInputSize` is
# called per-image so this is just an initialisation value.
_DEFAULT_INPUT_SIZE: tuple[int, int] = (320, 320)

# ---------------------------------------------------------------------------
# Lazy-loaded singleton — not created at import time (Part A §8)
# ---------------------------------------------------------------------------

_yunet_detector: Optional[cv2.FaceDetectorYN] = None

# ---------------------------------------------------------------------------
# T2-4 — Plate detector lazy singleton
# ---------------------------------------------------------------------------

#: Plate model name (smallest YOLOv9 end-to-end plate model).
_PLATE_MODEL_NAME: str = "yolo-v9-t-256-license-plate-end2end"

#: Plate detector singleton — None until first call to redact_plates.
_plate_detector: Optional[object] = None  # open_image_models ObjectDetector


# ---------------------------------------------------------------------------
# Internal helpers (T2-3)
# ---------------------------------------------------------------------------


def _get_model_path() -> Path:
    """Return the local path to the YuNet ONNX file, downloading if absent."""
    model_path = _MODELS_DIR / _YUNET_FILENAME
    if not model_path.exists():
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "YuNet ONNX model not found at %s — downloading from %s …",
            model_path,
            _YUNET_URL,
        )
        urllib.request.urlretrieve(_YUNET_URL, str(model_path))
        logger.info(
            "YuNet ONNX model downloaded: %d bytes.", model_path.stat().st_size
        )
    return model_path


def _get_detector() -> cv2.FaceDetectorYN:
    """Return the module-level YuNet detector, creating it on first call.

    This is the lazy-loading entry point required by Part A §8.  The detector
    is NOT created at module import time — it is only instantiated when
    `redact_faces` is first called.
    """
    global _yunet_detector
    if _yunet_detector is None:
        model_path = _get_model_path()
        _yunet_detector = cv2.FaceDetectorYN.create(
            str(model_path),
            "",
            _DEFAULT_INPUT_SIZE,
            score_threshold=_SCORE_THRESHOLD,
            nms_threshold=_NMS_THRESHOLD,
            top_k=_TOP_K,
        )
        logger.info("YuNet face detector loaded from %s.", model_path)
    return _yunet_detector


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact_faces(image: Image.Image) -> Image.Image:
    """Detect all human faces and apply Gaussian blur to each bounding box.

    Args:
        image: A PIL Image (any mode; will be converted to RGB for detection).

    Returns:
        A new PIL Image with detected face regions blurred (radius=20).
        If no faces are detected the original *image* object is returned
        unchanged.

    Notes:
        - The YuNet ONNX detector is loaded lazily on first call.
        - Multiple faces in the same image are all blurred.
        - The original face pixels are never stored or returned.
    """
    detector = _get_detector()

    # Convert to RGB numpy array for OpenCV (YuNet expects BGR; we convert below).
    img_rgb = image.convert("RGB")
    img_np = np.array(img_rgb)  # shape: (H, W, 3), dtype uint8, RGB

    height, width = img_np.shape[:2]

    # YuNet requires setting the input size to match the actual image resolution.
    detector.setInputSize((width, height))

    # OpenCV uses BGR; convert from RGB.
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    # Run detection.  Returns (retval, faces) where faces is None or (N, 15).
    _status, faces = detector.detect(img_bgr)

    if faces is None or len(faces) == 0:
        # No faces detected — return image unchanged (Part A §14 / T2-3 spec).
        logger.debug("redact_faces: no faces detected — image unchanged.")
        return image

    logger.debug("redact_faces: %d face(s) detected — applying blur.", len(faces))

    # Work on a copy so the input is not mutated.
    output = img_rgb.copy()

    for face in faces:
        # YuNet bbox: [x1, y1, w, h, ...landmarks..., score]
        x1 = int(face[0])
        y1 = int(face[1])
        w = int(face[2])
        h = int(face[3])

        # Clamp to image bounds.
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(width, x1 + w)
        y2 = min(height, y1 + h)

        if x2 <= x1 or y2 <= y1:
            # Degenerate bounding box — skip.
            continue

        # Crop the face region, blur it, paste back.
        face_crop = output.crop((x1, y1, x2, y2))
        blurred_crop = face_crop.filter(ImageFilter.GaussianBlur(radius=20))
        output.paste(blurred_crop, (x1, y1))

    return output


def reset_detector_for_testing() -> None:
    """Reset the lazy-loaded YuNet detector singleton.

    Intended for use in tests only.
    """
    global _yunet_detector
    _yunet_detector = None


# ---------------------------------------------------------------------------
# T2-4 — Plate detector lazy loader
# ---------------------------------------------------------------------------


def _get_plate_detector():
    """Return the module-level plate detector, creating it on first call.

    Lazy-loaded per Part A §8.  The detector is NOT created at import time.
    Uses open-image-models YOLOv9 licence-plate detector with
    CPUExecutionProvider to avoid Azure execution provider blocking.
    """
    global _plate_detector
    if _plate_detector is None:
        from open_image_models import create_detector  # deferred import

        _plate_detector = create_detector(
            _PLATE_MODEL_NAME,
            providers=["CPUExecutionProvider"],
        )
        logger.info("Licence-plate detector loaded (model: %s).", _PLATE_MODEL_NAME)
    return _plate_detector


# ---------------------------------------------------------------------------
# T2-4 — Public API
# ---------------------------------------------------------------------------


def redact_plates(image: Image.Image) -> Image.Image:
    """Detect all licence plates and apply Gaussian blur to each bounding box.

    Args:
        image: A PIL Image (any mode; converted to RGB for detection).

    Returns:
        A new PIL Image with detected plate regions blurred (radius=20).
        If no plates are detected the original *image* object is returned
        unchanged.

    Notes:
        - The plate detector is loaded lazily on first call (Part A §8).
        - Multiple plates are all redacted.
        - Bounding boxes are clamped to image bounds before drawing.
        - The original image is never mutated.
        - OCR is deliberately NOT performed (T2-4 non-goal).
    """
    detector = _get_plate_detector()

    # Convert to RGB and then BGR numpy array (detector expects BGR).
    img_rgb = image.convert("RGB")
    img_np = np.array(img_rgb)  # (H, W, 3), dtype uint8, RGB
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    height, width = img_bgr.shape[:2]

    # Run detection — returns list[DetectionResult] with .bounding_box (x1,y1,x2,y2).
    detections = detector.predict(img_bgr)

    if not detections:
        # No plates detected — return image unchanged (T2-4 spec).
        logger.debug("redact_plates: no plates detected — image unchanged.")
        return image

    logger.debug(
        "redact_plates: %d plate(s) detected — applying Gaussian blur.",
        len(detections),
    )

    # Work on a copy so the input is not mutated.
    output = img_rgb.copy()

    for det in detections:
        bbox = det.bounding_box  # BoundingBox(x1, y1, x2, y2)

        # Clamp to image bounds.
        x1 = max(0, int(bbox.x1))
        y1 = max(0, int(bbox.y1))
        x2 = min(width, int(bbox.x2))
        y2 = min(height, int(bbox.y2))

        if x2 <= x1 or y2 <= y1:
            # Degenerate bounding box — skip.
            continue

        # Crop the plate region, blur it, paste back.
        plate_crop = output.crop((x1, y1, x2, y2))
        blurred_crop = plate_crop.filter(ImageFilter.GaussianBlur(radius=20))
        output.paste(blurred_crop, (x1, y1))

    return output


def reset_plate_detector_for_testing() -> None:
    """Reset the lazy-loaded plate detector singleton.

    Intended for use in tests only.
    """
    global _plate_detector
    _plate_detector = None


# ---------------------------------------------------------------------------
# Combined privacy pipeline (T2-3 + T2-4)
# ---------------------------------------------------------------------------


def redact_privacy(image: Image.Image) -> Image.Image:
    """Run the full privacy redaction pipeline: faces then plates.

    Per the plan (Part B): redact_faces -> redact_plates -> return.

    Args:
        image: Input PIL Image.

    Returns:
        PIL Image with all detected faces blurred and all detected plates
        blurred.
    """
    img = redact_faces(image)
    img = redact_plates(img)
    return img
