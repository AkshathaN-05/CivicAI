-- =============================================================================
-- Migration 012 — PostGIS helper functions for evidence verification
-- Depends on: 010_evidence_fields.sql, 011_report_links.sql
-- Safe to re-run: CREATE OR REPLACE FUNCTION.
--
-- Creates two RPC-callable PostgreSQL functions used by the evidence
-- decision engine to run ST_DWithin geo-proximity queries:
--
--   nearby_active_reports(p_lat, p_lng, p_category, p_radius_m)
--     → active reports (SUBMITTED/UNDER_REVIEW) within p_radius_m metres,
--       ordered by created_at DESC.
--
--   nearby_resolved_reports(p_lat, p_lng, p_category, p_radius_m, p_window_days)
--     → RESOLVED reports within p_radius_m resolved in the last p_window_days,
--       ordered by resolved_at DESC.
--
-- These are called via supabase-py's .rpc() method from report_repo.py.
-- PostGIS must be enabled (the GiST index on reports.location already exists).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- nearby_active_reports
-- Returns reports that are active (SUBMITTED or UNDER_REVIEW) within radius.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.nearby_active_reports(
    p_lat      FLOAT,
    p_lng      FLOAT,
    p_category TEXT,
    p_radius_m INT DEFAULT 50
)
RETURNS TABLE (
    report_id        UUID,
    status           TEXT,
    ai_category      issue_category,
    created_at       TIMESTAMPTZ,
    distance_metres  FLOAT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT
        r.id                                                        AS report_id,
        r.status,
        r.ai_category,
        r.created_at,
        ST_Distance(
            r.location,
            ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::GEOGRAPHY
        )                                                           AS distance_metres
    FROM public.reports r
    WHERE
        r.location IS NOT NULL
        AND ST_DWithin(
            r.location,
            ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::GEOGRAPHY,
            p_radius_m
        )
        AND r.ai_category::TEXT = p_category
        AND r.status IN ('SUBMITTED', 'UNDER_REVIEW')
    ORDER BY r.created_at DESC;
$$;

-- ---------------------------------------------------------------------------
-- nearby_resolved_reports
-- Returns RESOLVED reports within radius resolved within the last window_days.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.nearby_resolved_reports(
    p_lat          FLOAT,
    p_lng          FLOAT,
    p_category     TEXT,
    p_radius_m     INT  DEFAULT 50,
    p_window_days  INT  DEFAULT 60
)
RETURNS TABLE (
    report_id        UUID,
    status           TEXT,
    ai_category      issue_category,
    resolved_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ,
    distance_metres  FLOAT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT
        r.id                                                        AS report_id,
        r.status,
        r.ai_category,
        r.resolved_at,
        r.created_at,
        ST_Distance(
            r.location,
            ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::GEOGRAPHY
        )                                                           AS distance_metres
    FROM public.reports r
    WHERE
        r.location IS NOT NULL
        AND ST_DWithin(
            r.location,
            ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::GEOGRAPHY,
            p_radius_m
        )
        AND r.ai_category::TEXT = p_category
        AND r.status = 'RESOLVED'
        AND r.resolved_at IS NOT NULL
        AND r.resolved_at > NOW() - (p_window_days || ' days')::INTERVAL
    ORDER BY r.resolved_at DESC;
$$;
