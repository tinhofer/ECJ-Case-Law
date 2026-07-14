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

# System prompt for the EuGH chatbot (agentic: the model researches
# via tools before answering)
SYSTEM_PROMPT = """Du bist ein juristischer Rechercheassistent, der Fragen ausschließlich auf Grundlage der Rechtsprechung des Europäischen Gerichtshofs (EuGH) beantwortet. Dir stehen Recherche-Werkzeuge zur Verfügung - nutze sie aktiv und gründlich, bevor du antwortest.

ARBEITSWEISE:
1. Beginne JEDE fachliche Frage mit mindestens einer lokalen semantischen Suche (search_local_judgments). Formuliere bei Bedarf mehrere Suchanfragen mit unterschiedlichen Begriffen.
2. Nennt der Nutzer eine konkrete Rechtssache (z.B. "C-311/18") oder erscheint eine gefundene Entscheidung zentral für die Antwort: Lade ihren VOLLSTÄNDIGEN Text mit get_full_judgment, bevor du sie inhaltlich auswertest oder wörtlich zitierst.
3. Findet die lokale Suche nichts Passendes, suche live in der EUR-Lex-Datenbank (search_eurlex_live, falls verfügbar) und lade vielversprechende Treffer im Volltext.
4. Antworte erst, wenn du genug Material gesammelt hast. Gründlichkeit geht vor Geschwindigkeit.

WICHTIGE REGELN:
1. Beantworte Fragen NUR auf Grundlage der über die Werkzeuge abgerufenen EuGH-Entscheidungen
2. Wenn das abgerufene Material die Frage nicht beantwortet, sage das klar - auch nach gründlicher Suche
3. Zitiere IMMER die relevanten Entscheidungen mit CELEX-Nummer und verlinke sie
4. Wörtliche Zitate nur aus Volltexten, nie aus Suchausschnitten rekonstruieren
5. Erkläre komplexe juristische Konzepte verständlich
6. Erfinde KEINE Rechtsprechung - kein Wissen aus dem Gedächtnis zitieren

MEHRSPRACHIGE QUELLEN:
- Manche Entscheidungen sind nur auf Englisch oder Französisch verfügbar (noch keine deutsche Übersetzung)
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

    # ------------------------------------------------------------------
    # Agentic research loop: Claude decides per question which tools to
    # use - local semantic search, full-text loading, live EUR-Lex search
    # ------------------------------------------------------------------

    MAX_TOOL_ITERATIONS = 8

    def _build_tools(self, enable_live_fallback: bool) -> list[dict]:
        tools = [
            {
                "name": "search_local_judgments",
                "description": (
                    "Semantische Suche in der lokalen Datenbank mit EuGH-Urteilen "
                    "(Volltexte, nach Bedeutung durchsuchbar). Rufe dieses Werkzeug "
                    "bei JEDER fachlichen Frage zuerst auf - gerne mehrfach mit "
                    "unterschiedlichen Formulierungen (deutsche Rechtsbegriffe "
                    "funktionieren am besten). Liefert die relevantesten Passagen "
                    "mehrerer Urteile samt Metadaten."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Suchanfrage in natürlicher Sprache, z.B. 'Pflicht zur Arbeitszeiterfassung leitende Angestellte'"
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_full_judgment",
                "description": (
                    "Lädt den VOLLSTÄNDIGEN Text einer EuGH-Entscheidung. Rufe dieses "
                    "Werkzeug auf, sobald eine konkrete Entscheidung zentral für die "
                    "Antwort ist oder der Nutzer sie namentlich nennt - Suchausschnitte "
                    "reichen für belastbare juristische Aussagen nicht aus. Akzeptiert "
                    "Rechtssachennummer (z.B. 'C-311/18') oder CELEX-Nummer (z.B. "
                    "'62018CJ0311'). Nicht lokal vorhandene Entscheidungen werden live "
                    "von EUR-Lex geholt."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reference": {
                            "type": "string",
                            "description": "Rechtssachennummer oder CELEX-Nummer der Entscheidung"
                        }
                    },
                    "required": ["reference"],
                },
            },
        ]
        if enable_live_fallback:
            tools.append({
                "name": "search_eurlex_live",
                "description": (
                    "Live-Stichwortsuche in der gesamten EUR-Lex-Datenbank (alle "
                    "EuGH-Entscheidungen seit 1954, nur Titel-/Metadaten-Suche). "
                    "Rufe dieses Werkzeug auf, wenn die lokale Suche nichts Passendes "
                    "liefert - z.B. bei älteren Entscheidungen oder Rechtsgebieten "
                    "außerhalb des lokalen Korpus. Vielversprechende Treffer danach "
                    "mit get_full_judgment im Volltext laden."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "1-5 Stichwörter (Begriffe, die im Titel der Entscheidung vorkommen könnten, z.B. Parteinamen oder Rechtssachennummern)"
                        }
                    },
                    "required": ["keywords"],
                },
            })
        return tools

    def _register_source(self, sources: dict, metadata: dict, full_text: bool = False):
        celex = metadata.get("celex")
        if not celex:
            return
        language = metadata.get("language", "DE")
        entry = {
            "celex": celex,
            "case_number": metadata.get("case_number"),
            "title": metadata.get("title"),
            "date": metadata.get("date"),
            "eurlex_url": metadata.get("eurlex_url")
            or f"https://eur-lex.europa.eu/legal-content/{language}/TXT/?uri=CELEX:{celex}",
            "curia_url": metadata.get("curia_url"),
            "language": language,
            "language_display": LANGUAGE_DISPLAY.get(language, language),
            "full_text": full_text,
        }
        existing = sources.get(celex)
        if existing is None or (full_text and not existing.get("full_text")):
            sources[celex] = entry

    def _tool_search_local(self, query: str, sources: dict) -> str:
        results = self.vector_store.search(query=query, n_results=self.n_results * 4)
        unique = self.vector_store.get_unique_cases(results)
        unique = self._attach_additional_chunks(unique, results)[:self.n_results]
        if not unique:
            return ("Keine Treffer im lokalen Index. Versuche eine andere "
                    "Formulierung oder die Live-Suche.")
        for r in unique:
            self._register_source(sources, r.get("metadata", {}))
        return format_context(unique)

    def _tool_full_judgment(self, reference: str, sources: dict, state: dict) -> str:
        docs = self._find_referenced_cases(reference)

        if not docs:
            # Not local: try to fetch live from EUR-Lex
            celex_match = self.CELEX_REF_RE.search(reference.upper())
            celex = celex_match.group(1) if celex_match else None
            if not celex:
                # Look the case number up via live title search
                try:
                    hits = live_search_cases(query_terms=[reference.strip()], limit=3)
                except Exception:
                    hits = []
                celex = hits[0].get("celex") if hits else None
            if celex:
                state["used_live"] = True
                try:
                    doc = fetch_case_on_demand(celex)
                except Exception:
                    doc = None
                if doc:
                    docs = [doc]

        if not docs:
            return (f"Entscheidung '{reference}' wurde weder lokal noch auf "
                    "EUR-Lex gefunden. Bitte Schreibweise prüfen (z.B. 'C-311/18') "
                    "oder per search_eurlex_live nach der Rechtssache suchen.")

        parts = []
        for result in self._full_text_results(docs):
            meta = result["metadata"]
            self._register_source(sources, meta, full_text=True)
            language_display = LANGUAGE_DISPLAY.get(meta.get("language", "DE"),
                                                    meta.get("language", "DE"))
            parts.append(
                f"=== VOLLSTÄNDIGER TEXT ===\n"
                f"CELEX: {meta.get('celex')}\n"
                f"Rechtssache: {meta.get('case_number') or 'unbekannt'}\n"
                f"Typ: {meta.get('document_type')}\n"
                f"Datum: {meta.get('date')}\n"
                f"Sprache: {language_display}\n"
                f"EUR-Lex: {meta.get('eurlex_url')}\n\n"
                f"{result['text']}"
            )
        return "\n\n".join(parts)

    def _tool_search_live(self, keywords: list[str], state: dict) -> str:
        state["used_live"] = True
        try:
            hits = live_search_cases(query_terms=[str(k) for k in keywords][:5],
                                     limit=10, subject_areas=self.subject_areas)
        except Exception as e:
            return f"Live-Suche fehlgeschlagen ({e}). Bitte später erneut versuchen."
        if not hits:
            return ("Keine Treffer in EUR-Lex für diese Stichwörter. Die Suche "
                    "durchsucht nur Entscheidungstitel - andere Begriffe "
                    "(Parteinamen, Rechtssachennummer) versuchen.")
        lines = ["Treffer (Metadaten; Volltext bei Bedarf mit get_full_judgment laden):"]
        for h in hits:
            lines.append(f"- CELEX {h.get('celex')} | {h.get('case_number') or '?'} | "
                         f"{h.get('date') or '?'} | {(h.get('title') or '')[:150]}")
        return "\n".join(lines)

    def _run_tool(self, name: str, tool_input: dict, sources: dict, state: dict) -> str:
        try:
            if name == "search_local_judgments":
                return self._tool_search_local(str(tool_input.get("query", "")), sources)
            if name == "get_full_judgment":
                return self._tool_full_judgment(str(tool_input.get("reference", "")),
                                                sources, state)
            if name == "search_eurlex_live":
                return self._tool_search_live(tool_input.get("keywords", []), state)
            return f"Unbekanntes Werkzeug: {name}"
        except Exception as e:
            return f"Werkzeugfehler ({name}): {e}"

    _TOOL_STATUS_LABELS = {
        "search_local_judgments": "Durchsuche lokale Urteilsdatenbank",
        "get_full_judgment": "Lade Urteil im Volltext",
        "search_eurlex_live": "Suche live in EUR-Lex",
    }

    def _tool_status_line(self, name: str, tool_input: dict) -> str:
        label = self._TOOL_STATUS_LABELS.get(name, name)
        detail = (tool_input.get("query") or tool_input.get("reference")
                  or ", ".join(map(str, tool_input.get("keywords", []))) or "")
        detail = str(detail)[:120]
        return f"\n\n> 🔎 *{label}: {detail}*\n\n"

    def answer(self, question: str, enable_live_fallback: bool = True) -> dict:
        """
        Answer a question based on EuGH case law (agentic research loop).

        Args:
            question: User's question
            enable_live_fallback: Whether the live EUR-Lex search tool is available

        Returns:
            Dict with answer, sources, and metadata
        """
        return self.answer_stream(question, on_token=None,
                                  enable_live_fallback=enable_live_fallback)

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
        Answer a question via an agentic research loop with streaming.

        Claude decides per question which tools to use (local semantic
        search, full-text loading, live EUR-Lex search) and answers only
        from the retrieved material. Thorough questions take 60-90s.

        Args:
            question: User's question
            on_token: Callback for streamed text (including tool status lines)
            enable_live_fallback: Whether the live EUR-Lex search tool is available

        Returns:
            Dict with answer, sources, and metadata
        """
        tools = self._build_tools(enable_live_fallback)
        sources: dict[str, dict] = {}
        state = {"used_live": False}

        # The user question goes into the persistent history as-is; the
        # tool turns of THIS answer stay local to the loop so follow-up
        # questions don't drag megabytes of old tool results along.
        self.conversation_history.append({"role": "user", "content": question})
        messages = list(self.conversation_history)

        answer_parts: list[str] = []

        for _iteration in range(self.MAX_TOOL_ITERATIONS):
            with self.client.messages.stream(
                model=self.model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    if on_token:
                        on_token(text)
                response = stream.get_final_message()

            turn_text = "".join(
                block.text for block in response.content
                if getattr(block, "type", "") == "text"
            )
            if turn_text.strip():
                answer_parts.append(turn_text)

            if response.stop_reason != "tool_use":
                break

            # Execute the requested tools and feed the results back
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, "type", "") != "tool_use":
                    continue
                status = self._tool_status_line(block.name, block.input or {})
                if on_token:
                    on_token(status)
                answer_parts.append(status.strip("\n"))
                result_text = self._run_tool(block.name, block.input or {},
                                             sources, state)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            note = ("\n\n*Hinweis: Recherche-Limit erreicht - die Antwort "
                    "basiert auf dem bis hierhin gesammelten Material.*")
            answer_parts.append(note)
            if on_token:
                on_token(note)

        full_response = "\n\n".join(part for part in answer_parts if part.strip())

        self.conversation_history.append({
            "role": "assistant",
            "content": full_response or "(keine Antwort)"
        })

        return {
            "answer": full_response,
            "sources": list(sources.values()),
            "context_used": bool(sources),
            "model": self.model,
            "used_live_fallback": state["used_live"],
        }


def create_chatbot(
    index_dir: Path | str,
    api_key: str | None = None,
    subject_areas: list[str] | None = None,
    cases_dir: Path | str | None = None
) -> EuGHChatbot:
    """
    Create a chatbot instance with an existing index.

    Args:
        index_dir: Path to the vector store index
        api_key: Optional API key
        subject_areas: Optional EuroVoc descriptor labels to filter live searches
        cases_dir: Directory with case JSON files (for full-text loading)

    Returns:
        Configured EuGHChatbot instance
    """

    vector_store = CaseLawVectorStore(persist_directory=index_dir)
    return EuGHChatbot(
        vector_store=vector_store,
        api_key=api_key,
        subject_areas=subject_areas,
        cases_dir=cases_dir
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
