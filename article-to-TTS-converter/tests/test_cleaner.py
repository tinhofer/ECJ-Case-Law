"""Tests for the cleaner module."""

from article2tts.cleaner import (
    clean_all,
    remove_bibliography,
    remove_cross_references,
    remove_figure_captions,
    remove_footnote_markers,
    remove_page_numbers,
    remove_parenthetical_citations,
    remove_table_of_contents,
    remove_urls_and_dois,
)


class TestRemoveFootnoteMarkers:
    def test_superscript_digits(self):
        assert remove_footnote_markers("the court¹²³ held") == "the court held"

    def test_mixed_superscripts(self):
        assert remove_footnote_markers("text⁴ and more⁵") == "text and more"


class TestRemoveParentheticalCitations:
    def test_simple_citation(self):
        result = remove_parenthetical_citations("as noted (Smith 2020) in the text")
        assert result == "as noted  in the text"

    def test_citation_with_page(self):
        result = remove_parenthetical_citations("argued (Jones 2019, p. 45)")
        assert result == "argued "

    def test_citation_with_see(self):
        result = remove_parenthetical_citations("(see Mueller 2021)")
        assert result == ""

    def test_multiple_authors(self):
        result = remove_parenthetical_citations("(Smith and Jones 2020)")
        assert result == ""

    def test_preserves_non_citations(self):
        result = remove_parenthetical_citations("(this is not a citation)")
        assert result == "(this is not a citation)"


class TestRemoveUrls:
    def test_http_url(self):
        result = remove_urls_and_dois("see https://example.com/foo here")
        assert result == "see  here"

    def test_doi(self):
        result = remove_urls_and_dois("doi: 10.1234/test.567")
        assert result.strip() == ""

    def test_preserves_normal_text(self):
        result = remove_urls_and_dois("no urls here")
        assert result == "no urls here"


class TestRemoveCrossReferences:
    def test_see_figure(self):
        result = remove_cross_references("data (see Figure 3) shows")
        assert result == "data  shows"

    def test_see_footnote(self):
        result = remove_cross_references("claim (see fn. 12) is")
        assert result == "claim  is"

    def test_cf_table(self):
        result = remove_cross_references("results (cf. Table 2) demonstrate")
        assert result == "results  demonstrate"

    def test_german_reference(self):
        result = remove_cross_references("Daten (siehe Tabelle 4) zeigen")
        assert result == "Daten  zeigen"


class TestRemoveFigureCaptions:
    def test_figure_caption(self):
        text = "Some text.\nFigure 3: Description of the figure.\nMore text."
        result = remove_figure_captions(text)
        assert "Figure 3" not in result
        assert "More text." in result

    def test_table_caption(self):
        text = "Table 1: Summary of results"
        result = remove_figure_captions(text)
        assert result.strip() == ""


class TestRemoveBibliography:
    def test_english_references(self):
        text = "Main text.\n\n## References\n\nSmith, J. (2020). Title."
        result = remove_bibliography(text)
        assert result == "Main text."

    def test_german_literatur(self):
        text = "Haupttext.\n\nLiteraturverzeichnis\n\nSchmidt (2019)."
        result = remove_bibliography(text)
        assert result == "Haupttext."

    def test_no_bibliography(self):
        text = "Just normal text."
        result = remove_bibliography(text)
        assert result == "Just normal text."


class TestRemoveTableOfContents:
    def test_toc_removal(self):
        text = "## Table of Contents\n\n1. Intro\n2. Main\n\n## Introduction\n\nBody text."
        result = remove_table_of_contents(text)
        assert "Table of Contents" not in result
        assert "## Introduction" in result
        assert "Body text." in result


class TestRemovePageNumbers:
    def test_standalone_numbers(self):
        text = "Text here.\n\n  42  \n\nMore text."
        result = remove_page_numbers(text)
        assert "42" not in result
        assert "Text here." in result

    def test_preserves_numbers_in_text(self):
        text = "Article 42 of the Treaty"
        result = remove_page_numbers(text)
        assert result == "Article 42 of the Treaty"


class TestCleanAll:
    def test_combined_cleaning(self):
        text = (
            "Introduction¹\n\n"
            "The court (Smith 2020) found that https://eur-lex.europa.eu is relevant.\n\n"
            "(see Figure 2)\n\n"
            "Figure 1: Overview.\n\n"
            "## References\n\nSmith, J. (2020). Article."
        )
        result = clean_all(text)
        assert "¹" not in result
        assert "Smith 2020" not in result
        assert "https://" not in result
        assert "see Figure" not in result
        assert "Figure 1:" not in result
        assert "References" not in result
