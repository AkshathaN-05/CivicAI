"""pgvector cosine similarity search on rti_knowledge_base — T2-12.

Provides:

    class KnowledgeChunk(dataclass)
    def search(embedding, top_k=5) -> list[KnowledgeChunk]
    def keyword_search(query_text, top_k=5) -> list[KnowledgeChunk]

Vector search SQL (LOCKED — Part B §Vector Search):
    SELECT id, title, content,
           1 - (embedding <=> $1::vector) AS similarity
    FROM rti_knowledge_base
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> $1::vector
    LIMIT 5;

Keyword fallback SQL (LOCKED — Part B §Keyword Fallback):
    SELECT id, title, content
    FROM rti_knowledge_base
    WHERE content ILIKE '%' || $1 || '%'
       OR title ILIKE '%' || $1 || '%'
    LIMIT 5;

Design:
- Both functions return an empty list when Supabase is unavailable or the
  table is empty.  Callers must handle empty-list gracefully.
- ``search()`` requires a pre-computed embedding from :func:`~rag.embedder.embed`.
- ``keyword_search()`` is used when the embedding model is unavailable.
- No model loading in this module — purely a DB access layer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

TABLE = "rti_knowledge_base"
DEFAULT_TOP_K: int = 5


# ---------------------------------------------------------------------------
# KnowledgeChunk — the unit returned by both search paths
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeChunk:
    """One retrieved chunk from the RTI knowledge base.

    Attributes:
        id:         Row UUID from ``rti_knowledge_base``.
        title:      Document title.
        content:    Chunk text (max 512 tokens as per T2-13 chunking spec).
        similarity: Cosine similarity score in [0.0, 1.0].
                    Set to ``None`` for keyword-fallback results (no score available).
        source_url: Optional source URL for the document.
    """
    id: str
    title: str
    content: str
    similarity: Optional[float] = field(default=None)
    source_url: Optional[str] = field(default=None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search(
    embedding: list[float],
    top_k: int = DEFAULT_TOP_K,
) -> list[KnowledgeChunk]:
    """Run pgvector cosine similarity search against ``rti_knowledge_base``.

    Uses the architecture-locked SQL:
        SELECT id, title, content,
               1 - (embedding <=> $1::vector) AS similarity
        FROM rti_knowledge_base
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT :top_k;

    Args:
        embedding: A ``list[float]`` of length 1536 produced by
                   :func:`~rag.embedder.embed`.
        top_k:     Maximum number of chunks to return.  Defaults to 5.

    Returns:
        Up to *top_k* :class:`KnowledgeChunk` objects ordered by descending
        cosine similarity.  Empty list when Supabase is unavailable, the
        table has no rows with embeddings, or any error occurs.
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        logger.debug("vector_store.search: Supabase unavailable — returning [].")
        return []

    # Format embedding as a pgvector literal string: '[x1,x2,...,xN]'
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"

    try:
        # Use Supabase RPC (recommended for custom SQL with vector operators).
        # The function `match_rti_knowledge_base` must exist in Supabase as
        # a SQL function.  We fall back to a direct .rpc() call that sends
        # the raw pgvector query via the Supabase PostgREST rpc interface.
        #
        # Alternatively use the raw REST query.  Since postgrest does not
        # expose ORDER BY with custom operators directly, we call a stored
        # function that wraps the architecture-specified SQL.
        result = client.rpc(
            "match_rti_knowledge_base",
            {
                "query_embedding": vector_str,
                "match_count": top_k,
            },
        ).execute()

        rows = result.data or []
        chunks = []
        for row in rows:
            chunks.append(
                KnowledgeChunk(
                    id=str(row.get("id", "")),
                    title=str(row.get("title", "")),
                    content=str(row.get("content", "")),
                    similarity=float(row["similarity"]) if row.get("similarity") is not None else None,
                    source_url=row.get("source_url"),
                )
            )
        logger.debug("vector_store.search: returned %d chunks.", len(chunks))
        return chunks

    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_store.search: query failed: %s", exc)
        return []


def keyword_search(
    query_text: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[KnowledgeChunk]:
    """Run ILIKE keyword fallback search on ``rti_knowledge_base``.

    Uses the architecture-locked SQL:
        SELECT id, title, content
        FROM rti_knowledge_base
        WHERE content ILIKE '%' || $1 || '%'
           OR title ILIKE '%' || $1 || '%'
        LIMIT :top_k;

    Args:
        query_text: The raw query string to search for.
        top_k:      Maximum number of chunks to return.  Defaults to 5.

    Returns:
        Up to *top_k* :class:`KnowledgeChunk` objects.  ``similarity`` is
        ``None`` for keyword results (no score computed).  Empty list when
        Supabase is unavailable or no rows match.
    """
    from db.supabase_client import get_client

    client = get_client()
    if client is None:
        logger.debug("vector_store.keyword_search: Supabase unavailable — returning [].")
        return []

    # Sanitise: strip leading/trailing whitespace; no SQL injection possible
    # because Supabase client uses parameterised queries.
    safe_query = query_text.strip()
    if not safe_query:
        return []

    try:
        # PostgREST ilike filter on content OR title.
        # Supabase Python client supports .ilike() per column but not OR
        # across two columns directly via the query builder.  We use .or_()
        # which is the correct Supabase client idiom for OR conditions.
        result = (
            client.table(TABLE)
            .select("id, title, content, source_url")
            .or_(f"content.ilike.%{safe_query}%,title.ilike.%{safe_query}%")
            .limit(top_k)
            .execute()
        )

        rows = result.data or []
        chunks = [
            KnowledgeChunk(
                id=str(row.get("id", "")),
                title=str(row.get("title", "")),
                content=str(row.get("content", "")),
                similarity=None,  # no score for keyword results
                source_url=row.get("source_url"),
            )
            for row in rows
        ]
        logger.debug("vector_store.keyword_search: returned %d chunks.", len(chunks))
        return chunks

    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_store.keyword_search: query failed: %s", exc)
        return []
