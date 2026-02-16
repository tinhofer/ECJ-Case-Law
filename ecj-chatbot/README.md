# EuGH Rechtsprechungs-Chatbot

Ein RAG-basierter (Retrieval-Augmented Generation) Chatbot, der Fragen ausschließlich auf Grundlage der Rechtsprechung des Europäischen Gerichtshofs (EuGH) beantwortet.

## Funktionen

- Beantwortet juristische Fragen basierend auf echten EuGH-Entscheidungen
- Verlinkt alle zitierten Entscheidungen zu EUR-Lex und CURIA
- Unterstützt Deutsch und andere EU-Sprachen
- Semantische Suche über tausende EuGH-Urteile
- Streaming-Antworten für bessere Benutzererfahrung

## Architektur

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EuGH Chatbot                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐   │
│   │   EUR-Lex   │───>│    Data      │───>│   Vector Store      │   │
│   │   SPARQL    │    │  Acquisition │    │   (ChromaDB)        │   │
│   └─────────────┘    └──────────────┘    └──────────┬──────────┘   │
│                                                      │              │
│   ┌─────────────┐    ┌──────────────┐    ┌──────────▼──────────┐   │
│   │   Benutzer  │───>│     RAG      │<───│    Embeddings       │   │
│   │   Anfrage   │    │   Pipeline   │    │  (Multilingual)     │   │
│   └─────────────┘    └──────┬───────┘    └─────────────────────┘   │
│                             │                                       │
│                      ┌──────▼───────┐                               │
│                      │   Claude     │                               │
│                      │   (LLM)      │                               │
│                      └──────┬───────┘                               │
│                             │                                       │
│                      ┌──────▼───────┐                               │
│                      │   Antwort    │                               │
│                      │   + Quellen  │                               │
│                      └──────────────┘                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Installation

### Voraussetzungen

