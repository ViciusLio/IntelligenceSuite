"""Centralised configuration via environment variables / .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # ── Ollama (local LLM + embeddings) ────────────────────────────────────────
    ollama_base_url:    str = "http://localhost:11434"
    ollama_model:       str = "qwen2.5-coder:7b"
    ollama_embed_model: str = "nomic-embed-text"

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
    chroma_persist_dir: str = "./.chroma"
    pgvector_dsn:       str = ""

    # ── Server ports (one per module, avoids conflicts when running together) ──
    ci_port: int = 8080   # CodeIntelligence
    di_port: int = 8081   # DocIntelligence
    mi_port: int = 8082   # MentorIntelligence

    # ── Shared server settings ─────────────────────────────────────────────────
    api_host:  str = "0.0.0.0"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
