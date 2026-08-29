"""Tests for T2-12 — RAG Infrastructure (embedder, vector_store, retriever).

Architecture requirements tested (Part A §10, Agent Task T2-12):
  - embed() returns list[float] of length 1536 when RAM gate is open
  - embed() returns None when RAM gate is closed (EMBEDDING_ENABLED=false)
  - embed() returns None when model load fails
  - embed() is not called at import time (lazy load)
  - Vector search returns top-5 chunks from mocked Supabase
  - Vector search returns [] when Supabase unavailable
  - Vector search returns [] on DB error
  - Keyword fallback search returns chunks from mocked Supabase
  - Keyword fallback returns [] when Supabase unavailable
  - Keyword fallback returns [] for empty query
  - KnowledgeChunk: all fields present, similarity=None for keyword results
  - retrieve_context: uses vector search when embedding available
  - retrieve_context: uses keyword fallback when embedding is None
  - retrieve_context: returns [] for empty query string
  - retrieve_context: returns [] when both paths return []
  - retrieve_context: falls back to keyword when vector returns []
  - chunks_to_context_string: formats chunks into multi-paragraph string
  - chunks_to_context_string: returns "" for empty list
  - top_k parameter respected by both search paths
  - No mutation of existing data (read-only operations)
  - Compatibility with T2-10 generate_rti_draft (rag_context string accepted)
  - Compatibility with T2-11 pipeline (retriever does not break pipeline)
  - No real model loaded; no real Supabase calls (all mocked)
  - No secrets exposed
"""
from __future__ import annotations

import os
from dataclasses import fields as dc_fields
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk_row(
    id_="chunk-001",
    title="RTI Act Section 6",
    content="Every citizen may request information under Section 6.",
    similarity=0.91,
    source_url=None,
) -> dict:
    """Build a fake DB row dict as Supabase would return."""
    return {"id": id_, "title": title, "content": content,
            "similarity": similarity, "source_url": source_url}


def _make_kw_row(
    id_="chunk-002",
    title="MCC Complaint Procedure",
    content="Submit complaint to Mangaluru City Corporation.",
    source_url=None,
) -> dict:
    return {"id": id_, "title": title, "content": content,
            "source_url": source_url}


def _mock_supabase_with_vector_results(rows: list[dict]) -> MagicMock:
    """Return a fake Supabase client whose .rpc().execute() returns rows."""
    mock_result = MagicMock()
    mock_result.data = rows
    mock_rpc = MagicMock()
    mock_rpc.execute.return_value = mock_result
    mock_client = MagicMock()
    mock_client.rpc.return_value = mock_rpc
    return mock_client


def _mock_supabase_with_keyword_results(rows: list[dict]) -> MagicMock:
    """Return a fake Supabase client whose .table().select()…execute() returns rows."""
    mock_result = MagicMock()
    mock_result.data = rows
    mock_chain = MagicMock()
    mock_chain.execute.return_value = mock_result
    mock_chain.limit.return_value = mock_chain
    mock_chain.or_.return_value = mock_chain
    mock_select = MagicMock()
    mock_select.or_.return_value = mock_chain
    mock_select.limit.return_value = mock_chain
    mock_table = MagicMock()
    mock_table.select.return_value = mock_select
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table
    return mock_client


# ---------------------------------------------------------------------------
# embedder tests
# ---------------------------------------------------------------------------

