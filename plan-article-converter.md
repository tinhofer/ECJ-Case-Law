# Plan: article-to-TTS-converter

## Goal

A CLI tool (Python) that converts academic/legal articles (PDF or Word) into clean Markdown files optimized for text-to-speech (TTS) tools like Aloud, stored in Obsidian.

---

## 1. New Repository Setup

- Repo: `tinhofer/article-to-TTS-converter`
- Description: *"Converts academic articles (PDF/Word) to TTS-friendly Markdown for Obsidian — strips footnotes, expands abbreviations, and normalizes text for read-aloud tools."*
- Python project with `pyproject.toml`, MIT license
- CLI entry point (e.g. `article2tts input.pdf -o ~/Obsidian/Articles/`)

---

## 2. Input Handling

| Format | Library |
|--------|---------|
| PDF | `pymupdf` (PyMuPDF) — fast, layout-aware text extraction |
| Word (.docx) | `python-docx` — native paragraph/style access |

Auto-detect format by file extension.

---

## 3. What to Remove / Transform

### 3.1 Remove entirely
- **Footnotes and endnotes** (both numbered and symbolic)
- **Footnote reference markers** in body text (superscript numbers like ¹²³)
- **Page numbers**, running headers/footers
- **Table of contents**
- **Bibliography / references section** at the end
- **Figure/table numbering and captions** (e.g. "Figure 3: …")
- **In-text cross-references** like "(see Figure 3)" or "(see fn. 12)" — remove the parenthetical
- **URLs and DOIs** — TTS would spell them out character by character
- **Line numbers** (common in legal drafts)

### 3.2 Expand abbreviations → full words
A configurable dictionary, at minimum covering:

| Abbreviation | Expansion |
|---|---|
| Art. | Article |
| para. / Abs. | paragraph / Absatz |
| cf. | compare |
| e.g. | for example |
| i.e. | that is |
| et al. | and others |
| ibid. | same source |
| no. / Nr. | number / Nummer |
| ed. / Hrsg. | editor / Herausgeber |
| vol. | volume |
| p. / pp. / S. | page / pages / Seite |
| § / §§ | Section / Sections |
| fn. | footnote |
| Rn. / Rz. | Randnummer |
| EuGH | Europäischer Gerichtshof |
| ECJ / CJEU | European Court of Justice |
| AG | Advocate General |
| EU | European Union |
| TFEU / AEUV | Treaty on the Functioning of the European Union / Vertrag über die Arbeitsweise der Europäischen Union |
| TEU / EUV | Treaty on European Union / Vertrag über die Europäische Union |
| ECHR / EMRK | European Convention on Human Rights / Europäische Menschenrechtskonvention |

User-extensible via a YAML/JSON config file.

### 3.3 Normalize for natural speech
- **Case citations** like `C-123/45` → "Case C 123 slash 45" (or configurable)
- **Section symbols**: `§ 12` → "Section 12"
- **Roman numerals** in headings → Arabic (e.g. "III." → "3.")
- **Ordinals**: 1st, 2nd, 3rd → leave as-is (TTS handles these)
- **Dates**: normalize to spoken form if needed (e.g. "12.03.2024" → "12 March 2024")
- **Dehyphenation**: rejoin words split across line breaks ("juris-\nprudence" → "jurisprudence")
- **Whitespace normalization**: collapse multiple spaces, fix broken paragraphs
- **Em/en dashes**: `—` / `–` → " — " (with spaces, so TTS pauses)
- **Parenthetical citations** like `(Smith 2020, p. 45)` → remove entirely
- **Quoted text**: keep the quote, optionally add "quote" / "end quote" markers

### 3.4 Structural cleanup
- **Tables** → linearize into prose or bulleted lists
- **Headings** → preserve as Markdown headings (`##`, `###`) — TTS tools use these as chapter markers
- **Lists** → preserve as Markdown lists
- **Bold/italic** → strip (no audible effect, clutters the .md less)
- **Images** → remove entirely

---

## 4. Output: Obsidian-Ready Markdown

