"""Regression tests for the bugs that made the tool unusable.

Each test class documents one previously-broken behavior.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from data_acquisition import (
    CaseLawDocument,
    document_passes_subject_filter,
    load_checkpoint,
    save_checkpoint,
    _build_sparql_query,
    DataAcquisitionError,
    _execute_sparql_query,
)
from embeddings import CaseLawVectorStore


def _make_doc(language="DE", keywords=None):
    return CaseLawDocument(
        celex="62020CJ0311", title="T", date="2020-01-01", case_number="C-311/18",
        court="Court of Justice", document_type="Judgment", text="text",
        eurlex_url="http://example.com", curia_url=None, ecli=None,
        keywords=keywords if keywords is not None else [], language=language,
    )


def _make_store(chunk_size=100, chunk_overlap=20):
    store = CaseLawVectorStore.__new__(CaseLawVectorStore)
    store.chunk_size = chunk_size
    store.chunk_overlap = chunk_overlap
    store.embedding_model = MagicMock()
    store.client = MagicMock()
    store.collection = MagicMock()
    store.persist_directory = "/tmp/test_index"
    return store


class TestChunkerTermination:
    """The chunker previously looped forever when the only sentence
    boundary in a window was near the window start (start moved backwards)."""

    def test_early_sentence_boundary_terminates(self):
        store = _make_store(chunk_size=1000, chunk_overlap=200)
        # One sentence end at position ~50, then no boundary for a long time
        text = "Kurzer Satz. " + "A" * 5000
        chunks = store._chunk_text(text)
        assert len(chunks) < 100  # would have been infinite before the fix
        # No content lost: last chunk must reach the end of the text
        assert chunks[-1].endswith("A")

    def test_forward_progress_with_large_overlap(self):
        store = _make_store(chunk_size=50, chunk_overlap=49)
        text = "B" * 500
        chunks = store._chunk_text(text)
        assert len(chunks) <= 500

    def test_no_infinite_loop_on_period_at_window_start(self):
        store = _make_store(chunk_size=100, chunk_overlap=90)
        text = ". " + "C" * 1000
        chunks = store._chunk_text(text)
        assert chunks  # completes at all


class TestLanguageAwareSubjectFilter:
    """English/French documents were previously always rejected because
    German keywords never matched their extracted keywords."""

    KEYWORDS = {
        "DE": ["Datenschutz"],
        "EN": ["data protection"],
    }

    def test_german_doc_matching_keyword_kept(self):
        doc = _make_doc("DE", ["Datenschutz", "Grundrechte"])
        assert document_passes_subject_filter(doc, self.KEYWORDS)

    def test_german_doc_not_matching_rejected(self):
        doc = _make_doc("DE", ["Zollunion", "Agrarpolitik"])
        assert not document_passes_subject_filter(doc, self.KEYWORDS)

    def test_english_doc_matched_against_english_keywords(self):
        doc = _make_doc("EN", ["Data protection", "GDPR"])
        assert document_passes_subject_filter(doc, self.KEYWORDS)

    def test_language_without_keyword_list_kept(self):
        # No FR list configured -> fail open, keep the document
        doc = _make_doc("FR", ["politique agricole"])
        assert document_passes_subject_filter(doc, self.KEYWORDS)

    def test_doc_without_extracted_keywords_kept(self):
        # Stichwort extraction failed -> fail open
        doc = _make_doc("EN", [])
        assert document_passes_subject_filter(doc, self.KEYWORDS)

    def test_plain_list_treated_as_german(self):
        de_doc = _make_doc("DE", ["Zollunion"])
        en_doc = _make_doc("EN", ["customs union"])
        assert not document_passes_subject_filter(de_doc, ["Datenschutz"])
        assert document_passes_subject_filter(en_doc, ["Datenschutz"])  # fail-open

    def test_no_filter_keeps_everything(self):
        assert document_passes_subject_filter(_make_doc("DE"), None)
        assert document_passes_subject_filter(_make_doc("DE"), {})


class TestRejectedCelexPersistence:
    """Rejected cases are stored in the checkpoint so they are not
    re-downloaded on every start."""

    def test_checkpoint_roundtrip_with_rejected(self, tmp_path):
        checkpoint = load_checkpoint(tmp_path)
        assert checkpoint["rejected_celex"] == []
        checkpoint["rejected_celex"] = ["62020CJ0001", "62020CJ0002"]
        save_checkpoint(tmp_path, checkpoint)
        loaded = load_checkpoint(tmp_path)
        assert loaded["rejected_celex"] == ["62020CJ0001", "62020CJ0002"]


class TestSparqlQueryBuilding:
    def test_celex_doc_type_filter_in_query(self):
        query = _build_sparql_query(limit=10, celex_doc_types=["CJ"])
        assert 'REGEX(STR(?celex), "^6[0-9]{4}(CJ)")' in query

    def test_multiple_doc_types(self):
        query = _build_sparql_query(limit=10, celex_doc_types=["CJ", "CO"])
        assert "(CJ|CO)" in query

    def test_date_range_filter_instead_of_year_function(self):
        query = _build_sparql_query(limit=10, year_from=2018, year_to=2020)
        # String comparison on ISO dates: robust to literal typing in CELLAR
        assert 'STR(?date) >= "2018-01-01"' in query
        assert 'STR(?date) <= "2020-12-31"' in query
        assert "year(?date)" not in query

    def test_no_celex_filter_when_not_requested(self):
        query = _build_sparql_query(limit=10, celex_doc_types=None)
        assert "REGEX(STR(?celex)" not in query


class TestSparqlErrorHandling:
    """SPARQL failures previously returned [] silently, leaving the app
    with an empty index and no explanation."""

    @patch("data_acquisition.SPARQLWrapper")
    @patch("data_acquisition.time.sleep")
    def test_raises_after_retries(self, mock_sleep, mock_wrapper):
        mock_wrapper.return_value.query.side_effect = OSError("connection refused")
        with pytest.raises(DataAcquisitionError, match="publications.europa.eu"):
            _execute_sparql_query("SELECT 1", retries=2)
        assert mock_wrapper.call_count == 2

    @patch("data_acquisition.SPARQLWrapper")
    @patch("data_acquisition.time.sleep")
    def test_best_effort_mode_returns_empty(self, mock_sleep, mock_wrapper):
        mock_wrapper.return_value.query.side_effect = OSError("connection refused")
        result = _execute_sparql_query("SELECT 1", retries=1, raise_on_error=False)
        assert result == []

    @patch("data_acquisition.SPARQLWrapper")
    def test_success_returns_parsed_cases(self, mock_wrapper):
        mock_wrapper.return_value.query.return_value.convert.return_value = {
            "results": {"bindings": [{
                "celex": {"value": "62020CJ0311"},
                "title": {"value": "Schrems II"},
                "date": {"value": "2020-07-16"},
            }]}
        }
        result = _execute_sparql_query("SELECT 1")
        assert result[0]["celex"] == "62020CJ0311"
