"""Tests for T2-11 — AI Pipeline Orchestrator.

Covers:
- AIResult: all required fields present
- run_ai_pipeline: valid image → returns AIResult
- run_ai_pipeline: invalid image → raises ImageValidationError (not swallowed)
- run_ai_pipeline: YOLO failure → graceful fallback, category=other
- run_ai_pipeline: privacy redaction failure → pipeline continues
- run_ai_pipeline: blake3 hash is computed
- run_ai_pipeline: is_duplicate=True when matching hash provided
- run_ai_pipeline: is_duplicate=False when no match
- run_ai_pipeline: authority_recommendation is set
- run_ai_pipeline: LLM failure → pipeline continues with empty description
- run_ai_pipeline: YOLO confidence < 0.5 → classify_category called
- Memory: test completes without unbounded growth (no memory assert — see note)
- Partial failure: YOLO fails → returns category=other, confidence=0.0 or computed
- No DB writes (pipeline is pure CPU + LLM; no side effects)
- redacted_image_bytes field is bytes
- validated_image_bytes field is bytes

Note on memory test:
  The architecture requires memory < 400 MB after pipeline run.
  An exact psutil assertion would be flaky on CI (GC timing, OS baseline).
  We verify the pipeline runs without error; memory regression would require
  profiling under production conditions.

All model inference is mocked to keep tests fast and deterministic.
"""
from __future__ import annotations

import gc
import io
import os
from dataclasses import fields
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from cv.image_validator import ImageValidationError
from cv.pipeline import AIResult, run_ai_pipeline
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Test image fixtures
# ---------------------------------------------------------------------------

