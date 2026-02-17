"""
EuGH Case Law Data Acquisition Module

This module handles fetching case law data from EUR-Lex via SPARQL queries.
"""

import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator

import requests
from SPARQLWrapper import SPARQLWrapper, JSON
from tqdm import tqdm


# EUR-Lex CELLAR SPARQL Endpoint
SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

# URL templates for linking
EURLEX_URL_TEMPLATE = "https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:{celex}"
CURIA_URL_TEMPLATE = "https://curia.europa.eu/juris/liste.jsf?num={case_number}&language=de"


# Language fallback order: German preferred, then English, then French
LANGUAGE_FALLBACK = ["DE", "EN", "FR"]

# Language names for display
LANGUAGE_NAMES = {
    "DE": "Deutsch",
    "EN": "English",
    "FR": "Français"
}


@dataclass
class CaseLawDocument:
    """Represents an EuGH case law document."""
    celex: str
    title: str
    date: str
    case_number: str | None
    court: str
    document_type: str
    text: str
    eurlex_url: str
    curia_url: str | None
    ecli: str | None
    keywords: list[str]
    language: str = "DE"  # Language of the document text

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def language_name(self) -> str:
        """Get the full language name."""
        return LANGUAGE_NAMES.get(self.language, self.language)


def extract_stichwort(text: str, language: str = "DE") -> list[str]:
    """
    Extract the "Stichwort" (subject keywords) from the header of an EuGH decision.

    EuGH decisions on EUR-Lex begin with a structured header that contains
    subject keywords in quotation marks, separated by en-dashes (–).

    Examples:
        DE: „Vorlage zur Vorabentscheidung – Sozialpolitik – Gleichbehandlung – ..."
        EN: (Reference for a preliminary ruling — Social policy — Equal treatment — ...)
        FR: « Renvoi préjudiciel – Politique sociale – Égalité de traitement – ... »

    Args:
        text: Full document text
        language: Language code (DE, EN, FR)

    Returns:
        List of keyword strings extracted from the Stichwort section
    """
    if not text:
        return []

    # Search only the first portion of the text (the header)
    header = text[:3000]

    stichwort_text = None

    if language == "DE":
        # German: „..." (U+201E ... U+201C) or "..." with special quotes
        match = re.search(r'\u201e(.+?)\u201c', header, re.DOTALL)
        if not match:
            # Fallback: sometimes „..." uses different closing quote "
            match = re.search(r'\u201e(.+?)["\u201d]', header, re.DOTALL)
        if match:
            stichwort_text = match.group(1)
    elif language == "EN":
        # English: typically in parentheses after (*), or with single quotes
        match = re.search(r'\(\s*(Reference for a preliminary ruling.+?)\)', header, re.DOTALL)
        if not match:
            match = re.search(r'\u2018(.+?)\u2019', header, re.DOTALL)
        if not match:
            # Broader pattern: parenthesized text with dashes near the top
            match = re.search(r'\(\s*([A-Z][^)]*\s[\u2013\u2014–—-]\s[^)]+)\)', header, re.DOTALL)
        if match:
            stichwort_text = match.group(1)
    elif language == "FR":
        # French: « ... » (guillemets)
        match = re.search(r'\u00ab\s*(.+?)\s*\u00bb', header, re.DOTALL)
        if match:
            stichwort_text = match.group(1)

    if not stichwort_text:
        return []

    # Split by en-dash (–), em-dash (—), or regular dash surrounded by spaces
    keywords = re.split(r'\s*[\u2013\u2014–—]\s*', stichwort_text)

    # Clean up: strip whitespace, collapse internal whitespace, filter empty
    cleaned = []
    for kw in keywords:
        kw = ' '.join(kw.split()).strip()
        if kw and len(kw) > 1:
            cleaned.append(kw)

    return cleaned


