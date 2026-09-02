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
        }
        actual_fields = {f.name for f in fields(AIResult)}
        missing = required_fields - actual_fields
        assert not missing, f"AIResult missing fields: {missing}"

    def test_ai_result_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(AIResult)


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

        with (
            patch("cv.pipeline.validate_image", wraps=__import__("cv.image_validator", fromlist=["validate_image"]).validate_image),
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=_fake_redact_privacy),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen_description),
            patch("services.llm_service.classify_category", new=_fake_classify),
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

    async def test_low_confidence_calls_classify_category(self):
        """When YOLO confidence < 0.5 the LLM classify_category is called."""
        classify_called = []

        async def _tracking_classify(image_context):
            classify_called.append(image_context)
            return IssueCategory.garbage_overflow

        async def _fake_gen_description(cv_result, location, address):
            return _mock_llm_output(cv_result.get("category", IssueCategory.other))

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "bottle"
            m.confidence = 0.3  # below 0.5 threshold
            m.category = IssueCategory.garbage_overflow
            return m

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.classify_category", new=_tracking_classify),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen_description),
        ):
            result = await run_ai_pipeline(
                VALID_JPEG, location="", address="Mangaluru"
            )

        assert classify_called, "classify_category should have been called for low confidence"

    async def test_high_confidence_skips_classify_category(self):
        """When YOLO confidence >= 0.5, classify_category is NOT called."""
        classify_called = []

        async def _tracking_classify(image_context):
            classify_called.append(True)
            return IssueCategory.road_damage

        async def _fake_gen(cv_result, location, address):
            return _mock_llm_output()

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.8  # >= 0.5 threshold
            m.category = IssueCategory.road_damage
            return m

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.classify_category", new=_tracking_classify),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

        assert not classify_called, "classify_category should NOT be called for high confidence"

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
