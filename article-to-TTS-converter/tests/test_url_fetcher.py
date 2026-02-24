"""Tests for the url_fetcher module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from article2tts.url_fetcher import (
    _looks_like_pdf_url,
    _normalize_url,
    extract_urls_from_markdown,
)


class TestLooksLikePdfUrl:
    def test_direct_pdf_link(self):
        assert _looks_like_pdf_url("https://example.com/paper.pdf")

    def test_pdf_with_query_params(self):
        assert _looks_like_pdf_url("https://example.com/paper.pdf?dl=1")

    def test_ssrn_abstract(self):
        assert _looks_like_pdf_url("https://ssrn.com/abstract=1234567")

    def test_ssrn_papers(self):
        assert _looks_like_pdf_url("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=123")

    def test_eurlex(self):
        assert _looks_like_pdf_url("https://eur-lex.europa.eu/something?FORMAT=PDF")

    def test_doi(self):
        assert _looks_like_pdf_url("https://doi.org/10.1234/test")

    def test_jstor(self):
        assert _looks_like_pdf_url("https://jstor.org/stable/12345")

    def test_arxiv_abs(self):
        assert _looks_like_pdf_url("https://arxiv.org/abs/2301.12345")

    def test_arxiv_pdf(self):
        assert _looks_like_pdf_url("https://arxiv.org/pdf/2301.12345")

    def test_random_html(self):
        assert not _looks_like_pdf_url("https://example.com/page.html")

    def test_random_url(self):
        assert not _looks_like_pdf_url("https://google.com")


class TestNormalizeUrl:
    def test_arxiv_abs_to_pdf(self):
        result = _normalize_url("https://arxiv.org/abs/2301.12345")
        assert "arxiv.org/pdf/2301.12345" in result

    def test_ssrn_abstract_to_download(self):
        result = _normalize_url("https://ssrn.com/abstract=9876543")
        assert "Delivery.cfm" in result
        assert "9876543" in result

    def test_normal_url_unchanged(self):
        url = "https://example.com/paper.pdf"
        assert _normalize_url(url) == url


class TestExtractUrlsFromMarkdown:
    def test_markdown_link(self, tmp_path: Path):
        md = tmp_path / "reading.md"
        md.write_text(
            "# Reading List\n\n"
            "- [Good Paper](https://example.com/paper.pdf)\n"
            "- [Blog Post](https://example.com/blog.html)\n"
        )
        results = extract_urls_from_markdown(md)
        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/paper.pdf"
        assert results[0]["title"] == "Good Paper"

    def test_bare_url(self, tmp_path: Path):
        md = tmp_path / "notes.md"
        md.write_text(
            "Check this paper: https://arxiv.org/abs/2301.12345\n"
        )
        results = extract_urls_from_markdown(md)
        assert len(results) == 1
        assert "arxiv.org" in results[0]["url"]

    def test_multiple_links(self, tmp_path: Path):
        md = tmp_path / "list.md"
        md.write_text(
            "- [Paper A](https://example.com/a.pdf)\n"
            "- [Paper B](https://ssrn.com/abstract=123456)\n"
            "- [Not a PDF](https://example.com/page.html)\n"
            "- https://doi.org/10.1234/test\n"
        )
        results = extract_urls_from_markdown(md)
        assert len(results) == 3

    def test_no_pdf_links(self, tmp_path: Path):
        md = tmp_path / "empty.md"
        md.write_text(
            "# Just Notes\n\nNo links to PDFs here.\n"
            "[Blog](https://example.com/blog.html)\n"
        )
        results = extract_urls_from_markdown(md)
        assert len(results) == 0

    def test_deduplicates_urls(self, tmp_path: Path):
        md = tmp_path / "dupes.md"
        md.write_text(
            "- [Paper](https://example.com/paper.pdf)\n"
            "- Also here: https://example.com/paper.pdf\n"
        )
        results = extract_urls_from_markdown(md)
        assert len(results) == 1

    def test_ssrn_link(self, tmp_path: Path):
        md = tmp_path / "ssrn.md"
        md.write_text(
            "Read this: [SSRN Paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4567890)\n"
        )
        results = extract_urls_from_markdown(md)
        assert len(results) == 1
        assert results[0]["title"] == "SSRN Paper"
