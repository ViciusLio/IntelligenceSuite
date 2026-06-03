"""Test di ProposalIntelligence: parser Q&A, ingest, prompt, orchestratore.

Niente rete: l'orchestratore usa retriever + LLM finti.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import intelligence_core.embedder as embedder_mod
from ProposalIntelligence import answer as answer_mod
from ProposalIntelligence.answer import (
    AnsweredQuestion,
    answer_questions,
    render_markdown,
)
from ProposalIntelligence.ingest_qa import _pair_to_chunk, ingest_qa
from ProposalIntelligence.prompts import (
    build_fewshot_context,
    system_prompt_for,
    temperature_for,
)
from ProposalIntelligence.qa_parser import parse_qa_pairs, parse_questions


# ── qa_parser: coppie ────────────────────────────────────────────────────────
def test_parse_pairs_markdown_table(tmp_path):
    f = tmp_path / "corpus.md"
    f.write_text(
        "# Titolo\n\n"
        "| Domanda | Risposta |\n"
        "|---|---|\n"
        "| Avete esperienza cloud? | Sì, ampia esperienza su progetti complessi. |\n"
        "| Supporto 24/7? | Offriamo presidi dedicati con SLA. |\n",
        encoding="utf-8",
    )
    pairs = parse_qa_pairs(f)
    assert len(pairs) == 2
    assert pairs[0][0] == "Avete esperienza cloud?"
    assert pairs[1][1].startswith("Offriamo presidi")


def test_parse_pairs_skips_html_comments_and_header(tmp_path):
    f = tmp_path / "corpus.md"
    f.write_text(
        "<!--\n"
        "Nota: tabella a 2 colonne (Domanda | Risposta). Nessun dato reale.\n"
        "-->\n\n"
        "# Corpus\n\n"
        "| Domanda | Risposta |\n"
        "|---|---|\n"
        "| Prima? | Risposta uno. |\n"
        "| Seconda? | Risposta due. |\n",
        encoding="utf-8",
    )
    pairs = parse_qa_pairs(f)
    assert pairs == [
        ("Prima?", "Risposta uno."),
        ("Seconda?", "Risposta due."),
    ]


def test_parse_pairs_markers_multiline(tmp_path):
    f = tmp_path / "corpus.txt"
    f.write_text(
        "D: Prima domanda?\n"
        "R: Prima riga della risposta.\n"
        "Seconda riga della stessa risposta.\n"
        "\n"
        "Domanda: Seconda domanda?\n"
        "Risposta: Risposta secca.\n",
        encoding="utf-8",
    )
    pairs = parse_qa_pairs(f)
    assert len(pairs) == 2
    assert "Seconda riga" in pairs[0][1]
    assert pairs[1][0] == "Seconda domanda?"


def test_parse_pairs_csv(tmp_path):
    f = tmp_path / "corpus.csv"
    f.write_text(
        "Domanda,Risposta\n"
        "Domanda uno?,Risposta uno.\n"
        "Domanda due?,Risposta due.\n",
        encoding="utf-8",
    )
    pairs = parse_qa_pairs(f)
    assert pairs == [
        ("Domanda uno?", "Risposta uno."),
        ("Domanda due?", "Risposta due."),
    ]


# ── qa_parser: sole domande ──────────────────────────────────────────────────
def test_parse_questions_numbered(tmp_path):
    f = tmp_path / "q.md"
    f.write_text("# Questionario\n\n1. Prima?\n2. Seconda?\n3. Terza?\n", encoding="utf-8")
    assert parse_questions(f) == ["Prima?", "Seconda?", "Terza?"]


def test_parse_questions_table_and_bullets(tmp_path):
    table = tmp_path / "t.md"
    table.write_text(
        "| Domanda |\n|---|\n| Alpha? |\n| Beta? |\n", encoding="utf-8"
    )
    assert parse_questions(table) == ["Alpha?", "Beta?"]

    bullets = tmp_path / "b.md"
    bullets.write_text("- Uno?\n- Due?\n", encoding="utf-8")
    assert parse_questions(bullets) == ["Uno?", "Due?"]


# ── ingest ───────────────────────────────────────────────────────────────────
def test_pair_to_chunk_shape():
    c = _pair_to_chunk("Domanda X?", "Risposta Y.", "corpus.md")
    assert c["domain"] == "qa"
    assert c["type"] == "qa_pair"
    assert c["id"].startswith("qa::qa_pair::")
    assert c["text"] == "D: Domanda X?\n\nR: Risposta Y."
    assert c["metadata"]["question"] == "Domanda X?"
    assert c["metadata"]["answer"] == "Risposta Y."


def test_ingest_dedups_same_question(tmp_path):
    f = tmp_path / "corpus.md"
    f.write_text(
        "| Domanda | Risposta |\n|---|---|\n"
        "| Stessa? | Prima. |\n"
        "| Stessa? | Seconda (duplicato). |\n",
        encoding="utf-8",
    )
    chunks = ingest_qa(f, output=None)
    assert len(chunks) == 1   # la domanda duplicata è scartata
    assert chunks[0]["metadata"]["answer"] == "Prima."


# ── prompts ──────────────────────────────────────────────────────────────────
def test_system_prompt_modes_differ():
    anchored = system_prompt_for("anchored")
    commercial = system_prompt_for("commercial")
    assert "ANCORATA" in anchored
    assert "COMMERCIALE" in commercial
    assert temperature_for("anchored") < temperature_for("commercial")


def test_system_prompt_invalid_mode():
    with pytest.raises(ValueError):
        system_prompt_for("inventata")


def test_build_fewshot_context_numbers_examples():
    hits = [{"text": "D: a?\n\nR: b."}, {"text": "D: c?\n\nR: d."}]
    ctx = build_fewshot_context(hits)
    assert "Esempio 1:" in ctx and "Esempio 2:" in ctx
    assert "D: a?" in ctx


# ── orchestratore (retriever + LLM finti) ────────────────────────────────────
@dataclass
class _Hit:
    chunk: dict
    score: float = 0.9


class _FakeRetriever:
    def __init__(self, chunks):
        self._chunks = chunks
        self.last_query = None

    def search(self, query, top_k=5, domain=None):
        self.last_query = query
        return [_Hit(chunk=c) for c in self._chunks[:top_k]]


class _CapturingLLM:
    backend_name = "fake"

    def __init__(self):
        self.calls = []

    def generate(self, question, context, *, system_prompt=None, temperature=0.1, **kw):
        self.calls.append(
            {"q": question, "ctx": context, "sys": system_prompt, "temp": temperature}
        )
        return f"Risposta a: {question}"


def test_answer_questions_uses_mode_prompt_and_context():
    chunks = [
        {"text": "D: Esempio?\n\nR: Modello di risposta.", "source": "corpus.md"},
    ]
    retr = _FakeRetriever(chunks)
    llm = _CapturingLLM()

    out = answer_questions(
        ["Avete esperienza?"], mode="commercial", top_k=3, retriever=retr, llm=llm
    )

    assert len(out) == 1
    assert isinstance(out[0], AnsweredQuestion)
    assert out[0].answer == "Risposta a: Avete esperienza?"
    assert out[0].sources[0]["source"] == "corpus.md"
    # ha usato il prompt commerciale e la sua temperatura
    assert "COMMERCIALE" in llm.calls[0]["sys"]
    assert llm.calls[0]["temp"] == temperature_for("commercial")
    # il contesto few-shot contiene l'esempio recuperato
    assert "Modello di risposta" in llm.calls[0]["ctx"]


def test_render_markdown_structure():
    answered = [
        AnsweredQuestion(question="Q1?", answer="A1", sources=[{"source": "c.md", "score": 0.8}]),
    ]
    md = render_markdown(answered, "anchored")
    assert "# Risposte al questionario" in md
    assert "Modalità: **anchored**" in md
    assert "## 1. Q1?" in md
    assert "Fonti di stile: c.md (0.8)" in md


# ── per-module embedder override ─────────────────────────────────────────────
def test_get_module_embedder_reads_pi_override(monkeypatch):
    from intelligence_core.config import settings

    monkeypatch.setattr(settings, "pi_embed_backend", "st", raising=False)
    monkeypatch.setattr(settings, "pi_embed_model", "multi-model", raising=False)

    captured = {}

    def _fake_get_embedder(backend=None, *, model=None):
        captured["backend"] = backend
        captured["model"] = model
        return object()

    monkeypatch.setattr(embedder_mod, "get_embedder", _fake_get_embedder)
    embedder_mod.get_module_embedder("pi")
    assert captured == {"backend": "st", "model": "multi-model"}


def test_get_module_embedder_falls_back_to_global(monkeypatch):
    from intelligence_core.config import settings

    monkeypatch.setattr(settings, "pi_embed_backend", "", raising=False)
    monkeypatch.setattr(settings, "pi_embed_model", "", raising=False)

    captured = {}

    def _fake_get_embedder(backend=None, *, model=None):
        captured["backend"] = backend
        captured["model"] = model
        return object()

    monkeypatch.setattr(embedder_mod, "get_embedder", _fake_get_embedder)
    embedder_mod.get_module_embedder("pi")
    assert captured == {"backend": None, "model": None}  # → globali
