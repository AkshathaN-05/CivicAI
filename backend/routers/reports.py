"""Reports router — thin handlers only.  All logic is in services/report_service.py.

Endpoints (Part A §18):
  POST /api/v1/reports       — create report (multipart, photo optional); JWT required (T3-3)
  GET  /api/v1/reports       — list all reports (auth required)
  GET  /api/v1/reports/{id}  — get single report; ownership enforced (T3-3 IDOR protection)

T3-3 AI pipeline path (Part A §22, §23):
  When a photo is uploaded AND no category/description are supplied, the handler
  calls create_report_from_image() which runs the full AI pipeline (T2-11):
    validate → redact → hash → YOLO → confidence → authority → LLM → storage → DB.
  The AI endpoint is rate-limited to 10/minute (Part A §13).

Backward-compatible text path:
  When category AND description are supplied (regardless of whether a photo is
  present), the handler uses the existing create_report() path with route_to_authority.
  The photo, if present, is stored as photo_filename (the original upload filename).
  This path preserves all existing tests and the camera+location workflow.

Path selection (T3-3):
  AI pipeline path:   photo uploaded AND (category is None OR description is None)
  Text fallback path: category provided AND description provided (photo optional)

NOTE: from __future__ import annotations is intentionally omitted in this module.
FastAPI resolves Form-field types at import time; that import turns all annotations
into strings (PEP 563), which causes Pydantic TypeAdapter failures when resolving
Optional[IssueCategory] for Form parameters.
"""
# NOTE: No from __future__ import annotations — see module docstring.

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, status
from pydantic import ValidationError

from dependencies import get_current_user, limiter, RATE_LIMIT_AI
from schemas.report import IssueCategory, ReportCreate, ReportListOut, ReportOut, ReportPatch
from security.input_sanitizer import sanitize_text
from security.ownership import verify_ownership
from services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT_AI)
async def create_report(
    request: Request,
    category: Optional[IssueCategory] = Form(None),
    area_text: str = Form(...),
    description: Optional[str] = Form(None),
    lat: Optional[float] = Form(None),
    lng: Optional[float] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    """Create a new civic issue report.  Requires a valid JWT (T3-3).

    Path selection (T3-3 AI pipeline vs backward-compatible text path):

    AI pipeline path (T3-3):
      Triggered when: photo is uploaded AND (category is None OR description is None).
      Runs the full AI pipeline (T2-11) to validate, redact, classify, and generate
      description.  lat/lng from GPS geolocation are passed for authority routing.
      category and description are derived from AI results — the AI is authoritative
      when the text fields are absent.

    Text-based path (backward-compatible):
      Triggered when: category AND description are both supplied.
      Uses route_to_authority directly — same behavior as pre-T3-3.
      Photo (if present) is stored as photo_filename (original upload filename).
      This path is used by all existing tests and the camera+location workflow.

    No photo, no category/description → 422 (neither path can proceed).
    """
    user_id: str = current_user["sub"]
    image_bytes: Optional[bytes] = None
    claimed_mime: str = ""
    photo_filename: Optional[str] = None

    if photo and photo.filename:
        if photo.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported image type: {photo.content_type}. "
                       "Allowed: jpeg, png, webp, gif.",
            )
        image_bytes = await photo.read()
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Photo must be under 10 MB.",
            )
        claimed_mime = photo.content_type or ""
        photo_filename = photo.filename

    # Sanitize user-controlled text inputs (T3-3 / input_sanitizer).
    clean_area_text = sanitize_text(area_text, max_length=500)

    # ---------------------------------------------------------------------------
    # Path selection: AI pipeline (T3-3) vs text-based (backward-compatible)
    # ---------------------------------------------------------------------------
    use_ai_pipeline = image_bytes is not None and (category is None or not description)

    # ---------------------------------------------------------------------------
    # AI pipeline path — photo uploaded, no text classification provided (T3-3)
    # ---------------------------------------------------------------------------
    if use_ai_pipeline:
        try:
            report = await report_service.create_report_from_image(
                image_bytes=image_bytes,
                claimed_mime=claimed_mime,
                lat=lat,
                lng=lng,
                address=clean_area_text,
                user_id=user_id,
            )
            return report
        except Exception as exc:
            # Detect ImageValidationError by class name (avoids import at module level).
            exc_type_name = type(exc).__name__
            if exc_type_name == "ImageValidationError" or "ImageValidationError" in str(type(exc).__mro__):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(exc),
                )
            # Any other AI pipeline failure → 500.
            import logging
            logging.getLogger(__name__).error(
                "create_report: AI pipeline failed: %s", exc, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI pipeline failed to process the image. Please try again.",
            )

    # ---------------------------------------------------------------------------
    # Text-based path — category + description provided (backward-compatible)
    # ---------------------------------------------------------------------------
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="category is required when no photo is uploaded.",
        )
    if not description:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="description is required when no photo is uploaded.",
        )

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

    report = report_service.create_report(payload, photo_filename=photo_filename, user_id=user_id)
    return report


@router.patch("/{report_id}", response_model=ReportOut)
async def patch_report(
    report_id: str,
    body: ReportPatch,
    current_user: dict = Depends(get_current_user),
):
    """Citizen confirms/edits AI result after Stage 2 review (Priority 3).

    Allowed fields: category (override), description (edit), authority_id (override).
    All fields are optional — only supplied fields are updated.

    Ownership enforced: only the report owner may call this endpoint.
    Admin role bypasses ownership check.

    This endpoint does NOT advance the report status — the report remains SUBMITTED
    until an admin acts on it.
    """
    result = report_service.get_report_with_owner(report_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )

    _report, owner_user_id = result
    user_id: str = current_user["sub"]
    user_role: str = current_user.get("app_role", "citizen")

    # Admins bypass ownership.
    if user_role != "admin" and owner_user_id:
        verify_ownership(owner_user_id, user_id)

    # Sanitize description if provided (input_sanitizer, T3-3).
    clean_description: Optional[str] = None
    if body.description is not None:
        clean_description = sanitize_text(body.description, max_length=2000)
        if len(clean_description) < 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="description must be at least 10 characters after sanitization.",
            )

    return report_service.update_report_fields(
        report_id=report_id,
        category=body.category,
        description=clean_description,
        authority_id=body.authority_id,
    )


@router.get("/", response_model=ReportListOut)
async def list_reports(
    current_user: dict = Depends(get_current_user),
):
    """List reports for the authenticated user.

    - Citizens see only their own reports.
    - Admins see all reports.

    Requires a valid JWT (T3-3).
    """
    user_id: str = current_user["sub"]
    user_role: str = current_user.get("app_role", "citizen")

    if user_role == "admin":
        reports = report_service.list_reports()
    else:
        reports = report_service.list_reports_for_user(user_id)

    return ReportListOut(reports=reports, total=len(reports))


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single report by ID.  Returns report with signed image URLs (T3-3).

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
