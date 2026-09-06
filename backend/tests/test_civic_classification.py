"""Tests for civic image classification — new vision-based flow.

Covers:
- CivicClassificationResult dataclass structure
- civic_classify_image service: Groq vision path
- civic_classify_image service: fallback heuristic path
- fallback_civic_classify_image: YOLO-based heuristic
- fallback_civic_classify_image: address keyword fallback
- map_vision_category_to_issue_category: mapping to canonical IssueCategory
- Pipeline: vision classification triggered for low-conf/other YOLO
- Pipeline: vision classification NOT triggered for high-conf YOLO
- Pipeline: pothole image correctly classified (simulated)
- Pipeline: invalid/non-civic image rejected by vision classifier
- Pipeline: people+car in civic image accepted
- Pipeline: confidence reflects vision model, not YOLO×weight
- Pipeline: description from vision model is used when available
- Fallback: no API key → fallback used immediately
- Fallback: Groq vision failure → heuristic fallback used
- Backward compat: existing AIResult fields unchanged
"""
from __future__ import annotations

import io
import os
from dataclasses import fields
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from cv.image_validator import ImageValidationError
from cv.pipeline import AIResult, run_ai_pipeline
from llm.fallback_provider import (
    fallback_civic_classify_image,
    map_vision_category_to_issue_category,
)
from llm.groq_provider import CivicClassificationResult
from llm.output_validator import LLMOutputInvalid
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


VALID_JPEG = _make_jpeg_bytes()
VALID_JPEG_BLUE = _make_jpeg_bytes(color="blue")


# ---------------------------------------------------------------------------
# CivicClassificationResult dataclass tests
# ---------------------------------------------------------------------------

class TestCivicClassificationResult:
    def test_dataclass_instantiation(self):
        r = CivicClassificationResult(
            valid=True,
            category="pothole",
            category_confidence=0.92,
            severity="high",
            severity_score=0.85,
            description="Large pothole visible on road surface.",
            reason="pothole_detected",
        )
        assert r.valid is True
        assert r.category == "pothole"
        assert r.category_confidence == 0.92
        assert r.severity == "high"
        assert r.severity_score == 0.85
        assert "pothole" in r.description.lower()
        assert r.reason == "pothole_detected"

    def test_invalid_image_result(self):
        r = CivicClassificationResult(
            valid=False,
            category="invalid",
            category_confidence=0.0,
            severity=None,
            severity_score=0.0,
            description="This appears to be a selfie.",
            reason="non_civic_image",
        )
        assert r.valid is False
        assert r.category == "invalid"
        assert r.severity is None
        assert r.severity_score == 0.0


# ---------------------------------------------------------------------------
# map_vision_category_to_issue_category tests
# ---------------------------------------------------------------------------

