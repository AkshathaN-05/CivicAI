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
       - if YOLO confidence < 0.5 OR category == other:
           → civic_classify_image (vision-based classification)
             uses actual image content for accurate civic classification.
             If result.valid=False → raise ImageValidationError (invalid image).
             If result is a genuine civic category → override category.
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
        llm_provider_used:     "groq", "groq_vision", "fallback", or "none".
        yolo_class:            Top-1 YOLO class name (empty string if none).
        raw_detection_confidence: Raw YOLOv8n confidence before weighting.
        match_reason:          Human-readable authority match reason.

        -- Evidence verification fields (new) --
        decision_state:        DecisionState string value.
        evidence_score:        Weighted multi-signal evidence score [0.0, 1.0].
        admin_priority:        AdminPriority string value.
        visual_confidence:     Image-only AI detection confidence [0.0, 1.0].
        category_confidence:   Model certainty about the civic category [0.0, 1.0].
        location_confidence:   GPS quality + plausibility [0.0, 1.0].
        freshness_confidence:  Temporal recency signal [0.0, 1.0].
        severity:              Civic impact severity ('low'/'medium'/'high').
        is_reopened:           True when decision_state = possible_reopened_issue.
        linked_report_id:      UUID of linked active/resolved report (or None).
        image_reuse_flag:      True when same hash found in non-active report.
        citizen_message:       User-facing message (hedged language, no scores).
        evidence_breakdown:    Admin-only dict for explainability.
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
    # Evidence verification fields
    decision_state: str = field(default="needs_admin_review")
    evidence_score: float = field(default=0.0)
    admin_priority: str = field(default="INSUFFICIENT")
    visual_confidence: float = field(default=0.0)
    category_confidence: float = field(default=0.0)
    location_confidence: float = field(default=0.0)
    freshness_confidence: float = field(default=0.0)
    severity: str = field(default="low")
    is_reopened: bool = field(default=False)
    linked_report_id: Optional[str] = field(default=None)
    image_reuse_flag: bool = field(default=False)
    citizen_message: str = field(default="")
    evidence_breakdown: dict = field(default_factory=dict)


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
    # Evidence verification parameters (new, optional — backward compatible)
    gps_accuracy: Optional[float] = None,
    submission_timestamp=None,  # datetime | None
    # Decision engine callbacks (injected by service layer; None = no DB queries)
    lookup_hash_active=None,
    lookup_hash_historical=None,
    find_nearby_active=None,
    find_nearby_resolved=None,
    # Severity from vision model (optional — passed when available)
    vision_severity: str = "low",
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
        gps_accuracy:    GPS accuracy radius in metres from browser geolocation API.
        submission_timestamp: Server-side submission datetime (defaults to now()).
        lookup_hash_active:   Callback (hash) -> Optional[HashLookupResult]
        lookup_hash_historical: Callback (hash) -> Optional[HashLookupResult]
        find_nearby_active:   Callback (lat, lng, category, radius) -> list
        find_nearby_resolved: Callback (lat, lng, category, radius, days) -> list
        vision_severity:  Severity from vision model ('low'/'medium'/'high').

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
    all_class_names: tuple = ()

    try:
        from cv.detection import detect_civic_issue

        pil_for_yolo = Image.open(io.BytesIO(validated_bytes))
        detection = detect_civic_issue(pil_for_yolo)
        yolo_class = detection.yolo_class
        raw_detection_confidence = detection.confidence
        category = detection.category
        all_class_names = detection.all_class_names
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
    # Step 9: Classification + LLM (T2-10)
    #
    # Routing (definitive post-fix):
    #
    #   Step 9a: LOCAL ROAD-DAMAGE SPECIALIST MODEL (hint only)
    #     Runs first for speed — it is CPU-only and cached.
    #     Its result is passed as a HINT to Groq Vision, NOT used as the
    #     final category.  This allows the specialist to say "I think this
    #     is a pothole" while Groq Vision makes the authoritative call.
    #
    #   Step 9b: GROQ VISION — ALWAYS the final semantic classifier
    #     Receives the privacy-redacted image bytes + the road model hint.
    #     Returns a structured civic classification using the 4-bucket schema:
    #       pothole / road_damage / streetlight / water_sewage / other / invalid
    #     Groq Vision is NEVER skipped for a valid candidate image.
    #     The YOLO generic-object labels do NOT bypass Groq Vision.
    #
    #   Step 9c: COMPLAINT DESCRIPTION
    #     Always generates a description using the (possibly updated) category.
    # -----------------------------------------------------------------------
    description: str = ""
    llm_provider_used: str = "none"

    try:
        from services.llm_service import civic_classify_image, generate_complaint_description
        from llm.fallback_provider import map_vision_category_to_issue_category

        # -------------------------------------------------------------------
        # Step 9a: Local road-damage specialist model (hint only)
        #
        # Run unconditionally — it is fast (CPU, cached singleton).
        # Its result is passed as a hint to Groq Vision; it does NOT
        # short-circuit Groq.  This preserves road-model expertise while
        # letting Groq Vision make the final semantic decision.
        # -------------------------------------------------------------------
        _road_model_hint: str = ""
        try:
            from cv.road_damage import classify_road_damage

            # Privacy requirement: road model receives the redacted image,
            # not the original validated (pre-redaction) bytes.
            pil_for_road = Image.open(io.BytesIO(redacted_bytes))
            road_result = classify_road_damage(pil_for_road)
            del pil_for_road
            gc.collect()

            if road_result.detected:
                # Build a NON-AUTHORITATIVE hint for Groq Vision.
                # Explicitly labelled as secondary evidence that can be wrong
                # (e.g. the road model may fire on the road surface visible
                # underneath a garbage dump).  Groq Vision always makes the
                # final semantic decision.
                _road_model_hint = (
                    f"[NON-AUTHORITATIVE secondary hint — road surface detector only] "
                    f"road specialist detected: {road_result.category} "
                    f"(conf={road_result.confidence:.2f}, raw class {road_result.raw_class}). "
                    f"This hint reflects road SURFACE texture only. "
                    f"If the primary civic problem is garbage, a streetlight, or water/sewage, "
                    f"ignore this hint and classify by the actual civic issue."
                )
                logger.info(
                    "pipeline: step 9a (road model hint) — %s (conf=%.2f, raw=%s) "
                    "→ passing as hint to Groq Vision",
                    road_result.category,
                    road_result.confidence,
                    road_result.raw_class,
                )
            else:
                logger.debug(
                    "pipeline: step 9a (road model) — no confident detection "
                    "(conf=%.3f) — no hint provided",
                    road_result.confidence,
                )
        except Exception as exc_road:
            logger.warning(
                "pipeline: step 9a (local road model) failed gracefully: %s",
                exc_road,
            )

        # -------------------------------------------------------------------
        # Step 9b: Groq Vision — ALWAYS the final semantic classifier
        #
        # Called for every valid image.  Receives the privacy-redacted bytes
        # and the road model hint (if available).
        #
        # Four semantic output categories:
        #   pothole       → IssueCategory.pothole
        #   road_damage   → IssueCategory.road_damage
        #   streetlight   → IssueCategory.broken_streetlight
        #   water_sewage  → IssueCategory.water_supply / .sewage / .waterlogging
        #                   (resolved from the 'reason' subtype field)
        #   other         → IssueCategory.other
        #   invalid       → rejected (ImageValidationError)
        # -------------------------------------------------------------------
        vision_result = await civic_classify_image(
            image_bytes=redacted_bytes,
            yolo_class=yolo_class,
            all_class_names=all_class_names,
            address=effective_address,
            road_model_hint=_road_model_hint,
        )

        logger.debug(
            "pipeline: step 9b (Groq Vision) — valid=%s category=%s conf=%.2f "
            "severity=%s reason='%s' yolo_was='%s'",
            vision_result.valid,
            vision_result.category,
            vision_result.category_confidence,
            vision_result.severity,
            vision_result.reason,
            yolo_class,
        )

        # If vision model says the image is NOT a civic issue, reject it.
        if not vision_result.valid:
            logger.info(
                "pipeline: step 9b (Groq Vision) — image rejected as non-civic: "
                "category=%s reason=%s",
                vision_result.category,
                vision_result.reason,
            )
            raise ImageValidationError(
                "This image does not appear to show a civic issue. "
                "Please upload a photo of a road, pothole, streetlight, "
                "water issue, or other public infrastructure problem. "
                f"({vision_result.reason})"
            )

        # Map vision category to canonical IssueCategory.
        # Pass reason so water_sewage can be resolved to the correct subtype.
        new_category = map_vision_category_to_issue_category(
            vision_result.category,
            reason=vision_result.reason,
        )

        # Use vision classification confidence as the authoritative confidence.
        new_confidence = vision_result.category_confidence

        logger.info(
            "pipeline: step 9b (Groq Vision) — "
            "YOLO(%s/%.2f) road_hint=%r → vision(%s) → db_category=%s (conf=%.2f)",
            category.value, confidence,
            _road_model_hint or "none",
            vision_result.category,
            new_category.value, new_confidence,
        )
        category = new_category
        confidence = new_confidence

        # Use vision-generated description as primary description.
        if vision_result.description:
            description = vision_result.description

        # Re-route authority for the vision-classified category.
        try:
            from services.authority_service import route_to_authority as _route
            auth_dict2, match_reason2, _ = _route(
                category.value, effective_address
            )
            if auth_dict2:
                authority_recommendation = auth_dict2.get("short_name", authority_recommendation)
                authority_id = auth_dict2.get("id", authority_id)
                match_reason = match_reason2
        except Exception as exc2:
            logger.warning("pipeline: step 9b (re-route authority) failed: %s", exc2)

        import os as _os
        # Report the provider that actually ran.
        # If the heuristic fallback was used (reason="heuristic_fallback"),
        # report that accurately so callers know Groq Vision did not run.
        if vision_result.reason == "heuristic_fallback":
            llm_provider_used = "heuristic_fallback"
        elif _os.environ.get("GROQ_API_KEY", "").strip():
            llm_provider_used = "groq_vision"
        else:
            llm_provider_used = "fallback"

        # 9c: Generate complaint description (if not already set by vision result)
        if not description:
            cv_result = {
                "category": category,
                "confidence": confidence,
                "yolo_class": yolo_class,
            }
            llm_out = await generate_complaint_description(cv_result, location, effective_address)
            description = llm_out.description
            logger.debug("pipeline: step 9b (LLM description) — %d chars", len(description))

    except Exception as exc:
        # Re-raise ImageValidationError so the router returns HTTP 422.
        from cv.image_validator import ImageValidationError as _IVE
        if isinstance(exc, _IVE):
            raise
        logger.warning("pipeline: step 9 (LLM) failed — using empty description: %s", exc)
        llm_provider_used = "none"

    # -----------------------------------------------------------------------
    # Step 10: Evidence verification (new)
    # Compute confidence dimensions, run decision engine, attach verdict.
    # -----------------------------------------------------------------------
    from datetime import datetime as _dt, timezone as _tz

    # Parse lat/lng from the location string if not passed directly
    _lat: Optional[float] = None
    _lng: Optional[float] = None
    if location:
        try:
            parts = location.split(",")
            if len(parts) == 2:
                _lat = float(parts[0].strip())
                _lng = float(parts[1].strip())
        except (ValueError, AttributeError):
            pass

    # Build confidence dimensions
    # visual_confidence: from the AI classification path
    #   local road model → road_result.confidence
    #   groq vision → vision_result.category_confidence
    #   YOLO+weight  → confidence (compute_confidence output)
    _visual_conf: float = min(max(float(confidence), 0.0), 1.0)
    _category_conf: float = _visual_conf  # same source for now; road model confidence IS the category confidence

    # location_confidence: GPS quality + Mangaluru plausibility
    _location_conf: float = _compute_location_confidence(_lat, _lng, gps_accuracy)

    # freshness_confidence: EXIF + submission recency
    _now = submission_timestamp if submission_timestamp is not None else _dt.now(_tz.utc)
    _freshness_conf: float = _compute_freshness_confidence(validated_bytes, _now)

    # Run decision engine if any callback is provided; otherwise produce defaults
    _evidence_result = None
    if any(cb is not None for cb in [lookup_hash_active, lookup_hash_historical,
                                      find_nearby_active, find_nearby_resolved]):
        try:
            from cv.decision_engine import (
                DecisionContext,
                DecisionEngine,
                HashLookupResult,
            )
            _ctx = DecisionContext(
                image_hash=image_hash or "",
                category=category.value,
                lat=_lat,
                lng=_lng,
                gps_accuracy_metres=gps_accuracy,
                submission_time=_now,
                visual_confidence=_visual_conf,
                category_confidence=_category_conf,
                location_confidence=_location_conf,
                freshness_confidence=_freshness_conf,
                severity=vision_severity or "low",
            )
            _engine = DecisionEngine(
                lookup_hash_active=lookup_hash_active or (lambda h: None),
                lookup_hash_historical=lookup_hash_historical or (lambda h: None),
                find_nearby_active=find_nearby_active or (lambda la, ln, cat, r: []),
                find_nearby_resolved=find_nearby_resolved or (lambda la, ln, cat, r, d: []),
            )
            _evidence_result = _engine.decide(_ctx)
            logger.info(
                "pipeline: step 10 (evidence) — state=%s score=%.3f priority=%s",
                _evidence_result.decision_state,
                _evidence_result.evidence_score,
                _evidence_result.admin_priority,
            )
        except Exception as exc:
            logger.warning("pipeline: step 10 (evidence) failed — using defaults: %s", exc)
    else:
        # No DB callbacks — compute score-only decision (offline / test mode)
        try:
            from cv.evidence_scorer import (
                compute_evidence_score,
                VALID_THRESHOLD,
                REVIEW_THRESHOLD,
            )
            from cv.decision_engine import _assign_admin_priority, _citizen_message
            _ev_score = compute_evidence_score(
                _visual_conf, _category_conf, _location_conf, _freshness_conf
            )
            if _ev_score >= VALID_THRESHOLD:
                _state = "valid_civic_report"
            elif _ev_score >= REVIEW_THRESHOLD:
                _state = "needs_admin_review"
            else:
                _state = "insufficient_evidence"
            _priority = _assign_admin_priority(_state, _ev_score, _visual_conf, vision_severity or "low")

            class _SimpleResult:
                decision_state = _state
                evidence_score = _ev_score
                admin_priority = _priority
                is_reopened = False
                linked_report_id = None
                image_reuse_flag = False
                image_reuse_prior_report_id = None
                image_reuse_prior_status = None
                citizen_message = _citizen_message(_state)
                evidence_breakdown: dict = {
                    "visual_confidence": _visual_conf,
                    "category_confidence": _category_conf,
                    "location_confidence": _location_conf,
                    "freshness_confidence": _freshness_conf,
                    "evidence_score": _ev_score,
                    "decision_state": _state,
                    "admin_priority": _priority,
                    "severity": vision_severity or "low",
                    "evidence_disclaimer": (
                        "Evidence scores reflect the strength of submitted evidence only, "
                        "not a verified assessment of current road conditions."
                    ),
                }

            _evidence_result = _SimpleResult()
        except Exception as exc:
            logger.warning("pipeline: step 10 (evidence score-only) failed: %s", exc)

    # -----------------------------------------------------------------------
    # Final result
    # -----------------------------------------------------------------------
    _ev = _evidence_result

    # Backward-compat: keep legacy is_duplicate/duplicate_report_id populated
    _final_is_dup = is_duplicate
    _final_dup_id = duplicate_report_id
    if _ev and _ev.decision_state == "duplicate_active_report":
        _final_is_dup = True
        _final_dup_id = _final_dup_id or _ev.linked_report_id

    result = AIResult(
        redacted_image_bytes=redacted_bytes,
        validated_image_bytes=validated_bytes,
        category=category,
        confidence=confidence,
        authority_recommendation=authority_recommendation,
        authority_id=authority_id,
        description=description,
        image_hash=image_hash,
        is_duplicate=_final_is_dup,
        duplicate_report_id=_final_dup_id,
        llm_provider_used=llm_provider_used,
        yolo_class=yolo_class,
        raw_detection_confidence=raw_detection_confidence,
        match_reason=match_reason,
        # Evidence verification fields
        decision_state=_ev.decision_state if _ev else "needs_admin_review",
        evidence_score=_ev.evidence_score if _ev else 0.0,
        admin_priority=_ev.admin_priority if _ev else "INSUFFICIENT",
        visual_confidence=_visual_conf,
        category_confidence=_category_conf,
        location_confidence=_location_conf,
        freshness_confidence=_freshness_conf,
        severity=vision_severity or "low",
        is_reopened=_ev.is_reopened if _ev else False,
        linked_report_id=_ev.linked_report_id if _ev else None,
        image_reuse_flag=_ev.image_reuse_flag if _ev else False,
        citizen_message=_ev.citizen_message if _ev else "",
        evidence_breakdown=_ev.evidence_breakdown if _ev else {},
    )

    logger.info(
        "pipeline: complete — category=%s confidence=%.3f decision=%s "
        "evidence_score=%.3f priority=%s provider=%s",
        result.category.value,
        result.confidence,
        result.decision_state,
        result.evidence_score,
        result.admin_priority,
        result.llm_provider_used,
    )
    return result


