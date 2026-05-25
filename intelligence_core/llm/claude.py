"""Anthropic Claude LLM provider.

Requirements:
    pip install "intelligence-suite[claude]"

Config (.env):
    LLM_BACKEND=claude
    ANTHROPIC_API_KEY=sk-ant-...
    CLAUDE_MODEL=claude-opus-4-5
"""

from __future__ import annotations
import logging

from intelligence_core.llm.protocol import SYSTEM_PROMPT_DEFAULT

logger = logging.getLogger(__name__)


class ClaudeProvider:
    """
    Calls the Anthropic Messages API.
    Requires ANTHROPIC_API_KEY and ``pip install anthropic``.
    """

    backend_name = "claude"

    def __init__(self, api_key: str = "", model: str = "claude-opus-4-5"):
        self.api_key = api_key
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
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package not installed. "
                "Run: pip install 'intelligence-suite[claude]'"
            ) from exc

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not configured. "
                "Set it in .env or export ANTHROPIC_API_KEY=sk-ant-..."
            )

        system = system_prompt or SYSTEM_PROMPT_DEFAULT
        user_msg = f"Context:\n{context}\n\nQuestion: {question}"
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            return resp.content[0].text.strip()
        except Exception as exc:
            logger.error("ClaudeProvider.generate failed: %s", exc)
            return (
                f"[Claude API error: {exc}]\n\n"
                f"Most relevant context:\n{context[:600]}"
            )

    def is_available(self) -> bool:
        return bool(self.api_key)
