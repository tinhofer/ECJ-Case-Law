"""Write Obsidian-ready Markdown files with YAML frontmatter and Notes section."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


def write_markdown(
    *,
    body: str,
    footnotes: list[str],
    title: str,
    author: str,
    language: str,
    tags: list[str],
    metadata: dict[str, str] | None = None,
    output_path: Path,
) -> Path:
    """Write a TTS-optimized Markdown file.

    Structure:
    - YAML frontmatter (title, author, date, source, converted, language, tags)
    - Body text
    - Notes section (appended footnotes)
    """
    frontmatter = _build_frontmatter(
        title=title,
        author=author,
        language=language,
        tags=tags,
        metadata=metadata or {},
    )

    parts = [frontmatter, "", body.strip()]

    if footnotes:
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append("## Notes")
        parts.append("")
        for i, fn in enumerate(footnotes, 1):
            parts.append(f"{i}. {fn}")

    content = "\n".join(parts) + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _build_frontmatter(
    *,
    title: str,
    author: str,
    language: str,
    tags: list[str],
    metadata: dict[str, str],
) -> str:
    """Build YAML frontmatter block."""
    lines = ["---"]

    if title:
        lines.append(f'title: "{_escape_yaml(title)}"')
    if author:
        lines.append(f'author: "{_escape_yaml(author)}"')

    # Use date from metadata if available
    doc_date = metadata.get("date", "")
    if doc_date:
        lines.append(f"date: {doc_date}")

    source = metadata.get("source", "")
    if source:
        lines.append(f'source: "{_escape_yaml(source)}"')

    lines.append(f"converted: {date.today().isoformat()}")
    lines.append(f"language: {language}")

    if tags:
        tag_str = ", ".join(tags)
        lines.append(f"tags: [{tag_str}]")

    lines.append("---")
    return "\n".join(lines)


def _escape_yaml(text: str) -> str:
    """Escape double quotes in YAML string values."""
    return text.replace('"', '\\"')


def generate_filename(title: str, fallback_name: str = "untitled") -> str:
    """Generate a clean filename from the article title."""
    if not title:
        return fallback_name

    # Remove non-alphanumeric characters (keep spaces and hyphens)
    name = re.sub(r"[^\w\s-]", "", title)
    # Replace spaces with hyphens
    name = re.sub(r"\s+", "-", name.strip())
    # Collapse multiple hyphens
    name = re.sub(r"-{2,}", "-", name)
    # Truncate to reasonable filename length
    name = name[:80].rstrip("-")
    return name.lower() or fallback_name
