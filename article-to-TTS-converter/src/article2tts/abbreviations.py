"""Abbreviation expansion engine for TTS-friendly text."""

from __future__ import annotations

import re

from article2tts.config import Config, load_abbreviations


def build_expansion_map(language: str, config: Config) -> dict[str, str]:
    """Build a combined abbreviation→expansion map for the given language."""
    abbrevs = load_abbreviations(language)
    # Merge custom abbreviations from config (custom overrides defaults)
    abbrevs.update(config.custom_abbreviations)
    return abbrevs


def expand_abbreviations(text: str, abbrev_map: dict[str, str]) -> str:
    """Replace abbreviations in text with their full expansions.

    Handles both symbol-style abbreviations (§, §§) and word-style ones
    (Art., e.g., TFEU).  Longer abbreviations are matched first to avoid
    partial replacements.
    """
    if not abbrev_map:
        return text

    # Sort by length descending so longer matches take priority
    # (e.g. "§§" before "§", "e.g." before "e.")
    sorted_abbrevs = sorted(abbrev_map.keys(), key=len, reverse=True)

    for abbrev in sorted_abbrevs:
        expansion = abbrev_map[abbrev]
        escaped = re.escape(abbrev)

        if abbrev in ("§", "§§"):
            # Section symbols: § 12 → "Section 12"
            text = re.sub(
                rf"{escaped}(?=\s|\d)",
                expansion,
                text,
            )
        elif abbrev[-1] == ".":
            # Abbreviations ending with a dot: match as whole token
            # Must be preceded by whitespace/start and followed by space/punctuation
            text = re.sub(
                rf"(?<![a-zA-ZäöüÄÖÜéèêàâ]){escaped}(?=\s|$|[,;:)\]])",
                expansion,
                text,
            )
        elif abbrev.isupper() and len(abbrev) >= 2:
            # Uppercase acronyms: word boundary matching
            text = re.sub(
                rf"\b{escaped}\b",
                expansion,
                text,
            )
        else:
            # Other abbreviations: word boundary matching
            text = re.sub(
                rf"\b{escaped}\b",
                expansion,
                text,
            )

    return text
