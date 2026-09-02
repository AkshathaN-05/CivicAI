"""AI pipeline orchestrator — T2-11.

Integrates all CV + LLM steps per the AI Flow in Part A §23 into a single
async function: ``run_ai_pipeline(image_bytes, location)``.

AI Flow (Part A §23, LOCKED):
    1. Validate image (T2-2)
    2. Redact faces (T2-3) + redact plates (T2-4)
    3. Compute BLAKE3 hash (T2-7) — of validated (pre-redaction) bytes
    4. Duplicate check (T2-7) — advisory flag only; never blocks submission
    5. YOLO detection (T2-5) → top-1 class + confidence
    6. Taxonomy map (T2-5) → IssueCategory
    7. Confidence score (T2-6) → evidence confidence
    8. Authority routing (ADR-001) → authority recommendation
    9. LLM (T2-10):
       - if YOLO confidence < 0.5 → classify_category first
       - always → generate_complaint_description
    10. Return AIResult

Public API:

    class AIResult(dataclass)
    async def run_ai_pipeline(
        image_bytes: bytes,
        location: str = "",
        address: str = "",
        claimed_mime: str = "",
        existing_hashes: list[str] | None = None,
    ) -> AIResult

Non-goals (Part A T2-11):
- Do NOT store images or DB records — that is the service layer.
- Do NOT implement RAG (T2-12/T2-13).

Failure handling:
- ImageValidationError → propagated (image is genuinely invalid)
- Any other step failure → graceful partial result (category=other, confidence=0)
- Memory cleanup: gc.collect() after heavy inference steps

LOCKED decisions:
- Part A §8  — lazy model loading; memory cleanup
- Part A §23 — AI flow sequence
- Part A §29 — performance: memory within 400 MB after pipeline
"""
from __future__ import annotations

import gc
import io
import logging
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

from cv.image_validator import ImageValidationError, validate_image
from cv.confidence import compute_confidence
from cv.taxonomy import map_to_category
from schemas.report import IssueCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AIResult schema
# ---------------------------------------------------------------------------

