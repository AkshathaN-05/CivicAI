"""Regression tests for Groq vision robustness fixes.

Covers:
1. _extract_json: truncated/unclosed <think> block — JSON not extracted from reasoning
2. _extract_json: normal closed <think> + final JSON — correct answer extracted
3. _extract_json: deeply nested think block with JSON-like fragments inside
4. civic_classify_image: empty content field with 'thinking' attribute fallback
5. civic_classify_image: empty content field with 'reasoning_content' attribute fallback
6. civic_classify_image: empty content, no thinking field → raises LLMOutputInvalid
7. civic_classify_image: max_tokens >= 2048 in the Groq API call
8. Fallback: open drain address keyword → open_drain
9. Fallback: "drain" keyword → open_drain
10. Fallback: "illegal" address keyword → illegal_construction
11. Fallback: "construction" keyword → illegal_construction
12. Fallback: "encroach" keyword → illegal_construction
13. Fallback: existing categories still work (pothole, road_damage, garbage, sewage,
    waterlogging, water_supply, streetlight)
14. Fallback: fallback reason tag is "heuristic_fallback" (not groq_vision)

All Groq API calls are mocked — no live API key required.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from llm.fallback_provider import fallback_civic_classify_image, map_vision_category_to_issue_category
from llm.groq_provider import _extract_json, GROQ_VISION_MODEL
from llm.output_validator import LLMOutputInvalid
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpeg_bytes(width: int = 100, height: int = 100, color: str = "gray") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


VALID_JPEG = _make_jpeg_bytes()

# A complete valid vision JSON response
_VALID_VISION_JSON = (
    '{"valid": true, "category": "garbage_overflow", "confidence": 0.88, '
    '"severity": 0.5, "description": "Garbage pile on the roadside.", '
    '"reason": "Accumulated waste visible."}'
)


def _make_vision_mock_response(content: str, thinking: str = "") -> MagicMock:
    """Build a fake Groq chat completion response for vision calls."""
    msg = MagicMock()
    msg.content = content
    # Simulate presence/absence of auxiliary thinking fields
    if thinking:
        msg.thinking = thinking
        msg.reasoning_content = thinking
    else:
        # Ensure getattr returns None for these so the fallback loop skips them
        del msg.thinking  # removes the MagicMock auto-attribute
        del msg.reasoning_content
        # Re-set them explicitly to None
        msg.thinking = None
        msg.reasoning_content = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Fix 3 — _extract_json: truncated/unclosed <think> block handling
# ---------------------------------------------------------------------------

class TestExtractJsonThinkBlock:
    """_extract_json correctly handles all <think>…</think> variants."""

    def test_normal_closed_think_block_json_extracted(self):
        """Standard qwen response: closed <think> then JSON — JSON is returned."""
        text = (
            "<think>\n"
            "The image shows garbage on the roadside. The category is garbage_overflow.\n"
            "Some JSON inside reasoning: {\"partial\": true}\n"
            "</think>\n"
            '{"valid": true, "category": "garbage_overflow", "confidence": 0.88, '
            '"severity": 0.5, "description": "Garbage pile.", "reason": "Waste visible."}'
        )
        result = _extract_json(text)
        assert result["category"] == "garbage_overflow"
        assert result["valid"] is True

    def test_truncated_unclosed_think_block_raises_invalid(self):
        """Response truncated inside <think> with no closing tag and no JSON after.

        With max_tokens raised to 2048 this should not occur in normal operation,
        but if it does _extract_json must not return a reasoning fragment.
        It should raise LLMOutputInvalid (no JSON after stripping).
        """
        text = (
            "<think>\n"
            "The image shows a broken streetlight near the intersection. "
            "I think the category is broken_streetlight based on the "
            'visible lamp arm. Raw fragment: {"category": "road_damage", "valid": true}'
            "\nMore reasoning that never ends..."
        )
        # After stripping unclosed <think>... the remaining text should be empty
        # → LLMOutputInvalid expected
        with pytest.raises(LLMOutputInvalid):
            _extract_json(text)

    def test_truncated_think_does_not_return_reasoning_fragment(self):
        """A JSON-like fragment inside a truncated <think> must NOT be returned."""
        text = (
            "<think>\n"
            'Intermediate thought: {"category": "other", "valid": true, "confidence": 0.1}'
            "\nMore thinking without end tag..."
        )
        # Must not return {"category": "other", ...} from inside the reasoning
        with pytest.raises(LLMOutputInvalid):
            _extract_json(text)

    def test_closed_think_with_json_fragments_inside_last_block_returned(self):
        """Closed think block with multiple JSON fragments inside — final JSON after tag wins."""
        text = (
            "<think>\n"
            'fragment 1: {"x": 1}\n'
            'fragment 2: {"y": 2}\n'
            "</think>\n"
            '{"valid": true, "category": "sewage", "confidence": 0.75, '
            '"severity": 0.85, "description": "Sewage overflow.", "reason": "Wastewater."}'
        )
        result = _extract_json(text)
        assert result["category"] == "sewage"
        assert result["valid"] is True

    def test_no_think_block_bare_json_extracted(self):
        """No think block at all — bare JSON extracted as before."""
        text = (
            '{"valid": true, "category": "pothole", "confidence": 0.92, '
            '"severity": 0.5, "description": "Pothole on road.", "reason": "Hole visible."}'
        )
        result = _extract_json(text)
        assert result["category"] == "pothole"

    def test_think_block_case_insensitive(self):
        """<THINK>...</THINK> in uppercase is also stripped."""
        text = (
            "<THINK>reasoning here</THINK>\n"
            '{"valid": true, "category": "waterlogging", "confidence": 0.8, '
            '"severity": 0.5, "description": "Flooded road.", "reason": "Standing water."}'
        )
        result = _extract_json(text)
        assert result["category"] == "waterlogging"

    def test_unclosed_think_prefix_only_clears_text(self):
        """When the entire response is inside an unclosed <think>, result is empty → raises."""
        text = "<think>nothing useful"
        with pytest.raises(LLMOutputInvalid):
            _extract_json(text)


# ---------------------------------------------------------------------------
# Fix 2 — civic_classify_image: thinking/reasoning_content field fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCivicClassifyImageThinkingField:
    """civic_classify_image falls back to message.thinking when content is empty."""

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_empty_content_thinking_field_used(self, mock_get_client):
        """When content is empty but thinking holds valid JSON, classification succeeds."""
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_vision_mock_response(
                content="",
                thinking=_VALID_VISION_JSON,
            )
        )
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            result = await civic_classify_image(VALID_JPEG, "Test location")

        assert result.category == "garbage_overflow"
        assert result.valid is True

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_empty_content_reasoning_content_field_used(self, mock_get_client):
        """When content is empty and thinking is None but reasoning_content holds JSON."""
        msg = MagicMock()
        msg.content = ""
        msg.thinking = None
        msg.reasoning_content = _VALID_VISION_JSON
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=resp)
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            result = await civic_classify_image(VALID_JPEG, "Test location")

        assert result.category == "garbage_overflow"
        assert result.valid is True

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_empty_content_no_thinking_field_raises_invalid(self, mock_get_client):
        """When content is empty AND no thinking field exists, LLMOutputInvalid is raised."""
        msg = MagicMock()
        msg.content = None
        msg.thinking = None
        msg.reasoning_content = None
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=resp)
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            with pytest.raises(LLMOutputInvalid, match="empty response"):
                await civic_classify_image(VALID_JPEG, "Test location")

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_normal_content_field_used_when_populated(self, mock_get_client):
        """When content is non-empty, the normal path is used (thinking field ignored)."""
        sewage_json = (
            '{"valid": true, "category": "sewage", "confidence": 0.90, '
            '"severity": 0.85, "description": "Sewage overflow on road.", '
            '"reason": "Dark wastewater visible."}'
        )
        # thinking field has wrong answer — must NOT be used
        msg = MagicMock()
        msg.content = sewage_json
        msg.thinking = _VALID_VISION_JSON  # different category — should be ignored
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=resp)
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            result = await civic_classify_image(VALID_JPEG, "Test location")

        # Must return sewage (from content), not garbage_overflow (from thinking)
        assert result.category == "sewage"


# ---------------------------------------------------------------------------
# Fix 1 — civic_classify_image: max_tokens >= 2048
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCivicClassifyImageMaxTokens:
    """civic_classify_image passes max_tokens >= 2048 to the Groq API."""

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_vision_call_uses_max_tokens_2048(self, mock_get_client):
        """The Groq vision call must use max_tokens >= 2048."""
        captured_kwargs: dict = {}

        async def _capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            return _make_vision_mock_response(_VALID_VISION_JSON)

        mock_client = MagicMock()
        mock_client.chat.completions.create = _capture_create
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            await civic_classify_image(VALID_JPEG, "Test location")

        assert "max_tokens" in captured_kwargs, "max_tokens not passed to Groq vision call"
        assert captured_kwargs["max_tokens"] >= 2048, (
            f"Expected max_tokens >= 2048, got {captured_kwargs['max_tokens']}"
        )

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_vision_model_unchanged(self, mock_get_client):
        """Vision model must remain qwen/qwen3.8-27b."""
        captured_kwargs: dict = {}

        async def _capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            return _make_vision_mock_response(_VALID_VISION_JSON)

        mock_client = MagicMock()
        mock_client.chat.completions.create = _capture_create
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            await civic_classify_image(VALID_JPEG, "Test location")

        assert captured_kwargs.get("model") == GROQ_VISION_MODEL
        assert "compound" not in GROQ_VISION_MODEL.lower(), (
            "Vision model must not be a Groq Compound model"
        )


# ---------------------------------------------------------------------------
# Fix 4 — Fallback address keyword additions: open_drain + illegal_construction
# ---------------------------------------------------------------------------

class TestFallbackAddressKeywords:
    """fallback_civic_classify_image maps new address keywords correctly."""

    def test_open_drain_keyword_maps_to_open_drain(self):
        """'open drain' in address → open_drain category."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="open drain near market road",
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.open_drain

    def test_drain_keyword_maps_to_open_drain(self):
        """'drain' alone in address → open_drain category."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="blocked drain at padil junction",
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.open_drain

    def test_open_drain_is_not_other(self):
        """'drain' must no longer return 'other'."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="drain overflowing in the locality",
        )
        assert result.category != "other"

    def test_illegal_keyword_maps_to_illegal_construction(self):
        """'illegal' in address → illegal_construction."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="illegal building on footpath near city centre",
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.illegal_construction

    def test_construction_keyword_maps_to_illegal_construction(self):
        """'construction' in address → illegal_construction."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="new construction blocking footpath",
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.illegal_construction

    def test_encroach_keyword_maps_to_illegal_construction(self):
        """'encroach' in address → illegal_construction."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="footpath encroachment near main road",
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.illegal_construction

    def test_illegal_construction_is_not_other(self):
        """'encroach' must no longer return 'other'."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="encroachment reported here",
        )
        assert result.category != "other"

    # ----- Existing category keywords must still work after the change -----

    def test_pothole_still_works(self):
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="pothole on main road"
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.pothole

    def test_waterlogging_still_works(self):
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="waterlogging near school"
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.waterlogging

    def test_flood_still_maps_to_waterlogging(self):
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="flood water on road"
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.waterlogging

    def test_sewage_still_works(self):
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="sewage overflow near house"
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.sewage

    def test_garbage_still_works(self):
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="garbage dump near park"
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.garbage_overflow

    def test_streetlight_still_works(self):
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="broken streetlight on MG road"
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.broken_streetlight

    def test_water_supply_still_works(self):
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="water pipe leak near junction"
        )
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.water_supply

    def test_unknown_address_returns_other(self):
        """Unrecognised address still falls back to 'other'."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="somewhere near the city",
        )
        assert result.category == "other"

    def test_fallback_always_valid_true(self):
        """Heuristic fallback always returns valid=True (image passed YOLO gate)."""
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="open drain on main road"
        )
        assert result.valid is True

    def test_fallback_reason_is_heuristic_fallback(self):
        """Fallback reason must be 'heuristic_fallback' not 'groq_vision'."""
        result = fallback_civic_classify_image(
            yolo_class="", all_class_names=(), address="drain blocked near school"
        )
        assert result.reason == "heuristic_fallback"

    def test_open_drain_preferred_over_road_for_drain_keyword(self):
        """'drain' must match open_drain before 'road' matches road_damage."""
        result = fallback_civic_classify_image(
            yolo_class="",
            all_class_names=(),
            address="drain next to road",
        )
        # 'open drain' or 'drain' must fire before generic 'road' keyword
        assert map_vision_category_to_issue_category(result.category) == IssueCategory.open_drain


# ---------------------------------------------------------------------------
# Compound model sanity guard
# ---------------------------------------------------------------------------

class TestNoCompoundModel:
    """Confirm qwen/qwen3.8-27b remains the vision model and Compound is absent."""

    def test_vision_model_is_qwen(self):
        from llm.groq_provider import GROQ_VISION_MODEL
        assert GROQ_VISION_MODEL == "qwen/qwen3.8-27b"

    def test_vision_model_not_compound(self):
        from llm.groq_provider import GROQ_VISION_MODEL
        assert "compound" not in GROQ_VISION_MODEL.lower()

    def test_text_model_not_compound(self):
        from llm.groq_provider import GROQ_MODEL
        assert "compound" not in GROQ_MODEL.lower()


# ---------------------------------------------------------------------------
# primary_issue field — parsing and evidence mismatch validation
# ---------------------------------------------------------------------------

class TestPrimaryIssueField:
    """_parse_civic_classification correctly extracts and uses primary_issue."""

    def test_primary_issue_extracted_from_response(self):
        """primary_issue field is parsed from raw response dict."""
        from llm.groq_provider import _parse_civic_classification
        raw = {
            "valid": True,
            "category": "garbage_overflow",
            "confidence": 0.9,
            "severity": 0.5,
            "description": "Garbage pile on roadside.",
            "reason": "Waste is dominant civic problem.",
            "primary_issue": "large garbage pile dumped on the roadside",
        }
        result = _parse_civic_classification(raw)
        assert result.primary_issue == "large garbage pile dumped on the roadside"

    def test_primary_issue_defaults_to_empty_string_when_absent(self):
        """primary_issue is '' when not present in model response (old responses)."""
        from llm.groq_provider import _parse_civic_classification
        raw = {
            "valid": True,
            "category": "pothole",
            "confidence": 0.85,
            "severity": 0.7,
            "description": "Deep pothole in road.",
            "reason": "Visible hole in asphalt.",
        }
        result = _parse_civic_classification(raw)
        assert result.primary_issue == ""

    def test_primary_issue_truncated_at_300_chars(self):
        """primary_issue is capped at 300 characters."""
        from llm.groq_provider import _parse_civic_classification
        long_text = "x" * 500
        raw = {
            "valid": True,
            "category": "garbage_overflow",
            "confidence": 0.9,
            "severity": 0.5,
            "description": "Desc.",
            "reason": "Reason.",
            "primary_issue": long_text,
        }
        result = _parse_civic_classification(raw)
        assert len(result.primary_issue) == 300


class TestEvidenceMismatchGuard:
    """_parse_civic_classification overrides category when primary_issue contradicts it."""

    def _make_raw(self, category: str, primary_issue: str) -> dict:
        return {
            "valid": True,
            "category": category,
            "confidence": 0.7,
            "severity": 0.5,
            "description": "Desc.",
            "reason": "Reason.",
            "primary_issue": primary_issue,
        }

    def test_road_damage_overridden_to_garbage_when_primary_is_garbage(self):
        """category=road_damage + primary_issue mentions garbage → overridden to garbage_overflow."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "large garbage pile on roadside")
        result = _parse_civic_classification(raw)
        assert result.category == "garbage_overflow", (
            f"Expected garbage_overflow, got {result.category}"
        )

    def test_road_damage_overridden_to_open_drain_when_primary_is_drain(self):
        """category=road_damage + primary_issue mentions open drain → overridden to open_drain."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "uncovered open drain beside the road")
        result = _parse_civic_classification(raw)
        assert result.category == "open_drain"

    def test_road_damage_overridden_to_broken_streetlight_when_primary_is_lamp(self):
        """category=road_damage + primary_issue mentions streetlight → overridden to broken_streetlight."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "broken streetlight lamp post fallen")
        result = _parse_civic_classification(raw)
        assert result.category == "broken_streetlight"

    def test_road_damage_overridden_to_illegal_construction_when_primary_is_construction(self):
        """category=road_damage + primary_issue mentions construction → overridden to illegal_construction."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "unauthorized construction encroaching on footpath")
        result = _parse_civic_classification(raw)
        assert result.category == "illegal_construction"

    def test_road_damage_overridden_to_water_sewage_when_primary_is_flood(self):
        """category=road_damage + primary_issue mentions flood/waterlogging → overridden to water_sewage."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "stagnant waterlogging flooding the street")
        result = _parse_civic_classification(raw)
        assert result.category == "water_sewage"

    def test_road_damage_overridden_to_water_sewage_when_primary_is_sewage(self):
        """category=road_damage + primary_issue mentions sewage → overridden to water_sewage."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "sewage overflow from manhole")
        result = _parse_civic_classification(raw)
        assert result.category == "water_sewage"

    def test_road_damage_not_overridden_when_primary_issue_empty(self):
        """If primary_issue is absent (old responses), road_damage is kept as-is."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "")
        result = _parse_civic_classification(raw)
        assert result.category == "road_damage"

    def test_road_damage_not_overridden_when_primary_issue_matches(self):
        """road_damage + primary_issue mentions cracks → kept as road_damage."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("road_damage", "deep cracks and broken asphalt on road surface")
        result = _parse_civic_classification(raw)
        assert result.category == "road_damage"

    def test_other_upgraded_to_garbage_when_primary_is_garbage(self):
        """category=other + primary_issue mentions waste → upgraded to garbage_overflow."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("other", "waste dump near bus stop")
        result = _parse_civic_classification(raw)
        assert result.category == "garbage_overflow"

    def test_other_upgraded_to_open_drain_when_primary_is_drain(self):
        """category=other + primary_issue mentions drain → upgraded to open_drain."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("other", "uncovered storm drain gutter near school")
        result = _parse_civic_classification(raw)
        assert result.category == "open_drain"

    def test_other_upgraded_to_broken_streetlight_when_primary_is_lamp(self):
        """category=other + primary_issue mentions lamp post → upgraded to broken_streetlight."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("other", "fallen lamp post streetlight on footpath")
        result = _parse_civic_classification(raw)
        assert result.category == "broken_streetlight"

    def test_other_upgraded_to_water_sewage_when_primary_is_burst_pipe(self):
        """category=other + primary_issue mentions burst pipe → upgraded to water_sewage."""
        from llm.groq_provider import _parse_civic_classification
        raw = self._make_raw("other", "burst water pipe leaking on street")
        result = _parse_civic_classification(raw)
        assert result.category == "water_sewage"

    def test_invalid_not_overridden_by_evidence_guard(self):
        """category=invalid is never overridden by the evidence guard."""
        from llm.groq_provider import _parse_civic_classification
        raw = {
            "valid": True,  # model incorrectly said valid=True
            "category": "invalid",
            "confidence": 0.9,
            "severity": 0.5,
            "description": "Selfie.",
            "reason": "Not civic.",
            "primary_issue": "garbage dump",
        }
        result = _parse_civic_classification(raw)
        # invalid takes precedence — evidence guard does not touch 'invalid'
        assert result.category == "invalid"
        assert result.valid is False  # forced by category=invalid logic


