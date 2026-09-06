-- =============================================================================
-- Migration 010 — Evidence Verification Fields on reports
-- Depends on: 007_report_status.sql
-- Safe to re-run: ADD COLUMN IF NOT EXISTS; DROP INDEX IF EXISTS.
--
-- Adds columns required by the CivicAI evidence-verification architecture:
--   decision_state      — canonical DecisionState enum value (TEXT)
--   evidence_score      — weighted multi-signal evidence score [0.0, 1.0]
--   admin_priority      — deterministic triage label for admin dashboard
--   visual_confidence   — image-only AI confidence [0.0, 1.0]
--   category_confidence — model certainty about the category [0.0, 1.0]
--   location_confidence — GPS quality + plausibility [0.0, 1.0]
--   freshness_confidence— temporal recency signal [0.0, 1.0]
--   is_reopened         — TRUE when decision_state = possible_reopened_issue
--   gps_accuracy_metres — GPS accuracy radius from browser geolocation (nullable)
--   severity            — civic impact severity: 'low'/'medium'/'high'/null
--   linked_report_id    — shortcut FK to the related active/resolved report
--   image_reuse_flag    — TRUE when same hash found in a non-active report
--
-- NOTE: ai_raw_response JSONB (already present) continues to store the full
--       evidence_breakdown dict for admin explainability.
-- =============================================================================

-- decision_state: string value of DecisionState enum
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS decision_state TEXT
    CHECK (decision_state IN (
        'invalid_image',
        'insufficient_evidence',
        'duplicate_active_report',
        'possible_reopened_issue',
        'valid_civic_report',
        'needs_admin_review'
    ));

-- evidence_score: overall weighted evidence strength [0.0, 1.0]
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS evidence_score REAL;

-- admin_priority: deterministic triage enum for admin dashboard
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS admin_priority TEXT DEFAULT 'INSUFFICIENT'
    CHECK (admin_priority IN (
        'CRITICAL', 'HIGH', 'MEDIUM', 'LOW',
        'REOPEN_REVIEW', 'DUPLICATE', 'INSUFFICIENT'
    ));

-- Individual confidence components (admin explainability)
ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS visual_confidence    REAL;
ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS category_confidence  REAL;
ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS location_confidence  REAL;
ALTER TABLE public.reports ADD COLUMN IF NOT EXISTS freshness_confidence REAL;

-- Reopen flag
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS is_reopened BOOLEAN DEFAULT FALSE;

-- GPS accuracy from browser geolocation API (nullable — not always provided)
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS gps_accuracy_metres REAL;

-- Civic impact severity
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS severity TEXT
    CHECK (severity IN ('low', 'medium', 'high'));

-- Shortcut FK to the linked active or resolved report
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS linked_report_id UUID REFERENCES public.reports(id);

-- Image reuse risk signal (non-blocking admin signal)
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS image_reuse_flag BOOLEAN DEFAULT FALSE;

-- ---------------------------------------------------------------------------
-- Indexes for admin dashboard filtering and scoring queries
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_reports_decision_state  ON public.reports (decision_state);
CREATE INDEX IF NOT EXISTS idx_reports_admin_priority  ON public.reports (admin_priority);
CREATE INDEX IF NOT EXISTS idx_reports_image_hash      ON public.reports (image_hash);
CREATE INDEX IF NOT EXISTS idx_reports_status          ON public.reports (status);
CREATE INDEX IF NOT EXISTS idx_reports_ai_category     ON public.reports (ai_category);
-- resolved_at is needed for the reopen window query; derive from ai_raw_response is impractical,
-- so we add a dedicated column here for the resolved timestamp.
ALTER TABLE public.reports
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_reports_resolved_at     ON public.reports (resolved_at);
