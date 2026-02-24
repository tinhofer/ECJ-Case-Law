"""Extract text and metadata from Word (.docx) files."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from article2tts.extractor_pdf import ExtractionResult


def extract_docx(path: str | Path) -> ExtractionResult:
    """Extract text, footnotes, and metadata from a .docx file.

    Uses python-docx for native access to paragraphs, styles, and
    footnotes/endnotes.
    """
    doc = Document(str(path))

    # --- Metadata from core properties ---
    props = doc.core_properties
    title = props.title or ""
    author = props.author or ""
    metadata: dict[str, str] = {}
    if title:
        metadata["title"] = title
    if author:
        metadata["author"] = author
    if props.created:
        metadata["date"] = str(props.created.date())

    # --- Body text ---
    body_parts: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name or "").lower()
        # Preserve headings with markdown markers
        if style_name.startswith("heading"):
            level = _heading_level(style_name)
            body_parts.append(f"{'#' * level} {text}")
        else:
            body_parts.append(text)

    # --- Footnotes ---
    footnotes = _extract_footnotes(doc)

    # --- Endnotes ---
    endnotes = _extract_endnotes(doc)

    return ExtractionResult(
        body="\n\n".join(body_parts),
        footnotes=footnotes + endnotes,
        title=title,
        author=author,
        metadata=metadata,
    )


def _heading_level(style_name: str) -> int:
    """Extract heading level from style name like 'heading 2'."""
    for part in style_name.split():
        if part.isdigit():
            return min(int(part), 6)
    return 1


def _extract_footnotes(doc: Document) -> list[str]:
    """Extract footnote text from the document's footnotes part."""
    footnotes: list[str] = []
    try:
        footnotes_part = doc.part.rels.get(
            next(
                (rel_id for rel_id, rel in doc.part.rels.items()
                 if "footnotes" in rel.reltype),
                None,
            )
        )
        if footnotes_part is None:
            return []

        from docx.oxml.ns import qn
        import lxml.etree as etree

        root = footnotes_part.target_part.element
        for fn_elem in root.findall(qn("w:footnote")):
            fn_type = fn_elem.get(qn("w:type"), "")
            if fn_type in ("separator", "continuationSeparator"):
                continue
            texts = []
            for p in fn_elem.findall(f".//{qn('w:t')}"):
                if p.text:
                    texts.append(p.text)
            content = "".join(texts).strip()
            if content:
                # Strip leading footnote number
                content = _strip_leading_number(content)
                if content:
                    footnotes.append(content)
    except (StopIteration, AttributeError, KeyError):
        pass
    return footnotes


def _extract_endnotes(doc: Document) -> list[str]:
    """Extract endnote text from the document's endnotes part."""
    endnotes: list[str] = []
    try:
        endnotes_part = doc.part.rels.get(
            next(
                (rel_id for rel_id, rel in doc.part.rels.items()
                 if "endnotes" in rel.reltype),
                None,
            )
        )
        if endnotes_part is None:
            return []

        from docx.oxml.ns import qn

        root = endnotes_part.target_part.element
        for en_elem in root.findall(qn("w:endnote")):
            en_type = en_elem.get(qn("w:type"), "")
            if en_type in ("separator", "continuationSeparator"):
                continue
            texts = []
            for p in en_elem.findall(f".//{qn('w:t')}"):
                if p.text:
                    texts.append(p.text)
            content = "".join(texts).strip()
            if content:
                content = _strip_leading_number(content)
                if content:
                    endnotes.append(content)
    except (StopIteration, AttributeError, KeyError):
        pass
    return endnotes


def _strip_leading_number(text: str) -> str:
    """Strip a leading footnote/endnote number from text."""
    i = 0
    superscript_digits = set("⁰¹²³⁴⁵⁶⁷⁸⁹")
    while i < len(text) and (text[i].isdigit() or text[i] in superscript_digits):
        i += 1
    return text[i:].lstrip(" .)")
