"""
EuGH Chatbot - Streamlit Web Application

A web interface for the EuGH case law chatbot.

Run with: streamlit run app.py
"""

import os
import sys
from pathlib import Path

# Check Python version compatibility before importing dependencies
if sys.version_info >= (3, 14):
    print(
        "WARNING: Python 3.14+ is not yet supported by chromadb.\n"
        "Please use Python 3.11-3.13.\n"
        "You can install Python 3.13 from https://www.python.org/downloads/\n"
        "Then run: py -3.13 -m streamlit run app.py"
    )
    sys.exit(1)

import streamlit as st

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import get_config, set_data_dir, Config
from rag_pipeline import create_chatbot, EuGHChatbot
from embeddings import CaseLawVectorStore, build_index_from_data_dir
from data_acquisition import (
    incremental_update,
    load_checkpoint,
    download_case_law_batch,
    download_topic_corpora,
    DataAcquisitionError,
    CHECKPOINT_FILE
)


def _case_files(cases_dir: Path) -> list[Path]:
    """Actual case documents on disk (excluding the bookkeeping checkpoint)."""
    if not cases_dir.exists():
        return []
    return [f for f in cases_dir.glob("*.json") if f.name != CHECKPOINT_FILE]


# Get configuration
config = get_config()


def _make_progress_callback(label: str):
    """Create a download progress callback that drives a Streamlit progress bar."""
    progress_bar = st.progress(0, text=label)

    def callback(done: int, total: int, celex: str):
        if total <= 0:
            return
        fraction = min(done / total, 1.0)
        text = f"{label} ({done}/{total})"
        if celex:
            text += f" – {celex}"
        progress_bar.progress(fraction, text=text)

    return callback


def show_data_error(e: Exception):
    """Display a data acquisition error with remediation hints."""
    st.error(
        f"**Fehler beim Datenabruf von EUR-Lex:**\n\n{e}\n\n"
        "**Mögliche Lösungen:**\n"
        "- Internetverbindung prüfen\n"
        "- Firmen-Firewall/Proxy: Zugriff auf `publications.europa.eu` und "
        "`eur-lex.europa.eu` freigeben\n"
        "- Später erneut versuchen (EUR-Lex kann zeitweise überlastet sein)\n"
        "- Zur Diagnose im Terminal ausführen: `python diagnose.py`"
    )


def download_topics_if_configured() -> int:
    """Download topic corpora (all decisions citing configured acts).

    Returns the number of newly downloaded documents; EUR-Lex problems
    are shown as a warning instead of aborting (the main corpus works).
    """
    if not config.topic_celex:
        return 0
    try:
        return download_topic_corpora(
            output_dir=config.cases_dir,
            topic_celex=config.topic_celex,
            delay_seconds=config.download_delay,
            celex_doc_types=config.celex_doc_types,
            progress_callback=_make_progress_callback(
                f"Lade Themen-Korpus ({', '.join(config.topic_celex)})")
        )
    except DataAcquisitionError as e:
        st.warning(f"Themen-Korpus übersprungen (EUR-Lex nicht erreichbar): {e}")
        return 0


