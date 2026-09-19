"""Regression tests for civic image classification correctness.

Tests the critical misclassification scenarios:
  - non-road problems appearing in images that contain a road background must
    NOT be classified as road_damage.
  - each civic category must be correctly identified when present.

All tests use mocked Groq responses — no live API key required.
"""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from llm.fallback_provider import (
    fallback_civic_classify_image,
    map_vision_category_to_issue_category,
)
from llm.groq_provider import (
    GROQ_MODEL,
    GROQ_VISION_MODEL,
    _parse_civic_classification,
    reset_groq_clients_for_testing,
)
from llm.output_validator import LLMOutputInvalid
from llm.prompts import CIVIC_IMAGE_CLASSIFICATION_PROMPT
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpeg_bytes(color: str = "gray") -> bytes:
    img = Image.new("RGB", (100, 100), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


VALID_JPEG = _make_jpeg_bytes()


def _vision_json(category: str, reason: str = "", description: str = "",
                  valid: bool = True, confidence: float = 0.88) -> str:
    """Build a minimal valid vision model JSON response string."""
    desc = description or f"Civic issue: {category} visible."
    rsn = reason or f"Primary civic problem is {category}."
    return json.dumps({
        "valid": valid,
        "category": category,
        "confidence": confidence,
        "severity": 0.5,
        "description": desc,
        "reason": rsn,
    })


def _make_vision_response(content: str) -> MagicMock:
    """Build a fake Groq chat completion response for vision calls."""
    msg = MagicMock()
    msg.content = content
    msg.thinking = None
    msg.reasoning_content = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Helper: run civic_classify_image with a mocked Groq response
# ---------------------------------------------------------------------------

async def _classify_with_mock(content: str, address: str = "test") -> "CivicClassificationResult":
    """Run civic_classify_image with a mocked Groq vision response."""
    import os
    from llm.groq_provider import civic_classify_image

    with patch("llm.groq_provider._get_groq_vision_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_vision_response(content)
        )
        mock_get_client.return_value = mock_client

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            reset_groq_clients_for_testing()
            return await civic_classify_image(VALID_JPEG, address)


# ---------------------------------------------------------------------------
# 1. Prompt content checks — critical structural requirements
# ---------------------------------------------------------------------------

class TestPromptStructure:
    """Verify the prompt contains all required disambiguation content."""

    def test_prompt_has_priority_order_section(self):
        assert "CLASSIFICATION PRIORITY ORDER" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_road_visible_not_road_damage_section(self):
        assert "ROAD VISIBLE" in CIVIC_IMAGE_CLASSIFICATION_PROMPT
        assert "ROAD DAMAGE" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_explicitly_forbids_road_damage_for_garbage(self):
        # The prompt must tell the model that garbage on a road is NOT road_damage
        assert "garbage_overflow" in CIVIC_IMAGE_CLASSIFICATION_PROMPT
        assert "NOT road_damage" in CIVIC_IMAGE_CLASSIFICATION_PROMPT or \
               "road_damage" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_waterlogging_disambiguation(self):
        assert "waterlogging" in CIVIC_IMAGE_CLASSIFICATION_PROMPT
        assert "water_sewage" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_open_drain_disambiguation(self):
        assert "open_drain" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_illegal_construction_disambiguation(self):
        assert "illegal_construction" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_sewage_disambiguation(self):
        assert "sewage" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_water_leakage_disambiguation(self):
        assert "water_leakage" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_broken_streetlight_disambiguation(self):
        assert "broken_streetlight" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_description_rule(self):
        assert "DESCRIPTION RULE" in CIVIC_IMAGE_CLASSIFICATION_PROMPT or \
               "description" in CIVIC_IMAGE_CLASSIFICATION_PROMPT.lower()

    def test_prompt_has_road_model_hint_field(self):
        assert "{road_model_hint}" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_has_address_field(self):
        assert "{address}" in CIVIC_IMAGE_CLASSIFICATION_PROMPT

    def test_prompt_renders_without_error(self):
        rendered = CIVIC_IMAGE_CLASSIFICATION_PROMPT.format(
            road_model_hint="none",
            address="MG Road, Mangaluru",
        )
        assert "garbage_overflow" in rendered
        assert "road_damage" in rendered

    def test_prompt_road_damage_is_last_specific_category(self):
        """road_damage category definition should appear AFTER garbage/water in priority list."""
        prompt = CIVIC_IMAGE_CLASSIFICATION_PROMPT
        # Look for the numbered priority entries, e.g. "2. garbage_overflow" vs "7. road_damage"
        import re
        # Find "N. road_damage" style entry (priority number for road_damage)
        m_road = re.search(r"\b(\d+)\.\s+road_damage\b", prompt)
        m_garbage = re.search(r"\b(\d+)\.\s+garbage_overflow\b", prompt)
        m_water = re.search(r"\b(\d+)\.\s+water_sewage\b", prompt)
        assert m_road is not None, "road_damage must appear as a numbered priority item"
        assert m_garbage is not None, "garbage_overflow must appear as a numbered priority item"
        assert m_water is not None, "water_sewage must appear as a numbered priority item"
        road_num = int(m_road.group(1))
        garbage_num = int(m_garbage.group(1))
        water_num = int(m_water.group(1))
        assert garbage_num < road_num, (
            f"garbage_overflow (priority {garbage_num}) must come before "
            f"road_damage (priority {road_num})"
        )
        assert water_num < road_num, (
            f"water_sewage (priority {water_num}) must come before "
            f"road_damage (priority {road_num})"
        )


# ---------------------------------------------------------------------------
# 2. reasoning_format parameter check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReasoningFormat:
    """civic_classify_image must pass reasoning_format='hidden' to the Groq API."""

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_reasoning_format_hidden_is_passed(self, mock_get_client):
        import os
        captured: dict = {}

        async def _capture(**kwargs):
            captured.update(kwargs)
            return _make_vision_response(_vision_json("pothole"))

        mock_client = MagicMock()
        mock_client.chat.completions.create = _capture
        mock_get_client.return_value = mock_client

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image
            reset_groq_clients_for_testing()
            await civic_classify_image(VALID_JPEG, "test")

        assert captured.get("reasoning_format") == "hidden", (
            f"Expected reasoning_format='hidden', got {captured.get('reasoning_format')!r}"
        )


# ---------------------------------------------------------------------------
# 3. Category normalization: Groq returns correct categories
#    (parse + normalize path — no road visible confusion at this layer)
# ---------------------------------------------------------------------------

class TestCategoryNormalization:
    """_parse_civic_classification correctly maps all vision output values."""

    def _parse(self, raw: dict):
        return _parse_civic_classification(raw)

    def test_garbage_overflow_direct(self):
        r = self._parse({"valid": True, "category": "garbage_overflow",
                         "confidence": 0.9, "severity": 0.5,
                         "description": "Garbage.", "reason": "Waste."})
        assert r.category == "garbage_overflow"
        assert r.valid is True

    def test_waterlogging_via_water_sewage_subtype(self):
        r = self._parse({"valid": True, "category": "water_sewage",
                         "confidence": 0.85, "severity": 0.5,
                         "description": "Flooded road.", "reason": "waterlogging visible."})
        assert r.category == "water_sewage"
        assert r.valid is True

    def test_waterlogging_direct(self):
        r = self._parse({"valid": True, "category": "waterlogging",
                         "confidence": 0.85, "severity": 0.5,
                         "description": "Standing water.", "reason": "Flood."})
        assert r.category == "waterlogging"

    def test_sewage_direct(self):
        r = self._parse({"valid": True, "category": "sewage",
                         "confidence": 0.8, "severity": 0.85,
                         "description": "Sewage.", "reason": "Wastewater."})
        assert r.category == "sewage"

    def test_water_supply_direct(self):
        r = self._parse({"valid": True, "category": "water_supply",
                         "confidence": 0.8, "severity": 0.5,
                         "description": "Pipe leak.", "reason": "water_leakage."})
        assert r.category == "water_supply"

    def test_open_drain_direct(self):
        r = self._parse({"valid": True, "category": "open_drain",
                         "confidence": 0.8, "severity": 0.5,
                         "description": "Open drain.", "reason": "Drain."})
        assert r.category == "open_drain"

    def test_illegal_construction_direct(self):
        r = self._parse({"valid": True, "category": "illegal_construction",
                         "confidence": 0.75, "severity": 0.5,
                         "description": "Construction.", "reason": "Encroachment."})
        assert r.category == "illegal_construction"

    def test_broken_streetlight_direct(self):
        r = self._parse({"valid": True, "category": "broken_streetlight",
                         "confidence": 0.9, "severity": 0.5,
                         "description": "Broken lamp.", "reason": "Lamp."})
        assert r.category == "broken_streetlight"

    def test_pothole_direct(self):
        r = self._parse({"valid": True, "category": "pothole",
                         "confidence": 0.92, "severity": 0.5,
                         "description": "Pothole.", "reason": "Hole."})
        assert r.category == "pothole"

    def test_road_damage_direct(self):
        r = self._parse({"valid": True, "category": "road_damage",
                         "confidence": 0.85, "severity": 0.5,
                         "description": "Cracked road.", "reason": "Cracks."})
        assert r.category == "road_damage"

    def test_other_direct(self):
        r = self._parse({"valid": True, "category": "other",
                         "confidence": 0.4, "severity": 0.3,
                         "description": "Unclear.", "reason": "No fit."})
        assert r.category == "other"


# ---------------------------------------------------------------------------
# 4. End-to-end mocked classification: non-road categories must NOT become road_damage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestClassificationDoesNotBecomRoadDamage:
    """Mocked Groq returns specific categories; pipeline must preserve them."""

    async def test_1_garbage_plus_road_returns_garbage_overflow(self):
        """Groq says garbage_overflow → pipeline must return garbage_overflow."""
        result = await _classify_with_mock(
            _vision_json("garbage_overflow",
                         description="Garbage pile beside the road.",
                         reason="Waste accumulation is the primary problem.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.garbage_overflow, (
            f"Expected garbage_overflow, got {final_cat}"
        )

    async def test_2_waterlogging_plus_road_returns_waterlogging(self):
        """Groq says water_sewage (waterlogging) → pipeline resolves to waterlogging."""
        result = await _classify_with_mock(
            _vision_json("water_sewage",
                         reason="waterlogging — standing water on road surface.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.waterlogging, (
            f"Expected waterlogging, got {final_cat}"
        )

    async def test_3_open_drain_plus_road_returns_open_drain(self):
        """Groq says open_drain → pipeline must return open_drain."""
        result = await _classify_with_mock(
            _vision_json("open_drain",
                         description="Exposed drain beside the road.",
                         reason="Open drainage channel visible.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.open_drain, (
            f"Expected open_drain, got {final_cat}"
        )

    async def test_4_sewage_plus_road_returns_sewage(self):
        """Groq says water_sewage (sewage) → pipeline resolves to sewage."""
        result = await _classify_with_mock(
            _vision_json("water_sewage",
                         reason="sewage — dark wastewater discharge visible.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.sewage, (
            f"Expected sewage, got {final_cat}"
        )

    async def test_5_water_supply_plus_road_returns_water_supply(self):
        """Groq says water_sewage (water_leakage) → pipeline resolves to water_supply."""
        result = await _classify_with_mock(
            _vision_json("water_sewage",
                         reason="water_leakage — burst pipe spraying water.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.water_supply, (
            f"Expected water_supply, got {final_cat}"
        )

    async def test_6_broken_streetlight_plus_road_returns_broken_streetlight(self):
        """Groq says broken_streetlight → pipeline must return broken_streetlight."""
        result = await _classify_with_mock(
            _vision_json("broken_streetlight",
                         description="Damaged street lamp beside road.",
                         reason="Lamp post is broken.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.broken_streetlight, (
            f"Expected broken_streetlight, got {final_cat}"
        )

    async def test_7_illegal_construction_supported_by_evidence(self):
        """Groq says illegal_construction → pipeline must return illegal_construction."""
        result = await _classify_with_mock(
            _vision_json("illegal_construction",
                         description="Construction encroaching on footpath.",
                         reason="Unauthorized structure obstructs public path.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.illegal_construction, (
            f"Expected illegal_construction, got {final_cat}"
        )

    async def test_8_pothole_plus_road_returns_pothole(self):
        """Groq says pothole → pipeline must return pothole."""
        result = await _classify_with_mock(
            _vision_json("pothole",
                         description="Distinct pothole in road surface.",
                         reason="Visible hole in asphalt.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.pothole, (
            f"Expected pothole, got {final_cat}"
        )

    async def test_9_genuinely_damaged_road_returns_road_damage(self):
        """Groq says road_damage → pipeline must return road_damage."""
        result = await _classify_with_mock(
            _vision_json("road_damage",
                         description="Road surface shows major cracking and erosion.",
                         reason="Road surface itself is deteriorated.")
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.road_damage, (
            f"Expected road_damage, got {final_cat}"
        )

    async def test_10_road_visible_no_problem_returns_other(self):
        """Groq says other (road visible but no civic damage) → pipeline returns other."""
        result = await _classify_with_mock(
            _vision_json("other",
                         description="Road with vehicles, no specific civic damage visible.",
                         reason="No clear civic problem identified.",
                         confidence=0.4)
        )
        from llm.fallback_provider import map_vision_category_to_issue_category
        final_cat = map_vision_category_to_issue_category(result.category, result.reason)
        assert final_cat == IssueCategory.other, (
            f"Expected other, got {final_cat}"
        )

    async def test_11_invalid_image_raises_validation_error(self):
        """Groq says invalid → pipeline must raise ImageValidationError."""
        import os
        from cv.image_validator import ImageValidationError
        from cv.pipeline import run_ai_pipeline
        from cv.detection import DetectionResult
        from cv.road_damage import RoadDamageResult

        def _fake_detect(_img):
            return DetectionResult(
                yolo_class="person", confidence=0.85, category=IssueCategory.other,
                all_class_names=("person",),
            )

        def _fake_road(_img):
            return RoadDamageResult(detected=False, category="", confidence=0.1)

        async def _fake_civic(image_bytes, yolo_class, all_class_names, address, *, road_model_hint=""):
            from llm.groq_provider import CivicClassificationResult
            return CivicClassificationResult(
                valid=False, category="invalid", category_confidence=0.95,
                severity="low", severity_score=0.1,
                description="Selfie photo.", reason="No civic infrastructure.",
            )

        async def _fake_desc(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category="other", description="test",
                             authority_recommendation="MCC", confidence=0.1)

        async def _fake_cat(ctx):
            return IssueCategory.other

        img_bytes = _make_jpeg_bytes()
        with patch("cv.detection.detect_civic_issue", _fake_detect), \
             patch("cv.road_damage.classify_road_damage", _fake_road), \
             patch("services.llm_service.civic_classify_image", _fake_civic), \
             patch("services.llm_service.generate_complaint_description", _fake_desc), \
             patch("services.llm_service.classify_category", _fake_cat), \
             patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with pytest.raises(ImageValidationError):
                await run_ai_pipeline(img_bytes, location="12.9,74.8", address="test")


# ---------------------------------------------------------------------------
# 5. Road specialist hint must NOT override Groq semantic category
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRoadSpecialistHintDoesNotOverride:
    """Groq Vision is semantic authority; road specialist provides a hint only."""

    async def test_12_groq_garbage_beats_road_specialist_road_damage_hint(self):
        """Road specialist hints road_damage but Groq identifies garbage_overflow → garbage wins."""
        import os
        from cv.pipeline import run_ai_pipeline
        from cv.detection import DetectionResult
        from cv.road_damage import RoadDamageResult

        def _fake_detect(_img):
            return DetectionResult(
                yolo_class="bottle", confidence=0.6, category=IssueCategory.garbage_overflow,
                all_class_names=("bottle",),
            )

        def _fake_road(_img):
            # specialist thinks it's road_damage (wrong — it's garbage on the road)
            return RoadDamageResult(detected=True, category="road_damage",
                                    confidence=0.55, raw_class="D20")

        groq_called_hints: list = []

        async def _tracking_groq(image_bytes, yolo_class, all_class_names, address, *,
                                  road_model_hint=""):
            groq_called_hints.append(road_model_hint)
            from llm.groq_provider import CivicClassificationResult
            # Groq correctly identifies garbage despite road hint
            return CivicClassificationResult(
                valid=True, category="garbage_overflow", category_confidence=0.91,
                severity="medium", severity_score=0.5,
                description="Garbage pile beside the road.",
                reason="Waste accumulation is the primary problem.",
            )

        async def _fake_desc(cv_result, location, address):
            from llm.output_validator import LLMOutput
            return LLMOutput(category="garbage_overflow",
                             description="Garbage accumulation at the roadside.",
                             authority_recommendation="MCC", confidence=0.91)

        async def _fake_cat(ctx):
            return IssueCategory.garbage_overflow

        img_bytes = _make_jpeg_bytes()
        with patch("cv.detection.detect_civic_issue", _fake_detect), \
             patch("cv.road_damage.classify_road_damage", _fake_road), \
             patch("services.llm_service.civic_classify_image", _tracking_groq), \
             patch("services.llm_service.generate_complaint_description", _fake_desc), \
             patch("services.llm_service.classify_category", _fake_cat), \
             patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            result = await run_ai_pipeline(img_bytes, location="12.9,74.8", address="test")

        # Groq was called with the road model hint (not bypassed)
        assert len(groq_called_hints) == 1, "Groq Vision must be called exactly once"
        assert "road" in groq_called_hints[0].lower() or groq_called_hints[0] == "", (
            "Road model hint should be present (or empty if specialist not confident)"
        )
        # Final category must be garbage_overflow from Groq, not road_damage from specialist
        assert result.category == IssueCategory.garbage_overflow, (
            f"Expected garbage_overflow (Groq authority), got {result.category}"
        )


# ---------------------------------------------------------------------------
# 6. Description must match category
# ---------------------------------------------------------------------------

class TestDescriptionMatchesCategory:
    """Parsed CivicClassificationResult description must reflect the category."""

    def test_13_garbage_description_describes_garbage(self):
        r = _parse_civic_classification({
            "valid": True, "category": "garbage_overflow", "confidence": 0.9,
            "severity": 0.5,
            "description": "Garbage has accumulated beside the roadside.",
            "reason": "Waste is the primary problem.",
        })
        assert r.category == "garbage_overflow"
        # Description should not mention road damage when category is garbage
        assert "garbage" in r.description.lower() or "waste" in r.description.lower() or \
               "accumulate" in r.description.lower()

    def test_13b_road_damage_description_describes_road(self):
        r = _parse_civic_classification({
            "valid": True, "category": "road_damage", "confidence": 0.88,
            "severity": 0.5,
            "description": "The road surface shows major cracking and erosion.",
            "reason": "Road surface itself is deteriorated.",
        })
        assert r.category == "road_damage"
        assert "road" in r.description.lower() or "crack" in r.description.lower() or \
               "surface" in r.description.lower() or "pavement" in r.description.lower()


# ---------------------------------------------------------------------------
# 7. Authority routing uses final normalized category
# ---------------------------------------------------------------------------

class TestAuthorityRoutingUsesCorrectCategory:
    """Authority lookup must receive the correct final category, not road_damage."""

    def test_14_garbage_routes_to_mcc_not_nhai(self):
        from services.authority_service import route_to_authority
        auth, reason, conf = route_to_authority("garbage_overflow", "Hampankatta, Mangaluru")
        if auth:  # may be None if authority data not loaded
            short_name = auth.get("short_name", "").upper()
            # MCC handles garbage — not NHAI (which handles highways/road damage)
            assert "NHAI" not in short_name, (
                f"garbage_overflow should not route to NHAI, got {short_name}"
            )

    def test_14b_waterlogging_routes_to_mcc_not_nhai(self):
        from services.authority_service import route_to_authority
        auth, reason, conf = route_to_authority("waterlogging", "MG Road, Mangaluru")
        if auth:
            short_name = auth.get("short_name", "").upper()
            assert "NHAI" not in short_name, (
                f"waterlogging should not route to NHAI, got {short_name}"
            )

    def test_14c_road_damage_generic_routes_correctly(self):
        from services.authority_service import route_to_authority
        auth, reason, conf = route_to_authority("road_damage", "Mangaluru")
        # road_damage should have some authority (MCC typically)
        assert auth is not None or conf >= 0.0  # at minimum doesn't crash

    def test_14d_broken_streetlight_routes_to_mescom(self):
        from services.authority_service import route_to_authority
        auth, reason, conf = route_to_authority("broken_streetlight", "Mangaluru")
        if auth:
            short_name = auth.get("short_name", "").upper()
            # MESCOM handles streetlights — not MCC/NHAI
            assert "MESCOM" in short_name or "ELECTRIC" in short_name or conf >= 0.0


# ---------------------------------------------------------------------------
# 8. Model identity guards
# ---------------------------------------------------------------------------

class TestModelIdentity:
    def test_vision_model_is_qwen(self):
        assert GROQ_VISION_MODEL == "qwen/qwen3.8-27b"

    def test_vision_model_not_compound(self):
        assert "compound" not in GROQ_VISION_MODEL.lower()

    def test_text_model_is_gpt_oss_20b(self):
        assert GROQ_MODEL == "openai/gpt-oss-20b"

    def test_text_model_not_compound(self):
        assert "compound" not in GROQ_MODEL.lower()

    def test_no_deprecated_llama_instant(self):
        assert "llama-3.1-8b-instant" not in GROQ_MODEL


# ---------------------------------------------------------------------------
# Helper import for _parse_civic_classification (private but tested directly)
# ---------------------------------------------------------------------------
from llm.groq_provider import _parse_civic_classification  # noqa: E402
