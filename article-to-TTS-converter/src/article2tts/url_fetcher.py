"""Fetch PDFs from URLs found in Obsidian Markdown files."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx


# URL patterns that typically point to PDFs
_PDF_URL_PATTERNS = [
    re.compile(r"\.pdf(?:\?[^\s)]*)?$", re.IGNORECASE),
    re.compile(r"ssrn\.com/abstract=\d+", re.IGNORECASE),
    re.compile(r"papers\.ssrn\.com", re.IGNORECASE),
    re.compile(r"eur-lex\.europa\.eu.*(?:PDF|FORMAT=PDF)", re.IGNORECASE),
    re.compile(r"doi\.org/", re.IGNORECASE),
    re.compile(r"jstor\.org/stable/", re.IGNORECASE),
    re.compile(r"arxiv\.org/(?:abs|pdf)/", re.IGNORECASE),
]

# Markdown link pattern: [text](url) and bare URLs
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_BARE_URL_RE = re.compile(r"(?<!\()https?://\S+")


def extract_urls_from_markdown(md_path: str | Path) -> list[dict[str, str]]:
    """Extract URLs from an Obsidian Markdown file.

    Returns a list of dicts with 'url', 'title' (link text or ''), and 'source' keys.
    Only returns URLs that look like they point to PDFs or academic papers.
    """
    text = Path(md_path).read_text(encoding="utf-8")
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # Markdown links: [title](url)
    for match in _MD_LINK_RE.finditer(text):
        title = match.group(1).strip()
        url = match.group(2).strip()
        if url not in seen_urls and _looks_like_pdf_url(url):
            results.append({"url": url, "title": title, "source": str(md_path)})
            seen_urls.add(url)

    # Bare URLs
    for match in _BARE_URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!?)")
        if url not in seen_urls and _looks_like_pdf_url(url):
            results.append({"url": url, "title": "", "source": str(md_path)})
            seen_urls.add(url)

    return results


def download_pdf(url: str, target_dir: str | Path | None = None) -> Path:
    """Download a PDF from a URL and return the local file path.

    If the URL points to an academic repository (SSRN, arXiv, etc.),
    follows redirects to reach the actual PDF.
    """
    if target_dir is None:
        target_dir = Path(tempfile.mkdtemp(prefix="article2tts_"))
    else:
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

    url = _normalize_url(url)

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        response = client.get(url, headers=_request_headers())
        response.raise_for_status()

        # Determine filename
        filename = _filename_from_response(response, url)
        filepath = target_dir / filename

        filepath.write_bytes(response.content)

    # Verify it looks like a PDF
    header = filepath.read_bytes()[:5]
    if header != b"%PDF-":
        filepath.unlink()
        raise ValueError(f"Downloaded file from {url} is not a PDF")

    return filepath


def _looks_like_pdf_url(url: str) -> bool:
    """Check if a URL likely points to a PDF or academic paper."""
    for pattern in _PDF_URL_PATTERNS:
        if pattern.search(url):
            return True
    return False


def _normalize_url(url: str) -> str:
    """Normalize academic URLs to point to the actual PDF download."""
    # arXiv: convert abs URL to pdf URL
    url = re.sub(r"arxiv\.org/abs/", "arxiv.org/pdf/", url)

    # SSRN: ensure we hit the download endpoint
    if "ssrn.com/abstract=" in url and "download" not in url.lower():
        abstract_match = re.search(r"abstract=(\d+)", url)
        if abstract_match:
            ssrn_id = abstract_match.group(1)
            url = f"https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID{ssrn_id}.pdf?abstractid={ssrn_id}"

    return url


def _request_headers() -> dict[str, str]:
    """HTTP headers that help with academic publisher access."""
    return {
        "User-Agent": "Mozilla/5.0 (compatible; article2tts/0.1.0)",
        "Accept": "application/pdf,*/*",
    }


def _filename_from_response(response: httpx.Response, url: str) -> str:
    """Derive a filename from the HTTP response or URL."""
    # Try Content-Disposition header
    cd = response.headers.get("content-disposition", "")
    if "filename=" in cd:
        match = re.search(r'filename="?([^";\n]+)"?', cd)
        if match:
            name = match.group(1).strip()
            if name:
                return name

    # Fall back to URL path
    parsed = urlparse(str(response.url))
    path = parsed.path.rstrip("/")
    if path:
        name = Path(path).name
        if name and "." in name:
            return name

    # Last resort
    return "downloaded.pdf"