def matches_subject_filter(
    keywords: list[str],
    subject_keywords: list[str]
) -> bool:
    """
    Check if a document's Stichwort keywords match any configured subject keywords.

    Uses case-insensitive substring matching so that e.g. "Gleichbehandlung"
    matches "Gleichbehandlung in Beschäftigung und Beruf".

    Args:
        keywords: Keywords extracted from the document's Stichwort
        subject_keywords: Configured subject keyword terms to match against

    Returns:
        True if at least one keyword matches a subject term
    """
    if not subject_keywords:
        return True  # No filter configured = accept all

    if not keywords:
        return False

    keywords_lower = [kw.lower() for kw in keywords]

    for subject_term in subject_keywords:
        term_lower = subject_term.lower()
        for kw in keywords_lower:
            if term_lower in kw or kw in term_lower:
                return True

    return False


def _build_sparql_query(
    limit: int = 1000,
    offset: int = 0,
    year_from: int | None = None,
    year_to: int | None = None,
    subject_areas: list[str] | None = None
) -> str:
    """Build a SPARQL query for case law metadata."""

    # Build date filter
    date_filter = ""
    if year_from:
        date_filter += f'FILTER(year(?date) >= {year_from})\n'
    if year_to:
        date_filter += f'FILTER(year(?date) <= {year_to})\n'

    # Build EuroVoc subject area filter
    subject_filter = ""
    if subject_areas:
        conditions = []
        for area in subject_areas:
            escaped = area.replace('"', '\\"')
            conditions.append(f'LCASE(STR(?eurovocLabel)) = "{escaped.lower()}"')
        subject_filter = f"""
        # Subject area filter via EuroVoc descriptors
        ?work cdm:work_is_about_concept_eurovoc ?eurovoc .
        ?eurovoc skos:prefLabel ?eurovocLabel .
        FILTER(lang(?eurovocLabel) = "en")
        FILTER({" || ".join(conditions)})
        """

    return f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT DISTINCT ?celex ?title ?date ?ecli ?caseNumber ?courtLabel ?typeLabel
    WHERE {{
        # Resource type: Case Law
        ?work a cdm:case-law .

        # CELEX number (required)
        ?work cdm:resource_legal_celex ?celex .

        # Date
        OPTIONAL {{ ?work cdm:work_date_document ?date . }}

        # Title
        OPTIONAL {{
            ?work cdm:work_title ?title .
            FILTER(lang(?title) = "de" || lang(?title) = "en")
        }}

        # ECLI
        OPTIONAL {{ ?work cdm:case-law_ecli ?ecli . }}

        # Case number
        OPTIONAL {{ ?work cdm:case-law_case_number ?caseNumber . }}

        # Court
        OPTIONAL {{
            ?work cdm:case-law_delivered_by_court ?court .
            ?court skos:prefLabel ?courtLabel .
            FILTER(lang(?courtLabel) = "en")
        }}

        # Document type
        OPTIONAL {{
            ?work cdm:resource_legal_type ?docType .
            ?docType skos:prefLabel ?typeLabel .
            FILTER(lang(?typeLabel) = "en")
        }}

        {subject_filter}
        {date_filter}
    }}
    ORDER BY DESC(?date)
    LIMIT {limit}
    OFFSET {offset}
    """


def _execute_sparql_query(query: str) -> list[dict]:
    """Execute a SPARQL query and return parsed case metadata."""
    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(120)

    try:
        results = sparql.query().convert()

        cases = []
        for binding in results["results"]["bindings"]:
            case = {
                "celex": binding.get("celex", {}).get("value", ""),
                "title": binding.get("title", {}).get("value", ""),
                "date": binding.get("date", {}).get("value", ""),
                "ecli": binding.get("ecli", {}).get("value"),
                "case_number": binding.get("caseNumber", {}).get("value"),
                "court": binding.get("courtLabel", {}).get("value", "Unknown"),
                "document_type": binding.get("typeLabel", {}).get("value", "Judgment"),
            }
            cases.append(case)

        return cases

    except Exception as e:
        print(f"SPARQL query failed: {e}")
        return []


def get_case_law_metadata(
    limit: int = 1000,
    offset: int = 0,
    year_from: int | None = None,
    year_to: int | None = None,
    court: str = "Court of Justice",
    subject_areas: list[str] | None = None
) -> list[dict]:
    """
    Fetch case law metadata from EUR-Lex via SPARQL (single page).

    If subject_areas are provided but the query returns 0 results (EuroVoc
    descriptors are often not available for case-law in CELLAR), the query
    is automatically retried without the subject area filter.

    Args:
        limit: Maximum number of results
        offset: Offset for pagination
        year_from: Filter by start year
        year_to: Filter by end year
        court: Court filter (Court of Justice, General Court, Civil Service Tribunal)
        subject_areas: Optional list of EuroVoc descriptor labels (English) to filter by.
                       Cases must have at least one matching descriptor.

    Returns:
        List of case metadata dictionaries
    """
    # Try with subject area filter first
    if subject_areas:
        query = _build_sparql_query(limit, offset, year_from, year_to, subject_areas)
        cases = _execute_sparql_query(query)
        if cases:
            return cases
        # EuroVoc descriptors are often not linked to case-law in CELLAR.
        # Fall back to querying without the subject area filter.
        print("  EuroVoc subject filter returned 0 results for case-law. "
              "Retrying without subject area filter...")

    query = _build_sparql_query(limit, offset, year_from, year_to, subject_areas=None)
    return _execute_sparql_query(query)


def get_all_case_law_metadata(
    year_from: int | None = None,
    year_to: int | None = None,
    subject_areas: list[str] | None = None,
    page_size: int = 1000
) -> list[dict]:
    """
    Fetch ALL case law metadata from EUR-Lex via paginated SPARQL queries.

    Automatically pages through all results until no more are returned.

    Args:
        year_from: Filter by start year
        year_to: Filter by end year
        subject_areas: Optional list of EuroVoc descriptor labels for SPARQL filtering
        page_size: Number of results per SPARQL query (max ~10000 for the endpoint)

    Returns:
        List of all case metadata dictionaries
    """
    all_cases = []
    offset = 0
    page = 1

    while True:
        print(f"  Fetching metadata page {page} (offset {offset})...")
        cases = get_case_law_metadata(
            limit=page_size,
            offset=offset,
            year_from=year_from,
            year_to=year_to,
            subject_areas=subject_areas
        )

        if not cases:
            break

        all_cases.extend(cases)
        print(f"    Got {len(cases)} cases (total so far: {len(all_cases)})")

        # If we got fewer results than the page size, we've reached the end
        if len(cases) < page_size:
            break

        offset += page_size
        page += 1

    # Deduplicate by CELEX number (pagination can sometimes return overlaps)
    seen = set()
    unique_cases = []
    for case in all_cases:
        celex = case.get("celex", "")
        if celex and celex not in seen:
            seen.add(celex)
            unique_cases.append(case)

    return unique_cases


def fetch_document_text(celex: str, language: str = "DE") -> str | None:
    """
    Fetch the full text of a document from EUR-Lex in a specific language.

    Args:
        celex: CELEX number of the document
        language: Language code (DE, EN, FR, etc.)

    Returns:
        Document text or None if not available
    """

    # EUR-Lex REST API for HTML content
    url = f"https://eur-lex.europa.eu/legal-content/{language}/TXT/HTML/?uri=CELEX:{celex}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Check if we got a valid document (not a "not available" page)
        if response.status_code == 404:
            return None

        # Parse HTML and extract text
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'lxml')

        # Check for "document not available" indicators
        page_text = soup.get_text()
        not_available_indicators = [
            "is not available in",
            "n'est pas disponible en",
            "ist nicht verfügbar in",
            "Document does not exist",
            "Dokument existiert nicht"
        ]
        if any(indicator in page_text for indicator in not_available_indicators):
            return None

        # Remove scripts and styles
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()

        # Get text content
        text = soup.get_text(separator='\n', strip=True)

        # Check if we got meaningful content (not just headers/navigation)
        if len(text) < 500:
            return None

        return text

    except Exception as e:
        print(f"Failed to fetch document {celex} in {language}: {e}")
        return None


def fetch_document_text_with_fallback(
    celex: str,
    languages: list[str] | None = None
) -> tuple[str | None, str]:
    """
    Fetch document text, trying multiple languages in order.

    Args:
        celex: CELEX number of the document
        languages: List of language codes to try (default: DE, EN, FR)

    Returns:
        Tuple of (text, language_code) or (None, "") if not available in any language
    """

    if languages is None:
        languages = LANGUAGE_FALLBACK

    for lang in languages:
        text = fetch_document_text(celex, lang)
        if text:
            if lang != "DE":
                print(f"  Document {celex} fetched in {LANGUAGE_NAMES.get(lang, lang)} (not available in German)")
            return text, lang

    return None, ""


def create_case_document(metadata: dict) -> CaseLawDocument | None:
    """
    Create a full CaseLawDocument from metadata by fetching the text.

    Tries to fetch the document in German first, then English, then French.
    This ensures that recent decisions not yet translated to German are still included.
    Extracts Stichwort keywords from the document header and stores them.

    Args:
        metadata: Case metadata dictionary

    Returns:
        CaseLawDocument or None if text couldn't be fetched in any language
    """

    celex = metadata.get("celex", "")
    if not celex:
        return None

    # Fetch document text with language fallback
    text, language = fetch_document_text_with_fallback(celex)
    if not text:
        return None

    # Extract Stichwort keywords from the document header
    keywords = extract_stichwort(text, language)

    # Build URLs - use the language the document was fetched in
    eurlex_url = f"https://eur-lex.europa.eu/legal-content/{language}/TXT/?uri=CELEX:{celex}"

    case_number = metadata.get("case_number")
    curia_url = None
    if case_number:
        # CURIA supports language parameter
        curia_lang = language.lower()
        curia_url = f"https://curia.europa.eu/juris/liste.jsf?num={case_number}&language={curia_lang}"

    return CaseLawDocument(
        celex=celex,
        title=metadata.get("title", ""),
        date=metadata.get("date", ""),
        case_number=case_number,
        court=metadata.get("court", "Court of Justice"),
        document_type=metadata.get("document_type", "Judgment"),
        text=text,
        eurlex_url=eurlex_url,
        curia_url=curia_url,
        ecli=metadata.get("ecli"),
        keywords=keywords,
        language=language
    )


def download_case_law_batch(
    output_dir: Path,
    year_from: int | None = None,
    year_to: int | None = None,
    delay_seconds: float = 1.0,
    subject_areas: list[str] | None = None,
    subject_keywords_de: list[str] | None = None,
    page_size: int = 1000
) -> int:
    """
    Download case law documents, paginating through ALL available results.

    Fetches all case metadata via paginated SPARQL queries, then downloads
    full texts for each case. If subject_keywords_de is provided, each
    document's Stichwort is checked and only matching documents are saved.

    Args:
        output_dir: Directory to save documents
        year_from: Filter by start year
        year_to: Filter by end year
        delay_seconds: Delay between requests to be respectful to the server
        subject_areas: Optional list of EuroVoc descriptor labels for SPARQL filtering
        subject_keywords_de: Optional list of German keywords for Stichwort-based filtering
        page_size: Number of results per SPARQL page

    Returns:
        Number of successfully downloaded documents
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching all case metadata since {year_from or 'beginning'}...")
    metadata_list = get_all_case_law_metadata(
        year_from=year_from,
        year_to=year_to,
        subject_areas=subject_areas,
        page_size=page_size
    )

    filter_info = ""
    if subject_keywords_de:
        filter_info = f" (filtering by {len(subject_keywords_de)} Stichwort keywords)"
    print(f"Found {len(metadata_list)} total cases. Downloading full texts{filter_info}...")

    downloaded = 0
    skipped = 0
    already_local = 0
    for metadata in tqdm(metadata_list, desc="Downloading"):
        celex = metadata.get("celex", "")
        if not celex:
            continue

        # Check if already downloaded
        output_file = output_dir / f"{celex.replace(':', '_')}.json"
        if output_file.exists():
            already_local += 1
            continue

        # Create document (fetches text and extracts Stichwort keywords)
        doc = create_case_document(metadata)
        if doc:
            # Apply Stichwort filter if configured
            if subject_keywords_de and not matches_subject_filter(doc.keywords, subject_keywords_de):
                skipped += 1
                continue

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(doc.to_dict(), f, ensure_ascii=False, indent=2)
            downloaded += 1

        # Respectful delay
        time.sleep(delay_seconds)

    if skipped:
        print(f"  Skipped {skipped} cases not matching subject keywords")
    if already_local:
        print(f"  {already_local} cases already downloaded")
    print(f"Downloaded {downloaded} new documents to {output_dir}")
    return downloaded + already_local