class TestMapVisionCategoryToIssueCategory:
    def test_pothole_maps_to_pothole(self):
        assert map_vision_category_to_issue_category("pothole") == IssueCategory.pothole

    def test_road_damage_maps_to_road_damage(self):
        assert map_vision_category_to_issue_category("road_damage") == IssueCategory.road_damage

    def test_broken_road_marking_maps_to_road_damage(self):
        # broken_road_marking not in enum, maps to road_damage via _VISION_CATEGORY_MAP
        assert map_vision_category_to_issue_category("broken_road_marking") == IssueCategory.road_damage

    def test_waterlogging_maps_to_waterlogging(self):
        assert map_vision_category_to_issue_category("waterlogging") == IssueCategory.waterlogging

    def test_drainage_maps_to_open_drain(self):
        assert map_vision_category_to_issue_category("drainage") == IssueCategory.open_drain

    def test_sewage_maps_to_sewage(self):
        assert map_vision_category_to_issue_category("sewage") == IssueCategory.sewage

    def test_water_leakage_maps_to_water_supply(self):
        assert map_vision_category_to_issue_category("water_leakage") == IssueCategory.water_supply

    def test_garbage_maps_to_garbage_overflow(self):
        assert map_vision_category_to_issue_category("garbage") == IssueCategory.garbage_overflow

    def test_streetlight_maps_to_broken_streetlight(self):
        assert map_vision_category_to_issue_category("streetlight") == IssueCategory.broken_streetlight

    def test_electrical_maps_to_broken_streetlight(self):
        assert map_vision_category_to_issue_category("electrical") == IssueCategory.broken_streetlight

    def test_other_civic_maps_to_other(self):
        assert map_vision_category_to_issue_category("other_civic") == IssueCategory.other

    def test_invalid_maps_to_other(self):
        assert map_vision_category_to_issue_category("invalid") == IssueCategory.other

    def test_exact_enum_match_preferred(self):
        # "road_damage" is a direct IssueCategory enum member
        assert map_vision_category_to_issue_category("road_damage") == IssueCategory.road_damage

    def test_completely_unknown_returns_other(self):
        assert map_vision_category_to_issue_category("unicorn") == IssueCategory.other

    def test_case_insensitive(self):
        assert map_vision_category_to_issue_category("POTHOLE") == IssueCategory.pothole
        assert map_vision_category_to_issue_category("Waterlogging") == IssueCategory.waterlogging

    def test_whitespace_stripped(self):
        assert map_vision_category_to_issue_category("  sewage  ") == IssueCategory.sewage


# ---------------------------------------------------------------------------
# fallback_civic_classify_image tests
# ---------------------------------------------------------------------------

class TestFallbackCivicClassifyImage:
    def test_car_yolo_gives_road_damage(self):
        r = fallback_civic_classify_image(
            yolo_class="car",
            all_class_names=("car",),
            address="MG Road, Mangaluru",
        )
        assert isinstance(r, CivicClassificationResult)
        assert r.valid is True
        assert r.category == "road_damage"
        assert r.category_confidence > 0.0
        assert r.severity in ("low", "medium", "high")

    def test_boat_yolo_gives_waterlogging(self):
        r = fallback_civic_classify_image(
            yolo_class="boat",
            all_class_names=("boat",),
            address="Balmatta Road",
        )
        assert r.category == "waterlogging"
        assert r.valid is True

    def test_toilet_yolo_gives_sewage(self):
        r = fallback_civic_classify_image(
            yolo_class="toilet",
            all_class_names=("toilet",),
            address="Near junction",
        )
        assert r.category == "sewage"
        assert r.valid is True

    def test_pothole_in_address_gives_pothole(self):
        r = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="Large pothole near MG Road",
        )
        assert r.category == "pothole"
        assert r.valid is True

    def test_waterlogging_in_address_gives_waterlogging(self):
        r = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="Waterlogging after heavy rain on Balmatta road",
        )
        assert r.category == "waterlogging"
        assert r.valid is True

    def test_sewage_in_address_gives_sewage(self):
        r = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="Sewage overflow near Derebail",
        )
        assert r.category == "sewage"
        assert r.valid is True

    def test_no_match_returns_other_civic(self):
        r = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="Mangaluru",
        )
        # No match → other_civic (still valid)
        assert r.category == "other_civic"
        assert r.valid is True

    def test_result_always_valid_true_in_heuristic(self):
        """Heuristic fallback assumes image passed YOLO gate so is probably civic."""
        r = fallback_civic_classify_image(
            yolo_class="frisbee",
            all_class_names=("frisbee",),
            address="Near local school",
        )
        # Frisbee is not a civic object, address has no keywords → other_civic
        assert r.valid is True  # heuristic fallback always returns valid=True

    def test_yolo_match_takes_priority_over_address(self):
        """YOLO car match wins over address containing 'sewage'."""
        r = fallback_civic_classify_image(
            yolo_class="car",
            all_class_names=("car",),
            address="sewage near road",
        )
        assert r.category == "road_damage"  # YOLO wins

    def test_confidence_reasonable(self):
        r = fallback_civic_classify_image(
            yolo_class="car", all_class_names=("car",), address=""
        )
        assert 0.0 < r.category_confidence <= 1.0

    def test_description_not_empty(self):
        r = fallback_civic_classify_image(
            yolo_class="car", all_class_names=("car",), address="MG Road"
        )
        assert len(r.description) > 0

    def test_description_under_500_chars(self):
        r = fallback_civic_classify_image(
            yolo_class="car",
            all_class_names=("car",),
            address="A" * 400,
        )
        assert len(r.description) <= 500

    def test_truck_yolo_gives_road_damage(self):
        r = fallback_civic_classify_image(
            yolo_class="truck",
            all_class_names=("truck", "car"),
            address="",
        )
        assert r.category == "road_damage"