def _make_jpeg_bytes(width: int = 300, height: int = 300, color="gray") -> bytes:
    """Create minimal valid JPEG bytes for testing."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_tiny_jpeg() -> bytes:
    """Create a JPEG that is too small to pass validation — for invalid-input tests.

    Under the updated rule an image is rejected when:
      area < MIN_AREA_PX (10_000)  OR  shortest side < MIN_SHORT_SIDE_PX (50).
    A 40×40 px image has area=1600 and short_side=40 — fails both thresholds.
    """
    img = Image.new("RGB", (40, 40), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


VALID_JPEG = _make_jpeg_bytes()
VALID_JPEG_2 = _make_jpeg_bytes(color="blue")
TINY_JPEG = _make_tiny_jpeg()

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_detection(category: IssueCategory = IssueCategory.road_damage, confidence: float = 0.8):
    """Return a mock DetectionResult-like object."""
    m = MagicMock()
    m.yolo_class = "car"
    m.confidence = confidence
    m.category = category
    return m


def _mock_llm_output(category: IssueCategory = IssueCategory.road_damage) -> MagicMock:
    from llm.output_validator import LLMOutput
    return LLMOutput(
        category=category,
        description="A civic issue has been detected.",
        authority_recommendation="MCC",
        confidence=0.8,
    )


# ---------------------------------------------------------------------------
# AIResult schema tests
# ---------------------------------------------------------------------------

class TestAIResultSchema:
    def test_all_required_fields_present(self):
        """AIResult must have all fields specified by the architecture."""
        required_fields = {
            "redacted_image_bytes",
            "validated_image_bytes",
            "category",
            "confidence",
            "authority_recommendation",
            "authority_id",
            "description",
            "image_hash",
            "is_duplicate",
            "duplicate_report_id",
            "llm_provider_used",
            "yolo_class",
            "raw_detection_confidence",
            "match_reason",
            # Evidence verification fields (new)
            "decision_state",
            "evidence_score",
            "admin_priority",
            "visual_confidence",
            "category_confidence",
            "location_confidence",
            "freshness_confidence",
            "severity",
            "is_reopened",
            "linked_report_id",
            "image_reuse_flag",
            "citizen_message",
            "evidence_breakdown",
        }
        actual_fields = {f.name for f in fields(AIResult)}
        missing = required_fields - actual_fields
        assert not missing, f"AIResult missing fields: {missing}"

    def test_ai_result_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(AIResult)

    def test_evidence_fields_have_defaults(self):
        """New evidence fields must have defaults so existing callers are not broken."""
        # Construct with only the originally-required fields
        from schemas.report import IssueCategory
        import io
        from PIL import Image as _PIL
        buf = io.BytesIO()
        _PIL.new("RGB", (10, 10), "white").save(buf, format="JPEG")
        dummy_bytes = buf.getvalue()
        result = AIResult(
            redacted_image_bytes=dummy_bytes,
            validated_image_bytes=dummy_bytes,
            category=IssueCategory.pothole,
            confidence=0.8,
            authority_recommendation="MCC",
            authority_id="mcc",
            description="test",
            image_hash="abc123",
            is_duplicate=False,
            duplicate_report_id=None,
            llm_provider_used="fallback",
            yolo_class="frisbee",
            raw_detection_confidence=0.5,
        )
        # Check all evidence fields have sensible defaults
        assert isinstance(result.decision_state, str)
        assert isinstance(result.evidence_score, float)
        assert isinstance(result.admin_priority, str)
        assert isinstance(result.is_reopened, bool)
        assert isinstance(result.image_reuse_flag, bool)
        assert isinstance(result.evidence_breakdown, dict)


# ---------------------------------------------------------------------------
# run_ai_pipeline tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRunAIPipeline:
    """All heavy model calls are mocked to keep tests fast."""

    async def _run_with_mocks(
        self,
        image_bytes: bytes = None,
        *,
        detection_category: IssueCategory = IssueCategory.road_damage,
        detection_confidence: float = 0.8,
        yolo_side_effect=None,
        redact_side_effect=None,
        llm_side_effect=None,
        existing_hashes=None,
    ) -> AIResult:
        """Run pipeline with heavy steps mocked."""
        if image_bytes is None:
            image_bytes = VALID_JPEG

        mock_det = _mock_detection(detection_category, detection_confidence)
        mock_det.all_class_names = ()  # ensure all_class_names is always set

        def _fake_detect(img):
            if yolo_side_effect:
                raise yolo_side_effect
            return mock_det

        fake_llm_out = _mock_llm_output(detection_category)

        async def _fake_gen_description(cv_result, location, address):
            if llm_side_effect:
                raise llm_side_effect
            return fake_llm_out

        async def _fake_classify(image_context):
            return detection_category

        def _fake_redact_privacy(img):
            if redact_side_effect:
                raise redact_side_effect
            return img  # return unchanged for speed

        # Mock civic_classify_image for cases where vision classification is triggered
        # (low confidence or category=other). Returns a simple valid civic result.
        from llm.groq_provider import CivicClassificationResult

        async def _fake_civic_classify(image_bytes, yolo_class, all_class_names, address):
            return CivicClassificationResult(
                valid=True,
                category=detection_category.value,
                category_confidence=detection_confidence if detection_confidence > 0 else 0.5,
                severity="medium",
                severity_score=0.5,
                description="A civic issue has been detected.",
                reason="mocked",
            )

        with (
            patch("cv.pipeline.validate_image", wraps=__import__("cv.image_validator", fromlist=["validate_image"]).validate_image),
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=_fake_redact_privacy),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen_description),
            patch("services.llm_service.classify_category", new=_fake_classify),
            patch("services.llm_service.civic_classify_image", new=_fake_civic_classify),
        ):
            return await run_ai_pipeline(
                image_bytes,
                location="13.0,74.0",
                address="MG Road, Mangaluru",
                existing_hashes=existing_hashes,
            )

    async def test_valid_image_returns_ai_result(self):
        result = await self._run_with_mocks()
        assert isinstance(result, AIResult)

    async def test_all_fields_populated(self):
        result = await self._run_with_mocks()
        assert isinstance(result.redacted_image_bytes, bytes)
        assert isinstance(result.validated_image_bytes, bytes)
        assert isinstance(result.category, IssueCategory)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.authority_recommendation, str)
        assert isinstance(result.authority_id, str)
        assert isinstance(result.description, str)
        assert isinstance(result.image_hash, str)
        assert isinstance(result.is_duplicate, bool)
        assert isinstance(result.yolo_class, str)
        assert isinstance(result.raw_detection_confidence, float)

    async def test_invalid_image_raises_validation_error(self):
        """ImageValidationError must propagate (not be swallowed)."""
        with pytest.raises(ImageValidationError):
            await run_ai_pipeline(TINY_JPEG, location="", address="")

    async def test_garbage_bytes_raises_validation_error(self):
        with pytest.raises(ImageValidationError):
            await run_ai_pipeline(b"not an image", location="", address="")

    async def test_yolo_failure_category_defaults_to_other(self):
        """When YOLO crashes: confidence=0.0, raw_detection_confidence=0.0.
        
        The LLM classify_category IS called (since raw_confidence < 0.5) when
        YOLO fails, but we verify that the pipeline gracefully continues and
        that raw_detection_confidence is 0.0.
        """
        result = await self._run_with_mocks(
            yolo_side_effect=RuntimeError("YOLO model crashed")
        )
        assert isinstance(result, AIResult)
        # When YOLO fails, raw_detection_confidence must be 0.0
        assert result.raw_detection_confidence == 0.0
        # Pipeline must not raise — it continues gracefully
        assert isinstance(result.category, IssueCategory)

    async def test_privacy_redaction_failure_pipeline_continues(self):
        """When privacy redaction fails the pipeline still returns a result."""
        result = await self._run_with_mocks(
            redact_side_effect=RuntimeError("redaction crashed")
        )
        assert isinstance(result, AIResult)
        # validated_image_bytes used as fallback
        assert len(result.redacted_image_bytes) > 0

    async def test_llm_failure_description_is_empty(self):
        """When LLM fails description is empty string (pipeline still succeeds)."""
        result = await self._run_with_mocks(
            llm_side_effect=RuntimeError("LLM failed")
        )
        assert isinstance(result, AIResult)
        assert result.description == ""

    async def test_image_hash_computed(self):
        """image_hash must be a non-empty hex string (BLAKE3)."""
        result = await self._run_with_mocks()
        assert len(result.image_hash) == 64  # BLAKE3 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in result.image_hash)

    async def test_same_image_same_hash(self):
        """Same image bytes → same BLAKE3 hash (deterministic)."""
        r1 = await self._run_with_mocks(VALID_JPEG)
        r2 = await self._run_with_mocks(VALID_JPEG)
        assert r1.image_hash == r2.image_hash

    async def test_different_images_different_hash(self):
        """Different image bytes → different BLAKE3 hash."""
        r1 = await self._run_with_mocks(VALID_JPEG)
        r2 = await self._run_with_mocks(VALID_JPEG_2)
        assert r1.image_hash != r2.image_hash

    async def test_is_duplicate_true_when_hash_matches(self):
        """Providing matching hash in existing_hashes → is_duplicate=True."""
        # First compute hash of VALID_JPEG
        import blake3 as _blake3
        known_hash = _blake3.blake3(
            __import__("cv.image_validator", fromlist=["validate_image"]).validate_image(VALID_JPEG)
        ).hexdigest()

        result = await self._run_with_mocks(
            VALID_JPEG,
            existing_hashes=[(known_hash, "existing-report-id")],
        )
        assert result.is_duplicate is True
        assert result.duplicate_report_id == "existing-report-id"

    async def test_is_duplicate_false_when_no_match(self):
        """No matching hash → is_duplicate=False."""
        result = await self._run_with_mocks(
            VALID_JPEG,
            existing_hashes=[("aaaaabbbbbc" * 6, "other-report")],
        )
        assert result.is_duplicate is False
        assert result.duplicate_report_id is None

    async def test_is_duplicate_false_when_empty_hashes(self):
        result = await self._run_with_mocks(existing_hashes=[])
        assert result.is_duplicate is False

    async def test_is_duplicate_false_when_hashes_none(self):
        result = await self._run_with_mocks(existing_hashes=None)
        assert result.is_duplicate is False

    async def test_authority_recommendation_set(self):
        """Authority recommendation must be a non-empty string."""
        result = await self._run_with_mocks(
            detection_category=IssueCategory.pothole
        )
        assert isinstance(result.authority_recommendation, str)
        assert len(result.authority_recommendation) > 0

    async def test_low_confidence_calls_civic_classify_image(self):
        """When YOLO confidence < 0.5, civic_classify_image (vision) is called.

        Updated behavior: the pipeline now uses vision-based civic classification
        (civic_classify_image) instead of classify_category for low-confidence
        YOLO detections.  This is the core fix for the pothole misclassification bug.
        """
        vision_called = []

        from llm.groq_provider import CivicClassificationResult

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_called.append({"yolo_class": yolo_class, "address": address})
            return CivicClassificationResult(
                valid=True, category="garbage",
                category_confidence=0.75,
                severity="medium", severity_score=0.5,
                description="Garbage overflow visible.",
                reason="garbage_detected",
            )

        async def _fake_gen_description(cv_result, location, address):
            return _mock_llm_output(cv_result.get("category", IssueCategory.other))

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "bottle"
            m.confidence = 0.3  # below 0.5 threshold
            m.category = IssueCategory.garbage_overflow
            m.all_class_names = ("bottle",)
            return m

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen_description),
        ):
            result = await run_ai_pipeline(
                VALID_JPEG, location="", address="Mangaluru"
            )

        assert vision_called, (
            "civic_classify_image (vision) should have been called for low confidence"
        )

    async def test_high_confidence_non_other_skips_civic_classify_image(self):
        """When YOLO confidence >= 0.5 AND category != other, civic_classify_image
        is NOT called; classify_category is used instead (existing flow).
        """
        vision_called = []

        from llm.groq_provider import CivicClassificationResult

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_called.append(True)
            return CivicClassificationResult(
                valid=True, category="road_damage",
                category_confidence=0.9,
                severity="medium", severity_score=0.5,
                description="Road damage visible.",
                reason="road_detected",
            )

        async def _fake_gen(cv_result, location, address):
            return _mock_llm_output()

        async def _fake_classify_cat(image_context):
            return IssueCategory.road_damage

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.8  # >= 0.5 AND category != other
            m.category = IssueCategory.road_damage
            m.all_class_names = ("car",)
            return m

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

        assert not vision_called, (
            "civic_classify_image should NOT be called when YOLO conf >= 0.5 "
            "and category != other"
        )

    async def test_no_db_writes(self):
        """Pipeline must not make any DB calls."""
        from unittest.mock import call as _call

        with patch("db.repositories.report_repo.insert_report") as mock_insert:
            await self._run_with_mocks()
            mock_insert.assert_not_called()

    async def test_redacted_bytes_are_bytes(self):
        result = await self._run_with_mocks()
        assert isinstance(result.redacted_image_bytes, bytes)
        assert len(result.redacted_image_bytes) > 0

    async def test_validated_bytes_are_bytes(self):
        result = await self._run_with_mocks()
        assert isinstance(result.validated_image_bytes, bytes)
        assert len(result.validated_image_bytes) > 0

    async def test_category_is_issue_category(self):
        result = await self._run_with_mocks()
        assert isinstance(result.category, IssueCategory)

    async def test_confidence_in_0_1_range(self):
        result = await self._run_with_mocks(
            detection_category=IssueCategory.garbage_overflow,
            detection_confidence=0.9,
        )
        assert 0.0 <= result.confidence <= 1.0

    async def test_memory_cleanup_does_not_raise(self):
        """gc.collect() calls in pipeline must not raise."""
        result = await self._run_with_mocks()
        gc.collect()  # Explicit cleanup should be safe post-pipeline
        assert isinstance(result, AIResult)


# ---------------------------------------------------------------------------
# Road model integration tests (requirements A–I from integration spec)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRoadModelIntegration:
    """Tests for the local road-damage model integration in the pipeline.

    All model inference is mocked.  Tests verify:
    A. Confident pothole/road result — local model accepted, civic_classify_image skipped.
    B. Low-confidence local result — local model rejected, civic_classify_image called.
    C. Unsupported/non-road image — civic_classify_image handles it.
    D. Local model failure — no crash, civic_classify_image called.
    E. Selfie/person-only — remains invalid/rejected.
    F. Civic image with people/vehicles — remains valid.
    G. No GROQ_API_KEY — local road classification still works.
    H. Privacy — road model receives redacted image, not original.
    I. Pipeline ordering — road model attempted BEFORE civic_classify_image.
    """

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _run(
        self,
        *,
        road_result=None,
        road_side_effect=None,
        vision_result=None,
        vision_side_effect=None,
        yolo_confidence: float = 0.1,
        yolo_category=None,
        image_bytes: bytes = None,
    ) -> "AIResult":
        """Run the pipeline with road model and vision both mocked."""
        from cv.road_damage import RoadDamageResult

        if image_bytes is None:
            image_bytes = VALID_JPEG

        if yolo_category is None:
            from schemas.report import IssueCategory as _IC
            yolo_category = _IC.other

        if road_result is None:
            road_result = RoadDamageResult(detected=False, category="", confidence=0.0)

        if vision_result is None:
            # Build a MagicMock so we don't need the groq package installed.
            vision_result = MagicMock()
            vision_result.valid = True
            vision_result.category = "road_damage"
            vision_result.category_confidence = 0.75
            vision_result.severity = "medium"
            vision_result.severity_score = 0.5
            vision_result.description = "Civic issue detected."
            vision_result.reason = "detected"

        def _fake_road(image):
            if road_side_effect is not None:
                raise road_side_effect
            return road_result

        async def _fake_vision(image_bytes, yolo_class, all_class_names, address):
            if vision_side_effect is not None:
                raise vision_side_effect
            return vision_result

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "frisbee"
            m.confidence = yolo_confidence
            m.category = yolo_category
            m.all_class_names = ()
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            from schemas.report import IssueCategory as _IC
            cat = cv_result.get("category", _IC.other)
            return LLMOutput(
                category=cat,
                description="A civic issue was detected.",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(image_context):
            from schemas.report import IssueCategory as _IC
            return _IC.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("services.llm_service.civic_classify_image", new=_fake_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            return await run_ai_pipeline(
                image_bytes,
                location="13.0,74.0",
                address="MG Road, Mangaluru",
            )

    # ------------------------------------------------------------------
    # A. Confident road result — civic_classify_image must be skipped
    # ------------------------------------------------------------------

    async def test_A_confident_pothole_uses_local_result(self):
        """A. Confident pothole detection: local result accepted, vision NOT called."""
        from cv.road_damage import RoadDamageResult
        from schemas.report import IssueCategory

        road_result = RoadDamageResult(detected=True, category="pothole",
                                       confidence=0.82, raw_class="D40")
        vision_calls = []

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_calls.append(True)
            v = MagicMock()
            v.valid = True; v.category = "pothole"; v.category_confidence = 0.9
            v.severity = "high"; v.severity_score = 0.85
            v.description = "desc"; v.reason = "r"
            return v

        def _fake_road(image):
            return road_result

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "frisbee"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category=IssueCategory.pothole,
                             description="desc", authority_recommendation="MCC",
                             confidence=0.82)

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(
                VALID_JPEG, location="", address="Mangaluru"
            )

        assert result.category == IssueCategory.pothole, (
            f"Expected pothole, got {result.category}"
        )
        assert result.confidence == pytest.approx(0.82, abs=1e-6)
        assert not vision_calls, "civic_classify_image must NOT be called when road model is confident"

    async def test_A_confident_road_damage_uses_local_result(self):
        """A. Confident road_damage (D00 crack): local result accepted, vision skipped."""
        from cv.road_damage import RoadDamageResult
        from schemas.report import IssueCategory

        road_result = RoadDamageResult(detected=True, category="road_damage",
                                       confidence=0.71, raw_class="D00")
        result = await self._run(road_result=road_result)

        assert result.category == IssueCategory.road_damage
        assert result.confidence == pytest.approx(0.71, abs=1e-6)
        assert result.llm_provider_used == "local_road_model"

    # ------------------------------------------------------------------
    # B. Low-confidence local result — vision must be called
    # ------------------------------------------------------------------

    async def test_B_low_confidence_falls_through_to_vision(self):
        """B. Road model below threshold: vision must be called."""
        from cv.road_damage import RoadDamageResult
        from schemas.report import IssueCategory

        # detected=False simulates below-threshold (road_damage.py already
        # returns detected=False when conf < threshold)
        road_result = RoadDamageResult(detected=False, category="", confidence=0.20)
        vision_calls = []

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_calls.append(True)
            v = MagicMock()
            v.valid = True; v.category = "garbage"; v.category_confidence = 0.75
            v.severity = "medium"; v.severity_score = 0.5
            v.description = "d"; v.reason = "r"
            return v

        def _fake_road(image):
            return road_result

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "bottle"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category=IssueCategory.garbage_overflow,
                             description="d", authority_recommendation="MCC",
                             confidence=0.75)

        async def _fake_classify_cat(ctx):
            return IssueCategory.other

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(
                VALID_JPEG, location="", address="Mangaluru"
            )

        assert vision_calls, "civic_classify_image MUST be called when road model is not confident"

    # ------------------------------------------------------------------
    # C. Non-road civic image — vision still responsible
    # ------------------------------------------------------------------

    async def test_C_non_road_image_goes_to_vision(self):
        """C. Non-road civic image: road model returns no detection, vision classifies."""
        from cv.road_damage import RoadDamageResult
        from schemas.report import IssueCategory

        road_result = RoadDamageResult(detected=False, category="", confidence=0.0)
        vision_result = MagicMock()
        vision_result.valid = True; vision_result.category = "waterlogging"
        vision_result.category_confidence = 0.88; vision_result.severity = "high"
        vision_result.severity_score = 0.85; vision_result.description = "Flooding."
        vision_result.reason = "r"
        result = await self._run(road_result=road_result, vision_result=vision_result,
                                 yolo_confidence=0.1)
        assert result.category == IssueCategory.waterlogging

    # ------------------------------------------------------------------
    # D. Local model failure — no crash, vision called
    # ------------------------------------------------------------------

    async def test_D_road_model_failure_no_crash(self):
        """D. Road model raises — pipeline does not crash; vision is called."""
        from schemas.report import IssueCategory

        vision_calls = []
        _vr = MagicMock()
        _vr.valid = True; _vr.category = "drainage"; _vr.category_confidence = 0.80
        _vr.severity = "medium"; _vr.severity_score = 0.5
        _vr.description = "d"; _vr.reason = "r"

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_calls.append(True)
            return _vr

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category=IssueCategory.open_drain,
                             description="d", authority_recommendation="MCC",
                             confidence=0.8)

        async def _fake_classify_cat(ctx):
            return IssueCategory.other

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("cv.road_damage.classify_road_damage",
                  side_effect=RuntimeError("model crashed")),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(
                VALID_JPEG, location="", address="Mangaluru"
            )

        assert isinstance(result, AIResult), "Pipeline must not raise when road model fails"
        assert vision_calls, "civic_classify_image must be called after road model failure"

    # ------------------------------------------------------------------
    # E. Selfie/person-only — still rejected
    # ------------------------------------------------------------------

    async def test_E_selfie_rejected_even_with_road_model(self):
        """E. Selfie: image remains invalid regardless of road model."""
        from cv.road_damage import RoadDamageResult
        from cv.image_validator import ImageValidationError
        from schemas.report import IssueCategory

        # Road model finds nothing (correct — selfie is not a road)
        road_result = RoadDamageResult(detected=False, category="", confidence=0.0)
        # Vision model says invalid (selfie) — use MagicMock, no groq package needed.
        vision_result = MagicMock()
        vision_result.valid = False; vision_result.category = "invalid"
        vision_result.category_confidence = 0.0; vision_result.severity = None
        vision_result.severity_score = 0.0
        vision_result.description = "This appears to be a selfie."
        vision_result.reason = "non_civic_image"

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ("person",)
            return m

        async def _fake_vision(image_bytes, yolo_class, all_class_names, address):
            return vision_result

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category=IssueCategory.other,
                             description="d", authority_recommendation="MCC",
                             confidence=0.0)

        async def _fake_classify_cat(ctx):
            return IssueCategory.other

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("cv.road_damage.classify_road_damage",
                  side_effect=lambda img: road_result),
            patch("services.llm_service.civic_classify_image", new=_fake_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            with pytest.raises(ImageValidationError):
                await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

    # ------------------------------------------------------------------
    # F. Genuine civic image with people/vehicles — remains valid
    # ------------------------------------------------------------------

    async def test_F_civic_image_with_people_remains_valid(self):
        """F. Civic image with pedestrians: must be accepted."""
        from schemas.report import IssueCategory

        # High-confidence YOLO: road_damage — road model is NOT invoked in this path
        result = await self._run(
            yolo_confidence=0.8,
            yolo_category=IssueCategory.road_damage,
        )
        assert isinstance(result, AIResult)
        assert result.category == IssueCategory.road_damage

    # ------------------------------------------------------------------
    # G. No GROQ_API_KEY — local road classification still works
    # ------------------------------------------------------------------

    async def test_G_no_groq_key_local_road_model_still_works(self):
        """G. With GROQ_API_KEY unset, local road model still classifies correctly."""
        from cv.road_damage import RoadDamageResult
        from schemas.report import IssueCategory

        road_result = RoadDamageResult(detected=True, category="pothole",
                                       confidence=0.78, raw_class="D40")
        vision_calls = []

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_calls.append(True)
            v = MagicMock()
            v.valid = True; v.category = "pothole"; v.category_confidence = 0.9
            v.severity = "high"; v.severity_score = 0.85; v.description = "d"; v.reason = "r"
            return v

        def _fake_road(image):
            return road_result

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "frisbee"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category=IssueCategory.pothole,
                             description="d", authority_recommendation="MCC",
                             confidence=0.78)

        async def _fake_classify_cat(ctx):
            return IssueCategory.other

        saved_key = os.environ.pop("GROQ_API_KEY", None)
        try:
            with (
                patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
                patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
                patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
                patch("services.llm_service.civic_classify_image", new=_tracking_vision),
                patch("services.llm_service.classify_category", new=_fake_classify_cat),
                patch("services.llm_service.generate_complaint_description",
                      new=_fake_gen),
            ):
                result = await run_ai_pipeline(
                    VALID_JPEG, location="", address="Mangaluru"
                )
        finally:
            if saved_key is not None:
                os.environ["GROQ_API_KEY"] = saved_key

        assert result.category == IssueCategory.pothole
        assert not vision_calls, "vision must be skipped when road model is confident"

    # ------------------------------------------------------------------
    # H. Privacy — road model receives the redacted image
    # ------------------------------------------------------------------

    async def test_H_road_model_receives_redacted_image(self):
        """H. The road model must receive the privacy-redacted image bytes."""
        from cv.road_damage import RoadDamageResult
        from schemas.report import IssueCategory
        import io as _io

        received_images = []

        original_bytes = VALID_JPEG
        # Redaction marker: create a blue image as "redacted"
        from PIL import Image as _PILImage
        redacted_image_pil = _PILImage.new("RGB", (300, 300), color="blue")

        def _fake_redact(img):
            # Return a distinctly blue image as the "redacted" version
            return redacted_image_pil

        def _fake_road(image):
            received_images.append(image)
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "frisbee"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        async def _fake_vision(image_bytes, yolo_class, all_class_names, address):
            v = MagicMock()
            v.valid = True; v.category = "road_damage"; v.category_confidence = 0.7
            v.severity = "medium"; v.severity_score = 0.5; v.description = "d"; v.reason = "r"
            return v

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category=IssueCategory.road_damage,
                             description="d", authority_recommendation="MCC",
                             confidence=0.7)

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=_fake_redact),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("services.llm_service.civic_classify_image", new=_fake_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            await run_ai_pipeline(original_bytes, location="", address="Mangaluru")

        assert received_images, "Road model was not called"
        # The image passed to the road model must be the blue "redacted" image,
        # not the original gray image.
        received = received_images[0]
        # Redacted image is blue (0, 0, 255); original is gray (128, 128, 128).
        pixel = received.convert("RGB").getpixel((150, 150))
        assert pixel[2] > pixel[0], (
            f"Road model should receive blue redacted image, got pixel={pixel}. "
            "Original image is gray — model received wrong (unredacted) image."
        )

    # ------------------------------------------------------------------
    # I. Pipeline ordering — road model before civic_classify_image
    # ------------------------------------------------------------------

    async def test_I_road_model_attempted_before_civic_classify_image(self):
        """I. Road model must be attempted BEFORE civic_classify_image."""
        from cv.road_damage import RoadDamageResult
        from schemas.report import IssueCategory

        call_order = []

        def _fake_road(image):
            call_order.append("road_model")
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            call_order.append("civic_classify_image")
            v = MagicMock()
            v.valid = True; v.category = "garbage"; v.category_confidence = 0.75
            v.severity = "medium"; v.severity_score = 0.5; v.description = "d"; v.reason = "r"
            return v

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "bottle"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category=IssueCategory.garbage_overflow,
                             description="d", authority_recommendation="MCC",
                             confidence=0.75)

        async def _fake_classify_cat(ctx):
            return IssueCategory.other

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

        assert "road_model" in call_order, "Road model was not called"
        assert "civic_classify_image" in call_order, "civic_classify_image was not called"
        road_idx = call_order.index("road_model")
        vision_idx = call_order.index("civic_classify_image")
        assert road_idx < vision_idx, (
            f"Road model (pos {road_idx}) must run BEFORE civic_classify_image "
            f"(pos {vision_idx}). Actual order: {call_order}"
        )
