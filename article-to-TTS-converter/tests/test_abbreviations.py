"""Tests for the abbreviation expansion engine."""

from article2tts.abbreviations import expand_abbreviations


class TestExpandAbbreviations:
    def test_dotted_abbreviation(self):
        abbrevs = {"e.g.": "for example"}
        result = expand_abbreviations("This is, e.g. a test", abbrevs)
        assert result == "This is, for example a test"

    def test_section_symbol(self):
        abbrevs = {"§": "Section"}
        result = expand_abbreviations("See § 12 of the Act", abbrevs)
        assert result == "See Section 12 of the Act"

    def test_double_section_symbol(self):
        abbrevs = {"§§": "Sections", "§": "Section"}
        result = expand_abbreviations("§§ 12-14", abbrevs)
        assert result == "Sections 12-14"

    def test_uppercase_acronym(self):
        abbrevs = {"TFEU": "Treaty on the Functioning of the European Union"}
        result = expand_abbreviations("Article 267 TFEU provides", abbrevs)
        assert "Treaty on the Functioning of the European Union" in result

    def test_article_abbreviation(self):
        abbrevs = {"Art.": "Article"}
        result = expand_abbreviations("Art. 267 provides", abbrevs)
        assert result == "Article 267 provides"

    def test_no_partial_match(self):
        abbrevs = {"EU": "European Union"}
        result = expand_abbreviations("The EUROPE project", abbrevs)
        assert result == "The EUROPE project"

    def test_multiple_abbreviations(self):
        abbrevs = {
            "Art.": "Article",
            "TFEU": "Treaty on the Functioning of the European Union",
            "cf.": "compare",
        }
        result = expand_abbreviations("cf. Art. 267 TFEU", abbrevs)
        assert "compare" in result
        assert "Article" in result
        assert "Treaty on the Functioning of the European Union" in result

    def test_empty_map(self):
        result = expand_abbreviations("no changes here", {})
        assert result == "no changes here"

    def test_german_paragraph(self):
        abbrevs = {"§": "Paragraph", "Abs.": "Absatz"}
        result = expand_abbreviations("§ 3 Abs. 1", abbrevs)
        assert result == "Paragraph 3 Absatz 1"