@dataclass
class AIResult:
    """Complete result of the AI pipeline.

    All fields are always present.  Downstream callers must not invent
    defaults — every field is explicitly set by run_ai_pipeline.

    Attributes:
        redacted_image_bytes:  JPEG bytes with faces + plates redacted.
                               Equal to validated_image_bytes when redaction
                               modules are unavailable or produce no changes.
        validated_image_bytes: JPEG bytes after T2-2 validation/re-encoding.
        category:              Civic IssueCategory (T2-5 + optional T2-10 LLM).
        confidence:            Evidence confidence score [0.0, 1.0] (T2-6).
        authority_recommendation: Short name of recommended authority (ADR-001).
        authority_id:          ID of recommended authority (or empty string).
        description:           LLM-generated complaint description (T2-10).
        image_hash:            BLAKE3 hex digest of validated image bytes (T2-7).
        is_duplicate:          True when a hash-match duplicate is found (T2-7).
        duplicate_report_id:   ID of the duplicate report, or None (T2-7).
        llm_provider_used:     "groq", "fallback", or "none".
        yolo_class:            Top-1 YOLO class name (empty string if none).
        raw_detection_confidence: Raw YOLOv8n confidence before weighting.
        match_reason:          Human-readable authority match reason.
    """

    redacted_image_bytes: bytes
    validated_image_bytes: bytes
    category: IssueCategory
    confidence: float
    authority_recommendation: str
    authority_id: str
    description: str
    image_hash: str
    is_duplicate: bool
    duplicate_report_id: Optional[str]
    llm_provider_used: str
    yolo_class: str
    raw_detection_confidence: float
    match_reason: str = field(default="")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pil_to_jpeg_bytes(image: Image.Image) -> bytes:
    """Convert a PIL Image to JPEG bytes."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _compute_hash(image_bytes: bytes) -> str:
    """Compute BLAKE3 hex digest of image bytes (T2-7)."""
    import blake3  # deferred import — available from requirements.txt
    return blake3.blake3(image_bytes).hexdigest()


def _check_duplicate(
    image_hash: str,
    existing_hashes: Optional[list[str]],
) -> tuple[bool, Optional[str]]:
    """Advisory duplicate check against known hashes (T2-7).

    The architecture specifies a ST_DWithin + hash check against the DB.
    At this layer (pipeline) we only check hashes supplied by the caller
    (the service layer owns DB queries).  Geo-proximity check is the
    service layer's responsibility.

    Args:
        image_hash:      BLAKE3 hex digest of the current image.
        existing_hashes: List of (hash, report_id) tuples from the DB, or
                         None/[] if no lookup was provided.

    Returns:
        (is_duplicate, duplicate_report_id)
    """
    if not existing_hashes:
        return False, None

    for entry in existing_hashes:
        # Accept either a plain hash string or a (hash, report_id) tuple/list.
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            known_hash, report_id = entry[0], entry[1]
        else:
            known_hash = str(entry)
            report_id = None
        if known_hash == image_hash:
            return True, str(report_id) if report_id else None

    return False, None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_ai_pipeline(
    image_bytes: bytes,
    location: str = "",
    address: str = "",
    claimed_mime: str = "",
    existing_hashes: Optional[list] = None,
) -> AIResult:
    """Run the full CivicAI AI pipeline on raw image bytes.

    Steps follow Part A §23 AI Flow exactly.  See module docstring.

    Args:
        image_bytes:     Raw bytes of the uploaded image.
        location:        Coordinates or location string ("lat,lng" or description).
        address:         Human-readable address / area_text for prompts.
        claimed_mime:    Client-provided Content-Type (advisory, magic-bytes authoritative).
        existing_hashes: Optional list of known hashes (or (hash, id) tuples) from
                         the caller for duplicate detection.  The full geo+hash DB
                         query is the service layer's responsibility.

    Returns:
        :class:`AIResult` with all fields populated.

    Raises:
        :class:`~cv.image_validator.ImageValidationError`:
            When the image fails T2-2 validation.  All other step failures
            are caught and produce graceful partial results.
    """
    effective_address = address or location or "Mangaluru"

    # -----------------------------------------------------------------------
    # Step 1: Image validation (T2-2) — raises ImageValidationError on failure
    # -----------------------------------------------------------------------
    validated_bytes: bytes = validate_image(image_bytes, claimed_mime)
    logger.debug("pipeline: step 1 (validate) — %d bytes → %d bytes JPEG",
                 len(image_bytes), len(validated_bytes))

    # -----------------------------------------------------------------------
    # Step 2: Privacy redaction — faces (T2-3) + plates (T2-4)
    # -----------------------------------------------------------------------
    redacted_bytes: bytes = validated_bytes
    try:
        from cv.privacy import redact_privacy

        pil_validated = Image.open(io.BytesIO(validated_bytes)).convert("RGB")
        pil_redacted = redact_privacy(pil_validated)
        redacted_bytes = _pil_to_jpeg_bytes(pil_redacted)
        del pil_validated, pil_redacted
        gc.collect()
        logger.debug("pipeline: step 2 (redact) — %d bytes JPEG", len(redacted_bytes))
    except Exception as exc:
        logger.warning("pipeline: step 2 (redact) failed — skipping: %s", exc)

    # -----------------------------------------------------------------------
    # Step 3: BLAKE3 hash of validated (pre-redaction) bytes (T2-7)
    # -----------------------------------------------------------------------
    image_hash: str = ""
    try:
        image_hash = _compute_hash(validated_bytes)
        logger.debug("pipeline: step 3 (hash) — %s", image_hash[:16])
    except Exception as exc:
        logger.warning("pipeline: step 3 (hash) failed: %s", exc)

    # -----------------------------------------------------------------------
    # Step 4: Duplicate check (T2-7) — advisory only
    # -----------------------------------------------------------------------
    is_duplicate, duplicate_report_id = _check_duplicate(image_hash, existing_hashes)
    logger.debug("pipeline: step 4 (duplicate) — is_duplicate=%s", is_duplicate)

    # -----------------------------------------------------------------------
    # Step 5 + 6: YOLO detection (T2-5) + taxonomy mapping
    # -----------------------------------------------------------------------
    yolo_class: str = ""
    raw_detection_confidence: float = 0.0
    category: IssueCategory = IssueCategory.other

    try:
        from cv.detection import detect_civic_issue

        pil_for_yolo = Image.open(io.BytesIO(validated_bytes))
        detection = detect_civic_issue(pil_for_yolo)
        yolo_class = detection.yolo_class
        raw_detection_confidence = detection.confidence
        category = detection.category
        del pil_for_yolo
        gc.collect()
        logger.debug(
            "pipeline: step 5-6 (YOLO+taxonomy) — class='%s' conf=%.3f → %s",
            yolo_class, raw_detection_confidence, category.value,
        )

        # -----------------------------------------------------------------------
        # Step 5b: Civic-relevance gate
        # Raises ImageValidationError for personal/portrait photos that contain
        # no civic-infrastructure evidence.  Valid civic scenes containing people
        # (e.g. a road with pedestrians) pass through unchanged.
        # ImageValidationError propagates to the caller exactly like a T2-2
        # validation failure — the report is not created.
        # -----------------------------------------------------------------------
        from cv.relevance import check_civic_relevance
        check_civic_relevance(detection)

    except Exception as exc:
        # Re-raise ImageValidationError so the router returns HTTP 422.
        from cv.image_validator import ImageValidationError as _IVE
        if isinstance(exc, _IVE):
            raise
        logger.warning(
            "pipeline: steps 5-6 (YOLO) failed — defaulting to category=other: %s", exc
        )

    # -----------------------------------------------------------------------
    # Step 7: Confidence scoring (T2-6)
    # -----------------------------------------------------------------------
    confidence: float = 0.0
    try:
        confidence = compute_confidence(raw_detection_confidence, category)
        logger.debug("pipeline: step 7 (confidence) — %.3f", confidence)
    except Exception as exc:
        logger.warning("pipeline: step 7 (confidence) failed: %s", exc)

    # -----------------------------------------------------------------------
    # Step 8: Authority routing (ADR-001)
    # -----------------------------------------------------------------------
    authority_recommendation: str = "MCC"
    authority_id: str = ""
    match_reason: str = ""
    try:
        from services.authority_service import route_to_authority

        auth_dict, match_reason, _auth_conf = route_to_authority(
            category.value, effective_address
        )
        if auth_dict:
            authority_recommendation = auth_dict.get("short_name", "MCC")
            authority_id = auth_dict.get("id", "")
        logger.debug(
            "pipeline: step 8 (authority) — %s (%s)",
            authority_recommendation, match_reason,
        )
    except Exception as exc:
        logger.warning("pipeline: step 8 (authority) failed: %s", exc)

    # -----------------------------------------------------------------------
    # Step 9: LLM (T2-10)
    # Per architecture §9: classify_category if YOLO confidence < 0.5
    # Then always generate_complaint_description
    # -----------------------------------------------------------------------
    description: str = ""
    llm_provider_used: str = "none"

    try:
        from services.llm_service import classify_category, generate_complaint_description

        # Use LLM to refine category when YOLO confidence is low.
        if raw_detection_confidence < 0.5:
            image_context = {
                "detected_objects": yolo_class,
                "address": effective_address,
                "extra_context": f"confidence={raw_detection_confidence:.2f}",
            }
            llm_category = await classify_category(image_context)
            if llm_category != category:
                logger.debug(
                    "pipeline: step 9a (LLM classify) — YOLO=%s conf=%.2f → LLM=%s",
                    category.value, raw_detection_confidence, llm_category.value,
                )
                category = llm_category
                # Re-compute confidence with LLM-derived category.
                try:
                    confidence = compute_confidence(raw_detection_confidence, category)
                except Exception:
                    pass

        # Generate complaint description.
        cv_result = {
            "category": category,
            "confidence": confidence,
            "yolo_class": yolo_class,
        }
        llm_out = await generate_complaint_description(cv_result, location, effective_address)
        description = llm_out.description
        # If Groq key is configured, provider could be groq; else fallback.
        import os
        llm_provider_used = "groq" if os.environ.get("GROQ_API_KEY", "").strip() else "fallback"
        logger.debug("pipeline: step 9 (LLM description) — %d chars", len(description))
    except Exception as exc:
        logger.warning("pipeline: step 9 (LLM) failed — using empty description: %s", exc)
        llm_provider_used = "none"

    # -----------------------------------------------------------------------
    # Final result
    # -----------------------------------------------------------------------
    result = AIResult(
        redacted_image_bytes=redacted_bytes,
        validated_image_bytes=validated_bytes,
        category=category,
        confidence=confidence,
        authority_recommendation=authority_recommendation,
        authority_id=authority_id,
        description=description,
        image_hash=image_hash,
        is_duplicate=is_duplicate,
        duplicate_report_id=duplicate_report_id,
        llm_provider_used=llm_provider_used,
        yolo_class=yolo_class,
        raw_detection_confidence=raw_detection_confidence,
        match_reason=match_reason,
    )

    logger.info(
        "pipeline: complete — category=%s confidence=%.3f is_duplicate=%s "
        "provider=%s",
        result.category.value,
        result.confidence,
        result.is_duplicate,
        result.llm_provider_used,
    )
    return result