# ---------------------------------------------------------------------------
# Evidence confidence helpers (pure functions, no model loading)
# ---------------------------------------------------------------------------

_MANGALURU_BBOX = {
    "lat_min": 12.7, "lat_max": 13.1,
    "lng_min": 74.7, "lng_max": 75.1,
}


def _compute_location_confidence(
    lat: Optional[float],
    lng: Optional[float],
    gps_accuracy: Optional[float],
) -> float:
    """Return location_confidence in [0.0, 1.0].

    GPS accuracy is a corroborating signal only — it does NOT prove the photo
    was taken at the reported coordinates.
    """
    if lat is None or lng is None:
        return 0.30  # text-only location

    # Plausibility: is the location within the Mangaluru service area?
    in_bbox = (
        _MANGALURU_BBOX["lat_min"] <= lat <= _MANGALURU_BBOX["lat_max"]
        and _MANGALURU_BBOX["lng_min"] <= lng <= _MANGALURU_BBOX["lng_max"]
    )

    if gps_accuracy is None:
        base = 0.60  # GPS present but no accuracy info
    elif gps_accuracy <= 20:
        base = 0.85  # precise GPS (≤20 m)
    elif gps_accuracy <= 50:
        base = 0.70  # reasonable mobile GPS (≤50 m)
    else:
        base = 0.40  # imprecise GPS (>50 m)

    if not in_bbox:
        return round(base * 0.1, 4)  # location outside service area → very low

    return base


