-- =============================================================================
-- Migration 006 — Auth Trigger: Auto-create Profile on User Registration
-- Task: T1-8 (SQL portion only)
-- Canonical plan: Part A §19
-- Depends on: 002_tables.sql, 004_rls.sql
-- On auth.users INSERT → auto-INSERT into public.profiles with role='citizen'.
-- Demo user creation and admin role assignment remain manual dashboard steps.
-- PostgreSQL does not support CREATE TRIGGER IF NOT EXISTS.
-- Made idempotent via DROP TRIGGER IF EXISTS before CREATE TRIGGER.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Function: handle_new_user()
-- Fires after a new row is inserted into auth.users by Supabase Auth.
-- Inserts a corresponding profiles row with role='citizen'.
-- full_name is read from raw_user_meta_data if provided at signup.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, role, created_at)
    VALUES (
        NEW.id,
        NEW.raw_user_meta_data ->> 'full_name',
        'citizen',
        NOW()
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Trigger: auth.users INSERT → create profile
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_on_auth_user_created ON auth.users;
CREATE TRIGGER trg_on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();
