"""Tests for the normalizer module."""

from article2tts.normalizer import (
    dehyphenate,
    linearize_tables,
    normalize_all,
    normalize_dashes,
    normalize_dates,
    normalize_whitespace,
    roman_to_arabic_in_headings,
    spell_out_case_citations,
    strip_bold_italic,
)


class TestDehyphenate:
    def test_basic(self):
        result = dehyphenate("juris-\nprudence")
        assert result == "jurisprudence"

    def test_preserves_real_hyphens(self):
        result = dehyphenate("well-known concept")
        assert result == "well-known concept"

    def test_german(self):
        result = dehyphenate("Rechts-\nsprechung")
        assert result == "Rechtssprechung"


class TestNormalizeDashes:
    def test_em_dash_spacing(self):
        result = normalize_dashes("word—another")
        assert result == "word — another"

    def test_en_dash_not_in_range(self):
        result = normalize_dashes("concept–analysis")
        assert result == "concept — analysis"

    def test_en_dash_in_number_range(self):
        result = normalize_dashes("2020–2023")
        assert result == "2020–2023"


class TestSpellOutCaseCitations:
    def test_c_case(self):
        result = spell_out_case_citations("In C-123/45 the court")
        assert result == "In Case C 123 slash 45 the court"

    def test_t_case(self):
        result = spell_out_case_citations("See T-456/78")
        assert result == "See Case T 456 slash 78"

    def test_case_with_suffix(self):
        result = spell_out_case_citations("C-123/45 P")
        assert result == "Case C 123 slash 45 P"

    def test_preserves_normal_text(self):
        result = spell_out_case_citations("No case here")
        assert result == "No case here"


class TestRomanToArabic:
    def test_heading_with_roman(self):
        result = roman_to_arabic_in_headings("III. Some Heading")
        assert result == "3. Some Heading"

    def test_markdown_heading(self):
        result = roman_to_arabic_in_headings("## IV. Title")
        assert result == "## 4. Title"

    def test_preserves_non_roman(self):
        result = roman_to_arabic_in_headings("Regular text with III mentions")
        assert result == "Regular text with III mentions"


class TestNormalizeDates:
    def test_english_date(self):
        result = normalize_dates("12.03.2024", "en")
        assert result == "12 March 2024"

    def test_german_date(self):
        result = normalize_dates("12.03.2024", "de")
        assert result == "12 März 2024"

    def test_french_date(self):
        result = normalize_dates("12.03.2024", "fr")
        assert result == "12 mars 2024"

    def test_preserves_non_date(self):
        result = normalize_dates("Article 12.3", "en")
        assert result == "Article 12.3"


class TestLinearizeTables:
    def test_simple_table(self):
        table = (
            "| Name | Value |\n"
            "|------|-------|\n"
            "| Foo  | 42    |\n"
            "| Bar  | 99    |"
        )
        result = linearize_tables(table)
        assert "- Name: Foo; Value: 42" in result
        assert "- Name: Bar; Value: 99" in result


class TestStripBoldItalic:
    def test_bold(self):
        assert strip_bold_italic("this is **bold** text") == "this is bold text"

    def test_italic(self):
        assert strip_bold_italic("this is *italic* text") == "this is italic text"

    def test_underscore_bold(self):
        assert strip_bold_italic("this is __bold__ text") == "this is bold text"


class TestNormalizeWhitespace:
    def test_multiple_spaces(self):
        result = normalize_whitespace("too    many   spaces")
        assert result == "too many spaces"

    def test_multiple_blank_lines(self):
        result = normalize_whitespace("para 1\n\n\n\n\npara 2")
        assert result == "para 1\n\npara 2"


class TestNormalizeAll:
    def test_combined(self):
        text = "In C-123/45 the court—on 12.03.2024—held"
        result = normalize_all(text, "en")
        assert "Case C 123 slash 45" in result
        assert "12 March 2024" in result
        assert " — " in result
