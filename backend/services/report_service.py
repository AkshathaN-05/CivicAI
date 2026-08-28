"""Report service — orchestrates report creation and retrieval.

Storage is intentionally isolated behind a repository interface so it can be
swapped from in-memory to Supabase without changing the service contract.
All business logic stays here; route handlers remain thin (Part A §6).

Persistence strategy:
  1. Always build the ReportOut object and write it to _STORE (in-memory).
  2. If Supabase is fully configured (URL + SERVICE_KEY + DEMO_USER_ID), also
     persist to the public.reports table via report_repo.
  3. On any Supabase error, the in-memory entry is already present so the
     response is unaffected.

Read strategy:
  1. Try Supabase first (get_report / list_reports).
  2. Fall back to _STORE if Supabase is unconfigured or the row is not found.
  This means data written to Supabase is visible even after a process restart,
  while the app degrades gracefully to in-memory when Supabase is unavailable.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from config import settings
from schemas.report import (
    AuthorityOut,
    IssueCategory,
    ReportCreate,
    ReportOut,
    ReportStatus,
    CATEGORY_LABELS,
)
from services.authority_service import get_authority_by_id, route_to_authority

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory demo repository — kept intact as fallback (Part A §6, T3-3)
# ---------------------------------------------------------------------------

_STORE: dict[str, ReportOut] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _supabase_enabled() -> bool:
    """True only when all three required settings are non-empty."""
    return bool(
        settings.SUPABASE_URL
        and settings.SUPABASE_SERVICE_KEY
        and settings.DEMO_USER_ID
    )


def _authority_dict_to_out(a: Optional[dict]) -> Optional[AuthorityOut]:
    if a is None:
        return None
    return AuthorityOut(
        id=a["id"],
        name=a["name"],
        short_name=a["short_name"],
        contact_email=a["contact_email"],
        phone=a["phone"],
    )


def _row_to_report_out(row: dict) -> Optional[ReportOut]:
    """Convert a public.reports DB row dict into a ReportOut.

    Field mapping (DB → API):
      id               → report_id
      ai_category      → category
      address_text     → area_text
      ai_confidence    → confidence
      ai_authority_id  → recommended_authority (re-looked-up from JSON)
      image_original_path → photo_filename
      ai_raw_response  → description + match_reason (extracted from JSONB)
      created_at       → created_at
      status           → always ReportStatus.submitted (not stored in DB)
    """
    try:
        category_val = row.get("ai_category") or "other"
        raw = row.get("ai_raw_response") or {}
        description = raw.get("description", "")
        match_reason = raw.get("match_reason")
        confidence = float(row.get("ai_confidence") or 0.0)
        authority_id = row.get("ai_authority_id")
        authority_dict = get_authority_by_id(authority_id) if authority_id else None
        created_at_val = row.get("created_at")
        if isinstance(created_at_val, str):
            from datetime import datetime as _dt
            # Supabase returns ISO strings; parse robustly.
            created_at_val = _dt.fromisoformat(
                created_at_val.replace("Z", "+00:00")
            )

        return ReportOut(
            report_id=str(row["id"]),
            category=IssueCategory(category_val),
            category_label=CATEGORY_LABELS.get(category_val, category_val),
            area_text=row.get("address_text") or "",
            description=description,
            status=ReportStatus.submitted,
            recommended_authority=_authority_dict_to_out(authority_dict),
            match_reason=match_reason,
            confidence=min(max(confidence, 0.0), 1.0),
            created_at=created_at_val or datetime.now(timezone.utc),
            photo_filename=row.get("image_original_path"),
        )
    except Exception:
        logger.warning("_row_to_report_out: failed to parse DB row.", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------

def create_report(
    payload: ReportCreate,
    photo_filename: Optional[str] = None,
) -> ReportOut:
    # Authority routing always uses the immutable JSON (ADR-001 — unchanged).
    authority, reason, confidence = route_to_authority(
        payload.category.value,
        payload.area_text,
    )

    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    report = ReportOut(
        report_id=report_id,
        category=payload.category,
        category_label=CATEGORY_LABELS[payload.category.value],
        area_text=payload.area_text,
        description=payload.description,
        status=ReportStatus.submitted,
        recommended_authority=_authority_dict_to_out(authority),
        match_reason=reason,
        confidence=confidence,
        created_at=now,
        photo_filename=photo_filename,
    )

    # Always write to in-memory store first — guarantees the response is
    # available regardless of Supabase outcome.
    _STORE[report.report_id] = report

    # Attempt Supabase persistence when fully configured.
    if _supabase_enabled():
        try:
            from db.repositories import report_repo

            row = {
                "id": report_id,
                "user_id": settings.DEMO_USER_ID,
                "ai_category": payload.category.value,
                "address_text": payload.area_text,
                "ai_confidence": confidence,
                "ai_authority_id": authority["id"] if authority else None,
                "image_original_path": photo_filename,
                "ai_raw_response": {
                    "description": payload.description,
                    "match_reason": reason,
                },
                # created_at left to DB default (NOW())
            }
            inserted = report_repo.insert_report(row)
            if inserted:
                # Use the DB-assigned created_at so reads are consistent.
                db_report = _row_to_report_out(inserted)
                if db_report:
                    _STORE[report.report_id] = db_report
                    return db_report
        except Exception:
            logger.warning(
                "create_report: Supabase insert failed — using in-memory result.",
                exc_info=True,
            )

    return report


def get_report(report_id: str) -> Optional[ReportOut]:
    # Try Supabase first so data survives process restarts.
    if _supabase_enabled():
        try:
            from db.repositories import report_repo

            row = report_repo.get_report_by_id(report_id)
            if row:
                return _row_to_report_out(row)
        except Exception:
            logger.warning(
                "get_report: Supabase query failed — falling back to in-memory.",
                exc_info=True,
            )

    return _STORE.get(report_id)


def list_reports() -> list[ReportOut]:
    # Try Supabase first; fall back to in-memory.
    if _supabase_enabled():
        try:
            from db.repositories import report_repo

            rows = report_repo.list_reports()
            if rows is not None:  # empty list is valid (zero reports)
                reports = [_row_to_report_out(r) for r in rows]
                return [r for r in reports if r is not None]
        except Exception:
            logger.warning(
                "list_reports: Supabase query failed — falling back to in-memory.",
                exc_info=True,
            )

    return sorted(_STORE.values(), key=lambda r: r.created_at, reverse=True)
