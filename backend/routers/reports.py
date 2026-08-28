"""Reports router — thin handlers only.  All logic is in services/report_service.py.

Endpoints (Part A §18):
  POST /api/v1/reports       — create report (multipart, photo optional); JWT required (T3-3)
  GET  /api/v1/reports       — list all reports (demo: no auth)
  GET  /api/v1/reports/{id}  — get single report; ownership enforced (T3-3 IDOR protection)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import ValidationError

from dependencies import get_current_user
from schemas.report import IssueCategory, ReportCreate, ReportListOut, ReportOut
from security.input_sanitizer import sanitize_text
from security.ownership import verify_ownership
from services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    category: IssueCategory = Form(...),
    area_text: str = Form(...),
    description: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    """Create a new civic issue report.  Requires a valid JWT (T3-3)."""
    photo_filename: Optional[str] = None

    if photo and photo.filename:
        if photo.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported image type: {photo.content_type}. "
                       "Allowed: jpeg, png, webp, gif.",
            )
        content = await photo.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Photo must be under 10 MB.",
            )
        photo_filename = photo.filename

    # Sanitize user-controlled text before validation and persistence (T3-3).
    clean_area_text = sanitize_text(area_text, max_length=500)
    clean_description = sanitize_text(description, max_length=2000)

    try:
        payload = ReportCreate(
            category=category,
            area_text=clean_area_text,
            description=clean_description,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        )

    user_id: str = current_user["sub"]
    report = report_service.create_report(payload, photo_filename=photo_filename, user_id=user_id)
    return report


@router.get("/", response_model=ReportListOut)
async def list_reports():
    """List all submitted reports (demo — no auth required)."""
    reports = report_service.list_reports()
    return ReportListOut(reports=reports, total=len(reports))


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single report by ID.

    Ownership enforced: a citizen may only access their own report (T3-3 IDOR
    protection).  Admin role bypasses the ownership check (Part A §19).
    """
    result = report_service.get_report_with_owner(report_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )

    report, owner_user_id = result
    user_id: str = current_user["sub"]
    user_role: str = current_user.get("app_role", "citizen")

    # Admins bypass ownership (Part A §19).
    if user_role != "admin" and owner_user_id:
        verify_ownership(owner_user_id, user_id)

    return report
