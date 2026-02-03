"""
EuGH RAG Pipeline Module

This module implements the Retrieval-Augmented Generation pipeline
for answering questions based on EuGH case law.
"""

import os
from pathlib import Path
from typing import Callable

from anthropic import Anthropic
from dotenv import load_dotenv

from embeddings import CaseLawVectorStore


load_dotenv()


# System prompt for the EuGH chatbot
SYSTEM_PROMPT = """Du bist ein juristischer Assistent, der Fragen ausschließlich auf Grundlage der Rechtsprechung des Europäischen Gerichtshofs (EuGH) beantwortet.

WICHTIGE REGELN:
1. Beantworte Fragen NUR basierend auf den bereitgestellten EuGH-Entscheidungen
2. Wenn die bereitgestellten Dokumente keine relevanten Informationen enthalten, sage das klar
3. Zitiere IMMER die relevanten Entscheidungen mit CELEX-Nummer und verlinke sie
4. Erkläre komplexe juristische Konzepte verständlich
5. Wenn du dir unsicher bist, sage das
6. Erfinde KEINE Rechtsprechung oder Urteile

FORMAT DER QUELLENANGABEN:
- Nenne die Rechtssache (z.B. "Rs. C-311/18 Schrems II")
- Verlinke zu EUR-Lex: [CELEX-Nummer](URL)
- Gib das Datum des Urteils an

Antworte auf Deutsch, es sei denn, der Nutzer fragt auf einer anderen Sprache."""


def format_context(search_results: list[dict]) -> str:
    """
    Format search results into context for the LLM.

    Args:
        search_results: List of search results from the vector store

    Returns:
        Formatted context string
    """

    context_parts = []

    for i, result in enumerate(search_results, 1):
        metadata = result.get('metadata', {})

        header = f"--- Dokument {i} ---"
        celex = metadata.get('celex', 'Unbekannt')
        title = metadata.get('title', 'Kein Titel')
        date = metadata.get('date', 'Unbekannt')
        case_number = metadata.get('case_number', '')
        eurlex_url = metadata.get('eurlex_url', '')
        document_type = metadata.get('document_type', 'Urteil')

        info = f"""
{header}
CELEX: {celex}
Rechtssache: {case_number}
Typ: {document_type}
Datum: {date}
Titel: {title}
EUR-Lex: {eurlex_url}

Textauszug:
{result.get('text', '')}
"""
        context_parts.append(info)

    return "\n".join(context_parts)


