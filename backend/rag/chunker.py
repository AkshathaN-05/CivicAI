"""Document chunker for RTI knowledge base — T2-13.

Implements the chunking strategy specified in the architecture (Part B
§Chunking Strategy):

    def chunk_document(text: str, max_tokens: int = 512) -> list[str]

Algorithm (LOCKED — Part A §10, Part B §Chunking Strategy):
1. Split the input text on sentence boundaries.
2. Accumulate sentences into the current chunk, counting tokens with tiktoken.
3. When adding the next sentence would exceed ``max_tokens``:
   - Flush the current chunk to the output list.
   - Start a new chunk with the overflowing sentence.
4. After the loop, flush any remaining sentences.

Token counter: ``tiktoken`` with the ``cl100k_base`` encoding (GPT-4 /
text-embedding-ada-002 vocabulary — reasonable proxy for BAAI/bge tokens).

Sentence splitter: splits on ``. ``, ``! ``, ``? ``, ``\\n`` and ``\\r\\n``
boundaries.  This is a lightweight deterministic splitter; no NLTK dependency.

Public API:

    chunk_document(text: str, max_tokens: int = 512) -> list[str]
    split_sentences(text: str) -> list[str]
    count_tokens(text: str) -> int

Usage:
    from rag.chunker import chunk_document

    chunks = chunk_document(long_rti_act_text)
    # Each chunk is at most ~512 tokens
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Architecture-locked constants (Part B §Chunking Strategy)
DEFAULT_MAX_TOKENS: int = 512
TIKTOKEN_ENCODING: str = "cl100k_base"

# ---------------------------------------------------------------------------
# Lazy-loaded tiktoken encoder — not created at import time
# ---------------------------------------------------------------------------

_encoder = None


def _get_encoder():
    """Return the tiktoken encoder singleton, loading on first call."""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        import tiktoken

        _encoder = tiktoken.get_encoding(TIKTOKEN_ENCODING)
        logger.debug("chunker: tiktoken encoder '%s' loaded.", TIKTOKEN_ENCODING)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "chunker: tiktoken unavailable (%s) — falling back to word-count "
            "approximation (4 chars ≈ 1 token).",
            exc,
        )
        _encoder = None
    return _encoder


# ---------------------------------------------------------------------------
# Token counter
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Return the token count for *text*.

    Uses tiktoken ``cl100k_base`` when available; falls back to a
    character-based approximation (``ceil(len(text) / 4)``) when tiktoken
    is unavailable.  The approximation is conservative — it slightly
    over-counts, ensuring chunks stay within the 512-token budget.

    Args:
        text: Any string.

    Returns:
        Integer token count (>= 0).
    """
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:  # noqa: BLE001
            pass
    # Fallback: 4 chars ≈ 1 token (conservative over-count)
    import math

    return math.ceil(len(text) / 4)


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

# Sentence-ending patterns: period/exclamation/question followed by whitespace,
# or a newline (paragraph break treated as sentence boundary).
_SENTENCE_SPLIT_RE: re.Pattern[str] = re.compile(
    r"(?<=[.!?])\s+|[\r\n]+"
)


def split_sentences(text: str) -> list[str]:
    """Split *text* into sentences on ``. ``, ``! ``, ``? ``, and newline boundaries.

    Args:
        text: Input text.

    Returns:
        List of non-empty sentence strings.  Never returns empty strings.
    """
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in parts if s and s.strip()]


# ---------------------------------------------------------------------------
# Main chunker (architecture-locked algorithm)
# ---------------------------------------------------------------------------

def chunk_document(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[str]:
    """Chunk *text* into segments of at most *max_tokens* tokens.

    Algorithm (architecture Part B §Chunking Strategy — LOCKED):
        1. Split text on sentence boundaries.
        2. Accumulate sentences into the current chunk until adding the next
           sentence would exceed *max_tokens*.
        3. Flush current chunk; start new chunk with the overflow sentence.
        4. After the loop, flush remaining sentences.

    If a single sentence exceeds *max_tokens* on its own it is placed in a
    chunk by itself (to avoid data loss — no sentence is silently dropped).

    Args:
        text:       The document text to chunk.
        max_tokens: Maximum token count per chunk.  Defaults to 512.

    Returns:
        List of chunk strings.  Empty list when *text* is empty or
        contains only whitespace.  Trailing/leading whitespace is stripped
        from each chunk.
    """
    if not text or not text.strip():
        return []

    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens: int = 0

    for sentence in sentences:
        tokens = count_tokens(sentence)

        if current_tokens + tokens > max_tokens:
            # Flush current chunk (only if it contains sentences)
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            # Start a new chunk with this sentence (even if it exceeds
            # max_tokens alone — never silently drop data)
            current_chunk = [sentence]
            current_tokens = tokens
        else:
            current_chunk.append(sentence)
            current_tokens += tokens

    # Flush any remaining sentences
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return [c.strip() for c in chunks if c.strip()]


def reset_encoder_for_testing() -> None:
    """Reset the lazy-loaded tiktoken encoder singleton to None.

    Intended for use in tests only.
    """
    global _encoder
    _encoder = None
