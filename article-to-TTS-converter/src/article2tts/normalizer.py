"""Text normalization for TTS: dehyphenation, whitespace, dates, symbols."""

from __future__ import annotations

import re

# Roman numeral pattern (I through XXXIX covers most heading usage)
_ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
    "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19,
    "XX": 20, "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25,
    "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29, "XXX": 30,
}

_MONTH_NAMES = {
    "en": {
        1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
        6: "June", 7: "July", 8: "August", 9: "September", 10: "October",
        11: "November", 12: "December",
    },
    "de": {
        1: "Jänner", 2: "Februar", 3: "März", 4: "April", 5: "Mai",
        6: "Juni", 7: "Juli", 8: "August", 9: "September", 10: "Oktober",
        11: "November", 12: "Dezember",
    },
    "fr": {
        1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai",
        6: "juin", 7: "juillet", 8: "août", 9: "septembre", 10: "octobre",
        11: "novembre", 12: "décembre",
    },
}


def dehyphenate(text: str) -> str:
    """Rejoin words split across line breaks: 'juris-\\nprudence' → 'jurisprudence'."""
    # Hyphen at end of line followed by a lowercase letter on next line
    text = re.sub(r"(\w)-\s*\n\s*([a-zäöüéèêàâ])", r"\1\2", text)
    return text


def normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces and blank lines."""
    # Replace multiple spaces (but not newlines) with single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace per line
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


def normalize_dashes(text: str) -> str:
    """Ensure em/en dashes have surrounding spaces for TTS pauses."""
    # Em dash
    text = re.sub(r"\s*—\s*", " — ", text)
    # En dash (but not in number ranges like 2020–2023)
    text = re.sub(r"(?<!\d)\s*–\s*(?!\d)", " — ", text)
    return text


def spell_out_case_citations(text: str) -> str:
    """Spell out ECJ case citations for TTS.

    C-123/45 → 'Case C 123 slash 45'
    T-456/78 → 'Case T 456 slash 78'
    C-123/45 P → 'Case C 123 slash 45 P'
    """
    def _replace_case(m: re.Match) -> str:
        prefix = m.group(1)  # C or T or F
        num1 = m.group(2)
        num2 = m.group(3)
        suffix = m.group(4) or ""
        result = f"Case {prefix} {num1} slash {num2}"
        if suffix.strip():
            result += f" {suffix.strip()}"
        return result

    text = re.sub(
        r"\b([CTF])-(\d+)/(\d+)(?:\s+([A-Z]{1,2})\b)?",
        _replace_case,
        text,
    )
    return text


def roman_to_arabic_in_headings(text: str) -> str:
    """Convert Roman numerals in headings to Arabic numerals.

    'III. Some Heading' → '3. Some Heading'
    '## IV. Title' → '## 4. Title'
    """
    def _replace_roman(m: re.Match) -> str:
        prefix = m.group(1) or ""  # markdown heading prefix
        roman = m.group(2)
        rest = m.group(3)
        arabic = _ROMAN_MAP.get(roman)
        if arabic is not None:
            return f"{prefix}{arabic}.{rest}"
        return m.group(0)

    text = re.sub(
        r"^(#{1,6}\s+)?([IVXL]+)\.(\s+.*)$",
        _replace_roman,
        text,
        flags=re.MULTILINE,
    )
    return text


def normalize_dates(text: str, language: str = "en") -> str:
    """Convert date formats to spoken form.

    '12.03.2024' → '12 March 2024' (or localized)
    """
    months = _MONTH_NAMES.get(language, _MONTH_NAMES["en"])

    def _replace_date(m: re.Match) -> str:
        day = int(m.group(1))
        month = int(m.group(2))
        year = m.group(3)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{day} {months[month]} {year}"
        return m.group(0)

    # dd.mm.yyyy format
    text = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", _replace_date, text)
    return text


def linearize_tables(text: str) -> str:
    """Convert simple markdown-style tables to bulleted lists.

    Detects table blocks (lines with | separators) and converts them
    to a readable bulleted list format.
    """
    lines = text.split("\n")
    result: list[str] = []
    table_lines: list[str] = []

    def _flush_table() -> None:
        if not table_lines:
            return
        # Parse header and data rows
        rows = [
            [cell.strip() for cell in line.strip("|").split("|")]
            for line in table_lines
            if not re.match(r"^\|?\s*[-:]+", line)  # skip separator rows
        ]
        if len(rows) < 2:
            # Not a real table, keep as-is
            result.extend(table_lines)
            return
        headers = rows[0]
        for row in rows[1:]:
            parts = []
            for i, cell in enumerate(row):
                if i < len(headers) and headers[i] and cell:
                    parts.append(f"{headers[i]}: {cell}")
                elif cell:
                    parts.append(cell)
            if parts:
                result.append(f"- {'; '.join(parts)}")
        table_lines.clear()

    for line in lines:
        if "|" in line and line.strip().startswith("|"):
            table_lines.append(line)
        else:
            _flush_table()
            result.append(line)
    _flush_table()

    return "\n".join(result)


def strip_bold_italic(text: str) -> str:
    """Remove markdown bold/italic markers (no audible effect in TTS)."""
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    return text


def normalize_all(text: str, language: str = "en") -> str:
    """Apply all normalization steps."""
    text = dehyphenate(text)
    text = normalize_dashes(text)
    text = spell_out_case_citations(text)
    text = roman_to_arabic_in_headings(text)
    text = normalize_dates(text, language)
    text = linearize_tables(text)
    text = strip_bold_italic(text)
    text = normalize_whitespace(text)
    return text