1. **Python 3.11 oder höher** — [Download](https://www.python.org/downloads/)
   - Bei der Installation unbedingt **"Add Python to PATH"** ankreuzen!
2. **Git** — [Download](https://git-scm.com/downloads)
3. **Anthropic API Key** — [Account erstellen](https://console.anthropic.com/)
4. **Terminal** — Eingabeaufforderung, PowerShell oder Node.js command prompt (Windows) bzw. Terminal (Mac/Linux)

Prüfen Sie nach der Installation, ob alles funktioniert:
```bash
python --version   # sollte 3.11+ anzeigen
git --version      # sollte eine Versionsnummer anzeigen
```

### Setup

Siehe [Schnellstart](#schnellstart) weiter unten für eine Schritt-für-Schritt-Anleitung.

## Verwendung

### Schnellstart

**Schritt 1 — Repository klonen:**
```bash
git clone https://github.com/tinhofer/ECJ-Case-Law.git
cd ECJ-Case-Law/ecj-chatbot
```

**Schritt 2 — Virtuelle Umgebung erstellen und aktivieren:**

Windows:
```cmd
python -m venv venv
venv\Scripts\activate
```

Linux/Mac:
```bash
python -m venv venv
source venv/bin/activate
```

**Schritt 3 — Abhängigkeiten installieren:**
```bash
pip install -r requirements.txt
```

**Schritt 4 — API-Key konfigurieren:**

Windows:
```cmd
copy .env.example .env
```

Linux/Mac:
```bash
cp .env.example .env
```

Dann die `.env`-Datei mit einem Texteditor öffnen und Ihren `ANTHROPIC_API_KEY` eintragen.

**Schritt 5 — Chatbot starten:**
```bash
streamlit run app.py
```

Beim ersten Start werden automatisch:
- EuGH-Entscheidungen seit 2018 heruntergeladen (~500 Fälle)
- Der Suchindex erstellt
- Bei weiteren Starts nur neue Fälle nachgeladen

### Manueller Workflow (optional)

Falls Sie mehr Kontrolle wünschen:

```bash
cd src

# Daten herunterladen
python data_acquisition.py

# Index erstellen
python embeddings.py

# Chatbot starten
cd ..
streamlit run app.py
```

## Cloud-Speicher (Multi-Device)

> **Wichtig:** Klonen Sie das Repository **nicht** direkt in einen Cloud-Ordner (OneDrive, Dropbox, Google Drive). Cloud-Sync-Dienste können die internen Git-Dateien und den ChromaDB-Index beschädigen. Speichern Sie das Repository in einem normalen lokalen Ordner (z.B. `C:\Users\IhrName\ECJ-Case-Law`).

Sie können aber die **heruntergeladenen EuGH-Fälle** in einem Cloud-Ordner speichern, um von mehreren Geräten darauf zuzugreifen.

### Einrichtung

1. Erstellen Sie einen Ordner in Ihrem Cloud-Speicher:
   - OneDrive: `OneDrive/EuGH-Data`
   - Google Drive: `Google Drive/EuGH-Data`
   - Dropbox: `Dropbox/EuGH-Data`

2. Setzen Sie die Umgebungsvariable in `.env`:
   ```bash
   # Windows
   ECJ_DATA_DIR=C:\Users\IhrName\OneDrive\EuGH-Data

   # macOS/Linux
   ECJ_DATA_DIR=/Users/IhrName/OneDrive/EuGH-Data
   ```

3. Starten Sie den Chatbot - er verwendet automatisch den Cloud-Ordner

### Wie es funktioniert

```
Gerät A (Ersteinrichtung)         Cloud (OneDrive/GDrive)
┌─────────────────────┐           ┌─────────────────────┐
│ 1. Download Fälle   │ ────────> │  cases/*.json       │
│ 2. Erstelle Index   │           │  (synchronisiert)   │
└─────────────────────┘           └─────────────────────┘
                                            │
                                            ▼
Gerät B (neue Installation)       ┌─────────────────────┐
┌─────────────────────┐           │  cases/*.json       │
│ 1. Daten vorhanden  │ <──────── │  (synchronisiert)   │
│ 2. Index fehlt      │           └─────────────────────┘
│ 3. Auto-Index! ✓    │
└─────────────────────┘
```

**Wichtig:** Der Index wird lokal erstellt (nicht synchronisiert), da ChromaDB-Dateien bei gleichzeitigem Zugriff korrupt werden können. Der Index wird automatisch erstellt, wenn Daten vorhanden sind aber kein Index existiert.

## Projektstruktur

```
ecj-chatbot/
├── src/
│   ├── __init__.py
│   ├── config.py             # Konfiguration (Pfade, Einstellungen)
│   ├── data_acquisition.py   # EUR-Lex SPARQL-Abfragen
│   ├── embeddings.py         # Vektorisierung mit ChromaDB
│   └── rag_pipeline.py       # RAG-Logik und Claude-Integration
├── data/                     # Standard-Speicherort (oder Cloud-Ordner)
│   ├── cases/                # Heruntergeladene Entscheidungen (JSON)
│   └── index/                # ChromaDB Vektor-Index (lokal)
├── app.py                    # Streamlit Web-Interface
├── requirements.txt          # Python-Abhängigkeiten
├── .env.example              # Beispiel-Umgebungsvariablen
└── README.md                 # Diese Datei
```

## Datenquellen

### EUR-Lex / CELLAR

- **SPARQL-Endpoint**: https://publications.europa.eu/webapi/rdf/sparql
- **Query Builder**: https://op.europa.eu/en/advanced-sparql-query-editor
- **Dokumentation**: https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-details.html

### CURIA

- **InfoCuria**: https://curia.europa.eu
- **Dokumentation**: https://curia.europa.eu/jcms/jcms/Jo2_7045/en/

## Verlinkungsformat

Der Chatbot verlinkt Entscheidungen in zwei Formaten:

1. **EUR-Lex (CELEX)**:
   ```
   https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:62019CJ0311
   ```

2. **CURIA (Rechtssache)**:
   ```
   https://curia.europa.eu/juris/liste.jsf?num=C-311/18&language=de
   ```

## Konfiguration

### Embedding-Modelle

Standardmäßig wird `paraphrase-multilingual-MiniLM-L12-v2` verwendet. Alternativen:

```python
# In embeddings.py ändern:
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"  # Höhere Qualität
EMBEDDING_MODEL = "deutsche-telekom/gbert-large-paraphrase-cosine"  # Deutsch-optimiert
```

### LLM-Modell

In `rag_pipeline.py` kann das Claude-Modell geändert werden:

```python
model = "claude-sonnet-4-20250514"  # Schneller
model = "claude-opus-4-20250514"       # Höhere Qualität
```

## Beispiel-Interaktion

```
Sie: Was hat der EuGH zum Datenschutz bei internationalen Datentransfers entschieden?

Assistent: Der EuGH hat in mehreren wegweisenden Entscheidungen die Voraussetzungen
für internationale Datentransfers konkretisiert:

1. **Rs. C-311/18 (Schrems II)** - Urteil vom 16. Juli 2020
   Der EuGH erklärte das Privacy Shield-Abkommen für ungültig, da das US-Recht
   kein angemessenes Schutzniveau bietet. Standardvertragsklauseln bleiben gültig,
   wenn ein angemessenes Schutzniveau gewährleistet werden kann.
   [EUR-Lex](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:62018CJ0311)

2. **Rs. C-362/14 (Schrems I)** - Urteil vom 6. Oktober 2015
   Der EuGH erklärte die Safe-Harbor-Entscheidung für ungültig und betonte das
   Grundrecht auf Datenschutz nach Art. 7 und 8 der Grundrechtecharta.
   [EUR-Lex](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:62014CJ0362)
```

## Erweiterungsmöglichkeiten

1. **Mehr Daten**: Erhöhen Sie das Download-Limit für mehr Entscheidungen
2. **Agentic RAG**: Lassen Sie das LLM dynamisch SPARQL-Queries erstellen
3. **Filterung**: Fügen Sie Filter nach Rechtsgebiet, Gericht oder Zeitraum hinzu
4. **API**: Erstellen Sie eine FastAPI-REST-Schnittstelle
5. **Scheduled Updates**: Automatisches Update neuer Entscheidungen via Cron

## Hinweise

- Dies ist ein Prototyp für Forschungs- und Bildungszwecke
- Keine Gewähr für Vollständigkeit oder Aktualität der Daten
- Kein Ersatz für professionelle Rechtsberatung
- Beachten Sie die Nutzungsbedingungen von EUR-Lex und Anthropic

## Lizenz

MIT License - siehe LICENSE-Datei

## Ressourcen

- [EUR-Lex](https://eur-lex.europa.eu/)
- [CURIA](https://curia.europa.eu/)
- [eurlex R Package](https://github.com/michalovadek/eurlex)
- [eurlex Python Package](https://github.com/step21/eurlex)
- [Anthropic Claude](https://www.anthropic.com/)
- [ChromaDB](https://www.trychroma.com/)
- [LangChain](https://www.langchain.com/)