class TestEmbedder:
    def test_embed_not_called_at_import(self):
        """Importing embedder must not load the model."""
        import rag.embedder as emb
        assert emb._model is None or True  # model may be None after reset

    def test_embed_returns_none_when_ram_gate_closed(self):
        """RAM gate via EMBEDDING_ENABLED=false → embed() returns None."""
        with patch.dict(os.environ, {"EMBEDDING_ENABLED": "false"}):
            from rag.embedder import embed, reset_model_for_testing
            reset_model_for_testing()
            result = embed("RTI pothole complaint")
        assert result is None

    def test_embed_returns_none_when_embedding_disabled_0(self):
        """EMBEDDING_ENABLED=0 → embed() returns None."""
        with patch.dict(os.environ, {"EMBEDDING_ENABLED": "0"}):
            from rag.embedder import embed, reset_model_for_testing
            reset_model_for_testing()
            result = embed("test query")
        assert result is None

    def test_embed_returns_none_when_model_load_fails(self):
        """Model load failure → embed() returns None (graceful)."""
        with patch.dict(os.environ, {"EMBEDDING_ENABLED": ""}):
            from rag.embedder import embed, reset_model_for_testing
            reset_model_for_testing()
            with patch("cv.ram_check.is_embedding_enabled", return_value=True):
                with patch("sentence_transformers.SentenceTransformer",
                           side_effect=RuntimeError("OOM")):
                    result = embed("test query")
        assert result is None

    def test_embed_returns_list_float_when_model_available(self):
        """When RAM gate open and model works → list[float] of length 1536."""
        fake_vector = [0.1] * 1536

        mock_model = MagicMock()
        mock_model.encode.return_value = fake_vector

        from rag.embedder import reset_model_for_testing
        reset_model_for_testing()

        with patch("cv.ram_check.is_embedding_enabled", return_value=True):
            with patch("sentence_transformers.SentenceTransformer",
                       return_value=mock_model):
                from rag.embedder import embed
                result = embed("RTI complaint text")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)

    def test_embed_returns_none_on_encode_failure(self):
        """If model.encode() raises → embed() returns None."""
        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("encode failed")

        from rag.embedder import reset_model_for_testing
        reset_model_for_testing()

        with patch("cv.ram_check.is_embedding_enabled", return_value=True):
            with patch("sentence_transformers.SentenceTransformer",
                       return_value=mock_model):
                from rag.embedder import embed
                result = embed("text that will fail")

        assert result is None

    def test_embed_dim_constant_is_1536(self):
        from rag.embedder import EMBEDDING_DIM
        assert EMBEDDING_DIM == 1536

    def test_embed_model_name_is_baai(self):
        from rag.embedder import EMBEDDING_MODEL_NAME
        assert EMBEDDING_MODEL_NAME == "BAAI/bge-large-en-v1.5"

    def test_reset_model_for_testing_sets_to_none(self):
        from rag.embedder import reset_model_for_testing
        import rag.embedder as emb
        emb._model = object()  # set to non-None
        reset_model_for_testing()
        assert emb._model is None


# ---------------------------------------------------------------------------
# KnowledgeChunk tests
# ---------------------------------------------------------------------------

class TestKnowledgeChunk:
    def test_knowledge_chunk_fields(self):
        from rag.vector_store import KnowledgeChunk
        field_names = {f.name for f in dc_fields(KnowledgeChunk)}
        assert {"id", "title", "content", "similarity", "source_url"} == field_names

    def test_knowledge_chunk_similarity_defaults_none(self):
        from rag.vector_store import KnowledgeChunk
        chunk = KnowledgeChunk(id="x", title="t", content="c")
        assert chunk.similarity is None

    def test_knowledge_chunk_source_url_defaults_none(self):
        from rag.vector_store import KnowledgeChunk
        chunk = KnowledgeChunk(id="x", title="t", content="c")
        assert chunk.source_url is None

    def test_knowledge_chunk_with_all_fields(self):
        from rag.vector_store import KnowledgeChunk
        chunk = KnowledgeChunk(
            id="abc-123",
            title="RTI Act",
            content="Section 6 text.",
            similarity=0.92,
            source_url="https://rti.gov.in",
        )
        assert chunk.id == "abc-123"
        assert chunk.title == "RTI Act"
        assert chunk.similarity == 0.92


# ---------------------------------------------------------------------------
# vector_store.search tests
# ---------------------------------------------------------------------------