def load_documents_from_disk(data_dir: Path) -> Iterator[CaseLawDocument]:
    """
    Load previously downloaded documents from disk.

    Args:
        data_dir: Directory containing JSON documents

    Yields:
        CaseLawDocument instances
    """

    data_dir = Path(data_dir)
    for json_file in data_dir.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                yield CaseLawDocument(**data)
        except Exception as e:
            print(f"Failed to load {json_file}: {e}")


# =============================================================================
# CHECKPOINT & INCREMENTAL UPDATE SYSTEM
# =============================================================================

CHECKPOINT_FILE = "download_checkpoint.json"


def load_checkpoint(data_dir: Path) -> dict:
    """
    Load the download checkpoint from disk.

    Returns:
        Dict with 'last_download_date', 'last_celex', 'total_downloaded'
    """
    checkpoint_path = Path(data_dir) / CHECKPOINT_FILE
    if checkpoint_path.exists():
        with open(checkpoint_path, 'r') as f:
            return json.load(f)
    return {
        "last_download_date": None,
        "last_case_date": None,
        "total_downloaded": 0,
        "initial_year": None
    }


def save_checkpoint(data_dir: Path, checkpoint: dict):
    """Save the download checkpoint to disk."""
    checkpoint_path = Path(data_dir) / CHECKPOINT_FILE
    checkpoint["updated_at"] = datetime.now().isoformat()
    with open(checkpoint_path, 'w') as f:
        json.dump(checkpoint, f, indent=2)