```markdown
---
title: "Original Article Title"
author: "Author Name(s)"
date: 2024-03-15
source: "Journal Name, Vol. X"
converted: 2026-02-24
language: en
---

# Original Article Title

[Clean, TTS-optimized body text here...]
```

- YAML frontmatter for Obsidian metadata/search
- Single `.md` file per article
- UTF-8, no special characters that confuse TTS
- Configurable output directory (default: current dir)

---

## 5. Language Detection

- Auto-detect language using `langdetect` or similar
- Load the matching abbreviation dictionary (EN, DE, FR)
- Store detected language in frontmatter

---

## 6. Configuration

A `config.yaml` (user-editable, bundled defaults):

```yaml
output_dir: ~/Obsidian/Articles
language: auto            # auto | en | de | fr
remove_bibliography: true
remove_footnotes: true
remove_urls: true
remove_citations: true    # parenthetical citations like (Smith 2020)
expand_abbreviations: true
custom_abbreviations:     # user additions
  GDPR: General Data Protection Regulation
  DS-GVO: Datenschutz-Grundverordnung
```

---

## 7. Project Structure

```
article-to-TTS-converter/
├── src/
│   └── article2tts/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point (click/argparse)
│       ├── extractor_pdf.py    # PDF text extraction
│       ├── extractor_docx.py   # Word text extraction
│       ├── cleaner.py          # Footnote/citation/URL removal
│       ├── abbreviations.py    # Abbreviation expansion engine
│       ├── normalizer.py       # Dehyphenation, whitespace, dates, symbols
│       ├── markdown_writer.py  # Obsidian-ready .md output
│       └── config.py           # Config loading
├── config/
│   ├── default.yaml            # Default settings
│   ├── abbreviations_en.yaml   # English abbreviation dictionary
│   ├── abbreviations_de.yaml   # German abbreviation dictionary
│   └── abbreviations_fr.yaml   # French abbreviation dictionary
├── tests/
├── pyproject.toml
├── README.md
└── LICENSE
```

---

## 8. Processing Pipeline

```
Input (PDF/Word)
      │
      ▼
┌─────────────────┐
│  1. Extract      │  pymupdf / python-docx
│     raw text     │  (preserve paragraph structure)
├─────────────────┤
│  2. Dehyphenate  │  rejoin line-break-split words
├─────────────────┤
│  3. Detect       │  langdetect → pick abbreviation dict
│     language     │
├─────────────────┤
│  4. Remove       │  footnotes, bibliography, page numbers,
│     clutter      │  TOC, figure refs, URLs, citations
├─────────────────┤
│  5. Expand       │  abbreviations, symbols, case refs
│     abbreviations│
├─────────────────┤
│  6. Normalize    │  whitespace, dashes, dates, tables
├─────────────────┤
│  7. Write .md    │  YAML frontmatter + clean body
└─────────────────┘
      │
      ▼
Output: ~/Obsidian/Articles/article-title.md
```

---

## 9. CLI Usage

```bash
# Single file
article2tts paper.pdf

# Specify output directory
article2tts paper.pdf -o ~/Obsidian/Articles/

# Word document, German forced
article2tts aufsatz.docx --lang de

# Custom config
article2tts paper.pdf --config my-config.yaml

# Keep footnotes inline (instead of removing)
article2tts paper.pdf --keep-footnotes
```

---

## 10. Dependencies

- `pymupdf` — PDF extraction
- `python-docx` — Word extraction
- `langdetect` — language detection
- `click` — CLI framework
- `pyyaml` — config files
- `pytest` — testing

---

## 11. Open Questions for Discussion

1. **Footnotes: remove or inline?** Default is remove, but `--keep-footnotes` could inline them in parentheses. Which do you prefer as default?
2. **Parenthetical citations**: Remove `(Smith 2020)` entirely, or keep author name and remove year/page?
3. **Case citations**: `C-123/45` — spell out as "Case C 123 slash 45", or just "Case C-123/45" and let TTS handle it?
4. **Batch mode**: Process an entire folder of PDFs at once? (Easy to add.)
5. **Obsidian tags**: Auto-generate tags from keywords? (e.g. `tags: [EU-law, CJEU, fundamental-rights]`)
