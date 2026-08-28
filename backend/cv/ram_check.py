"""RAM availability check — T2-1.

Measures available system RAM at runtime and gates the BAAI embedding model
based on the Render free-tier 512 MB constraint (Part A §8, §29).

Usage:

    from cv.ram_check import available_ram_mb, is_embedding_enabled

    if is_embedding_enabled():
        # load BAAI/bge-large-en-v1.5
        ...

Expected memory footprint per model (Part A §8):
    YOLOv8n               ~30 MB  (lazy-loaded per inference)
    YuNet ONNX            ~5 MB   (lazy-loaded per inference)
    fast-alpr             ~80 MB  (lazy-loaded per inference)
    BAAI/bge-large-en-v1.5 ~440 MB (disabled if RAM < 512 MB)
    LLM (Groq API)         0 MB    (remote; no local footprint)

RAM gate: BAAI embeddings are disabled when available_ram_mb() < 512.
This matches the Render free-tier 512 MB constraint (Part A §29).
The gate can also be overridden by setting EMBEDDING_ENABLED=False in the
environment (useful for explicitly disabling on constrained deployments).
"""
from __future__ import annotations

import logging
import os

import psutil

logger = logging.getLogger(__name__)

# Threshold below which BAAI/bge-large-en-v1.5 is disabled (Part A §8, §29).
_RAM_GATE_MB = 512


def available_ram_mb() -> int:
    """Return available system RAM in megabytes (integer).

    Uses psutil.virtual_memory().available which reflects the current free
    memory including reclaimable caches — the same metric that constrains
    model loading on Render.

    Returns:
        int: Available RAM in MB.  Always a positive integer on supported
             platforms (Linux, macOS, Windows).
    """
    available_bytes: int = psutil.virtual_memory().available
    return available_bytes // (1024 * 1024)


def is_embedding_enabled() -> bool:
    """Return True when the BAAI embedding model should be loaded.

    False when:
      - available_ram_mb() < 512 (Part A §8 RAM gate), OR
      - the EMBEDDING_ENABLED environment variable is set to "false" or "0"
        (allows explicit opt-out on constrained deployments).

    This function is cheap — it reads RAM once at call time; callers should
    cache the result if called in a tight loop.
    """
    # Explicit opt-out via environment variable.
    env_flag = os.environ.get("EMBEDDING_ENABLED", "").lower()
    if env_flag in ("false", "0"):
        logger.debug("is_embedding_enabled: disabled via EMBEDDING_ENABLED env var.")
        return False

    ram = available_ram_mb()
    if ram < _RAM_GATE_MB:
        logger.info(
            "is_embedding_enabled: available RAM %d MB < %d MB threshold — "
            "BAAI embeddings disabled.",
            ram,
            _RAM_GATE_MB,
        )
        return False

    return True
