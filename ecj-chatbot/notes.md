# EuGH-Chatbot Entwicklungsnotizen

## Projektziel
Entwicklung eines Chatbots, der Fragen ausschließlich basierend auf der EuGH-Rechtsprechung beantwortet und dabei Entscheidungen verlinkt.

## Recherche-Ergebnisse

### Datenquellen für EuGH-Entscheidungen

#### 1. EUR-Lex / CELLAR (empfohlen)
- **SPARQL-Endpoint**: Offizieller Zugang zu EU-Rechtsdokumenten
- **URL**: https://publications.europa.eu/webapi/rdf/sparql
- **CDM (Common Data Model)**: FRBR-kompatible OWL-Ontologie
- **Query Builder**: https://op.europa.eu/en/advanced-sparql-query-editor
- **Vorteile**: Strukturierte Metadaten, vollständige Rechtsprechung, öffentlich zugänglich
- **CELEX-Nummern**: Eindeutige Identifikatoren für alle EU-Rechtsdokumente

#### 2. CURIA / InfoCuria
- **URL**: https://curia.europa.eu
- **Abdeckung**: Alle Fälle seit 1953
- **Aktualisiert 2024/2025**: Neue Suchoberfläche mit erweiterter Funktionalität
- **Limitation**: Kein direktes API für Bulk-Zugriff, primär Web-Interface
- **Verlinkung**: Ältere Fälle (bis 1997) verlinken zu EUR-Lex

#### 3. Bestehende Bibliotheken
- **R-Package `eurlex`**: https://github.com/michalovadek/eurlex
  - `elx_make_query()` - SPARQL-Abfragen erstellen
  - `elx_run_query()` - Abfragen ausführen
  - `elx_fetch_data()` - REST API Abruf
  - Unterstützt `resource_type = "caselaw"`

- **Python-Package `eurlex`**: https://github.com/step21/eurlex
  - SPARQL-Queries für CELLAR
  - Download-Funktionen

### Relevante Ressourcentypen
- Urteile (Judgments)
- Schlussanträge des Generalanwalts (Opinions)
- Beschlüsse (Orders)
- Gutachten (Advisory Opinions)

## Architektur-Überlegungen

### Option A: RAG-basierter Ansatz (Retrieval-Augmented Generation)

```
[Datenakquise] -> [Preprocessing] -> [Vektordatenbank] -> [RAG-Pipeline] -> [LLM] -> [Antwort]
     |                  |                    |                  |
  SPARQL API      Text-Extraktion      Embeddings         Kontextuelle
  EUR-Lex         Chunking             ChromaDB/          Antwort mit
                  Metadaten            Pinecone           Zitationen
```

**Vorteile**:
- Antworten basieren nachweislich auf echten Entscheidungen
- Direkte Verlinkung möglich
- Skalierbar
- Aktualisierbar

**Komponenten**:
1. **Data Pipeline**: Regelmäßiger Abruf neuer Entscheidungen
2. **Vektordatenbank**: Speicherung der Embeddings
3. **Retrieval**: Semantische Suche nach relevanten Dokumenten
4. **Generation**: LLM erzeugt Antwort basierend auf gefundenen Dokumenten

### Option B: Fine-tuned Model
- Nicht empfohlen für diesen Use-Case
- Schwierig zu aktualisieren
- Keine direkte Quellenangabe möglich

### Option C: Agentic RAG mit Tool-Calling
- LLM kann aktiv SPARQL-Queries formulieren
- Flexibler für komplexe Anfragen
- Höhere Komplexität

## Technologie-Stack (Empfehlung)

### Backend
- **Python 3.11+**
- **LangChain** oder **LlamaIndex**: RAG-Framework
- **ChromaDB** oder **Weaviate**: Vektordatenbank (lokal)
- **Pinecone** oder **Qdrant**: Vektordatenbank (Cloud)
- **FastAPI**: REST API
- **Claude API** oder **OpenAI**: LLM

### Datenakquise
- **SPARQLWrapper**: SPARQL-Queries
- **requests**: HTTP-Abruf
- **BeautifulSoup/lxml**: HTML/XML-Parsing

### Frontend
- **Streamlit** (schneller Prototyp)
- **Next.js + React** (Produktions-UI)

### Infrastruktur
- **Docker**: Containerisierung
- **Scheduled Jobs**: Cron/Celery für Updates

