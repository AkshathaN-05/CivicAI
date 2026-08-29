"""Tests for T2-9 — LLM Deterministic Fallback + Watsonx stub.

Covers:
- fallback_complaint_description: valid output for all IssueCategory values
- fallback_rti_draft: valid output, correct template rendering
- fallback_classify_category: keyword detection, unknown object → other
- Every output is a valid LLMOutput (category, description ≤500, confidence [0,1])
- LLMOutputInvalid is never raised by the fallback (it always produces valid output)
- watsonx_stub: all methods raise NotImplementedError
- watsonx_stub: is NOT wired anywhere (no import chain from service/pipeline)
"""
from __future__ import annotations

import pytest

from llm.fallback_provider import (
    fallback_classify_category,
    fallback_complaint_description,
    fallback_rti_draft,
)
from llm.output_validator import LLMOutput
from llm.watsonx_stub import WatsonxProvider
from schemas.report import IssueCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_valid_llm_output(out: LLMOutput) -> None:
    assert isinstance(out, LLMOutput)
    assert isinstance(out.category, IssueCategory)
    assert isinstance(out.description, str)
    assert len(out.description) <= 500
    assert isinstance(out.authority_recommendation, str)
    assert len(out.authority_recommendation) > 0
    assert 0.0 <= out.confidence <= 1.0


# ---------------------------------------------------------------------------
# fallback_complaint_description tests
# ---------------------------------------------------------------------------

class TestFallbackComplaintDescription:
    def test_valid_category_pothole(self):
        out = fallback_complaint_description(
            category="pothole",
            address="MG Road, Mangaluru",
            confidence=0.9,
        )
        _assert_valid_llm_output(out)
        assert out.category == IssueCategory.pothole

    def test_valid_category_waterlogging(self):
        out = fallback_complaint_description(
            category="waterlogging",
            address="Hampankatta",
            confidence=0.6,
        )
        _assert_valid_llm_output(out)
        assert out.category == IssueCategory.waterlogging

    def test_all_categories_produce_valid_output(self):
        for cat in IssueCategory:
            out = fallback_complaint_description(
                category=cat.value,
                address="Mangaluru",
                confidence=0.5,
            )
            _assert_valid_llm_output(out)
            assert out.category == cat

    def test_description_contains_category_and_address(self):
        out = fallback_complaint_description(
            category="garbage_overflow",
            address="Kadri Hills",
            confidence=0.75,
        )
        assert "garbage" in out.description.lower() or "overflow" in out.description.lower() or "civic" in out.description.lower()
        assert "Kadri Hills" in out.description

    def test_detected_objects_included_when_provided(self):
        out = fallback_complaint_description(
            category="road_damage",
            address="Bunts Hostel",
            confidence=0.8,
            detected_objects="car, truck",
        )
        assert "car" in out.description or "truck" in out.description

    def test_no_detected_objects_no_crash(self):
        out = fallback_complaint_description(
            category="pothole",
            address="Surathkal",
            confidence=0.5,
            detected_objects="",
        )
        _assert_valid_llm_output(out)

    def test_description_never_exceeds_500_chars(self):
        out = fallback_complaint_description(
            category="illegal_construction",
            address="A" * 400,
            confidence=0.5,
            detected_objects="B" * 200,
        )
        assert len(out.description) <= 500

    def test_confidence_clamped_to_0_1(self):
        out = fallback_complaint_description(
            category="pothole",
            address="Mangaluru",
            confidence=5.0,  # out-of-range input
        )
        assert 0.0 <= out.confidence <= 1.0

    def test_invalid_category_falls_back_to_other(self):
        out = fallback_complaint_description(
            category="flying_car",
            address="Mangaluru",
            confidence=0.5,
        )
        assert out.category == IssueCategory.other

    def test_authority_recommendation_not_empty(self):
        out = fallback_complaint_description("sewage", "Bejai", 0.7)
        assert out.authority_recommendation != ""

    def test_deterministic_same_inputs_same_output(self):
        out1 = fallback_complaint_description("pothole", "MG Road", 0.8)
        out2 = fallback_complaint_description("pothole", "MG Road", 0.8)
        assert out1.description == out2.description
        assert out1.category == out2.category
        assert out1.confidence == out2.confidence


# ---------------------------------------------------------------------------
# fallback_rti_draft tests
# ---------------------------------------------------------------------------

