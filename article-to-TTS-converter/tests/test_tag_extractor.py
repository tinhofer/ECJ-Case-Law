"""Tests for the tag extractor module."""

from article2tts.tag_extractor import extract_tags


class TestExtractTags:
    def test_eu_law_tags(self):
        text = (
            "The European Court of Justice has ruled on fundamental rights "
            "in the context of data protection. The GDPR applies."
        )
        tags = extract_tags(text)
        assert "fundamental-rights" in tags
        assert "data-protection" in tags
        assert "GDPR" in tags

    def test_german_text_tags(self):
        text = (
            "Der EuGH hat im Bereich des Datenschutzes entschieden. "
            "Die Grundrechte der Charta müssen beachtet werden."
        )
        tags = extract_tags(text)
        assert "fundamental-rights" in tags or "data-protection" in tags

    def test_max_tags_limit(self):
        text = (
            "fundamental rights data protection competition law state aid "
            "consumer protection environmental law tax law labour law "
            "free movement internal market proportionality "
        ) * 5
        tags = extract_tags(text, max_tags=3)
        assert len(tags) <= 3

    def test_empty_text(self):
        tags = extract_tags("")
        assert tags == []

    def test_no_matching_keywords(self):
        tags = extract_tags("This text is about cooking recipes and gardening.")
        assert tags == []

    def test_tags_are_sorted(self):
        text = "state aid and competition law and fundamental rights"
        tags = extract_tags(text)
        assert tags == sorted(tags)

    def test_preliminary_ruling(self):
        text = "The request for a preliminary ruling concerns Article 267 TFEU."
        tags = extract_tags(text)
        assert "preliminary-ruling" in tags

    def test_cjeu_institution_tag(self):
        text = "The CJEU and the European Court of Justice decided the case."
        tags = extract_tags(text)
        assert "CJEU" in tags
