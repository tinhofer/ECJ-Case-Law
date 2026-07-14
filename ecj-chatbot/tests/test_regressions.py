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


class TestCheckpointNotACase:
    """The checkpoint file must never be counted or loaded as a case:
    after a failed download it was the only .json on disk, the app
    counted it as '1 Entscheidung', skipped the download, and built an
    empty index."""

    def test_load_documents_skips_checkpoint(self, tmp_path, sample_case_dict):
        from data_acquisition import (load_documents_from_disk,
                                      save_checkpoint, load_checkpoint)
        save_checkpoint(tmp_path, load_checkpoint(tmp_path))
        (tmp_path / "62020CJ0311.json").write_text(
            json.dumps(sample_case_dict), encoding="utf-8")
        docs = list(load_documents_from_disk(tmp_path))
        assert [d.celex for d in docs] == ["62020CJ0311"]

    def test_config_status_excludes_checkpoint(self, tmp_path):
        from config import Config
        cfg = Config(data_dir=tmp_path)
        cfg.ensure_directories()
        from data_acquisition import save_checkpoint, load_checkpoint
        save_checkpoint(cfg.cases_dir, load_checkpoint(cfg.cases_dir))
        assert cfg.get_status()["cases_count"] == 0


class TestTopicCorpora:
    """Topic corpora: ALL decisions citing a given legal act."""

    def test_citing_query_shape(self):
        from unittest.mock import patch
        import data_acquisition as da

        captured = {}

        def fake_execute(query, **kwargs):
            captured["query"] = query
            return []

        with patch.object(da, "_execute_sparql_query", side_effect=fake_execute):
            da.get_citing_case_law_metadata("32016R0679")

        q = captured["query"]
        assert "cdm:work_cites_work" in q
        assert '"32016R0679"' in q
        assert 'STRSTARTS(STR(?celex), "6")' in q  # only case-law
        assert "a cdm:case-law" not in q           # broken class constraint stays out

    def test_citing_results_filtered_and_sorted(self):
        from unittest.mock import patch
        import data_acquisition as da

        rows = [
            {"celex": "62019CJ0311", "document_type": "", "court": "", "date": "2020-07-16"},
            {"celex": "62021CC0300", "document_type": "", "court": "", "date": "2023-01-01"},
            {"celex": "62022CJ0100", "document_type": "", "court": "", "date": "2024-03-03"},
        ]
        with patch.object(da, "_execute_sparql_query", return_value=list(rows)):
            result = da.get_citing_case_law_metadata("32016R0679")
        # AG opinion filtered out, newest judgment first
        assert [c["celex"] for c in result] == ["62022CJ0100", "62019CJ0311"]

    def test_topic_download_ignores_keyword_filter(self, tmp_path):
        """Citing the act IS the relevance criterion - a decision whose
        Stichwort would fail the keyword filter must still be saved."""
        from unittest.mock import patch
        import data_acquisition as da

        meta = {"celex": "62019CJ0311", "title": "T", "date": "2020-07-16",
                "case_number": "C-311/18", "court": "Court of Justice",
                "document_type": "Judgment (Court of Justice)",
                "ecli": None}
        doc = da.CaseLawDocument(
            celex="62019CJ0311", title="T", date="2020-07-16",
            case_number="C-311/18", court="Court of Justice",
            document_type="Judgment (Court of Justice)", text="x" * 600,
            eurlex_url="http://example.com", curia_url=None, ecli=None,
            keywords=["Zollunion"],  # would NOT match any subject keywords
            language="DE",
        )
        with patch.object(da, "get_citing_case_law_metadata", return_value=[meta]), \
             patch.object(da, "create_case_document", return_value=doc), \
             patch.object(da.time, "sleep"):
            n = da.download_topic_corpora(tmp_path, ["32016R0679"])
        assert n == 1
        assert (tmp_path / "62019CJ0311.json").exists()

    def test_topic_download_skips_existing(self, tmp_path):
        from unittest.mock import patch
        import data_acquisition as da

        meta = {"celex": "62019CJ0311"}
        (tmp_path / "62019CJ0311.json").write_text("{}", encoding="utf-8")
        with patch.object(da, "get_citing_case_law_metadata", return_value=[meta]), \
             patch.object(da, "create_case_document") as mock_create:
            n = da.download_topic_corpora(tmp_path, ["32016R0679"])
        assert n == 0
        mock_create.assert_not_called()

    def test_config_topic_celex_from_env(self, monkeypatch):
        from config import Config
        monkeypatch.setenv("ECJ_TOPIC_CELEX", "32016R0679, 32003L0088")
        cfg = Config.from_env()
        assert cfg.topic_celex == ["32016R0679", "32003L0088"]


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
        query = _build_sparql_query(limit=10, date_from="2018-01-01",
                                    date_to="2020-12-31")
        # String comparison on ISO dates: robust to literal typing in CELLAR
        assert 'STR(?date) >= "2018-01-01"' in query
        assert 'STR(?date) <= "2020-12-31"' in query
        assert "year(?date)" not in query

    def test_no_expensive_constructs(self):
        # ORDER BY / OFFSET / label joins made the endpoint's anytime
        # timeout truncate results to 0-104 rows; they must stay out.
        query = _build_sparql_query(limit=10, date_from="2026-06-01",
                                    date_to="2026-06-30")
        assert "ORDER BY" not in query
        assert "OFFSET" not in query
        assert "skos:prefLabel" not in query

    def test_no_case_law_class_constraint(self):
        # CELLAR types judgments with subclasses and the endpoint does no
        # inference: "?work a cdm:case-law" matched only a stray handful
        # of documents (0-10/month, zero judgments) and hid every ruling.
        query = _build_sparql_query(limit=10)
        assert "a cdm:case-law" not in query


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

    def test_month_windows_newest_first_with_correct_boundaries(self):
        from data_acquisition import _month_windows
        windows = _month_windows(2020, 2020)  # fixed past year: no today-dependence
        assert len(windows) == 12
        assert windows[0] == ("2020-12-01", "2020-12-31")   # newest first
        assert windows[-1] == ("2020-01-01", "2020-01-31")
        assert ("2020-02-01", "2020-02-29") in windows      # leap year

    def test_month_windows_span_years(self):
        from data_acquisition import _month_windows
        windows = _month_windows(2019, 2020)
        assert len(windows) == 24
        assert windows[12] == ("2019-12-01", "2019-12-31")

    def test_windowed_fetch_collects_across_months(self):
        """Fetching walks month windows and accumulates until max_cases."""
        from unittest.mock import patch
        import data_acquisition as da

        case1 = {"celex": "62020CJ0001", "document_type": "", "date": "2020-12-10"}
        case2 = {"celex": "62020CJ0002", "document_type": "", "date": "2020-11-05"}
        pages = [([case1], 4), ([case2], 3)]
        with patch.object(da, "_fetch_metadata_window", side_effect=pages) as mock:
            result = da.get_all_case_law_metadata(
                year_from=2020, year_to=2020, max_cases=2)
        assert [c["celex"] for c in result] == ["62020CJ0001", "62020CJ0002"]
        assert mock.call_count == 2  # stopped at max_cases, not all 12 months

    def test_empty_window_retried_once(self):
        """An empty month may be an endpoint timeout - retry once (field:
        the same query returned 104 rows on one run and 0 on the next)."""
        from unittest.mock import patch
        import data_acquisition as da

        case = {"celex": "62020CJ0003", "document_type": "", "date": "2020-11-20"}
        pages = [([], 0), ([], 0), ([case], 2)]  # Dec empty twice, Nov delivers
        with patch.object(da, "_fetch_metadata_window", side_effect=pages) as mock:
            result = da.get_all_case_law_metadata(
                year_from=2020, year_to=2020, max_cases=1)
        assert len(result) == 1
        assert mock.call_count == 3  # December was retried before moving on


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