def get_latest_case_date(data_dir: Path) -> str | None:
    """
    Get the date of the most recent case in our local data.

    Returns:
        ISO date string or None
    """
    latest_date = None

    for json_file in Path(data_dir).glob("*.json"):
        if json_file.name == CHECKPOINT_FILE:
            continue
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                case_date = data.get('date', '')
                if case_date and (latest_date is None or case_date > latest_date):
                    latest_date = case_date
        except Exception:
            continue

    return latest_date


def get_local_celex_numbers(data_dir: Path) -> set[str]:
    """
    Get the set of CELEX numbers already downloaded locally.

    Returns:
        Set of CELEX strings
    """
    celex_numbers = set()
    for json_file in Path(data_dir).glob("*.json"):
        if json_file.name == CHECKPOINT_FILE:
            continue
        # Filename format: 62023CJ0060.json (CELEX with ':' replaced by '_')
        # Reverse the transformation to get the CELEX number
        celex = json_file.stem.replace('_', ':')
        celex_numbers.add(celex)
    return celex_numbers


def incremental_update(
    data_dir: Path,
    delay_seconds: float = 1.0,
    max_new_cases: int = 500,
    subject_areas: list[str] | None = None,
    subject_keywords_de: list[str] | None = None,
    initial_year: int = 2018
) -> int:
    """
    Download only new cases since the last update.

    On first run (no local data), fetches ALL cases since initial_year
    via paginated SPARQL queries. On subsequent runs, fetches the most
    recent metadata and downloads any cases not yet present locally
    (identified by CELEX number, not by date — this ensures that cases
    added to CELLAR with a delay are not missed).

    Args:
        data_dir: Directory containing case JSON files
        delay_seconds: Delay between requests
        max_new_cases: Number of recent cases to check per update
        subject_areas: Optional list of EuroVoc descriptor labels for SPARQL filtering
        subject_keywords_de: Optional list of German keywords for Stichwort filtering
        initial_year: Start year for initial download if no local data exists

    Returns:
        Number of new cases downloaded
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = load_checkpoint(data_dir)
    local_celex = get_local_celex_numbers(data_dir)
    has_data = len(local_celex) > 0

    print(f"Checking for new cases...")
    if has_data:
        print(f"  {len(local_celex)} cases in local database")
    else:
        print(f"  No local cases found - performing full initial download since {initial_year}")
        return download_case_law_batch(
            output_dir=data_dir,
            year_from=initial_year,
            delay_seconds=delay_seconds,
            subject_areas=subject_areas,
            subject_keywords_de=subject_keywords_de
        )

    # Fetch recent metadata and find cases not yet downloaded locally
    metadata_list = get_case_law_metadata(
        limit=max_new_cases,
        subject_areas=subject_areas
    )

    # Filter to cases we don't have yet (by CELEX number)
    new_cases = [
        m for m in metadata_list
        if m.get('celex', '') and m['celex'] not in local_celex
    ]

    if not new_cases:
        print(f"  No new cases found. Database is up to date.")
        return 0

    print(f"  Found {len(new_cases)} new cases. Downloading...")

    downloaded = 0
    skipped = 0
    for metadata in tqdm(new_cases, desc="Downloading new cases"):
        celex = metadata.get("celex", "")
        if not celex:
            continue

        output_file = data_dir / f"{celex.replace(':', '_')}.json"
        if output_file.exists():
            continue

        doc = create_case_document(metadata)
        if doc:
            # Apply Stichwort filter if configured
            if subject_keywords_de and not matches_subject_filter(doc.keywords, subject_keywords_de):
                skipped += 1
                continue

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(doc.to_dict(), f, ensure_ascii=False, indent=2)
            downloaded += 1

        time.sleep(delay_seconds)

    # Update checkpoint
    checkpoint["last_download_date"] = datetime.now().isoformat()
    checkpoint["last_case_date"] = get_latest_case_date(data_dir)
    checkpoint["total_downloaded"] = checkpoint.get("total_downloaded", 0) + downloaded
    save_checkpoint(data_dir, checkpoint)

    if skipped:
        print(f"  Skipped {skipped} cases not matching subject keywords")
    print(f"  Downloaded {downloaded} new cases.")
    return downloaded


# =============================================================================
# LIVE SPARQL SEARCH (FALLBACK FOR OLDER CASES)
# =============================================================================

def _build_live_search_query(
    query_terms: list[str],
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 10,
    subject_areas: list[str] | None = None
) -> str:
    """Build a SPARQL query for live case search."""
    # Build FILTER for search terms (case-insensitive search in title)
    term_filters = []
    for term in query_terms:
        escaped = term.replace('"', '\\"').replace("'", "\\'")
        term_filters.append(f'CONTAINS(LCASE(?title), LCASE("{escaped}"))')

    filter_clause = " || ".join(term_filters) if term_filters else "true"

    # Date filters
    date_filters = ""
    if year_from:
        date_filters += f"FILTER(year(?date) >= {year_from})\n"
    if year_to:
        date_filters += f"FILTER(year(?date) <= {year_to})\n"

    # EuroVoc subject area filter
    subject_filter = ""
    if subject_areas:
        conditions = []
        for area in subject_areas:
            escaped = area.replace('"', '\\"')
            conditions.append(f'LCASE(STR(?eurovocLabel)) = "{escaped.lower()}"')
        subject_filter = f"""
        ?work cdm:work_is_about_concept_eurovoc ?eurovoc .
        ?eurovoc skos:prefLabel ?eurovocLabel .
        FILTER(lang(?eurovocLabel) = "en")
        FILTER({" || ".join(conditions)})
        """

    return f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

    SELECT DISTINCT ?celex ?title ?date ?caseNumber
    WHERE {{
        ?work a cdm:case-law .
        ?work cdm:resource_legal_celex ?celex .

        OPTIONAL {{ ?work cdm:work_date_document ?date . }}
        OPTIONAL {{
            ?work cdm:work_title ?title .
            FILTER(lang(?title) = "de" || lang(?title) = "en" || lang(?title) = "fr")
        }}
        OPTIONAL {{ ?work cdm:case-law_case_number ?caseNumber . }}

        {subject_filter}
        FILTER({filter_clause})
        {date_filters}
    }}
    ORDER BY DESC(?date)
    LIMIT {limit}
    """


