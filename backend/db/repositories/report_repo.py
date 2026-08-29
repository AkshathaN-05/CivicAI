"""Report repository — Supabase data-access layer.

Field mapping between the service/API layer and the public.reports table:

  API / service         DB column
  --------------------  ------------------
  report_id             id  (UUID)
  category              ai_category
  area_text             address_text
  confidence            ai_confidence
  authority.id          ai_authority_id
  photo_filename        image_original_path
  image_hash            image_hash          (T3-3 — BLAKE3 hash from AI pipeline)
  image_redacted_path   image_redacted_path (T3-3 — Storage path for redacted image)
  description           ai_raw_response->description  (JSONB)
  match_reason          ai_raw_response->match_reason (JSONB)
  is_duplicate          ai_raw_response->is_duplicate (JSONB)
  duplicate_report_id   ai_raw_response->duplicate_report_id (JSONB)
  llm_provider_used     ai_raw_response->llm_provider_used (JSONB)
  yolo_class            ai_raw_response->yolo_class (JSONB)
  status                status TEXT (migration 007 — DEFAULT 'SUBMITTED')
  rejection_reason      rejection_reason TEXT (migration 007 — NULL unless REJECTED)
  category_label        (not stored — derived from category)
  recommended_auth      (not stored — re-looked up from JSON via authority_service)

All functions return None / [] on any error so the service layer can fall
back to the in-memory _STORE without surfacing Supabase internals.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

TABLE = "reports"


def insert_report(row: dict) -> Optional[dict]:
    """Insert one report row.  Returns the inserted row dict, or None on error.

    Expected keys in *row*:
        id, user_id, ai_category, address_text, ai_confidence,
        ai_authority_id, image_original_path, ai_raw_response, created_at
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        return None

    try:
        result = (
            client.table(TABLE)
            .insert(row)
            .execute()
        )
        data = result.data
        if data:
            return data[0]
        return None
    except Exception:
        logger.warning("insert_report failed — falling back to in-memory.", exc_info=True)
        return None


def get_report_by_id(report_id: str) -> Optional[dict]:
    """Return a single report row by its UUID, or None if not found / on error."""
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        return None

    try:
        result = (
            client.table(TABLE)
            .select("*")
            .eq("id", report_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if data:
            return data[0]
        return None
    except Exception:
        logger.warning("get_report_by_id failed — falling back to in-memory.", exc_info=True)
        return None


def list_reports() -> Optional[list[dict]]:
    """Return all report rows ordered newest-first.

    Returns:
        list[dict]  — rows from DB (may be empty list if table is empty)
        None        — DB unavailable or query failed; caller should use fallback
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        return None

    try:
        result = (
            client.table(TABLE)
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data if result.data is not None else []
    except Exception:
        logger.warning("list_reports failed — falling back to in-memory.", exc_info=True)
        return None


def list_reports_by_user(user_id: str) -> Optional[list[dict]]:
    """Return report rows belonging to a specific user, ordered newest-first.

    Returns:
        list[dict]  — rows for this user (may be empty list)
        None        — DB unavailable or query failed; caller should use fallback
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        return None

    try:
        result = (
            client.table(TABLE)
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data if result.data is not None else []
    except Exception:
        logger.warning("list_reports_by_user failed — falling back to in-memory.", exc_info=True)
        return None


def update_report_status(
    report_id: str,
    new_status: str,
    rejection_reason: Optional[str] = None,
) -> Optional[dict]:
    """Update the status (and optional rejection_reason) of a report row.

    Args:
        report_id:        UUID string of the report to update.
        new_status:       New status value string (e.g. 'UNDER_REVIEW').
        rejection_reason: Required when new_status == 'REJECTED'; None otherwise.

    Returns:
        The updated row dict, or None on error / DB unavailable.

    Notes:
        - This function only updates status + rejection_reason.
        - The service layer is responsible for transition validation.
        - The Supabase service-role client bypasses RLS for the UPDATE.
          The admin-only RLS policy (migration 007) is an additional layer
          of defence but service-role writes are not subject to it.
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        return None

    try:
        updates: dict = {"status": new_status}
        if rejection_reason is not None:
            updates["rejection_reason"] = rejection_reason
        else:
            # Explicitly clear rejection_reason when moving to a non-rejected
            # status (e.g. if a previous state was REJECTED and admin corrects).
            updates["rejection_reason"] = None

        result = (
            client.table(TABLE)
            .update(updates)
            .eq("id", report_id)
            .execute()
        )
        data = result.data
        if data:
            return data[0]
        return None
    except Exception:
        logger.warning(
            "update_report_status failed for report_id=%s.", report_id, exc_info=True
        )
        return None


def update_report_fields(
    report_id: str,
    updates: dict,
) -> Optional[dict]:
    """Patch specific fields on a report row (citizen confirm step, Priority 3).

    Args:
        report_id: UUID string of the report to update.
        updates:   Dict of DB column name → value.  Caller is responsible for
                   mapping API fields to DB columns:
                     category     → ai_category
                     description  → ai_raw_response (merged into existing JSONB)
                     authority_id → ai_authority_id

    Returns:
        The updated row dict, or None on error / DB unavailable.
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        return None

    try:
        result = (
            client.table(TABLE)
            .update(updates)
            .eq("id", report_id)
            .execute()
        )
        data = result.data
        if data:
            return data[0]
        return None
    except Exception:
        logger.warning(
            "update_report_fields failed for report_id=%s.", report_id, exc_info=True
        )
        return None