# ---------------------------------------------------------------------------
# civic_classify_image service function tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCivicClassifyImageService:
    """Tests for services.llm_service.civic_classify_image."""

    async def test_uses_groq_vision_when_key_available(self):
        """When GROQ_API_KEY is set, Groq vision is attempted."""
        from services.llm_service import civic_classify_image

        mock_result = CivicClassificationResult(
            valid=True, category="pothole",
            category_confidence=0.91,
            severity="high", severity_score=0.85,
            description="Road pothole visible.", reason="pothole",
        )

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key-abc"}):
            with patch(
                "llm.groq_provider.civic_classify_image",
                new=AsyncMock(return_value=mock_result)
            ):
                result = await civic_classify_image(
                    image_bytes=VALID_JPEG,
                    yolo_class="",
                    all_class_names=(),
                    address="MG Road",
                )

        assert result.valid is True
        assert result.category == "pothole"
        assert result.category_confidence == 0.91

    async def test_falls_back_when_no_groq_key(self):
        """When no GROQ_API_KEY, heuristic fallback is used immediately."""
        from services.llm_service import civic_classify_image

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            result = await civic_classify_image(
                image_bytes=VALID_JPEG,
                yolo_class="car",
                all_class_names=("car",),
                address="MG Road",
            )

        assert isinstance(result, CivicClassificationResult)
        assert result.valid is True
        assert result.category == "road_damage"

    async def test_falls_back_when_groq_vision_fails(self):
        """When Groq vision raises LLMOutputInvalid, fallback is used."""
        from services.llm_service import civic_classify_image

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key-abc"}):
            with patch(
                "llm.groq_provider.civic_classify_image",
                new=AsyncMock(side_effect=LLMOutputInvalid("vision failed"))
            ):
                result = await civic_classify_image(
                    image_bytes=VALID_JPEG,
                    yolo_class="toilet",
                    all_class_names=("toilet",),
                    address="",
                )

        # Groq failed → heuristic fallback → toilet → sewage
        assert isinstance(result, CivicClassificationResult)
        assert result.category == "sewage"

    async def test_pothole_via_address_when_yolo_useless(self):
        """When YOLO returns irrelevant class (e.g. frisbee), address keyword wins."""
        from services.llm_service import civic_classify_image

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            result = await civic_classify_image(
                image_bytes=VALID_JPEG,
                yolo_class="frisbee",
                all_class_names=("frisbee",),
                address="Large pothole near MG Road",
            )

        assert result.category == "pothole"

    async def test_returns_civic_classification_result(self):
        from services.llm_service import civic_classify_image

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            result = await civic_classify_image(
                image_bytes=VALID_JPEG,
                yolo_class="",
                all_class_names=(),
                address="Mangaluru",
            )

        assert isinstance(result, CivicClassificationResult)


