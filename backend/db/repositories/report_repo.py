"""Report repository — Supabase data-access layer.

Field mapping between the service/API layer and the public.reports table:

  API / service      DB column
  -----------------  ------------------
  report_id          id  (UUID)
  category           ai_category
  area_text          address_text
  confidence         ai_confidence
  authority.id       ai_authority_id
  photo_filename     image_original_path
  description        ai_raw_response->description  (JSONB)
  match_reason       ai_raw_response->match_reason (JSONB)
  status             (not stored — always SUBMITTED)
  category_label     (not stored — derived from category)
  recommended_auth   (not stored — re-looked up from JSON via authority_service)

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
