# CLAUDE.md - EuGH Chatbot Projekt

Dieses Dokument enthält alle relevanten Informationen für die Fortsetzung der Entwicklung in neuen Claude-Sessions.

## Projektziel

Entwicklung eines RAG-basierten Chatbots, der Fragen **ausschließlich** auf Grundlage der EuGH-Rechtsprechung (Europäischer Gerichtshof) beantwortet und dabei die Entscheidungen verlinkt.

## Aktueller Stand

**Merged PR:** #1 (`claude/eu-court-chatbot-r1gjM` → `main`)

**Status:** Feature-komplett (v0.1.0). Tests und CI hinzugefügt.

### Was ist fertig
- Full RAG pipeline with EUR-Lex SPARQL data acquisition
- Multilingual support (DE → EN → FR fallback)
- Incremental updates with checkpoint system
- Live fallback search for older/unindexed cases
- Cloud storage support (OneDrive, Google Drive, Dropbox)
- Streamlit web interface with streaming responses
- **75 pytest tests** covering all 4 core modules
- **CI pipeline** (GitHub Actions, Python 3.11/3.12 matrix)
- **Project README** with quick start, architecture, config reference

### What was done in the last session
- Added `ecj-chatbot/tests/` with 4 test files + conftest.py (75 tests, all passing)
- Heavy deps (chromadb, sentence-transformers) are mocked via `sys.modules` in conftest.py so tests run without ML packages
- Replaced Node.js CI template with Python workflow in `.github/workflows/ci.yml`
- Rewrote top-level `README.md` from generic scaffold to project-specific content

## Architektur

```
EUR-Lex SPARQL → JSON docs → sentence-transformers embeddings → ChromaDB → RAG context → Claude → sourced answer
```

## Projektstruktur

```
ecj-chatbot/
├── src/
│   ├── __init__.py
│   ├── config.py             # Konfiguration (Pfade, Einstellungen)
│   ├── data_acquisition.py   # EUR-Lex SPARQL-Abfragen, Download, Live-Suche
│   ├── embeddings.py         # ChromaDB Vektorisierung
│   └── rag_pipeline.py       # RAG-Logik, Claude-Integration
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures, sys.modules mocking
│   ├── test_config.py        # 19 tests
│   ├── test_data_acquisition.py  # 22 tests
│   ├── test_embeddings.py    # 14 tests
│   └── test_rag_pipeline.py  # 20 tests
├── data/                     # Standard-Speicherort (oder via ECJ_DATA_DIR)
│   ├── cases/                # JSON-Dateien der Entscheidungen
│   └── index/                # ChromaDB Vektor-Index (lokal)
├── app.py                    # Streamlit Web-Interface
├── requirements.txt          # Python-Abhängigkeiten
├── .env.example              # Umgebungsvariablen-Vorlage
├── notes.md                  # Entwicklungsnotizen
└── README.md                 # Benutzer-Dokumentation (Deutsch)
```

## Running Tests

```bash
cd ecj-chatbot
pip install pytest pytest-cov
python -m pytest tests/ -v
```

All 75 tests pass in ~1.7s. Tests mock all external services (SPARQL, Claude API, ChromaDB).

## Wichtige Dateien

### `src/config.py`
Zentrale Konfiguration mit Umgebungsvariablen:
- `ECJ_DATA_DIR`: Pfad zum Datenordner (Cloud-Ordner möglich)
- `ECJ_INITIAL_YEAR`: Startjahr für Download (default: 2020)
- `ECJ_ENABLE_LIVE_FALLBACK`: Live-Suche aktivieren (default: true)

### `src/data_acquisition.py`
- `get_case_law_metadata()`: SPARQL-Abfrage für Metadaten
- `fetch_document_text_with_fallback()`: Download mit Sprach-Fallback
- `incremental_update()`: Nur neue Fälle laden
- `live_search_cases()`: Live-SPARQL-Suche für ältere Fälle

### `src/rag_pipeline.py`
- `EuGHChatbot`: Hauptklasse für den Chatbot
- `search_relevant_cases()`: Suche mit optionalem Live-Fallback
- `answer_stream()`: Streaming-Antworten mit Claude

### `app.py`
- Streamlit Web-Interface
- Auto-Initialisierung beim ersten Start
- Sidebar mit Status, Update-Button, Einstellungen

## Empfohlene nächste Schritte (nach Priorität)

### Medium Priority
1. **Add linting/formatting** — Set up `ruff` with a `pyproject.toml`
2. **Add type hints** — More thorough annotations in core modules
3. **Dockerize** — `Dockerfile` for easier deployment

### Lower Priority
4. **Better error handling** — Retry logic for EUR-Lex/CURIA network failures
5. **FastAPI endpoint** — REST API (deps already in requirements.txt, no server code yet)
6. **Expand language coverage** — More EU languages beyond DE/EN/FR

## Technische Details

### Datenquellen
- **EUR-Lex SPARQL**: `https://publications.europa.eu/webapi/rdf/sparql`
- **CURIA**: `https://curia.europa.eu`

### URL-Formate
- EUR-Lex: `https://eur-lex.europa.eu/legal-content/{lang}/TXT/?uri=CELEX:{celex}`
- CURIA: `https://curia.europa.eu/juris/liste.jsf?num={case_number}&language={lang}`

### Embedding-Modell
- Default: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

### LLM
- Claude API (Anthropic), default: `claude-sonnet-4-20250514`

## Bekannte Einschränkungen

1. **ChromaDB nicht sync-safe**: Index muss lokal erstellt werden
2. **EUR-Lex Rate-Limiting**: Download mit 1s Delay zwischen Requests
3. **Keine Offline-Suche in alten Fällen**: Live-Fallback benötigt Internet
