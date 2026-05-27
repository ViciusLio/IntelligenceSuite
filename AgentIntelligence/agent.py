"""AgentIntelligence — ReAct loop with tool use and optional Qwen3 thinking mode.

Flow per query:
  1. Build messages [system, user]
  2. Call llm.generate_with_tools(messages, TOOLS, thinking=thinking)
  3. If model returned structured tool_calls → execute them (OpenAI path)
     Else if content contains <tool_call>...</tool_call> → parse + execute (Qwen3 text path)
  4. Append tool results to messages, loop
  5. If max_iterations reached → force final answer via llm.generate()

Qwen3 note:
  When vLLM returns tool calls as text (<tool_call>{...}</tool_call>) rather than
  structured API tool_calls, we parse them manually and execute them exactly the same
  way. This makes the ReAct loop backend-agnostic.
"""

from __future__ import annotations

import json
import logging
import re
from types import SimpleNamespace
from typing import Any

from AgentIntelligence.tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = (
    "Sei un assistente tecnico intelligente con accesso a tre knowledge base:\n"
    "- search_code: codice sorgente (classi, funzioni, moduli)\n"
    "- search_docs: documentazione tecnica (PDF, guide, specifiche)\n"
    "- search_practices: pratiche e convenzioni del team\n\n"
    "Per rispondere a una domanda complessa:\n"
    "1. Usa i tool per cercare informazioni rilevanti — puoi fare più ricerche\n"
    "2. Sintetizza i risultati in una risposta completa e precisa\n"
    "3. Cita le fonti quando rilevante\n\n"
    "Quando hai abbastanza informazioni, rispondi direttamente senza chiamare altri tool."
)


# ── Thinking extraction ───────────────────────────────────────────────────────

def _extract_thinking(msg: Any) -> tuple[str, str]:
    """Extract (reasoning, clean_content) from a ChatCompletionMessage.

    Handles two formats:
    - Qwen3 vLLM: ``reasoning_content`` field (separate from content)
    - Fallback: ``<think>...</think>`` tags inside content
    """
    # Format 1: separate reasoning_content field
    reasoning = getattr(msg, "reasoning_content", None) or ""

    content = msg.content or ""

    # Format 2: <think> tags inside content
    if not reasoning and "<think>" in content:
        match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
        if match:
            reasoning = match.group(1).strip()
            # Remove the think block from content
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()

    return reasoning, content


# ── Text-based tool call parser (Qwen3 native format) ────────────────────────

def _parse_text_tool_calls(content: str) -> list | None:
    """Parse Qwen3/Hermes-style <tool_call>...</tool_call> blocks from text.

    When vLLM returns tool calls embedded in text content rather than as
    structured API tool_calls, this extracts them into SimpleNamespace objects
    that match the interface used by the ReAct loop.

    Returns a list of tool-call-like objects, or None if none found.
    """
    pattern = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
    matches = pattern.findall(content)
    if not matches:
        return None

    parsed: list = []
    for i, raw in enumerate(matches):
        try:
            data = json.loads(raw)
            name = data.get("name", "")
            arguments = data.get("arguments", {})
            arguments_str = (
                json.dumps(arguments, ensure_ascii=False)
                if isinstance(arguments, dict)
                else str(arguments)
            )
            tc = SimpleNamespace(
                id=f"text_call_{i}",
                function=SimpleNamespace(name=name, arguments=arguments_str),
            )
            parsed.append(tc)
        except Exception as exc:
            logger.warning(
                "AgentIntelligence: errore parsing text tool_call #%d: %s — raw: %r",
                i, exc, raw[:120],
            )

    return parsed or None


def _tc_to_dict(tc: Any) -> dict:
    """Serialize a tool_call object to dict for the messages API."""
    if hasattr(tc, "model_dump"):
        return tc.model_dump()
    return {
        "id": getattr(tc, "id", "call_unknown"),
        "type": "function",
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        },
    }


# ── Context builder for fallback ─────────────────────────────────────────────

def _build_context_from_messages(messages: list[dict]) -> str:
    """Extract tool results from message history to build a context string."""
    parts: list[str] = []
    for m in messages:
        if m.get("role") == "tool":
            try:
                data = json.loads(m.get("content", "{}"))
                for r in data.get("results", []):
                    src = r.get("source", "")
                    text = r.get("text", "")
                    if text:
                        parts.append(f"[{src}]\n{text}")
            except Exception:
                parts.append(m.get("content", ""))
    return "\n\n---\n\n".join(parts[:10])  # cap at 10 chunks


# ── Main ReAct loop ───────────────────────────────────────────────────────────

