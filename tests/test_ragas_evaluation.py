"""Test per la pipeline di valutazione RAGAS.

I test unitari non richiedono chiamate LLM reali — mockano RAGAS per
isolare la logica di report/evaluator/generator.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# --- Unit test: report.py ---


def test_print_report_no_previous(capsys):
    from intelligence_core.evaluation.report import print_report

    evaluation = {
        "scores": {"faithfulness": 0.80, "answer_relevancy": 0.78,
                   "context_precision": 0.72, "context_recall": 0.70},
        "targets": {"faithfulness": 0.75, "answer_relevancy": 0.75,
                    "context_precision": 0.70, "context_recall": 0.68},
        "passed": {"faithfulness": True, "answer_relevancy": True,
                   "context_precision": True, "context_recall": True},
        "overall_pass": True,
    }
    print_report(evaluation, "code", previous=None)
    captured = capsys.readouterr()
    assert "PASS" in captured.out
    assert "faithfulness" in captured.out


def test_print_report_with_delta(capsys):
    from intelligence_core.evaluation.report import print_report

    evaluation = {
        "scores": {"faithfulness": 0.85, "answer_relevancy": 0.80,
                   "context_precision": 0.75, "context_recall": 0.72},
        "targets": {"faithfulness": 0.75, "answer_relevancy": 0.75,
                    "context_precision": 0.70, "context_recall": 0.68},
        "passed": {"faithfulness": True, "answer_relevancy": True,
                   "context_precision": True, "context_recall": True},
        "overall_pass": True,
    }
    previous = {
        "scores": {"faithfulness": 0.80, "answer_relevancy": 0.77,
                   "context_precision": 0.70, "context_recall": 0.69}
    }
    print_report(evaluation, "code", previous=previous)
    captured = capsys.readouterr()
    assert "↑" in captured.out


def test_report_fail_when_below_target(capsys):
    from intelligence_core.evaluation.report import print_report

    evaluation = {
        "scores": {"faithfulness": 0.60, "answer_relevancy": 0.78,
                   "context_precision": 0.65, "context_recall": 0.70},
        "targets": {"faithfulness": 0.75, "answer_relevancy": 0.75,
                    "context_precision": 0.70, "context_recall": 0.68},
        "passed": {"faithfulness": False, "answer_relevancy": True,
                   "context_precision": False, "context_recall": True},
        "overall_pass": False,
    }
    print_report(evaluation, "code")
    captured = capsys.readouterr()
    assert "FAIL" in captured.out
    assert "✗" in captured.out


def test_save_and_load_report(tmp_path):
    from intelligence_core.evaluation import report as rep

    rep.EVAL_DIR = tmp_path  # override per il test

    evaluation = {
        "scores": {"faithfulness": 0.80},
        "targets": {"faithfulness": 0.75},
        "passed": {"faithfulness": True},
        "overall_pass": True,
    }
    path = rep.save_report(evaluation, "code")
    assert path.exists()

    loaded = rep.load_previous_report("code")
    assert loaded is not None
    assert loaded["scores"]["faithfulness"] == 0.80


def test_load_previous_report_missing(tmp_path):
    from intelligence_core.evaluation import report as rep

    rep.EVAL_DIR = tmp_path
    assert rep.load_previous_report("doc") is None


# --- Unit test: evaluator.py ---


def test_evaluator_all_pass():
    from intelligence_core.evaluation.evaluator import KPI_TARGETS, evaluate_results

    mock_scores = {k: v + 0.05 for k, v in KPI_TARGETS.items()}

    with patch("intelligence_core.evaluation.evaluator.evaluate", return_value=mock_scores):
        with patch("intelligence_core.evaluation.evaluator.Dataset"):
            results = [{"question": "q", "answer": "a",
                        "contexts": ["c"], "ground_truth": "g"}]
            evaluation = evaluate_results(results)

    assert evaluation["overall_pass"] is True
    assert all(evaluation["passed"].values())


def test_evaluator_partial_fail():
    from intelligence_core.evaluation.evaluator import KPI_TARGETS, evaluate_results

    mock_scores = dict(KPI_TARGETS)
    mock_scores["faithfulness"] = 0.50  # sotto target

    with patch("intelligence_core.evaluation.evaluator.evaluate", return_value=mock_scores):
        with patch("intelligence_core.evaluation.evaluator.Dataset"):
            results = [{"question": "q", "answer": "a",
                        "contexts": ["c"], "ground_truth": "g"}]
            evaluation = evaluate_results(results)

    assert evaluation["overall_pass"] is False
    assert evaluation["passed"]["faithfulness"] is False


# --- Unit test: paths.py ---


def test_paths_chunks_and_collection():
    from intelligence_core.evaluation.paths import get_chunks_path, get_collection

    assert get_chunks_path("code", base_dir=Path("/x")).name == "chunks.jsonl"
    assert get_chunks_path("doc", base_dir=Path("/x")).name == "doc_chunks.jsonl"
    assert get_collection("mentor") == "mentor_intelligence"


# --- Unit test: generator.py ---


def test_generator_loads_from_cache(tmp_path):
    from intelligence_core.evaluation import generator as gen

    cache_data = [{"question": "test?", "ground_truth": "risposta"}]
    cache_path = tmp_path / "code_testset.jsonl"
    with open(cache_path, "w", encoding="utf-8") as f:
        for row in cache_data:
            f.write(json.dumps(row) + "\n")

    result = gen._load_from_cache(cache_path)
    assert len(result) == 1
    assert result[0]["question"] == "test?"


def test_generator_raises_if_no_chunks(tmp_path):
    from intelligence_core.evaluation.generator import generate_testset

    with patch("intelligence_core.evaluation.generator._get_chunks_path",
               return_value=tmp_path / "nonexistent.jsonl"):
        with patch("intelligence_core.evaluation.generator.Path",
                   return_value=tmp_path / "no_cache.jsonl"):
            with pytest.raises(FileNotFoundError):
                generate_testset("code", test_size=5)


def test_normalize_row_maps_ragas_fields():
    from intelligence_core.evaluation.generator import _normalize_row

    row = _normalize_row({"user_input": "Q?", "reference": "A"})
    assert row["question"] == "Q?"
    assert row["ground_truth"] == "A"


def test_generator_generation_path(tmp_path):
    from intelligence_core.evaluation import generator as gen

    cache = tmp_path / "code_testset.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text('{"text":"x"}\n', encoding="utf-8")

    fake_ts = MagicMock()
    fake_ts.to_pandas.return_value.to_dict.return_value = [
        {"user_input": "Q", "reference": "A"}
    ]
    fake_gen = MagicMock()
    fake_gen.generate_with_langchain_docs.return_value = fake_ts

    with patch("intelligence_core.evaluation.generator.Path", return_value=cache), \
         patch("intelligence_core.evaluation.generator._get_chunks_path", return_value=chunks), \
         patch("intelligence_core.evaluation.generator._load_chunks_as_documents",
               return_value=["doc"]), \
         patch("ragas.testset.TestsetGenerator", return_value=fake_gen), \
         patch("intelligence_core.evaluation.ragas_factory.get_ragas_llm",
               return_value=MagicMock()), \
         patch("intelligence_core.evaluation.ragas_factory.get_ragas_embeddings",
               return_value=MagicMock()):
        rows = gen.generate_testset("code", test_size=2, force_regenerate=True)

    assert rows[0]["question"] == "Q"
    assert rows[0]["ground_truth"] == "A"
    assert cache.exists()


# --- Unit test: runner.py ---


def test_runner_builds_results():
    from intelligence_core.evaluation import runner

    fake_result = MagicMock()
    fake_result.chunk = {"text": "contesto rilevante"}
    fake_retriever = MagicMock()
    fake_retriever.search.return_value = [fake_result]
    fake_llm = MagicMock()
    fake_llm.generate.return_value = "risposta generata"

    with patch("intelligence_core.retriever.Retriever.load_default",
               return_value=fake_retriever), \
         patch("intelligence_core.llm.get_llm_provider", return_value=fake_llm):
        results = runner.run_testset(
            [{"question": "domanda?", "ground_truth": "gt"}], "code", top_k=3
        )

    assert len(results) == 1
    assert results[0]["answer"] == "risposta generata"
    assert results[0]["contexts"] == ["contesto rilevante"]
    assert results[0]["ground_truth"] == "gt"
    fake_retriever.search.assert_called_once_with(query="domanda?", top_k=3, domain="code")


# --- Unit test: ragas_factory.py ---


def test_ragas_factory_llm():
    from intelligence_core.evaluation import ragas_factory as rf

    with patch("langchain_openai.ChatOpenAI") as chat, \
         patch("ragas.llms.LangchainLLMWrapper", side_effect=lambda x: ("wrapped", x)) as wrap:
        out = rf.get_ragas_llm()

    assert out[0] == "wrapped"
    chat.assert_called_once()
    wrap.assert_called_once()


def test_ragas_factory_embeddings_adapter():
    from intelligence_core.evaluation import ragas_factory as rf

    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.1, 0.2]]
    fake_embedder.embed_one.return_value = [0.3, 0.4]

    with patch("intelligence_core.embedder.get_embedder", return_value=fake_embedder), \
         patch("ragas.embeddings.LangchainEmbeddingsWrapper", side_effect=lambda x: x):
        adapter = rf.get_ragas_embeddings()

    assert adapter.embed_documents(["a"]) == [[0.1, 0.2]]
    assert adapter.embed_query("q") == [0.3, 0.4]


async def test_ragas_factory_embeddings_async():
    from intelligence_core.evaluation.ragas_factory import _ProjectEmbeddings

    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[1.0]]
    fake_embedder.embed_one.return_value = [2.0]
    adapter = _ProjectEmbeddings(fake_embedder)

    assert await adapter.aembed_documents(["a"]) == [[1.0]]
    assert await adapter.aembed_query("q") == [2.0]


# --- Integration test (skippato se chunks reali non disponibili) ---


@pytest.mark.skipif(
    not (Path.cwd() / "chunks.jsonl").exists(),
    reason="chunks.jsonl non disponibile — esegui ci-parse e ci-embed",
)
def test_load_chunks_as_documents():
    from intelligence_core.evaluation.generator import _load_chunks_as_documents

    docs = _load_chunks_as_documents(Path.cwd() / "chunks.jsonl")
    assert len(docs) > 0
    assert hasattr(docs[0], "page_content")
    assert len(docs[0].page_content) > 0
