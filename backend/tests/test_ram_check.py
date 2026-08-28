"""T2-1 tests — RAM check utility.

Acceptance criterion (T2-1 canonical plan):
  - ram_check.py returns a positive integer for available RAM
  - is_embedding_enabled() returns a bool
  - EMBEDDING_ENABLED=false env var disables embeddings regardless of RAM
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def test_available_ram_mb_returns_positive_integer():
    """available_ram_mb() must return a positive integer (T2-1 acceptance criterion)."""
    from cv.ram_check import available_ram_mb

    result = available_ram_mb()
    assert isinstance(result, int), f"Expected int, got {type(result)}"
    assert result > 0, f"Expected positive RAM MB, got {result}"


def test_is_embedding_enabled_returns_bool():
    """is_embedding_enabled() must return a bool."""
    from cv.ram_check import is_embedding_enabled

    result = is_embedding_enabled()
    assert isinstance(result, bool)


def test_is_embedding_enabled_env_override_disables():
    """EMBEDDING_ENABLED=false must return False regardless of available RAM."""
    from cv.ram_check import is_embedding_enabled

    original = os.environ.get("EMBEDDING_ENABLED")
    try:
        os.environ["EMBEDDING_ENABLED"] = "false"
        assert is_embedding_enabled() is False

        os.environ["EMBEDDING_ENABLED"] = "0"
        assert is_embedding_enabled() is False
    finally:
        if original is None:
            os.environ.pop("EMBEDDING_ENABLED", None)
        else:
            os.environ["EMBEDDING_ENABLED"] = original


def test_is_embedding_disabled_below_512mb(monkeypatch):
    """When available RAM < 512 MB the gate returns False."""
    import psutil

    # Patch psutil to report 256 MB available.
    class _FakeVMem:
        available = 256 * 1024 * 1024

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _FakeVMem())

    # Clear the env override so only the RAM gate decides.
    monkeypatch.delenv("EMBEDDING_ENABLED", raising=False)

    from cv import ram_check
    # Reload to pick up monkeypatched psutil.
    import importlib
    importlib.reload(ram_check)
    assert ram_check.is_embedding_enabled() is False


def test_is_embedding_enabled_above_512mb(monkeypatch):
    """When available RAM >= 512 MB and no env override the gate returns True."""
    import psutil

    class _FakeVMem:
        available = 1024 * 1024 * 1024  # 1 GB

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _FakeVMem())
    monkeypatch.delenv("EMBEDDING_ENABLED", raising=False)

    from cv import ram_check
    import importlib
    importlib.reload(ram_check)
    assert ram_check.is_embedding_enabled() is True
