"""Admin router — admin-only report management (Part A §19, T3-1 RBAC).

Exposes:
  GET   /api/v1/admin/reports              — paginated list of all reports (admin only)
  GET   /api/v1/admin/stats                — aggregate statistics (admin only)
  PATCH /api/v1/admin/reports/{id}/status  — update report status (admin only)

All endpoints require a valid JWT with app_role == "admin".
Business logic lives in report_service.py — routers are thin handlers only
(Part A §6).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_current_user
from security.rbac import require_role
from security.input_sanitizer import sanitize_text
from schemas.report import AdminStatusUpdate, ReportListOut, ReportOut, REJECTION_REASON_MAX_LENGTH
from services import report_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/reports", response_model=ReportListOut)
async def admin_list_reports(
    _admin: dict = Depends(require_role("admin")),
):
    """List ALL reports — admin only (bypasses ownership filter)."""
    reports = report_service.list_reports()
    return ReportListOut(reports=reports, total=len(reports))


@router.get("/stats")
async def admin_stats(
    _admin: dict = Depends(require_role("admin")),
):
    """Return aggregate statistics for the admin dashboard."""
    reports = report_service.list_reports()
    total = len(reports)

    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_authority: dict[str, int] = {}

    for r in reports:
        cat = r.category_label or r.category.value
        by_category[cat] = by_category.get(cat, 0) + 1

        st = r.status.value if hasattr(r.status, "value") else str(r.status)
        by_status[st] = by_status.get(st, 0) + 1

        if r.recommended_authority:
            auth_name = r.recommended_authority.short_name
            by_authority[auth_name] = by_authority.get(auth_name, 0) + 1

    return {
        "total_reports": total,
        "by_category": by_category,
        "by_status": by_status,
        "by_authority": by_authority,
    }


@router.patch("/reports/{report_id}/status", response_model=ReportOut)
async def admin_update_report_status(
    report_id: str,
    payload: AdminStatusUpdate,
    admin: dict = Depends(require_role("admin")),
):
    """Update the status of a single report — admin only.

    Allowed status transitions (Part A §24):
        SUBMITTED    → UNDER_REVIEW, REJECTED, ARCHIVED
        UNDER_REVIEW → RESOLVED, REJECTED, ARCHIVED
        RESOLVED     → ARCHIVED
        REJECTED     → ARCHIVED
        ARCHIVED     → (terminal, no transitions allowed)

    When new_status is REJECTED, rejection_reason is REQUIRED.
    When new_status is anything else, rejection_reason must be absent.

    Raises:
        401 — missing or invalid JWT.
        403 — authenticated user is not an admin.
        404 — report not found.
        422 — invalid status transition or missing rejection_reason.
    """
    admin_user_id: str = admin["sub"]

    # Sanitize rejection reason before passing to service layer (Part A §9).
    # AdminStatusUpdate already validated length/presence; sanitize strips
    # any residual injection characters.
    clean_reason: str | None = None
    if payload.rejection_reason is not None:
        clean_reason = sanitize_text(payload.rejection_reason, max_length=REJECTION_REASON_MAX_LENGTH)
        # If sanitizer stripped everything, treat as missing (should not
        # happen after AdminStatusUpdate validation, but defensive).
        if not clean_reason:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="rejection_reason must not be empty after sanitization.",
            )

    # All business logic — transition validation, DB update, in-memory update —
    # is in the service layer (Part A §6).
    return report_service.admin_update_report_status(
        report_id=report_id,
        new_status=payload.new_status,
        rejection_reason=clean_reason,
        admin_user_id=admin_user_id,
    )
