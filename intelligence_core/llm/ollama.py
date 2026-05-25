"""Ollama LLM provider — fully local, zero API key required."""

from __future__ import annotations
import logging

import httpx

from intelligence_core.llm.protocol import SYSTEM_PROMPT_DEFAULT

logger = logging.getLogger(__name__)


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
        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json={
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
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OllamaProvider.generate failed: %s", exc)
            return (
                f"[LLM unavailable — Ollama error: {exc}]\n\n"
                f"Most relevant context:\n{context[:600]}"
            )

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
