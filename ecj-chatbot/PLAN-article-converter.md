# Plan: Article-to-TTS Converter

Tool that converts academic/legal articles (PDF or Word) into clean text
optimized for text-to-speech reading tools (e.g. Aloud).

## Design Decisions (agreed)

| Decision | Choice |
|----------|--------|
| Footnotes | Remove markers from body; optionally append footnote content at end (flag) |
| Abbreviations | Dictionary-based expansion + Claude LLM fallback for ambiguous cases |
| Interface | Both: CLI tool for batch processing + Streamlit page for interactive use |

---

## Problems to Solve

### 1. Footnotes & Endnotes
- Superscript footnote markers (1, 2, 3...) interrupt sentence flow
- Footnote text at page bottom interleaved with body text in PDF extraction
- Endnote blocks are out of context
- **Solution:** Strip all markers from body text. Optionally collect footnote
  content and append as "Anmerkungen" section at end (via `--keep-footnotes` flag).

### 2. Acronyms & Abbreviations
- Legal German: EuGH, EuG, Art., Abs., Rs., Rn., Slg., ABl., RL, VO, GA,
  UAbs., lit., S., vgl., std. Rspr., m.w.N.
- Treaty/Instrument: AEUV, EUV, EMRK, GRCh, EuGVVO, DSGVO, DSA, DMA
- Academic: e.g., i.e., cf., ibid., et al., op. cit., a.a.O., Fn.
- Institutional: EU, EZB, EuGH, Kommission
- **Solution:** JSON dictionaries per language + domain. Dictionary lookup first,
  Claude API call for unresolved/ambiguous abbreviations.

### 3. Inline Citations & References
- Parenthetical: `(Muller, 2020, S. 45)`, `(see Case C-131/12, para. 42)`
- Bracketed: `[12]`, `[23, 24]`
- Cross-references: "see Section 2.3 above", "as discussed in Part III"
- **Solution:** Remove bracketed number references `[n]`. Simplify parenthetical
  citations (remove or reduce to author name only). Remove cross-references
  to sections/figures that are meaningless in audio.

### 4. PDF Layout Artifacts
- Running headers/footers on every page
- Page numbers embedded in text
- Hyphenation from line breaks: `Recht-\nsprechung` -> `Rechtsprechung`
- Column breaks splitting sentences
- Orphaned lines, widows
- **Solution:** Dehyphenation via regex. Detect and remove repeated
  headers/footers. Strip isolated page numbers. Rejoin broken sentences.

### 5. Tables & Figures
- Tables unreadable by TTS
- Figure references ("see Figure 3") point to nothing in audio
- **Solution:** Remove tables entirely. Remove figure references. Optionally
  keep figure captions as standalone sentences.

### 6. Special Characters & Symbols
- `SS` -> "Paragraph" (German legal context)
- `%` -> "Prozent" / "percent"
- `EUR`/euro sign -> "Euro"
- Em-dashes, en-dashes -> commas or periods as appropriate
- Smart quotes -> straight quotes
- Bullet points -> sentence flow
- **Solution:** Character-level replacement dictionary with context awareness.

### 7. Bibliography / Reference List
- Entire bibliography section unlistenable
- **Solution:** Detect reference section (by heading: "Literatur",
  "Bibliographie", "References", "Quellenverzeichnis") and remove entirely.

### 8. Formatting & Structure
- Section numbers ("2.3.1 Die Rechtsprechung...") verbose when read
- ALL CAPS headings may be spelled out letter-by-letter by TTS
- **Solution:** Keep headings but normalize case. Optionally prefix with
  "Abschnitt:" for orientation. Remove deep numbering.

### 9. Legal-Specific References
- `Art. 267 Abs. 3 AEUV` -> "Artikel 267 Absatz 3 des Vertrags uber die
  Arbeitsweise der Europaischen Union"
- `Rs. C-131/12` -> "Rechtssache C-131/12"
- `ABl. L 281/31` -> "Amtsblatt L 281 Seite 31"
- `Rn. 45-52` -> "Randnummern 45 bis 52"
- **Solution:** Pattern-based expansion with legal reference grammar.

### 10. Language & Encoding
- Mixed-language passages (German body with French/English case names)
- Unicode normalization (combining characters, ligatures)
- PDF encoding artifacts (fi/fl ligatures, wrong character mappings)
- **Solution:** Unicode NFKC normalization. Ligature replacement table.

---

## Architecture

