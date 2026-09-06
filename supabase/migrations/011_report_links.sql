-- =============================================================================
-- Migration 011 — report_links table
-- Depends on: 010_evidence_fields.sql
-- Safe to re-run: CREATE TABLE IF NOT EXISTS; DROP POLICY IF EXISTS.
--
-- Creates the report_links relationship table used to record:
--   'duplicate'          — exact same image hash, active target report
--   'supporting_evidence'— geo-proximity match with active target report
--   'reopened'           — new report references a recently-resolved target
--
-- source_report_id = new incoming report
-- target_report_id = existing active/resolved report it is linked to
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.report_links (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_report_id   UUID        NOT NULL REFERENCES public.reports(id) ON DELETE CASCADE,
    target_report_id   UUID        NOT NULL REFERENCES public.reports(id) ON DELETE CASCADE,
    link_type          TEXT        NOT NULL CHECK (link_type IN (
                                       'duplicate',
                                       'supporting_evidence',
                                       'reopened'
                                   )),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_report_id, target_report_id)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
-- Find all supporting evidence for a target report (admin "N supporting reports" count)
CREATE INDEX IF NOT EXISTS idx_report_links_target
    ON public.report_links (target_report_id);

-- Find all links sourced from a given report (citizen "your report is linked" lookup)
CREATE INDEX IF NOT EXISTS idx_report_links_source
    ON public.report_links (source_report_id);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE public.report_links ENABLE ROW LEVEL SECURITY;

-- Citizens can see links where their own report is either source or target.
DROP POLICY IF EXISTS "report_links_citizen_select" ON public.report_links;
CREATE POLICY "report_links_citizen_select"
    ON public.report_links FOR SELECT TO authenticated
    USING (
        source_report_id IN (SELECT id FROM public.reports WHERE user_id = auth.uid())
        OR
        target_report_id IN (SELECT id FROM public.reports WHERE user_id = auth.uid())
    );

-- Admins can see all links.
DROP POLICY IF EXISTS "report_links_admin_select" ON public.report_links;
CREATE POLICY "report_links_admin_select"
    ON public.report_links FOR SELECT TO authenticated
    USING (public.is_admin());

-- Service role inserts (no JWT policy needed — service_role bypasses RLS).
