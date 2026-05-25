"""LLMProvider Protocol — unified interface for all generation backends."""

from __future__ import annotations
from typing import Protocol, runtime_checkable

SYSTEM_PROMPT_DEFAULT = (
    "You are an expert technical assistant. "
    "Answer the user's question using ONLY the provided context. "
    "Be precise and concise. Cite the source file when relevant. "
    "If the answer is not in the context, say so explicitly."
)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol that every LLM backend must satisfy."""

    @property
    def backend_name(self) -> str:
        """Human-readable identifier, e.g. 'ollama', 'openai', 'claude'."""
        ...

    def generate(
        self,
        question: str,
        context: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        """
        Generate an answer given a question and a pre-built context string.

        Args:
            question:      The user's question.
            context:       Concatenated text of retrieved chunks.
            system_prompt: Override the default system prompt if needed.
            max_tokens:    Maximum tokens in the generated reply.
            temperature:   Sampling temperature (0.0 = deterministic).

        Returns:
            Generated answer as plain text.
        """
        ...

    def is_available(self) -> bool:
        """Quick connectivity / configuration check. Non-blocking preferred."""
        ...
