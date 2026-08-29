"""BAAI/bge-large-en-v1.5 embedding with RAM gate — T2-12.

Provides a single public function:

    embed(text: str) -> list[float] | None

Behaviour (LOCKED — Part A §8, §10):
- Model: ``BAAI/bge-large-en-v1.5``
- Vector dimension: 1536
- Loaded lazily on first call (not at import time).
- RAM gate via :func:`~cv.ram_check.is_embedding_enabled`:
    - If RAM < 512 MB OR ``EMBEDDING_ENABLED=false`` → return None.
    - Callers receiving None must activate keyword-fallback search.
- Returns a Python ``list[float]`` of length 1536.
- Returns ``None`` on any failure (model load error, encoding error, RAM gate).
- No external API call — model runs locally on CPU.

Usage:
    from rag.embedder import embed

    vec = embed("RTI application for pothole complaint")
    if vec is None:
        # RAM gate active — use keyword search instead
        ...
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Architecture-locked constants (Part A §10)
EMBEDDING_MODEL_NAME: str = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIM: int = 1536

# ---------------------------------------------------------------------------
# Lazy-loaded singleton — NOT created at import time (Part A §8)
# ---------------------------------------------------------------------------
_model = None  # sentence_transformers.SentenceTransformer instance


def _get_model():
    """Return the BAAI embedding model singleton, loading on first call.

    Returns None if loading fails (e.g. first-call OOM, missing model files).
    """
    global _model
    if _model is not None:
        return _model

    try:
        from sentence_transformers import SentenceTransformer  # deferred import

        logger.info("Loading BAAI/bge-large-en-v1.5 embedding model …")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("BAAI embedding model loaded (dim=%d).", EMBEDDING_DIM)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load BAAI embedding model: %s", exc)
        _model = None

    return _model


def embed(text: str) -> Optional[list[float]]:
    """Embed *text* using BAAI/bge-large-en-v1.5.

    Returns a ``list[float]`` of length :data:`EMBEDDING_DIM` (1536), or
    ``None`` when the RAM gate is active or the model is unavailable.

    Callers receiving ``None`` must fall back to keyword-based retrieval.

    Args:
        text: Input text to embed.  Sanitised before this call by the caller.

    Returns:
        ``list[float]`` of length 1536, or ``None``.
    """
    # RAM gate — check before attempting model load (Part A §8).
    from cv.ram_check import is_embedding_enabled

    if not is_embedding_enabled():
        logger.debug("embed: RAM gate active — returning None.")
        return None

    model = _get_model()
    if model is None:
        logger.debug("embed: model unavailable — returning None.")
        return None

    try:
        # encode() returns a numpy array; convert to plain Python list[float].
        vector = model.encode(text, normalize_embeddings=True)
        return list(float(x) for x in vector)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed: encoding failed: %s", exc)
        return None


def reset_model_for_testing() -> None:
    """Reset the lazy-loaded model singleton to None.

    Intended for use in tests only.
    """
    global _model
    _model = None
