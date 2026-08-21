"""Reports router — thin handlers only.  All logic is in services/report_service.py.

Endpoints (Part A §18):
  POST /api/v1/reports       — create report (multipart, photo optional)
  GET  /api/v1/reports       — list all reports (demo: no auth)
  GET  /api/v1/reports/{id}  — get single report
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from schemas.report import IssueCategory, ReportCreate, ReportListOut, ReportOut
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
):
    """Create a new civic issue report."""
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

    try:
        payload = ReportCreate(
            category=category,
            area_text=area_text,
            description=description,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        )
    report = report_service.create_report(payload, photo_filename=photo_filename)
    return report


@router.get("/", response_model=ReportListOut)
async def list_reports():
    """List all submitted reports (demo — no auth required)."""
    reports = report_service.list_reports()
    return ReportListOut(reports=reports, total=len(reports))


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: str):
    """Get a single report by ID."""
    report = report_service.get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    return report