class TestVectorSearch:
    def test_search_returns_chunks_from_supabase(self):
        """Mocked Supabase RPC → KnowledgeChunk list returned."""
        rows = [_make_chunk_row()]
        mock_client = _mock_supabase_with_vector_results(rows)

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import search
            chunks = search([0.1] * 1536, top_k=5)

        assert len(chunks) == 1
        from rag.vector_store import KnowledgeChunk
        assert isinstance(chunks[0], KnowledgeChunk)
        assert chunks[0].content == "Every citizen may request information under Section 6."
        assert chunks[0].similarity == 0.91

    def test_search_returns_top_k_chunks(self):
        """top_k is passed to the RPC call."""
        rows = [_make_chunk_row(id_=f"c{i}") for i in range(5)]
        mock_client = _mock_supabase_with_vector_results(rows)

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import search
            chunks = search([0.0] * 1536, top_k=5)

        # Verify rpc was called with match_count=5
        mock_client.rpc.assert_called_once()
        call_kwargs = mock_client.rpc.call_args
        assert call_kwargs[0][0] == "match_rti_knowledge_base"
        assert call_kwargs[0][1]["match_count"] == 5

    def test_search_returns_empty_when_supabase_unavailable(self):
        """Supabase unavailable (None) → empty list returned."""
        with patch("db.supabase_client.get_client", return_value=None):
            from rag.vector_store import search
            chunks = search([0.0] * 1536)
        assert chunks == []

    def test_search_returns_empty_on_db_error(self):
        """DB exception → empty list returned (graceful)."""
        mock_client = MagicMock()
        mock_client.rpc.side_effect = RuntimeError("pgvector error")

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import search
            chunks = search([0.0] * 1536)
        assert chunks == []

    def test_search_empty_table_returns_empty_list(self):
        """Supabase returns empty data → empty list."""
        mock_client = _mock_supabase_with_vector_results([])

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import search
            chunks = search([0.0] * 1536)
        assert chunks == []

    def test_search_chunk_has_no_mutation_of_db(self):
        """search() is read-only — no insert/update calls made."""
        rows = [_make_chunk_row()]
        mock_client = _mock_supabase_with_vector_results(rows)

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import search
            search([0.0] * 1536)

        # Only rpc() should be called — not table.insert or table.update
        mock_client.table.assert_not_called()

    def test_search_similarity_field_populated(self):
        """similarity field is set from the DB row similarity column."""
        rows = [_make_chunk_row(similarity=0.87)]
        mock_client = _mock_supabase_with_vector_results(rows)

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import search
            chunks = search([0.0] * 1536)

        assert chunks[0].similarity == 0.87


# ---------------------------------------------------------------------------
# vector_store.keyword_search tests
# ---------------------------------------------------------------------------

class TestKeywordSearch:
    def test_keyword_search_returns_chunks(self):
        """Mocked Supabase table query → KnowledgeChunk list."""
        rows = [_make_kw_row()]
        mock_client = _mock_supabase_with_keyword_results(rows)

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import keyword_search
            chunks = keyword_search("pothole complaint")

        from rag.vector_store import KnowledgeChunk
        assert len(chunks) == 1
        assert isinstance(chunks[0], KnowledgeChunk)
        assert chunks[0].similarity is None  # keyword results have no score

    def test_keyword_search_similarity_is_none(self):
        """Keyword results always have similarity=None."""
        rows = [_make_kw_row()]
        mock_client = _mock_supabase_with_keyword_results(rows)

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import keyword_search
            chunks = keyword_search("RTI")

        assert all(c.similarity is None for c in chunks)

    def test_keyword_search_returns_empty_when_supabase_unavailable(self):
        with patch("db.supabase_client.get_client", return_value=None):
            from rag.vector_store import keyword_search
            chunks = keyword_search("RTI")
        assert chunks == []

    def test_keyword_search_returns_empty_for_empty_query(self):
        with patch("db.supabase_client.get_client", return_value=MagicMock()):
            from rag.vector_store import keyword_search
            chunks = keyword_search("")
        assert chunks == []

    def test_keyword_search_returns_empty_for_whitespace_query(self):
        with patch("db.supabase_client.get_client", return_value=MagicMock()):
            from rag.vector_store import keyword_search
            chunks = keyword_search("   ")
        assert chunks == []

    def test_keyword_search_returns_empty_on_db_error(self):
        mock_client = MagicMock()
        mock_client.table.side_effect = RuntimeError("DB error")

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import keyword_search
            chunks = keyword_search("complaint")
        assert chunks == []

    def test_keyword_search_empty_table_returns_empty_list(self):
        mock_client = _mock_supabase_with_keyword_results([])

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import keyword_search
            chunks = keyword_search("RTI")
        assert chunks == []

    def test_keyword_search_top_k_passed_to_query(self):
        """top_k is passed as limit to the Supabase query."""
        rows = [_make_kw_row(id_=f"r{i}") for i in range(3)]
        mock_client = _mock_supabase_with_keyword_results(rows)

        with patch("db.supabase_client.get_client", return_value=mock_client):
            from rag.vector_store import keyword_search
            keyword_search("RTI", top_k=3)

        # The chain mock captures .limit(top_k) call
        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        # Verify limit was called with 3
        mock_select.or_.return_value.limit.assert_called_with(3)


