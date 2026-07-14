"""
EuGH RAG Pipeline Module

This module implements the Retrieval-Augmented Generation pipeline
for answering questions based on EuGH case law.
"""

import os
import re
from pathlib import Path
from typing import Callable

from anthropic import Anthropic
from dotenv import load_dotenv

from config import get_config
from embeddings import CaseLawVectorStore
from data_acquisition import (
    live_search_cases,
    fetch_case_on_demand,
    CaseLawDocument
)


load_dotenv(override=True)  # .env wins over stale system environment variables


# Language display names
LANGUAGE_DISPLAY = {
    "DE": "Deutsch",
    "EN": "Englisch",
    "FR": "Französisch"
}

# System prompt for the EuGH chatbot
SYSTEM_PROMPT = """Du bist ein juristischer Assistent, der Fragen ausschließlich auf Grundlage der Rechtsprechung des Europäischen Gerichtshofs (EuGH) beantwortet.

WICHTIGE REGELN:
1. Beantworte Fragen NUR basierend auf den bereitgestellten EuGH-Entscheidungen
2. Wenn die bereitgestellten Dokumente keine relevanten Informationen enthalten, sage das klar
3. Zitiere IMMER die relevanten Entscheidungen mit CELEX-Nummer und verlinke sie
4. Erkläre komplexe juristische Konzepte verständlich
5. Wenn du dir unsicher bist, sage das
6. Erfinde KEINE Rechtsprechung oder Urteile

MEHRSPRACHIGE QUELLEN:
- Manche Entscheidungen sind nur auf Englisch oder Französisch verfügbar (noch keine deutsche Übersetzung)
- Dies betrifft besonders aktuelle Entscheidungen
- Wenn eine Quelle nicht auf Deutsch ist, erwähne dies kurz: "(Quelle auf Englisch/Französisch)"
- Die Sprache der Quelle ist in den Metadaten angegeben

FORMAT DER QUELLENANGABEN:
- Nenne die Rechtssache (z.B. "Rs. C-311/18 Schrems II")
- Verlinke zu EUR-Lex: [CELEX-Nummer](URL)
- Gib das Datum des Urteils an
- Bei nicht-deutschen Quellen: Sprache in Klammern angeben

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
        language = metadata.get('language', 'DE')
        language_display = LANGUAGE_DISPLAY.get(language, language)

        # Add language note if not German
        language_note = ""
        if language != "DE":
            language_note = f" [Quelle auf {language_display}]"

        info = f"""
{header}
CELEX: {celex}
Rechtssache: {case_number}
Typ: {document_type}
Datum: {date}
Sprache: {language_display}{language_note}
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

    # Case references like "C-311/18", "T-604/18", "F-46/09"
    CASE_REF_RE = re.compile(r"\b([CTF])\s?-\s?(\d{1,4})/(\d{2})\b", re.IGNORECASE)
    # CELEX numbers like "62018CJ0311"
    CELEX_REF_RE = re.compile(r"\b(6\d{4}[A-Z]{2}\d{4})\b")

    # Limits for full-text context (characters). A judgment is typically
    # 50-200k chars; the model's context window handles several at once.
    MAX_FULL_TEXT_DOCS = 3
    MAX_FULL_TEXT_CHARS = 300_000

    def __init__(
        self,
        vector_store: CaseLawVectorStore,
        api_key: str | None = None,
        model: str | None = None,
        n_results: int = 5,
        subject_areas: list[str] | None = None,
        cases_dir: Path | str | None = None
    ):
        """
        Initialize the chatbot.

        Args:
            vector_store: CaseLawVectorStore instance
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
            model: Claude model to use (default: config / ECJ_LLM_MODEL)
            n_results: Number of documents to retrieve for context
            subject_areas: Optional EuroVoc descriptor labels to filter live searches
            cases_dir: Directory with the downloaded case JSON files (for
                full-text loading when a question names a specific case)
        """

        self.vector_store = vector_store
        self.model = model or get_config().llm_model
        self.n_results = n_results
        self.subject_areas = subject_areas
        self.cases_dir = Path(cases_dir) if cases_dir else get_config().cases_dir
        self._case_lookup: dict[str, Path] | None = None

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = Anthropic(api_key=api_key)
        self.conversation_history = []

    # ------------------------------------------------------------------
    # Full-text loading for explicitly referenced cases
    # ------------------------------------------------------------------

    def _build_case_lookup(self) -> dict[str, Path]:
        """Map case numbers ("C-311/18") and CELEX numbers to JSON files."""
        if self._case_lookup is not None:
            return self._case_lookup

        import json as _json
        lookup: dict[str, Path] = {}
        if self.cases_dir.exists():
            for json_file in self.cases_dir.glob("*.json"):
                if json_file.name == "download_checkpoint.json":
                    continue
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = _json.load(f)
                except Exception:
                    continue
                celex = (data.get("celex") or "").upper()
                if celex:
                    lookup[celex] = json_file
                case_number = (data.get("case_number") or "").upper().replace(" ", "")
                if case_number:
                    lookup[case_number] = json_file
        self._case_lookup = lookup
        return lookup

    def _find_referenced_cases(self, question: str) -> list[CaseLawDocument]:
        """Load the FULL text of cases explicitly named in the question.

        When the user names a specific case ("C-311/18", "62018CJ0311"),
        excerpt-based retrieval is not enough for legal analysis - the
        complete judgment is loaded from disk into the context instead.
        """
        import json as _json
        refs: list[str] = []
        for match in self.CASE_REF_RE.finditer(question):
            court, num, year = match.groups()
            refs.append(f"{court.upper()}-{int(num)}/{year}")
        refs.extend(m.upper() for m in self.CELEX_REF_RE.findall(question))

        if not refs:
            return []

        lookup = self._build_case_lookup()
        docs: list[CaseLawDocument] = []
        seen: set[str] = set()
        for ref in refs:
            path = lookup.get(ref.replace(" ", ""))
            if not path:
                continue
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    doc = CaseLawDocument(**_json.load(f))
            except Exception:
                continue
            if doc.celex in seen:
                continue
            seen.add(doc.celex)
            docs.append(doc)
            if len(docs) >= self.MAX_FULL_TEXT_DOCS:
                break
        return docs

    def _full_text_results(self, docs: list[CaseLawDocument]) -> list[dict]:
        """Format full documents as context entries."""
        results = []
        for doc in docs:
            text = doc.text
            if len(text) > self.MAX_FULL_TEXT_CHARS:
                text = text[:self.MAX_FULL_TEXT_CHARS] + "\n[... Text gekürzt ...]"
            results.append({
                "text": text,
                "metadata": {
                    "celex": doc.celex,
                    "title": doc.title,
                    "date": doc.date,
                    "case_number": doc.case_number,
                    "court": doc.court,
                    "document_type": doc.document_type,
                    "eurlex_url": doc.eurlex_url,
                    "curia_url": doc.curia_url,
                    "ecli": doc.ecli,
                    "language": doc.language,
                },
                "distance": None,
                "source": "full_text",
            })
        return results

    def search_relevant_cases(
        self,
        query: str,
        enable_live_fallback: bool = True,
        min_relevance_threshold: float = 1.5
    ) -> tuple[list[dict], bool]:
        """
        Search for relevant case law for a query.

        First searches the local vector index. If no sufficiently relevant
        results are found and enable_live_fallback is True, performs a
        live SPARQL search for older cases.

        Args:
            query: User's question
            enable_live_fallback: Whether to search older cases via SPARQL if needed
            min_relevance_threshold: Maximum distance to consider a result relevant

        Returns:
            Tuple of (search_results, used_live_fallback)
        """
        # First: Search local vector index (extra chunks so that each
        # case can contribute several passages, not just one)
        results = self.vector_store.search(
            query=query,
            n_results=self.n_results * 4
        )

        # Deduplicate to unique cases, then attach the other matching
        # passages of the same case (one 1000-char excerpt per judgment
        # was too little context for legal analysis)
        unique_cases = self.vector_store.get_unique_cases(results)
        unique_cases = self._attach_additional_chunks(unique_cases, results)
        local_results = unique_cases[:self.n_results]

        # Check if we have sufficiently relevant results
        has_relevant_results = False
        if local_results:
            # Check the best result's distance (lower = more relevant)
            best_distance = local_results[0].get('distance', float('inf'))
            has_relevant_results = best_distance < min_relevance_threshold

        # If we have good local results, return them
        if has_relevant_results or not enable_live_fallback:
            return local_results, False

        # Fallback: Live SPARQL search for older/unindexed cases
        print(f"  Local index has no highly relevant results. Searching older cases...")

        # Extract key terms from the query for SPARQL search
        query_terms = self._extract_search_terms(query)

        if not query_terms:
            return local_results, False

        # Search without year restriction to include older cases.
        # Live search is best-effort: a network problem must never crash
        # a chat turn, so fall back to local results on any error.
        try:
            live_cases = live_search_cases(
                query_terms=query_terms,
                limit=self.n_results,
                subject_areas=self.subject_areas
            )
        except Exception as e:
            print(f"  Live fallback search failed: {e}")
            return local_results, False

        if not live_cases:
            return local_results, False

        # Fetch full documents for live results
        live_results = []
        for case_meta in live_cases:
            celex = case_meta.get('celex')
            if not celex:
                continue

            # Fetch the document on-demand (best-effort)
            try:
                doc = fetch_case_on_demand(celex)
            except Exception:
                continue
            if doc:
                # Format as search result
                live_results.append({
                    "text": doc.text[:2000],  # First 2000 chars as preview
                    "metadata": {
                        "celex": doc.celex,
                        "title": doc.title,
                        "date": doc.date,
                        "case_number": doc.case_number,
                        "court": doc.court,
                        "document_type": doc.document_type,
                        "eurlex_url": doc.eurlex_url,
                        "curia_url": doc.curia_url,
                        "ecli": doc.ecli,
                        "language": doc.language
                    },
                    "distance": None,  # No distance for live results
                    "source": "live_search"
                })

        # Combine: prioritize live results (they matched the search terms),
        # but include local results as additional context
        combined = live_results[:self.n_results]

        # Fill remaining slots with local results (if any)
        seen_celex = {r['metadata']['celex'] for r in combined}
        for local_r in local_results:
            if len(combined) >= self.n_results:
                break
            if local_r['metadata'].get('celex') not in seen_celex:
                combined.append(local_r)

        return combined, len(live_results) > 0

    def _attach_additional_chunks(
        self,
        unique_cases: list[dict],
        all_results: list[dict],
        max_chunks: int = 3
    ) -> list[dict]:
        """Combine up to max_chunks matching passages per case into one text."""
        if not isinstance(all_results, list) or not isinstance(unique_cases, list):
            return unique_cases

        by_celex: dict[str, list[str]] = {}
        for r in all_results:
            try:
                celex = r["metadata"].get("celex", "")
                text = r.get("text", "")
            except (TypeError, AttributeError, KeyError):
                return unique_cases
            if celex and text:
                by_celex.setdefault(celex, []).append(text)

        enriched = []
        for case in unique_cases:
            celex = case.get("metadata", {}).get("celex", "")
            chunks = by_celex.get(celex, [])
            if len(chunks) > 1:
                case = dict(case)
                case["text"] = "\n[...]\n".join(chunks[:max_chunks])
            enriched.append(case)
        return enriched

    def _extract_search_terms(self, query: str) -> list[str]:
        """
        Extract meaningful search terms from a user query.

        Args:
            query: User's question

        Returns:
            List of search terms for SPARQL query
        """
        # Remove common German question words and stopwords
        stopwords = {
            'was', 'wie', 'wer', 'wo', 'wann', 'warum', 'welche', 'welcher',
            'welches', 'hat', 'haben', 'ist', 'sind', 'der', 'die', 'das',
            'ein', 'eine', 'eines', 'und', 'oder', 'aber', 'für', 'mit',
            'bei', 'nach', 'von', 'zu', 'zur', 'zum', 'im', 'in', 'an',
            'auf', 'über', 'unter', 'durch', 'gegen', 'ohne', 'bis',
            'the', 'is', 'are', 'was', 'were', 'has', 'have', 'what',
            'which', 'who', 'how', 'when', 'where', 'why', 'eugh', 'gerichtshof'
        }

        # Extract words (alphanumeric sequences)
        words = re.findall(r'\b[a-zA-ZäöüÄÖÜß]{3,}\b', query.lower())

        # Filter stopwords and keep meaningful terms
        terms = [w for w in words if w not in stopwords]

        # Return top terms (max 5)
        return terms[:5]

    def answer(self, question: str, enable_live_fallback: bool = True) -> dict:
        """
        Answer a question based on EuGH case law.

        Args:
            question: User's question
            enable_live_fallback: Whether to search older cases if local index has no results

        Returns:
            Dict with answer, sources, and metadata
        """

        # Retrieve relevant documents (with optional live fallback)
        search_results, used_live_fallback = self.search_relevant_cases(
            question,
            enable_live_fallback=enable_live_fallback
        )

        if not search_results:
            return {
                "answer": "Es wurden keine relevanten EuGH-Entscheidungen zu Ihrer Frage gefunden. "
                         "Bitte formulieren Sie Ihre Frage anders oder stellen Sie eine andere Frage.",
                "sources": [],
                "context_used": False,
                "used_live_fallback": False
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
            language = metadata.get('language', 'DE')
            sources.append({
                "celex": metadata.get('celex'),
                "case_number": metadata.get('case_number'),
                "title": metadata.get('title'),
                "date": metadata.get('date'),
                "eurlex_url": metadata.get('eurlex_url'),
                "curia_url": metadata.get('curia_url'),
                "language": language,
                "language_display": LANGUAGE_DISPLAY.get(language, language)
            })

        return {
            "answer": assistant_message,
            "sources": sources,
            "context_used": True,
            "model": self.model,
            "used_live_fallback": used_live_fallback
        }

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

    def answer_stream(
        self,
        question: str,
        on_token: Callable[[str], None] | None = None,
        enable_live_fallback: bool = True
    ) -> dict:
        """
        Answer a question with streaming response.

        Args:
            question: User's question
            on_token: Callback function for each token
            enable_live_fallback: Whether to search older cases if local index has no results

        Returns:
            Dict with answer, sources, and metadata
        """

        # Retrieve relevant documents (with optional live fallback)
        search_results, used_live_fallback = self.search_relevant_cases(
            question,
            enable_live_fallback=enable_live_fallback
        )

        if not search_results:
            return {
                "answer": "Es wurden keine relevanten EuGH-Entscheidungen gefunden.",
                "sources": [],
                "context_used": False,
                "used_live_fallback": False
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
            language = metadata.get('language', 'DE')
            sources.append({
                "celex": metadata.get('celex'),
                "case_number": metadata.get('case_number'),
                "title": metadata.get('title'),
                "eurlex_url": metadata.get('eurlex_url'),
                "language": language,
                "language_display": LANGUAGE_DISPLAY.get(language, language)
            })

        return {
            "answer": full_response,
            "sources": sources,
            "context_used": True,
            "used_live_fallback": used_live_fallback
        }


def create_chatbot(
    index_dir: Path | str,
    api_key: str | None = None,
    subject_areas: list[str] | None = None
) -> EuGHChatbot:
    """
    Create a chatbot instance with an existing index.

    Args:
        index_dir: Path to the vector store index
        api_key: Optional API key
        subject_areas: Optional EuroVoc descriptor labels to filter live searches

    Returns:
        Configured EuGHChatbot instance
    """

    vector_store = CaseLawVectorStore(persist_directory=index_dir)
    return EuGHChatbot(
        vector_store=vector_store,
        api_key=api_key,
        subject_areas=subject_areas
    )


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