def run_agent(
    question: str,
    llm: Any,
    max_iterations: int = 5,
    thinking: bool = False,
) -> dict:
    """Run the ReAct agent loop.

    Args:
        question:       User query.
        llm:            LLMProvider instance. Must have ``generate_with_tools()``
                        for full agentic behaviour; falls back to ``generate()``
                        otherwise.
        max_iterations: Maximum tool-call cycles before forcing a final answer.
        thinking:       Enable Qwen3 thinking mode (only works on vLLM backend).

    Returns:
        dict with keys: answer, intent, iterations, reasoning, tools_used, backend
    """
    # Fallback: provider doesn't support tool calling (e.g. Ollama)
    if not hasattr(llm, "generate_with_tools"):
        logger.info(
            "AgentIntelligence: backend '%s' non supporta tool calling, fallback RAG",
            llm.backend_name,
        )
        answer = llm.generate(question, "", system_prompt=AGENT_SYSTEM_PROMPT)
        return {
            "answer":     answer,
            "intent":     "agent_fallback",
            "iterations": 0,
            "reasoning":  "",
            "tools_used": [],
            "backend":    llm.backend_name,
        }

    messages: list[dict] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user",   "content": question},
    ]
    tools_used: list[str] = []
    reasoning:  str       = ""

    for i in range(max_iterations):
        logger.debug("AgentIntelligence: iterazione %d/%d", i + 1, max_iterations)

        try:
            msg = llm.generate_with_tools(messages, TOOLS, thinking=thinking)
        except Exception as exc:
            logger.warning("AgentIntelligence: generate_with_tools fallito: %s", exc)
            break

        # Extract thinking and clean content
        turn_reasoning, clean_content = _extract_thinking(msg)
        if turn_reasoning:
            reasoning = turn_reasoning

        # ── Determine effective tool calls ────────────────────────────────────
        # Path A: structured tool_calls from the API (OpenAI / vLLM native)
        effective_tool_calls = msg.tool_calls if msg.tool_calls else None

        # Path B: text-embedded tool calls (Qwen3 native format via vLLM)
        text_parsed = False
        if not effective_tool_calls and "<tool_call>" in clean_content:
            effective_tool_calls = _parse_text_tool_calls(clean_content)
            text_parsed = bool(effective_tool_calls)
            if text_parsed:
                logger.info(
                    "AgentIntelligence: %d tool call(s) in formato testo (Qwen3), parsing manuale",
                    len(effective_tool_calls),
                )

        # No tool calls → model gave a direct answer
        if not effective_tool_calls:
            answer = clean_content or "Nessuna risposta generata."
            return {
                "answer":     answer,
                "intent":     "agent",
                "iterations": i + 1,
                "reasoning":  reasoning,
                "tools_used": tools_used,
                "backend":    llm.backend_name,
            }

        # ── Append assistant turn ─────────────────────────────────────────────
        if text_parsed:
            # Keep the original content (with <tool_call> blocks) so the model
            # can track its own tool-call history in subsequent turns.
            messages.append({"role": "assistant", "content": clean_content})
        else:
            # Standard OpenAI format: structured tool_calls field
            assistant_turn: dict = {"role": "assistant", "content": clean_content or ""}
            try:
                assistant_turn["tool_calls"] = [_tc_to_dict(tc) for tc in effective_tool_calls]
            except Exception:
                assistant_turn["tool_calls"] = effective_tool_calls
            messages.append(assistant_turn)

        # ── Execute each tool call ────────────────────────────────────────────
        tool_results: list[str] = []
        for tc in effective_tool_calls:
            try:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
            except Exception as exc:
                logger.warning("AgentIntelligence: errore parsing tool call: %s", exc)
                continue

            logger.info("AgentIntelligence: eseguo tool '%s' con args %s", fn_name, fn_args)
            result = execute_tool(fn_name, fn_args)
            tools_used.append(fn_name)

            result_json = json.dumps(result, ensure_ascii=False)

            if text_parsed:
                # For text-parsed calls, collect results and inject as a user turn
                # (tool role with tool_call_id is for structured API calls only)
                tool_results.append(f"[{fn_name}]\n{result_json}")
            else:
                messages.append({
                    "role":         "tool",
                    "tool_call_id": getattr(tc, "id", fn_name),
                    "name":         fn_name,
                    "content":      result_json,
                })

        if text_parsed and tool_results:
            # Inject all tool results as a single user turn with a synthesis prompt
            combined = "\n\n".join(tool_results)
            messages.append({
                "role": "user",
                "content": (
                    f"Risultati delle ricerche:\n\n{combined}\n\n"
                    "Ora sintetizza una risposta completa e precisa basata su questi risultati."
                ),
            })

    # Max iterations reached — force a final answer without tools
    logger.info(
        "AgentIntelligence: max iterazioni (%d) raggiunte, forzo risposta finale",
        max_iterations,
    )
    context = _build_context_from_messages(messages)
    try:
        final_answer = llm.generate(question, context, system_prompt=AGENT_SYSTEM_PROMPT)
    except Exception as exc:
        logger.warning("AgentIntelligence: generate fallback fallito: %s", exc)
        final_answer = "Impossibile generare una risposta dopo il numero massimo di iterazioni."

    return {
        "answer":     final_answer,
        "intent":     "agent",
        "iterations": max_iterations,
        "reasoning":  reasoning,
        "tools_used": tools_used,
        "backend":    llm.backend_name,
    }