# ---------------------------------------------------------------------------
# New API call parameters — reasoning_effort + response_format + resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestNewApiCallParameters:
    """civic_classify_image passes reasoning_effort='high', response_format,
    and uses max dimension 1024px for image resizing."""

    def _make_jpeg_large(self, width: int = 2000, height: int = 3000) -> bytes:
        """Make a large JPEG to test the resize path."""
        img = Image.new("RGB", (width, height), color="brown")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_reasoning_effort_high_passed(self, mock_get_client):
        """reasoning_effort='high' must be passed to the Groq vision call."""
        captured_kwargs: dict = {}

        async def _capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            return _make_vision_mock_response(_VALID_VISION_JSON)

        mock_client = MagicMock()
        mock_client.chat.completions.create = _capture_create
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            await civic_classify_image(VALID_JPEG, "Test location")

        assert captured_kwargs.get("reasoning_effort") == "high", (
            f"Expected reasoning_effort='high', got {captured_kwargs.get('reasoning_effort')!r}"
        )

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_response_format_is_json_schema(self, mock_get_client):
        """response_format with type='json_schema' must be passed."""
        captured_kwargs: dict = {}

        async def _capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            return _make_vision_mock_response(_VALID_VISION_JSON)

        mock_client = MagicMock()
        mock_client.chat.completions.create = _capture_create
        mock_get_client.return_value = mock_client

        import os
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            await civic_classify_image(VALID_JPEG, "Test location")

        rf = captured_kwargs.get("response_format")
        assert rf is not None, "response_format was not passed to Groq vision call"
        assert rf.get("type") == "json_schema", f"response_format type should be 'json_schema', got {rf.get('type')!r}"
        schema = rf.get("json_schema", {}).get("schema", {})
        assert schema.get("additionalProperties") is False, "strict schema must have additionalProperties=False"
        required = schema.get("required", [])
        assert "primary_issue" in required, "primary_issue must be in schema required fields"

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_image_resized_to_max_1024px(self, mock_get_client):
        """A 2000×3000 image must be resized to max 1024px on the long edge."""
        captured_messages: list = []

        async def _capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return _make_vision_mock_response(_VALID_VISION_JSON)

        mock_client = MagicMock()
        mock_client.chat.completions.create = _capture_create
        mock_get_client.return_value = mock_client

        large_jpeg = self._make_jpeg_large(2000, 3000)

        import os, base64 as _b64
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            await civic_classify_image(large_jpeg, "Test location")

        # Extract the image_url from the captured messages
        assert len(captured_messages) == 1
        content = captured_messages[0]["content"]
        image_part = next(p for p in content if p.get("type") == "image_url")
        data_url = image_part["image_url"]["url"]
        assert data_url.startswith("data:image/jpeg;base64,")
        img_bytes = _b64.b64decode(data_url.split(",", 1)[1])
        decoded = Image.open(io.BytesIO(img_bytes))
        w, h = decoded.size
        assert max(w, h) <= 1024, (
            f"Image should be resized to max 1024px, got {w}×{h}"
        )

    @patch("llm.groq_provider._get_groq_vision_client")
    async def test_image_not_upscaled_when_already_small(self, mock_get_client):
        """A 100×100 image must not be upscaled beyond its original size."""
        captured_messages: list = []

        async def _capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return _make_vision_mock_response(_VALID_VISION_JSON)

        mock_client = MagicMock()
        mock_client.chat.completions.create = _capture_create
        mock_get_client.return_value = mock_client

        import os, base64 as _b64
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            from llm.groq_provider import civic_classify_image, reset_groq_clients_for_testing
            reset_groq_clients_for_testing()
            await civic_classify_image(VALID_JPEG, "Test location")  # 100×100

        content = captured_messages[0]["content"]
        image_part = next(p for p in content if p.get("type") == "image_url")
        data_url = image_part["image_url"]["url"]
        img_bytes = _b64.b64decode(data_url.split(",", 1)[1])
        decoded = Image.open(io.BytesIO(img_bytes))
        w, h = decoded.size
        # Should be unchanged — 100×100 is already under 1024px
        assert max(w, h) <= 1024
        assert w <= 100 and h <= 100, f"Small image should not be upscaled, got {w}×{h}"
