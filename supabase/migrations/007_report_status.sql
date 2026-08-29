-- =============================================================================
-- Migration 007 — Report Status and Rejection Reason
-- Depends on: 001_enums.sql, 002_tables.sql, 004_rls.sql
-- Safe to re-run: ADD COLUMN IF NOT EXISTS; policy guards use DROP IF EXISTS.
--
-- Changes:
--   1. Add reports.status       TEXT NOT NULL DEFAULT 'SUBMITTED'
--      Stores the current admin-managed lifecycle status of the report.
--      Uses TEXT (not the complaint_status enum) to avoid ALTER TYPE complexity
--      and to stay decoupled from the complaints table enum; values are
--      constrained to the same set via a CHECK constraint.
--
--   2. Add reports.rejection_reason  TEXT
--      Stores the admin-supplied reason when a report is rejected.
--      NULL for non-rejected reports.  Max 500 characters enforced at app layer.
--
--   3. Add RLS UPDATE policy for admins on reports.
--      The existing 004_rls.sql only grants admins SELECT on reports.
--      Status updates require UPDATE permission (admin only).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. reports.status
-- ---------------------------------------------------------------------------
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'SUBMITTED'
    CHECK (status IN (
        'SUBMITTED',
        'UNDER_REVIEW',
        'RESOLVED',
        'REJECTED',
        'ARCHIVED'
    ));

-- ---------------------------------------------------------------------------
-- 2. reports.rejection_reason
-- ---------------------------------------------------------------------------
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- ---------------------------------------------------------------------------
-- 3. Admin UPDATE policy on reports
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "reports_update_admin" ON public.reports;

CREATE POLICY "reports_update_admin"
    ON public.reports FOR UPDATE
    USING (public.is_admin())
    WITH CHECK (public.is_admin());
