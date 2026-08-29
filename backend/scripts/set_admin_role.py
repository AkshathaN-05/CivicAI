"""Helper script: set app_metadata.role = "admin" for an existing Supabase user.

Usage (from the backend/ directory with .venv active):
    python scripts/set_admin_role.py <email>

Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from backend/.env.
Requires the Supabase service-role key (not the anon key).

This script ONLY sets the admin role.  It does NOT change any password,
does NOT create new accounts, and does NOT delete any accounts.

After running this script, sign out and sign back in so the browser session
picks up the new app_metadata from a freshly issued JWT.
"""
from __future__ import annotations

import sys
import os

# Allow running from the backend/ directory without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/set_admin_role.py <email>")
        print("Example: python scripts/set_admin_role.py admin@example.com")
        sys.exit(1)

    target_email = sys.argv[1].strip()

    # Load credentials from .env
    from config import settings

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in backend/.env"
        )
        sys.exit(1)

    from supabase import create_client

    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    # List all users and find the one matching the given email.
    # The admin auth API is accessible via the service-role key.
    print(f"Looking up user with email: {target_email}")

    # Use the Admin API to list users and find by email.
    # supabase-py v2 exposes client.auth.admin.list_users()
    try:
        users_response = client.auth.admin.list_users()
    except Exception as exc:
        print(f"ERROR: Could not list users via Admin API: {exc}")
        print(
            "Make sure SUPABASE_SERVICE_KEY is the service-role key (not the anon key)."
        )
        sys.exit(1)

    # Find the user by email.
    target_user = None
    for user in users_response:
        if hasattr(user, "email") and user.email == target_email:
            target_user = user
            break

    if target_user is None:
        print(f"ERROR: No user found with email '{target_email}'")
        print("Check the email address and try again.")
        sys.exit(1)

    user_id = target_user.id
    current_meta = target_user.app_metadata or {}
    current_role = current_meta.get("role", "<not set>")
    print(f"Found user: id={user_id}, current app_metadata.role={current_role!r}")

    if current_role == "admin":
        print("User already has app_metadata.role = 'admin'. No change needed.")
        return

    # Update app_metadata.role = "admin" using the Admin API.
    try:
        client.auth.admin.update_user_by_id(
            user_id,
            {"app_metadata": {"role": "admin"}},
        )
    except Exception as exc:
        print(f"ERROR: Failed to update user metadata: {exc}")
        sys.exit(1)

    print(f"SUCCESS: app_metadata.role = 'admin' set for {target_email} (id={user_id})")
    print()
    print("IMPORTANT: The user must sign out and sign back in for the new role")
    print("to appear in their JWT.  Supabase JWTs are not updated retroactively.")
    print("Use the 'Sign out & Sign back in' button on the Admin Portal page.")


if __name__ == "__main__":
    main()