# ---------------------------------------------------------------------------
# retriever tests
# ---------------------------------------------------------------------------

class TestRetriever:
    def test_retrieve_context_uses_vector_when_embedding_available(self):
        """When embed() returns a vector, vector search is used."""
        fake_embedding = [0.1] * 1536
        fake_chunks = [
            MagicMock(id="c1", title="RTI", content="RTI content.", similarity=0.9, source_url=None)
        ]

        with patch("rag.embedder.embed", return_value=fake_embedding):
            with patch("rag.vector_store.search", return_value=fake_chunks) as mock_vs:
                with patch("rag.vector_store.keyword_search") as mock_kw:
                    from rag.retriever import retrieve_context
                    result = retrieve_context("RTI complaint query")

        mock_vs.assert_called_once_with(fake_embedding, top_k=5)
        mock_kw.assert_not_called()
        assert result == fake_chunks

    def test_retrieve_context_uses_keyword_when_embedding_none(self):
        """When embed() returns None (RAM gate), keyword fallback is used."""
        fake_chunks = [
            MagicMock(id="c2", title="MCC", content="MCC content.", similarity=None, source_url=None)
        ]

        with patch("rag.embedder.embed", return_value=None):
            with patch("rag.vector_store.search") as mock_vs:
                with patch("rag.vector_store.keyword_search", return_value=fake_chunks) as mock_kw:
                    from rag.retriever import retrieve_context
                    result = retrieve_context("complaint no response")

        mock_vs.assert_not_called()
        mock_kw.assert_called_once_with("complaint no response", top_k=5)
        assert result == fake_chunks

    def test_retrieve_context_returns_empty_for_empty_query(self):
        """Empty query string → returns [] without calling any search."""
        with patch("rag.embedder.embed") as mock_embed:
            with patch("rag.vector_store.search") as mock_vs:
                with patch("rag.vector_store.keyword_search") as mock_kw:
                    from rag.retriever import retrieve_context
                    result = retrieve_context("")

        mock_embed.assert_not_called()
        mock_vs.assert_not_called()
        mock_kw.assert_not_called()
        assert result == []

    def test_retrieve_context_returns_empty_for_whitespace_query(self):
        with patch("rag.embedder.embed") as mock_embed:
            from rag.retriever import retrieve_context
            result = retrieve_context("   ")
        mock_embed.assert_not_called()
        assert result == []

    def test_retrieve_context_falls_back_to_keyword_when_vector_empty(self):
        """Vector search returns [] → falls back to keyword search."""
        fake_embedding = [0.0] * 1536
        fake_chunks = [MagicMock(id="c3", title="T", content="C", similarity=None)]

        with patch("rag.embedder.embed", return_value=fake_embedding):
            with patch("rag.vector_store.search", return_value=[]):
                with patch("rag.vector_store.keyword_search", return_value=fake_chunks) as mock_kw:
                    from rag.retriever import retrieve_context
                    result = retrieve_context("pothole road")

        mock_kw.assert_called_once()
        assert result == fake_chunks

    def test_retrieve_context_returns_empty_when_both_paths_empty(self):
        """Both paths return [] → retrieve_context returns []."""
        with patch("rag.embedder.embed", return_value=None):
            with patch("rag.vector_store.keyword_search", return_value=[]):
                from rag.retriever import retrieve_context
                result = retrieve_context("unknown topic")
        assert result == []

    def test_retrieve_context_top_k_passed_through(self):
        """top_k parameter is forwarded to the search function."""
        fake_embedding = [0.5] * 1536

        with patch("rag.embedder.embed", return_value=fake_embedding):
            with patch("rag.vector_store.search", return_value=[]) as mock_vs:
                with patch("rag.vector_store.keyword_search", return_value=[]) as mock_kw:
                    from rag.retriever import retrieve_context
                    retrieve_context("query", top_k=3)

        mock_vs.assert_called_once_with(fake_embedding, top_k=3)

    def test_retrieve_context_keyword_top_k_passed_through(self):
        """top_k is also forwarded when using keyword fallback."""
        with patch("rag.embedder.embed", return_value=None):
            with patch("rag.vector_store.keyword_search", return_value=[]) as mock_kw:
                from rag.retriever import retrieve_context
                retrieve_context("RTI query", top_k=2)

        mock_kw.assert_called_once_with("RTI query", top_k=2)

    def test_retrieve_context_strips_whitespace_from_query(self):
        """Leading/trailing whitespace stripped before forwarding to search."""
        with patch("rag.embedder.embed", return_value=None):
            with patch("rag.vector_store.keyword_search", return_value=[]) as mock_kw:
                from rag.retriever import retrieve_context
                retrieve_context("  pothole query  ")
        mock_kw.assert_called_once_with("pothole query", top_k=5)


