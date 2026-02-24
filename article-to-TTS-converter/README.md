# article-to-TTS-converter

Converts academic articles (PDF/Word) to TTS-friendly Markdown for Obsidian — strips footnotes, expands abbreviations, and normalizes text for read-aloud tools.

## What it does

Takes a PDF or Word document and produces a clean `.md` file optimized for text-to-speech tools like **Aloud**:

- **Removes** footnote markers, page numbers, bibliography, URLs, figure captions, parenthetical citations
- **Appends** footnote content as a "Notes" section at the end
- **Expands** abbreviations (Art. → Article, § → Section, TFEU → Treaty on the Functioning of the European Union, …)
- **Spells out** case citations (C-123/45 → "Case C 123 slash 45")
- **Normalizes** dates, dashes, Roman numerals, whitespace
- **Auto-generates** Obsidian tags from article keywords
- **Detects** language (EN/DE/FR) and loads matching abbreviation dictionary
- **Batch mode** for converting entire folders

## Output

Obsidian-ready Markdown with YAML frontmatter:

```markdown
---
title: "Fundamental Rights in EU Data Protection Law"
author: "Jane Smith"
date: 2024-03-15
converted: 2026-02-24
language: en
tags: [CJEU, GDPR, data-protection, fundamental-rights]
---

# Fundamental Rights in EU Data Protection Law

[Clean, TTS-optimized body text...]

---

## Notes

1. First footnote content, fully expanded.
2. Second footnote content.
```

## Installation

```bash
git clone https://github.com/tinhofer/article-to-TTS-converter.git
cd article-to-TTS-converter
pip install -e .
```

## Usage

```bash
# Single file
article2tts paper.pdf

# Specify output directory (e.g. Obsidian vault)
article2tts paper.pdf -o ~/Obsidian/Articles/

# Word document, force German
article2tts aufsatz.docx --lang de

# Custom config
article2tts paper.pdf --config my-config.yaml

# Batch mode — convert all files in a folder
article2tts ~/Downloads/papers/ -o ~/Obsidian/Articles/

# Batch mode with glob pattern
article2tts ~/Downloads/papers/*.pdf -o ~/Obsidian/Articles/
```

## Configuration

Create a `config.yaml` to customize behavior:

```yaml
output_dir: ~/Obsidian/Articles
language: auto            # auto | en | de | fr
remove_bibliography: true
remove_urls: true
remove_citations: true
expand_abbreviations: true
custom_abbreviations:
  GDPR: General Data Protection Regulation
  DS-GVO: Datenschutz-Grundverordnung
```

Pass it with `--config my-config.yaml`.

## Processing Pipeline

```
Input (PDF/Word)
      │
      ▼
1. Extract text         (pymupdf / python-docx)
2. Dehyphenate          (rejoin line-break-split words)
3. Detect language      (auto EN/DE/FR)
4. Remove clutter       (bibliography, page numbers, URLs, citations)
5. Extract footnotes    (strip markers, keep content for Notes section)
6. Expand abbreviations (Art. → Article, § → Section, CJEU → ...)
7. Normalize            (dates, dashes, case citations, tables)
8. Extract tags         (keyword-based for Obsidian frontmatter)
9. Write .md            (YAML frontmatter + body + Notes)
      │
      ▼
Output: ~/Obsidian/Articles/article-title.md
```

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Tech Stack

- **Python 3.11+**
- **PyMuPDF** — PDF text extraction
- **python-docx** — Word document extraction
- **langdetect** — language detection
- **click** — CLI framework
- **PyYAML** — configuration

## License

MIT
