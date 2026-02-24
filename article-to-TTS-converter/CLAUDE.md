# CLAUDE.md — article-to-TTS-converter

## Project overview

Python CLI tool that converts academic articles (PDF/Word) into TTS-friendly Markdown for Obsidian. Focused on EU law and legal academic texts in EN/DE/FR.

## Tech stack

- Python 3.11+
- PyMuPDF (PDF extraction), python-docx (Word extraction)
- langdetect (language detection), click (CLI), PyYAML (config)
- pytest for testing

## Project structure

```
src/article2tts/
  cli.py              # CLI entry point (click), orchestrates the pipeline
  config.py           # YAML config loading, Config dataclass
  extractor_pdf.py    # PDF text + footnote extraction via PyMuPDF
  extractor_docx.py   # Word text + footnote extraction via python-docx
  cleaner.py          # Remove citations, URLs, bibliography, footnote markers, etc.
  abbreviations.py    # Abbreviation expansion engine (longest-match-first)
  normalizer.py       # Dehyphenation, dates, dashes, case citations, tables
  tag_extractor.py    # Keyword-based Obsidian tag extraction (~60 legal terms)
  markdown_writer.py  # YAML frontmatter + body + Notes section output
config/
  default.yaml           # Default configuration
  abbreviations_en.yaml  # English abbreviation dictionary
  abbreviations_de.yaml  # German abbreviation dictionary (incl. Austrian law)
  abbreviations_fr.yaml  # French abbreviation dictionary
tests/                   # pytest tests for cleaner, abbreviations, normalizer, tags, writer
```

## Processing pipeline

Input → Extract text → Detect language → Clean (remove clutter) → Expand abbreviations → Normalize for TTS → Extract tags → Write Markdown

## Commands

```bash
# Install (editable mode with dev deps)
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Convert a file
article2tts paper.pdf -o ~/Obsidian/Articles/

# Batch convert
article2tts ~/Downloads/papers/ -o ~/Obsidian/Articles/
```

## Key design decisions

- Footnotes are stripped from the body and appended as a numbered "Notes" section at the end
- Abbreviation expansion uses longest-match-first to avoid partial replacements (§§ before §)
- Case citations (C-123/45) are spelled out for TTS ("Case C 123 slash 45")
- Tag extraction uses curated keyword dictionaries, not ML, for predictable results
- Config is YAML-based with sensible defaults; custom abbreviations merge on top

## Adding abbreviations

Edit `config/abbreviations_{en,de,fr}.yaml` — format is `"abbreviation": "expansion"`. Abbreviations ending with a dot are matched including the dot. Uppercase acronyms use word-boundary matching.

## Testing conventions

- Tests are in `tests/`, one file per module (test_cleaner.py, test_normalizer.py, etc.)
- Tests use plain pytest classes, no fixtures except `tmp_path` for file I/O tests
- All 72 tests should pass before committing
