"""Test suite for AgentIntelligence v0.5.0.

Coverage:
  - TestTools            : execute_tool output format + graceful fallback cases
  - TestThinkingExtract  : <think> tag parsing, reasoning_content field, edge cases
  - TestAgentLoop        : ReAct loop (direct answer, tool call, max_iterations, no-tools LLM)
  - TestAgentServer      : health / query / thinking-toggle (FastAPI TestClient)
  - TestOpenAICompatTools: generate_with_tools params, thinking extra_body, exception fallback
  - TestLauncherAgent    : Agent card in HTML, pollAgent + toggleThinking JS present
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ret_result(text: str = "code snippet", source: str = "src/foo.py", score: float = 0.85):
    """Minimal RetrievalResult-like mock."""
    r = MagicMock()
    r.chunk = {"text": text, "source": source}
    r.score = score
    return r


def _make_tool_call(name: str, arguments: dict, call_id: str = "call_1"):
    """Mock ChatCompletionMessage tool_call object."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    tc.model_dump.return_value = {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }
    return tc


def _make_msg(content: str = "", tool_calls=None, reasoning_content=None):
    """Mock ChatCompletionMessage object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    msg.reasoning_content = reasoning_content
    return msg


def _llm_with_tools(*responses) -> MagicMock:
    """LLM mock that has generate_with_tools() returning responses in sequence."""
    llm = MagicMock()
    llm.backend_name = "vllm"
    llm.is_available.return_value = True
    llm.generate_with_tools.side_effect = list(responses)
    llm.generate.return_value = "Fallback answer from generate()."
    return llm


def _llm_no_tools() -> MagicMock:
    """LLM mock WITHOUT generate_with_tools — simulates Ollama / non-tool backend."""
    llm = MagicMock(spec=["generate", "backend_name", "is_available", "stream"])
    llm.backend_name = "ollama"
    llm.is_available.return_value = True
    llm.generate.return_value = "Ollama plain answer."
    return llm


# ── 1. TestTools ──────────────────────────────────────────────────────────────

class TestTools:

    def test_unknown_tool_returns_error(self):
        from AgentIntelligence.tools import execute_tool
        result = execute_tool("search_weather", {"query": "pioggia"})
        assert result["results"] == []
        assert "error" in result
        assert "search_weather" in result["error"]

    def test_empty_query_returns_error(self):
        from AgentIntelligence.tools import execute_tool
        result = execute_tool("search_code", {"query": "   "})
        assert result["results"] == []
        assert "error" in result

    def test_execute_search_code_success(self):
        from AgentIntelligence.tools import execute_tool
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            _make_ret_result("def foo(): pass", "bar.py", 0.9),
            _make_ret_result("class Baz:", "baz.py", 0.75),
        ]
        with patch("AgentIntelligence.tools._get_retriever", return_value=mock_retriever):
            result = execute_tool("search_code", {"query": "foo function", "top_k": 2})

        assert len(result["results"]) == 2
        assert result["results"][0]["text"] == "def foo(): pass"
        assert result["results"][0]["source"] == "bar.py"
        assert result["results"][0]["score"] == 0.9

    def test_execute_search_docs_success(self):
        from AgentIntelligence.tools import execute_tool
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            _make_ret_result("API endpoint documentation", "api.pdf", 0.88),
        ]
        with patch("AgentIntelligence.tools._get_retriever", return_value=mock_retriever):
            result = execute_tool("search_docs", {"query": "API configuration"})

        assert len(result["results"]) == 1
        assert result["results"][0]["source"] == "api.pdf"

    def test_execute_tool_retriever_unavailable_returns_note(self):
        from AgentIntelligence.tools import execute_tool
        with patch("AgentIntelligence.tools._get_retriever", return_value=None):
            result = execute_tool("search_docs", {"query": "how to deploy"})
        assert result["results"] == []
        assert "note" in result
        assert "non disponibile" in result["note"]

    def test_execute_tool_retriever_exception_returns_error(self):
        from AgentIntelligence.tools import execute_tool
        mock_retriever = MagicMock()
        mock_retriever.search.side_effect = RuntimeError("ChromaDB timeout")
        with patch("AgentIntelligence.tools._get_retriever", return_value=mock_retriever):
            result = execute_tool("search_practices", {"query": "deploy process"})
        assert result["results"] == []
        assert "error" in result
        assert "ChromaDB timeout" in result["error"]

    def test_tools_schema_has_three_entries(self):
        from AgentIntelligence.tools import TOOLS
        assert len(TOOLS) == 3

    def test_tools_schema_names_and_structure(self):
        from AgentIntelligence.tools import TOOLS
        names = {t["function"]["name"] for t in TOOLS}
        assert names == {"search_code", "search_docs", "search_practices"}
        for tool in TOOLS:
            assert tool["type"] == "function"
            assert "description" in tool["function"]
            params = tool["function"]["parameters"]
            assert "query" in params["properties"]
            assert "query" in params["required"]

    def test_text_truncated_at_600_chars(self):
        from AgentIntelligence.tools import execute_tool
        long_text = "x" * 900
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [_make_ret_result(long_text, "big.py", 0.5)]
        with patch("AgentIntelligence.tools._get_retriever", return_value=mock_retriever):
            result = execute_tool("search_code", {"query": "something"})
        assert len(result["results"][0]["text"]) <= 600


# ── 2. TestTextToolCallParser (Qwen3 native format) ──────────────────────────

class TestTextToolCallParser:

    def test_single_tool_call_parsed(self):
        from AgentIntelligence.agent import _parse_text_tool_calls
        content = '<tool_call>\n{"name": "search_code", "arguments": {"query": "foo", "top_k": 5}}\n</tool_call>'
        result = _parse_text_tool_calls(content)
        assert result is not None
        assert len(result) == 1
        assert result[0].function.name == "search_code"
        args = json.loads(result[0].function.arguments)
        assert args["query"] == "foo"
        assert args["top_k"] == 5

    def test_multiple_tool_calls_parsed(self):
        from AgentIntelligence.agent import _parse_text_tool_calls
        content = (
            '<tool_call>{"name": "search_code", "arguments": {"query": "embedding"}}</tool_call>\n'
            '<tool_call>{"name": "search_docs", "arguments": {"query": "architecture"}}</tool_call>'
        )
        result = _parse_text_tool_calls(content)
        assert result is not None
        assert len(result) == 2
        assert result[0].function.name == "search_code"
        assert result[1].function.name == "search_docs"

    def test_no_tool_calls_returns_none(self):
        from AgentIntelligence.agent import _parse_text_tool_calls
        result = _parse_text_tool_calls("Just a plain text answer with no tool calls.")
        assert result is None

    def test_malformed_json_skipped(self):
        from AgentIntelligence.agent import _parse_text_tool_calls
        content = (
            '<tool_call>{"name": "search_code", "arguments": {"query": "ok"}}</tool_call>\n'
            '<tool_call>NOT VALID JSON!!!</tool_call>'
        )
        result = _parse_text_tool_calls(content)
        # Only the valid one is returned
        assert result is not None
        assert len(result) == 1
        assert result[0].function.name == "search_code"

    def test_text_tool_call_loop_executes_and_synthesizes(self):
        """Agent loop handles Qwen3 text-format tool calls end-to-end."""
        from AgentIntelligence.agent import run_agent
        # Iteration 1: model outputs text with <tool_call> blocks
        iter1_content = (
            '<tool_call>{"name": "search_code", "arguments": {"query": "retriever"}}</tool_call>'
        )
        iter1 = _make_msg(content=iter1_content, tool_calls=None)
        # Iteration 2: model gives final answer (after seeing tool results)
        iter2 = _make_msg(content="Il Retriever è usato in server_base.py.", tool_calls=None)

        llm = _llm_with_tools(iter1, iter2)
        mock_result = {"results": [{"text": "class Retriever:", "source": "retriever.py", "score": 0.9}]}

        with patch("AgentIntelligence.agent.execute_tool", return_value=mock_result):
            result = run_agent("Come funziona il Retriever?", llm, max_iterations=5)

        assert result["intent"] == "agent"
        assert "Retriever" in result["answer"]
        assert "search_code" in result["tools_used"]
        assert result["iterations"] == 2


# ── 3. TestThinkingExtraction ─────────────────────────────────────────────────

class TestThinkingExtraction:

    def test_think_tags_extracted_from_content(self):
        from AgentIntelligence.agent import _extract_thinking
        msg = _make_msg(content="<think>This is my reasoning.</think>Final answer.", reasoning_content=None)
        reasoning, content = _extract_thinking(msg)
        assert "This is my reasoning." in reasoning
        assert "Final answer." in content
        assert "<think>" not in content

    def test_reasoning_content_field_takes_precedence(self):
        from AgentIntelligence.agent import _extract_thinking
        msg = _make_msg(content="Plain answer.", reasoning_content="Chain of thought here.")
        reasoning, content = _extract_thinking(msg)
        assert reasoning == "Chain of thought here."
        assert content == "Plain answer."

    def test_no_thinking_returns_empty_reasoning(self):
        from AgentIntelligence.agent import _extract_thinking
        msg = _make_msg(content="Simple answer.", reasoning_content=None)
        reasoning, content = _extract_thinking(msg)
        assert reasoning == ""
        assert content == "Simple answer."

    def test_multiline_think_tags(self):
        from AgentIntelligence.agent import _extract_thinking
        msg = _make_msg(content="<think>\nStep 1\nStep 2\n</think>\n\nConclusion.", reasoning_content=None)
        reasoning, content = _extract_thinking(msg)
        assert "Step 1" in reasoning
        assert "Step 2" in reasoning
        assert "Conclusion." in content
        assert "<think>" not in content

    def test_reasoning_content_skips_tag_branch(self):
        """When reasoning_content is set, <think> tags in content are NOT stripped."""
        from AgentIntelligence.agent import _extract_thinking
        msg = _make_msg(
            content="<think>tag reasoning</think>Answer",
            reasoning_content="field reasoning",
        )
        reasoning, content = _extract_thinking(msg)
        assert reasoning == "field reasoning"
        # content is not cleaned because the tag-stripping branch was skipped
        assert "Answer" in content


# ── 3. TestAgentLoop ──────────────────────────────────────────────────────────

class TestAgentLoop:

    def test_single_iteration_direct_answer(self):
        """Model returns a direct answer in iteration 1 — no tools called."""
        from AgentIntelligence.agent import run_agent
        llm = _llm_with_tools(_make_msg(content="La risposta diretta.", tool_calls=None))

        result = run_agent("Cosa fa il modulo X?", llm, max_iterations=5)

        assert result["intent"] == "agent"
        assert result["answer"] == "La risposta diretta."
        assert result["iterations"] == 1
        assert result["tools_used"] == []
        assert result["backend"] == "vllm"

    def test_multi_iteration_tool_then_answer(self):
        """Model calls search_code first, then gives final answer in iteration 2."""
        from AgentIntelligence.agent import run_agent

        tc = _make_tool_call("search_code", {"query": "Retriever class"})
        iter1 = _make_msg(content="", tool_calls=[tc])
        iter2 = _make_msg(content="Ecco la risposta sintetica.", tool_calls=None)
        llm = _llm_with_tools(iter1, iter2)

        mock_tool_result = {"results": [{"text": "class Retriever:", "source": "retriever.py", "score": 0.9}]}
        with patch("AgentIntelligence.agent.execute_tool", return_value=mock_tool_result):
            result = run_agent("Come funziona il Retriever?", llm, max_iterations=5)

        assert result["intent"] == "agent"
        assert result["answer"] == "Ecco la risposta sintetica."
        assert result["iterations"] == 2
        assert "search_code" in result["tools_used"]

    def test_max_iterations_forces_final_answer(self):
        """After max_iterations all with tool calls, agent forces final via llm.generate()."""
        from AgentIntelligence.agent import run_agent

        tc = _make_tool_call("search_docs", {"query": "config"})
        always_tool = _make_msg(content="", tool_calls=[tc])
        llm = _llm_with_tools(always_tool, always_tool, always_tool)
        llm.generate.return_value = "Risposta da generate() fallback."

        mock_tool_result = {"results": [{"text": "config info", "source": "doc.pdf", "score": 0.8}]}
        with patch("AgentIntelligence.agent.execute_tool", return_value=mock_tool_result):
            result = run_agent("Tell me about config", llm, max_iterations=3)

        assert result["intent"] == "agent"
        assert result["iterations"] == 3
        assert "fallback" in result["answer"]
        llm.generate.assert_called_once()

    def test_no_generate_with_tools_fallback(self):
        """LLM without generate_with_tools falls back to generate() immediately."""
        from AgentIntelligence.agent import run_agent
        llm = _llm_no_tools()

        result = run_agent("Analizza tutto il sistema", llm, max_iterations=5)

        assert result["intent"] == "agent_fallback"
        assert result["answer"] == "Ollama plain answer."
        assert result["iterations"] == 0
        assert result["tools_used"] == []
        llm.generate.assert_called_once()

    def test_generate_with_tools_exception_breaks_loop(self):
        """If generate_with_tools raises, the loop breaks and falls back to generate()."""
        from AgentIntelligence.agent import run_agent

        llm = _llm_with_tools()
        llm.generate_with_tools.side_effect = RuntimeError("vLLM offline")
        llm.generate.return_value = "Risposta di emergenza."

        result = run_agent("Analizza", llm, max_iterations=3)

        assert "answer" in result
        llm.generate.assert_called_once()

    def test_thinking_flag_passed_to_generate_with_tools(self):
        """thinking=True is forwarded to llm.generate_with_tools()."""
        from AgentIntelligence.agent import run_agent

        llm = _llm_with_tools(_make_msg(content="Risposta.", tool_calls=None))
        run_agent("Query", llm, max_iterations=5, thinking=True)

        call_kwargs = llm.generate_with_tools.call_args[1]
        assert call_kwargs.get("thinking") is True


# ── 4. TestAgentServer ────────────────────────────────────────────────────────

@pytest.fixture
def agent_client():
    """TestClient on a fresh AgentIntelligence app with mocked LLM + run_agent."""
    mock_llm = MagicMock()
    mock_llm.backend_name = "mock"
    mock_llm.is_available.return_value = True
    mock_llm.generate_with_tools = MagicMock()  # presence → supports_tools=True

    mock_run_result = {
        "answer": "Risposta agente.",
        "intent": "agent",
        "iterations": 2,
        "reasoning": "Ho cercato nel codice.",
        "tools_used": ["search_code"],
        "backend": "mock",
    }

    with patch("AgentIntelligence.agent.run_agent", return_value=mock_run_result), \
         patch("AgentIntelligence.agent_server.get_llm_provider", return_value=mock_llm):
        import AgentIntelligence.agent_server as _srv
        fresh_app = _srv.build_app()
        # Reset thinking state for each test
        _srv._thinking_enabled = False
        with TestClient(fresh_app) as client:
            yield client


class TestAgentServer:

    def test_health_returns_ok(self, agent_client):
        resp = agent_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["module"] == "agent"
        assert data["version"] == "0.5.0"
        assert "thinking_mode" in data
        assert "supports_tools" in data
        assert "max_iterations" in data
        assert isinstance(data["max_iterations"], int)

    def test_thinking_get_returns_bool(self, agent_client):
        resp = agent_client.get("/api/v1/thinking")
        assert resp.status_code == 200
        assert "enabled" in resp.json()
        assert isinstance(resp.json()["enabled"], bool)

    def test_thinking_post_updates_state(self, agent_client):
        resp = agent_client.post("/api/v1/thinking", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        resp2 = agent_client.get("/api/v1/thinking")
        assert resp2.json()["enabled"] is True

        # Reset
        agent_client.post("/api/v1/thinking", json={"enabled": False})

    def test_query_endpoint_returns_response(self, agent_client):
        resp = agent_client.post("/api/v1/query", json={"question": "Analizza il codice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Risposta agente."
        assert data["intent"] == "agent"
        assert data["iterations"] == 2
        assert "search_code" in data["tools_used"]
        assert data["latency_ms"] >= 0.0

    def test_root_redirects_to_docs(self, agent_client):
        resp = agent_client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert "/docs" in resp.headers.get("location", "")

    def test_health_reflects_supports_tools(self, agent_client):
        """Health shows supports_tools=True when LLM has generate_with_tools."""
        resp = agent_client.get("/health")
        assert resp.json()["supports_tools"] is True


# ── 5. TestOpenAICompatTools ──────────────────────────────────────────────────

class TestOpenAICompatTools:

    def _make_provider(self, backend_hint: str = "vllm"):
        from intelligence_core.llm.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            base_url="http://localhost:8000/v1",
            api_key="not-needed",
            model="qwen3",
            backend_hint=backend_hint,
        )

    def _mock_openai_client(self, content: str = "Answer"):
        mock_client = MagicMock()
        choice = MagicMock()
        choice.message.content = content
        choice.message.tool_calls = None
        choice.message.reasoning_content = None
        mock_client.chat.completions.create.return_value = MagicMock(choices=[choice])
        return mock_client

    def test_generate_with_tools_calls_create(self):
        # OpenAI is imported lazily inside the method → patch the source module
        provider = self._make_provider()
        messages = [{"role": "user", "content": "test"}]
        tools = [{"type": "function", "function": {"name": "search_code", "parameters": {}}}]

        mock_client = self._mock_openai_client()
        with patch("openai.OpenAI", return_value=mock_client):
            provider.generate_with_tools(messages, tools, thinking=False)

        mock_client.chat.completions.create.assert_called_once()
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert kwargs["tool_choice"] == "auto"
        assert kwargs["tools"] == tools
        assert "extra_body" not in kwargs

    def test_generate_with_tools_thinking_adds_extra_body_for_vllm(self):
        provider = self._make_provider(backend_hint="vllm")
        mock_client = self._mock_openai_client()
        with patch("openai.OpenAI", return_value=mock_client):
            provider.generate_with_tools([], [], thinking=True)
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert "extra_body" in kwargs
        assert kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True

    def test_generate_with_tools_no_extra_body_for_openai_backend(self):
        """thinking=True is ignored for non-vLLM backends."""
        provider = self._make_provider(backend_hint="openai")
        mock_client = self._mock_openai_client()
        with patch("openai.OpenAI", return_value=mock_client):
            provider.generate_with_tools([], [], thinking=True)
        kwargs = mock_client.chat.completions.create.call_args[1]
        assert "extra_body" not in kwargs

    def test_generate_with_tools_returns_fallback_on_exception(self):
        """On LLM failure, returns a _FallbackMsg instead of raising."""
        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Connection refused")
        with patch("openai.OpenAI", return_value=mock_client):
            msg = provider.generate_with_tools([], [], thinking=False)
        assert msg.tool_calls is None
        assert "LLM error" in msg.content

    def test_generate_thinking_adds_extra_body_for_vllm_backend(self):
        """generate() also passes extra_body when thinking_mode=True + vllm backend."""
        provider = self._make_provider(backend_hint="vllm")
        mock_client = self._mock_openai_client(content="RAG answer")

        mock_settings = MagicMock()
        mock_settings.thinking_mode = True

        with patch("intelligence_core.config.settings", mock_settings), \
             patch("openai.OpenAI", return_value=mock_client):
            provider.generate("What is X?", "context here")

        kwargs = mock_client.chat.completions.create.call_args[1]
        assert "extra_body" in kwargs
        assert kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True


# ── 6. TestLauncherAgent ──────────────────────────────────────────────────────

class TestLauncherAgent:

    @pytest.fixture(scope="class")
    def html(self):
        from intelligence_ui.launcher import _HTML
        return _HTML

    def test_agent_card_title_present(self, html):
        assert "Agent Intelligence" in html

    def test_agent_port_8084_present(self, html):
        assert "localhost:8084" in html

    def test_poll_agent_function_present(self, html):
        assert "pollAgent" in html

    def test_poll_agent_checks_health_endpoint(self, html):
        assert "8084/health" in html

    def test_toggle_thinking_function_present(self, html):
        assert "toggleThinking" in html

    def test_thinking_api_endpoint_in_html(self, html):
        assert "/api/v1/thinking" in html

    def test_thinking_button_element_present(self, html):
        assert "thinking-btn" in html

    def test_four_column_grid_layout(self, html):
        assert "md:grid-cols-4" in html

    def test_launcher_root_serves_html(self):
        from intelligence_ui.launcher import app
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "IntelligenceSuite" in resp.text
        assert "Agent Intelligence" in resp.text
        assert "pollAgent" in resp.text
