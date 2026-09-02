"""Schema validator — checks that required DB columns exist at startup.

Called once during application startup (from main.py lifespan) when Supabase
is configured.  Logs a clear WARNING if any required column is missing so the
operator knows to apply pending migrations before status management works.

Does NOT raise — the application can start without the columns (in-memory mode
or pre-migration deployment), but admin status updates will fail with 502 until
the migrations are applied.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Columns in public.reports that migration 007 adds.
# If any are missing, admin status updates cannot be persisted to DB.
REQUIRED_REPORT_COLUMNS: tuple[str, ...] = ("status", "rejection_reason")


def validate_reports_schema() -> bool:
    """Check that public.reports has the columns required by migration 007.

    Returns:
        True  — all required columns exist.
        False — one or more columns are missing (migration 007 not applied).
        None  — Supabase not configured or check failed; treated as non-blocking.
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        logger.debug("validate_reports_schema: Supabase not configured — skipping.")
        return True  # Not applicable; in-memory mode is fine

    try:
        # SELECT the specific columns; a 42703 error means column is missing.
        cols = ", ".join(REQUIRED_REPORT_COLUMNS)
        client.table("reports").select(cols).limit(0).execute()
        logger.debug(
            "validate_reports_schema: all required columns present (%s).",
            ", ".join(REQUIRED_REPORT_COLUMNS),
        )
        return True
    except Exception as exc:
        exc_str = str(exc)
        if "42703" in exc_str or "does not exist" in exc_str:
            # Determine which columns are missing for a precise warning.
            missing = []
            for col in REQUIRED_REPORT_COLUMNS:
                try:
                    client.table("reports").select(col).limit(0).execute()
                except Exception:
                    missing.append(col)

            logger.warning(
                "============================================================\n"
                "SCHEMA MIGRATION REQUIRED\n"
                "============================================================\n"
                "The following columns are missing from public.reports:\n"
                "  %s\n"
                "\n"
                "Migration 007 has not been applied to the remote database.\n"
                "Admin status updates (Under Review / Resolve / Reject) will\n"
                "fail with HTTP 502 until the migration is applied.\n"
                "\n"
                "To apply the migration:\n"
                "  Option A — Supabase Dashboard SQL Editor:\n"
                "    https://supabase.com/dashboard/project/<ref>/sql/new\n"
                "    Paste: supabase/migrations/007_report_status.sql\n"
                "\n"
                "  Option B — Supabase CLI:\n"
                "    supabase db push --project-ref <ref>\n"
                "    (requires SUPABASE_ACCESS_TOKEN or --password)\n"
                "\n"
                "  Option C — Direct postgres connection:\n"
                "    psql <connection-string> < supabase/migrations/007_report_status.sql\n"
                "============================================================",
                ", ".join(f"reports.{c}" for c in missing),
            )
            return False
        else:
            logger.warning(
                "validate_reports_schema: unexpected error during schema check: %s",
                exc_str[:200],
            )
            return True  # Unknown error — don't block startup
