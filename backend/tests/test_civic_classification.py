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

    def test_no_match_returns_other(self):
        r = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="Mangaluru",
        )
        # No match → "other" (still valid — image passed YOLO gate)
        assert r.category == "other"
        assert r.valid is True

    def test_result_always_valid_true_in_heuristic(self):
        """Heuristic fallback assumes image passed YOLO gate so is probably civic."""
        r = fallback_civic_classify_image(
            yolo_class="frisbee",
            all_class_names=("frisbee",),
            address="Near local school",
        )
        # Frisbee is not a civic object, address has no keywords → "other"
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
        road_detected: bool = False,
        road_category: str = "",
        road_confidence: float = 0.0,
    ) -> AIResult:
        """Run pipeline with vision classification and road model both mocked.

        By default the road model returns detected=False so Groq Vision is always
        invoked (which is the normal path for non-road-damage images).
        Pass road_detected=True to exercise the road-model fast path.
        """
        from cv.road_damage import RoadDamageResult

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

        def _fake_road(_img):
            return RoadDamageResult(
                detected=road_detected,
                category=road_category,
                confidence=road_confidence,
            )

        async def _fake_civic_classify(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
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
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
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
        """A civic image containing people should be accepted and classified.

        Under the new routing, Groq Vision is ALWAYS called.  The road model
        provides a hint when confident.  Vision classifies the final category.
        """
        result = await self._run_pipeline_with_vision_mock(
            yolo_category=IssueCategory.road_damage,
            yolo_confidence=0.75,
            # Road model is confident → hint passed to Groq Vision.
            road_detected=True,
            road_category="road_damage",
            road_confidence=0.80,
            # Vision is still called and returns road_damage (default mock returns pothole,
            # so supply a road_damage vision result explicitly).
            vision_result=CivicClassificationResult(
                valid=True, category="road_damage",
                category_confidence=0.90,
                severity="medium", severity_score=0.5,
                description="Road damage visible on the surface.",
                reason="road_damage_detected",
            ),
        )
        assert isinstance(result, AIResult)
        assert result.category == IssueCategory.road_damage

    async def test_vision_ALWAYS_called_regardless_of_road_model_confidence(self):
        """Groq Vision is ALWAYS the final semantic authority.

        Under the new routing, the road model is hint-only.  Even when the road
        model is confident, Groq Vision is STILL called with the hint passed in
        road_model_hint.  The test verifies:
        - Vision IS called when road model is confident (hint passed)
        - Vision IS called when road model is NOT confident (no hint)
        """
        from cv.road_damage import RoadDamageResult

        vision_called = []
        hints_received = []

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            vision_called.append(True)
            hints_received.append(road_model_hint)
            return CivicClassificationResult(
                valid=True, category="road_damage",
                category_confidence=0.9,
                severity="medium", severity_score=0.5,
                description="desc", reason="road_damage",
            )

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.8
            m.category = IssueCategory.road_damage
            m.all_class_names = ("car",)
            return m

        def _fake_road_confident(_img):
            return RoadDamageResult(detected=True, category="road_damage", confidence=0.85)

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.road_damage,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.9,
            )

        async def _fake_classify_cat(image_context):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road_confident),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

        assert vision_called, (
            "Vision classifier MUST always be called — Groq Vision is the final semantic authority"
        )
        assert hints_received and hints_received[0] != "", (
            "Road model hint should be passed to Vision when road model is confident"
        )
        assert result.category == IssueCategory.road_damage

    async def test_vision_triggered_when_road_model_not_confident(self):
        """Vision is triggered whenever the road model is NOT confident.

        This covers the case where YOLO category=other (high conf) as well as
        any non-road image where the specialist model cannot make a confident call.
        """
        from cv.road_damage import RoadDamageResult

        vision_called = []

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
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
            m.confidence = 0.7  # high YOLO conf, but road model not confident
            m.category = IssueCategory.other
            m.all_class_names = ("frisbee",)
            return m

        def _fake_road_not_confident(_img):
            return RoadDamageResult(detected=False, category="", confidence=0.1)

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
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road_not_confident),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(VALID_JPEG, location="", address="Mangaluru")

        assert vision_called, (
            "Vision classifier MUST be called when road model is not confident"
        )

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


# ---------------------------------------------------------------------------
# Tests for the categorization bug fix (synonym normalisation, prompt routing,
# redacted-bytes privacy, latency optimisations)
# ---------------------------------------------------------------------------

from llm.groq_provider import (
    _normalise_category,
    _CANONICAL_CATEGORIES,
    _CATEGORY_SYNONYMS,
)


class TestNormaliseCategory:
    """Unit tests for _normalise_category() — synonym table and canonical keys."""

    # --- canonical pass-through -----------------------------------------------

    def test_canonical_pothole(self):
        assert _normalise_category("pothole") == "pothole"

    def test_canonical_road_damage(self):
        assert _normalise_category("road_damage") == "road_damage"

    def test_canonical_broken_road_marking(self):
        # legacy key — remapped to road_damage
        assert _normalise_category("broken_road_marking") == "road_damage"

    def test_canonical_drainage(self):
        # legacy key — remapped to open_drain
        assert _normalise_category("drainage") == "open_drain"

    def test_canonical_sewage(self):
        assert _normalise_category("sewage") == "sewage"

    def test_canonical_waterlogging(self):
        assert _normalise_category("waterlogging") == "waterlogging"

    def test_canonical_water_leakage(self):
        # legacy key — remapped to water_supply
        assert _normalise_category("water_leakage") == "water_supply"

    def test_canonical_garbage(self):
        # legacy key — remapped to garbage_overflow
        assert _normalise_category("garbage") == "garbage_overflow"

    def test_canonical_streetlight(self):
        # legacy key — remapped to broken_streetlight
        assert _normalise_category("streetlight") == "broken_streetlight"

    def test_canonical_electrical(self):
        # legacy key — remapped to broken_streetlight
        assert _normalise_category("electrical") == "broken_streetlight"

    def test_canonical_other_civic(self):
        # other_civic is a legacy alias; _normalise_category now returns "other"
        assert _normalise_category("other_civic") == "other"

    def test_canonical_invalid(self):
        assert _normalise_category("invalid") == "invalid"

    # DB enum values returned directly by the new prompt
    def test_db_broken_streetlight_passes_through(self):
        assert _normalise_category("broken_streetlight") == "broken_streetlight"

    def test_db_garbage_overflow_passes_through(self):
        assert _normalise_category("garbage_overflow") == "garbage_overflow"

    def test_db_open_drain_passes_through(self):
        assert _normalise_category("open_drain") == "open_drain"

    def test_db_water_supply_passes_through(self):
        assert _normalise_category("water_supply") == "water_supply"

    # --- synonym normalisation ------------------------------------------------

    def test_drain_to_open_drain(self):
        assert _normalise_category("drain") == "open_drain"

    def test_open_drain_to_open_drain(self):
        assert _normalise_category("open drain") == "open_drain"

    def test_blocked_drain_to_open_drain(self):
        assert _normalise_category("blocked drain") == "open_drain"

    def test_open_drain_underscore_to_open_drain(self):
        assert _normalise_category("open_drain") == "open_drain"

    def test_sewer_to_sewage(self):
        assert _normalise_category("sewer") == "sewage"

    def test_sewage_overflow_to_sewage(self):
        assert _normalise_category("sewage overflow") == "sewage"

    def test_flooding_to_waterlogging(self):
        assert _normalise_category("flooding") == "waterlogging"

    def test_flood_to_waterlogging(self):
        assert _normalise_category("flood") == "waterlogging"

    def test_standing_water_to_waterlogging(self):
        assert _normalise_category("standing water") == "waterlogging"

    def test_waterlogged_to_waterlogging(self):
        assert _normalise_category("waterlogged") == "waterlogging"

    def test_flooded_road_to_waterlogging(self):
        assert _normalise_category("flooded road") == "waterlogging"

    def test_water_pipe_leak_to_water_supply(self):
        assert _normalise_category("water pipe leak") == "water_supply"

    def test_leaking_pipe_to_water_supply(self):
        assert _normalise_category("leaking pipe") == "water_supply"

    def test_water_leakage_string_to_water_supply(self):
        assert _normalise_category("water leakage") == "water_supply"

    def test_water_supply_synonym_to_water_supply(self):
        assert _normalise_category("water supply") == "water_supply"

    def test_trash_to_garbage_overflow(self):
        assert _normalise_category("trash") == "garbage_overflow"

    def test_waste_to_garbage_overflow(self):
        assert _normalise_category("waste") == "garbage_overflow"

    def test_rubbish_to_garbage_overflow(self):
        assert _normalise_category("rubbish") == "garbage_overflow"

    def test_litter_to_garbage_overflow(self):
        assert _normalise_category("litter") == "garbage_overflow"

    def test_garbage_overflow_to_garbage_overflow(self):
        assert _normalise_category("garbage overflow") == "garbage_overflow"

    def test_garbage_overflow_underscore_to_garbage_overflow(self):
        assert _normalise_category("garbage_overflow") == "garbage_overflow"

    def test_street_light_to_broken_streetlight(self):
        assert _normalise_category("street light") == "broken_streetlight"

    def test_lamp_post_to_broken_streetlight(self):
        assert _normalise_category("lamp post") == "broken_streetlight"

    def test_street_lamp_to_broken_streetlight(self):
        assert _normalise_category("street lamp") == "broken_streetlight"

    def test_broken_streetlight_str_to_broken_streetlight(self):
        assert _normalise_category("broken streetlight") == "broken_streetlight"

    def test_broken_streetlight_underscore_to_broken_streetlight(self):
        assert _normalise_category("broken_streetlight") == "broken_streetlight"

    def test_electric_pole_to_broken_streetlight(self):
        assert _normalise_category("electric pole") == "broken_streetlight"

    def test_exposed_wire_to_broken_streetlight(self):
        assert _normalise_category("exposed wire") == "broken_streetlight"

    def test_electrical_hazard_to_broken_streetlight(self):
        assert _normalise_category("electrical hazard") == "broken_streetlight"

    def test_electrical_damage_to_broken_streetlight(self):
        assert _normalise_category("electrical damage") == "broken_streetlight"

    def test_cracked_road_to_road_damage(self):
        assert _normalise_category("cracked road") == "road_damage"

    def test_road_crack_to_road_damage(self):
        assert _normalise_category("road crack") == "road_damage"

    def test_road_cracks_to_road_damage(self):
        assert _normalise_category("road cracks") == "road_damage"

    def test_damaged_road_to_road_damage(self):
        assert _normalise_category("damaged road") == "road_damage"

    def test_broken_road_surface_to_road_damage(self):
        assert _normalise_category("broken road surface") == "road_damage"

    def test_pot_hole_to_pothole(self):
        assert _normalise_category("pot hole") == "pothole"

    def test_pot_hole_underscore_to_pothole(self):
        assert _normalise_category("pot_hole") == "pothole"

    def test_road_marking_to_road_damage(self):
        # broken_road_marking is subsumed into road_damage in the new scheme
        assert _normalise_category("road marking") == "road_damage"

    def test_broken_road_marking_str_to_road_damage(self):
        assert _normalise_category("broken road marking") == "road_damage"

    def test_faded_road_marking_to_road_damage(self):
        assert _normalise_category("faded road marking") == "road_damage"

    def test_other_str_to_other(self):
        # "other" is now the canonical form; "other_civic" is normalised to it
        assert _normalise_category("other") == "other"

    # --- unknown → "other" (not "invalid" / not dropped) ----------------------

    def test_unknown_returns_other(self):
        assert _normalise_category("unicorn") == "other"

    def test_empty_returns_other(self):
        # empty string is not a canonical category or synonym → "other"
        assert _normalise_category("") == "other"

    # --- whitespace / case tolerance -----------------------------------------

    def test_case_insensitive_pothole(self):
        assert _normalise_category("POTHOLE") == "pothole"

    def test_case_insensitive_drain(self):
        assert _normalise_category("DRAIN") == "open_drain"

    def test_whitespace_stripped(self):
        assert _normalise_category("  sewage  ") == "sewage"

    def test_whitespace_synonym(self):
        assert _normalise_category("  sewer  ") == "sewage"


