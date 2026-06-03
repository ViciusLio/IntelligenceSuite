"""Ollama LLM provider — fully local, zero API key required."""

from __future__ import annotations
import logging

import httpx

from intelligence_core.llm.protocol import SYSTEM_PROMPT_DEFAULT

logger = logging.getLogger(__name__)


def _ollama_timeout() -> float:
    """Read OLLAMA_TIMEOUT from settings (default 300s). Lazy import to avoid cycles."""
    try:
        from intelligence_core.config import settings
        return settings.ollama_timeout
    except Exception:
        return 300.0


def _thinking_flag() -> bool | None:
    """Read THINKING_MODE from settings (tri-state). Lazy import to avoid cycles.

    Returns ``True``/``False`` to force thinking on/off (sent as Ollama's native
    ``think`` field), or ``None`` to leave the model default untouched.
    Only thinking-capable models (qwen3, deepseek-r1, …) accept the ``think``
    field — set THINKING_MODE only when running such a model.
    """
    try:
        from intelligence_core.config import settings
        return settings.thinking_mode
    except Exception:
        return None


class OllamaProvider:
    """
    Calls Ollama /api/chat endpoint.

    Requirements:
        - Ollama running locally (default: http://localhost:11434)
        - Model pulled: ``ollama pull <model>``

    Config (.env):
        LLM_BACKEND=ollama
        OLLAMA_BASE_URL=http://localhost:11434
        OLLAMA_MODEL=qwen2.5-coder:7b
        OLLAMA_TIMEOUT=300        # seconds — increase for slow CPU / long answers
    """

    backend_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(
        self,
        question: str,
        context: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        system = system_prompt or SYSTEM_PROMPT_DEFAULT
        user_msg = f"Context:\n{context}\n\nQuestion: {question}"
        timeout = _ollama_timeout()
        payload: dict = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user_msg},
            ],
        }
        think = _thinking_flag()
        if think is not None:
            payload["think"] = think
        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OllamaProvider.generate failed: %s", exc)
            return (
                f"[LLM unavailable — Ollama error: {exc}]\n\n"
                f"Most relevant context:\n{context[:600]}"
            )

    def stream(
        self,
        question: str,
        context: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ):
        """Sync generator — yields tokens one by one as Ollama streams them."""
        import json as _json
        system  = system_prompt or SYSTEM_PROMPT_DEFAULT
        user_msg = f"Context:\n{context}\n\nQuestion: {question}"
        timeout = _ollama_timeout()
        payload: dict = {
            "model":   self.model,
            "stream":  True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user_msg},
            ],
        }
        think = _thinking_flag()
        if think is not None:
            payload["think"] = think
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        data  = _json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
        except Exception as exc:
            logger.warning("OllamaProvider.stream failed: %s", exc)
            yield f"\n\n[LLM error: {exc}]"

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
