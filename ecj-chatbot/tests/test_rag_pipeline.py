"""Tests for the rag_pipeline module."""

import os
from unittest.mock import patch, MagicMock

import pytest

from rag_pipeline import format_context, EuGHChatbot, SYSTEM_PROMPT
from data_acquisition import CaseLawDocument


class TestFormatContext:
    def test_formats_single_result(self):
        results = [{
            "text": "Some judgment text.",
            "metadata": {
                "celex": "62020CJ0311",
                "title": "Schrems II",
                "date": "2020-07-16",
                "case_number": "C-311/18",
                "eurlex_url": "https://eur-lex.europa.eu/...",
                "document_type": "Judgment",
                "language": "DE",
            },
        }]
        ctx = format_context(results)
        assert "62020CJ0311" in ctx
        assert "Schrems II" in ctx
        assert "2020-07-16" in ctx
        assert "Some judgment text." in ctx

    def test_non_german_shows_language_note(self):
        results = [{
            "text": "English text.",
            "metadata": {
                "celex": "X", "title": "Title", "date": "2020-01-01",
                "case_number": "", "eurlex_url": "",
                "document_type": "Judgment", "language": "EN",
            },
        }]
        ctx = format_context(results)
        assert "Englisch" in ctx
        assert "Quelle auf Englisch" in ctx

    def test_german_has_no_language_note(self):
        results = [{
            "text": "Deutscher Text.",
            "metadata": {
                "celex": "X", "title": "Title", "date": "2020-01-01",
                "case_number": "", "eurlex_url": "",
                "document_type": "Judgment", "language": "DE",
            },
        }]
        ctx = format_context(results)
        assert "Quelle auf" not in ctx

    def test_empty_results(self):
        ctx = format_context([])
        assert ctx == ""

    def test_multiple_results_numbered(self):
        results = [
            {
                "text": f"Text {i}",
                "metadata": {
                    "celex": f"CELEX{i}", "title": f"Title {i}",
                    "date": "2020-01-01", "case_number": "",
                    "eurlex_url": "", "document_type": "Judgment",
                    "language": "DE",
                },
            }
            for i in range(3)
        ]
        ctx = format_context(results)
        assert "Dokument 1" in ctx
        assert "Dokument 2" in ctx
        assert "Dokument 3" in ctx


def _make_chatbot(**kwargs):
    """Create an EuGHChatbot with mocked dependencies."""
    mock_store = kwargs.pop("vector_store", MagicMock())
    kwargs.setdefault("cases_dir", "/nonexistent-cases-dir")
    with patch("rag_pipeline.Anthropic"):
        bot = EuGHChatbot(
            vector_store=mock_store,
            api_key="test-key",
            **kwargs,
        )
    bot.client = MagicMock()
    return bot


def _text_response(text, stop_reason="end_turn"):
    """Build a fake final message containing one text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = stop_reason
    return resp


def _tool_use_response(name, tool_input, tool_id="toolu_1"):
    """Build a fake final message requesting one tool call."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = tool_input
    block.id = tool_id
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "tool_use"
    return resp


def _fake_stream(bot, responses):
    """Make bot.client.messages.stream return the given messages in order."""
    contexts = []
    for resp in responses:
        inner = MagicMock()
        inner.text_stream = iter(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
        inner.get_final_message = MagicMock(return_value=resp)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=inner)
        ctx.__exit__ = MagicMock(return_value=False)
        contexts.append(ctx)
    bot.client.messages.stream = MagicMock(side_effect=contexts)


