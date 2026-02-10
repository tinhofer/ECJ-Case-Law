"""Shared fixtures for the EuGH chatbot test suite.

Heavy dependencies (chromadb, sentence_transformers) are mocked via sys.modules
so that tests can run in CI without installing large ML packages.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Mock heavy third-party packages BEFORE any src module is imported.
# This lets us test pure logic without downloading ML models or ChromaDB.
# ---------------------------------------------------------------------------

# Only mock if the packages aren't actually installed
for _mod_name in ("chromadb", "chromadb.config", "sentence_transformers"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Add src/ to the path so tests can import modules the same way the app does
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_case_dict():
    """A minimal case law document as a dict (matches JSON on disk)."""
    return {
        "celex": "62020CJ0311",
        "title": "Schrems II - Datenschutz",
        "date": "2020-07-16",
        "case_number": "C-311/18",
        "court": "Court of Justice",
        "document_type": "Judgment",
        "text": "This is the full text of the judgment. " * 50,
        "eurlex_url": "https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:62020CJ0311",
        "curia_url": "https://curia.europa.eu/juris/liste.jsf?num=C-311/18&language=de",
        "ecli": "ECLI:EU:C:2020:559",
        "keywords": ["Datenschutz", "Privacy Shield"],
        "language": "DE",
    }


@pytest.fixture
def sample_metadata():
    """Metadata dict as returned by get_case_law_metadata."""
    return {
        "celex": "62020CJ0311",
        "title": "Schrems II - Datenschutz",
        "date": "2020-07-16",
        "ecli": "ECLI:EU:C:2020:559",
        "case_number": "C-311/18",
        "court": "Court of Justice",
        "document_type": "Judgment",
    }


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory structure."""
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    return tmp_path


@pytest.fixture
def populated_cases_dir(tmp_data_dir, sample_case_dict):
    """A cases directory with two sample JSON files."""
    cases_dir = tmp_data_dir / "cases"

    for i, celex in enumerate(["62020CJ0311", "62021CJ0100"]):
        doc = dict(sample_case_dict, celex=celex, date=f"202{i}-07-16")
        path = cases_dir / f"{celex}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    return cases_dir
