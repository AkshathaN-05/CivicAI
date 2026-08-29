"""pytest conftest.py — shared fixtures for the CivicAI backend test suite.

Provides:
  reset_rate_limiter (autouse) — clears the slowapi in-memory rate-limit storage
    before each test so individual tests don't interfere with each other's limits.
    Without this, the 10/minute AI rate limit is shared across all tests in the
    same pytest session and causes spurious 429 responses after the 10th test
    that hits POST /api/v1/reports/.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the slowapi in-memory rate-limit storage before every test.

    The application-level ``limiter`` is a module singleton.  Its default
    storage backend is ``limits.storage.MemoryStorage``.  Resetting it between
    tests prevents cross-test rate-limit interference.
    """
    from dependencies import limiter

    # Access the underlying limits FixedWindowRateLimiter and its MemoryStorage.
    try:
        inner = getattr(limiter, "_limiter", None)
        if inner is not None:
            storage = getattr(inner, "storage", None)
            if storage is not None and hasattr(storage, "reset"):
                storage.reset()
    except Exception:
        pass
    yield