def initialize_data_and_index(auto_update: bool = True) -> bool:
    """
    Initialize or update the case law data and search index.

    Uses paths from global config. If data exists in cloud folder but no local
    index, automatically builds the index.

    Args:
        auto_update: Whether to check for new cases on startup

    Returns:
        True if initialization was successful
    """
    config.ensure_directories()

    cases_dir = config.cases_dir
    index_dir = config.index_dir

    # Check if we have any data. The checkpoint file must not count:
    # a failed download leaves it behind, and counting it as a "case"
    # made the app skip the download entirely and build an empty index.
    existing_cases = _case_files(cases_dir)
    has_data = len(existing_cases) > 0

    # Check if index exists
    index_exists = index_dir.exists() and any(index_dir.iterdir())

    # Case 1: Data exists but no index (e.g., synced from cloud on new device)
    if has_data and not index_exists:
        st.info(f"Daten gefunden ({len(existing_cases)} Entscheidungen), aber kein Index. Erstelle Index...")
        with st.spinner("Indiziere Dokumente (beim ersten Mal wird das Embedding-Modell heruntergeladen)..."):
            build_index_from_data_dir(cases_dir, index_dir)
        st.success("Index erstellt!")
        return True

    # Case 2: No data - initial download
    if not has_data:
        initial_year = config.initial_year
        st.info(
            f"Erste Initialisierung: Lade bis zu {config.max_initial_cases} "
            f"EuGH-Urteile seit {initial_year} (neueste zuerst). "
            "Dies dauert je nach Anzahl einige Minuten bis Stunden – der "
            "Fortschritt wird unten angezeigt und bereits geladene "
            "Entscheidungen bleiben bei einem Abbruch erhalten."
        )
        try:
            downloaded = download_case_law_batch(
                output_dir=cases_dir,
                year_from=initial_year,
                delay_seconds=config.download_delay,
                subject_areas=config.active_subject_areas,
                subject_keywords=config.subject_keywords,
                max_cases=config.max_initial_cases,
                celex_doc_types=config.celex_doc_types,
                progress_callback=_make_progress_callback("Lade Entscheidungen von EUR-Lex")
            )
        except DataAcquisitionError as e:
            show_data_error(e)
            return False

        # Topic corpora (all decisions citing configured legal acts)
        downloaded += download_topics_if_configured()

        if downloaded == 0:
            st.error(
                "Es konnten keine Entscheidungen heruntergeladen werden. "
                "Bitte führen Sie `python diagnose.py` aus, um die Ursache zu finden."
            )
            return False

        st.success(f"{downloaded} Entscheidungen heruntergeladen.")

        # Build initial index
        st.info("Erstelle Suchindex...")
        with st.spinner("Indiziere Dokumente (beim ersten Mal wird das Embedding-Modell heruntergeladen)..."):
            build_index_from_data_dir(cases_dir, index_dir)
            st.success("Index erstellt.")

        return True

    # Case 3: Data and index exist - check for updates
    if auto_update:
        checkpoint = load_checkpoint(cases_dir)
        last_update = checkpoint.get("last_download_date") or "Nie"

        try:
            with st.spinner(f"Prüfe auf neue Entscheidungen (letztes Update: {last_update[:10]})..."):
                new_cases = incremental_update(
                    data_dir=cases_dir,
                    delay_seconds=config.download_delay,
                    max_new_cases=config.update_limit,
                    subject_areas=config.active_subject_areas,
                    subject_keywords=config.subject_keywords,
                    initial_year=config.initial_year,
                    max_initial_cases=config.max_initial_cases,
                    celex_doc_types=config.celex_doc_types
                )
        except DataAcquisitionError as e:
            # Existing data still works offline - warn but continue
            st.warning(f"Update übersprungen (EUR-Lex nicht erreichbar): {e}")
            return True

        new_cases += download_topics_if_configured()

        if new_cases > 0:
            st.info(f"{new_cases} neue Entscheidungen gefunden. Aktualisiere Index...")
            with st.spinner("Aktualisiere Suchindex..."):
                build_index_from_data_dir(cases_dir, index_dir)
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

    index_dir = config.index_dir

    # Initialize data and index if needed (only on first run).
    # Only mark as initialized on success, so a failed download is retried
    # on the next rerun instead of leaving the app permanently empty.
    # Also (re-)initialize when there are no actual case documents, even
    # if an (empty) index directory exists from an earlier failed run.
    if "initialized" not in st.session_state:
        index_missing = not index_dir.exists() or not any(index_dir.iterdir())
        if index_missing or not _case_files(config.cases_dir):
            if not initialize_data_and_index(auto_update=auto_update):
                return None
        st.session_state.initialized = True

    if "chatbot" not in st.session_state:
        if not index_dir.exists():
            st.error(
                f"Index-Verzeichnis nicht gefunden: {index_dir}\n\n"
                "Bitte führen Sie zuerst die Datenakquise und Indizierung durch."
            )
            return None

        try:
            st.session_state.chatbot = create_chatbot(
                index_dir, api_key, subject_areas=config.subject_areas
            )
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
        page_icon="⚖️",
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

        # Get status from config
        status = config.get_status()

        # Show storage location
        if config.is_cloud_storage():
            st.success("Cloud-Speicher erkannt")
        st.caption(f"Speicherort: {status['data_dir']}")

        # Count local cases
        st.metric("Lokale Entscheidungen", status['cases_count'])

        if status['index_exists']:
            try:
                store = CaseLawVectorStore(persist_directory=config.index_dir)
                stats = store.get_collection_stats()
                st.metric("Indizierte Textabschnitte", stats.get('total_chunks', 0))
            except Exception:
                st.warning("Index-Statistiken nicht verfügbar")
        else:
            st.warning("Kein Index vorhanden")

        # Show last update time
        if config.cases_dir.exists():
            checkpoint = load_checkpoint(config.cases_dir)
            last_update = checkpoint.get("last_download_date")
            if last_update:
                st.caption(f"Letztes Update: {last_update[:10]}")

        st.divider()

        # Update button
        st.header("Daten aktualisieren")
        if st.button("Neue Entscheidungen laden", help="Prüft EUR-Lex auf neue Entscheidungen"):
            try:
                with st.spinner("Suche neue Entscheidungen..."):
                    new_cases = incremental_update(
                        data_dir=config.cases_dir,
                        delay_seconds=config.download_delay,
                        max_new_cases=config.update_limit,
                        subject_areas=config.active_subject_areas,
                        subject_keywords=config.subject_keywords,
                        initial_year=config.initial_year,
                        max_initial_cases=config.max_initial_cases,
                        celex_doc_types=config.celex_doc_types
                    )
            except DataAcquisitionError as e:
                show_data_error(e)
                new_cases = 0
            new_cases += download_topics_if_configured()
            if new_cases > 0:
                st.success(f"{new_cases} neue Entscheidungen geladen!")
                # Rebuild index
                with st.spinner("Aktualisiere Suchindex..."):
                    build_index_from_data_dir(config.cases_dir, config.index_dir)
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
            value=st.session_state.get("enable_live_fallback", config.enable_live_fallback),
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
