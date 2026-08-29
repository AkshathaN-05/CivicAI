"""Image validation module — T2-2.

Validates uploaded report images before they enter the CV pipeline.
Checks MIME type, magic bytes, file size, minimum dimensions, then
re-encodes (strips EXIF metadata) and resizes to max 1024px longest side.

Per Part A §13, §28 and Part B AI/CV Implementation Plan.

Usage:
    from cv.image_validator import validate_image, ImageValidationError

    validated_bytes = validate_image(raw_bytes, claimed_mime_type)
    # Returns re-encoded JPEG bytes ready for CV inference / storage.
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (Part A §13, §28 and T2-2 spec)
# ---------------------------------------------------------------------------

#: Accepted MIME types (case-normalised).
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

#: Maximum accepted file size: 10 MB.
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

#: Minimum image dimension on both axes.
MIN_DIMENSION_PX: int = 200  # 200×200 px

#: Max longest-side dimension after resize (for CV inference memory).
MAX_SIDE_PX: int = 1024

#: Magic-byte signatures for each supported type.
#: (offset, bytes) — checked against the raw file header.
_MAGIC_BYTES: dict[str, Tuple[int, bytes]] = {
    "image/jpeg": (0, b"\xff\xd8\xff"),
    "image/png": (0, b"\x89\x50\x4e\x47"),
    "image/webp": (0, b"\x52\x49\x46\x46"),  # RIFF header
}

# WebP files have "WEBP" at offset 8 in addition to the RIFF header.
_WEBP_SECONDARY_MAGIC: Tuple[int, bytes] = (8, b"WEBP")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImageValidationError(ValueError):
    """Raised for any image that fails validation.

    The message describes the specific failure mode so callers can return
    a meaningful HTTP 422 response.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_image(
    raw_bytes: bytes,
    claimed_mime: str = "",
) -> bytes:
    """Validate *raw_bytes* as an image and return re-encoded JPEG bytes.

    Steps (in order):
    1. File-size check  — reject if > MAX_FILE_SIZE_BYTES.
    2. MIME check       — reject claimed_mime not in ALLOWED_MIME_TYPES (when
                          provided; the magic-bytes check is always authoritative).
    3. Magic-bytes check — reject bytes that don't match a known image header.
    4. Pillow open       — reject files Pillow cannot decode (corrupted, truncated).
    5. Dimensions check  — reject images smaller than MIN_DIMENSION_PX × MIN_DIMENSION_PX.
    6. Resize            — scale down to MAX_SIDE_PX longest side (LANCZOS).
    7. Re-encode         — save as JPEG quality=85, strips EXIF / metadata.

    Args:
        raw_bytes:    The raw bytes of the uploaded file.
        claimed_mime: The Content-Type header value supplied by the client.
                      Optional; used as an early rejection before magic-bytes.

    Returns:
        Re-encoded JPEG bytes (no EXIF, max 1024px longest side).

    Raises:
        ImageValidationError: For any of the failure modes described above.
    """
    # 1. File-size check.
    file_size = len(raw_bytes)
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ImageValidationError(
            f"File too large: {file_size} bytes exceeds maximum of "
            f"{MAX_FILE_SIZE_BYTES} bytes (10 MB)."
        )

    # 2. Claimed MIME check (advisory, but we reject clearly wrong types early).
    if claimed_mime:
        normalised = claimed_mime.lower().split(";")[0].strip()
        if normalised not in ALLOWED_MIME_TYPES:
            raise ImageValidationError(
                f"Unsupported MIME type '{claimed_mime}'. "
                f"Accepted types: {sorted(ALLOWED_MIME_TYPES)}."
            )

    # 3. Magic-bytes check (authoritative — cannot be spoofed via headers).
    _check_magic_bytes(raw_bytes)

    # 4. Pillow decode — catches corrupted / truncated files.
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.verify()  # Raise for truncated / corrupt files without full decode.
    except (UnidentifiedImageError, Exception) as exc:
        raise ImageValidationError(
            f"Image file could not be decoded: {exc}"
        ) from exc

    # Re-open after verify() (verify() exhausts the file object in Pillow).
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.load()  # Force full decode to catch late-stage corruption.
    except Exception as exc:
        raise ImageValidationError(
            f"Image file could not be fully decoded: {exc}"
        ) from exc

    # 5. Minimum dimensions check.
    width, height = img.size
    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        raise ImageValidationError(
            f"Image too small: {width}×{height} px. "
            f"Minimum required: {MIN_DIMENSION_PX}×{MIN_DIMENSION_PX} px."
        )

    # 6. Resize to max 1024px longest side (in-place thumbnail).
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX), Image.LANCZOS)

    # 7. Re-encode as JPEG, strips EXIF and any embedded metadata.
    #    Convert to RGB first (PNG/WebP may be RGBA or P mode).
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    output_buffer = io.BytesIO()
    img.save(output_buffer, format="JPEG", quality=85)
    result = output_buffer.getvalue()

    logger.debug(
        "validate_image: accepted %d bytes → %d bytes JPEG (%dx%d px).",
        file_size,
        len(result),
        img.width,
        img.height,
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_magic_bytes(raw_bytes: bytes) -> None:
    """Raise ImageValidationError if raw_bytes don't match any allowed magic."""
    for mime_type, (offset, magic) in _MAGIC_BYTES.items():
        if raw_bytes[offset : offset + len(magic)] == magic:
            # Extra WebP check: bytes 8-12 must be "WEBP".
            if mime_type == "image/webp":
                wb_offset, wb_magic = _WEBP_SECONDARY_MAGIC
                if raw_bytes[wb_offset : wb_offset + len(wb_magic)] != wb_magic:
                    continue  # RIFF but not WebP — keep checking.
            return  # Magic bytes match — accepted.

    raise ImageValidationError(
        "File does not match any supported image format. "
        "Expected JPEG (FF D8 FF), PNG (89 50 4E 47), or WebP (52 49 46 46 … WEBP)."
    )
