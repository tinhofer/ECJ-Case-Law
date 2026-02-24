"""Tests for the Markdown writer module."""

from pathlib import Path

from article2tts.markdown_writer import generate_filename, write_markdown


class TestGenerateFilename:
    def test_basic_title(self):
        result = generate_filename("Some Article Title")
        assert result == "some-article-title"

    def test_special_characters(self):
        result = generate_filename("Art. 267 TFEU: A Review!")
        assert "267" in result
        assert "!" not in result
        assert ":" not in result

    def test_empty_title(self):
        result = generate_filename("")
        assert result == "untitled"

    def test_long_title(self):
        result = generate_filename("A" * 200)
        assert len(result) <= 80

    def test_custom_fallback(self):
        result = generate_filename("", fallback_name="my-paper")
        assert result == "my-paper"


class TestWriteMarkdown:
    def test_basic_output(self, tmp_path: Path):
        output = tmp_path / "test.md"
        write_markdown(
            body="This is the body text.",
            footnotes=["First footnote.", "Second footnote."],
            title="Test Article",
            author="John Doe",
            language="en",
            tags=["EU-law", "CJEU"],
            output_path=output,
        )
        content = output.read_text(encoding="utf-8")
        assert "---" in content
        assert 'title: "Test Article"' in content
        assert 'author: "John Doe"' in content
        assert "language: en" in content
        assert "tags: [EU-law, CJEU]" in content
        assert "This is the body text." in content
        assert "## Notes" in content
        assert "1. First footnote." in content
        assert "2. Second footnote." in content

    def test_no_footnotes(self, tmp_path: Path):
        output = tmp_path / "test.md"
        write_markdown(
            body="Body only.",
            footnotes=[],
            title="No Notes",
            author="Author",
            language="de",
            tags=[],
            output_path=output,
        )
        content = output.read_text(encoding="utf-8")
        assert "## Notes" not in content
        assert "Body only." in content

    def test_creates_parent_dirs(self, tmp_path: Path):
        output = tmp_path / "deep" / "nested" / "test.md"
        write_markdown(
            body="Text.",
            footnotes=[],
            title="Title",
            author="Author",
            language="en",
            tags=[],
            output_path=output,
        )
        assert output.exists()
