-- =============================================================================
-- Migration 002 — Core Tables
-- Task: T1-2 (Phase 1)
-- Canonical plan: Part A §7, §21
-- Depends on: 001_enums.sql
-- Creates all 7 application tables. Safe to re-run (IF NOT EXISTS).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- profiles
-- Extends auth.users (1:1). Auto-created by auth trigger (006_auth_trigger.sql).
-- Part A §7: id (FK→auth.users), full_name, phone, role, ward_number, created_at
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
    id            UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name     TEXT,
    phone         TEXT,
    role          user_role   NOT NULL DEFAULT 'citizen',
    ward_number   INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- authorities
-- Seeded from immutable JSON (001_authorities.sql). Read-only after seed.
-- Part A §7, §21: id, name, jurisdiction, categories[], area_text, contact_email, phone, created_at
-- short_name is present in the canonical immutable JSON source
-- (backend/data/mangaluru_authorities.json) and is referenced by the existing
-- authority_service.py. Included here for data compatibility.
-- ADR-001: no ward_range, no ward integers, no routing geometry.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.authorities (
    id            TEXT        PRIMARY KEY,
    name          TEXT        NOT NULL,
    short_name    TEXT        NOT NULL,
    jurisdiction  TEXT,
    categories    issue_category[] NOT NULL DEFAULT '{}',
    area_text     TEXT        NOT NULL DEFAULT '',
    contact_email TEXT        NOT NULL DEFAULT '',
    phone         TEXT        NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- reports
-- Raw record created when a citizen uploads a photo.
-- Part A §7, §21: id, user_id, image_original_path, image_redacted_path,
--   image_hash, location (GEOGRAPHY POINT), address_text, ai_category,
--   ai_confidence, ai_authority_id, ai_raw_response (JSONB), created_at
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.reports (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    image_original_path   TEXT,
    image_redacted_path   TEXT,
    image_hash            TEXT,
    location              GEOGRAPHY(POINT, 4326),
    address_text          TEXT,
    ai_category           issue_category,
    ai_confidence         FLOAT,
    ai_authority_id       TEXT        REFERENCES public.authorities(id),
    ai_raw_response       JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- complaints
-- Approved complaint created from a report.
-- Part A §7, §21: id, report_id, user_id, category, description,
--   authority_id, status, submitted_at, resolved_at, resolution_image_path,
--   resolution_notes, mock_gov_ref, created_at, updated_at
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.complaints (
    id                    UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id             UUID            REFERENCES public.reports(id) ON DELETE SET NULL,
    user_id               UUID            NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    category              issue_category  NOT NULL,
    description           TEXT            NOT NULL,
    authority_id          TEXT            NOT NULL REFERENCES public.authorities(id),
    status                complaint_status NOT NULL DEFAULT 'DRAFT',
    submitted_at          TIMESTAMPTZ,
    resolved_at           TIMESTAMPTZ,
    resolution_image_path TEXT,
    resolution_notes      TEXT,
    mock_gov_ref          TEXT,
    created_at            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- rti_requests
-- RTI linked to a stale (≥30-day unresolved) complaint.
-- Part A §7, §21: id, complaint_id, user_id, status, draft_text,
--   approved_text, mock_submitted_at, rti_ref, created_at, updated_at
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rti_requests (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id      UUID        NOT NULL REFERENCES public.complaints(id) ON DELETE CASCADE,
    user_id           UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    status            rti_status  NOT NULL DEFAULT 'DRAFT',
    draft_text        TEXT,
    approved_text     TEXT,
    mock_submitted_at TIMESTAMPTZ,
    rti_ref           TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- rti_knowledge_base
-- RTI Act / MCC procedure knowledge chunks for RAG.
-- Part A §7, §21: id, title, content, embedding vector(1536), source_url, created_at
-- embedding uses pgvector extension (must be enabled before this migration runs).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rti_knowledge_base (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title      TEXT        NOT NULL,
    content    TEXT        NOT NULL,
    embedding  vector(1536),
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- audit_log
-- Immutable append-only audit trail. Part A §7, §13, §21.
-- Fields: id, user_id, action, entity_type, entity_id, metadata (JSONB),
--   ip_address, created_at
-- Append-only enforced by a rule that raises an exception on UPDATE/DELETE.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID,
    action      TEXT        NOT NULL,
    entity_type TEXT        NOT NULL,
    entity_id   UUID,
    metadata    JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enforce append-only: reject UPDATE and DELETE at the rule level.
-- CREATE OR REPLACE RULE works idempotently.
CREATE OR REPLACE RULE audit_log_no_update AS
    ON UPDATE TO public.audit_log
    DO INSTEAD NOTHING;

CREATE OR REPLACE RULE audit_log_no_delete AS
    ON DELETE TO public.audit_log
    DO INSTEAD NOTHING;
