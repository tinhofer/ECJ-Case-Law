# ECJ Case Law Chatbot

A RAG-based (Retrieval-Augmented Generation) chatbot that answers legal questions exclusively based on European Court of Justice (EuGH/ECJ) case law. All answers are grounded in actual court decisions and linked to their official sources on EUR-Lex and CURIA.

## Features

- Answers legal questions based on real ECJ decisions with source citations
- Links every cited decision to [EUR-Lex](https://eur-lex.europa.eu/) and [CURIA](https://curia.europa.eu/)
- Multilingual support (DE/EN/FR) with automatic language fallback
- Semantic search over thousands of ECJ judgments via ChromaDB
- Live fallback search for older cases not in the local index
- Incremental updates — only downloads new decisions on subsequent runs
- Cloud storage support (OneDrive, Google Drive, Dropbox) for multi-device access
- Streaming responses via Streamlit web interface

## Quick Start

```bash
# Clone and enter the project
git clone https://github.com/tinhofer/ECJ-Case-Law.git
cd ECJ-Case-Law/ecj-chatbot

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Launch the chatbot
streamlit run app.py
```

On first launch the app automatically downloads ~500 recent ECJ decisions from EUR-Lex and builds the search index. Subsequent launches only fetch new cases.

## Architecture

```
User Question
      │
      ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  ChromaDB   │────>│  RAG Pipeline│────>│   Claude     │
│  Vector     │     │  (retrieval  │     │   (LLM)      │
│  Search     │     │   + context) │     │              │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                                         ┌──────▼───────┐
                                         │   Answer     │
                                         │   + Sources  │
                                         └──────────────┘
```

**Data flow:** EUR-Lex SPARQL → JSON documents → sentence-transformers embeddings → ChromaDB index → RAG context → Claude → sourced answer

## Project Structure

```
ecj-chatbot/
├── src/
│   ├── config.py             # Configuration & cloud storage paths
│   ├── data_acquisition.py   # EUR-Lex SPARQL queries & incremental updates
│   ├── embeddings.py         # ChromaDB vector store & text chunking
│   └── rag_pipeline.py       # RAG logic & Claude API integration
├── tests/                    # Pytest test suite
├── app.py                    # Streamlit web interface
├── requirements.txt          # Python dependencies
└── .env.example              # Environment variable template
```

## Running Tests

```bash
cd ecj-chatbot
pip install pytest pytest-cov
python -m pytest tests/ -v
```

## Configuration

Key settings via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | (required) |
| `ECJ_DATA_DIR` | Data storage path (supports cloud folders) | `./data` |
| `ECJ_LLM_MODEL` | Claude model to use | `claude-sonnet-4-20250514` |
| `ECJ_INITIAL_YEAR` | Earliest year to download cases from | `2020` |
| `ECJ_ENABLE_LIVE_FALLBACK` | Search EUR-Lex live for older cases | `true` |

## Tech Stack

- **Python 3.11+** — core language
- **Anthropic Claude** — LLM for answer generation
- **ChromaDB** — local vector database
- **sentence-transformers** — multilingual embeddings (`paraphrase-multilingual-MiniLM-L12-v2`)
- **Streamlit** — web interface
- **SPARQLWrapper** — EUR-Lex data acquisition
- **BeautifulSoup4** — HTML text extraction

## Documentation

- [Detailed setup & usage guide](ecj-chatbot/README.md) (German)
- [Contributing guidelines](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

MIT License — see [LICENSE](LICENSE) for details.
