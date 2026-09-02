-- =============================================================================
-- Migration 009 — Supabase Storage Buckets (Part A §20)
-- Task: T3-3 storage bucket creation
-- Depends on: 004_rls.sql
-- Creates the two private storage buckets used for image storage and
-- configures storage RLS policies (T1-6).
--
-- Buckets:
--   report-originals — private; original un-redacted images (service role only)
--   report-redacted  — private; privacy-processed redacted images
--
-- Access model (Part A §20, §28):
--   - Uploads   : backend service-role only (no citizen JWT can upload directly)
--   - Signed URLs: backend service-role generates 15-minute signed URLs
--   - Citizens  : may access their own report-redacted image via signed URL
--   - Admins    : may access any report-redacted image via signed URL
--   - original  : never exposed to citizens or admins via URL (service-role only)
--
-- NOTE: Supabase storage bucket INSERT/SELECT are managed via storage.objects
-- policies. The service-role key bypasses these policies, which is correct for
-- backend uploads. Signed-URL generation also uses the service-role key.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Create private buckets (idempotent — skipped if already exists)
-- ---------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('report-originals', 'report-originals', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('report-redacted', 'report-redacted', false)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Storage RLS policies — report-originals
-- Only the service-role key may INSERT/SELECT (backend uploads + signed URLs).
-- No JWT role is granted direct SELECT — only time-limited signed URLs.
-- ---------------------------------------------------------------------------

-- Drop existing policies before re-creating (idempotent).
DROP POLICY IF EXISTS "originals_service_role_insert" ON storage.objects;
DROP POLICY IF EXISTS "originals_service_role_select" ON storage.objects;

-- Allow service-role to INSERT into report-originals.
CREATE POLICY "originals_service_role_insert"
    ON storage.objects FOR INSERT
    WITH CHECK (
        bucket_id = 'report-originals'
        AND auth.role() = 'service_role'
    );

-- Allow service-role to SELECT from report-originals (needed for signed URL generation).
CREATE POLICY "originals_service_role_select"
    ON storage.objects FOR SELECT
    USING (
        bucket_id = 'report-originals'
        AND auth.role() = 'service_role'
    );

-- ---------------------------------------------------------------------------
-- Storage RLS policies — report-redacted
-- Service-role INSERT (backend upload) + service-role SELECT (signed URL).
-- Citizens/admins access via time-limited signed URLs only (no direct SELECT).
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS "redacted_service_role_insert" ON storage.objects;
DROP POLICY IF EXISTS "redacted_service_role_select" ON storage.objects;

CREATE POLICY "redacted_service_role_insert"
    ON storage.objects FOR INSERT
    WITH CHECK (
        bucket_id = 'report-redacted'
        AND auth.role() = 'service_role'
    );

-- Service-role SELECT allows signed URL creation from the backend.
CREATE POLICY "redacted_service_role_select"
    ON storage.objects FOR SELECT
    USING (
        bucket_id = 'report-redacted'
        AND auth.role() = 'service_role'
    );
