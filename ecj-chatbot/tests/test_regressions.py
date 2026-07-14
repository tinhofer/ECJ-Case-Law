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
    def test_uses_correct_celex_predicate(self):
        # cdm:resource_legal_celex does not exist in CELLAR (matches 0 rows);
        # the correct property is cdm:resource_legal_id_celex.
        query = _build_sparql_query(limit=10)
        assert "cdm:resource_legal_id_celex" in query

    def test_sector_six_filter(self):
        query = _build_sparql_query(limit=10)
        assert 'STRSTARTS(STR(?celex), "6")' in query

    def test_no_server_side_type_regex(self):
        # Server-side REGEX type filtering returned 0 rows on the CELLAR
        # endpoint; doc-type filtering must happen client-side instead.
        query = _build_sparql_query(limit=10)
        assert "REGEX(STR(?celex)" not in query

    def test_date_range_filter_instead_of_year_function(self):
        query = _build_sparql_query(limit=10, year_from=2018, year_to=2020)
        # String comparison on ISO dates: robust to literal typing in CELLAR
        assert 'STR(?date) >= "2018-01-01"' in query
        assert 'STR(?date) <= "2020-12-31"' in query
        assert "year(?date)" not in query


class TestClientSideDocTypeFiltering:
    """Doc-type filtering and labeling from the CELEX code, done client-side."""

    CASES = [
        {"celex": "62025CJ0100", "document_type": ""},   # judgment
        {"celex": "62025CC0819", "document_type": ""},   # AG opinion
        {"celex": "62025CO0055", "document_type": ""},   # order
    ]

    def test_celex_doc_type_extraction(self):
        from data_acquisition import celex_doc_type
        assert celex_doc_type("62025CJ0100") == "CJ"
        assert celex_doc_type("62025CC0819") == "CC"
        assert celex_doc_type("32016R0679") is None  # legislation, not sector 6
        assert celex_doc_type("") is None

    def test_filter_keeps_only_requested_types(self):
        from data_acquisition import _filter_and_label_by_doc_type
        kept = _filter_and_label_by_doc_type(list(self.CASES), ["CJ"])
        assert [c["celex"] for c in kept] == ["62025CJ0100"]

    def test_no_filter_keeps_all_and_labels(self):
        from data_acquisition import _filter_and_label_by_doc_type
        kept = _filter_and_label_by_doc_type(list(self.CASES), None)
        assert len(kept) == 3
        labels = {c["celex"]: c["document_type"] for c in kept}
        # AG opinions must NOT be labeled as judgments
        assert "Advocate General" in labels["62025CC0819"]
        assert "Judgment" in labels["62025CJ0100"]
        assert "Order" in labels["62025CO0055"]

    def test_existing_label_preserved(self):
        from data_acquisition import _filter_and_label_by_doc_type
        cases = [{"celex": "62025CJ0100", "document_type": "Urteil"}]
        kept = _filter_and_label_by_doc_type(cases, ["CJ"])
        assert kept[0]["document_type"] == "Urteil"

    def test_pagination_uses_raw_count(self):
        """A filtered page smaller than page_size must not stop pagination."""
        from unittest.mock import patch
        import data_acquisition as da

        # Two full raw pages (only some CJ), then an empty page ending the set
        pages = [
            ([{"celex": f"62025CJ{i:04d}", "document_type": ""} for i in range(2)], 5),
            ([{"celex": f"62024CJ{i:04d}", "document_type": ""} for i in range(2)], 5),
            ([], 0),
        ]
        with patch.object(da, "_fetch_metadata_page", side_effect=pages):
            result = da.get_all_case_law_metadata(page_size=5)
        assert len(result) == 4  # both full pages were consumed

    def test_partial_pages_do_not_end_pagination(self):
        """CELLAR's anytime timeout returns partial pages; only an empty
        page means the result set is exhausted (field: 104 rows for a
        1000-row request despite thousands of matches)."""
        from unittest.mock import patch
        import data_acquisition as da

        pages = [
            ([{"celex": "62025CJ0001", "document_type": ""}], 104),  # partial!
            ([{"celex": "62024CJ0002", "document_type": ""}], 50),   # partial!
            ([], 0),
        ]
        with patch.object(da, "_fetch_metadata_page", side_effect=pages) as mock:
            result = da.get_all_case_law_metadata(page_size=1000)
        assert len(result) == 2          # kept paging past the short pages
        assert mock.call_count == 3
        # Offset advances by rows actually received (104, then +50)
        offsets = [call.kwargs["offset"] for call in mock.call_args_list]
        assert offsets == [0, 104, 154]


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
