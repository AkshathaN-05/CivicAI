-- =============================================================================
-- Migration 008 — Enable Supabase Realtime for reports table
-- Depends on: 002_tables.sql, 004_rls.sql, 007_report_status.sql
-- Safe to re-run: ADD TABLE IF NOT EXISTS on a publication is idempotent
--   in PostgreSQL 15+; for older versions the DO block guards against
--   duplicate-member errors.
--
-- Purpose:
--   Enables postgres_changes events (INSERT, UPDATE, DELETE) on the
--   public.reports table via the built-in 'supabase_realtime' publication.
--
--   This is required for the frontend Supabase Realtime subscription
--   (postgres_changes, event: UPDATE, table: reports) to receive events
--   when an admin changes a report's status.
--
--   Without this migration, the publication exists but public.reports is
--   not a member, so no UPDATE events are delivered to subscribers.
--
-- NOTE:
--   Supabase Realtime postgres_changes also requires:
--     1. RLS enabled on the table (done in 004_rls.sql).
--     2. A SELECT policy for the subscribing user role (done in 004_rls.sql).
--   Both conditions are met by existing migrations.
-- =============================================================================

-- Add public.reports to the supabase_realtime publication.
-- The DO block is idempotent: if reports is already a member it skips the ADD.
DO $$ BEGIN
    -- Check if supabase_realtime publication exists
    IF EXISTS (
        SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime'
    ) THEN
        -- Check if reports is already in the publication
        IF NOT EXISTS (
            SELECT 1
            FROM pg_publication_tables
            WHERE pubname = 'supabase_realtime'
              AND schemaname = 'public'
              AND tablename = 'reports'
        ) THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE public.reports;
            RAISE NOTICE 'Added public.reports to supabase_realtime publication.';
        ELSE
            RAISE NOTICE 'public.reports already in supabase_realtime publication.';
        END IF;
    ELSE
        RAISE WARNING 'supabase_realtime publication not found — Realtime may not be enabled for this project.';
    END IF;
END $$;