class TestFallbackRtiDraft:
    def _make_draft(self, **kwargs):
        defaults = {
            "category": "garbage_overflow",
            "address": "Hampankatta, Mangaluru",
            "submitted_at": "2024-01-01",
            "authority_name": "Mangaluru City Corporation",
            "mock_gov_ref": "MCC-2024-001",
            "status": "SUBMITTED",
            "days_elapsed": 45,
        }
        defaults.update(kwargs)
        return fallback_rti_draft(**defaults)

    def test_returns_valid_llm_output(self):
        out = self._make_draft()
        _assert_valid_llm_output(out)

    def test_all_categories_produce_valid_output(self):
        for cat in IssueCategory:
            out = self._make_draft(category=cat.value)
            _assert_valid_llm_output(out)

    def test_description_contains_gov_ref(self):
        out = self._make_draft(mock_gov_ref="TEST-REF-999")
        assert "TEST-REF-999" in out.description

    def test_description_contains_authority_name(self):
        out = self._make_draft(authority_name="MESCOM")
        # Authority name appears in the draft
        assert "MESCOM" in out.description

    def test_description_never_exceeds_500_chars(self):
        out = self._make_draft(
            address="A" * 300,
            authority_name="B" * 100,
        )
        assert len(out.description) <= 500

    def test_invalid_category_falls_back_to_other(self):
        out = self._make_draft(category="alien_invasion")
        assert out.category == IssueCategory.other

    def test_confidence_is_valid(self):
        out = self._make_draft()
        assert 0.0 <= out.confidence <= 1.0

    def test_authority_recommendation_from_param(self):
        out = self._make_draft(authority_name="MWWD")
        assert out.authority_recommendation == "MWWD"


# ---------------------------------------------------------------------------
# fallback_classify_category tests
# ---------------------------------------------------------------------------

class TestFallbackClassifyCategory:
    def test_bottle_detected_maps_to_garbage_overflow(self):
        out = fallback_classify_category(detected_objects="bottle", address="Mangaluru")
        assert out.category == IssueCategory.garbage_overflow

    def test_car_detected_maps_to_road_damage(self):
        out = fallback_classify_category(detected_objects="car", address="Mangaluru")
        assert out.category == IssueCategory.road_damage

    def test_toilet_detected_maps_to_sewage(self):
        out = fallback_classify_category(detected_objects="toilet", address="Mangaluru")
        assert out.category == IssueCategory.sewage

    def test_sink_detected_maps_to_water_supply(self):
        out = fallback_classify_category(detected_objects="sink", address="Mangaluru")
        assert out.category == IssueCategory.water_supply

    def test_boat_detected_maps_to_waterlogging(self):
        out = fallback_classify_category(detected_objects="boat", address="Mangaluru")
        assert out.category == IssueCategory.waterlogging

    def test_fire_hydrant_maps_to_broken_streetlight(self):
        out = fallback_classify_category(detected_objects="fire hydrant", address="Mangaluru")
        assert out.category == IssueCategory.broken_streetlight

    def test_unknown_object_maps_to_other(self):
        out = fallback_classify_category(detected_objects="dragon", address="Mangaluru")
        assert out.category == IssueCategory.other

    def test_empty_objects_maps_to_other(self):
        out = fallback_classify_category(detected_objects="", address="Mangaluru")
        assert out.category == IssueCategory.other

    def test_valid_llm_output_returned(self):
        out = fallback_classify_category(detected_objects="truck", address="MG Road")
        _assert_valid_llm_output(out)

    def test_confidence_is_0_5(self):
        out = fallback_classify_category(detected_objects="bus", address="Mangaluru")
        assert out.confidence == 0.5

    def test_description_not_empty(self):
        out = fallback_classify_category(detected_objects="bottle", address="Hampankatta")
        assert len(out.description) > 0

    def test_description_max_500_chars(self):
        out = fallback_classify_category(
            detected_objects="x" * 400, address="y" * 400
        )
        assert len(out.description) <= 500


# ---------------------------------------------------------------------------
# WatsonxProvider stub tests
# ---------------------------------------------------------------------------

class TestWatsonxStub:
    def test_generate_complaint_description_raises_not_implemented(self):
        stub = WatsonxProvider()
        with pytest.raises(NotImplementedError):
            stub.generate_complaint_description(category="pothole")

    def test_generate_rti_draft_raises_not_implemented(self):
        stub = WatsonxProvider()
        with pytest.raises(NotImplementedError):
            stub.generate_rti_draft(complaint={})

    def test_classify_category_raises_not_implemented(self):
        stub = WatsonxProvider()
        with pytest.raises(NotImplementedError):
            stub.classify_category(image_context={})

    def test_watsonx_stub_not_imported_in_llm_service(self):
        """WatsonxProvider is NOT imported by llm_service (not wired)."""
        import services.llm_service as svc
        assert not hasattr(svc, "WatsonxProvider"), (
            "WatsonxProvider must not be imported in llm_service — it is a stub only"
        )

    def test_watsonx_stub_not_imported_in_pipeline(self):
        """WatsonxProvider is NOT imported by cv/pipeline.py (not wired)."""
        import cv.pipeline as pl
        assert not hasattr(pl, "WatsonxProvider"), (
            "WatsonxProvider must not be imported in pipeline — it is a stub only"
        )

    def test_watsonx_stub_not_imported_in_groq_provider(self):
        """WatsonxProvider is NOT imported by groq_provider (not wired)."""
        import llm.groq_provider as gp
        assert not hasattr(gp, "WatsonxProvider"), (
            "WatsonxProvider must not be imported in groq_provider — it is a stub only"
        )
