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

    # ── Reranking (cross-encoder) ──────────────────────────────────────────────
    # Re-order the candidate chunks with a cross-encoder before cutting to top_k.
    # Big lift for context_precision; needs the [st] extra (sentence-transformers).
    #   RERANK_ENABLED=false → keep the legacy keyword-boost behavior (default)
    #   RERANK_ENABLED=true  → cross-encoder rerank (downloads RERANK_MODEL once)
    # RERANK_CANDIDATES — how many chunks to fetch before reranking down to top_k.
    rerank_enabled:    bool = False
    rerank_model:      str  = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidates: int  = 30

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
    # ProposalIntelligence (PI_LLM_*)
    pi_llm_backend:  str = ""   # e.g. "claude"
    pi_llm_model:    str = ""
    pi_llm_base_url: str = ""
    pi_llm_api_key:  str = ""

    # ── ProposalIntelligence — questionari / gare (auto-risposta in stile) ─────
    # Embedder dedicato: il match domanda-su-domanda in IT/EN rende molto con un
    # modello multilingue, senza dover re-indicizzare le altre collezioni
    # (lasciale sull'embedder globale).
    #   PI_EMBED_BACKEND=st
    #   PI_EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
    pi_embed_backend: str = ""
    pi_embed_model:   str = ""
    # Modalità di risposta predefinita: "anchored" (solo fatti negli esempi) o
    # "commercial" (elaborazione persuasiva, claim fattuali comunque ancorati).
    proposal_mode:    str = "anchored"
    proposal_top_k:   int = 4   # quanti esempi Q&A passati usare come few-shot

    # ── Intent Routing ────────────────────────────────────────────────────────
    # Set INTENT_ROUTING=false to disable routing and keep current RAG behavior
    intent_routing:              bool  = True
    intent_confidence_threshold: float = 0.85
    # Set INTENT_AGENT_ENABLED=true to activate real AgentIntelligence (v0.5+)
    intent_agent_enabled:        bool  = False

    # ── Agent / Thinking mode (v0.5) ──────────────────────────────────────────
    # Controls chain-of-thought ("thinking") for thinking-capable models
    # (Qwen3, DeepSeek-R1, …) on the Ollama and vLLM backends.
    #   THINKING_MODE unset  → use the model's own default (nothing is sent)
    #   THINKING_MODE=true   → force thinking ON
    #   THINKING_MODE=false  → force thinking OFF (disables Qwen3 default thinking)
    # AGENT_MAX_ITERATIONS — max ReAct iterations before forcing a final answer
    thinking_mode:        bool | None = None
    agent_max_iterations: int  = 5

    # ── API authentication (v0.9.1) ───────────────────────────────────────────
    # IS_AUTH_ENABLED=false (default) → no checks, identical to v0.8.x.
    # IS_AUTH_ENABLED=true  → all /api/v1/* endpoints require:
    #     Authorization: Bearer <IS_API_KEY>
    # /health and / (web UI) remain public regardless.
    # Warning logged at boot if IS_AUTH_ENABLED=true and IS_API_KEY is empty.
    is_auth_enabled: bool = False
    is_api_key:      str  = ""

    # ── Observability (v0.9.2) ────────────────────────────────────────────────
    # Structured logging + opt-in metrics. All default to current behavior.
    #   IS_LOG_LEVEL    standard logging level (default INFO)
    #   IS_LOG_FORMAT   "json" (default, one JSON object per line) | "text"
    #   IS_METRICS_ENABLED=false (default) → GET /metrics returns 404 (no route);
    #                     true → GET /metrics returns in-memory counters as JSON.
    # Query/answer text is NEVER logged — only metadata (e.g. question length).
    is_log_level:       str  = "INFO"
    is_log_format:      str  = "json"
    is_metrics_enabled: bool = False

    # ── Ingestion service (v0.11.0) ───────────────────────────────────────────
    # On-demand parser+embed via API/UI. All default to current behavior (off).
    #   IS_INGEST_ENABLED=false (default) → no ingest routes, identical to v0.10.x.
    #   IS_INGEST_ROOT  empty (default)   → server-side path ingest disabled until
    #     you set it; when set, ``POST /ingest/path`` accepts only paths *inside*
    #     this directory (defence against path traversal).
    #   IS_INGEST_MAX_MB — per-file upload size cap (default 50 MB).
    is_ingest_enabled: bool = False
    is_ingest_root:    str  = ""
    is_ingest_max_mb:  int  = 50

    # ── Multi-project namespacing ─────────────────────────────────────────────
    # Set IS_PROJECT to isolate collections and state dirs per project.
    # Default ("default") replicates the exact single-project behavior of v0.8.x.
    # Example: IS_PROJECT=acme  → collections acme_code_intelligence, …
    #                             state dirs  ~/.intelligence_suite/acme/…
    is_project: str = "default"

    # ── Server ports (one per module, avoids conflicts when running together) ──
    ci_port:       int = 8080   # CodeIntelligence
    di_port:       int = 8081   # DocIntelligence
    mi_port:       int = 8082   # MentorIntelligence
    si_port:       int = 8083   # SkillIntelligence
    agent_port:    int = 8084   # AgentIntelligence
    pi_port:       int = 8085   # ProposalIntelligence
    gw_port:       int = 8086   # OpenAI-compatible Gateway (for OpenWebUI & co.)
    launcher_port: int = 8079   # Launcher dashboard

    # ── Gateway (OpenAI-compatible adapter) ───────────────────────────────────
    # Host the gateway uses to reach the module servers. "localhost" for a
    # single-host run; in docker-compose set GW_UPSTREAM_HOST to a service name
    # (or per-service via the module ports), e.g. GW_UPSTREAM_HOST=is-core.
    gw_upstream_host: str = "localhost"

    # ── Shared server settings ─────────────────────────────────────────────────
    api_host:  str = "0.0.0.0"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
