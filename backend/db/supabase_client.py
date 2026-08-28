"""Supabase client — lazy singleton.

Returns None (instead of raising) when SUPABASE_URL or SUPABASE_SERVICE_KEY
are absent, so the application falls back to in-memory storage without
crashing.  Never initialised at import time.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level sentinel — None until first successful initialisation.
_client = None
_init_attempted = False


def get_client():
    """Return the Supabase service-role client, or None if unavailable.

    Lazily initialised on first call.  Subsequent calls return the cached
    client (or cached None if credentials were missing / init failed).
    """
    global _client, _init_attempted

    if _init_attempted:
        return _client

    _init_attempted = True

    # Import here — avoids any import-time side-effects when credentials
    # are absent (e.g. during pytest without a .env file).
    from config import settings  # local import to avoid circular deps

    url = settings.SUPABASE_URL
    key = settings.SUPABASE_SERVICE_KEY

    if not url or not key:
        logger.debug(
            "Supabase credentials not configured — using in-memory storage."
        )
        return None

    try:
        from supabase import create_client  # type: ignore[import]

        _client = create_client(url, key)
        logger.info("Supabase client initialised successfully.")
    except Exception:
        # Log without revealing credential values.
        logger.warning(
            "Supabase client initialisation failed — using in-memory storage.",
            exc_info=True,
        )
        _client = None

    return _client
