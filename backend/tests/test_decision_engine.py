"""Tests for cv/decision_engine.py — canonical decision algorithm.

All DB interactions are mocked via injected callbacks.
No external services required.

Covers (per architecture spec §17):
  Hash:
    - exact hash + active → unconditional DUPLICATE
    - exact hash + resolved → reuse flag, normal evaluation
    - exact hash + rejected → reuse flag
    - exact hash + archived → reuse flag
    - no hash match → continue

  Geo duplicate:
    - <=30 days + score >=0.30 → duplicate
    - <=30 days + score <0.30 → score-only
    - >30 days + score >=0.70 → duplicate
    - >30 days + 0.50–<0.70 → review
    - >30 days + <0.50 → score-only
    - wrong category → not duplicate
    - >50m → not duplicate (no candidate returned)

  Reopen:
    - 10m / 20 days / strong visual → possible reopened
    - 45m / 55 days / strong visual → possible reopened
    - >60 days → not reopen (no candidate returned)
    - visual below 0.45 → no reopen
    - freshness below 0.50 → no reopen
    - plausibility*visual below 0.30 → no reopen

  Score-only:
    - >=0.65 → VALID_CIVIC_REPORT
    - 0.35–<0.65 → NEEDS_ADMIN_REVIEW
    - <0.35 → INSUFFICIENT_EVIDENCE

  Priority:
    - valid + >=0.75 + medium/high → HIGH
    - valid + <0.75 → MEDIUM
    - reopen + visual>=0.65 + medium/high → CRITICAL
    - reopen otherwise → REOPEN_REVIEW
    - duplicate → DUPLICATE
    - insufficient → INSUFFICIENT

  Relationship:
    - decision_state = duplicate_active_report → linked_report_id populated
    - decision_state = possible_reopened_issue → is_reopened = True
    - image_reuse_flag set correctly
    - evidence_breakdown contains required keys
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from cv.decision_engine import (
    DecisionContext,
    DecisionEngine,
    HashLookupResult,
    NearbyActiveReport,
    NearbyResolvedReport,
)
from cv.evidence_scorer import GEO_DUPLICATE_FLOOR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return _now() - timedelta(days=n)


def _make_ctx(
    image_hash: str = "abc123",
    category: str = "pothole",
    lat: float = 12.87,
    lng: float = 74.84,
    gps_accuracy: float = 15.0,
    visual: float = 0.85,
    category_conf: float = 0.90,
    location: float = 0.85,
    freshness: float = 0.80,
    severity: str = "medium",
) -> DecisionContext:
    return DecisionContext(
        image_hash=image_hash,
        category=category,
        lat=lat,
        lng=lng,
        gps_accuracy_metres=gps_accuracy,
        submission_time=_now(),
        visual_confidence=visual,
        category_confidence=category_conf,
        location_confidence=location,
        freshness_confidence=freshness,
        severity=severity,
    )


def _make_engine(
    hash_active=None,
    hash_historical=None,
    nearby_active=None,
    nearby_resolved=None,
) -> DecisionEngine:
    return DecisionEngine(
        lookup_hash_active=hash_active or (lambda h: HashLookupResult(found=False)),
        lookup_hash_historical=hash_historical or (lambda h: HashLookupResult(found=False)),
        find_nearby_active=nearby_active or (lambda la, ln, cat, r: []),
        find_nearby_resolved=nearby_resolved or (lambda la, ln, cat, r, d: []),
    )


# ---------------------------------------------------------------------------
# Hash: exact active match — DUPLICATE unconditional (no floor)
# ---------------------------------------------------------------------------

def test_hash_active_unconditional_duplicate():
    """Exact hash + active report → DUPLICATE regardless of evidence_score."""
    # Use very low confidence to confirm no floor applies
    ctx = _make_ctx(visual=0.10, category_conf=0.10, location=0.10, freshness=0.10)
    engine = _make_engine(
        hash_active=lambda h: HashLookupResult(found=True, report_id="EXISTING-1", status="SUBMITTED"),
    )
    result = engine.decide(ctx)
    assert result.decision_state == "duplicate_active_report"
    assert result.linked_report_id == "EXISTING-1"
    assert result.admin_priority == "DUPLICATE"


def test_hash_active_no_floor_even_at_zero():
    """Evidence score near zero + active hash → still DUPLICATE."""
    ctx = _make_ctx(visual=0.0, category_conf=0.0, location=0.0, freshness=0.0)
    engine = _make_engine(
        hash_active=lambda h: HashLookupResult(found=True, report_id="EXISTING-2", status="UNDER_REVIEW"),
    )
    result = engine.decide(ctx)
    assert result.decision_state == "duplicate_active_report"


# ---------------------------------------------------------------------------
# Hash: historical match → image_reuse_flag (non-blocking)
# ---------------------------------------------------------------------------

def test_hash_resolved_sets_reuse_flag():
    """Hash match against RESOLVED report → reuse flag, not duplicate."""
    ctx = _make_ctx(visual=0.90, category_conf=0.90, location=0.85, freshness=0.85)
    engine = _make_engine(
        hash_historical=lambda h: HashLookupResult(found=True, report_id="OLD-1", status="RESOLVED"),
    )
    result = engine.decide(ctx)
    assert result.image_reuse_flag is True
    assert result.image_reuse_prior_report_id == "OLD-1"
    assert result.image_reuse_prior_status == "RESOLVED"
    # Not a duplicate
    assert result.decision_state != "duplicate_active_report"


def test_hash_rejected_sets_reuse_flag():
    ctx = _make_ctx()
    engine = _make_engine(
        hash_historical=lambda h: HashLookupResult(found=True, report_id="OLD-2", status="REJECTED"),
    )
    result = engine.decide(ctx)
    assert result.image_reuse_flag is True
    assert result.decision_state != "duplicate_active_report"


def test_hash_archived_sets_reuse_flag():
    ctx = _make_ctx()
    engine = _make_engine(
        hash_historical=lambda h: HashLookupResult(found=True, report_id="OLD-3", status="ARCHIVED"),
    )
    result = engine.decide(ctx)
    assert result.image_reuse_flag is True


def test_no_hash_match_no_reuse_flag():
    ctx = _make_ctx()
    engine = _make_engine()  # all callbacks return nothing
    result = engine.decide(ctx)
    assert result.image_reuse_flag is False


# ---------------------------------------------------------------------------
# Geo duplicate: <=30 days
# ---------------------------------------------------------------------------

def test_geo_active_recent_score_above_floor_is_duplicate():
    """Active candidate <=30 days old + score >= 0.30 → DUPLICATE."""
    ctx = _make_ctx(visual=0.85, category_conf=0.90, location=0.85, freshness=0.80)
    # Score ≈ 0.85*0.35 + 0.90*0.20 + 0.85*0.30 + 0.80*0.15 = 0.852
    candidate = NearbyActiveReport(
        report_id="ACTIVE-1",
        created_at=_days_ago(10),
        status="SUBMITTED",
        distance_metres=30.0,
    )
    engine = _make_engine(nearby_active=lambda la, ln, cat, r: [candidate])
    result = engine.decide(ctx)
    assert result.decision_state == "duplicate_active_report"
    assert result.linked_report_id == "ACTIVE-1"
    assert result.admin_priority == "DUPLICATE"


def test_geo_active_recent_score_below_floor_not_duplicate():
    """Active candidate <=30 days + score < 0.30 → fall through to score-only."""
    # Force a very low evidence score
    ctx = _make_ctx(visual=0.10, category_conf=0.10, location=0.10, freshness=0.10)
    # Score = 0.10*0.35 + 0.10*0.20 + 0.10*0.30 + 0.10*0.15 = 0.10
    assert 0.10 < GEO_DUPLICATE_FLOOR
    candidate = NearbyActiveReport(
        report_id="ACTIVE-2",
        created_at=_days_ago(5),
        status="SUBMITTED",
        distance_metres=20.0,
    )
    engine = _make_engine(nearby_active=lambda la, ln, cat, r: [candidate])
    result = engine.decide(ctx)
    assert result.decision_state != "duplicate_active_report"
    assert result.decision_state == "insufficient_evidence"


# ---------------------------------------------------------------------------
# Geo duplicate: >30 days
# ---------------------------------------------------------------------------

def test_geo_active_stale_score_ge_0_70_is_duplicate():
    """Stale active (>30 days) + score >= 0.70 → DUPLICATE."""
    ctx = _make_ctx(visual=0.85, category_conf=0.90, location=0.85, freshness=0.80)
    candidate = NearbyActiveReport(
        report_id="STALE-1",
        created_at=_days_ago(45),
        status="SUBMITTED",
        distance_metres=40.0,
    )
    engine = _make_engine(nearby_active=lambda la, ln, cat, r: [candidate])
    result = engine.decide(ctx)
    assert result.decision_state == "duplicate_active_report"
    assert result.linked_report_id == "STALE-1"


def test_geo_active_stale_score_0_50_to_0_70_is_review():
    """Stale active (>30 days) + score in [0.50, 0.70) → NEEDS_ADMIN_REVIEW."""
    # Score ≈ 0.60*0.35 + 0.60*0.20 + 0.60*0.30 + 0.60*0.15 = 0.60
    ctx = _make_ctx(visual=0.60, category_conf=0.60, location=0.60, freshness=0.60)
    candidate = NearbyActiveReport(
        report_id="STALE-2",
        created_at=_days_ago(35),
        status="SUBMITTED",
        distance_metres=45.0,
    )
    engine = _make_engine(nearby_active=lambda la, ln, cat, r: [candidate])
    result = engine.decide(ctx)
    assert result.decision_state == "needs_admin_review"


def test_geo_active_stale_score_below_0_50_not_duplicate():
    """Stale active (>30 days) + score < 0.50 → score-only."""
    ctx = _make_ctx(visual=0.30, category_conf=0.30, location=0.40, freshness=0.30)
    # Score = 0.30*0.35 + 0.30*0.20 + 0.40*0.30 + 0.30*0.15 = 0.105+0.06+0.12+0.045 = 0.33
    candidate = NearbyActiveReport(
        report_id="STALE-3",
        created_at=_days_ago(40),
        status="SUBMITTED",
        distance_metres=48.0,
    )
    engine = _make_engine(nearby_active=lambda la, ln, cat, r: [candidate])
    result = engine.decide(ctx)
    assert result.decision_state != "duplicate_active_report"
    # 0.33 < 0.35 → insufficient
    assert result.decision_state == "insufficient_evidence"


def test_no_geo_candidate_continues():
    """No active candidates → proceed normally."""
    ctx = _make_ctx(visual=0.85, category_conf=0.90, location=0.85, freshness=0.80)
    engine = _make_engine(nearby_active=lambda la, ln, cat, r: [])
    result = engine.decide(ctx)
    # Should not be a duplicate
    assert result.decision_state != "duplicate_active_report"


# ---------------------------------------------------------------------------
# Reopen detection
# ---------------------------------------------------------------------------

def test_reopen_10m_20_days_strong_visual():
    """10m / 20 days / visual=0.90 / freshness=0.90 → POSSIBLE_REOPENED_ISSUE."""
    ctx = _make_ctx(visual=0.90, freshness=0.90, location=0.85, category_conf=0.90)
    resolved_candidate = NearbyResolvedReport(
        report_id="RESOLVED-1",
        resolved_at=_days_ago(20),
        distance_metres=10.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.decision_state == "possible_reopened_issue"
    assert result.is_reopened is True
    assert result.linked_report_id == "RESOLVED-1"


def test_reopen_45m_55_days_strong_visual():
    """45m / 55 days / visual=0.88 → POSSIBLE_REOPENED_ISSUE.

    Plausibility (31–60 band) = 0.45; combined = 0.45 * 0.88 = 0.396 >= 0.30.
    """
    ctx = _make_ctx(visual=0.88, freshness=0.80, location=0.85, category_conf=0.90)
    resolved_candidate = NearbyResolvedReport(
        report_id="RESOLVED-2",
        resolved_at=_days_ago(55),
        distance_metres=45.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.decision_state == "possible_reopened_issue"
    assert result.is_reopened is True


def test_reopen_gt_60_days_not_reopen():
    """Reports resolved >60 days ago are not queried; treated as independent."""
    ctx = _make_ctx(visual=0.90, freshness=0.90)
    # Simulate the DB callback returning empty (>60 days filtered out at SQL level)
    engine = _make_engine(nearby_resolved=lambda la, ln, cat, r, d: [])
    result = engine.decide(ctx)
    assert result.decision_state != "possible_reopened_issue"
    assert result.is_reopened is False


def test_reopen_visual_below_floor():
    """visual_confidence < 0.45 → no reopen even if other signals pass."""
    ctx = _make_ctx(visual=0.40, freshness=0.80, location=0.85, category_conf=0.90)
    resolved_candidate = NearbyResolvedReport(
        report_id="RESOLVED-3",
        resolved_at=_days_ago(20),
        distance_metres=15.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.decision_state != "possible_reopened_issue"


def test_reopen_freshness_below_floor():
    """freshness_confidence < 0.50 → no reopen."""
    ctx = _make_ctx(visual=0.90, freshness=0.40, location=0.85, category_conf=0.90)
    resolved_candidate = NearbyResolvedReport(
        report_id="RESOLVED-4",
        resolved_at=_days_ago(20),
        distance_metres=15.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.decision_state != "possible_reopened_issue"


def test_reopen_plausibility_times_visual_below_floor():
    """31-60 day band (plausibility=0.45); visual=0.60; combined=0.27 < 0.30 → no reopen."""
    ctx = _make_ctx(visual=0.60, freshness=0.70, location=0.85, category_conf=0.90)
    # plausibility(55 days) = 0.45; combined = 0.45 * 0.60 = 0.27 < 0.30
    resolved_candidate = NearbyResolvedReport(
        report_id="RESOLVED-5",
        resolved_at=_days_ago(55),
        distance_metres=20.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.decision_state != "possible_reopened_issue"


# ---------------------------------------------------------------------------
# Score-only decision states
# ---------------------------------------------------------------------------

def test_score_only_valid():
    """evidence_score >= 0.65 → VALID_CIVIC_REPORT."""
    ctx = _make_ctx(visual=0.85, category_conf=0.90, location=0.85, freshness=0.80)
    engine = _make_engine()
    result = engine.decide(ctx)
    assert result.decision_state == "valid_civic_report"


def test_score_only_needs_review():
    """evidence_score in [0.35, 0.65) → NEEDS_ADMIN_REVIEW."""
    ctx = _make_ctx(visual=0.40, category_conf=0.40, location=0.50, freshness=0.40)
    # Score = 0.40*0.35 + 0.40*0.20 + 0.50*0.30 + 0.40*0.15 = 0.14+0.08+0.15+0.06 = 0.43
    engine = _make_engine()
    result = engine.decide(ctx)
    assert result.decision_state == "needs_admin_review"


def test_score_only_insufficient():
    """evidence_score < 0.35 → INSUFFICIENT_EVIDENCE."""
    ctx = _make_ctx(visual=0.10, category_conf=0.10, location=0.10, freshness=0.10)
    engine = _make_engine()
    result = engine.decide(ctx)
    assert result.decision_state == "insufficient_evidence"


# ---------------------------------------------------------------------------
# Admin priority
# ---------------------------------------------------------------------------

def test_priority_valid_high():
    """VALID + score >= 0.75 + severity medium → HIGH."""
    ctx = _make_ctx(visual=0.88, category_conf=0.92, location=0.85, freshness=0.90, severity="medium")
    engine = _make_engine()
    result = engine.decide(ctx)
    assert result.decision_state == "valid_civic_report"
    assert result.evidence_score >= 0.75
    assert result.admin_priority == "HIGH"


def test_priority_valid_medium():
    """VALID + score < 0.75 → MEDIUM (Example C)."""
    ctx = _make_ctx(visual=0.62, category_conf=0.70, location=0.85, freshness=0.90, severity="medium")
    engine = _make_engine()
    result = engine.decide(ctx)
    assert result.decision_state == "valid_civic_report"
    assert result.evidence_score < 0.75
    assert result.admin_priority == "MEDIUM"


def test_priority_reopen_critical():
    """REOPEN + visual >= 0.65 + severity high → CRITICAL."""
    ctx = _make_ctx(visual=0.90, freshness=0.85, location=0.85, category_conf=0.90, severity="high")
    resolved_candidate = NearbyResolvedReport(
        report_id="RESOLVED-C",
        resolved_at=_days_ago(10),
        distance_metres=15.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.decision_state == "possible_reopened_issue"
    assert result.admin_priority == "CRITICAL"


def test_priority_reopen_review():
    """REOPEN + visual < 0.65 → REOPEN_REVIEW."""
    ctx = _make_ctx(visual=0.55, freshness=0.80, location=0.85, category_conf=0.90, severity="medium")
    # 31–60 day band: plausibility = 0.45; combined = 0.45 * 0.55 = 0.2475 < 0.30
    # Use 0–14 day band instead: plausibility = 0.95; combined = 0.95 * 0.55 = 0.5225 >= 0.30
    resolved_candidate = NearbyResolvedReport(
        report_id="RESOLVED-R",
        resolved_at=_days_ago(5),
        distance_metres=20.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.decision_state == "possible_reopened_issue"
    assert result.admin_priority == "REOPEN_REVIEW"


def test_priority_duplicate():
    ctx = _make_ctx()
    engine = _make_engine(
        hash_active=lambda h: HashLookupResult(found=True, report_id="X", status="SUBMITTED"),
    )
    result = engine.decide(ctx)
    assert result.admin_priority == "DUPLICATE"


def test_priority_insufficient():
    ctx = _make_ctx(visual=0.10, category_conf=0.10, location=0.10, freshness=0.10)
    engine = _make_engine()
    result = engine.decide(ctx)
    assert result.admin_priority == "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Relationship persistence
# ---------------------------------------------------------------------------

def test_duplicate_linked_report_id_populated():
    ctx = _make_ctx()
    engine = _make_engine(
        hash_active=lambda h: HashLookupResult(found=True, report_id="LINKED-1", status="SUBMITTED"),
    )
    result = engine.decide(ctx)
    assert result.linked_report_id == "LINKED-1"


def test_reopen_is_reopened_flag_true():
    ctx = _make_ctx(visual=0.90, freshness=0.90)
    resolved_candidate = NearbyResolvedReport(
        report_id="REOPENED-1",
        resolved_at=_days_ago(15),
        distance_metres=20.0,
    )
    engine = _make_engine(
        nearby_resolved=lambda la, ln, cat, r, d: [resolved_candidate],
    )
    result = engine.decide(ctx)
    assert result.is_reopened is True
    assert result.linked_report_id == "REOPENED-1"


def test_non_duplicate_linked_report_id_none():
    ctx = _make_ctx(visual=0.90, freshness=0.90)
    engine = _make_engine()  # no nearby reports
    result = engine.decide(ctx)
    if result.decision_state not in ("duplicate_active_report", "possible_reopened_issue"):
        assert result.linked_report_id is None


# ---------------------------------------------------------------------------
# Evidence breakdown required keys
# ---------------------------------------------------------------------------

def test_evidence_breakdown_has_required_keys():
    ctx = _make_ctx()
    engine = _make_engine()
    result = engine.decide(ctx)
    bd = result.evidence_breakdown
    required_keys = [
        "visual_confidence", "category_confidence", "location_confidence",
        "freshness_confidence", "evidence_score", "decision_state",
        "admin_priority", "evidence_disclaimer",
    ]
    for key in required_keys:
        assert key in bd, f"Missing key '{key}' in evidence_breakdown"


def test_evidence_breakdown_disclaimer_present():
    ctx = _make_ctx()
    engine = _make_engine()
    result = engine.decide(ctx)
    disclaimer = result.evidence_breakdown.get("evidence_disclaimer", "")
    assert "evidence" in disclaimer.lower()
    assert "current road conditions" in disclaimer.lower()


# ---------------------------------------------------------------------------
# Failure resilience
# ---------------------------------------------------------------------------

def test_hash_lookup_exception_does_not_crash():
    """If hash lookup raises, engine continues gracefully."""
    ctx = _make_ctx(visual=0.80, category_conf=0.85, location=0.85, freshness=0.80)
    def _bad_hash(h):
        raise RuntimeError("DB connection failed")
    engine = _make_engine(hash_active=_bad_hash)
    result = engine.decide(ctx)
    # Should complete without exception
    assert result.decision_state in (
        "valid_civic_report", "needs_admin_review", "insufficient_evidence",
        "duplicate_active_report", "possible_reopened_issue"
    )


def test_nearby_active_exception_does_not_crash():
    ctx = _make_ctx()
    def _bad_nearby(la, ln, cat, r):
        raise RuntimeError("DB geo query failed")
    engine = _make_engine(nearby_active=_bad_nearby)
    result = engine.decide(ctx)
    assert result.decision_state is not None


def test_no_gps_skips_geo_queries():
    """If lat/lng are None, geo queries are not called."""
    called = []
    ctx = DecisionContext(
        image_hash="abc",
        category="pothole",
        lat=None,
        lng=None,
        gps_accuracy_metres=None,
        submission_time=_now(),
        visual_confidence=0.80,
        category_confidence=0.85,
        location_confidence=0.30,  # text-only floor
        freshness_confidence=0.60,
        severity="medium",
    )
    def _tracking_nearby(la, ln, cat, r):
        called.append("active")
        return []
    engine = _make_engine(nearby_active=_tracking_nearby)
    engine.decide(ctx)
    assert "active" not in called, "Geo query should not be called when lat/lng are None"
