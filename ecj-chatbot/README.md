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

- Python 3.11 oder höher
- Anthropic API Key (für Claude)

### Setup

```bash
# Repository klonen
git clone <repository-url>
cd ecj-chatbot

# Virtuelle Umgebung erstellen
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Abhängigkeiten installieren
pip install -r requirements.txt

# Umgebungsvariablen konfigurieren
cp .env.example .env
# Bearbeiten Sie .env und fügen Sie Ihren ANTHROPIC_API_KEY ein
```

## Verwendung

### 1. Daten herunterladen

Laden Sie zuerst EuGH-Entscheidungen von EUR-Lex herunter:

```bash
cd src
python data_acquisition.py
```

Dies lädt standardmäßig 50 aktuelle Entscheidungen. Für mehr Daten bearbeiten Sie die Parameter in der `__main__`-Sektion.

### 2. Index erstellen

Erstellen Sie den Vektor-Index für die semantische Suche:

```bash
python embeddings.py
```

### 3. Chatbot starten

#### Option A: Kommandozeile

```bash
python rag_pipeline.py
```

#### Option B: Web-Interface (Streamlit)

```bash
cd ..
streamlit run app.py
```

Der Chatbot ist dann unter `http://localhost:8501` erreichbar.

## Projektstruktur

```
ecj-chatbot/
├── src/
│   ├── __init__.py
│   ├── data_acquisition.py   # EUR-Lex SPARQL-Abfragen
│   ├── embeddings.py         # Vektorisierung mit ChromaDB
│   └── rag_pipeline.py       # RAG-Logik und Claude-Integration
├── data/
│   ├── cases/                # Heruntergeladene Entscheidungen (JSON)
│   └── index/                # ChromaDB Vektor-Index
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
