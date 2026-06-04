"""Server REST per ProposalIntelligence.

Endpoint:
  GET  /health                      — stato + numero coppie indicizzate + backend LLM
  POST /api/v1/proposal/answer      — risposte in stile a una lista di domande
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from intelligence_core.config import settings
from intelligence_core.store import ChromaStore
from ProposalIntelligence import COLLECTION_NAME
from ProposalIntelligence.answer import answer_questions
from ProposalIntelligence.web import PROPOSAL_HTML


class AnswerRequest(BaseModel):
    questions: list[str]
    mode:  str | None = None     # "anchored" | "commercial"
    top_k: int | None = None


class AnswerItem(BaseModel):
    question: str
    answer:   str
    sources:  list[dict]


class AnswerResponse(BaseModel):
    mode:    str
    backend: str
    answers: list[AnswerItem]


def build_app() -> FastAPI:
    app = FastAPI(title="ProposalIntelligence Server", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from intelligence_core.auth import add_auth_middleware, warn_if_key_missing
    add_auth_middleware(app)
    warn_if_key_missing()

    from intelligence_core import paths
    store = ChromaStore(collection_name=paths.collection_name("qa"),
                        persist_dir=str(paths.chroma_dir()))

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        return HTMLResponse(content=PROPOSAL_HTML)

    @app.get("/health")
    def health():
        from intelligence_core.llm import get_module_llm_provider
        return {
            "status":         "ok",
            "module":         "proposal",
            "chunks_indexed": store.count(),
            "llm_backend":    get_module_llm_provider("pi").backend_name,
            "default_mode":   settings.proposal_mode,
        }

    @app.post("/api/v1/proposal/answer", response_model=AnswerResponse)
    def answer(req: AnswerRequest):
        from intelligence_core.llm import get_module_llm_provider
        mode = req.mode or settings.proposal_mode
        llm = get_module_llm_provider("pi")
        answered = answer_questions(
            req.questions, mode=mode, top_k=req.top_k, llm=llm
        )
        return AnswerResponse(
            mode=mode,
            backend=llm.backend_name,
            answers=[
                AnswerItem(question=a.question, answer=a.answer, sources=a.sources)
                for a in answered
            ],
        )

    return app


app = build_app()


def main():
    uvicorn.run(
        "ProposalIntelligence.proposal_server:app",
        host=settings.api_host,
        port=settings.pi_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
