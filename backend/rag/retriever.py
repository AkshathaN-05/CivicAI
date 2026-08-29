"""RAG context retriever — T2-12.

Provides the public entry point for the RAG pipeline:

    retrieve_context(query_text: str, top_k: int = 5) -> list[KnowledgeChunk]

Behaviour (LOCKED — Part A §10, Part B §Embedding-Unavailable Fallback):
1. Call :func:`~rag.embedder.embed` on *query_text*.
2. If embedding is available (non-None):
       → call :func:`~rag.vector_store.search` (pgvector cosine similarity).
3. If embedding is None (RAM gate active or model unavailable):
       → call :func:`~rag.vector_store.keyword_search` (ILIKE fallback).
4. Return up to *top_k* :class:`~rag.vector_store.KnowledgeChunk` objects.

The caller (T3-5 RTI service) uses the returned chunks as ``rag_context``
injected into :func:`~services.llm_service.generate_rti_draft`.

This module owns no state, no models, no DB connections — it is purely an
orchestration layer that delegates to embedder and vector_store.

Usage:
    from rag.retriever import retrieve_context

    chunks = retrieve_context("complaint about pothole no response 30 days")
    rag_context = "\\n\\n".join(c.content for c in chunks)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag.vector_store import KnowledgeChunk

logger = logging.getLogger(__name__)


def retrieve_context(
    query_text: str,
    top_k: int = 5,
) -> list["KnowledgeChunk"]:
    """Retrieve the most relevant RTI knowledge chunks for *query_text*.

    Tries vector search first; falls back to keyword search when the BAAI
    embedding model is unavailable (RAM gate or load failure).

    Args:
        query_text: The query string — typically the complaint description or
                    an RTI-context query.  Should already be sanitised by the
                    caller (no prompt injection risk here, but safe_query text
                    is only used for DB search, not injected into LLM prompts).
        top_k:      Maximum number of chunks to retrieve.  Defaults to 5.

    Returns:
        A list of up to *top_k* :class:`~rag.vector_store.KnowledgeChunk`
        objects.  Empty list when the knowledge base is empty, Supabase is
        unavailable, or both search paths fail.

    Notes:
        - Both search paths can return fewer than *top_k* results if the
          knowledge base has fewer matching rows.
        - An empty list is a valid (non-error) response; callers should
          handle it by passing an empty ``rag_context`` string to the LLM,
          which the deterministic fallback handles gracefully.
    """
    if not query_text or not query_text.strip():
        logger.debug("retrieve_context: empty query — returning [].")
        return []

    from rag.embedder import embed
    from rag.vector_store import keyword_search, search

    # Step 1: attempt embedding.
    embedding = embed(query_text.strip())

    if embedding is not None:
        # Step 2a: vector search (embedding available).
        logger.debug("retrieve_context: using vector search (embedding available).")
        chunks = search(embedding, top_k=top_k)
        if chunks:
            logger.debug(
                "retrieve_context: vector search returned %d chunks.", len(chunks)
            )
            return chunks
        # Vector search returned 0 results (empty knowledge base or error).
        # Fall through to keyword search as a last resort.
        logger.debug(
            "retrieve_context: vector search returned 0 results — "
            "falling back to keyword search."
        )

    # Step 2b: keyword fallback (embedding unavailable or vector returned nothing).
    logger.debug("retrieve_context: using keyword fallback.")
    chunks = keyword_search(query_text.strip(), top_k=top_k)
    logger.debug("retrieve_context: keyword search returned %d chunks.", len(chunks))
    return chunks


def chunks_to_context_string(chunks: list["KnowledgeChunk"]) -> str:
    """Concatenate retrieved chunks into a single context string for LLM injection.

    Each chunk is prefixed with its title so the LLM can reference the source.
    Returns an empty string when *chunks* is empty.

    Args:
        chunks: List of :class:`~rag.vector_store.KnowledgeChunk` objects.

    Returns:
        Multi-paragraph context string suitable for the ``{rag_context}``
        placeholder in :data:`~llm.prompts.RTI_DRAFT_PROMPT`.
    """
    if not chunks:
        return ""
    parts = []
    for chunk in chunks:
        header = f"[{chunk.title}]" if chunk.title else "[RTI Context]"
        parts.append(f"{header}\n{chunk.content}")
    return "\n\n".join(parts)
