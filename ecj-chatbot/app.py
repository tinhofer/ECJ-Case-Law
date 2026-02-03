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
from embeddings import CaseLawVectorStore


# Configuration
INDEX_DIR = Path(__file__).parent / "data" / "index"


def init_chatbot() -> EuGHChatbot | None:
    """Initialize or retrieve the chatbot from session state."""

    if "chatbot" not in st.session_state:
        api_key = os.getenv("ANTHROPIC_API_KEY")

        if not api_key:
            st.error(
                "Bitte setzen Sie die ANTHROPIC_API_KEY Umgebungsvariable "
                "oder geben Sie den API-Schlüssel in der Seitenleiste ein."
            )
            return None

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

        # Index stats
        st.header("Index-Statistiken")
        if INDEX_DIR.exists():
            try:
                store = CaseLawVectorStore(persist_directory=INDEX_DIR)
                stats = store.get_collection_stats()
                st.metric("Indizierte Textabschnitte", stats.get('total_chunks', 0))
            except Exception:
                st.warning("Index-Statistiken nicht verfügbar")
        else:
            st.warning("Kein Index vorhanden")

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
                with st.spinner("Suche relevante Entscheidungen..."):
                    response_placeholder = st.empty()
                    full_response = ""

                    # Stream response
                    def on_token(token: str):
                        nonlocal full_response
                        full_response += token
                        response_placeholder.markdown(full_response + "...")

                    result = chatbot.answer_stream(prompt, on_token=on_token)

                    # Display final response
                    response_placeholder.markdown(result["answer"])

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