class EuGHChatbot:
    """
    RAG-based chatbot for EuGH case law questions.
    """

    def __init__(
        self,
        vector_store: CaseLawVectorStore,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        n_results: int = 5
    ):
        """
        Initialize the chatbot.

        Args:
            vector_store: CaseLawVectorStore instance
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
            model: Claude model to use
            n_results: Number of documents to retrieve for context
        """

        self.vector_store = vector_store
        self.model = model
        self.n_results = n_results

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = Anthropic(api_key=api_key)
        self.conversation_history = []

    def search_relevant_cases(self, query: str) -> list[dict]:
        """
        Search for relevant case law for a query.

        Args:
            query: User's question

        Returns:
            List of relevant search results
        """

        results = self.vector_store.search(
            query=query,
            n_results=self.n_results * 2  # Get more to allow deduplication
        )

        # Deduplicate to unique cases
        unique_cases = self.vector_store.get_unique_cases(results)

        return unique_cases[:self.n_results]

    def answer(self, question: str) -> dict:
        """
        Answer a question based on EuGH case law.

        Args:
            question: User's question

        Returns:
            Dict with answer, sources, and metadata
        """

        # Retrieve relevant documents
        search_results = self.search_relevant_cases(question)

        if not search_results:
            return {
                "answer": "Es wurden keine relevanten EuGH-Entscheidungen zu Ihrer Frage gefunden. "
                         "Bitte formulieren Sie Ihre Frage anders oder stellen Sie eine andere Frage.",
                "sources": [],
                "context_used": False
            }

        # Format context
        context = format_context(search_results)

        # Build the prompt
        user_message = f"""Basierend auf den folgenden EuGH-Entscheidungen, beantworte die Frage des Nutzers.

RELEVANTE DOKUMENTE:
{context}

FRAGE DES NUTZERS:
{question}

Beantworte die Frage basierend auf den obigen Dokumenten. Zitiere die relevanten Entscheidungen mit Links."""

        # Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Call Claude API
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=self.conversation_history
        )

        assistant_message = response.content[0].text

        # Add response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        # Extract sources
        sources = []
        for result in search_results:
            metadata = result.get('metadata', {})
            sources.append({
                "celex": metadata.get('celex'),
                "case_number": metadata.get('case_number'),
                "title": metadata.get('title'),
                "date": metadata.get('date'),
                "eurlex_url": metadata.get('eurlex_url'),
                "curia_url": metadata.get('curia_url')
            })

        return {
            "answer": assistant_message,
            "sources": sources,
            "context_used": True,
            "model": self.model
        }

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

    def answer_stream(
        self,
        question: str,
        on_token: Callable[[str], None] | None = None
    ) -> dict:
        """
        Answer a question with streaming response.

        Args:
            question: User's question
            on_token: Callback function for each token

        Returns:
            Dict with answer, sources, and metadata
        """

        # Retrieve relevant documents
        search_results = self.search_relevant_cases(question)

        if not search_results:
            return {
                "answer": "Es wurden keine relevanten EuGH-Entscheidungen gefunden.",
                "sources": [],
                "context_used": False
            }

        # Format context
        context = format_context(search_results)

        # Build the prompt
        user_message = f"""Basierend auf den folgenden EuGH-Entscheidungen, beantworte die Frage des Nutzers.

RELEVANTE DOKUMENTE:
{context}

FRAGE DES NUTZERS:
{question}

Beantworte die Frage basierend auf den obigen Dokumenten. Zitiere die relevanten Entscheidungen mit Links."""

        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Stream response
        full_response = ""

        with self.client.messages.stream(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=self.conversation_history
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                if on_token:
                    on_token(text)

        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })

        # Extract sources
        sources = []
        for result in search_results:
            metadata = result.get('metadata', {})
            sources.append({
                "celex": metadata.get('celex'),
                "case_number": metadata.get('case_number'),
                "title": metadata.get('title'),
                "eurlex_url": metadata.get('eurlex_url')
            })

        return {
            "answer": full_response,
            "sources": sources,
            "context_used": True
        }


def create_chatbot(
    index_dir: Path | str,
    api_key: str | None = None
) -> EuGHChatbot:
    """
    Create a chatbot instance with an existing index.

    Args:
        index_dir: Path to the vector store index
        api_key: Optional API key

    Returns:
        Configured EuGHChatbot instance
    """

    vector_store = CaseLawVectorStore(persist_directory=index_dir)
    return EuGHChatbot(vector_store=vector_store, api_key=api_key)


if __name__ == "__main__":
    # Example usage
    base_dir = Path(__file__).parent.parent
    index_dir = base_dir / "data" / "index"

    if not index_dir.exists():
        print("Index not found. Please run embeddings.py first.")
        exit(1)

    chatbot = create_chatbot(index_dir)

    print("EuGH Chatbot gestartet. Stellen Sie Ihre Fragen (Strg+C zum Beenden).\n")

    while True:
        try:
            question = input("Sie: ").strip()
            if not question:
                continue

            print("\nAssistent: ", end="", flush=True)
            result = chatbot.answer_stream(
                question,
                on_token=lambda t: print(t, end="", flush=True)
            )
            print("\n")

            if result["sources"]:
                print("Quellen:")
                for source in result["sources"]:
                    print(f"  - {source['case_number']}: {source['eurlex_url']}")
                print()

        except KeyboardInterrupt:
            print("\n\nAuf Wiedersehen!")
            break
