"""
EuGH Chatbot - Streamlit Web Application

A web interface for the EuGH case law chatbot.

Run with: streamlit run app.py
"""

import os
from pathlib import Path

import streamlit as st

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rag_pipeline import create_chatbot, EuGHChatbot
from embeddings import CaseLawVectorStore, build_index_from_data_dir
from data_acquisition import (
    incremental_update,
    load_checkpoint,
    download_case_law_batch
)


# Configuration
DATA_DIR = Path(__file__).parent / "data" / "cases"
INDEX_DIR = Path(__file__).parent / "data" / "index"


def initialize_data_and_index(
    auto_update: bool = True,
    initial_year: int = 2020
) -> bool:
    """
    Initialize or update the case law data and search index.

    This function:
    1. Checks if data exists, if not performs initial download
    2. If auto_update is True, checks for and downloads new cases
    3. Rebuilds the index if new data was added

    Args:
        auto_update: Whether to check for new cases on startup
        initial_year: Year from which to download cases initially

    Returns:
        True if initialization was successful
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # Check if we have any data
    existing_cases = list(DATA_DIR.glob("*.json"))
    has_data = len(existing_cases) > 0

    if not has_data:
        # Initial download
        st.info(f"Erste Initialisierung: Lade EuGH-Entscheidungen seit {initial_year}...")
        with st.spinner("Lade Daten von EUR-Lex..."):
            downloaded = download_case_law_batch(
                output_dir=DATA_DIR,
                limit=500,  # Initial batch
                year_from=initial_year,
                delay_seconds=1.0
            )
            st.success(f"{downloaded} Entscheidungen heruntergeladen.")

        # Build initial index
        st.info("Erstelle Suchindex...")
        with st.spinner("Indiziere Dokumente..."):
            build_index_from_data_dir(DATA_DIR, INDEX_DIR)
            st.success("Index erstellt.")

        return True

    elif auto_update:
        # Check for updates
        checkpoint = load_checkpoint(DATA_DIR)
        last_update = checkpoint.get("last_download_date", "Nie")

        with st.spinner(f"Prüfe auf neue Entscheidungen (letztes Update: {last_update[:10] if last_update != 'Nie' else last_update})..."):
            new_cases = incremental_update(
                data_dir=DATA_DIR,
                delay_seconds=1.0,
                max_new_cases=100
            )

        if new_cases > 0:
            st.info(f"{new_cases} neue Entscheidungen gefunden. Aktualisiere Index...")
            with st.spinner("Aktualisiere Suchindex..."):
                build_index_from_data_dir(DATA_DIR, INDEX_DIR)
            st.success("Index aktualisiert.")

    return True


def init_chatbot(auto_update: bool = False) -> EuGHChatbot | None:
    """
    Initialize or retrieve the chatbot from session state.

    Args:
        auto_update: Whether to check for new cases on startup
    """
    # Check for API key first
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error(
            "Bitte setzen Sie die ANTHROPIC_API_KEY Umgebungsvariable "
            "oder geben Sie den API-Schlüssel in der Seitenleiste ein."
        )
        return None

    # Initialize data and index if needed (only on first run)
    if "initialized" not in st.session_state:
        if not INDEX_DIR.exists() or not any(INDEX_DIR.iterdir()):
            initialize_data_and_index(auto_update=auto_update)
        st.session_state.initialized = True

    if "chatbot" not in st.session_state:
        if not INDEX_DIR.exists():
            st.error(
                f"Index-Verzeichnis nicht gefunden: {INDEX_DIR}\n\n"
                "Bitte führen Sie zuerst die Datenakquise und Indizierung durch."
            )
            return None

        try:
            st.session_state.chatbot = create_chatbot(INDEX_DIR, api_key)
        except Exception as e:
            st.error(f"Fehler beim Initialisieren des Chatbots: {e}")
            return None

    return st.session_state.chatbot


def display_sources(sources: list[dict]):
    """Display source citations in an expandable section."""

    if not sources:
        return

    with st.expander("Zitierte Entscheidungen", expanded=False):
        for source in sources:
            celex = source.get('celex', 'Unbekannt')
            case_number = source.get('case_number', '')
            title = source.get('title', 'Kein Titel')
            eurlex_url = source.get('eurlex_url', '')
            curia_url = source.get('curia_url', '')
            language = source.get('language', 'DE')
            language_display = source.get('language_display', 'Deutsch')

            # Show case number with language indicator if not German
            header = case_number or celex
            if language != "DE":
                header += f" ({language_display})"

            st.markdown(f"**{header}**")

            if title:
                st.markdown(f"*{title[:200]}{'...' if len(title) > 200 else ''}*")

            cols = st.columns(2)
            if eurlex_url:
                cols[0].markdown(f"[EUR-Lex]({eurlex_url})")
            if curia_url:
                cols[1].markdown(f"[CURIA]({curia_url})")

            st.divider()


def main():
    """Main Streamlit application."""

    st.set_page_config(
        page_title="EuGH Chatbot",
        page_icon="EU Flag",
        layout="wide"
    )

    # Header
    st.title("EuGH Rechtsprechungs-Chatbot")
    st.markdown(
        "Stellen Sie Fragen zur Rechtsprechung des Europäischen Gerichtshofs. "
        "Alle Antworten basieren ausschließlich auf tatsächlichen EuGH-Entscheidungen."
    )

    # Sidebar
    with st.sidebar:
        st.header("Einstellungen")

        # API Key input (if not set via environment)
        if not os.getenv("ANTHROPIC_API_KEY"):
            api_key = st.text_input(
                "Anthropic API Key",
                type="password",
                help="Ihr Anthropic API-Schlüssel für Claude"
            )
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key

        # Index & Data stats
        st.header("Datenbank-Status")

        # Count local cases
        case_count = len(list(DATA_DIR.glob("*.json"))) if DATA_DIR.exists() else 0
        st.metric("Lokale Entscheidungen", case_count)

        if INDEX_DIR.exists():
            try:
                store = CaseLawVectorStore(persist_directory=INDEX_DIR)
                stats = store.get_collection_stats()
                st.metric("Indizierte Textabschnitte", stats.get('total_chunks', 0))
            except Exception:
                st.warning("Index-Statistiken nicht verfügbar")
        else:
            st.warning("Kein Index vorhanden")

        # Show last update time
        if DATA_DIR.exists():
            checkpoint = load_checkpoint(DATA_DIR)
            last_update = checkpoint.get("last_download_date")
            if last_update:
                st.caption(f"Letztes Update: {last_update[:10]}")

        st.divider()

        # Update button
        st.header("Daten aktualisieren")
        if st.button("Neue Entscheidungen laden", help="Prüft EUR-Lex auf neue Entscheidungen"):
            with st.spinner("Suche neue Entscheidungen..."):
                new_cases = incremental_update(
                    data_dir=DATA_DIR,
                    delay_seconds=1.0,
                    max_new_cases=50
                )
            if new_cases > 0:
                st.success(f"{new_cases} neue Entscheidungen geladen!")
                # Rebuild index
                with st.spinner("Aktualisiere Suchindex..."):
                    build_index_from_data_dir(DATA_DIR, INDEX_DIR)
                st.success("Index aktualisiert!")
                # Clear chatbot to reload index
                if "chatbot" in st.session_state:
                    del st.session_state.chatbot
                st.rerun()
            else:
                st.info("Keine neuen Entscheidungen gefunden.")

        # Live fallback toggle
        st.session_state.enable_live_fallback = st.checkbox(
            "Live-Suche in älteren Fällen",
            value=st.session_state.get("enable_live_fallback", True),
            help="Wenn aktiviert, wird bei unzureichenden lokalen Ergebnissen "
                 "eine Live-Suche in der gesamten EUR-Lex-Datenbank durchgeführt."
        )

        st.divider()

        # Clear conversation
        if st.button("Gespräch zurücksetzen"):
            if "messages" in st.session_state:
                st.session_state.messages = []
            if "chatbot" in st.session_state:
                st.session_state.chatbot.clear_history()
            st.rerun()

        st.divider()

        # Info
        st.markdown("""
        ### Über diesen Chatbot

        Dieser Chatbot beantwortet Fragen ausschließlich
        auf Grundlage der EuGH-Rechtsprechung.

        **Datenquellen:**
        - EUR-Lex (CELLAR)
        - CURIA

        **Features:**
        - Automatische Updates neuer Entscheidungen
        - Live-Fallback für ältere Fälle
        - Mehrsprachige Unterstützung (DE/EN/FR)

        **Hinweis:** Dies ist kein Ersatz für
        professionelle Rechtsberatung.
        """)

    # Initialize chatbot
    chatbot = init_chatbot()

    # Initialize message history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("sources"):
                display_sources(message["sources"])

    # Chat input
    if prompt := st.chat_input("Ihre Frage zur EuGH-Rechtsprechung..."):
        # Add user message to history
        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            if chatbot:
                # Get live fallback setting
                enable_live_fallback = st.session_state.get("enable_live_fallback", True)

                with st.spinner("Suche relevante Entscheidungen..."):
                    response_placeholder = st.empty()
                    full_response = ""

                    # Stream response
                    def on_token(token: str):
                        nonlocal full_response
                        full_response += token
                        response_placeholder.markdown(full_response + "...")

                    result = chatbot.answer_stream(
                        prompt,
                        on_token=on_token,
                        enable_live_fallback=enable_live_fallback
                    )

                    # Display final response
                    response_placeholder.markdown(result["answer"])

                    # Show info if live fallback was used
                    if result.get("used_live_fallback"):
                        st.info(
                            "Hinweis: Für diese Antwort wurden auch ältere Entscheidungen "
                            "live von EUR-Lex abgerufen, die nicht im lokalen Index waren."
                        )

                    # Display sources
                    if result.get("sources"):
                        display_sources(result["sources"])

                    # Add to history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": result["answer"],
                        "sources": result.get("sources", [])
                    })
            else:
                st.error("Chatbot nicht initialisiert. Bitte überprüfen Sie die Konfiguration.")


# Example questions section
def show_example_questions():
    """Display example questions for users."""

    st.markdown("### Beispielfragen")

    examples = [
        "Was hat der EuGH zum Datenschutz bei internationalen Datentransfers entschieden?",
        "Welche Grundsätze gelten nach der EuGH-Rechtsprechung für die Vorratsdatenspeicherung?",
        "Wie definiert der EuGH den Begriff 'Arbeitnehmer' im Unionsrecht?",
        "Was ist die Rechtsprechung des EuGH zur Arbeitnehmerfreizügigkeit?",
        "Welche Voraussetzungen hat der EuGH für die Staatshaftung entwickelt?"
    ]

    for example in examples:
        if st.button(example, key=example):
            st.session_state.example_question = example


if __name__ == "__main__":
    main()
