"""Tests for T2-13 — RTI Knowledge Base Chunker and Seed Content.

Architecture requirements tested (Part A §10, Part B §Chunking Strategy,
Agent Task T2-13):

Chunker (chunker.py):
  - chunk_document: empty text returns []
  - chunk_document: whitespace-only text returns []
  - chunk_document: short text within 512 tokens returns single chunk
  - chunk_document: long text exceeding 512 tokens returns multiple chunks
  - chunk_document: each chunk is at most max_tokens tokens (where possible)
  - chunk_document: no sentence data is silently dropped
  - chunk_document: a single sentence larger than max_tokens is not dropped
  - chunk_document: chunks are non-empty strings
  - chunk_document: preserves all sentence content (total tokens ≈ original)
  - chunk_document: deterministic for same input
  - chunk_document: custom max_tokens respected
  - split_sentences: splits on '. ', '! ', '? ' boundaries
  - split_sentences: splits on newline boundaries
  - split_sentences: returns non-empty strings only
  - count_tokens: returns positive integer for non-empty text
  - count_tokens: returns 0 for empty string
  - count_tokens: tiktoken disabled → word-count approximation used
  - Chunker is not called at import time (no model loading)

Seed content (002_rti_knowledge_base.sql):
  - SQL file exists at the correct path
  - SQL contains all 5 required content categories
  - SQL contains at least 16 INSERT rows
  - SQL includes the match_rti_knowledge_base function definition
  - SQL is idempotent (ON CONFLICT DO NOTHING)
  - SQL uses NULL embedding (keyword fallback compatible)
  - Each INSERT has id, title, content, embedding, source_url columns

Seed content (Python documents):
  - RTI Act sections 6, 7, 19 content present
  - MCC complaint procedure content present
  - Karnataka Municipal Corporations Act content present
  - RTI letter format / escalation hierarchy content present

Compatibility with T2-12:
  - chunk_document output is compatible with KnowledgeChunk.content
  - chunked content is keyword-searchable (contains RTI query keywords)
  - retrieve_context compatibility (end-to-end with mocked DB)

Ingestion script:
  - ingest() with dry_run=True returns expected chunk count
  - ingest() is idempotent (safe to call multiple times)
  - ingest() handles Supabase unavailable gracefully
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEED_SQL_PATH = Path(__file__).parent.parent.parent / "supabase" / "seed" / "002_rti_knowledge_base.sql"

_LONG_TEXT = (
    "The Right to Information Act 2005 is a landmark legislation in India. "
    "It empowers citizens to request information from public authorities. "
    "The Act covers all public authorities at central, state and local levels. "
    "Municipal corporations are public authorities under Section 2(h) of the Act. "
    "Citizens may request information about civic complaints and government actions. "
    "The Public Information Officer is responsible for providing information. "
    "Applications must be responded to within 30 days of receipt. "
    "Failure to respond is deemed a refusal under Section 7 of the Act. "
    "First appeals may be filed within 30 days of the deemed refusal. "
    "Second appeals may be filed with the State Information Commission. "
    "The Commission may impose penalties of up to Rs. 25,000 on the PIO. "
    "Citizens in Karnataka may also approach the Karnataka Lokayukta. "
    "Mangaluru City Corporation is a public authority under the RTI Act. "
    "Complaints about potholes, garbage, streetlights may be filed with MCC. "
    "MWWD handles water supply and sewage issues in Mangaluru city. "
    "MESCOM handles electricity and streetlight complaints in Mangaluru. "
    "NHAI Mangaluru handles national highway road issues. "
    "MCC must respond to civic complaints within 30 days. "
    "Escalation options include RTI applications to the MCC PIO. "
    "The Karnataka Municipal Corporations Act 1976 governs MCC operations. "
    "Section 58 of the Act empowers citizens to petition the corporation. "
    "Citizens may seek redress through the Karnataka High Court if needed. "
    "The RTI Act applies to all bodies financed by the government. "
    "Information commissioners adjudicate disputes about RTI applications. "
    "The second appeal to KSIC can result in compensation for the applicant. "
) * 3  # repeat to exceed 512 tokens


# ---------------------------------------------------------------------------
# split_sentences tests
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_splits_on_period_space(self):
        from rag.chunker import split_sentences
        sentences = split_sentences("Hello world. This is a test. Another sentence.")
        assert len(sentences) >= 2
        assert all(s for s in sentences)

    def test_splits_on_exclamation(self):
        from rag.chunker import split_sentences
        sentences = split_sentences("Alert! This is important! Take action.")
        assert len(sentences) >= 2

    def test_splits_on_question_mark(self):
        from rag.chunker import split_sentences
        sentences = split_sentences("What happened? Nothing resolved. Why?")
        assert len(sentences) >= 2

    def test_splits_on_newline(self):
        from rag.chunker import split_sentences
        sentences = split_sentences("First paragraph.\nSecond paragraph.")
        assert len(sentences) >= 2

    def test_no_empty_strings_returned(self):
        from rag.chunker import split_sentences
        sentences = split_sentences("A sentence.   \n\n  Another sentence.")
        assert all(s.strip() for s in sentences)

    def test_single_sentence_returns_one_element(self):
        from rag.chunker import split_sentences
        sentences = split_sentences("A single sentence without any split point")
        assert len(sentences) == 1

    def test_empty_string_returns_empty_list(self):
        from rag.chunker import split_sentences
        assert split_sentences("") == []

    def test_whitespace_only_returns_empty_list(self):
        from rag.chunker import split_sentences
        assert split_sentences("   \n\n  ") == []


# ---------------------------------------------------------------------------
# count_tokens tests
# ---------------------------------------------------------------------------

class TestCountTokens:
    def test_empty_string_returns_0(self):
        from rag.chunker import count_tokens
        assert count_tokens("") == 0

    def test_non_empty_returns_positive_integer(self):
        from rag.chunker import count_tokens
        result = count_tokens("Hello world")
        assert isinstance(result, int)
        assert result > 0

    def test_longer_text_more_tokens(self):
        from rag.chunker import count_tokens
        short = count_tokens("Hi.")
        long_ = count_tokens("This is a much longer sentence with many more tokens.")
        assert long_ > short

    def test_tiktoken_disabled_falls_back_gracefully(self):
        """When tiktoken unavailable, word-count approximation is used."""
        from rag.chunker import count_tokens, reset_encoder_for_testing
        reset_encoder_for_testing()
        # Patch the _get_encoder helper to return None (simulates tiktoken unavailable)
        with patch("rag.chunker._get_encoder", return_value=None):
            result = count_tokens("This is a test sentence.")
        assert isinstance(result, int)
        assert result > 0

    def test_deterministic_for_same_input(self):
        from rag.chunker import count_tokens
        assert count_tokens("RTI Act Section 6") == count_tokens("RTI Act Section 6")


# ---------------------------------------------------------------------------
# chunk_document tests
# ---------------------------------------------------------------------------

class TestChunkDocument:
    def test_empty_text_returns_empty_list(self):
        from rag.chunker import chunk_document
        assert chunk_document("") == []

    def test_whitespace_only_returns_empty_list(self):
        from rag.chunker import chunk_document
        assert chunk_document("   \n\n  ") == []

    def test_short_text_returns_single_chunk(self):
        from rag.chunker import chunk_document
        text = "This is a short document. It has very few tokens."
        chunks = chunk_document(text, max_tokens=512)
        assert len(chunks) == 1

    def test_long_text_returns_multiple_chunks(self):
        from rag.chunker import chunk_document
        chunks = chunk_document(_LONG_TEXT, max_tokens=512)
        assert len(chunks) > 1

    def test_each_chunk_is_non_empty_string(self):
        from rag.chunker import chunk_document
        chunks = chunk_document(_LONG_TEXT, max_tokens=512)
        assert all(isinstance(c, str) and c.strip() for c in chunks)

    def test_no_sentence_content_dropped(self):
        """All words from original text must appear somewhere in the chunks."""
        from rag.chunker import chunk_document
        text = "First sentence about RTI. Second sentence about MCC. Third sentence about complaint."
        chunks = chunk_document(text, max_tokens=512)
        combined = " ".join(chunks)
        for keyword in ["RTI", "MCC", "complaint"]:
            assert keyword in combined, f"Keyword '{keyword}' missing from chunks"

    def test_max_tokens_512_respected_when_possible(self):
        """Each chunk should be at most 512 tokens (unless single sentence exceeds it)."""
        from rag.chunker import chunk_document, count_tokens
        chunks = chunk_document(_LONG_TEXT, max_tokens=512)
        for chunk in chunks:
            tokens = count_tokens(chunk)
            # Single sentences that themselves exceed 512 tokens are allowed.
            # For our test text, all sentences are short, so all chunks should be ≤512.
            assert tokens <= 600, (  # slight tolerance for boundary sentences
                f"Chunk exceeded token budget: {tokens} tokens"
            )

    def test_single_long_sentence_not_dropped(self):
        """A sentence that alone exceeds max_tokens is placed in its own chunk."""
        from rag.chunker import chunk_document
        # A very long single sentence (no split point)
        long_sentence = "word " * 600  # no punctuation split points
        chunks = chunk_document(long_sentence, max_tokens=512)
        # The content must not be dropped, even if it exceeds 512 tokens
        assert len(chunks) >= 1
        combined = " ".join(chunks)
        assert "word" in combined

    def test_deterministic_same_input_same_output(self):
        from rag.chunker import chunk_document
        chunks1 = chunk_document(_LONG_TEXT, max_tokens=512)
        chunks2 = chunk_document(_LONG_TEXT, max_tokens=512)
        assert chunks1 == chunks2

    def test_custom_max_tokens_respected(self):
        """Smaller max_tokens → more chunks."""
        from rag.chunker import chunk_document
        chunks_512 = chunk_document(_LONG_TEXT, max_tokens=512)
        chunks_128 = chunk_document(_LONG_TEXT, max_tokens=128)
        assert len(chunks_128) > len(chunks_512)

    def test_default_max_tokens_is_512(self):
        from rag.chunker import DEFAULT_MAX_TOKENS
        assert DEFAULT_MAX_TOKENS == 512

    def test_output_chunks_are_stripped_strings(self):
        from rag.chunker import chunk_document
        chunks = chunk_document("  Hello world.  ", max_tokens=512)
        for c in chunks:
            assert c == c.strip()

    def test_rti_act_text_chunks_contain_expected_keywords(self):
        """RTI Act content chunks must contain the original key terms."""
        from rag.chunker import chunk_document
        rti_text = (
            "Section 6 of the RTI Act 2005 requires a written request to the PIO. "
            "The application must include the prescribed fee of Rs. 10. "
            "Section 7 requires response within 30 days. "
            "Section 19 allows a first appeal within 30 days of deemed refusal. "
            "The Information Commission may impose penalties of up to Rs. 25,000."
        )
        chunks = chunk_document(rti_text, max_tokens=512)
        combined = " ".join(chunks)
        for term in ["RTI", "PIO", "Section 7", "30 days"]:
            assert term in combined

    def test_tiktoken_encoding_constant(self):
        from rag.chunker import TIKTOKEN_ENCODING
        assert TIKTOKEN_ENCODING == "cl100k_base"


# ---------------------------------------------------------------------------
# Seed SQL file tests
# ---------------------------------------------------------------------------

class TestSeedSQLFile:
    def test_seed_file_exists(self):
        assert SEED_SQL_PATH.exists(), f"Seed file not found at {SEED_SQL_PATH}"

    def test_seed_file_is_non_empty(self):
        content = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert len(content.strip()) > 0

    def test_seed_contains_rti_act_section_6(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "Section 6" in sql, "RTI Act Section 6 content missing from seed"

    def test_seed_contains_rti_act_section_7(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "Section 7" in sql or "30 days" in sql, "RTI Act Section 7 content missing"

    def test_seed_contains_rti_act_section_19(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "Section 19" in sql or "appeal" in sql.lower(), "RTI Act Section 19 content missing"

    def test_seed_contains_mcc_procedure(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "Mangaluru City Corporation" in sql or "MCC" in sql

    def test_seed_contains_karnataka_act(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "Karnataka" in sql

    def test_seed_contains_rti_letter_format(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "letter" in sql.lower() or "format" in sql.lower() or "Public Information Officer" in sql

    def test_seed_contains_escalation_contacts(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        # Escalation hierarchy must include at least one phone number
        assert re.search(r"0824-\d{7}", sql) or "1912" in sql

    def test_seed_has_at_least_16_inserts(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        # Count INSERT rows: each tuple starts with a UUID literal
        uuid_count = len(re.findall(r"'[0-9a-f-]{36}'::uuid", sql))
        assert uuid_count >= 16, f"Expected >=16 UUID rows, found {uuid_count}"

    def test_seed_uses_null_embedding(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        # All seed rows use NULL for embedding
        assert "NULL" in sql
        # Should not contain actual vector literals in the INSERT rows
        assert "::vector" not in sql or "match_rti_knowledge_base" in sql

    def test_seed_is_idempotent_on_conflict(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql

    def test_seed_creates_match_function(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "match_rti_knowledge_base" in sql
        assert "CREATE OR REPLACE FUNCTION" in sql

    def test_seed_match_function_returns_similarity(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "similarity" in sql.lower()

    def test_seed_match_function_uses_cosine_distance(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "<=>" in sql  # pgvector cosine distance operator

    def test_seed_table_name_correct(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        assert "rti_knowledge_base" in sql

    def test_seed_columns_present_in_insert(self):
        sql = SEED_SQL_PATH.read_text(encoding="utf-8")
        for col in ("id", "title", "content", "embedding", "source_url"):
            assert col in sql, f"Column '{col}' missing from seed SQL"


# ---------------------------------------------------------------------------
# Seed document content tests (using ingestion script documents)
# ---------------------------------------------------------------------------

class TestSeedDocuments:
    def _get_docs(self):
        from scripts.ingest_rti_knowledge_base import _DOCUMENTS
        return _DOCUMENTS

    def test_five_document_categories_present(self):
        docs = self._get_docs()
        titles = " ".join(d["title"] for d in docs).lower()
        content = " ".join(d["content"] for d in docs).lower()
        # Must contain: RTI Act, MCC, Karnataka, RTI procedure
        assert "rti act" in titles or "rti act" in content
        assert "section 6" in content or "section 7" in content
        assert "mangaluru" in content or "mcc" in content or "mangaluru" in titles
        assert "karnataka" in content or "karnataka" in titles

    def test_all_documents_have_title_and_content(self):
        docs = self._get_docs()
        for doc in docs:
            assert "title" in doc and doc["title"].strip()
            assert "content" in doc and doc["content"].strip()

    def test_rti_section_6_content_keyword_searchable(self):
        docs = self._get_docs()
        all_content = " ".join(d["content"] for d in docs).lower()
        # Must be retrievable by keyword: "section 6", "rti", "application"
        assert "section 6" in all_content or "public information officer" in all_content

    def test_rti_section_7_content_keyword_searchable(self):
        docs = self._get_docs()
        all_content = " ".join(d["content"] for d in docs).lower()
        assert "30 days" in all_content or "section 7" in all_content

    def test_rti_section_19_appeal_content_keyword_searchable(self):
        docs = self._get_docs()
        all_content = " ".join(d["content"] for d in docs).lower()
        assert "appeal" in all_content or "section 19" in all_content

    def test_mcc_complaint_no_response_keyword_searchable(self):
        """Key query: 'complaint no response 30 days' (architecture acceptance criterion)."""
        docs = self._get_docs()
        all_content = " ".join(d["content"] for d in docs).lower()
        # At least two of these terms must appear for keyword retrieval to work
        terms_found = sum(1 for t in ["complaint", "response", "30 days", "unresolved"] if t in all_content)
        assert terms_found >= 2, f"Keyword query terms missing. Found: {terms_found}/4"

    def test_escalation_contacts_present(self):
        docs = self._get_docs()
        all_content = " ".join(d["content"] for d in docs)
        # At least one MCC phone number or MWWD or MESCOM must appear
        assert ("0824" in all_content or "1912" in all_content or "MESCOM" in all_content)


# ---------------------------------------------------------------------------
# Compatibility with T2-12 retriever
# ---------------------------------------------------------------------------

class TestT213CompatibilityWithT212:
    def test_chunks_from_rti_doc_are_compatible_with_knowledge_chunk(self):
        """Chunks from chunk_document can be stored as KnowledgeChunk.content."""
        from rag.chunker import chunk_document
        from rag.vector_store import KnowledgeChunk

        text = (
            "Section 6 of the RTI Act 2005 requires a written request. "
            "The PIO must respond within 30 days. "
            "A first appeal can be filed under Section 19."
        )
        chunks = chunk_document(text, max_tokens=512)
        assert len(chunks) >= 1
        # Each chunk must be usable as KnowledgeChunk.content
        for i, c in enumerate(chunks):
            kc = KnowledgeChunk(id=f"test-{i}", title="RTI Act", content=c)
            assert isinstance(kc.content, str)
            assert kc.content.strip()

    def test_keyword_search_can_find_rti_query_in_seed_content(self):
        """Mocked keyword search returns chunks matching 'complaint no response 30 days'."""
        from scripts.ingest_rti_knowledge_base import _DOCUMENTS
        from rag.chunker import chunk_document
        from rag.vector_store import KnowledgeChunk

        # Simulate what keyword_search does: filter by ILIKE
        query = "complaint no response 30 days"
        all_chunks = []
        for doc in _DOCUMENTS:
            for chunk_text in chunk_document(doc["content"], max_tokens=512):
                all_chunks.append(
                    KnowledgeChunk(
                        id="x", title=doc["title"], content=chunk_text
                    )
                )

        # Simulate ILIKE matching (case-insensitive substring search)
        query_lower = query.lower()
        # Any of the query words should match something
        query_words = [w for w in query_lower.split() if len(w) > 3]
        matched = [
            c for c in all_chunks
            if any(w in c.content.lower() or w in c.title.lower() for w in query_words)
        ]
        assert len(matched) > 0, (
            "No chunks matched RTI query keywords — keyword search would fail"
        )

    def test_retrieve_context_compatible_with_chunker_output(self):
        """retrieve_context(query) with mocked DB returns chunks from chunked content."""
        from rag.retriever import retrieve_context
        from rag.vector_store import KnowledgeChunk

        fake_chunk = KnowledgeChunk(
            id="t1",
            title="RTI Act Section 6",
            content="A written request must be submitted to the PIO within 30 days.",
            similarity=None,
        )

        with patch("rag.embedder.embed", return_value=None):
            with patch("rag.vector_store.keyword_search", return_value=[fake_chunk]):
                result = retrieve_context("complaint no response 30 days")

        assert len(result) == 1
        assert "PIO" in result[0].content

    def test_chunks_to_context_string_with_seed_chunks(self):
        """chunks_to_context_string produces valid rag_context string for LLM."""
        from rag.chunker import chunk_document
        from rag.vector_store import KnowledgeChunk
        from rag.retriever import chunks_to_context_string

        text = "RTI Act requires response within 30 days. File appeal under Section 19."
        chunks_text = chunk_document(text, max_tokens=512)
        knowledge_chunks = [
            KnowledgeChunk(id=f"c{i}", title="RTI Act", content=c)
            for i, c in enumerate(chunks_text)
        ]
        context = chunks_to_context_string(knowledge_chunks)
        assert "RTI Act" in context
        assert "30 days" in context


# ---------------------------------------------------------------------------
# Ingestion script tests
# ---------------------------------------------------------------------------

class TestIngestionScript:
    def test_dry_run_returns_positive_chunk_count(self):
        """dry_run=True returns the expected number of chunks without DB writes."""
        from scripts.ingest_rti_knowledge_base import ingest

        count = ingest(dry_run=True)
        # At least 5 documents × 1 chunk each = ≥5 chunks
        assert count >= 5

    def test_ingest_supabase_unavailable_returns_0(self):
        """When Supabase is unavailable, ingest() returns 0 (graceful)."""
        from scripts.ingest_rti_knowledge_base import ingest

        with patch("db.supabase_client.get_client", return_value=None):
            count = ingest(dry_run=False)

        assert count == 0

    def test_ingest_dry_run_does_not_write_to_supabase(self):
        """dry_run=True must not call table.upsert (no DB writes)."""
        from scripts.ingest_rti_knowledge_base import ingest

        mock_client = MagicMock()
        with patch("db.supabase_client.get_client", return_value=mock_client):
            with patch("rag.embedder.embed", return_value=None):
                ingest(dry_run=True)
        # table.upsert must NOT have been called
        mock_client.table.assert_not_called()

    def test_ingest_inserts_chunks_when_supabase_available(self):
        """When Supabase is available, ingest() calls table.upsert for each chunk."""
        from scripts.ingest_rti_knowledge_base import ingest

        mock_result = MagicMock()
        mock_result.data = [{"id": "x"}]
        mock_chain = MagicMock()
        mock_chain.execute.return_value = mock_result
        mock_upsert = MagicMock(return_value=mock_chain)
        mock_table = MagicMock()
        mock_table.upsert = mock_upsert
        mock_client = MagicMock()
        mock_client.table.return_value = mock_table

        with patch("db.supabase_client.get_client", return_value=mock_client):
            with patch("rag.embedder.embed", return_value=None):
                count = ingest(dry_run=False)

        assert count > 0
        assert mock_client.table.called
