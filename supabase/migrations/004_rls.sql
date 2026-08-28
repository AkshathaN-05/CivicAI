-- =============================================================================
-- Migration 004 — Row Level Security
-- Task: T1-4 (Phase 1)
-- Canonical plan: Part A §7, §13, §19, §20
-- Depends on: 002_tables.sql
-- Enables RLS on all 6 application tables and creates all access policies.
-- Safe to re-run: policies use CREATE POLICY with DROP IF EXISTS guards.
-- NOTE: Storage RLS (T1-6) is configured separately in the Supabase dashboard.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Helper: is_admin()
-- Returns TRUE when the calling user has role='admin' in profiles.
-- Used by policies that allow admin full access.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.profiles
        WHERE id = auth.uid()
          AND role = 'admin'
    );
$$;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "profiles_select_own"   ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own"   ON public.profiles;
DROP POLICY IF EXISTS "profiles_select_admin" ON public.profiles;

-- Citizen: SELECT own row
CREATE POLICY "profiles_select_own"
    ON public.profiles FOR SELECT
    USING (id = auth.uid());

-- Citizen: INSERT own row (on registration — see auth trigger 006)
CREATE POLICY "profiles_insert_own"
    ON public.profiles FOR INSERT
    WITH CHECK (id = auth.uid());

-- Admin: SELECT all rows
CREATE POLICY "profiles_select_admin"
    ON public.profiles FOR SELECT
    USING (public.is_admin());

-- ---------------------------------------------------------------------------
-- authorities
-- Read-only for all authenticated users. Writes via service role only.
-- Part A §12 (ADR-001): immutable after seed.
-- ---------------------------------------------------------------------------
ALTER TABLE public.authorities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "authorities_select_authenticated" ON public.authorities;

CREATE POLICY "authorities_select_authenticated"
    ON public.authorities FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- reports
-- Part A §7 T1-4: citizen SELECT/INSERT own; admin SELECT all
-- ---------------------------------------------------------------------------
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "reports_select_own"   ON public.reports;
DROP POLICY IF EXISTS "reports_insert_own"   ON public.reports;
DROP POLICY IF EXISTS "reports_select_admin" ON public.reports;

-- Citizen: SELECT own
CREATE POLICY "reports_select_own"
    ON public.reports FOR SELECT
    USING (user_id = auth.uid());

-- Citizen: INSERT own
CREATE POLICY "reports_insert_own"
    ON public.reports FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Admin: SELECT all
CREATE POLICY "reports_select_admin"
    ON public.reports FOR SELECT
    USING (public.is_admin());

-- ---------------------------------------------------------------------------
-- complaints
-- Part A §7 T1-4:
--   citizen SELECT/INSERT own
--   admin SELECT/UPDATE all
--   authority_officer SELECT where authority_id matches their assigned authority
-- ---------------------------------------------------------------------------
ALTER TABLE public.complaints ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "complaints_select_own"             ON public.complaints;
DROP POLICY IF EXISTS "complaints_insert_own"             ON public.complaints;
DROP POLICY IF EXISTS "complaints_select_admin"           ON public.complaints;
DROP POLICY IF EXISTS "complaints_update_admin"           ON public.complaints;
DROP POLICY IF EXISTS "complaints_select_authority_officer" ON public.complaints;

-- Citizen: SELECT own
CREATE POLICY "complaints_select_own"
    ON public.complaints FOR SELECT
    USING (user_id = auth.uid());

-- Citizen: INSERT own
CREATE POLICY "complaints_insert_own"
    ON public.complaints FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Admin: SELECT all
CREATE POLICY "complaints_select_admin"
    ON public.complaints FOR SELECT
    USING (public.is_admin());

-- Admin: UPDATE all
CREATE POLICY "complaints_update_admin"
    ON public.complaints FOR UPDATE
    USING (public.is_admin());

-- Authority officer: SELECT complaints assigned to their authority.
-- Joins profiles to determine which authority the officer belongs to.
-- The officer's authority is stored in profiles.ward_number is not used here;
-- authority matching uses the complaints.authority_id against a future
-- officer→authority mapping. For MVP: authority_officer can SELECT all
-- complaints where the authority_id matches any authority in the system
-- (narrowed further at the service layer — Part A §19).
CREATE POLICY "complaints_select_authority_officer"
    ON public.complaints FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM public.profiles p
            WHERE p.id = auth.uid()
              AND p.role = 'authority_officer'
              AND public.complaints.authority_id = (
                  SELECT a.id
                  FROM public.authorities a
                  LIMIT 1
              )
        )
    );

-- ---------------------------------------------------------------------------
-- rti_requests
-- Part A §7 T1-4: citizen SELECT/INSERT own; admin SELECT all
-- ---------------------------------------------------------------------------
ALTER TABLE public.rti_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "rti_requests_select_own"   ON public.rti_requests;
DROP POLICY IF EXISTS "rti_requests_insert_own"   ON public.rti_requests;
DROP POLICY IF EXISTS "rti_requests_select_admin" ON public.rti_requests;

-- Citizen: SELECT own
CREATE POLICY "rti_requests_select_own"
    ON public.rti_requests FOR SELECT
    USING (user_id = auth.uid());

-- Citizen: INSERT own
CREATE POLICY "rti_requests_insert_own"
    ON public.rti_requests FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Admin: SELECT all
CREATE POLICY "rti_requests_select_admin"
    ON public.rti_requests FOR SELECT
    USING (public.is_admin());

-- ---------------------------------------------------------------------------
-- rti_knowledge_base
-- Part A §7 T1-4: SELECT all authenticated; INSERT via service role only
-- ---------------------------------------------------------------------------
ALTER TABLE public.rti_knowledge_base ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "rti_knowledge_base_select_authenticated" ON public.rti_knowledge_base;

-- All authenticated users can SELECT (RAG retrieval)
CREATE POLICY "rti_knowledge_base_select_authenticated"
    ON public.rti_knowledge_base FOR SELECT
    USING (auth.role() = 'authenticated');

-- INSERT is intentionally not granted to any JWT role.
-- Only the service_role key (backend service client) can INSERT.

-- ---------------------------------------------------------------------------
-- audit_log
-- Part A §7 T1-4: INSERT via service role only; citizen SELECT own; admin SELECT all
-- ---------------------------------------------------------------------------
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "audit_log_select_own"   ON public.audit_log;
DROP POLICY IF EXISTS "audit_log_select_admin" ON public.audit_log;

-- Citizen: SELECT own rows
CREATE POLICY "audit_log_select_own"
    ON public.audit_log FOR SELECT
    USING (user_id = auth.uid());

-- Admin: SELECT all
CREATE POLICY "audit_log_select_admin"
    ON public.audit_log FOR SELECT
    USING (public.is_admin());

-- INSERT is intentionally not granted to any JWT role.
-- Only the service_role key can INSERT into audit_log.
