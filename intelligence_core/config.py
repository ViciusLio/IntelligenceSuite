"""Centralised configuration via environment variables / .env file."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # ── Ollama (local LLM + embeddings) ────────────────────────────────────────
    ollama_base_url:    str = "http://localhost:11434"
    ollama_model:       str = "qwen2.5-coder:7b"
    ollama_embed_model: str = "nomic-embed-text"
    # Timeout in seconds for Ollama generation (CPU can be slow on long answers)
    # Override via OLLAMA_TIMEOUT=300 in .env
    ollama_timeout:     float = 300.0

    # ── LLM generation backend ─────────────────────────────────────────────────
    # Choices: ollama | openai | vllm | claude
    # "vllm" uses the same OpenAI-compat client as "openai" — just set
    # OPENAI_BASE_URL to your vLLM server (e.g. http://localhost:8000/v1)
    llm_backend: str = "ollama"

    # OpenAI / vLLM / Groq / Mistral / any OpenAI-compatible server
    openai_api_key:  str = ""
    openai_model:    str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    # Anthropic Claude
    anthropic_api_key: str = ""
    claude_model:      str = "claude-opus-4-5"

    # ── Escalation policy ──────────────────────────────────────────────────────
    # When confidence < threshold, escalate to Claude API (if key is set)
    escalation_threshold:  float = 0.70
    escalation_max_tokens: int   = 4096

    # ── Embedding backend ──────────────────────────────────────────────────────
    # Choices: ollama | st (sentence-transformers) | claude (voyage)
    embed_backend:    str = "ollama"
    embed_batch_size: int = 32
    # SentenceTransformer model — change for multilingual support:
    #   English only (fast, 384-dim):   all-MiniLM-L6-v2  (default)
    #   Multilingual 50+ langs (384-dim): paraphrase-multilingual-MiniLM-L12-v2
    #   Multilingual high quality (768-dim): paraphrase-multilingual-mpnet-base-v2
    st_model: str = "all-MiniLM-L6-v2"

    # ── Vector store ───────────────────────────────────────────────────────────
    vector_store:       str = "chromadb"
    # Default: ~/.intelligence_suite/chroma  (absolute — works from any CWD)
    # Override via CHROMA_PERSIST_DIR in .env, e.g. CHROMA_PERSIST_DIR=./.chroma
    chroma_persist_dir: str = "~/.intelligence_suite/chroma"
    pgvector_dsn:       str = ""

    @field_validator("chroma_persist_dir", mode="before")
    @classmethod
    def _resolve_chroma_dir(cls, v: str) -> str:
        """Expand ~ and resolve to an absolute path so CWD never matters."""
        return str(Path(v).expanduser().resolve())

    # ── Per-module LLM overrides ───────────────────────────────────────────────
    # Leave empty to use the global LLM_BACKEND / OLLAMA_MODEL / OPENAI_* settings.
    # Set any combination to route a specific module to a different backend or model.
    #
    # CodeIntelligence  (CI_LLM_*)
    ci_llm_backend:  str = ""   # e.g. "ollama" | "openai" | "vllm" | "claude"
    ci_llm_model:    str = ""   # e.g. "qwen2.5-coder:7b"
    ci_llm_base_url: str = ""   # e.g. "http://gpu-server:8000/v1"
    ci_llm_api_key:  str = ""
    # DocIntelligence   (DI_LLM_*)
    di_llm_backend:  str = ""   # e.g. "ollama" | "openai" | "claude"
    di_llm_model:    str = ""   # e.g. "mistral:7b"
    di_llm_base_url: str = ""
    di_llm_api_key:  str = ""
    # MentorIntelligence (MI_LLM_*)
    mi_llm_backend:  str = ""   # e.g. "claude"
    mi_llm_model:    str = ""   # e.g. "claude-sonnet-4-5"
    mi_llm_base_url: str = ""
    mi_llm_api_key:  str = ""

    # ── Intent Routing ────────────────────────────────────────────────────────
    # Set INTENT_ROUTING=false to disable routing and keep current RAG behavior
    intent_routing:              bool  = True
    intent_confidence_threshold: float = 0.85
    # AgentIntelligence is stub in v0.4 — if AGENT detected, falls back to RAG
    intent_agent_enabled:        bool  = False

    # ── Server ports (one per module, avoids conflicts when running together) ──
    ci_port:       int = 8080   # CodeIntelligence
    di_port:       int = 8081   # DocIntelligence
    mi_port:       int = 8082   # MentorIntelligence
    si_port:       int = 8083   # SkillIntelligence
    agent_port:    int = 8084   # AgentIntelligence (reserved — stub in v0.4)
    launcher_port: int = 8079   # Launcher dashboard

    # ── Shared server settings ─────────────────────────────────────────────────
    api_host:  str = "0.0.0.0"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