def _execute_live_search_query(query: str) -> list[dict]:
    """Execute a live search SPARQL query and return results."""
    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(60)

    try:
        results = sparql.query().convert()

        cases = []
        for binding in results["results"]["bindings"]:
            cases.append({
                "celex": binding.get("celex", {}).get("value", ""),
                "title": binding.get("title", {}).get("value", ""),
                "date": binding.get("date", {}).get("value", ""),
                "case_number": binding.get("caseNumber", {}).get("value"),
            })
        return cases

    except Exception as e:
        print(f"Live SPARQL search failed: {e}")
        return []


def live_search_cases(
    query_terms: list[str],
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 10,
    subject_areas: list[str] | None = None
) -> list[dict]:
    """
    Perform a live SPARQL search for cases matching the query terms.

    This is used as a fallback when the local index doesn't have relevant results.
    Searches in case titles and subjects.

    If subject_areas are provided but the query returns 0 results (EuroVoc
    descriptors are often not available for case-law in CELLAR), the query
    is automatically retried without the subject area filter.

    Args:
        query_terms: List of search terms (will be OR-combined)
        year_from: Optional start year filter
        year_to: Optional end year filter
        limit: Maximum results
        subject_areas: Optional list of EuroVoc descriptor labels to filter by

    Returns:
        List of case metadata dicts with basic info
    """
    # Try with subject area filter first
    if subject_areas:
        query = _build_live_search_query(query_terms, year_from, year_to, limit, subject_areas)
        cases = _execute_live_search_query(query)
        if cases:
            return cases

    # Retry without subject area filter
    query = _build_live_search_query(query_terms, year_from, year_to, limit, subject_areas=None)
    return _execute_live_search_query(query)