```
ecj-chatbot/
  article_converter/
  +-- __init__.py
  +-- cli.py                  # CLI entry point (argparse)
  +-- converter.py            # Main pipeline orchestrator
  +-- extractors/
  |   +-- __init__.py
  |   +-- pdf_extractor.py    # PDF -> raw structured text (pymupdf)
  |   +-- docx_extractor.py   # DOCX -> raw structured text (python-docx)
  +-- cleaners/
  |   +-- __init__.py
  |   +-- footnotes.py        # Remove/collect footnote markers + text
  |   +-- citations.py        # Remove/simplify inline citations
  |   +-- layout.py           # Dehyphenation, headers/footers, page numbers
  |   +-- sections.py         # Remove bibliography, normalize headings
  |   +-- tables.py           # Remove tables and figure references
  +-- expanders/
  |   +-- __init__.py
  |   +-- abbreviations.py    # Dictionary + LLM expansion of abbreviations
  |   +-- symbols.py          # SS -> Paragraph, % -> Prozent, etc.
  |   +-- legal_refs.py       # Expand Art./Abs./Rs./Rn./ABl. patterns
  +-- dictionaries/
  |   +-- legal_abbrev_de.json    # German legal abbreviations
  |   +-- legal_abbrev_en.json    # English legal abbreviations
  |   +-- academic_abbrev.json    # General academic abbreviations
  |   +-- symbols.json            # Symbol -> word mappings
  +-- tests/
      +-- __init__.py
      +-- test_converter.py       # Integration tests for full pipeline
      +-- test_extractors.py      # Unit tests for PDF/DOCX extraction
      +-- test_cleaners.py        # Unit tests for each cleaner
      +-- test_expanders.py       # Unit tests for each expander
      +-- fixtures/               # Sample PDF/DOCX files for testing
```

---

## Processing Pipeline

Order matters - each step assumes the previous one has run:

```
Input (PDF/DOCX)
  |
  v
1. EXTRACT -----------> Raw text with structural metadata
  |                     (footnotes separated, headings tagged)
  v
2. FIX LAYOUT --------> Dehyphenate, remove headers/footers/page numbers
  |
  v
3. REMOVE FOOTNOTES --> Strip markers from body; optionally collect content
  |
  v
4. REMOVE BIBLIOGRAPHY -> Detect and strip reference section
  |
  v
5. CLEAN CITATIONS ---> Remove [n] references, simplify (Author, Year)
  |
  v
6. REMOVE TABLES -----> Strip tables, figure refs; keep captions optionally
  |
  v
7. EXPAND ABBREVIATIONS -> Dictionary lookup + Claude fallback
  |
  v
8. EXPAND SYMBOLS -----> SS -> Paragraph, % -> Prozent, etc.
  |
  v
9. EXPAND LEGAL REFS --> Art. 267 Abs. 3 AEUV -> full readable form
  |
  v
10. NORMALIZE ---------> Whitespace, punctuation, heading case
  |
  v
Output (.txt)
  + optional appended footnotes section
```

---

## Interfaces

### CLI

```bash
# Basic usage
python -m article_converter input.pdf -o output.txt

# With options
python -m article_converter input.docx \
  --output output.txt \
  --keep-footnotes \          # Append footnotes at end
  --language de \             # Primary language (for abbreviation dicts)
  --no-llm                   # Skip Claude fallback, dictionary only
```

### Streamlit Page

- New page in existing Streamlit app (or tab)
- Drag-and-drop file upload (PDF/DOCX)
- Checkboxes for options (keep footnotes, language, LLM expansion)
- Preview of converted text
- Download button for .txt output
- Processing log showing what was removed/expanded

---

## Dependencies (new, to add to requirements.txt)

```
pymupdf>=1.24.0          # PDF extraction (aka fitz)
python-docx>=1.1.0       # DOCX extraction
```

No other new dependencies needed. The project already has `anthropic` for
Claude API calls, and all text processing uses Python stdlib (re, json, etc.).

---

## Implementation Order

1. **Dictionaries first** - Build abbreviation/symbol JSON files (foundation
   for everything else, easy to review and extend)
2. **Extractors** - PDF and DOCX to structured text (needed for all testing)
3. **Layout cleaner** - Dehyphenation, headers/footers (fixes raw extraction)
4. **Footnote cleaner** - Core requirement
5. **Citation cleaner** - High impact for listening experience
6. **Section cleaner** - Bibliography removal, heading normalization
7. **Table cleaner** - Remove tables/figures
8. **Symbol expander** - Simple character replacement
9. **Legal reference expander** - Pattern-based, legal-specific
10. **Abbreviation expander** - Dictionary + LLM integration
11. **Converter pipeline** - Wire everything together
12. **CLI** - Command-line interface
13. **Tests** - Unit + integration tests with fixture files
14. **Streamlit page** - Interactive UI

---

## Open Questions for Later

- Should the tool detect the article language automatically, or always require
  it as input?
- Should there be a "verbose" mode that logs every transformation for debugging?
- How to handle multi-column PDFs (common in journals)?
  pymupdf can handle this but may need column detection logic.
- Should the tool preserve paragraph structure (double newlines) for readability
  of the output file, or produce a single continuous text block?
