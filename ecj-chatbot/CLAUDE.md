# CLAUDE.md - EuGH Chatbot Projekt

Dieses Dokument enthält alle relevanten Informationen für die Fortsetzung der Entwicklung in neuen Claude-Sessions.

## Projektziel

Entwicklung eines RAG-basierten Chatbots, der Fragen **ausschließlich** auf Grundlage der EuGH-Rechtsprechung (Europäischer Gerichtshof) beantwortet und dabei die Entscheidungen verlinkt.

## Aktueller Stand

**Branch:** `claude/eu-court-chatbot-r1gjM`

**Commits:**
1. ✅ `feat: Add EuGH case law chatbot with RAG architecture`
2. ✅ `feat: Add multilingual support with DE/EN/FR fallback`
3. ✅ `feat: Add incremental updates and live fallback search`
4. ✅ `feat: Add configurable data paths for cloud storage support`

**Status:** Feature-komplett, bereit für Tests und PR

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EuGH CHATBOT                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DATENQUELLEN                    VERARBEITUNG              AUSGABE          │
│  ┌───────────────┐              ┌──────────────┐         ┌──────────────┐  │
│  │ EUR-Lex       │──SPARQL───>  │ ChromaDB     │──RAG──> │ Claude API   │  │
│  │ (CELLAR)      │              │ (Vektor-DB)  │         │ (Anthropic)  │  │
│  └───────────────┘              └──────────────┘         └──────────────┘  │
│         │                              │                        │          │
│         │                              │                        ▼          │
│         │                              │                 ┌──────────────┐  │
│         └──────Live-Fallback──────────>│                 │ Antwort +    │  │
│           (für ältere Fälle)           │                 │ Quellenlinks │  │
│                                        │                 └──────────────┘  │
│                                        │                                   │
│  SPEICHERUNG                           │                                   │
│  ┌───────────────┐                     │                                   │
│  │ Cloud-Ordner  │<────sync────────────┘                                   │
│  │ (OneDrive/    │     (nur JSON,                                          │
│  │  GDrive)      │      nicht Index)                                       │
│  └───────────────┘                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
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
├── data/                     # Standard-Speicherort (oder via ECJ_DATA_DIR)
│   ├── cases/                # JSON-Dateien der Entscheidungen
│   └── index/                # ChromaDB Vektor-Index (lokal)
├── app.py                    # Streamlit Web-Interface
├── requirements.txt          # Python-Abhängigkeiten
├── .env.example              # Umgebungsvariablen-Vorlage
├── notes.md                  # Entwicklungsnotizen
└── README.md                 # Benutzer-Dokumentation
```

## Implementierte Features

### 1. RAG-basierter Chatbot
- Semantische Suche über EuGH-Entscheidungen
- Claude API für Antwortgenerierung
- Quellenangaben mit EUR-Lex und CURIA Links

### 2. Mehrsprachige Unterstützung
- Sprach-Fallback: DE → EN → FR
- Aktuelle Entscheidungen oft nur auf EN/FR verfügbar
- Sprache wird in Metadaten gespeichert und in UI angezeigt

### 3. Inkrementelle Updates
- Checkpoint-System speichert letztes Download-Datum
- Bei App-Start nur neue Fälle nachladen
- Manueller Update-Button in UI

### 4. Live-Fallback-Suche
- Wenn lokaler Index keine relevanten Ergebnisse hat
- SPARQL-Suche in gesamter EUR-Lex-Datenbank
- On-Demand Download gefundener Fälle

### 5. Cloud-Speicher
- Konfigurierbarer Datenpfad via `ECJ_DATA_DIR`
- Auto-Index-Erstellung wenn Daten vorhanden aber Index fehlt
- Nur JSON-Daten werden synchronisiert (nicht Index)

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

## Offene Punkte / Nächste Schritte

### Zum Testen
1. `pip install -r requirements.txt`
2. `.env` mit `ANTHROPIC_API_KEY` erstellen
3. `streamlit run app.py`
4. Erster Start lädt ~500 Fälle (dauert ~10-15 Min)

### Mögliche Erweiterungen
- [ ] Filterung nach Rechtsgebiet/Gericht
- [ ] Caching für API-Anfragen
- [ ] FastAPI REST-Endpunkt
- [ ] Docker-Container
- [ ] Agentic RAG für komplexe Anfragen

### PR erstellen
Wenn Tests erfolgreich, PR mit:
```bash
gh pr create --title "feat: EuGH Case Law Chatbot" --body "..."
```

## Technische Details

### Datenquellen
- **EUR-Lex SPARQL**: `https://publications.europa.eu/webapi/rdf/sparql`
- **CURIA**: `https://curia.europa.eu`

### URL-Formate
- EUR-Lex: `https://eur-lex.europa.eu/legal-content/{lang}/TXT/?uri=CELEX:{celex}`
- CURIA: `https://curia.europa.eu/juris/liste.jsf?num={case_number}&language={lang}`

### Embedding-Modell
- Default: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Multilingual für DE/EN/FR Support

### LLM
- Claude API (Anthropic)
- Default-Modell: `claude-sonnet-4-20250514`

## Bekannte Einschränkungen

1. **ChromaDB nicht sync-safe**: Index muss lokal erstellt werden
2. **EUR-Lex Rate-Limiting**: Download mit 1s Delay zwischen Requests
3. **Keine Offline-Suche in alten Fällen**: Live-Fallback benötigt Internet

## Kontext für neue Sessions

Bei Fortsetzung in neuer Session:
1. Branch `claude/eu-court-chatbot-r1gjM` auschecken
2. Diese Datei lesen für Kontext
3. `notes.md` für detaillierte Entwicklungsnotizen
4. `README.md` für Benutzer-Dokumentation
