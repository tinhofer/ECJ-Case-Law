"""Tests for the data_acquisition module."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from data_acquisition import (
    CaseLawDocument,
    LANGUAGE_NAMES,
    load_documents_from_disk,
    load_checkpoint,
    save_checkpoint,
    get_latest_case_date,
    fetch_document_text_with_fallback,
    create_case_document,
    CHECKPOINT_FILE,
)


class TestCaseLawDocument:
    def test_to_dict_roundtrip(self, sample_case_dict):
        doc = CaseLawDocument(**sample_case_dict)
        result = doc.to_dict()
        assert result["celex"] == "62020CJ0311"
        assert result["language"] == "DE"
        assert isinstance(result["keywords"], list)

    def test_language_name_de(self):
        doc = CaseLawDocument(
            celex="X", title="T", date="2020-01-01", case_number=None,
            court="CJ", document_type="J", text="text",
            eurlex_url="http://x", curia_url=None, ecli=None,
            keywords=[], language="DE",
        )
        assert doc.language_name == "Deutsch"

    def test_language_name_en(self):
        doc = CaseLawDocument(
            celex="X", title="T", date="2020-01-01", case_number=None,
            court="CJ", document_type="J", text="text",
            eurlex_url="http://x", curia_url=None, ecli=None,
            keywords=[], language="EN",
        )
        assert doc.language_name == "English"

    def test_language_name_unknown_falls_back(self):
        doc = CaseLawDocument(
            celex="X", title="T", date="2020-01-01", case_number=None,
            court="CJ", document_type="J", text="text",
            eurlex_url="http://x", curia_url=None, ecli=None,
            keywords=[], language="IT",
        )
        assert doc.language_name == "IT"


class TestLoadDocumentsFromDisk:
    def test_loads_valid_json_files(self, populated_cases_dir, sample_case_dict):
        docs = list(load_documents_from_disk(populated_cases_dir))
        assert len(docs) == 2
        assert all(isinstance(d, CaseLawDocument) for d in docs)

    def test_skips_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json", encoding="utf-8")
        docs = list(load_documents_from_disk(tmp_path))
        assert len(docs) == 0

    def test_empty_directory(self, tmp_path):
        docs = list(load_documents_from_disk(tmp_path))
        assert len(docs) == 0


class TestCheckpointSystem:
    def test_load_missing_checkpoint_returns_defaults(self, tmp_path):
        cp = load_checkpoint(tmp_path)
        assert cp["last_download_date"] is None
        assert cp["total_downloaded"] == 0

    def test_save_and_load_checkpoint(self, tmp_path):
        save_checkpoint(tmp_path, {
            "last_download_date": "2024-01-01T00:00:00",
            "last_case_date": "2024-01-01",
            "total_downloaded": 42,
        })
        cp = load_checkpoint(tmp_path)
        assert cp["total_downloaded"] == 42
        assert cp["last_download_date"] == "2024-01-01T00:00:00"
        assert "updated_at" in cp

    def test_checkpoint_file_location(self, tmp_path):
        save_checkpoint(tmp_path, {"total_downloaded": 1})
        assert (tmp_path / CHECKPOINT_FILE).exists()


class TestGetLatestCaseDate:
    def test_returns_most_recent_date(self, populated_cases_dir):
        latest = get_latest_case_date(populated_cases_dir)
        assert latest == "2021-07-16"

    def test_returns_none_for_empty_dir(self, tmp_path):
        latest = get_latest_case_date(tmp_path)
        assert latest is None

    def test_ignores_checkpoint_file(self, tmp_path):
        # Write a checkpoint file (should be skipped)
        cp_path = tmp_path / CHECKPOINT_FILE
        cp_path.write_text(json.dumps({"date": "9999-12-31"}), encoding="utf-8")
        latest = get_latest_case_date(tmp_path)
        assert latest is None


class TestFetchDocumentTextWithFallback:
    @patch("data_acquisition.fetch_document_text")
    def test_returns_first_successful_language(self, mock_fetch):
        mock_fetch.side_effect = [None, "English text", "French text"]
        text, lang = fetch_document_text_with_fallback("62020CJ0311")
        assert text == "English text"
        assert lang == "EN"
        assert mock_fetch.call_count == 2

    @patch("data_acquisition.fetch_document_text")
    def test_returns_german_first(self, mock_fetch):
        mock_fetch.side_effect = ["German text"]
        text, lang = fetch_document_text_with_fallback("62020CJ0311")
        assert text == "German text"
        assert lang == "DE"

    @patch("data_acquisition.fetch_document_text")
    def test_returns_none_when_all_fail(self, mock_fetch):
        mock_fetch.return_value = None
        text, lang = fetch_document_text_with_fallback("62020CJ0311")
        assert text is None
        assert lang == ""

    @patch("data_acquisition.fetch_document_text")
    def test_respects_custom_language_list(self, mock_fetch):
        mock_fetch.side_effect = ["French text"]
        text, lang = fetch_document_text_with_fallback("X", languages=["FR"])
        assert lang == "FR"


class TestCreateCaseDocument:
    @patch("data_acquisition.fetch_document_text_with_fallback")
    def test_creates_document_with_german_text(self, mock_fallback, sample_metadata):
        mock_fallback.return_value = ("Volltext des Urteils. " * 50, "DE")
        doc = create_case_document(sample_metadata)
        assert doc is not None
        assert doc.celex == "62020CJ0311"
        assert doc.language == "DE"
        assert "eur-lex.europa.eu/legal-content/DE" in doc.eurlex_url

    @patch("data_acquisition.fetch_document_text_with_fallback")
    def test_creates_document_with_english_fallback(self, mock_fallback, sample_metadata):
        mock_fallback.return_value = ("English judgment text. " * 50, "EN")
        doc = create_case_document(sample_metadata)
        assert doc is not None
        assert doc.language == "EN"
        assert "legal-content/EN" in doc.eurlex_url

    @patch("data_acquisition.fetch_document_text_with_fallback")
    def test_returns_none_when_no_text(self, mock_fallback, sample_metadata):
        mock_fallback.return_value = (None, "")
        doc = create_case_document(sample_metadata)
        assert doc is None

    def test_returns_none_for_empty_celex(self):
        doc = create_case_document({"celex": ""})
        assert doc is None

    @patch("data_acquisition.fetch_document_text_with_fallback")
    def test_curia_url_uses_correct_language(self, mock_fallback, sample_metadata):
        mock_fallback.return_value = ("Text", "FR")
        doc = create_case_document(sample_metadata)
        assert doc is not None
        assert "language=fr" in doc.curia_url

    @patch("data_acquisition.fetch_document_text_with_fallback")
    def test_no_curia_url_without_case_number(self, mock_fallback):
        meta = {"celex": "X", "title": "T"}
        mock_fallback.return_value = ("Text", "DE")
        doc = create_case_document(meta)
        assert doc is not None
        assert doc.curia_url is None
