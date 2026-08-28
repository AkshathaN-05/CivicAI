-- =============================================================================
-- Migration 003 — Indexes
-- Task: T1-3 (Phase 1)
-- Canonical plan: Part A §7, §29
-- Depends on: 002_tables.sql
-- Creates all performance indexes. Safe to re-run (IF NOT EXISTS).
-- =============================================================================

-- reports.location — GiST spatial index for PostGIS ST_DWithin duplicate detection
-- Part A §7, §11: duplicate detection only (not routing — ADR-001)
CREATE INDEX IF NOT EXISTS idx_reports_location
    ON public.reports USING GIST (location);

-- rti_knowledge_base.embedding — IVFFlat index for pgvector cosine similarity search
-- Part A §7, §10: RAG semantic search
-- lists=100 per T1-3 specification
CREATE INDEX IF NOT EXISTS idx_rti_knowledge_base_embedding
    ON public.rti_knowledge_base USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- complaints(user_id, status) — composite index for citizen dashboard queries
-- Part A §7, §29
CREATE INDEX IF NOT EXISTS idx_complaints_user_status
    ON public.complaints (user_id, status);

-- complaints.authority_id — for admin/officer complaint filtering
-- Part A §7
CREATE INDEX IF NOT EXISTS idx_complaints_authority_id
    ON public.complaints (authority_id);

-- audit_log.user_id — for per-user audit queries
-- Part A §7
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id
    ON public.audit_log (user_id);

-- audit_log.entity_id — for per-entity audit queries
-- Part A §7
CREATE INDEX IF NOT EXISTS idx_audit_log_entity_id
    ON public.audit_log (entity_id);