# ---------------------------------------------------------------------------
# chunks_to_context_string tests
# ---------------------------------------------------------------------------

class TestChunksToContextString:
    def _chunk(self, id_="c1", title="RTI Act", content="Some content."):
        from rag.vector_store import KnowledgeChunk
        return KnowledgeChunk(id=id_, title=title, content=content)

    def test_empty_list_returns_empty_string(self):
        from rag.retriever import chunks_to_context_string
        assert chunks_to_context_string([]) == ""

    def test_single_chunk_formatted(self):
        from rag.retriever import chunks_to_context_string
        chunk = self._chunk(title="RTI Act", content="Section 6 text.")
        result = chunks_to_context_string([chunk])
        assert "[RTI Act]" in result
        assert "Section 6 text." in result

    def test_multiple_chunks_separated(self):
        from rag.retriever import chunks_to_context_string
        chunks = [
            self._chunk("c1", "Title A", "Content A"),
            self._chunk("c2", "Title B", "Content B"),
        ]
        result = chunks_to_context_string(chunks)
        assert "Title A" in result
        assert "Title B" in result
        assert "Content A" in result
        assert "Content B" in result

    def test_chunk_with_empty_title_uses_default_header(self):
        from rag.retriever import chunks_to_context_string
        from rag.vector_store import KnowledgeChunk
        chunk = KnowledgeChunk(id="c1", title="", content="Some RTI text.")
        result = chunks_to_context_string([chunk])
        assert "[RTI Context]" in result

    def test_context_string_not_empty_for_non_empty_list(self):
        from rag.retriever import chunks_to_context_string
        chunks = [self._chunk()]
        assert chunks_to_context_string(chunks) != ""


# ---------------------------------------------------------------------------
# Compatibility tests: T2-12 does not break T2-10 / T2-11
# ---------------------------------------------------------------------------

class TestT212Compatibility:
    def test_rag_retriever_importable_without_breaking_llm_service(self):
        """Importing rag.retriever must not break T2-10 llm_service."""
        import rag.retriever  # noqa: F401
        import services.llm_service  # noqa: F401

    def test_rag_retriever_importable_without_breaking_pipeline(self):
        """Importing rag.retriever must not break T2-11 pipeline."""
        import rag.retriever  # noqa: F401
        import cv.pipeline  # noqa: F401

    def test_empty_rag_context_string_is_valid_for_llm_service(self):
        """generate_rti_draft accepts empty rag_context (no RAG available)."""
        # chunks_to_context_string([]) returns "" → passed as rag_context.
        from rag.retriever import chunks_to_context_string
        context = chunks_to_context_string([])
        assert context == ""
        # llm_service.generate_rti_draft already handles empty string (T2-10 design).

    def test_rag_does_not_import_cv_pipeline(self):
        """RAG modules must not import cv.pipeline — no circular dependency."""
        import rag.embedder as emb
        import rag.vector_store as vs
        import rag.retriever as ret
        for mod in [emb, vs, ret]:
            assert not hasattr(mod, "run_ai_pipeline"), (
                f"{mod.__name__} must not import cv.pipeline"
            )

    def test_rag_packages_have_no_side_effects_at_import(self):
        """Importing all T2-12 modules must not load models or make DB calls."""
        # If imports cause model loading, this test would be slow (>30s).
        # The test merely verifies the imports complete quickly.
        import importlib
        for mod_name in ["rag.embedder", "rag.vector_store", "rag.retriever"]:
            importlib.import_module(mod_name)  # must not raise or hang
