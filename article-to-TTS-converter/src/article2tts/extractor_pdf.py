"""Extract text and metadata from PDF files using PyMuPDF."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz  # pymupdf


@dataclass
class ExtractionResult:
    """Result of extracting text from a document."""
    body: str
    footnotes: list[str] = field(default_factory=list)
    title: str = ""
    author: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


def extract_pdf(path: str | Path) -> ExtractionResult:
    """Extract text, footnotes, and metadata from a PDF file.

    Uses PyMuPDF for layout-aware extraction.  Footnotes are identified
    heuristically: text blocks in the bottom portion of a page that start
    with a superscript number are treated as footnotes.
    """
    doc = fitz.open(str(path))

    meta = doc.metadata or {}
    title = meta.get("title", "") or ""
    author = meta.get("author", "") or ""

    body_parts: list[str] = []
    footnotes: list[str] = []

    for page in doc:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        page_height = page.rect.height
        # Threshold: blocks in the bottom 20% are footnote candidates
        footnote_y_threshold = page_height * 0.80

        page_body: list[str] = []
        page_footnotes: list[str] = []

        for block in blocks:
            if block["type"] != 0:  # skip images
                continue

            block_text = ""
            block_top = block["bbox"][1]

            for line in block["lines"]:
                spans_text = "".join(span["text"] for span in line["spans"])
                block_text += spans_text

            block_text = block_text.strip()
            if not block_text:
                continue

            # Heuristic: footnote = in lower page area and starts with digit(s)
            if block_top >= footnote_y_threshold and _looks_like_footnote(block_text):
                page_footnotes.append(block_text)
            else:
                page_body.append(block_text)

        body_parts.extend(page_body)
        footnotes.extend(page_footnotes)

    doc.close()

    # Clean up footnote numbering for consistent format
    cleaned_footnotes = _clean_footnotes(footnotes)

    return ExtractionResult(
        body="\n\n".join(body_parts),
        footnotes=cleaned_footnotes,
        title=title,
        author=author,
        metadata={k: v for k, v in meta.items() if v},
    )


def _looks_like_footnote(text: str) -> bool:
    """Check if text starts with a footnote-style number."""
    stripped = text.lstrip()
    if not stripped:
        return False
    # Matches "1 ...", "12 ...", "¹ ...", etc.
    i = 0
    superscript_digits = set("⁰¹²³⁴⁵⁶⁷⁸⁹")
    while i < len(stripped) and (stripped[i].isdigit() or stripped[i] in superscript_digits):
        i += 1
    return i > 0 and i < len(stripped)


def _clean_footnotes(footnotes: list[str]) -> list[str]:
    """Strip leading numbers from footnotes and return clean text."""
    cleaned = []
    for fn in footnotes:
        text = fn.lstrip()
        # Strip leading digits or superscript digits
        superscript_digits = set("⁰¹²³⁴⁵⁶⁷⁸⁹")
        i = 0
        while i < len(text) and (text[i].isdigit() or text[i] in superscript_digits):
            i += 1
        content = text[i:].lstrip(" .)")
        if content:
            cleaned.append(content)
    return cleaned
