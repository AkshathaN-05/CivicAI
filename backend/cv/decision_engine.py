"""Evidence decision engine — DB queries + canonical decision algorithm.

Implements the full evidence-verification decision flow in the canonical order:

    1. Exact hash: active report  → DUPLICATE_ACTIVE_REPORT (unconditional)
    2. Exact hash: historical     → image_reuse_flag (non-blocking signal)
    3. Active geo duplicate       → DUPLICATE_ACTIVE_REPORT / NEEDS_ADMIN_REVIEW
    4. Recently-resolved (reopen) → POSSIBLE_REOPENED_ISSUE
    5. Score-only thresholds      → VALID / NEEDS_REVIEW / INSUFFICIENT
    6. Admin priority assignment  → CRITICAL / HIGH / MEDIUM / DUPLICATE /
                                    REOPEN_REVIEW / INSUFFICIENT

DB queries are injected via a thin ``NearbyReportProvider`` protocol so the
engine is testable without a live database.

Public API:
    @dataclass EvidenceResult
    @dataclass DecisionContext
    class DecisionEngine

Decision states (string values of DecisionState enum — see schemas/report.py):
    invalid_image           — image fails validation (not assigned here)
    insufficient_evidence   — evidence_score < 0.35
    duplicate_active_report — existing active case linked
    possible_reopened_issue — recently-resolved case may have recurred
    valid_civic_report      — evidence_score >= 0.65
    needs_admin_review      — evidence_score in [0.35, 0.65)

Admin priorities:
    CRITICAL       — reopen + strong visual + medium/high severity
    HIGH           — valid + score >= 0.75 + medium/high severity
    MEDIUM         — valid borderline OR needs_admin_review
    LOW            — reserved; not assigned at launch
    REOPEN_REVIEW  — reopen + weaker visual or low severity
    DUPLICATE      — duplicate_active_report
    INSUFFICIENT   — insufficient_evidence
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from cv.evidence_scorer import (
    GEO_DUPLICATE_FLOOR,
    REVIEW_THRESHOLD,
    VALID_THRESHOLD,
    compute_evidence_score,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reopen plausibility bands (days_since_resolution → multiplier)
# ---------------------------------------------------------------------------

REOPEN_PLAUSIBILITY_BANDS: list[tuple[int, int, float]] = [
    # (min_days_inclusive, max_days_inclusive, multiplier)
    (0,  14, 0.95),
    (15, 30, 0.75),
    (31, 60, 0.45),
    # > 60 days: not queried; treated as new independent report
]

REOPEN_WINDOW_DAYS: int = 60          # resolved_at > NOW() - 60 days
REOPEN_VISUAL_FLOOR: float = 0.45     # visual_confidence >= this for reopen
REOPEN_FRESHNESS_FLOOR: float = 0.50  # freshness_confidence >= this for reopen
REOPEN_COMBINED_FLOOR: float = 0.30   # plausibility × visual >= this for reopen

GEO_RADIUS_METRES: int = 50           # both duplicate and reopen queries


# ---------------------------------------------------------------------------
# Nearby-report data objects (returned by DB provider callbacks)
# ---------------------------------------------------------------------------

@dataclass
class NearbyActiveReport:
    """A candidate active report returned by the geo-proximity query."""
    report_id: str
    created_at: datetime
    status: str      # 'SUBMITTED' or 'UNDER_REVIEW'
    distance_metres: Optional[float] = None


@dataclass
class NearbyResolvedReport:
    """A recently-resolved report returned by the geo-proximity query."""
    report_id: str
    resolved_at: datetime
    distance_metres: Optional[float] = None


@dataclass
class HashLookupResult:
    """Result of an image-hash lookup."""
    found: bool
    report_id: Optional[str] = None
    status: Optional[str] = None     # DB status value of the matched report


# ---------------------------------------------------------------------------
# Input context for the decision engine
# ---------------------------------------------------------------------------

@dataclass
class DecisionContext:
    """All inputs required to make the full evidence decision.

    Attributes:
        image_hash:           BLAKE3 hex digest of validated image bytes.
        category:             Civic issue category string (e.g. 'pothole').
        lat:                  GPS latitude (None if not provided).
        lng:                  GPS longitude (None if not provided).
        gps_accuracy_metres:  GPS accuracy from browser geolocation (optional).
        submission_time:      Server-side submission timestamp.
        visual_confidence:    Image-only AI detection confidence [0, 1].
        category_confidence:  Model certainty about the category [0, 1].
        location_confidence:  GPS quality + plausibility [0, 1].
        freshness_confidence: Temporal recency signal [0, 1].
        severity:             Civic impact severity ('low'/'medium'/'high').
    """
    image_hash: str
    category: str
    lat: Optional[float]
    lng: Optional[float]
    gps_accuracy_metres: Optional[float]
    submission_time: datetime
    visual_confidence: float
    category_confidence: float
    location_confidence: float
    freshness_confidence: float
    severity: str = "low"


# ---------------------------------------------------------------------------
# Output of the decision engine
# ---------------------------------------------------------------------------

@dataclass
class EvidenceResult:
    """Complete evidence verdict for one submission.

    Fields are stored in DB columns (reports) and in ai_raw_response JSONB
    (evidence_breakdown).

    NOTE: NEVER expose numeric scores to citizens — only decision_state and
    citizen_message are surfaced in citizen-facing API responses.
    """
    decision_state: str              # DecisionState value string
    evidence_score: float            # [0.0, 1.0] — overall weighted score
    admin_priority: str              # AdminPriority value string
    visual_confidence: float         # [0.0, 1.0]
    category_confidence: float       # [0.0, 1.0]
    location_confidence: float       # [0.0, 1.0]
    freshness_confidence: float      # [0.0, 1.0]
    severity: str                    # 'low' / 'medium' / 'high'
    is_reopened: bool                # True when decision_state = possible_reopened_issue
    linked_report_id: Optional[str]  # shortcut FK to active/resolved report
    image_reuse_flag: bool           # True when same hash in non-active report
    image_reuse_prior_report_id: Optional[str]
    image_reuse_prior_status: Optional[str]
    citizen_message: str
    evidence_breakdown: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Citizen messages (hedged language — never claims ground-truth verification)
# ---------------------------------------------------------------------------

_CITIZEN_MESSAGES: dict[str, str] = {
    "valid_civic_report": (
        "Your report has been verified and submitted. "
        "An authority will review it shortly."
    ),
    "needs_admin_review": (
        "Your report has been submitted for manual review. "
        "An authority representative will assess the submitted evidence."
    ),
    "insufficient_evidence": (
        "The system could not clearly identify a civic issue in the submitted image "
        "or location. Your report has been submitted but may need additional information. "
        "You can edit the category or description below."
    ),
    "duplicate_active_report": (
        "An issue near this location has already been reported and is currently being "
        "reviewed. Your report has been recorded and linked as additional evidence to "
        "support the existing case."
    ),
    "possible_reopened_issue": (
        "A similar issue at this location was previously resolved. Your report suggests "
        "it may have recurred. It has been forwarded to the authority for review."
    ),
}


def _citizen_message(state: str) -> str:
    return _CITIZEN_MESSAGES.get(state, "Your report has been submitted.")


# ---------------------------------------------------------------------------
# Reopen plausibility helper
# ---------------------------------------------------------------------------

def _reopen_plausibility(days_since_resolution: int) -> float:
    """Return the reopen plausibility multiplier for a resolved report."""
    for min_d, max_d, multiplier in REOPEN_PLAUSIBILITY_BANDS:
        if min_d <= days_since_resolution <= max_d:
            return multiplier
    # > 60 days — should not be called for these; callers must filter
    return 0.0


# ---------------------------------------------------------------------------
# Admin priority assignment
# ---------------------------------------------------------------------------

def _assign_admin_priority(
    decision_state: str,
    evidence_score: float,
    visual_confidence: float,
    severity: str,
) -> str:
    """Return the deterministic admin priority string."""
    if decision_state == "duplicate_active_report":
        return "DUPLICATE"

    if decision_state == "possible_reopened_issue":
        if visual_confidence >= 0.65 and severity in ("medium", "high"):
            return "CRITICAL"
        return "REOPEN_REVIEW"

    if decision_state == "valid_civic_report":
        if evidence_score >= 0.75 and severity in ("medium", "high"):
            return "HIGH"
        return "MEDIUM"

    if decision_state == "needs_admin_review":
        return "MEDIUM"

    # insufficient_evidence (and any unexpected fallback)
    return "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------

class DecisionEngine:
    """Applies the canonical evidence decision algorithm.

    DB queries are injected via three callbacks so the engine is testable
    without a live database.  Each callback must be a callable that takes
    the arguments described below and returns the appropriate object.

    Args:
        lookup_hash_active: (image_hash: str) -> Optional[HashLookupResult]
            Returns the FIRST matching report with status SUBMITTED/UNDER_REVIEW,
            or None if no active match exists.

        lookup_hash_historical: (image_hash: str) -> Optional[HashLookupResult]
            Returns the FIRST matching report with ANY non-active status,
            or None.

        find_nearby_active: (lat: float, lng: float, category: str, radius_m: int)
            -> list[NearbyActiveReport]
            Returns active reports (SUBMITTED/UNDER_REVIEW) within radius_m of
            the given coordinates with the given category, ordered by
            created_at DESC.

        find_nearby_resolved: (lat: float, lng: float, category: str,
                               radius_m: int, window_days: int)
            -> list[NearbyResolvedReport]
            Returns RESOLVED reports within radius_m resolved within the last
            window_days days, ordered by resolved_at DESC.
    """

    def __init__(
        self,
        lookup_hash_active: Callable[[str], Optional[HashLookupResult]],
        lookup_hash_historical: Callable[[str], Optional[HashLookupResult]],
        find_nearby_active: Callable[
            [float, float, str, int], list[NearbyActiveReport]
        ],
        find_nearby_resolved: Callable[
            [float, float, str, int, int], list[NearbyResolvedReport]
        ],
    ) -> None:
        self._lookup_hash_active = lookup_hash_active
        self._lookup_hash_historical = lookup_hash_historical
        self._find_nearby_active = find_nearby_active
        self._find_nearby_resolved = find_nearby_resolved

    def decide(self, ctx: DecisionContext) -> EvidenceResult:
        """Run the canonical decision algorithm and return an EvidenceResult.

        Steps:
          1. Compute evidence_score from the four confidence dimensions.
          2. Exact hash + active report  → DUPLICATE_ACTIVE_REPORT (unconditional).
          3. Exact hash + historical     → image_reuse_flag (non-blocking).
          4. Active geo duplicate        → DUPLICATE / NEEDS_ADMIN_REVIEW / continue.
          5. Recently-resolved (reopen)  → POSSIBLE_REOPENED_ISSUE / continue.
          6. Score-only thresholds       → VALID / NEEDS_REVIEW / INSUFFICIENT.
          7. Assign admin priority.
        """
        evidence_score = compute_evidence_score(
            ctx.visual_confidence,
            ctx.category_confidence,
            ctx.location_confidence,
            ctx.freshness_confidence,
        )

        # Shared state accumulated during the walk
        image_reuse_flag = False
        image_reuse_prior_report_id: Optional[str] = None
        image_reuse_prior_status: Optional[str] = None
        breakdown_notes: list[str] = []

        # ── Step 1: Exact hash — active report ─────────────────────────────
        if ctx.image_hash:
            try:
                active_hash = self._lookup_hash_active(ctx.image_hash)
            except Exception as exc:
                logger.warning("decision_engine: hash active lookup failed: %s", exc)
                active_hash = None

            if active_hash and active_hash.found and active_hash.report_id:
                breakdown_notes.append(
                    f"Exact hash match: active report {active_hash.report_id} "
                    f"(status={active_hash.status})."
                )
                return self._make_result(
                    decision_state="duplicate_active_report",
                    evidence_score=evidence_score,
                    ctx=ctx,
                    linked_report_id=active_hash.report_id,
                    image_reuse_flag=False,
                    image_reuse_prior_report_id=None,
                    image_reuse_prior_status=None,
                    breakdown_notes=breakdown_notes,
                    extra_breakdown={
                        "hash_match_type": "exact_active",
                        "hash_matched_report_id": active_hash.report_id,
                        "hash_matched_status": active_hash.status,
                    },
                )

            # ── Step 2: Exact hash — historical ────────────────────────────
            try:
                hist_hash = self._lookup_hash_historical(ctx.image_hash)
            except Exception as exc:
                logger.warning("decision_engine: hash historical lookup failed: %s", exc)
                hist_hash = None

            if hist_hash and hist_hash.found:
                image_reuse_flag = True
                image_reuse_prior_report_id = hist_hash.report_id
                image_reuse_prior_status = hist_hash.status
                breakdown_notes.append(
                    f"Image reuse flag: same hash found in historical report "
                    f"{hist_hash.report_id} (status={hist_hash.status})."
                )

        # ── Step 3: Active geo duplicate ───────────────────────────────────
        if ctx.lat is not None and ctx.lng is not None:
            try:
                active_nearby = self._find_nearby_active(
                    ctx.lat, ctx.lng, ctx.category, GEO_RADIUS_METRES
                )
            except Exception as exc:
                logger.warning("decision_engine: find_nearby_active failed: %s", exc)
                active_nearby = []

            if active_nearby:
                # Use the most recent active candidate (list is created_at DESC)
                candidate = active_nearby[0]
                now = datetime.now(timezone.utc)
                cand_created = candidate.created_at
                if cand_created.tzinfo is None:
                    cand_created = cand_created.replace(tzinfo=timezone.utc)
                age_days = (now - cand_created).days
                dist_note = (
                    f"{candidate.distance_metres:.0f}m"
                    if candidate.distance_metres is not None
                    else "≤50m"
                )
                breakdown_notes.append(
                    f"Active geo candidate: report {candidate.report_id} "
                    f"age={age_days}d distance={dist_note} status={candidate.status}."
                )

                if age_days <= 30:
                    # Recent active report: link if evidence floor passes
                    if evidence_score >= GEO_DUPLICATE_FLOOR:
                        return self._make_result(
                            decision_state="duplicate_active_report",
                            evidence_score=evidence_score,
                            ctx=ctx,
                            linked_report_id=candidate.report_id,
                            image_reuse_flag=image_reuse_flag,
                            image_reuse_prior_report_id=image_reuse_prior_report_id,
                            image_reuse_prior_status=image_reuse_prior_status,
                            breakdown_notes=breakdown_notes,
                            extra_breakdown={
                                "geo_match_type": "active_recent",
                                "geo_candidate_report_id": candidate.report_id,
                                "geo_candidate_age_days": age_days,
                                "geo_candidate_distance": candidate.distance_metres,
                                "geo_candidate_status": candidate.status,
                            },
                        )
                    else:
                        breakdown_notes.append(
                            f"Active candidate age={age_days}d but evidence_score "
                            f"{evidence_score:.3f} < floor {GEO_DUPLICATE_FLOOR} "
                            "— not linked; continuing to score-only."
                        )
                        # Fall through to score-only

                else:
                    # Stale active report (> 30 days)
                    if evidence_score >= 0.70:
                        return self._make_result(
                            decision_state="duplicate_active_report",
                            evidence_score=evidence_score,
                            ctx=ctx,
                            linked_report_id=candidate.report_id,
                            image_reuse_flag=image_reuse_flag,
                            image_reuse_prior_report_id=image_reuse_prior_report_id,
                            image_reuse_prior_status=image_reuse_prior_status,
                            breakdown_notes=breakdown_notes,
                            extra_breakdown={
                                "geo_match_type": "active_stale",
                                "geo_candidate_report_id": candidate.report_id,
                                "geo_candidate_age_days": age_days,
                                "geo_candidate_distance": candidate.distance_metres,
                            },
                        )
                    elif evidence_score >= 0.50:
                        # NEEDS_ADMIN_REVIEW for stale active + moderate evidence
                        extra = {
                            "geo_match_type": "active_stale_review",
                            "geo_candidate_report_id": candidate.report_id,
                            "geo_candidate_age_days": age_days,
                            "geo_candidate_distance": candidate.distance_metres,
                        }
                        return self._make_result(
                            decision_state="needs_admin_review",
                            evidence_score=evidence_score,
                            ctx=ctx,
                            linked_report_id=None,
                            image_reuse_flag=image_reuse_flag,
                            image_reuse_prior_report_id=image_reuse_prior_report_id,
                            image_reuse_prior_status=image_reuse_prior_status,
                            breakdown_notes=breakdown_notes,
                            extra_breakdown=extra,
                        )
                    else:
                        breakdown_notes.append(
                            f"Stale active candidate (age={age_days}d) but "
                            f"evidence_score {evidence_score:.3f} < 0.50 — not linked."
                        )
                        # Fall through to score-only

        # ── Step 4: Recently-resolved (reopen) ─────────────────────────────
        if ctx.lat is not None and ctx.lng is not None:
            try:
                resolved_nearby = self._find_nearby_resolved(
                    ctx.lat, ctx.lng, ctx.category,
                    GEO_RADIUS_METRES, REOPEN_WINDOW_DAYS,
                )
            except Exception as exc:
                logger.warning("decision_engine: find_nearby_resolved failed: %s", exc)
                resolved_nearby = []

            if resolved_nearby:
                candidate = resolved_nearby[0]
                now = datetime.now(timezone.utc)
                resolved_at = candidate.resolved_at
                if resolved_at.tzinfo is None:
                    resolved_at = resolved_at.replace(tzinfo=timezone.utc)
                days_since = (now - resolved_at).days
                plausibility = _reopen_plausibility(days_since)
                combined = plausibility * ctx.visual_confidence
                dist_note = (
                    f"{candidate.distance_metres:.0f}m"
                    if candidate.distance_metres is not None
                    else "≤50m"
                )
                breakdown_notes.append(
                    f"Resolved geo candidate: report {candidate.report_id} "
                    f"days_since_resolution={days_since} distance={dist_note} "
                    f"plausibility={plausibility:.2f} combined={combined:.3f}."
                )

                if (
                    ctx.visual_confidence >= REOPEN_VISUAL_FLOOR
                    and ctx.freshness_confidence >= REOPEN_FRESHNESS_FLOOR
                    and combined >= REOPEN_COMBINED_FLOOR
                ):
                    return self._make_result(
                        decision_state="possible_reopened_issue",
                        evidence_score=evidence_score,
                        ctx=ctx,
                        linked_report_id=candidate.report_id,
                        image_reuse_flag=image_reuse_flag,
                        image_reuse_prior_report_id=image_reuse_prior_report_id,
                        image_reuse_prior_status=image_reuse_prior_status,
                        is_reopened=True,
                        breakdown_notes=breakdown_notes,
                        extra_breakdown={
                            "reopen_source_report_id": candidate.report_id,
                            "reopen_days_since_resolution": days_since,
                            "reopen_plausibility": plausibility,
                            "reopen_combined_signal": combined,
                            "reopen_distance": candidate.distance_metres,
                        },
                    )
                else:
                    breakdown_notes.append(
                        f"Reopen candidate found but floors not met: "
                        f"visual={ctx.visual_confidence:.2f} (floor {REOPEN_VISUAL_FLOOR}), "
                        f"freshness={ctx.freshness_confidence:.2f} (floor {REOPEN_FRESHNESS_FLOOR}), "
                        f"combined={combined:.3f} (floor {REOPEN_COMBINED_FLOOR})."
                    )

        # ── Step 5: Score-only ─────────────────────────────────────────────
        if evidence_score >= VALID_THRESHOLD:
            state = "valid_civic_report"
        elif evidence_score >= REVIEW_THRESHOLD:
            state = "needs_admin_review"
        else:
            state = "insufficient_evidence"

        return self._make_result(
            decision_state=state,
            evidence_score=evidence_score,
            ctx=ctx,
            linked_report_id=None,
            image_reuse_flag=image_reuse_flag,
            image_reuse_prior_report_id=image_reuse_prior_report_id,
            image_reuse_prior_status=image_reuse_prior_status,
            breakdown_notes=breakdown_notes,
            extra_breakdown={},
        )

    # ── Internal result builder ─────────────────────────────────────────────

    def _make_result(
        self,
        decision_state: str,
        evidence_score: float,
        ctx: DecisionContext,
        linked_report_id: Optional[str],
        image_reuse_flag: bool,
        image_reuse_prior_report_id: Optional[str],
        image_reuse_prior_status: Optional[str],
        is_reopened: bool = False,
        breakdown_notes: Optional[list[str]] = None,
        extra_breakdown: Optional[dict] = None,
    ) -> EvidenceResult:
        admin_priority = _assign_admin_priority(
            decision_state,
            evidence_score,
            ctx.visual_confidence,
            ctx.severity,
        )

        breakdown: dict = {
            "visual_confidence": ctx.visual_confidence,
            "category_confidence": ctx.category_confidence,
            "location_confidence": ctx.location_confidence,
            "freshness_confidence": ctx.freshness_confidence,
            "evidence_score": evidence_score,
            "decision_state": decision_state,
            "admin_priority": admin_priority,
            "severity": ctx.severity,
            "gps_accuracy_metres": ctx.gps_accuracy_metres,
            "image_reuse_flag": image_reuse_flag,
            "image_reuse_prior_report_id": image_reuse_prior_report_id,
            "image_reuse_prior_status": image_reuse_prior_status,
            "notes": breakdown_notes or [],
            "evidence_disclaimer": (
                "Evidence scores reflect the strength of submitted evidence only, "
                "not a verified assessment of current road conditions."
            ),
        }
        if extra_breakdown:
            breakdown.update(extra_breakdown)

        return EvidenceResult(
            decision_state=decision_state,
            evidence_score=evidence_score,
            admin_priority=admin_priority,
            visual_confidence=ctx.visual_confidence,
            category_confidence=ctx.category_confidence,
            location_confidence=ctx.location_confidence,
            freshness_confidence=ctx.freshness_confidence,
            severity=ctx.severity,
            is_reopened=is_reopened,
            linked_report_id=linked_report_id,
            image_reuse_flag=image_reuse_flag,
            image_reuse_prior_report_id=image_reuse_prior_report_id,
            image_reuse_prior_status=image_reuse_prior_status,
            citizen_message=_citizen_message(decision_state),
            evidence_breakdown=breakdown,
        )
