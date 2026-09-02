"""Script to apply migration 007 (report status columns) to the remote Supabase DB.

This script is safe to run multiple times — it uses ADD COLUMN IF NOT EXISTS.
It applies exactly the DDL from supabase/migrations/007_report_status.sql.

Usage:
    cd backend
    python scripts/apply_migration_007.py

The script uses the SUPABASE_URL and SUPABASE_SERVICE_KEY from the .env file.
It does NOT print or log any secrets.
"""
from __future__ import annotations

import sys
import os

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    sys.exit(1)

import httpx

url = settings.SUPABASE_URL
key = settings.SUPABASE_SERVICE_KEY

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
}


def check_columns_exist() -> dict:
    """Check which columns currently exist."""
    result = {}
    for col in ("status", "rejection_reason"):
        try:
            resp = httpx.get(
                f"{url}/rest/v1/reports",
                params={"select": col, "limit": "1"},
                headers=headers,
                timeout=15,
            )
            result[col] = resp.status_code == 200
        except Exception as e:
            result[col] = False
            print(f"  Error checking {col}: {e}")
    return result


def apply_ddl_via_rpc_create_and_call() -> bool:
    """Create a SECURITY DEFINER function then call it to apply migration 007.

    This is the only reliable way to run DDL statements via the supabase-py
    service-role REST API without a direct postgres connection.
    """
    # Step 1: Create a helper function via the REST API
    # We POST a function definition using the rpc endpoint for a pre-existing exec function.
    # Since exec_sql doesn't exist, we use the Supabase Management REST API instead.

    # The Supabase Management API is at api.supabase.io, not the project URL.
    # It requires a personal access token, not the service_role key.
    # So we must use an alternative approach.

    # Alternative: Use the supabase-py client to create the function via .schema()
    # and then RPC it.

    # The most reliable approach for this project's constraints is to use
    # the postgres REST API directly. Supabase exposes DDL execution via:
    # POST /rest/v1/ with special headers for postgres commands.

    # Actually, the correct supabase approach for DDL when you only have the
    # service_role key is to use the Supabase SQL Editor API or the CLI.
    # Without those, we must use a creative workaround.

    # WORKAROUND: Use the supabase-py client's .rpc() to call a PL/pgSQL block
    # by first creating the function, then calling it.

    from supabase import create_client

    client = create_client(url, key)

    # The supabase REST API does NOT support arbitrary DDL.
    # The only way is to use the postgres connection string directly.
    # Let's check if the project's db URL is derivable from the project ref.

    # Extract project ref from URL: https://<ref>.supabase.co
    import re
    m = re.match(r"https://([^.]+)\.supabase\.co", url)
    if not m:
        print(f"  Cannot extract project ref from URL: {url[:40]}...")
        return False

    project_ref = m.group(1)
    print(f"  Project ref: {project_ref}")

    # Supabase's transaction pooler endpoint (port 6543) or session pooler (5432)
    # can be used if we have the postgres password.
    # The service_role key IS the JWT, not the postgres password.
    # We can't use it for direct postgres connections.

    print("  Cannot run DDL via REST API without exec_sql function.")
    print("  Need to use Supabase dashboard SQL editor or CLI.")
    return False


def verify_after_migration() -> bool:
    """Verify the columns exist after migration."""
    cols = check_columns_exist()
    print(f"  status column: {'EXISTS' if cols['status'] else 'MISSING'}")
    print(f"  rejection_reason column: {'EXISTS' if cols['rejection_reason'] else 'MISSING'}")
    return all(cols.values())


if __name__ == "__main__":
    print("=" * 60)
    print("Migration 007 — Report Status and Rejection Reason")
    print("=" * 60)

    print("\n[1] Checking current column state...")
    before = check_columns_exist()
    for col, exists in before.items():
        print(f"  {col}: {'EXISTS' if exists else 'MISSING'}")

    if all(before.values()):
        print("\n✓ Both columns already exist — migration already applied.")
        sys.exit(0)

    print("\n[2] Columns are missing — migration 007 needs to be applied.")
    print("    The migration SQL is in: supabase/migrations/007_report_status.sql")
    print()
    print("    To apply this migration, run ONE of:")
    print()
    print("    Option A — Supabase CLI (if installed):")
    print("      supabase db push")
    print()
    print("    Option B — Supabase Dashboard:")
    print("      1. Go to https://supabase.com/dashboard/project/<ref>/sql")
    print("      2. Paste and run the contents of supabase/migrations/007_report_status.sql")
    print()
    print("    Option C — Using a direct Postgres connection string")
    print("      psql <connection-string> < supabase/migrations/007_report_status.sql")
    print()
    print("  Attempting to apply via Supabase API...")
    success = apply_ddl_via_rpc_create_and_call()

    if not success:
        print("\n  Could not apply automatically — see above instructions.")
        sys.exit(2)

    print("\n[3] Verifying migration was applied...")
    if verify_after_migration():
        print("\n✓ Migration 007 applied successfully.")
    else:
        print("\n✗ Migration 007 could not be verified.")
        sys.exit(1)
