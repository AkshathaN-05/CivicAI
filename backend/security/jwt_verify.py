"""JWT verification — Part A §13, §19, T3-1.

Verifies Supabase Auth JWTs (RS256) on every protected FastAPI request.
Public keys are fetched from the Supabase JWKS endpoint and cached in memory
for the lifetime of the process (re-fetched only on key-id miss).

Raises:
    HTTPException 401 — missing, malformed, expired, or invalid-signature token
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWKS cache  {kid: public_key_object}
# ---------------------------------------------------------------------------
_jwks_cache: dict[str, object] = {}


def _jwks_url() -> str:
    """Return the Supabase JWKS endpoint URL."""
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/auth/v1/jwks"


def _fetch_jwks() -> dict[str, object]:
    """Fetch JWKS from Supabase and return a {kid: key} mapping."""
    url = _jwks_url()
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch JWKS from %s: %s", url, exc)
        return {}

    result: dict[str, object] = {}
    for key_data in data.get("keys", []):
        try:
            kid = key_data["kid"]
            public_key = jwk.construct(key_data)
            result[kid] = public_key
        except Exception as exc:
            logger.warning("Skipping JWKS key entry: %s", exc)
    return result


def _get_public_key(kid: str) -> Optional[object]:
    """Return cached public key for *kid*, fetching JWKS if needed."""
    global _jwks_cache

    if kid in _jwks_cache:
        return _jwks_cache[kid]

    # Cache miss — re-fetch
    _jwks_cache = _fetch_jwks()
    return _jwks_cache.get(kid)


def verify_jwt(token: str) -> dict:
    """Verify a Supabase RS256 JWT and return its decoded claims.

    Args:
        token: Raw JWT string (without "Bearer " prefix).

    Returns:
        Decoded payload dict containing at minimum ``sub`` (user UUID)
        and ``role`` (from app_metadata or profile).

    Raises:
        HTTPException 401: token missing, expired, or invalid signature.
    """
    # Peek at the header to get the kid without full verification yet.
    try:
        headers = jwt.get_unverified_header(token)
    except JWTError as exc:
        logger.debug("JWT header decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    kid = headers.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing key identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    public_key = _get_public_key(kid)
    if public_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to verify token signature.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Supabase JWTs have "authenticated" audience
        )
    except JWTError as exc:
        logger.debug("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