class TestExtractSearchTerms:
    def test_removes_german_stopwords(self):
        bot = _make_chatbot()
        terms = bot._extract_search_terms(
            "Was hat der EuGH zum Datenschutz entschieden?"
        )
        assert "was" not in terms
        assert "hat" not in terms
        assert "der" not in terms
        assert "datenschutz" in terms

    def test_removes_english_stopwords(self):
        bot = _make_chatbot()
        terms = bot._extract_search_terms(
            "What is the ruling on data protection?"
        )
        assert "what" not in terms
        assert "the" not in terms

    def test_returns_max_five_terms(self):
        bot = _make_chatbot()
        terms = bot._extract_search_terms(
            "Datenschutz Grundrechte Arbeitnehmer Freizügigkeit "
            "Staatshaftung Vorratsdaten Richtlinie Verordnung"
        )
        assert len(terms) <= 5

    def test_filters_short_words(self):
        bot = _make_chatbot()
        terms = bot._extract_search_terms("EU law is ok for us")
        assert "eu" not in terms
        assert "is" not in terms
        assert "ok" not in terms

    def test_empty_query(self):
        bot = _make_chatbot()
        terms = bot._extract_search_terms("")
        assert terms == []


class TestEuGHChatbot:
    def test_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("rag_pipeline.Anthropic"):
                with pytest.raises(ValueError, match="API key required"):
                    EuGHChatbot(vector_store=MagicMock(), api_key=None)

    def test_clear_history(self):
        bot = _make_chatbot()
        bot.conversation_history = [{"role": "user", "content": "test"}]
        bot.clear_history()
        assert bot.conversation_history == []

    def test_answer_no_tools_no_sources(self):
        bot = _make_chatbot()
        _fake_stream(bot, [_text_response("Bitte präzisieren Sie Ihre Frage.")])
        result = bot.answer("test question", enable_live_fallback=False)
        assert result["context_used"] is False
        assert result["sources"] == []
        assert "präzisieren" in result["answer"]

    def test_answer_with_local_search_tool(self):
        bot = _make_chatbot()
        search_results = [{
            "text": "Judgment text.",
            "metadata": {
                "celex": "62020CJ0311", "case_number": "C-311/18",
                "title": "Schrems II", "date": "2020-07-16",
                "eurlex_url": "https://eur-lex.europa.eu/...",
                "curia_url": "https://curia.europa.eu/...",
                "language": "DE", "court": "Court of Justice",
                "document_type": "Judgment",
            },
            "distance": 0.5,
        }]
        bot.vector_store.search.return_value = search_results
        bot.vector_store.get_unique_cases.return_value = search_results

        _fake_stream(bot, [
            _tool_use_response("search_local_judgments", {"query": "Datenschutz"}),
            _text_response("Claude's answer about Schrems II."),
        ])

        result = bot.answer("Datenschutz?", enable_live_fallback=False)
        assert result["context_used"] is True
        assert len(result["sources"]) == 1
        assert result["sources"][0]["celex"] == "62020CJ0311"
        assert "Claude's answer" in result["answer"]
        assert result["used_live_fallback"] is False

    def test_answer_appends_to_conversation_history(self):
        bot = _make_chatbot()
        _fake_stream(bot, [_text_response("Answer")])

        bot.answer("Question?", enable_live_fallback=False)
        assert len(bot.conversation_history) == 2
        assert bot.conversation_history[0] == {"role": "user", "content": "Question?"}
        assert bot.conversation_history[1]["role"] == "assistant"
        assert "Answer" in bot.conversation_history[1]["content"]

    def test_answer_full_text_tool_marks_source(self, tmp_path):
        import json as _json
        case = {
            "celex": "62020CJ0311", "title": "Schrems II", "date": "2020-07-16",
            "case_number": "C-311/18", "court": "Court of Justice",
            "document_type": "Judgment", "text": "Volltext " * 200,
            "eurlex_url": "https://eur-lex.europa.eu/x", "curia_url": None,
            "ecli": None, "keywords": [], "language": "DE",
        }
        (tmp_path / "62020CJ0311.json").write_text(_json.dumps(case), encoding="utf-8")
        bot = _make_chatbot(cases_dir=tmp_path)

        _fake_stream(bot, [
            _tool_use_response("get_full_judgment", {"reference": "C-311/18"}),
            _text_response("Analyse des Urteils."),
        ])

        result = bot.answer("Analysiere C-311/18", enable_live_fallback=False)
        assert result["sources"][0]["celex"] == "62020CJ0311"
        assert result["sources"][0]["full_text"] is True
        # The tool result handed to Claude contained the full text marker
        second_call = bot.client.messages.stream.call_args_list[1]
        tool_result_msg = second_call.kwargs["messages"][-1]
        assert "VOLLSTÄNDIGER TEXT" in tool_result_msg["content"][0]["content"]

    def test_answer_live_tool_only_when_enabled(self):
        bot = _make_chatbot()
        _fake_stream(bot, [_text_response("ok"), _text_response("ok")])
        bot.answer("Frage?", enable_live_fallback=False)
        tools_off = bot.client.messages.stream.call_args_list[0].kwargs["tools"]
        assert all(t["name"] != "search_eurlex_live" for t in tools_off)

        _fake_stream(bot, [_text_response("ok")])
        bot.answer("Frage?", enable_live_fallback=True)
        tools_on = bot.client.messages.stream.call_args_list[0].kwargs["tools"]
        assert any(t["name"] == "search_eurlex_live" for t in tools_on)

    def test_answer_stops_at_iteration_limit(self):
        bot = _make_chatbot()
        bot.vector_store.search.return_value = []
        bot.vector_store.get_unique_cases.return_value = []
        # Model keeps requesting tools forever
        _fake_stream(bot, [
            _tool_use_response("search_local_judgments", {"query": f"q{i}"})
            for i in range(bot.MAX_TOOL_ITERATIONS + 2)
        ])
        result = bot.answer("Frage?", enable_live_fallback=False)
        assert bot.client.messages.stream.call_count == bot.MAX_TOOL_ITERATIONS
        assert "Recherche-Limit" in result["answer"]