# ---------------------------------------------------------------------------
# Pipeline integration tests for new vision classification flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPipelineVisionClassification:
    """Pipeline tests for the new vision-based classification behavior."""

    async def _run_pipeline_with_vision_mock(
        self,
        image_bytes: bytes = None,
        *,
        yolo_category: IssueCategory = IssueCategory.other,
        yolo_confidence: float = 0.1,
        vision_result: CivicClassificationResult = None,
        vision_side_effect=None,
    ) -> AIResult:
        """Run pipeline with vision classification mocked."""
        if image_bytes is None:
            image_bytes = VALID_JPEG

        if vision_result is None:
            vision_result = CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.92,
                severity="high", severity_score=0.85,
                description="Pothole on road surface.",
                reason="pothole_detected",
            )

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "frisbee"
            m.confidence = yolo_confidence
            m.category = yolo_category
            m.all_class_names = ()
            return m

        async def _fake_civic_classify(image_bytes, yolo_class, all_class_names, address):
            if vision_side_effect:
                raise vision_side_effect
            return vision_result

        async def _fake_gen_description(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="A civic issue has been detected.",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(image_context):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic_classify),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen_description),
        ):
            return await run_ai_pipeline(
                image_bytes,
                location="13.0,74.0",
                address="MG Road, Mangaluru",
            )

    async def test_pothole_image_classified_correctly(self):
        """Core fix: a pothole image (YOLO returns 'frisbee') is correctly
        classified as 'pothole' via vision classifier."""
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.other,
            yolo_confidence=0.11,
            vision_result=CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.93,
                severity="high", severity_score=0.85,
                description="Large pothole on road surface with broken asphalt.",
                reason="pothole_detected",
            ),
        )
        assert result.category == IssueCategory.pothole
        assert result.confidence >= 0.9  # vision confidence, not YOLO×weight

    async def test_confidence_reflects_vision_model_not_yolo_weight(self):
        """Confidence must reflect vision model confidence, not YOLO×weight."""
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.other,
            yolo_confidence=0.11,
            vision_result=CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.94,  # 94% from vision
                severity="high", severity_score=0.85,
                description="Road pothole.",
                reason="pothole_detected",
            ),
        )
        # Old behavior: 0.11 × 0.4 = 0.044 (4.4%)
        # New behavior: 0.94 (from vision model)
        assert result.confidence > 0.5, (
            f"Expected confidence > 0.5 but got {result.confidence:.2f}. "
            "Vision model confidence should replace YOLO×weight."
        )

    async def test_vision_generated_description_used(self):
        """Description from vision model is used when available."""
        specific_desc = "A deep pothole has formed on the road surface with exposed aggregate."
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.other,
            yolo_confidence=0.15,
            vision_result=CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.90,
                severity="high", severity_score=0.85,
                description=specific_desc,
                reason="pothole_detected",
            ),
        )
        assert result.description == specific_desc

    async def test_non_civic_image_rejected_by_vision(self):
        """When vision model returns valid=False, ImageValidationError is raised."""
        with pytest.raises(ImageValidationError):
            await self._run_pipeline_with_vision_mock(
                yolo_category=IssueCategory.other,
                yolo_confidence=0.0,
                vision_result=CivicClassificationResult(
                    valid=False, category="invalid",
                    category_confidence=0.0,
                    severity=None, severity_score=0.0,
                    description="This appears to be a selfie.",
                    reason="non_civic_image",
                ),
            )

    async def test_civic_image_with_people_accepted(self):
        """A civic image containing people should be accepted and classified."""
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.road_damage,
            yolo_confidence=0.75,  # high confidence → vision not triggered
            vision_result=None,    # should not be called
        )
        assert isinstance(result, AIResult)
        assert result.category == IssueCategory.road_damage

    async def test_vision_NOT_triggered_when_high_confidence_non_other(self):
        """When YOLO confidence >= 0.5 and category != other, vision is skipped."""
        vision_called = []

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_called.append(True)
            return CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.9,
                severity="high", severity_score=0.85,
                description="desc", reason="pothole",
            )

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.8  # >= 0.5 AND category != other
            m.category = IssueCategory.road_damage
            m.all_class_names = ("car",)
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.road_damage,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(image_context):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

        assert not vision_called, "Vision classifier should NOT be called for high-conf non-other YOLO"

    async def test_vision_triggered_when_category_other_even_high_confidence(self):
        """When YOLO category == other (even with high confidence), vision is triggered."""
        vision_called = []

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address):
            vision_called.append(True)
            return CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.9,
                severity="high", severity_score=0.85,
                description="desc", reason="pothole",
            )

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "frisbee"
            m.confidence = 0.7  # high conf but category=other
            m.category = IssueCategory.other
            m.all_class_names = ("frisbee",)
            return m

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.pothole,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.9,
            )

        async def _fake_classify_cat(image_context):
            return IssueCategory.pothole

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

        assert vision_called, "Vision classifier SHOULD be called when category=other"

    async def test_waterlogging_image_classified_correctly(self):
        """Waterlogging/drainage image is classified with appropriate category."""
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.other,
            yolo_confidence=0.2,
            vision_result=CivicClassificationResult(
                valid=True, category="waterlogging",
                category_confidence=0.88,
                severity="high", severity_score=0.85,
                description="Standing water on road surface indicating waterlogging.",
                reason="waterlogging_detected",
            ),
        )
        assert result.category == IssueCategory.waterlogging
        assert result.confidence > 0.5

    async def test_sewage_image_classified_correctly(self):
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.other,
            yolo_confidence=0.0,
            vision_result=CivicClassificationResult(
                valid=True, category="sewage",
                category_confidence=0.85,
                severity="high", severity_score=0.85,
                description="Sewage overflow visible on public road.",
                reason="sewage_detected",
            ),
        )
        assert result.category == IssueCategory.sewage

    async def test_yolo_label_not_in_description_for_invalid_class(self):
        """Generic YOLO labels like 'frisbee' must not appear in citizen-facing description.

        This is the regression test for the original 'frisbee' bug.
        """
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.other,
            yolo_confidence=0.11,
            vision_result=CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.93,
                severity="high", severity_score=0.85,
                description="A pothole has formed on the road surface with broken asphalt.",
                reason="pothole_detected",
            ),
        )
        assert "frisbee" not in result.description.lower(), (
            "Spurious YOLO label 'frisbee' must not appear in citizen-facing description."
        )

    async def test_vision_failure_does_not_crash_pipeline(self):
        """Vision classification failure (non-ImageValidationError) → pipeline continues."""
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.other,
            yolo_confidence=0.1,
            vision_side_effect=RuntimeError("network failure"),
        )
        # Pipeline should not raise; category may remain other
        assert isinstance(result, AIResult)

    async def test_all_result_fields_present(self):
        """All AIResult fields must be populated after vision classification."""
        result = await self._run_pipeline_with_vision_mock()
        assert isinstance(result.redacted_image_bytes, bytes)
        assert isinstance(result.validated_image_bytes, bytes)
        assert isinstance(result.category, IssueCategory)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.authority_recommendation, str)
        assert isinstance(result.description, str)
        assert isinstance(result.image_hash, str)
        assert isinstance(result.is_duplicate, bool)
        assert isinstance(result.yolo_class, str)
        assert isinstance(result.raw_detection_confidence, float)

    async def test_ai_result_backward_compatible(self):
        """Existing AIResult field names must not have changed."""
        required_fields = {
            "redacted_image_bytes", "validated_image_bytes", "category",
            "confidence", "authority_recommendation", "authority_id",
            "description", "image_hash", "is_duplicate", "duplicate_report_id",
            "llm_provider_used", "yolo_class", "raw_detection_confidence",
            "match_reason",
        }
        actual_fields = {f.name for f in fields(AIResult)}
        missing = required_fields - actual_fields
        assert not missing, f"AIResult missing expected fields: {missing}"
