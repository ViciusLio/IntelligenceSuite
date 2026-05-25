"""
IntelligenceSuite — Example 03: Switching LLM backends
=======================================================
Demonstrates how to switch the generation backend without
changing any application code — only the environment variable
(or the explicit argument to get_llm_provider).

Supported backends
------------------
  ollama  — Local Ollama server (default, free, no API key)
  openai  — OpenAI API (GPT-4o, GPT-4o-mini, o1, …)
  vllm    — vLLM local GPU server (OpenAI-compatible)
  claude  — Anthropic Claude API

Any OpenAI-compatible server (Groq, Mistral AI, LM Studio, Together AI)
works with backend="openai" by changing OPENAI_BASE_URL.

Run
---
    python examples/03_switch_llm_backend.py
    LLM_BACKEND=openai  OPENAI_API_KEY=sk-... python examples/03_switch_llm_backend.py
    LLM_BACKEND=claude  ANTHROPIC_API_KEY=sk-ant-... python examples/03_switch_llm_backend.py
"""

from __future__ import annotations
from intelligence_core.llm import get_llm_provider
from intelligence_core.llm.ollama import OllamaProvider
from intelligence_core.llm.openai_compat import OpenAICompatProvider
from intelligence_core.llm.claude import ClaudeProvider
from intelligence_core.llm.protocol import SYSTEM_PROMPT_DEFAULT

SAMPLE_CONTEXT = """
[intelligence_core/retriever.py]
class Retriever:
    def search(self, query: str, top_k: int = 5, domain: str = None) -> list[RetrievalResult]:
        embedding = self.embedder.embed_one(query)
        filters = {"domain": domain} if domain else None
        raw = self.store.search(embedding, top_k=top_k * 2, filters=filters)
        ...
        return [RetrievalResult(chunk=c, score=c["score"], rank=i+1) for i, c in enumerate(raw[:top_k])]

    @classmethod
    def load_default(cls) -> "Retriever":
        from intelligence_core.embedder import get_embedder
        from intelligence_core.store import get_store
        return cls(embedder=get_embedder(), store=get_store())
"""

SAMPLE_QUESTION = "How does the Retriever work and how do I instantiate it?"


def demo_provider(llm, label: str):
    print(f"\n{'─'*55}")
    print(f"  Backend : {label}")
    print(f"  Class   : {llm.__class__.__name__}")
    print(f"  Available: {llm.is_available()}")

    if not llm.is_available():
        print("  ⚠  Not reachable — skipping generation.")
        return

    print(f"  Generating answer...")
    answer = llm.generate(SAMPLE_QUESTION, SAMPLE_CONTEXT)
    preview = answer[:300].replace("\n", " ")
    print(f"  Answer  : {preview}{'...' if len(answer) > 300 else ''}")


def main():
    print(f"\n{'='*55}")
    print(f"  IntelligenceSuite — LLM Backend Switcher")
    print(f"{'='*55}")
    print(f"\nQuestion: {SAMPLE_QUESTION}")

    # ── Option 1: reads LLM_BACKEND from .env (or default=ollama) ────────────
    print("\n[1] Auto — from LLM_BACKEND env var / .env")
    llm = get_llm_provider()
    demo_provider(llm, f"{llm.backend_name} (from env)")

    # ── Option 2: explicit Ollama ─────────────────────────────────────────────
    print("\n[2] Explicit Ollama (local)")
    llm_ollama = OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen2.5-coder:7b",
    )
    demo_provider(llm_ollama, "ollama / qwen2.5-coder:7b")

    # ── Option 3: OpenAI-compatible — also covers vLLM, Groq, Mistral, etc. ──
    import os
    openai_key = os.getenv("OPENAI_API_KEY", "")
    print("\n[3] OpenAI-compatible (OpenAI / vLLM / Groq / Mistral / LM Studio)")
    llm_oai = OpenAICompatProvider(
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=openai_key,
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        backend_hint="openai",
    )
    demo_provider(llm_oai, f"openai-compat / {llm_oai.model}")

    # vLLM example (same class, different URL)
    print("\n  vLLM variant (OpenAI-compatible, local GPU):")
    llm_vllm = OpenAICompatProvider(
        base_url="http://localhost:8000/v1",   # your vLLM server
        api_key="not-needed",
        model="mistralai/Mistral-7B-Instruct-v0.2",
        backend_hint="vllm",
    )
    print(f"  backend_name = {llm_vllm.backend_name}  (available={llm_vllm.is_available()})")

    # ── Option 4: Anthropic Claude ────────────────────────────────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    print("\n[4] Anthropic Claude")
    llm_claude = ClaudeProvider(
        api_key=anthropic_key,
        model=os.getenv("CLAUDE_MODEL", "claude-opus-4-5"),
    )
    demo_provider(llm_claude, f"claude / {llm_claude.model}")

    print(f"\n{'='*55}")
    print("  To switch backend globally — just set in .env:")
    print("    LLM_BACKEND=ollama")
    print("    LLM_BACKEND=openai   OPENAI_API_KEY=sk-...")
    print("    LLM_BACKEND=vllm     OPENAI_BASE_URL=http://localhost:8000/v1")
    print("    LLM_BACKEND=claude   ANTHROPIC_API_KEY=sk-ant-...")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
