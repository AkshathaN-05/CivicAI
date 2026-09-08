"""pytest configuration for the backend test suite.

Fixtures defined here are available to all test modules automatically.

Provides:
  reset_rate_limiter (autouse) — clears the slowapi in-memory rate-limit storage
    before each test so individual tests don't interfere with each other's limits.
    Without this, the 10/minute AI rate limit is shared across all tests in the
    same pytest session and causes spurious 429 responses after the 10th test
    that hits POST /api/v1/reports/.

  reset_groq_client_singletons (autouse) — resets the Groq AsyncGroq client
    singletons before each test so tests that patch ``groq.AsyncGroq`` always
    receive a fresh mock instance.
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


@pytest.fixture(autouse=True)
def reset_groq_client_singletons():
    """Reset Groq client singletons before each test.

    Tests that patch ``llm.groq_provider.groq.AsyncGroq`` rely on the
    mock constructor being called to return a fresh mock instance.  The
    module-level client singletons introduced for production latency
    optimisation would otherwise cache the mock instance from a previous
    test, causing subsequent tests to use the wrong (stale) mock.

    This fixture ensures every test starts with a clean slate for the
    Groq client singletons.
    """
    try:
        from llm.groq_provider import reset_groq_clients_for_testing
        reset_groq_clients_for_testing()
    except ImportError:
        pass  # module not yet importable in some edge-case collection phases
    yield
    # Reset again after the test so the next test always starts clean
    try:
        from llm.groq_provider import reset_groq_clients_for_testing
        reset_groq_clients_for_testing()
    except ImportError:
        pass
