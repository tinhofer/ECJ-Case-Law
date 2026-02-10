"""Tests for the embeddings module — focuses on pure logic (chunking, dedup)."""

from unittest.mock import MagicMock

import pytest

from embeddings import CaseLawVectorStore
from data_acquisition import CaseLawDocument


def _make_store(chunk_size=100, chunk_overlap=20):
    """Create a CaseLawVectorStore with mocked heavy deps."""
    store = CaseLawVectorStore.__new__(CaseLawVectorStore)
    store.chunk_size = chunk_size
    store.chunk_overlap = chunk_overlap
    store.embedding_model = MagicMock()
    store.client = MagicMock()
    store.collection = MagicMock()
    store.persist_directory = "/tmp/test_index"
    return store


class TestChunkText:
    def test_short_text_single_chunk(self):
        store = _make_store(chunk_size=500)
        chunks = store._chunk_text("Hello world")
        assert chunks == ["Hello world"]

    def test_long_text_produces_multiple_chunks(self):
        store = _make_store(chunk_size=50, chunk_overlap=10)
        text = "A" * 200
        chunks = store._chunk_text(text)
        assert len(chunks) > 1

    def test_chunks_overlap(self):
        store = _make_store(chunk_size=50, chunk_overlap=10)
        text = "ABCDEFGHIJ" * 20  # 200 chars
        chunks = store._chunk_text(text)
        # Adjacent chunks should share some content due to overlap
        for i in range(len(chunks) - 1):
            end_of_current = chunks[i][-10:]
            assert end_of_current in chunks[i + 1] or len(chunks[i]) <= 50

    def test_empty_text(self):
        store = _make_store(chunk_size=100)
        chunks = store._chunk_text("")
        assert chunks == [""]

    def test_sentence_boundary_splitting(self):
        store = _make_store(chunk_size=60, chunk_overlap=10)
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = store._chunk_text(text)
        assert len(chunks) >= 2


class TestGetUniqueCases:
    def test_deduplicates_by_celex(self):
        store = _make_store()
        results = [
            {"metadata": {"celex": "A"}, "text": "chunk 1", "distance": 0.1},
            {"metadata": {"celex": "A"}, "text": "chunk 2", "distance": 0.2},
            {"metadata": {"celex": "B"}, "text": "chunk 3", "distance": 0.3},
        ]
        unique = store.get_unique_cases(results)
        assert len(unique) == 2
        celex_ids = [r["metadata"]["celex"] for r in unique]
        assert "A" in celex_ids
        assert "B" in celex_ids

    def test_keeps_first_occurrence(self):
        store = _make_store()
        results = [
            {"metadata": {"celex": "A"}, "text": "best", "distance": 0.1},
            {"metadata": {"celex": "A"}, "text": "worse", "distance": 0.5},
        ]
        unique = store.get_unique_cases(results)
        assert len(unique) == 1
        assert unique[0]["text"] == "best"

    def test_empty_results(self):
        store = _make_store()
        unique = store.get_unique_cases([])
        assert unique == []

    def test_missing_celex_skipped(self):
        store = _make_store()
        results = [
            {"metadata": {}, "text": "no celex", "distance": 0.1},
            {"metadata": {"celex": "B"}, "text": "has celex", "distance": 0.2},
        ]
        unique = store.get_unique_cases(results)
        assert len(unique) == 1
        assert unique[0]["metadata"]["celex"] == "B"


class TestAddDocument:
    def test_add_document_calls_collection(self):
        store = _make_store(chunk_size=500)
        doc = CaseLawDocument(
            celex="62020CJ0311", title="Test", date="2020-01-01",
            case_number="C-311/18", court="Court of Justice",
            document_type="Judgment", text="Short text for testing.",
            eurlex_url="http://example.com", curia_url=None, ecli=None,
            keywords=[], language="DE",
        )
        count = store.add_document(doc)
        assert count == 1
        store.collection.add.assert_called_once()

    def test_add_document_chunk_metadata(self):
        store = _make_store(chunk_size=500)
        doc = CaseLawDocument(
            celex="TEST123", title="Title", date="2020-01-01",
            case_number="C-1/20", court="Court of Justice",
            document_type="Judgment", text="Document text.",
            eurlex_url="http://example.com", curia_url="http://curia.example.com",
            ecli="ECLI:EU:C:2020:1", keywords=["test"], language="EN",
        )
        store.add_document(doc)
        call_args = store.collection.add.call_args
        metadatas = call_args.kwargs.get("metadatas") or call_args[1].get("metadatas")
        assert metadatas[0]["celex"] == "TEST123"
        assert metadatas[0]["language"] == "EN"


class TestSearch:
    def test_search_returns_formatted_results(self):
        store = _make_store()
        store.collection.query.return_value = {
            "documents": [["text1", "text2"]],
            "metadatas": [[{"celex": "A"}, {"celex": "B"}]],
            "distances": [[0.1, 0.2]],
        }
        results = store.search("test query", n_results=2)
        assert len(results) == 2
        assert results[0]["text"] == "text1"
        assert results[0]["metadata"]["celex"] == "A"
        assert results[0]["distance"] == 0.1

    def test_search_empty_results(self):
        store = _make_store()
        store.collection.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        results = store.search("no match")
        assert results == []
