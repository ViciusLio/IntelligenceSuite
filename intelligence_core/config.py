"""Configurazione centralizzata via variabili d'ambiente."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Ollama
    ollama_base_url:    str   = "http://localhost:11434"
    ollama_model:       str   = "qwen2.5-coder:7b"
    ollama_embed_model: str   = "nomic-embed-text"

    # Escalation
    anthropic_api_key:     str   = ""
    escalation_threshold:  float = 0.70
    escalation_max_tokens: int   = 4096

    # Vector Store
    vector_store:       str = "chromadb"
    chroma_persist_dir: str = "./.chroma"
    pgvector_dsn:       str = ""

    # Server
    api_port:  int = 8080
    api_host:  str = "0.0.0.0"
    log_level: str = "INFO"

    # Embedding
    embed_backend:    str = "ollama"
    embed_batch_size: int = 32

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
