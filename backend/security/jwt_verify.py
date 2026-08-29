"""JWT verification — Part A §13, §19, T3-1.

Verifies Supabase Auth JWTs on every protected FastAPI request.
Supported signing algorithms: ES256 (ECC P-256, current Supabase default) and
RS256 (RSA, legacy/self-hosted).  The algorithm is read from the JWT header
``alg`` claim; no algorithm is hard-coded here.

Public keys are fetched from the Supabase JWKS endpoint and cached in memory
for the lifetime of the process (re-fetched only on key-id miss).

JWKS endpoint: ``/auth/v1/.well-known/jwks.json``
  — the public, unauthenticated JWKS URL (no API key required).
  — ``/auth/v1/jwks`` is the Kong-gateway-protected variant that requires an
    ``apikey`` header and MUST NOT be used here.

Raises:
    HTTPException 401 — missing, malformed, expired, or invalid-signature token
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwk, jwt

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Algorithms accepted from the JWT header ``alg`` claim.
# ES256 — ECC P-256 (current Supabase hosted/cloud default)
# RS256 — RSA 2048  (legacy self-hosted Supabase or older projects)
# ---------------------------------------------------------------------------
_ALLOWED_ALGORITHMS = {"ES256", "RS256"}

# ---------------------------------------------------------------------------
# JWKS cache  {kid: public_key_object}
# ---------------------------------------------------------------------------
_jwks_cache: dict[str, object] = {}


def _jwks_url() -> str:
    """Return the public, unauthenticated Supabase JWKS endpoint URL.

    Uses ``/auth/v1/.well-known/jwks.json`` which is publicly accessible
    (no API key required) and is the correct URL for JWT verification.

    ``/auth/v1/jwks`` is Kong-protected and requires an ``apikey`` header —
    it must NOT be used for verification.
    """
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _alg_for_key(key_data: dict) -> str:
    """Infer the JWK algorithm string from key metadata.

    If the JWK carries an explicit ``alg`` field, use it.
    Otherwise fall back to key-type inference:
      - EC  → ES256
      - RSA → RS256
    """
    if "alg" in key_data:
        return key_data["alg"]
    kty = key_data.get("kty", "")
    return "ES256" if kty == "EC" else "RS256"


def _fetch_jwks() -> dict[str, object]:
    """Fetch JWKS from Supabase and return a {kid: key} mapping.

    On success, logs the key IDs that were loaded.
    On failure, logs the full exception with URL and HTTP status so the cause
    is visible in production logs rather than hidden behind a generic 401.
    """
    url = _jwks_url()
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "JWKS fetch failed — HTTP %s from %s. "
            "Check SUPABASE_URL in .env and network egress from the backend host.",
            exc.response.status_code,
            url,
        )
        return {}
    except Exception as exc:
        logger.error(
            "JWKS fetch failed — could not reach %s: %s. "
            "Check SUPABASE_URL in .env and outbound HTTPS connectivity from the backend host.",
            url,
            exc,
        )
        return {}

    result: dict[str, object] = {}
    for key_data in data.get("keys", []):
        try:
            kid = key_data["kid"]
            alg = _alg_for_key(key_data)
            public_key = jwk.construct(key_data, algorithm=alg)
            result[kid] = public_key
        except Exception as exc:
            logger.warning("Skipping JWKS key entry (kid=%s): %s", key_data.get("kid"), exc)

    if result:
        logger.info("JWKS loaded successfully from %s — key IDs: %s", url, list(result.keys()))
    else:
        logger.error(
            "JWKS response from %s contained no usable keys. "
            "Verify the Supabase project URL and that the signing key is active.",
            url,
        )
    return result


def _get_public_key(kid: str) -> Optional[object]:
    """Return cached public key for *kid*, fetching JWKS if needed."""
    global _jwks_cache

    if kid in _jwks_cache:
        return _jwks_cache[kid]

    # Cache miss — re-fetch (handles key rotation)
    _jwks_cache = _fetch_jwks()
    return _jwks_cache.get(kid)


def verify_jwt(token: str) -> dict:
    """Verify a Supabase JWT (ES256 or RS256) and return its decoded claims.

    The algorithm is taken from the token's own header; the JWKS endpoint
    supplies the matching public key for whichever algorithm Supabase is using.

    Args:
        token: Raw JWT string (without "Bearer " prefix).

    Returns:
        Decoded payload dict containing at minimum ``sub`` (user UUID)
        and ``role`` (from app_metadata or profile).

    Raises:
        HTTPException 401: token missing, expired, or invalid signature.
    """
    # Peek at the header to get kid and alg without full verification yet.
    try:
        headers = jwt.get_unverified_header(token)
    except JWTError as exc:
        logger.debug("JWT header decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject tokens whose algorithm is not on the explicit allowlist.
    token_alg = headers.get("alg", "")
    if token_alg not in _ALLOWED_ALGORITHMS:
        logger.debug("JWT algorithm not allowed: %s", token_alg)
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
        logger.error(
            "JWT verification failed: kid '%s' not found in JWKS cache (keys: %s). "
            "The token may have been issued by a different Supabase project, "
            "or the JWKS endpoint is unreachable from this host. "
            "JWKS URL: %s",
            kid,
            list(_jwks_cache.keys()),
            _jwks_url(),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to verify token signature.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=list(_ALLOWED_ALGORITHMS),
            options={"verify_aud": False},  # Supabase JWTs carry "authenticated" audience
        )
    except JWTError as exc:
        logger.debug("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
