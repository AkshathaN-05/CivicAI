"""Report service — orchestrates report creation and retrieval.

Storage is intentionally isolated behind a repository interface so it can be
swapped from in-memory to Supabase without changing the service contract.
All business logic stays here; route handlers remain thin (Part A §6).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from schemas.report import (
    AuthorityOut,
    IssueCategory,
    ReportCreate,
    ReportOut,
    ReportStatus,
    CATEGORY_LABELS,
)
from services.authority_service import route_to_authority

# ---------------------------------------------------------------------------
# In-memory demo repository — replace with Supabase repo at T3-3
# ---------------------------------------------------------------------------

_STORE: dict[str, ReportOut] = {}


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


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------

def create_report(
    payload: ReportCreate,
    photo_filename: Optional[str] = None,
) -> ReportOut:
    authority, reason, confidence = route_to_authority(
        payload.category.value,
        payload.area_text,
    )

    report = ReportOut(
        report_id=str(uuid.uuid4()),
        category=payload.category,
        category_label=CATEGORY_LABELS[payload.category.value],
        area_text=payload.area_text,
        description=payload.description,
        status=ReportStatus.submitted,
        recommended_authority=_authority_dict_to_out(authority),
        match_reason=reason,
        confidence=confidence,
        created_at=datetime.now(timezone.utc),
        photo_filename=photo_filename,
    )
    _STORE[report.report_id] = report
    return report


def get_report(report_id: str) -> Optional[ReportOut]:
    return _STORE.get(report_id)


def list_reports() -> list[ReportOut]:
    return sorted(_STORE.values(), key=lambda r: r.created_at, reverse=True)
