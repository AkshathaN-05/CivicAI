-- =============================================================================
-- Migration 005 — Audit Log Triggers
-- Task: T1-7 (Phase 1)
-- Canonical plan: Part A §13
-- Depends on: 002_tables.sql, 004_rls.sql
-- Fires on: complaints INSERT, complaints UPDATE (status), rti_requests UPDATE (status)
-- PostgreSQL does not support CREATE TRIGGER IF NOT EXISTS.
-- Triggers are made idempotent via DROP TRIGGER IF EXISTS before CREATE TRIGGER.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Trigger function: record_audit_event()
-- Inserts one row into audit_log for INSERT or UPDATE events on
-- complaints and rti_requests.
-- Part A §13: logs entity_type, entity_id, action, old_status, new_status,
--             user_id (auth.uid()), created_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.record_audit_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_old_status TEXT;
    v_new_status TEXT;
    v_entity_type TEXT;
BEGIN
    -- Determine entity type from table name
    v_entity_type := TG_TABLE_NAME;

    IF TG_OP = 'INSERT' THEN
        v_old_status := NULL;
        -- complaints has status; rti_requests has status
        IF TG_TABLE_NAME = 'complaints' THEN
            v_new_status := NEW.status::TEXT;
        ELSIF TG_TABLE_NAME = 'rti_requests' THEN
            v_new_status := NEW.status::TEXT;
        ELSE
            v_new_status := NULL;
        END IF;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Only log when the status column actually changes (Part A §13, T1-7)
        IF TG_TABLE_NAME = 'complaints' THEN
            IF OLD.status = NEW.status THEN
                RETURN NEW; -- status unchanged — skip
            END IF;
            v_old_status := OLD.status::TEXT;
            v_new_status := NEW.status::TEXT;
        ELSIF TG_TABLE_NAME = 'rti_requests' THEN
            IF OLD.status = NEW.status THEN
                RETURN NEW; -- status unchanged — skip
            END IF;
            v_old_status := OLD.status::TEXT;
            v_new_status := NEW.status::TEXT;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    INSERT INTO public.audit_log (
        user_id,
        action,
        entity_type,
        entity_id,
        metadata,
        created_at
    ) VALUES (
        auth.uid(),
        TG_OP,
        v_entity_type,
        NEW.id,
        jsonb_build_object(
            'old_status', v_old_status,
            'new_status', v_new_status
        ),
        NOW()
    );

    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Trigger: complaints INSERT → audit_log
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_audit_complaints_insert ON public.complaints;
CREATE TRIGGER trg_audit_complaints_insert
    AFTER INSERT ON public.complaints
    FOR EACH ROW
    EXECUTE FUNCTION public.record_audit_event();

-- ---------------------------------------------------------------------------
-- Trigger: complaints UPDATE (status) → audit_log
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_audit_complaints_update ON public.complaints;
CREATE TRIGGER trg_audit_complaints_update
    AFTER UPDATE ON public.complaints
    FOR EACH ROW
    EXECUTE FUNCTION public.record_audit_event();

-- ---------------------------------------------------------------------------
-- Trigger: rti_requests UPDATE (status) → audit_log
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_audit_rti_requests_update ON public.rti_requests;
CREATE TRIGGER trg_audit_rti_requests_update
    AFTER UPDATE ON public.rti_requests
    FOR EACH ROW
    EXECUTE FUNCTION public.record_audit_event();