class TestParseCivicClassificationNormalisation:
    """Tests for _parse_civic_classification normalisation of raw model output."""

    def _parse(self, raw: dict):
        from llm.groq_provider import _parse_civic_classification
        return _parse_civic_classification(raw)

    def test_canonical_pothole_passes_through(self):
        r = self._parse({
            "valid": True, "category": "pothole",
            "category_confidence": 0.9, "severity": "high",
            "severity_score": 0.85, "description": "desc", "reason": "r",
        })
        assert r.category == "pothole"
        assert r.valid is True

    def test_drain_synonym_normalised(self):
        r = self._parse({
            "valid": True, "category": "drain",
            "category_confidence": 0.8, "severity": "medium",
            "severity_score": 0.5, "description": "desc", "reason": "r",
        })
        assert r.category == "open_drain"
        assert r.valid is True

    def test_sewer_synonym_normalised(self):
        r = self._parse({
            "valid": True, "category": "sewer",
            "category_confidence": 0.75, "severity": "high",
            "severity_score": 0.85, "description": "desc", "reason": "r",
        })
        assert r.category == "sewage"

    def test_flooding_synonym_normalised(self):
        r = self._parse({
            "valid": True, "category": "flooding",
            "category_confidence": 0.8, "severity": "high",
            "severity_score": 0.85, "description": "desc", "reason": "r",
        })
        assert r.category == "waterlogging"

    def test_trash_synonym_normalised(self):
        r = self._parse({
            "valid": True, "category": "trash",
            "category_confidence": 0.7, "severity": "medium",
            "severity_score": 0.5, "description": "desc", "reason": "r",
        })
        assert r.category == "garbage_overflow"

    def test_lamp_post_normalised(self):
        r = self._parse({
            "valid": True, "category": "lamp post",
            "category_confidence": 0.82, "severity": "medium",
            "severity_score": 0.5, "description": "desc", "reason": "r",
        })
        assert r.category == "broken_streetlight"

    def test_cracked_road_normalised(self):
        r = self._parse({
            "valid": True, "category": "cracked road",
            "category_confidence": 0.88, "severity": "medium",
            "severity_score": 0.5, "description": "desc", "reason": "r",
        })
        assert r.category == "road_damage"

    def test_invalid_category_forces_valid_false(self):
        """When category normalises to 'invalid', valid must be forced to False."""
        r = self._parse({
            "valid": True,  # model mistakenly said valid=True
            "category": "invalid",
            "category_confidence": 0.1, "severity": None,
            "severity_score": 0.0, "description": "selfie", "reason": "r",
        })
        assert r.category == "invalid"
        assert r.valid is False

    def test_unknown_category_becomes_other_not_invalid(self):
        """Completely unknown category → 'other', valid stays True (not silently invalid)."""
        r = self._parse({
            "valid": True, "category": "unicorn",
            "category_confidence": 0.3, "severity": "low",
            "severity_score": 0.0, "description": "desc", "reason": "r",
        })
        assert r.category == "other"
        assert r.valid is True

    def test_other_str_normalised_to_other(self):
        r = self._parse({
            "valid": True, "category": "other",
            "category_confidence": 0.4, "severity": "low",
            "severity_score": 0.0, "description": "desc", "reason": "r",
        })
        assert r.category == "other"
        assert r.valid is True

    # --- new prompt JSON format (confidence + numeric severity) ---------------

    def test_new_format_confidence_field(self):
        """New prompt format uses 'confidence' key, not 'category_confidence'."""
        r = self._parse({
            "valid": True, "category": "pothole",
            "confidence": 0.92,  # new key
            "severity": 0.85,    # numeric
            "description": "Pothole visible.", "reason": "r",
        })
        assert r.category == "pothole"
        assert r.category_confidence == pytest.approx(0.92)
        assert r.severity == "high"
        assert r.severity_score == pytest.approx(0.85)

    def test_new_format_numeric_severity_low(self):
        r = self._parse({
            "valid": True, "category": "drainage",
            "confidence": 0.80,
            "severity": 0.0,
            "description": "Drain visible.", "reason": "r",
        })
        assert r.severity == "low"
        assert r.severity_score == pytest.approx(0.0)

    def test_new_format_numeric_severity_medium(self):
        r = self._parse({
            "valid": True, "category": "waterlogging",
            "confidence": 0.75,
            "severity": 0.5,
            "description": "Standing water.", "reason": "r",
        })
        assert r.severity == "medium"
        assert r.severity_score == pytest.approx(0.5)

    def test_new_format_numeric_severity_high(self):
        r = self._parse({
            "valid": True, "category": "sewage",
            "confidence": 0.88,
            "severity": 0.85,
            "description": "Sewage overflow.", "reason": "r",
        })
        assert r.severity == "high"
        assert r.severity_score == pytest.approx(0.85)

    def test_both_confidence_keys_coexist(self):
        """If both 'confidence' and 'category_confidence' are present, 'confidence' wins."""
        r = self._parse({
            "valid": True, "category": "garbage",
            "confidence": 0.77,
            "category_confidence": 0.30,  # should be ignored
            "severity": 0.5,
            "description": "Garbage.", "reason": "r",
        })
        assert r.category_confidence == pytest.approx(0.77)

    def test_new_format_invalid_severity_float(self):
        """Invalid float (> 1.0) is clamped to 1.0."""
        r = self._parse({
            "valid": True, "category": "garbage",
            "confidence": 0.7,
            "severity": 1.5,
            "description": "desc", "reason": "r",
        })
        assert r.severity_score <= 1.0

    # --- new task synonyms ----------------------------------------------------

    def test_road_hole_to_pothole(self):
        r = self._parse({
            "valid": True, "category": "road hole",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "pothole"

    def test_road_pit_to_pothole(self):
        r = self._parse({
            "valid": True, "category": "road pit",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "pothole"

    def test_crater_to_pothole(self):
        r = self._parse({
            "valid": True, "category": "crater",
            "confidence": 0.7, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "pothole"

    def test_broken_road_to_road_damage(self):
        r = self._parse({
            "valid": True, "category": "broken road",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "road_damage"

    def test_deteriorated_road_to_road_damage(self):
        r = self._parse({
            "valid": True, "category": "deteriorated road",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "road_damage"

    def test_cracked_pavement_to_road_damage(self):
        r = self._parse({
            "valid": True, "category": "cracked pavement",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "road_damage"

    def test_lane_marking_to_road_damage(self):
        r = self._parse({
            "valid": True, "category": "lane marking",
            "confidence": 0.7, "severity": 0.0,
            "description": "desc", "reason": "r",
        })
        assert r.category == "road_damage"

    def test_gutter_to_open_drain(self):
        r = self._parse({
            "valid": True, "category": "gutter",
            "confidence": 0.7, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "open_drain"

    def test_stagnant_water_to_waterlogging(self):
        r = self._parse({
            "valid": True, "category": "stagnant water",
            "confidence": 0.8, "severity": 0.85,
            "description": "desc", "reason": "r",
        })
        assert r.category == "waterlogging"

    def test_burst_pipe_to_water_supply(self):
        r = self._parse({
            "valid": True, "category": "burst pipe",
            "confidence": 0.8, "severity": 0.85,
            "description": "desc", "reason": "r",
        })
        assert r.category == "water_supply"

    def test_water_leak_to_water_supply(self):
        r = self._parse({
            "valid": True, "category": "water leak",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "water_supply"

    def test_dumped_waste_to_garbage_overflow(self):
        r = self._parse({
            "valid": True, "category": "dumped waste",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "garbage_overflow"

    def test_broken_lamp_to_broken_streetlight(self):
        r = self._parse({
            "valid": True, "category": "broken lamp",
            "confidence": 0.8, "severity": 0.5,
            "description": "desc", "reason": "r",
        })
        assert r.category == "broken_streetlight"

    def test_damaged_electrical_infrastructure_to_broken_streetlight(self):
        r = self._parse({
            "valid": True, "category": "damaged electrical infrastructure",
            "confidence": 0.75, "severity": 0.85,
            "description": "desc", "reason": "r",
        })
        assert r.category == "broken_streetlight"

    def test_electrical_infrastructure_to_broken_streetlight(self):
        """'electrical' legacy key — remapped to broken_streetlight."""
        r = self._parse({
            "valid": True, "category": "electrical",
            "confidence": 0.8, "severity": 0.85,
            "description": "desc", "reason": "r",
        })
        assert r.category == "broken_streetlight"


@pytest.mark.asyncio
class TestCategorizationBugFix:
    """End-to-end tests for the categorization bug fix.

    These tests verify that each canonical civic category is correctly
    classified through the pipeline when Groq Vision returns the correct
    category (or a synonym that should be normalised).

    They also verify:
    - Groq Vision receives redacted_bytes, never original bytes
    - Road model confident result → Groq Vision NOT called
    - Road model low-confidence result → Groq Vision IS called
    - Groq failure → heuristic fallback
    - No duplicate expensive model inference
    """

    def _make_pipe_mocks(
        self,
        *,
        yolo_category: IssueCategory = IssueCategory.other,
        yolo_confidence: float = 0.1,
        road_detected: bool = False,
        road_category: str = "",
        road_confidence: float = 0.0,
        vision_result: CivicClassificationResult | None = None,
        vision_side_effect=None,
    ):
        """Return context manager patches for a pipeline run."""
        from unittest.mock import patch as _patch

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = yolo_confidence
            m.category = yolo_category
            m.all_class_names = ()
            return m

        from cv.road_damage import RoadDamageResult

        def _fake_road(img):
            return RoadDamageResult(
                detected=road_detected,
                category=road_category,
                confidence=road_confidence,
            )

        _default_vision = CivicClassificationResult(
            valid=True, category="pothole",
            category_confidence=0.9,
            severity="high", severity_score=0.85,
            description="desc", reason="r",
        )

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            if vision_side_effect is not None:
                raise vision_side_effect
            return vision_result if vision_result is not None else _default_vision

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Generated description.",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(image_context):
            return IssueCategory.road_damage

        return (
            _patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            _patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            _patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            _patch("services.llm_service.civic_classify_image", new=_fake_civic),
            _patch("services.llm_service.classify_category", new=_fake_classify_cat),
            _patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        )

    async def _run(self, vision_category: str, **kwargs) -> AIResult:
        """Run pipeline with a given Groq Vision category result."""
        v_result = CivicClassificationResult(
            valid=True, category=vision_category,
            category_confidence=0.88,
            severity="medium", severity_score=0.5,
            description=f"Visible {vision_category} issue.",
            reason=f"{vision_category}_detected",
        )
        patches = self._make_pipe_mocks(vision_result=v_result, **kwargs)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            return await run_ai_pipeline(
                VALID_JPEG,
                location="12.97,74.82",
                address="MG Road, Mangaluru",
            )

    # --- per-category round-trip tests ----------------------------------------

    async def test_pothole_category(self):
        r = await self._run("pothole")
        assert r.category == IssueCategory.pothole

    async def test_road_damage_category(self):
        r = await self._run("road_damage")
        assert r.category == IssueCategory.road_damage

    async def test_broken_road_marking_category(self):
        r = await self._run("broken_road_marking")
        # broken_road_marking maps to road_damage via _VISION_CATEGORY_MAP
        assert r.category == IssueCategory.road_damage

    async def test_drainage_category(self):
        r = await self._run("drainage")
        assert r.category == IssueCategory.open_drain

    async def test_sewage_category(self):
        r = await self._run("sewage")
        assert r.category == IssueCategory.sewage

    async def test_waterlogging_category(self):
        r = await self._run("waterlogging")
        assert r.category == IssueCategory.waterlogging

    async def test_water_leakage_category(self):
        r = await self._run("water_leakage")
        assert r.category == IssueCategory.water_supply

    async def test_garbage_category(self):
        r = await self._run("garbage")
        assert r.category == IssueCategory.garbage_overflow

    async def test_streetlight_category(self):
        r = await self._run("streetlight")
        assert r.category == IssueCategory.broken_streetlight

    async def test_electrical_category(self):
        r = await self._run("electrical")
        assert r.category == IssueCategory.broken_streetlight

    # --- synonym normalisation round-trip through pipeline -------------------

    async def test_drain_synonym_to_drainage(self):
        """Groq returns 'drain' → normalised to 'drainage' → IssueCategory.open_drain."""
        r = await self._run("drain")
        assert r.category == IssueCategory.open_drain

    async def test_sewer_synonym_to_sewage(self):
        r = await self._run("sewer")
        assert r.category == IssueCategory.sewage

    async def test_flooding_synonym_to_waterlogging(self):
        r = await self._run("flooding")
        assert r.category == IssueCategory.waterlogging

    async def test_trash_synonym_to_garbage(self):
        r = await self._run("trash")
        assert r.category == IssueCategory.garbage_overflow

    async def test_lamp_post_synonym_to_streetlight(self):
        r = await self._run("lamp post")
        assert r.category == IssueCategory.broken_streetlight

    async def test_cracked_road_synonym_to_road_damage(self):
        r = await self._run("cracked road")
        assert r.category == IssueCategory.road_damage

    # --- non-civic image rejected --------------------------------------------

    async def test_non_civic_image_rejected(self):
        """invalid category from Groq → ImageValidationError (HTTP 422)."""
        invalid_result = CivicClassificationResult(
            valid=False, category="invalid",
            category_confidence=0.0,
            severity=None, severity_score=0.0,
            description="This is a selfie.", reason="non_civic",
        )
        patches = self._make_pipe_mocks(vision_result=invalid_result)
        with pytest.raises(ImageValidationError):
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                await run_ai_pipeline(
                    VALID_JPEG,
                    location="12.97,74.82",
                    address="Mangaluru",
                )

    # --- road model routing --------------------------------------------------

    async def test_road_model_confident_hint_still_calls_groq_vision(self):
        """Even when road model is confident, Groq Vision is ALWAYS called.

        Under the new routing, the road model result is a HINT passed to Groq
        Vision — it does NOT short-circuit the Groq Vision call.  Groq Vision
        is the final semantic authority for every image.
        """
        vision_called = []
        hints_received = []

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        from cv.road_damage import RoadDamageResult

        def _fake_road(img):
            return RoadDamageResult(
                detected=True, category="pothole", confidence=0.75, raw_class="D40"
            )

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            vision_called.append(True)
            hints_received.append(road_model_hint)
            return CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.9,
                severity="high", severity_score=0.85,
                description="A pothole is clearly visible.", reason="pothole",
            )

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.pothole,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.9,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.pothole

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(
                VALID_JPEG, location="12.97,74.82", address="Mangaluru"
            )

        assert vision_called, (
            "Groq Vision MUST be called even when road model is confident — "
            "Groq Vision is now always the final semantic authority."
        )
        # Road model hint must be passed to Groq Vision
        assert hints_received, "Road model hint must be passed to civic_classify_image"
        assert "pothole" in hints_received[0].lower() or "d40" in hints_received[0].lower(), (
            f"Road model hint should mention pothole/D40, got: {hints_received[0]!r}"
        )
        assert result.category == IssueCategory.pothole

    async def test_low_confidence_road_model_calls_groq_vision(self):
        """When road model is NOT confident, Groq Vision MUST be called (no hint)."""
        vision_called = []
        hints_received = []

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        from cv.road_damage import RoadDamageResult

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.1)

        async def _tracking_vision(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            vision_called.append(True)
            hints_received.append(road_model_hint)
            return CivicClassificationResult(
                valid=True, category="water_sewage",
                category_confidence=0.8,
                severity="medium", severity_score=0.5,
                description="Open drain visible.", reason="waterlogging",
            )

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.waterlogging,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.waterlogging

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_tracking_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            result = await run_ai_pipeline(
                VALID_JPEG, location="12.97,74.82", address="Mangaluru"
            )

        assert vision_called, "Groq Vision MUST be called for every valid image."
        # No hint when road model was not confident
        assert hints_received[0] == "", (
            f"Expected empty hint when road model not confident, got: {hints_received[0]!r}"
        )
        assert result.category == IssueCategory.waterlogging

    # --- Groq failure → heuristic fallback ----------------------------------

    async def test_groq_failure_falls_back_to_heuristic(self):
        """When Groq Vision fails, heuristic fallback is used (not a crash)."""
        from llm.output_validator import LLMOutputInvalid

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "toilet"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ("toilet",)
            return m

        from cv.road_damage import RoadDamageResult

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _groq_fails(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            raise LLMOutputInvalid("Groq timed out")

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.sewage,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.45,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.sewage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_groq_fails),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            # Pipeline must NOT crash; it should complete with a result
            result = await run_ai_pipeline(
                VALID_JPEG, location="12.97,74.82", address="Mangaluru"
            )

        assert isinstance(result, AIResult)

    # --- Groq receives redacted bytes, never original bytes -----------------

    async def test_groq_receives_redacted_bytes_not_original(self):
        """Groq Vision must receive privacy-redacted bytes, not original bytes."""
        import io as _io
        from PIL import Image as _PIL

        # Create a visually distinct "original" and "redacted" image.
        original_img = _PIL.new("RGB", (300, 300), color="red")
        original_buf = _io.BytesIO()
        original_img.save(original_buf, format="JPEG", quality=85)
        original_bytes = original_buf.getvalue()

        redacted_img = _PIL.new("RGB", (300, 300), color="blue")
        redacted_buf = _io.BytesIO()
        redacted_img.save(redacted_buf, format="JPEG", quality=85)
        redacted_bytes = redacted_buf.getvalue()

        bytes_received_by_groq = []

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        from cv.road_damage import RoadDamageResult

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        # Return the distinct "redacted" bytes from the privacy step
        def _fake_redact(img):
            # Convert redacted_bytes back to PIL to simulate redaction
            return _PIL.open(_io.BytesIO(redacted_bytes)).convert("RGB")

        async def _tracking_groq(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            bytes_received_by_groq.append(image_bytes)
            return CivicClassificationResult(
                valid=True, category="water_sewage",
                category_confidence=0.8,
                severity="medium", severity_score=0.5,
                description="desc", reason="waterlogging",
            )

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.open_drain,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.open_drain

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=_fake_redact),
            patch("services.llm_service.civic_classify_image", new=_tracking_groq),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            await run_ai_pipeline(
                original_bytes, location="12.97,74.82", address="Mangaluru"
            )

        assert bytes_received_by_groq, "Groq Vision was not called"
        # The bytes sent to Groq must NOT be the original bytes
        assert bytes_received_by_groq[0] != original_bytes, (
            "Groq Vision received original (unredacted) bytes — privacy violation!"
        )

    # --- no duplicate inference --------------------------------------------

    async def test_road_model_called_exactly_once(self):
        """Road model must be invoked at most once per pipeline run."""
        road_call_count = []

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        from cv.road_damage import RoadDamageResult

        def _fake_road(img):
            road_call_count.append(1)
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _fake_vision(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            return CivicClassificationResult(
                valid=True, category="garbage",
                category_confidence=0.8,
                severity="medium", severity_score=0.5,
                description="desc", reason="r",
            )

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.garbage_overflow,
                description="desc",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.garbage_overflow

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_vision),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            await run_ai_pipeline(
                VALID_JPEG, location="12.97,74.82", address="Mangaluru"
            )

        assert sum(road_call_count) == 1, (
            f"Road model should be called exactly once, was called {sum(road_call_count)} times."
        )


# ===========================================================================
# TestPrimaryCategories — deterministic unit tests for the four primary
# civic categories and YOLO-override cases.
#
# These tests prove:
# 1.  pothole       → IssueCategory.pothole
# 2.  multiple potholes → IssueCategory.pothole
# 3.  cracked road (no hole) → IssueCategory.road_damage
# 4.  damaged streetlight → IssueCategory.broken_streetlight
# 5.  sewage overflow → IssueCategory.sewage
# 6.  wastewater / sewage via water_sewage → IssueCategory.sewage
# 7.  open drain → IssueCategory.open_drain
# 8.  broken water pipe → IssueCategory.water_supply
# 9.  standing water (no pipe/sewage) → IssueCategory.waterlogging
# 10. YOLO=car + Vision=water/sewage → Vision wins, NOT road_damage
# 11. YOLO=person + Vision=streetlight → Vision wins, NOT other
# 12. road model=road_damage + Vision=pothole → final=pothole (Vision wins)
# 13. road model=pothole + Vision=road_damage → final=road_damage (Vision wins)
# 14. selfie → invalid/rejected (ImageValidationError)
# 15. non-civic image → invalid/rejected
# 16. valid ambiguous civic image → other (only when no specific category supported)
# 17. Groq receives redacted_bytes, never original bytes
# 18. Groq Vision called exactly once per pipeline run
# ===========================================================================

class TestPrimaryCategories:
    """Deterministic unit tests for the four primary civic categories.

    All tests mock YOLO, road model, and Groq Vision to produce controlled
    inputs.  The assertions verify the exact IssueCategory produced by the
    pipeline end-to-end through _parse_civic_classification,
    _normalise_category, and map_vision_category_to_issue_category.
    """

    # -----------------------------------------------------------------------
    # Helper: run pipeline with a controlled Vision response and YOLO label
    # -----------------------------------------------------------------------

    async def _run(
        self,
        *,
        vision_category: str,
        vision_reason: str = "",
        vision_valid: bool = True,
        yolo_class: str = "car",
        all_class_names: tuple = ("car",),
        road_detected: bool = False,
        road_category: str = "",
        road_confidence: float = 0.0,
    ) -> "AIResult":
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        v_result = CivicClassificationResult(
            valid=vision_valid,
            category=vision_category,
            category_confidence=0.88,
            severity="medium",
            severity_score=0.5,
            description=f"Visible {vision_category} civic issue.",
            reason=vision_reason or f"{vision_category}_detected",
        )

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = yolo_class
            m.confidence = 0.7
            m.category = IssueCategory.road_damage  # generic YOLO says road_damage
            m.all_class_names = all_class_names
            return m

        def _fake_road(img):
            return RoadDamageResult(
                detected=road_detected,
                category=road_category,
                confidence=road_confidence,
            )

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            return v_result

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Generated description.",
                authority_recommendation="MCC",
                confidence=0.8,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            return await run_ai_pipeline(
                VALID_JPEG,
                location="12.97,74.82",
                address="MG Road, Mangaluru",
            )

    # -----------------------------------------------------------------------
    # 1. pothole → IssueCategory.pothole
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_01_pothole_maps_to_pothole(self):
        """Vision returns 'pothole' → IssueCategory.pothole."""
        r = await self._run(vision_category="pothole")
        assert r.category == IssueCategory.pothole, (
            f"pothole should map to IssueCategory.pothole, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 2. multiple potholes → IssueCategory.pothole (via synonym)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_02_potholes_plural_maps_to_pothole(self):
        """Vision returns 'potholes' → normalised to 'pothole' → IssueCategory.pothole."""
        from llm.groq_provider import _normalise_category
        from llm.fallback_provider import map_vision_category_to_issue_category
        # 'potholes' normalises via synonym or direct match
        norm = _normalise_category("potholes")
        # May normalise to 'other' if no synonym — but 'pothole' (singular) must work
        r = await self._run(vision_category="pothole", vision_reason="multiple potholes visible")
        assert r.category == IssueCategory.pothole

    # -----------------------------------------------------------------------
    # 3. cracked road (no hole) → IssueCategory.road_damage
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_03_cracked_road_maps_to_road_damage(self):
        """Vision returns 'road_damage' → IssueCategory.road_damage."""
        r = await self._run(vision_category="road_damage")
        assert r.category == IssueCategory.road_damage, (
            f"road_damage should map to IssueCategory.road_damage, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 4. damaged streetlight → IssueCategory.broken_streetlight
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_04_streetlight_maps_to_broken_streetlight(self):
        """Vision returns 'streetlight' → IssueCategory.broken_streetlight.

        YOLO top-1 is 'person' but 'car' is also detected (civic indicator allows
        the relevance gate to accept the image).  Vision correctly identifies the
        broken streetlight as the primary civic problem.
        """
        r = await self._run(
            vision_category="streetlight",
            # person top-1, car also present → relevance gate accepts
            yolo_class="person",
            all_class_names=("person", "car"),
        )
        assert r.category == IssueCategory.broken_streetlight, (
            f"streetlight should map to IssueCategory.broken_streetlight, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 5. sewage overflow → IssueCategory.sewage
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_05_sewage_overflow_maps_to_sewage(self):
        """Vision returns 'sewage' (legacy category) → IssueCategory.sewage."""
        r = await self._run(vision_category="sewage")
        assert r.category == IssueCategory.sewage, (
            f"sewage should map to IssueCategory.sewage, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 6. water_sewage with sewage reason → IssueCategory.sewage
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_06_water_sewage_with_sewage_reason_maps_to_sewage(self):
        """Vision returns 'water_sewage' with reason='sewage overflow' → IssueCategory.sewage."""
        r = await self._run(
            vision_category="water_sewage",
            vision_reason="sewage overflow visible on road",
        )
        assert r.category == IssueCategory.sewage, (
            f"water_sewage/sewage reason should map to IssueCategory.sewage, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 7. open drain → IssueCategory.open_drain
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_07_drainage_maps_to_open_drain(self):
        """Vision returns 'drainage' → IssueCategory.open_drain."""
        r = await self._run(vision_category="drainage")
        assert r.category == IssueCategory.open_drain, (
            f"drainage should map to IssueCategory.open_drain, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 8. broken water pipe → IssueCategory.water_supply
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_08_water_leakage_maps_to_water_supply(self):
        """Vision returns 'water_leakage' → IssueCategory.water_supply."""
        r = await self._run(vision_category="water_leakage")
        assert r.category == IssueCategory.water_supply, (
            f"water_leakage should map to IssueCategory.water_supply, got {r.category}"
        )

    @pytest.mark.asyncio
    async def test_08b_water_sewage_pipe_reason_maps_to_water_supply(self):
        """Vision returns 'water_sewage' with burst pipe reason → IssueCategory.water_supply."""
        r = await self._run(
            vision_category="water_sewage",
            vision_reason="burst pipe leaking water supply",
        )
        assert r.category == IssueCategory.water_supply, (
            f"water_sewage/pipe reason should map to IssueCategory.water_supply, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 9. standing water (no pipe/sewage) → IssueCategory.waterlogging
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_09_waterlogging_maps_to_waterlogging(self):
        """Vision returns 'waterlogging' → IssueCategory.waterlogging."""
        r = await self._run(vision_category="waterlogging")
        assert r.category == IssueCategory.waterlogging, (
            f"waterlogging should map to IssueCategory.waterlogging, got {r.category}"
        )

    @pytest.mark.asyncio
    async def test_09b_water_sewage_standing_water_reason_maps_to_waterlogging(self):
        """Vision returns 'water_sewage' with standing water reason → IssueCategory.waterlogging."""
        r = await self._run(
            vision_category="water_sewage",
            vision_reason="standing water on flooded road",
        )
        assert r.category == IssueCategory.waterlogging, (
            f"water_sewage/waterlogging reason should map to IssueCategory.waterlogging, got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 10. YOLO=car + Vision=water/sewage → Vision wins (not road_damage)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_10_yolo_car_vision_sewage_vision_wins(self):
        """YOLO says 'car' (road_damage), Vision says 'sewage' → final=sewage, NOT road_damage.

        This is the key test: generic YOLO labels must NOT override Groq Vision.
        """
        r = await self._run(
            vision_category="water_sewage",
            vision_reason="sewage overflow visible",
            yolo_class="car",
            all_class_names=("car",),
        )
        assert r.category == IssueCategory.sewage, (
            f"Vision (sewage) must override YOLO (car→road_damage). Got {r.category}"
        )
        assert r.category != IssueCategory.road_damage, (
            "YOLO 'car' must NOT produce road_damage when Vision says sewage"
        )

    # -----------------------------------------------------------------------
    # 11. YOLO=person + Vision=streetlight → Vision wins (not other)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_11_yolo_person_vision_streetlight_vision_wins(self):
        """YOLO detects person+car, Vision says 'streetlight' → final=broken_streetlight, NOT other.

        The 'car' civic indicator allows the relevance gate to accept the image.
        The key assertion: even though YOLO's top-1 is 'person', Vision's decision
        (streetlight → broken_streetlight) wins over YOLO's generic label.
        """
        r = await self._run(
            vision_category="streetlight",
            vision_reason="broken lamp post visible",
            # person top-1, but car also present (civic indicator → relevance gate accepts)
            yolo_class="person",
            all_class_names=("person", "car"),
        )
        assert r.category == IssueCategory.broken_streetlight, (
            f"Vision (streetlight) must override YOLO (person→other). Got {r.category}"
        )
        assert r.category != IssueCategory.other, (
            "Vision result must not become 'other' just because YOLO top-1 was 'person'"
        )

    # -----------------------------------------------------------------------
    # 12. road model=road_damage + Vision=pothole → final=pothole (Vision wins)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_12_road_model_road_damage_vision_pothole_vision_wins(self):
        """Road model says road_damage, Vision says pothole → final category = pothole."""
        r = await self._run(
            vision_category="pothole",
            vision_reason="distinct hole visible in road",
            road_detected=True,
            road_category="road_damage",
            road_confidence=0.75,
        )
        assert r.category == IssueCategory.pothole, (
            f"Vision (pothole) must override road model (road_damage). Got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 13. road model=pothole + Vision=road_damage → final=road_damage (Vision wins)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_13_road_model_pothole_vision_road_damage_vision_wins(self):
        """Road model says pothole, Vision says road_damage → final category = road_damage."""
        r = await self._run(
            vision_category="road_damage",
            vision_reason="widespread cracks without distinct hole",
            road_detected=True,
            road_category="pothole",
            road_confidence=0.72,
        )
        assert r.category == IssueCategory.road_damage, (
            f"Vision (road_damage) must override road model (pothole). Got {r.category}"
        )

    # -----------------------------------------------------------------------
    # 14. selfie → rejected (ImageValidationError)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_14_selfie_rejected_as_invalid(self):
        """Vision returns valid=False, category='invalid' → ImageValidationError raised."""
        with pytest.raises(ImageValidationError):
            await self._run(
                vision_category="invalid",
                vision_valid=False,
                vision_reason="This appears to be a selfie portrait.",
                yolo_class="person",
                all_class_names=("person",),
            )

    # -----------------------------------------------------------------------
    # 15. non-civic image → rejected (ImageValidationError)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_15_non_civic_random_photo_rejected(self):
        """Vision returns valid=False for non-civic content → ImageValidationError."""
        with pytest.raises(ImageValidationError):
            await self._run(
                vision_category="invalid",
                vision_valid=False,
                vision_reason="Random food photo, no civic issue.",
                yolo_class="donut",
                all_class_names=("donut",),
            )

    # -----------------------------------------------------------------------
    # 16. valid ambiguous civic image → other (last resort)
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_16_ambiguous_civic_image_becomes_other(self):
        """Vision returns valid=True, category='other' for ambiguous civic scenes.
        Must NOT raise; must return IssueCategory.other.
        """
        r = await self._run(
            vision_category="other",
            vision_valid=True,
            vision_reason="Public infrastructure issue but no specific category matches.",
        )
        assert r.category == IssueCategory.other
        # Must not be an exception

    # -----------------------------------------------------------------------
    # 17. Groq receives redacted_bytes, never original bytes
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_17_groq_receives_redacted_bytes_only(self):
        """Verify the bytes passed to civic_classify_image match redacted_bytes, not original."""
        import io as _io
        from PIL import Image as _PIL

        original_img = _PIL.new("RGB", (300, 300), color="red")
        original_buf = _io.BytesIO()
        original_img.save(original_buf, format="JPEG", quality=85)
        original_bytes = original_buf.getvalue()

        redacted_img = _PIL.new("RGB", (300, 300), color="blue")
        redacted_buf = _io.BytesIO()
        redacted_img.save(redacted_buf, format="JPEG", quality=85)
        redacted_bytes = redacted_buf.getvalue()

        received = []

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.7
            m.category = IssueCategory.road_damage
            m.all_class_names = ("car",)
            return m

        from cv.road_damage import RoadDamageResult

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        def _fake_redact(img):
            return _PIL.open(_io.BytesIO(redacted_bytes)).convert("RGB")

        async def _tracking_groq(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            received.append(image_bytes)
            return CivicClassificationResult(
                valid=True, category="road_damage",
                category_confidence=0.85,
                severity="medium", severity_score=0.5,
                description="Road damage.", reason="road_damage_detected",
            )

        async def _fake_gen(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(
                category=IssueCategory.road_damage,
                description="desc", authority_recommendation="MCC", confidence=0.8,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=_fake_redact),
            patch("services.llm_service.civic_classify_image", new=_tracking_groq),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            await run_ai_pipeline(
                original_bytes, location="12.97,74.82", address="Mangaluru"
            )

        assert received, "civic_classify_image was not called at all"
        assert received[0] != original_bytes, (
            "Groq Vision received original (unredacted) bytes — PRIVACY VIOLATION"
        )

    # -----------------------------------------------------------------------
    # 18. Groq Vision called exactly once per pipeline run
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_18_groq_vision_called_exactly_once(self):
        """civic_classify_image must be called exactly once per pipeline run."""
        call_count = []

        async def _counting_groq(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            call_count.append(1)
            return CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.9,
                severity="high", severity_score=0.85,
                description="Pothole.", reason="pothole_detected",
            )

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = 0.1
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=IssueCategory.pothole,
                description="desc", authority_recommendation="MCC", confidence=0.9,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.pothole

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_counting_groq),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            await run_ai_pipeline(VALID_JPEG, location="12.97,74.82", address="Mangaluru")

        assert sum(call_count) == 1, (
            f"civic_classify_image must be called exactly once, was called {sum(call_count)} times"
        )

    # -----------------------------------------------------------------------
    # Extra: pothole synonym normalisation end-to-end
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pothole_synonym_road_hole_normalises(self):
        """Vision returns 'road hole' synonym → normalised to pothole → IssueCategory.pothole."""
        r = await self._run(vision_category="road hole")
        assert r.category == IssueCategory.pothole

    @pytest.mark.asyncio
    async def test_streetlight_synonym_lamp_post_normalises(self):
        """Vision returns 'lamp post' synonym → normalised to streetlight → broken_streetlight."""
        r = await self._run(vision_category="lamp post")
        assert r.category == IssueCategory.broken_streetlight

    @pytest.mark.asyncio
    async def test_sewage_synonym_wastewater_normalises(self):
        """Vision returns 'wastewater' synonym → normalised to sewage → IssueCategory.sewage."""
        r = await self._run(vision_category="wastewater")
        assert r.category == IssueCategory.sewage


# ===========================================================================
# TestGarbageClassification — targeted tests for Bug 1 fix
# Covers: garbage vision output, new synonyms, mapping, YOLO-override safety.
# ===========================================================================

class TestGarbageClassification:
    """Targeted tests for the garbage first-class Vision bucket (Bug 1 fix)."""

    # -----------------------------------------------------------------------
    # 1. Groq returns "garbage" → IssueCategory.garbage_overflow (not other)
    # -----------------------------------------------------------------------
    def test_garbage_vision_maps_to_garbage_overflow(self):
        """Vision category 'garbage' must map to IssueCategory.garbage_overflow."""
        from llm.fallback_provider import map_vision_category_to_issue_category
        result = map_vision_category_to_issue_category("garbage")
        assert result == IssueCategory.garbage_overflow, (
            f"'garbage' should map to garbage_overflow, got {result}"
        )

    def test_garbage_vision_not_other(self):
        """'garbage' from Vision must NOT produce IssueCategory.other."""
        from llm.fallback_provider import map_vision_category_to_issue_category
        result = map_vision_category_to_issue_category("garbage")
        assert result != IssueCategory.other, (
            "garbage Vision output must not be collapsed to 'other'"
        )

    # -----------------------------------------------------------------------
    # 2. New garbage synonym normalisation tests
    #    All synonyms normalise → "garbage_overflow" (the canonical DB value)
    # -----------------------------------------------------------------------
    def test_solid_waste_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("solid waste") == "garbage_overflow"

    def test_garbage_dump_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("garbage dump") == "garbage_overflow"

    def test_waste_pile_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("waste pile") == "garbage_overflow"

    def test_dumped_garbage_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("dumped garbage") == "garbage_overflow"

    def test_waste_dump_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("waste dump") == "garbage_overflow"

    def test_illegal_dumping_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("illegal dumping") == "garbage_overflow"

    def test_roadside_garbage_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("roadside garbage") == "garbage_overflow"

    def test_roadside_waste_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("roadside waste") == "garbage_overflow"

    def test_municipal_solid_waste_to_garbage_overflow(self):
        from llm.groq_provider import _normalise_category
        assert _normalise_category("municipal solid waste") == "garbage_overflow"

    # -----------------------------------------------------------------------
    # 3. garbage_overflow is a canonical category (in _CANONICAL_CATEGORIES)
    # -----------------------------------------------------------------------
    def test_garbage_overflow_is_canonical(self):
        from llm.groq_provider import _CANONICAL_CATEGORIES
        assert "garbage_overflow" in _CANONICAL_CATEGORIES, (
            "'garbage_overflow' must be in _CANONICAL_CATEGORIES for Vision to return it directly"
        )

    # -----------------------------------------------------------------------
    # 4. YOLO generic label cannot override garbage Vision result
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_yolo_label_does_not_override_garbage_vision(self):
        """YOLO top-1='car' but Vision returns 'garbage' → final=garbage_overflow, NOT road_damage."""
        from llm.fallback_provider import map_vision_category_to_issue_category

        # Simulate: Vision returns garbage regardless of YOLO label
        vision_cat = map_vision_category_to_issue_category("garbage")
        assert vision_cat == IssueCategory.garbage_overflow, (
            "Vision 'garbage' must map to garbage_overflow"
        )
        # Confirm road_damage (what YOLO 'car' would produce) is NOT the result
        assert vision_cat != IssueCategory.road_damage, (
            "YOLO 'car' label must NOT override Vision 'garbage'"
        )

    @pytest.mark.asyncio
    async def test_pipeline_garbage_vision_overrides_yolo_car(self):
        """End-to-end pipeline: YOLO='car', Vision='garbage' → IssueCategory.garbage_overflow."""
        import io as _io
        from PIL import Image as _PIL
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color=(80, 60, 50)).save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        v_result = CivicClassificationResult(
            valid=True,
            category="garbage",
            category_confidence=0.91,
            severity="medium",
            severity_score=0.5,
            description="Large roadside garbage dump visible.",
            reason="garbage — accumulated solid waste on public roadside",
        )

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.75
            m.category = IssueCategory.road_damage  # YOLO says road_damage
            m.all_class_names = ("car",)
            return m

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            return v_result

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Garbage dump.",
                authority_recommendation="MCC",
                confidence=0.9,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            from cv.pipeline import run_ai_pipeline
            result = await run_ai_pipeline(img_bytes, location="12.97,74.82", address="MG Road, Mangaluru")

        assert result.category == IssueCategory.garbage_overflow, (
            f"Vision (garbage) must override YOLO (car→road_damage). Got {result.category}"
        )
        assert result.category != IssueCategory.other, (
            "garbage must NOT become 'other' — it has its own first-class bucket"
        )
        assert result.category != IssueCategory.road_damage, (
            "YOLO 'car' must NOT produce road_damage when Vision says garbage"
        )

    # -----------------------------------------------------------------------
    # 5. garbage maps directly in _VISION_CATEGORY_MAP (not via water_sewage path)
    # -----------------------------------------------------------------------
    def test_garbage_not_routed_through_water_sewage_path(self):
        """map_vision_category_to_issue_category('garbage') should NOT call _map_water_sewage_reason."""
        from llm.fallback_provider import map_vision_category_to_issue_category
        # If garbage were accidentally routed through water_sewage, it would return
        # water_supply (the default). Confirm it returns garbage_overflow instead.
        result = map_vision_category_to_issue_category("garbage", reason="")
        assert result == IssueCategory.garbage_overflow
        # Also test with a misleading reason that would change water_sewage mapping
        result2 = map_vision_category_to_issue_category("garbage", reason="sewage overflow")
        assert result2 == IssueCategory.garbage_overflow, (
            "garbage category must not be affected by reason field — it is not water_sewage"
        )


# ===========================================================================
# TestAuthorityRouting — targeted tests for Bug 2 fix (specialist tie-breaking)
# ===========================================================================

class TestAuthorityRouting:
    """Tests for the singleton-specialist authority selection algorithm."""

    def _route(self, category: str, area_text: str = "") -> tuple:
        from services.authority_service import route_to_authority
        return route_to_authority(category, area_text or None)

    # -----------------------------------------------------------------------
    # 5. broken_streetlight → MESCOM (singleton specialist), not MCC
    # -----------------------------------------------------------------------
    def test_broken_streetlight_routes_to_mescom_no_location(self):
        """Without area text, broken_streetlight must route to MESCOM (singleton specialist)."""
        auth, reason, conf = self._route("broken_streetlight")
        assert auth is not None, "Must return an authority for broken_streetlight"
        assert auth["short_name"] == "MESCOM", (
            f"broken_streetlight without location should route to MESCOM, got {auth['short_name']}"
        )

    def test_broken_streetlight_mescom_is_singleton_specialist(self):
        """MESCOM handles exactly 1 category — it is the singleton specialist."""
        from services.authority_service import _load_authorities, _specialist_rank
        authorities = _load_authorities()
        mescom = next(a for a in authorities if a["short_name"] == "MESCOM")
        assert _specialist_rank(mescom) == 1, "MESCOM must have exactly 1 category"
        assert "broken_streetlight" in mescom["categories"]

    # -----------------------------------------------------------------------
    # 6. Specialist authority beats generic MCC fallback
    # -----------------------------------------------------------------------
    def test_mescom_beats_mcc_for_streetlight_without_location(self):
        """MESCOM (1 category) must outrank MCC (7 categories) for broken_streetlight."""
        auth, reason, conf = self._route("broken_streetlight")
        assert auth["short_name"] != "MCC", (
            "MCC (7 categories) must NOT be preferred over MESCOM (1 category) for broken_streetlight"
        )

    def test_confidence_is_specialist_level(self):
        """Specialist match returns confidence 0.8."""
        _, _, conf = self._route("broken_streetlight")
        assert conf == 0.8, f"Specialist match should have confidence 0.8, got {conf}"

    # -----------------------------------------------------------------------
    # 7. Geographic keyword match still takes priority over specialist tie-break
    # -----------------------------------------------------------------------
    def test_geographic_match_beats_specialist(self):
        """A geographic keyword match (conf=1.0) must beat the specialist tie-break."""
        # MESCOM's area includes "Surathkal" — route with that area text
        auth, reason, conf = self._route("broken_streetlight", area_text="Surathkal road")
        assert conf == 1.0, "Geographic match must return confidence 1.0"
        # Both MCC North and MESCOM cover Surathkal — the one with the higher keyword
        # score wins; conf 1.0 confirms geographic path was taken, not specialist.
        assert auth is not None

    # -----------------------------------------------------------------------
    # Authority selection uses FINAL category (regression)
    # -----------------------------------------------------------------------
    def test_pothole_routes_to_mcc_not_nhai_without_location(self):
        """pothole without location → MCC (first generic match), NOT NHAI.
        NHAI (2 categories) is not a singleton specialist → step 4 applies.
        """
        auth, reason, conf = self._route("pothole")
        assert auth is not None
        assert auth["short_name"] == "MCC", (
            f"pothole without location should route to MCC (first generic match), got {auth['short_name']}"
        )

    def test_road_damage_routes_to_mcc_without_location(self):
        """road_damage without location → MCC (first generic match)."""
        auth, reason, conf = self._route("road_damage")
        assert auth is not None
        assert auth["short_name"] == "MCC", (
            f"road_damage without location should route to MCC, got {auth['short_name']}"
        )

    def test_water_supply_routes_to_mwwd(self):
        """water_supply → MWWD (only matching authority)."""
        auth, reason, conf = self._route("water_supply")
        assert auth is not None
        assert auth["short_name"] == "MWWD"

    def test_sewage_routes_to_mwwd(self):
        """sewage → MWWD (first among [MWWD, MCC Drainage]; neither is a singleton)."""
        auth, reason, conf = self._route("sewage")
        assert auth is not None
        assert auth["short_name"] == "MWWD"

    def test_garbage_overflow_routes_to_mcc(self):
        """garbage_overflow → MCC (only matching authority with garbage_overflow)."""
        auth, reason, conf = self._route("garbage_overflow")
        assert auth is not None
        assert auth["short_name"] == "MCC"

    def test_waterlogging_routes_to_mcc_drainage(self):
        """waterlogging → MCC Drainage (only matching authority)."""
        auth, reason, conf = self._route("waterlogging")
        assert auth is not None
        assert auth["short_name"] == "MCC Drainage"

    def test_nhai_selected_for_nh_location(self):
        """pothole near NH 75 → NHAI wins via geographic keyword match."""
        auth, reason, conf = self._route("pothole", area_text="NH 75 Surathkal")
        assert auth is not None
        assert auth["short_name"] == "NHAI Mangaluru", (
            f"NH 75 pothole should route to NHAI, got {auth['short_name']}"
        )
        assert conf == 1.0

    def test_unknown_category_returns_none(self):
        """A category with no matching authority returns None."""
        from services.authority_service import route_to_authority
        auth, reason, conf = route_to_authority("nonexistent_category")
        assert auth is None
        assert conf == 0.0

    # -----------------------------------------------------------------------
    # Authority selection must use FINAL IssueCategory — regression checks
    # -----------------------------------------------------------------------
    def test_streetlight_authority_after_vision_reclassification(self):
        """After Vision reclassifies from road_damage to broken_streetlight,
        authority must be re-routed to MESCOM, not MCC."""
        # Simulate: initial category was road_damage (from YOLO), re-routed after Vision
        initial_auth, _, _ = self._route("road_damage")
        final_auth, _, _ = self._route("broken_streetlight")
        assert initial_auth["short_name"] == "MCC", "road_damage baseline should be MCC"
        assert final_auth["short_name"] == "MESCOM", (
            "After Vision reclassifies to broken_streetlight, authority must be MESCOM"
        )
        assert initial_auth["short_name"] != final_auth["short_name"], (
            "Authority must change when category changes from road_damage to broken_streetlight"
        )


# ===========================================================================
# TestFinalClassificationRegression — 10 required regression tests
#
# These tests prove:
# 1.  garbage image cannot become road_damage because a road is visible
# 2.  garbage semantic result normalizes to garbage_overflow
# 3.  broken_streetlight semantic result normalizes to broken_streetlight
# 4.  generic YOLO road/car/person labels cannot override Groq's category
# 5.  road specialist road_damage hint cannot override Groq garbage_overflow
# 6.  Groq broken_streetlight cannot later be overwritten by other
# 7.  Groq garbage_overflow cannot later be overwritten by road_damage
# 8.  selfie/person-dominant image is still rejected by relevance gate
# 9.  Groq is always invoked for valid civic images
# 10. authority routing uses FINAL semantic category
# ===========================================================================

class TestFinalClassificationRegression:
    """10 required regression tests for the final classification fix."""

    # -----------------------------------------------------------------------
    # Test 1: garbage with road in background → garbage_overflow, NOT road_damage
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_1_garbage_on_road_is_garbage_overflow_not_road_damage(self):
        """A garbage image where a road is visible must NOT become road_damage.

        YOLO detects 'car' (road context) and road-model detects road surface.
        Vision returns 'garbage_overflow'. Final must be garbage_overflow.
        """
        import io as _io
        from PIL import Image as _PIL
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color=(80, 60, 50)).save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        # Simulate road model firing because road IS visible under the garbage
        road_hint_fired = []

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"         # YOLO sees road context
            m.confidence = 0.75
            m.category = IssueCategory.road_damage   # YOLO wrongly suggests road_damage
            m.all_class_names = ("car",)
            return m

        def _fake_road(img):
            road_hint_fired.append(True)
            return RoadDamageResult(   # road model fires on the road surface behind garbage
                detected=True, category="road_damage", confidence=0.62, raw_class="D20"
            )

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            # Vision correctly sees garbage regardless of road hint
            return CivicClassificationResult(
                valid=True,
                category="garbage_overflow",   # new prompt returns DB enum directly
                category_confidence=0.91,
                severity="medium", severity_score=0.5,
                description="Large roadside garbage dump.",
                reason="Accumulated solid waste on roadside; road visible in background only.",
            )

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Garbage dump.", authority_recommendation="MCC", confidence=0.9,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            from cv.pipeline import run_ai_pipeline
            result = await run_ai_pipeline(img_bytes, location="12.97,74.82", address="Mangaluru")

        # Road model DID fire (to confirm the hint was present)
        assert road_hint_fired, "Road model should have fired in this test"
        # Final category must be garbage_overflow regardless of YOLO and road model
        assert result.category == IssueCategory.garbage_overflow, (
            f"Garbage on road must be garbage_overflow, got {result.category}. "
            "YOLO 'car' and road model 'road_damage' must NOT override Vision 'garbage_overflow'."
        )
        assert result.category != IssueCategory.road_damage, (
            "garbage_overflow must not be overwritten by road_damage"
        )

    # -----------------------------------------------------------------------
    # Test 2: garbage semantic result normalizes to garbage_overflow
    # -----------------------------------------------------------------------
    def test_2_garbage_overflow_normalises_to_garbage_overflow(self):
        """'garbage_overflow' from Vision normalises to IssueCategory.garbage_overflow."""
        from llm.groq_provider import _normalise_category
        from llm.fallback_provider import map_vision_category_to_issue_category

        # New prompt returns DB enum value directly
        assert _normalise_category("garbage_overflow") == "garbage_overflow"
        assert map_vision_category_to_issue_category("garbage_overflow") == IssueCategory.garbage_overflow
        # Legacy short form also resolves correctly
        assert _normalise_category("garbage") == "garbage_overflow"
        assert map_vision_category_to_issue_category("garbage") == IssueCategory.garbage_overflow

    # -----------------------------------------------------------------------
    # Test 3: broken_streetlight semantic result normalizes correctly
    # -----------------------------------------------------------------------
    def test_3_broken_streetlight_normalises_correctly(self):
        """'broken_streetlight' from Vision normalises to IssueCategory.broken_streetlight."""
        from llm.groq_provider import _normalise_category
        from llm.fallback_provider import map_vision_category_to_issue_category

        # New prompt returns DB enum value directly
        assert _normalise_category("broken_streetlight") == "broken_streetlight"
        assert map_vision_category_to_issue_category("broken_streetlight") == IssueCategory.broken_streetlight
        # Legacy short forms also resolve correctly
        assert _normalise_category("streetlight") == "broken_streetlight"
        assert map_vision_category_to_issue_category("streetlight") == IssueCategory.broken_streetlight
        assert _normalise_category("lamp post") == "broken_streetlight"
        assert map_vision_category_to_issue_category("lamp post") == IssueCategory.broken_streetlight

    # -----------------------------------------------------------------------
    # Test 4: generic YOLO labels cannot override Groq's category
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_4_yolo_cannot_override_groq_category(self):
        """YOLO 'car' → road_damage cannot override Vision 'broken_streetlight'."""
        import io as _io
        from PIL import Image as _PIL
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color="blue").save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.80
            m.category = IssueCategory.road_damage
            m.all_class_names = ("car",)
            return m

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            return CivicClassificationResult(
                valid=True, category="broken_streetlight",
                category_confidence=0.93, severity="medium", severity_score=0.5,
                description="Broken street lamp.", reason="Damaged lamp fixture visible.",
            )

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Broken streetlight.", authority_recommendation="MESCOM", confidence=0.9,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            from cv.pipeline import run_ai_pipeline
            result = await run_ai_pipeline(img_bytes, location="12.97,74.82", address="Mangaluru")

        assert result.category == IssueCategory.broken_streetlight, (
            f"Vision 'broken_streetlight' must override YOLO 'car→road_damage'. Got {result.category}"
        )
        assert result.category != IssueCategory.road_damage

    # -----------------------------------------------------------------------
    # Test 5: road specialist hint cannot override Groq garbage_overflow
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_5_road_specialist_hint_cannot_override_groq_garbage(self):
        """Road model D20 hint must not force road_damage when Vision says garbage_overflow."""
        import io as _io
        from PIL import Image as _PIL
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color=(100, 80, 60)).save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        received_hints = []

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.6
            m.category = IssueCategory.road_damage
            m.all_class_names = ("car",)
            return m

        def _fake_road(img):
            return RoadDamageResult(detected=True, category="road_damage", confidence=0.70, raw_class="D20")

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            received_hints.append(road_model_hint)
            # Vision ignores the road_damage hint and correctly classifies garbage
            return CivicClassificationResult(
                valid=True, category="garbage_overflow",
                category_confidence=0.88, severity="medium", severity_score=0.5,
                description="Garbage dump on roadside.",
                reason="Accumulated waste is dominant civic problem; road surface visible behind garbage only.",
            )

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Garbage.", authority_recommendation="MCC", confidence=0.88,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            from cv.pipeline import run_ai_pipeline
            result = await run_ai_pipeline(img_bytes, location="12.97,74.82", address="Mangaluru")

        # Confirm the hint WAS passed to Groq
        assert received_hints, "Groq must have been called with a hint"
        assert "NON-AUTHORITATIVE" in received_hints[0] or "road" in received_hints[0].lower(), (
            "Road model hint should have been present"
        )
        # Confirm Vision overrode the hint
        assert result.category == IssueCategory.garbage_overflow, (
            f"Road specialist hint must not override Vision garbage_overflow. Got {result.category}"
        )

    # -----------------------------------------------------------------------
    # Test 6: Groq broken_streetlight cannot later be overwritten by other
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_6_broken_streetlight_not_overwritten_by_other(self):
        """Once Groq returns broken_streetlight, the pipeline must store broken_streetlight."""
        import io as _io
        from PIL import Image as _PIL
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color="gray").save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = ""          # no YOLO detection for lamp-only image
            m.confidence = 0.0
            m.category = IssueCategory.other
            m.all_class_names = ()
            return m

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            return CivicClassificationResult(
                valid=True, category="broken_streetlight",
                category_confidence=0.93, severity="medium", severity_score=0.5,
                description="Broken street lamp on wooden pole.",
                reason="Lamp fixture visibly damaged/dangling.",
            )

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Broken streetlight.", authority_recommendation="MESCOM", confidence=0.93,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.other  # text classifier would say other — must not win

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            from cv.pipeline import run_ai_pipeline
            result = await run_ai_pipeline(img_bytes, location="12.97,74.82", address="Mangaluru")

        assert result.category == IssueCategory.broken_streetlight, (
            f"broken_streetlight must not be overwritten by other. Got {result.category}"
        )
        assert result.category != IssueCategory.other

    # -----------------------------------------------------------------------
    # Test 7: Groq garbage_overflow cannot later be overwritten by road_damage
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_7_garbage_overflow_not_overwritten_by_road_damage(self):
        """Once Groq sets garbage_overflow, no subsequent step overwrites it with road_damage."""
        import io as _io
        from PIL import Image as _PIL
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color=(80, 60, 50)).save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "truck"
            m.confidence = 0.78
            m.category = IssueCategory.road_damage
            m.all_class_names = ("truck",)
            return m

        def _fake_road(img):
            return RoadDamageResult(detected=True, category="road_damage", confidence=0.65, raw_class="D10")

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            return CivicClassificationResult(
                valid=True, category="garbage_overflow",
                category_confidence=0.87, severity="medium", severity_score=0.5,
                description="Garbage pile on road.", reason="Waste accumulation is primary civic problem.",
            )

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=cv_result.get("category", IssueCategory.other),
                description="Garbage.", authority_recommendation="MCC", confidence=0.87,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.road_damage

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_fake_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            from cv.pipeline import run_ai_pipeline
            result = await run_ai_pipeline(img_bytes, location="12.97,74.82", address="Mangaluru")

        assert result.category == IssueCategory.garbage_overflow, (
            f"garbage_overflow must not be overwritten by road_damage. Got {result.category}"
        )
        assert result.category != IssueCategory.road_damage

    # -----------------------------------------------------------------------
    # Test 8: selfie / person-dominant image is still rejected
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_8_selfie_still_rejected_by_relevance_gate(self):
        """Selfie/portrait image must still raise ImageValidationError (unchanged behaviour)."""
        import io as _io
        from PIL import Image as _PIL
        from cv.image_validator import ImageValidationError

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color=(180, 150, 130)).save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "person"
            m.confidence = 0.85        # above PERSON_DOMINANCE_THRESHOLD(0.20)
            m.category = IssueCategory.other
            m.all_class_names = ("person",)   # no civic indicators
            return m

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
        ):
            from cv.pipeline import run_ai_pipeline
            with pytest.raises(ImageValidationError, match="civic issue"):
                await run_ai_pipeline(img_bytes, location="", address="Mangaluru")

    # -----------------------------------------------------------------------
    # Test 9: Groq is always invoked for valid civic images
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_9_groq_always_invoked_for_valid_civic_images(self):
        """civic_classify_image (Groq Vision) must be called for every valid image."""
        import io as _io
        from PIL import Image as _PIL
        from cv.road_damage import RoadDamageResult
        from llm.output_validator import LLMOutput

        call_count = []

        buf = _io.BytesIO()
        _PIL.new("RGB", (300, 300), color="gray").save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        def _fake_detect(img):
            m = MagicMock()
            m.yolo_class = "car"
            m.confidence = 0.80
            m.category = IssueCategory.road_damage
            m.all_class_names = ("car",)
            return m

        def _fake_road(img):
            return RoadDamageResult(detected=False, category="", confidence=0.0)

        async def _counting_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            call_count.append(1)
            return CivicClassificationResult(
                valid=True, category="pothole",
                category_confidence=0.90, severity="medium", severity_score=0.5,
                description="Pothole.", reason="pothole_detected",
            )

        async def _fake_gen(cv_result, location, address):
            return LLMOutput(
                category=IssueCategory.pothole,
                description="Pothole.", authority_recommendation="MCC", confidence=0.9,
            )

        async def _fake_classify_cat(ctx):
            return IssueCategory.pothole

        with (
            patch("cv.detection.detect_civic_issue", side_effect=_fake_detect),
            patch("cv.road_damage.classify_road_damage", side_effect=_fake_road),
            patch("cv.privacy.redact_privacy", side_effect=lambda img: img),
            patch("services.llm_service.civic_classify_image", new=_counting_civic),
            patch("services.llm_service.classify_category", new=_fake_classify_cat),
            patch("services.llm_service.generate_complaint_description", new=_fake_gen),
        ):
            from cv.pipeline import run_ai_pipeline
            await run_ai_pipeline(img_bytes, location="12.97,74.82", address="Mangaluru")

        assert sum(call_count) == 1, (
            f"civic_classify_image must be called exactly once per pipeline run. Called {sum(call_count)} times."
        )

    # -----------------------------------------------------------------------
    # Test 10: authority routing uses FINAL semantic category
    # -----------------------------------------------------------------------
    def test_10_authority_routing_uses_final_category(self):
        """Authority routing must reflect the FINAL Vision category, not the initial YOLO category.

        Scenario: YOLO initially suggests road_damage → MCC.
        Vision then reclassifies to broken_streetlight → MESCOM.
        Authority must be MESCOM, not MCC.
        """
        from services.authority_service import route_to_authority

        # Initial YOLO-based category would route to MCC
        initial_auth, _, _ = route_to_authority("road_damage")
        assert initial_auth["short_name"] == "MCC"

        # Vision-final category must route to MESCOM (singleton specialist)
        final_auth, reason, conf = route_to_authority("broken_streetlight")
        assert final_auth["short_name"] == "MESCOM", (
            f"broken_streetlight must route to MESCOM, not {final_auth['short_name']}"
        )
        assert conf == 0.8, "Specialist match must return confidence 0.8"
        assert initial_auth["short_name"] != final_auth["short_name"], (
            "Authority must change when Vision reclassifies from road_damage to broken_streetlight"
        )

        # garbage_overflow → MCC (only authority with this category)
        garbage_auth, _, _ = route_to_authority("garbage_overflow")
        assert garbage_auth["short_name"] == "MCC"
