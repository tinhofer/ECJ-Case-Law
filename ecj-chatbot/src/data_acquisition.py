"""
EuGH Case Law Data Acquisition Module

This module handles fetching case law data from EUR-Lex via SPARQL queries.
"""

import json
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


def get_case_law_metadata(
    limit: int = 1000,
    offset: int = 0,
    year_from: int | None = None,
    year_to: int | None = None,
    court: str = "Court of Justice"
) -> list[dict]:
    """
    Fetch case law metadata from EUR-Lex via SPARQL.

    Args:
        limit: Maximum number of results
        offset: Offset for pagination
        year_from: Filter by start year
        year_to: Filter by end year
        court: Court filter (Court of Justice, General Court, Civil Service Tribunal)

    Returns:
        List of case metadata dictionaries
    """

    # Build date filter
    date_filter = ""
    if year_from:
        date_filter += f'FILTER(year(?date) >= {year_from})\n'
    if year_to:
        date_filter += f'FILTER(year(?date) <= {year_to})\n'

    query = f"""
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

        {date_filter}
    }}
    ORDER BY DESC(?date)
    LIMIT {limit}
    OFFSET {offset}
    """

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
        keywords=[],
        language=language
    )


def download_case_law_batch(
    output_dir: Path,
    limit: int = 100,
    year_from: int | None = None,
    year_to: int | None = None,
    delay_seconds: float = 1.0
) -> int:
    """
    Download a batch of case law documents.

    Args:
        output_dir: Directory to save documents
        limit: Maximum number of documents
        year_from: Filter by start year
        year_to: Filter by end year
        delay_seconds: Delay between requests to be respectful to the server

    Returns:
        Number of successfully downloaded documents
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching metadata for up to {limit} cases...")
    metadata_list = get_case_law_metadata(
        limit=limit,
        year_from=year_from,
        year_to=year_to
    )

    print(f"Found {len(metadata_list)} cases. Downloading full texts...")

    downloaded = 0
    for metadata in tqdm(metadata_list, desc="Downloading"):
        celex = metadata.get("celex", "")
        if not celex:
            continue

        # Check if already downloaded
        output_file = output_dir / f"{celex.replace(':', '_')}.json"
        if output_file.exists():
            downloaded += 1
            continue

        # Create document
        doc = create_case_document(metadata)
        if doc:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(doc.to_dict(), f, ensure_ascii=False, indent=2)
            downloaded += 1

        # Respectful delay
        time.sleep(delay_seconds)

    print(f"Downloaded {downloaded} documents to {output_dir}")
    return downloaded


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


if __name__ == "__main__":
    # Example: Download recent case law
    from pathlib import Path

    data_dir = Path(__file__).parent.parent / "data" / "cases"

    # Download 50 recent cases
    download_case_law_batch(
        output_dir=data_dir,
        limit=50,
        year_from=2020,
        delay_seconds=1.5
    )
