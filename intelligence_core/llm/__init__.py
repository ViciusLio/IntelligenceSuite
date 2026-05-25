"""LLM provider factory for Intelligence Suite.

Supported backends
------------------
ollama       Local Ollama server (default, zero cost, no API key)
openai       OpenAI Chat Completions API
vllm         vLLM local GPU server (OpenAI-compatible)
claude       Anthropic Claude API

Any other OpenAI-compatible server (Groq, Mistral AI, LM Studio, Together AI, …)
can be used with ``LLM_BACKEND=openai`` by changing ``OPENAI_BASE_URL``.

Usage
-----
    from intelligence_core.llm import get_llm_provider

    llm = get_llm_provider()          # reads LLM_BACKEND from .env
    answer = llm.generate(question, context)
"""

from __future__ import annotations

from intelligence_core.llm.protocol import LLMProvider, SYSTEM_PROMPT_DEFAULT


def get_llm_provider(backend: str | None = None) -> LLMProvider:
    """
    Factory: return the configured LLM provider.

    Args:
        backend: Override ``LLM_BACKEND`` from settings.
                 Values: ``"ollama"`` | ``"openai"`` | ``"vllm"`` | ``"claude"``

    Returns:
        An object satisfying the :class:`LLMProvider` protocol.
    """
    from intelligence_core.config import settings

    _backend = backend or settings.llm_backend

    if _backend in ("openai", "vllm"):
        from intelligence_core.llm.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            backend_hint=_backend,
        )

    if _backend == "claude":
        from intelligence_core.llm.claude import ClaudeProvider
        return ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
        )

    # default: ollama
    from intelligence_core.llm.ollama import OllamaProvider
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )


__all__ = ["LLMProvider", "SYSTEM_PROMPT_DEFAULT", "get_llm_provider"]