def fetch_case_on_demand(celex: str) -> CaseLawDocument | None:
    """
    Fetch a single case on-demand (for fallback search results).

    Args:
        celex: CELEX number of the case

    Returns:
        CaseLawDocument or None
    """
    # First get metadata
    metadata = {
        "celex": celex,
        "title": "",
        "date": "",
        "case_number": None,
        "court": "Court of Justice",
        "document_type": "Judgment"
    }

    # Try to get more metadata via SPARQL
    query = f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>

    SELECT ?title ?date ?caseNumber
    WHERE {{
        ?work cdm:resource_legal_celex "{celex}" .
        OPTIONAL {{ ?work cdm:work_date_document ?date . }}
        OPTIONAL {{ ?work cdm:work_title ?title . }}
        OPTIONAL {{ ?work cdm:case-law_case_number ?caseNumber . }}
    }}
    LIMIT 1
    """

    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    try:
        results = sparql.query().convert()
        if results["results"]["bindings"]:
            binding = results["results"]["bindings"][0]
            metadata["title"] = binding.get("title", {}).get("value", "")
            metadata["date"] = binding.get("date", {}).get("value", "")
            metadata["case_number"] = binding.get("caseNumber", {}).get("value")
    except Exception:
        pass

    return create_case_document(metadata)


if __name__ == "__main__":
    # Example: Download recent case law with incremental updates
    from config import get_config
    cfg = get_config()
    data_dir = cfg.cases_dir

    # First run: downloads cases since initial_year in configured subject areas
    # Subsequent runs: only downloads new cases
    incremental_update(
        data_dir=data_dir,
        delay_seconds=cfg.download_delay,
        max_new_cases=cfg.update_limit,
        subject_areas=cfg.subject_areas,
        subject_keywords_de=cfg.subject_keywords_de,
        initial_year=cfg.initial_year
    )
