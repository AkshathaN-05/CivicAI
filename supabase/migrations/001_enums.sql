-- =============================================================================
-- Migration 001 — Enums
-- Task: T1-1 (Phase 1)
-- Canonical plan: Part A §7
-- Creates all four application enums. Safe to re-run (DO block guards).
-- =============================================================================

-- complaint_status: Part A §7, §24
DO $$ BEGIN
    CREATE TYPE complaint_status AS ENUM (
        'DRAFT',
        'SUBMITTED',
        'UNDER_REVIEW',
        'RESOLVED',
        'REJECTED',
        'ARCHIVED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- rti_status: Part A §7, §25
DO $$ BEGIN
    CREATE TYPE rti_status AS ENUM (
        'DRAFT',
        'SUBMITTED',
        'ACKNOWLEDGED',
        'RESPONDED',
        'ESCALATED',
        'CLOSED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- issue_category: Part A §7
DO $$ BEGIN
    CREATE TYPE issue_category AS ENUM (
        'pothole',
        'waterlogging',
        'broken_streetlight',
        'garbage_overflow',
        'open_drain',
        'illegal_construction',
        'water_supply',
        'sewage',
        'road_damage',
        'other'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- user_role: Part A §7, §19
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM (
        'citizen',
        'admin',
        'authority_officer'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
