"""OpenAI-compatible LLM provider.

Covers any API that speaks the OpenAI Chat Completions protocol:
  - OpenAI          base_url="https://api.openai.com/v1"
  - vLLM            base_url="http://localhost:8000/v1"
  - LM Studio       base_url="http://localhost:1234/v1"
  - Groq            base_url="https://api.groq.com/openai/v1"
  - Mistral AI      base_url="https://api.mistral.ai/v1"
  - Azure OpenAI    base_url="https://<resource>.openai.azure.com/openai/deployments/<model>"
  - Together AI     base_url="https://api.together.xyz/v1"

Requirements:
    pip install "intelligence-suite[openai]"

Config (.env):
    LLM_BACKEND=openai          # or vllm — same provider, different base_url
    OPENAI_API_KEY=sk-...
    OPENAI_MODEL=gpt-4o
    OPENAI_BASE_URL=https://api.openai.com/v1

For vLLM (local GPU server):
    LLM_BACKEND=vllm
    OPENAI_BASE_URL=http://localhost:8000/v1
    OPENAI_MODEL=mistralai/Mistral-7B-Instruct-v0.2
    OPENAI_API_KEY=not-needed
"""

from __future__ import annotations
import logging

from intelligence_core.llm.protocol import SYSTEM_PROMPT_DEFAULT

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    """
    Single provider for all OpenAI-compatible endpoints.
    Point ``base_url`` at any compatible server to switch backend.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        backend_hint: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "not-needed"
        self.model = model
        self._backend_hint = backend_hint

    @property
    def backend_name(self) -> str:
        # Explicit hint from factory takes precedence (e.g. "vllm")
        if self._backend_hint:
            return self._backend_hint
        if "openai.com" in self.base_url:
            return "openai"
        if "groq.com" in self.base_url:
            return "groq"
        if "mistral.ai" in self.base_url:
            return "mistral"
        if "together.xyz" in self.base_url:
            return "together"
        if "azure.com" in self.base_url:
            return "azure-openai"
        return "vllm"  # local OpenAI-compat server (vLLM, LM Studio, …)

    def generate(
        self,
        question: str,
        context: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package not installed. "
                "Run: pip install 'intelligence-suite[openai]'"
            ) from exc

        system = system_prompt or SYSTEM_PROMPT_DEFAULT
        user_msg = f"Context:\n{context}\n\nQuestion: {question}"
        try:
            client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("OpenAICompatProvider.generate failed: %s", exc)
            return (
                f"[LLM error ({self.backend_name}): {exc}]\n\n"
                f"Most relevant context:\n{context[:600]}"
            )

    def is_available(self) -> bool:
        try:
            from openai import OpenAI
            client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            client.models.list()
            return True
        except Exception:
            return False