class TestSearchRelevantCases:
    def test_returns_local_results_when_relevant(self):
        bot = _make_chatbot(n_results=3)
        results = [{
            "text": "text", "metadata": {"celex": "A"}, "distance": 0.5,
        }]
        bot.vector_store.search.return_value = results
        bot.vector_store.get_unique_cases.return_value = results

        cases, used_fallback = bot.search_relevant_cases(
            "test", enable_live_fallback=True, min_relevance_threshold=1.5,
        )
        assert len(cases) == 1
        assert used_fallback is False

    def test_no_fallback_when_disabled(self):
        bot = _make_chatbot(n_results=3)
        bot.vector_store.search.return_value = []
        bot.vector_store.get_unique_cases.return_value = []

        cases, used_fallback = bot.search_relevant_cases(
            "test", enable_live_fallback=False,
        )
        assert used_fallback is False

    @patch("rag_pipeline.live_search_cases")
    @patch("rag_pipeline.fetch_case_on_demand")
    def test_uses_fallback_when_no_relevant_local(self, mock_fetch, mock_live):
        bot = _make_chatbot(n_results=3)
        bot.vector_store.search.return_value = [{
            "text": "text", "metadata": {"celex": "A"}, "distance": 2.0,
        }]
        bot.vector_store.get_unique_cases.return_value = [{
            "text": "text", "metadata": {"celex": "A"}, "distance": 2.0,
        }]

        mock_live.return_value = [{"celex": "LIVE1", "title": "T", "date": "2020-01-01"}]
        mock_fetch.return_value = CaseLawDocument(
            celex="LIVE1", title="T", date="2020-01-01",
            case_number="C-1/20", court="CJ", document_type="J",
            text="Live fetched text " * 100,
            eurlex_url="http://example.com", curia_url=None,
            ecli=None, keywords=[], language="DE",
        )

        cases, used_fallback = bot.search_relevant_cases(
            "Datenschutz Grundrechte",
            enable_live_fallback=True,
            min_relevance_threshold=1.5,
        )
        assert used_fallback is True
        assert any(c["metadata"]["celex"] == "LIVE1" for c in cases)


class TestSystemPrompt:
    def test_system_prompt_is_german(self):
        assert "EuGH" in SYSTEM_PROMPT
        assert "CELEX" in SYSTEM_PROMPT

    def test_system_prompt_mentions_multilingual(self):
        assert "Englisch" in SYSTEM_PROMPT or "English" in SYSTEM_PROMPT
        assert "Französisch" in SYSTEM_PROMPT or "French" in SYSTEM_PROMPT
