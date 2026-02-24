"""CLI entry point for article2tts."""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import click

from article2tts.abbreviations import build_expansion_map, expand_abbreviations
from article2tts.cleaner import clean_all
from article2tts.config import Config
from article2tts.extractor_docx import extract_docx
from article2tts.extractor_pdf import ExtractionResult, extract_pdf
from article2tts.markdown_writer import generate_filename, write_markdown
from article2tts.normalizer import normalize_all
from article2tts.tag_extractor import extract_tags

_SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


@click.command()
@click.argument("input_path", nargs=-1, required=True)
@click.option(
    "-o", "--output-dir",
    default=None,
    help="Output directory for .md files (default: current dir or config value).",
)
@click.option(
    "--lang",
    default=None,
    help="Force language (en/de/fr). Default: auto-detect.",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(exists=True),
    help="Path to custom config.yaml.",
)
def main(
    input_path: tuple[str, ...],
    output_dir: str | None,
    lang: str | None,
    config_path: str | None,
) -> None:
    """Convert academic articles (PDF/Word) to TTS-friendly Markdown.

    INPUT_PATH can be one or more files, a directory, or a glob pattern.

    \b
    Examples:
        article2tts paper.pdf
        article2tts paper.pdf -o ~/Obsidian/Articles/
        article2tts ~/Downloads/papers/
        article2tts ~/Downloads/papers/*.pdf
    """
    cfg = Config.load(config_path)

    if output_dir:
        cfg.output_dir = str(Path(output_dir).expanduser())

    # Resolve input paths: expand directories and globs
    files = _resolve_inputs(input_path)
    if not files:
        click.echo("No supported files found (.pdf, .docx).", err=True)
        sys.exit(1)

    click.echo(f"Converting {len(files)} file(s)...")

    success = 0
    for file_path in files:
        try:
            out = convert_file(file_path, cfg, forced_language=lang)
            click.echo(f"  OK: {file_path.name} -> {out.name}")
            success += 1
        except Exception as e:
            click.echo(f"  FAIL: {file_path.name}: {e}", err=True)

    click.echo(f"\nDone. {success}/{len(files)} converted.")


def convert_file(
    file_path: Path,
    cfg: Config,
    *,
    forced_language: str | None = None,
) -> Path:
    """Run the full conversion pipeline on a single file."""

    # 1. Extract raw text
    result = _extract(file_path)

    # 2. Detect language
    language = forced_language or cfg.language
    if language == "auto":
        language = _detect_language(result.body)

    # 3. Clean: remove clutter
    body = clean_all(
        result.body,
        remove_bib=cfg.remove_bibliography,
        remove_urls=cfg.remove_urls,
        remove_cites=cfg.remove_citations,
    )

    # 4. Expand abbreviations
    if cfg.expand_abbreviations:
        abbrev_map = build_expansion_map(language, cfg)
        body = expand_abbreviations(body, abbrev_map)
        # Also expand abbreviations in footnotes
        result.footnotes = [expand_abbreviations(fn, abbrev_map) for fn in result.footnotes]

    # 5. Normalize for TTS
    body = normalize_all(body, language)
    result.footnotes = [normalize_all(fn, language) for fn in result.footnotes]

    # 6. Extract tags
    tags = extract_tags(body)

    # 7. Write markdown
    title = result.title or _title_from_filename(file_path)
    filename = generate_filename(title, fallback_name=file_path.stem)
    output_path = Path(cfg.output_dir) / f"{filename}.md"

    write_markdown(
        body=body,
        footnotes=result.footnotes,
        title=title,
        author=result.author,
        language=language,
        tags=tags,
        metadata=result.metadata,
        output_path=output_path,
    )

    return output_path


def _extract(file_path: Path) -> ExtractionResult:
    """Extract text based on file extension."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(file_path)
    elif ext == ".docx":
        return extract_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _detect_language(text: str) -> str:
    """Detect the language of the text."""
    try:
        from langdetect import detect
        lang = detect(text[:5000])  # sample first 5000 chars
        # Map to our supported codes
        if lang.startswith("de"):
            return "de"
        elif lang.startswith("fr"):
            return "fr"
        else:
            return "en"
    except Exception:
        return "en"


def _title_from_filename(path: Path) -> str:
    """Derive a title from the filename when metadata is missing."""
    return path.stem.replace("-", " ").replace("_", " ").title()


def _resolve_inputs(paths: tuple[str, ...]) -> list[Path]:
    """Resolve input paths to a flat list of supported files."""
    files: list[Path] = []
    for pattern in paths:
        p = Path(pattern).expanduser()
        if p.is_dir():
            # All supported files in directory
            for ext in _SUPPORTED_EXTENSIONS:
                files.extend(sorted(p.glob(f"*{ext}")))
        elif p.exists() and p.suffix.lower() in _SUPPORTED_EXTENSIONS:
            files.append(p)
        else:
            # Try glob expansion
            expanded = glob.glob(pattern)
            for f in sorted(expanded):
                fp = Path(f)
                if fp.suffix.lower() in _SUPPORTED_EXTENSIONS:
                    files.append(fp)
    return files


if __name__ == "__main__":
    main()
