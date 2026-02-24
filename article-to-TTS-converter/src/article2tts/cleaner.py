"""Remove clutter from extracted text: citations, URLs, bibliography, etc."""

from __future__ import annotations

import re


def remove_footnote_markers(text: str) -> str:
    """Remove superscript footnote reference numbers from body text.

    Matches superscript Unicode digits (¹²³…) and regular digits that appear
    as inline references (e.g. a digit immediately after a word with no space).
    """
    # Remove Unicode superscript digits
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", text)
    # Remove regular digits used as superscript refs: word immediately followed
    # by 1-3 digits with no space (e.g. "court12" or "ruling3")
    # But avoid removing digits that are part of normal text (years, article numbers)
    text = re.sub(r"(?<=\w)(\d{1,3})(?=[\s,.\);:!?]|$)", _remove_if_superscript_ref, text)
    return text


def _remove_if_superscript_ref(match: re.Match) -> str:
    """Only remove numbers that look like footnote refs (small numbers after words)."""
    num = int(match.group(1))
    # Footnote refs are typically 1-999; skip if preceded by common patterns
    # that use numbers legitimately (Article 12, paragraph 3, etc.)
    return "" if num < 200 else match.group(0)


def remove_parenthetical_citations(text: str) -> str:
    """Remove parenthetical academic citations like (Smith 2020, p. 45).

    Patterns matched:
    - (Author 2020)
    - (Author 2020, p. 45)
    - (Author and Other 2019; Third 2021)
    - (see Author 2020)
    """
    # Match parenthetical with author-year pattern
    text = re.sub(
        r"\("
        r"(?:see\s+|See\s+|cf\.?\s*|Cf\.?\s*)?"
        r"[A-Z][a-zäöüéèê]+(?:\s+(?:and|&|und|et)\s+[A-Z][a-zäöüéèê]+)*"
        r"(?:\s+et\s+al\.?)?"
        r"\s*(?:19|20)\d{2}[a-z]?"
        r"(?:\s*[,;]\s*(?:p\.?\s*\d+(?:\s*[-–]\s*\d+)?|"
        r"[A-Z][a-zäöüéèê]+(?:\s+(?:and|&|und|et)\s+[A-Z][a-zäöüéèê]+)*"
        r"(?:\s+et\s+al\.?)?"
        r"\s*(?:19|20)\d{2}[a-z]?"
        r"(?:\s*,\s*p\.?\s*\d+(?:\s*[-–]\s*\d+)?)?))*"
        r"\)",
        "",
        text,
    )
    return text


def remove_urls_and_dois(text: str) -> str:
    """Remove URLs and DOIs from text."""
    # URLs
    text = re.sub(r"https?://\S+", "", text)
    # DOIs
    text = re.sub(r"doi:\s*\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"10\.\d{4,}/\S+", "", text)
    return text


def remove_cross_references(text: str) -> str:
    """Remove in-text cross-references like (see Figure 3) or (see fn. 12)."""
    text = re.sub(
        r"\(\s*(?:[Ss]ee|[Cc]f\.?|[Ss]iehe|[Vv]gl\.?)\s+"
        r"(?:[Ff]igure|[Ff]ig\.|[Tt]able|[Ff]n\.|[Ff]ootnote|[Nn]ote|"
        r"[Aa]bbildung|[Tt]abelle|[Ff]ußnote|[Ss]ection|[Ss]ec\.|[Cc]hapter|[Cc]h\.)"
        r"\s*\d+[a-z]?"
        r"\)",
        "",
        text,
    )
    return text


def remove_figure_captions(text: str) -> str:
    """Remove figure/table captions like 'Figure 3: Description here'."""
    text = re.sub(
        r"^(?:Figure|Fig\.|Table|Tab\.|Abbildung|Abb\.|Tabelle)\s*\d+\s*[:.].*$",
        "",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    return text


def remove_bibliography(text: str) -> str:
    """Remove the bibliography/references section at the end of the document."""
    # Find the last occurrence of a bibliography heading
    patterns = [
        r"^#{0,3}\s*(?:Bibliography|References|Literature|Works Cited|"
        r"Literaturverzeichnis|Literatur|Quellenverzeichnis|"
        r"Bibliographie|Références)\s*$",
    ]
    for pattern in patterns:
        match = None
        for m in re.finditer(pattern, text, flags=re.MULTILINE | re.IGNORECASE):
            match = m  # keep the last match
        if match:
            text = text[: match.start()].rstrip()
            break
    return text


def remove_table_of_contents(text: str) -> str:
    """Remove table of contents section."""
    patterns = [
        r"^#{0,3}\s*(?:Table of Contents|Contents|Inhaltsverzeichnis|"
        r"Table des matières|Sommaire)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if match:
            # Remove from heading until the next heading or double newline block
            rest = text[match.end():]
            # Find next proper heading (## or line that doesn't look like a TOC entry)
            next_section = re.search(r"^#{1,6}\s+\S", rest, flags=re.MULTILINE)
            if next_section:
                text = text[: match.start()].rstrip() + "\n\n" + rest[next_section.start():]
            else:
                text = text[: match.start()].rstrip()
            break
    return text


def remove_page_numbers(text: str) -> str:
    """Remove standalone page numbers (lines that are just a number)."""
    text = re.sub(r"^\s*-?\s*\d{1,4}\s*-?\s*$", "", text, flags=re.MULTILINE)
    return text


def remove_line_numbers(text: str) -> str:
    """Remove line numbers at the start of lines (common in legal drafts)."""
    text = re.sub(r"^\s*\d{1,4}\s{2,}", "", text, flags=re.MULTILINE)
    return text


def clean_all(text: str, *, remove_bib: bool = True, remove_urls: bool = True,
              remove_cites: bool = True) -> str:
    """Apply all cleaning steps to the text."""
    text = remove_footnote_markers(text)
    text = remove_page_numbers(text)
    text = remove_line_numbers(text)
    text = remove_table_of_contents(text)
    text = remove_figure_captions(text)
    text = remove_cross_references(text)
    if remove_urls:
        text = remove_urls_and_dois(text)
    if remove_cites:
        text = remove_parenthetical_citations(text)
    if remove_bib:
        text = remove_bibliography(text)
    return text
