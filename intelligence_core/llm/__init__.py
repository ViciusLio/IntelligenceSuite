"""LLM provider factory for Intelligence Suite.

Supported backends
------------------
ollama       Local Ollama server (default, zero cost, no API key)
openai       OpenAI Chat Completions API
vllm         vLLM local GPU server (OpenAI-compatible)
claude       Anthropic Claude API

Any other OpenAI-compatible server (Groq, Mistral AI, LM Studio, Together AI, …)
can be used with ``LLM_BACKEND=openai`` by changing ``OPENAI_BASE_URL``.

Per-module routing
------------------
Each module can override the global backend/model independently:

    CI_LLM_BACKEND=openai          CI_LLM_MODEL=codellama:34b
    CI_LLM_BASE_URL=http://gpu:8000/v1

    DI_LLM_BACKEND=ollama          DI_LLM_MODEL=mistral:7b

    MI_LLM_BACKEND=claude          MI_LLM_MODEL=claude-sonnet-4-5

Leave any variable empty to fall back to the global LLM_BACKEND settings.

Usage
-----
    from intelligence_core.llm import get_llm_provider, get_module_llm_provider

    llm = get_llm_provider()              # global settings
    llm = get_module_llm_provider("ci")   # CodeIntelligence — with per-module override
    llm = get_module_llm_provider("di")   # DocIntelligence
    llm = get_module_llm_provider("mi")   # MentorIntelligence
"""

from __future__ import annotations
import logging

from intelligence_core.llm.protocol import LLMProvider, SYSTEM_PROMPT_DEFAULT

logger = logging.getLogger(__name__)


def get_llm_provider(
    backend: str | None = None,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> LLMProvider:
    """
    Factory: return the configured LLM provider.

    Args:
        backend:  Override ``LLM_BACKEND`` from settings.
                  Values: ``"ollama"`` | ``"openai"`` | ``"vllm"`` | ``"claude"``
        model:    Override the model name (OLLAMA_MODEL / OPENAI_MODEL / CLAUDE_MODEL).
        base_url: Override the API base URL (OPENAI_BASE_URL / OLLAMA_BASE_URL).
        api_key:  Override the API key (OPENAI_API_KEY / ANTHROPIC_API_KEY).

    Returns:
        An object satisfying the :class:`LLMProvider` protocol.
    """
    from intelligence_core.config import settings

    _backend = backend or settings.llm_backend

    if _backend in ("openai", "vllm"):
        from intelligence_core.llm.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            base_url=base_url or settings.openai_base_url,
            api_key=api_key or settings.openai_api_key,
            model=model or settings.openai_model,
            backend_hint=_backend,
        )

    if _backend == "claude":
        from intelligence_core.llm.claude import ClaudeProvider
        return ClaudeProvider(
            api_key=api_key or settings.anthropic_api_key,
            model=model or settings.claude_model,
        )

    # default: ollama
    from intelligence_core.llm.ollama import OllamaProvider
    return OllamaProvider(
        base_url=base_url or settings.ollama_base_url,
        model=model or settings.ollama_model,
    )


def get_module_llm_provider(module: str) -> LLMProvider:
    """
    Get the LLM provider for a specific module, applying per-module env overrides.

    Module prefixes
    ---------------
    "ci"  → CodeIntelligence   (CI_LLM_BACKEND, CI_LLM_MODEL, CI_LLM_BASE_URL, CI_LLM_API_KEY)
    "di"  → DocIntelligence    (DI_LLM_BACKEND, DI_LLM_MODEL, DI_LLM_BASE_URL, DI_LLM_API_KEY)
    "mi"  → MentorIntelligence (MI_LLM_BACKEND, MI_LLM_MODEL, MI_LLM_BASE_URL, MI_LLM_API_KEY)

    Any variable left empty falls back to the global LLM_BACKEND / model / URL / key.

    Example .env
    ------------
    # Route CodeIntelligence to a vLLM GPU server
    CI_LLM_BACKEND=openai
    CI_LLM_MODEL=codellama:34b
    CI_LLM_BASE_URL=http://gpu-server:8000/v1

    # Route DocIntelligence to a local Mistral (better multilingual)
    DI_LLM_BACKEND=ollama
    DI_LLM_MODEL=mistral:7b

    # Route MentorIntelligence to Claude (best pedagogical quality)
    MI_LLM_BACKEND=claude
    MI_LLM_MODEL=claude-sonnet-4-5
    """
    from intelligence_core.config import settings

    prefix = module.lower()  # "ci", "di", "mi"

    backend  = getattr(settings, f"{prefix}_llm_backend",  "") or None
    model    = getattr(settings, f"{prefix}_llm_model",    "") or None
    base_url = getattr(settings, f"{prefix}_llm_base_url", "") or None
    api_key  = getattr(settings, f"{prefix}_llm_api_key",  "") or None

    if any([backend, model, base_url, api_key]):
        logger.info(
            "Module [%s] LLM override → backend=%s  model=%s  base_url=%s",
            module.upper(),
            backend  or "(global)",
            model    or "(global)",
            base_url or "(global)",
        )

    return get_llm_provider(backend, model=model, base_url=base_url, api_key=api_key)


__all__ = [
    "LLMProvider",
    "SYSTEM_PROMPT_DEFAULT",
    "get_llm_provider",
    "get_module_llm_provider",
]
