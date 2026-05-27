"""AgentIntelligence — ReAct loop with tool use and optional Qwen3 thinking mode.

Flow per query:
  1. Build messages [system, user]
  2. Call llm.generate_with_tools(messages, TOOLS, thinking=thinking)
  3. If no tool_calls → final answer, return
  4. Execute each tool call, append results to messages
  5. Repeat up to max_iterations
  6. If max_iterations reached → force final answer via llm.generate()
"""

from __future__ import annotations

import json
import logging
import re
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
        logger.info("AgentIntelligence: backend '%s' non supporta tool calling, fallback RAG", llm.backend_name)
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
            reasoning = turn_reasoning  # keep last reasoning block

        # No tool calls → model gave a direct answer
        if not msg.tool_calls:
            answer = clean_content or "Nessuna risposta generata."
            return {
                "answer":     answer,
                "intent":     "agent",
                "iterations": i + 1,
                "reasoning":  reasoning,
                "tools_used": tools_used,
                "backend":    llm.backend_name,
            }

        # Append assistant turn (with tool_calls)
        assistant_turn: dict = {
            "role":    "assistant",
            "content": clean_content or "",
        }
        try:
            assistant_turn["tool_calls"] = [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in msg.tool_calls
            ]
        except Exception:
            assistant_turn["tool_calls"] = msg.tool_calls
        messages.append(assistant_turn)

        # Execute each tool call and append results
        for tc in msg.tool_calls:
            try:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
            except Exception as exc:
                logger.warning("AgentIntelligence: errore parsing tool call: %s", exc)
                continue

            logger.info("AgentIntelligence: eseguo tool '%s' con args %s", fn_name, fn_args)
            result = execute_tool(fn_name, fn_args)
            tools_used.append(fn_name)

            messages.append({
                "role":         "tool",
                "tool_call_id": getattr(tc, "id", fn_name),
                "name":         fn_name,
                "content":      json.dumps(result, ensure_ascii=False),
            })

    # Max iterations reached — force a final answer without tools
    logger.info("AgentIntelligence: max iterazioni (%d) raggiunte, forzo risposta finale", max_iterations)
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
