"""FastAPI shared dependencies — Part A §13, §19, T3-1.

Provides:
    get_current_user()  — verifies JWT, returns decoded user dict
    get_db()            — returns the Supabase service-role client (or None)
    get_limiter()       — returns the application-level slowapi Limiter
    limiter             — module-level Limiter instance for use in main.py

Rate limits (Part A §13):
    - Standard endpoints: 60 requests/minute
    - AI endpoints:       10 requests/minute

The ``limiter`` instance is also exported so ``main.py`` can attach it to the
app state and register the 429 exception handler exactly once.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi import Limiter
from slowapi.util import get_remote_address

# ---------------------------------------------------------------------------
# Rate limiter — module-level singleton (Part A §13)
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

# Rate limit strings for explicit per-route decoration.
RATE_LIMIT_STANDARD = "60/minute"
RATE_LIMIT_AI = "10/minute"

# ---------------------------------------------------------------------------
# HTTP Bearer extraction
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# get_current_user — verifies Supabase JWT RS256, returns claims dict
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Verify the Bearer JWT and return the decoded claims.

    The returned dict always contains:
        sub       — user UUID (Supabase auth.users.id)
        app_role  — resolved role string ('citizen' | 'admin' | 'authority_officer')
                    sourced from ``app_metadata.role`` in the JWT, defaulting to
                    'citizen' if absent (Part A §19).

    Raises:
        HTTPException 401: missing or invalid token.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from security.jwt_verify import verify_jwt

    payload = verify_jwt(credentials.credentials)

    # Resolve the user role from the JWT.
    # Supabase stores custom claims in ``app_metadata``; fall back to 'citizen'.
    app_metadata = payload.get("app_metadata") or {}
    app_role = app_metadata.get("role") or payload.get("role") or "citizen"

    payload["app_role"] = app_role
    return payload


# ---------------------------------------------------------------------------
# get_db — returns the Supabase service-role client (may be None)
# ---------------------------------------------------------------------------

def get_db():
    """Return the Supabase service-role client, or None if unconfigured.

    Routes that require DB access should declare this as a dependency and
    handle a None return gracefully (fall back to in-memory or raise 503).
    """
    from db.supabase_client import get_client

    return get_client()


# ---------------------------------------------------------------------------
# get_limiter — returns the module-level Limiter instance
# ---------------------------------------------------------------------------

def get_limiter() -> Limiter:
    """Return the application Limiter (used by routes that need explicit limits)."""
    return limiter
