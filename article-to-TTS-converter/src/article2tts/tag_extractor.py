"""Extract topic tags from article text for Obsidian frontmatter."""

from __future__ import annotations

import re
from collections import Counter

# Curated legal domain keywords mapped to Obsidian-friendly tag names.
# Each entry: (regex pattern, tag name).  Patterns are case-insensitive.
_LEGAL_KEYWORD_TAGS: list[tuple[str, str]] = [
    # EU law areas
    (r"\bfundamental rights?\b", "fundamental-rights"),
    (r"\bhuman rights?\b", "human-rights"),
    (r"\bfree movement\b", "free-movement"),
    (r"\binternal market\b", "internal-market"),
    (r"\bcompetition law\b", "competition-law"),
    (r"\bstate aid\b", "state-aid"),
    (r"\bdata protection\b", "data-protection"),
    (r"\bprivacy\b", "privacy"),
    (r"\benvironmental law\b", "environmental-law"),
    (r"\bconsumer protection\b", "consumer-protection"),
    (r"\btax(?:ation)? law\b", "tax-law"),
    (r"\blabou?r law\b", "labour-law"),
    (r"\bemployment law\b", "employment-law"),
    (r"\bmigration\b|asylum\b", "migration-asylum"),
    (r"\btrade(?:mark)? law\b", "trade-law"),
    (r"\bintellectual property\b", "intellectual-property"),
    (r"\bcriminal law\b", "criminal-law"),
    (r"\bconstitutional\b", "constitutional-law"),
    (r"\badministrative law\b", "administrative-law"),
    (r"\bprocedural law\b", "procedural-law"),
    (r"\bprocurement\b", "public-procurement"),
    (r"\btransport law\b", "transport-law"),
    (r"\benergy law\b", "energy-law"),
    (r"\bdigital\b.*\bmarket\b", "digital-market"),
    (r"\bartificial intelligence\b|\bAI regulation\b", "AI-regulation"),

    # Legal concepts
    (r"\bpreliminary rul(?:ing|ings|eference)\b", "preliminary-ruling"),
    (r"\bproportionality\b", "proportionality"),
    (r"\bsubsidiarity\b", "subsidiarity"),
    (r"\bdirect effect\b", "direct-effect"),
    (r"\bsupremacy\b|primacy\b", "supremacy"),
    (r"\bnon-discrimination\b|\bequal treatment\b", "non-discrimination"),
    (r"\bjudicial review\b", "judicial-review"),
    (r"\binfringement\b.*\bproceeding", "infringement-proceedings"),
    (r"\bannulment\b", "annulment"),
    (r"\bpreliminary reference\b", "preliminary-reference"),
    (r"\blegal basis\b", "legal-basis"),
    (r"\bharmoni[sz]ation\b", "harmonisation"),

    # Institutions
    (r"\bEuropean Court of Justice\b|\bEuGH\b|\bCJEU\b|\bECJ\b", "CJEU"),
    (r"\bGeneral Court\b|\bEuG\b", "General-Court"),
    (r"\bEuropean Commission\b", "European-Commission"),
    (r"\bEuropean Parliament\b", "European-Parliament"),
    (r"\bCouncil of the EU\b|\bCouncil of Ministers\b", "Council-EU"),
    (r"\bEuropean Court of Human Rights\b|\bECtHR\b|\bEGMR\b", "ECtHR"),

    # Key instruments
    (r"\bGDPR\b|\bDS-?GVO\b|\bDSGVO\b", "GDPR"),
    (r"\bCharter of Fundamental Rights\b|\bGRCh\b", "EU-Charter"),
    (r"\bBrussels Regulation\b", "Brussels-Regulation"),
    (r"\bRome Regulation\b", "Rome-Regulation"),

    # German legal terms
    (r"\bGrundrechte?\w*\b", "fundamental-rights"),
    (r"\bFreizügigkeit\b", "free-movement"),
    (r"\bBinnenmarkt\b", "internal-market"),
    (r"\bWettbewerbsrecht\b", "competition-law"),
    (r"\bBeihilfe(?:n|recht)?\b", "state-aid"),
    (r"\bDatenschutz\w*\b", "data-protection"),
    (r"\bUmweltrecht\b", "environmental-law"),
    (r"\bVerbraucherschutz\b", "consumer-protection"),
    (r"\bSteuerrecht\b", "tax-law"),
    (r"\bArbeitsrecht\b", "labour-law"),
    (r"\bVorabentscheidung\b", "preliminary-ruling"),
    (r"\bVerhältnismäßigkeit\b", "proportionality"),
    (r"\bGleichbehandlung\b|\bDiskriminierung\b", "non-discrimination"),
    (r"\bVerfassungsrecht\b", "constitutional-law"),
    (r"\bVerwaltungsrecht\b", "administrative-law"),

    # French legal terms
    (r"\bdroits fondamentaux\b", "fundamental-rights"),
    (r"\blibre circulation\b", "free-movement"),
    (r"\bmarché intérieur\b", "internal-market"),
    (r"\bdroit de la concurrence\b", "competition-law"),
    (r"\baide[s]? d'[EÉeé]tat\b", "state-aid"),
    (r"\bprotection des données\b", "data-protection"),
    (r"\brenvoi préjudiciel\b", "preliminary-ruling"),
    (r"\bproportionnalité\b", "proportionality"),
]


def extract_tags(text: str, max_tags: int = 8) -> list[str]:
    """Extract topic tags from article text.

    Uses a two-pass approach:
    1. Match against curated legal keyword dictionary (high precision)
    2. Count matches to rank by relevance, return top tags

    Returns a sorted list of Obsidian-friendly tag strings.
    """
    tag_counts: Counter[str] = Counter()

    for pattern, tag in _LEGAL_KEYWORD_TAGS:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            tag_counts[tag] += len(matches)

    # Return the most frequent tags, up to max_tags
    top_tags = [tag for tag, _ in tag_counts.most_common(max_tags)]
    return sorted(top_tags)