## SPARQL Query Beispiel

```sparql
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT ?work ?celex ?date ?title
WHERE {
  ?work cdm:resource_legal_resource_type ?type .
  ?type skos:prefLabel "Judgment"@en .
  ?work cdm:resource_legal_celex ?celex .
  OPTIONAL { ?work cdm:work_date_document ?date . }
  OPTIONAL { ?work cdm:work_title ?title . }
}
ORDER BY DESC(?date)
LIMIT 100
```

## Verlinkungsstrategie

EuGH-Entscheidungen können über folgende URL-Muster verlinkt werden:

1. **EUR-Lex (CELEX)**:
   `https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:{celex_number}`
   Beispiel: https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:62019CJ0311

2. **CURIA (Case Number)**:
   `https://curia.europa.eu/juris/liste.jsf?num={case_number}&language=de`
   Beispiel: https://curia.europa.eu/juris/liste.jsf?num=C-311/18&language=de

3. **ECLI (European Case Law Identifier)**:
   Format: ECLI:EU:C:YYYY:NNN
   Beispiel: ECLI:EU:C:2020:559

## Implementierte Komponenten

1. [x] SPARQL-Endpoint Zugriff (data_acquisition.py)
2. [x] Datenstruktur definiert (CaseLawDocument)
3. [x] Proof-of-Concept für Datenakquise
4. [x] Embedding-Pipeline mit ChromaDB (embeddings.py)
5. [x] RAG-Prototyp mit Claude (rag_pipeline.py)
6. [x] Streamlit Frontend (app.py)
7. [x] Mehrsprachige Unterstützung (DE → EN → FR Fallback)

## Mehrsprachige Unterstützung

Aktuelle Entscheidungen sind oft noch nicht auf Deutsch verfügbar. Das System unterstützt daher:

- **Sprach-Fallback**: DE → EN → FR (in dieser Reihenfolge)
- **Sprach-Kennzeichnung**: Jedes Dokument speichert seine Sprache
- **LLM-Hinweis**: Der Chatbot informiert, wenn Quellen nicht auf Deutsch sind
- **URL-Anpassung**: EUR-Lex und CURIA Links führen zur korrekten Sprachversion

Beispiel-Output:
```
Rs. C-XXX/23 (Englisch)
[EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:...)
```

## Inkrementelle Updates & Live-Fallback

### Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EINMALIGE INITIALISIERUNG                          │
│   1. Download aller Fälle seit 2020 (konfigurierbar)                        │
│   2. Erstellung des Vektor-Index                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BEI JEDEM START / UPDATE                            │
│   1. Prüfe auf neue Entscheidungen seit letztem Download                    │
│   2. Lade nur die neuen Fälle herunter                                      │
│   3. Aktualisiere den Index (falls neue Fälle)                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BEI JEDER ANFRAGE                                 │
│   1. Suche im lokalen Vektor-Index                                          │
│   2. Falls keine guten Ergebnisse: Live-SPARQL-Suche (ältere Fälle)         │
│   3. On-Demand Download der gefundenen älteren Fälle                        │
│   4. Antwort generieren mit allen gefundenen Quellen                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementierte Funktionen

1. **Checkpoint-System** (`data_acquisition.py`)
   - Speichert letztes Download-Datum
   - Ermöglicht inkrementelle Updates

2. **Inkrementelle Updates** (`incremental_update()`)
   - Lädt nur neue Entscheidungen seit letztem Update
   - Automatisch beim App-Start oder manuell per Button

3. **Live-Fallback-Suche** (`live_search_cases()`)
   - SPARQL-Suche in gesamter EUR-Lex-Datenbank
   - Aktiviert wenn lokaler Index keine relevanten Ergebnisse hat
   - On-Demand Download der gefundenen Fälle

4. **UI-Integration**
   - Update-Button in Sidebar
   - Toggle für Live-Fallback
   - Anzeige wenn Fallback verwendet wurde

## Offene Erweiterungen

- [ ] Caching für API-Anfragen implementieren
- [ ] Filterung nach Rechtsgebiet/Gericht
- [ ] Agentic RAG für komplexe Anfragen
- [ ] FastAPI REST-Endpunkt
- [ ] Docker-Container
- [x] Automatische Updates neuer Entscheidungen
- [x] Live-Fallback für ältere Fälle