def _compute_freshness_confidence(
    validated_bytes: bytes,
    submission_time,
) -> float:
    """Return freshness_confidence in [0.0, 1.0].

    Uses EXIF DateTimeOriginal if available; falls back to 0.50 default.
    EXIF timestamps are NOT treated as proof — they are one corroborating signal.
    """
    try:
        from PIL import Image as _PIL, ExifTags as _ExifTags
        import io as _io
        from datetime import datetime as _dt, timezone as _tz

        img = _PIL.open(_io.BytesIO(validated_bytes))
        exif_data = img._getexif() if hasattr(img, "_getexif") else None
        if exif_data:
            # Find DateTimeOriginal tag
            date_tag = next(
                (k for k, v in _ExifTags.TAGS.items() if v == "DateTimeOriginal"),
                None,
            )
            if date_tag and date_tag in exif_data:
                raw_dt = exif_data[date_tag]
                exif_time = _dt.strptime(raw_dt, "%Y:%m:%d %H:%M:%S").replace(
                    tzinfo=_tz.utc
                )
                if submission_time.tzinfo is None:
                    submission_time = submission_time.replace(tzinfo=_tz.utc)
                age_seconds = abs((submission_time - exif_time).total_seconds())
                if age_seconds < 3600:        # < 1 hour
                    return 0.90
                elif age_seconds < 86400:     # < 24 hours
                    return 0.75
                elif age_seconds < 604800:    # < 7 days
                    return 0.55
                else:
                    return 0.25               # image is older than 7 days
    except Exception:
        pass  # EXIF unavailable or unreadable — use default

    return 0.50  # default: submission timestamp is authoritative
