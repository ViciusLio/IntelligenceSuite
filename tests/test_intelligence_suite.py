"""
Test suite per Intelligence Suite.
Copre: parser documenti, qualita chunk, benchmark retrieval, metriche KPI.

Esecuzione:
  pytest tests/ -v
  pytest tests/ -v -k "TestChunkFormat"     # solo formato chunk
  pytest tests/ -v -k "TestPDFParser"       # solo parser PDF
  pytest tests/ -v -k "TestMetricFunctions" # solo metriche pure
  pytest tests/ -v -k "TestKPIThresholds"   # solo KPI (richiede sistema attivo)
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Optional
import pytest

DOCS_DIR = Path(__file__).parent.parent / "docs"
PDF_API  = DOCS_DIR / "api_reference_v2.pdf"
PDF_OPS  = DOCS_DIR / "deploy_procedure_v3.pdf"
DOCX_ADR = DOCS_DIR / "ADR-007-vector-store.docx"
XLSX_KPI = DOCS_DIR / "intelligence_suite_kpi_benchmark.xlsx"


# ═══════════════════════════════════════════════════════════════════
# SEZIONE 1 — FORMATO CHUNK
# ═══════════════════════════════════════════════════════════════════

class TestChunkFormat:
    """Ogni chunk prodotto da qualsiasi parser deve rispettare il formato standard."""

    REQUIRED_FIELDS = {"id", "domain", "type", "text", "source", "language", "metadata"}
    VALID_DOMAINS   = {"code", "doc", "api", "data", "mentor"}
    VALID_DOC_TYPES = {"section", "table", "code_example", "definition", "procedure", "file"}

    def validate_chunk(self, chunk: dict) -> list[str]:
        errors = []
        for field in self.REQUIRED_FIELDS:
            if field not in chunk:
                errors.append(f"Campo mancante: {field}")
        if "id" in chunk:
            parts = chunk["id"].split("::")
            if len(parts) < 3:
                errors.append(f"ID malformato: {chunk['id']}")
        if "domain" in chunk and chunk["domain"] not in self.VALID_DOMAINS:
            errors.append(f"Domain non valido: {chunk['domain']}")
        if "type" in chunk and chunk.get("domain") == "doc":
            if chunk["type"] not in self.VALID_DOC_TYPES:
                errors.append(f"Tipo doc non valido: {chunk['type']}")
        if "text" in chunk:
            text = chunk["text"]
            if len(text.strip()) < 20:
                errors.append(f"Testo troppo corto ({len(text)} chars)")
            if len(text) > 8000:
                errors.append(f"Testo troppo lungo ({len(text)} chars)")
            if text.strip().startswith("{") and text.strip().endswith("}"):
                errors.append("Testo sembra JSON raw — non human-readable")
        if "source" in chunk:
            if not chunk["source"] or chunk["source"].startswith("/"):
                errors.append("Source deve essere path relativo")
        if "metadata" in chunk and not isinstance(chunk["metadata"], dict):
            errors.append("Metadata deve essere un dict")
        return errors

    def test_chunk_has_all_required_fields(self, sample_chunk):
        errors = self.validate_chunk(sample_chunk)
        assert not errors, f"Chunk non valido: {errors}"

    def test_chunk_text_is_human_readable(self, sample_chunk):
        """INVARIANTE: il testo deve essere comprensibile senza aprire il file originale."""
        text = sample_chunk.get("text", "")
        source = sample_chunk.get("source", "")
        filename = Path(source).stem if source else ""
        assert filename.lower() in text.lower() or len(text) > 100, \
            "Testo non autocontenuto: non menziona il file sorgente"

    def test_chunk_id_is_unique_within_document(self, chunks_from_same_doc):
        ids = [c["id"] for c in chunks_from_same_doc]
        assert len(ids) == len(set(ids)), \
            f"ID duplicati: {set(x for x in ids if ids.count(x) > 1)}"

    def test_chunk_checksum_matches_text(self, sample_chunk):
        if "checksum" in sample_chunk and sample_chunk["checksum"]:
            expected = hashlib.sha256(sample_chunk["text"].encode()).hexdigest()
            assert sample_chunk["checksum"] == expected, "Checksum non corrisponde"

    def test_metadata_has_page_info_for_pdf(self, sample_pdf_chunk):
        assert "page_start" in sample_pdf_chunk.get("metadata", {}), \
            "Chunk PDF deve avere page_start"

    def test_metadata_has_heading_path_for_section(self, sample_section_chunk):
        meta = sample_section_chunk.get("metadata", {})
        assert "heading_path" in meta, "Chunk section deve avere heading_path"
        assert isinstance(meta["heading_path"], list) and len(meta["heading_path"]) > 0


# ═══════════════════════════════════════════════════════════════════
# SEZIONE 2 — PARSER PDF
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not PDF_API.exists(), reason="File PDF non trovato in docs/")
class TestPDFParser:

    @pytest.fixture(scope="class")
    def api_chunks(self):
        try:
            from DocIntelligence.parsers.pdf_parser import parse_file
            return parse_file(PDF_API, PDF_API.parent)
        except ImportError:
            pytest.skip("DocIntelligence.parsers.pdf_parser non disponibile")

    def test_pdf_produces_chunks(self, api_chunks):
        assert len(api_chunks) > 0

    def test_pdf_extracts_multiple_sections(self, api_chunks):
        sections = [c for c in api_chunks if c.get("type") == "section"]
        assert len(sections) >= 3, f"Attese >= 3 sezioni, trovate {len(sections)}"

    def test_pdf_finds_authentication_content(self, api_chunks):
        texts = [c["text"].lower() for c in api_chunks]
        assert any("autenticaz" in t or "bearer" in t or "token" in t for t in texts)

    def test_pdf_finds_rate_limiting_content(self, api_chunks):
        texts = [c["text"].lower() for c in api_chunks]
        assert any("rate limit" in t or "query/minuto" in t or "piano" in t for t in texts)

    def test_pdf_chunks_have_page_numbers(self, api_chunks):
        for chunk in api_chunks:
            assert "page_start" in chunk.get("metadata", {}), \
                f"Chunk senza page_start: {chunk['id']}"

    def test_pdf_chunks_reference_source_file(self, api_chunks):
        filename = PDF_API.stem
        for chunk in api_chunks[:3]:
            assert filename.lower() in chunk["text"].lower() or \
                   chunk.get("source", "").endswith(".pdf"), \
                f"Chunk non referenzia il file sorgente: {chunk['id']}"

    def test_pdf_no_garbage_chunks(self, api_chunks):
        for chunk in api_chunks:
            assert len(chunk["text"].strip()) >= 30, \
                f"Chunk garbage: {repr(chunk['text'][:60])}"

    def test_pdf_chunk_uses_make_chunk_schema(self, api_chunks):
        try:
            from intelligence_core.chunk import validate_chunk
            for chunk in api_chunks:
                errors = validate_chunk(chunk)
                assert not errors, f"Chunk non valido: {errors} — {chunk['id']}"
        except ImportError:
            pytest.skip("intelligence_core non disponibile")

    def test_pdf_ops_procedure_has_rollback(self):
        try:
            from DocIntelligence.parsers.pdf_parser import parse_file
            chunks = parse_file(PDF_OPS, PDF_OPS.parent)
            assert len(chunks) > 0
            texts = [c["text"].lower() for c in chunks]
            assert any("rollback" in t for t in texts), \
                "Sezione rollback non trovata in deploy_procedure"
        except ImportError:
            pytest.skip("DocIntelligence non disponibile")


# ═══════════════════════════════════════════════════════════════════
# SEZIONE 3 — PARSER DOCX
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not DOCX_ADR.exists(), reason="File DOCX non trovato in docs/")
class TestDOCXParser:

    @pytest.fixture(scope="class")
    def adr_chunks(self):
        try:
            from DocIntelligence.parsers.docx_parser import parse_file
            return parse_file(DOCX_ADR, DOCX_ADR.parent)
        except ImportError:
            pytest.skip("DocIntelligence.parsers.docx_parser non disponibile")

    def test_docx_produces_chunks(self, adr_chunks):
        assert len(adr_chunks) > 0

    def test_docx_preserves_all_headings(self, adr_chunks):
        texts = " ".join(c["text"].lower() for c in adr_chunks)
        for heading in ["contesto", "decisione", "opzioni", "conseguenze"]:
            assert heading in texts, f"Heading '{heading}' non trovato"

    def test_docx_extracts_table_as_chunk(self, adr_chunks):
        table_chunks = [c for c in adr_chunks if c.get("type") == "table"]
        assert len(table_chunks) >= 1, "Nessun chunk table estratto"

    def test_docx_table_contains_pgvector(self, adr_chunks):
        table_chunks = [c for c in adr_chunks if c.get("type") == "table"]
        combined = " ".join(c["text"].lower() for c in table_chunks)
        assert "pgvector" in combined

    def test_docx_decision_is_findable(self, adr_chunks):
        texts = [c["text"].lower() for c in adr_chunks]
        assert any("pgvector" in t and ("scelt" in t or "decisio" in t or "adott" in t)
                   for t in texts), "Decisione pgvector non recuperabile"

    def test_docx_chunk_uses_make_chunk_schema(self, adr_chunks):
        try:
            from intelligence_core.chunk import validate_chunk
            for chunk in adr_chunks:
                errors = validate_chunk(chunk)
                assert not errors, f"Chunk non valido: {errors}"
        except ImportError:
            pytest.skip("intelligence_core non disponibile")


# ═══════════════════════════════════════════════════════════════════
# SEZIONE 4 — METRICHE DI RETRIEVAL
# ═══════════════════════════════════════════════════════════════════

def hit_at_k(retrieved_ids: list[str], relevant_id: str, k: int) -> bool:
    return relevant_id in retrieved_ids[:k]


def reciprocal_rank(retrieved_ids: list[str], relevant_id: str) -> float:
    try:
        return 1.0 / (retrieved_ids.index(relevant_id) + 1)
    except ValueError:
        return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    import math
    dcg = sum(
        (len(relevant_ids) - relevant_ids.index(rid)) / math.log2(i + 2)
        for i, rid in enumerate(retrieved_ids[:k])
        if rid in relevant_ids
    )
    idcg = sum(
        rel / math.log2(i + 2)
        for i, rel in enumerate(range(len(relevant_ids), 0, -1))
        if i < k
    )
    return dcg / idcg if idcg > 0 else 0.0


def compute_metrics(results: list[dict], k_values: list[int] = [1, 3, 5]) -> dict:
    metrics = {}
    mrr_scores = []
    for k in k_values:
        hits, ndcgs = [], []
        for r in results:
            rel = r["relevant"] if isinstance(r["relevant"], list) else [r["relevant"]]
            hits.append(float(any(hit_at_k(r["retrieved"], rv, k) for rv in rel)))
            ndcgs.append(ndcg_at_k(r["retrieved"], rel, k))
        metrics[f"hit_at_{k}"]  = sum(hits)  / len(hits)  if hits  else 0.0
        metrics[f"ndcg_at_{k}"] = sum(ndcgs) / len(ndcgs) if ndcgs else 0.0
    for r in results:
        rel = r["relevant"] if isinstance(r["relevant"], list) else [r["relevant"]]
        mrr_scores.append(max(reciprocal_rank(r["retrieved"], rv) for rv in rel))
    metrics["mrr"] = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0.0
    return metrics


class TestMetricFunctions:

    def test_hit_at_1_found(self):
        assert hit_at_k(["A", "B", "C"], "A", 1) is True

    def test_hit_at_1_not_found(self):
        assert hit_at_k(["A", "B", "C"], "D", 1) is False

    def test_hit_at_5_found_at_position_3(self):
        assert hit_at_k(["A", "B", "C", "D", "E"], "C", 5) is True

    def test_hit_at_3_not_found_at_position_4(self):
        assert hit_at_k(["A", "B", "C", "D", "E"], "D", 3) is False

    def test_reciprocal_rank_first(self):
        assert reciprocal_rank(["A", "B", "C"], "A") == pytest.approx(1.0)

    def test_reciprocal_rank_second(self):
        assert reciprocal_rank(["A", "B", "C"], "B") == pytest.approx(0.5)

    def test_reciprocal_rank_not_found(self):
        assert reciprocal_rank(["A", "B", "C"], "Z") == 0.0

    def test_ndcg_perfect(self):
        assert ndcg_at_k(["A", "B"], ["A", "B"], k=2) == pytest.approx(1.0)

    def test_ndcg_zero(self):
        assert ndcg_at_k(["X", "Y"], ["A", "B"], k=2) == pytest.approx(0.0)

    def test_compute_metrics_returns_all_keys(self):
        results = [
            {"query_id": "Q001", "retrieved": ["A", "B", "C"], "relevant": "A"},
            {"query_id": "Q002", "retrieved": ["X", "A", "C"], "relevant": "A"},
        ]
        m = compute_metrics(results, k_values=[1, 5])
        for key in ["hit_at_1", "hit_at_5", "ndcg_at_1", "ndcg_at_5", "mrr"]:
            assert key in m, f"Metrica mancante: {key}"
        assert 0.0 <= m["hit_at_1"] <= 1.0
        assert 0.0 <= m["mrr"] <= 1.0

    def test_hit_at_1_is_050_for_half_correct(self):
        results = [
            {"query_id": "Q001", "retrieved": ["A", "B"], "relevant": "A"},
            {"query_id": "Q002", "retrieved": ["B", "A"], "relevant": "A"},
        ]
        assert compute_metrics(results, k_values=[1])["hit_at_1"] == pytest.approx(0.5)


# ═══════════════════════════════════════════════════════════════════
# SEZIONE 5 — KPI THRESHOLDS (richiede sistema completo attivo)
# ═══════════════════════════════════════════════════════════════════

BENCHMARK_DATASET = [
    {"query_id": "Q001", "query": "Dove viene gestita l autenticazione JWT?",
     "relevant": "code::function::auth.validate_token", "difficulty": "easy", "category": "retrieval"},
    {"query_id": "Q002", "query": "Quali endpoint richiedono ruolo admin?",
     "relevant": "code::function::routes.admin_endpoints", "difficulty": "medium", "category": "reasoning"},
    {"query_id": "Q003", "query": "Come funziona l escalation da locale a Claude?",
     "relevant": "code::class::escalation.EscalationPolicy", "difficulty": "medium", "category": "retrieval"},
    {"query_id": "Q004", "query": "Quale modello embedding viene usato di default?",
     "relevant": "code::class::embedder.OllamaEmbedder", "difficulty": "easy", "category": "retrieval"},
    {"query_id": "Q005", "query": "Come si aggiunge un nuovo parser di linguaggio?",
     "relevant": "code::function::parsers.__init__.register_parser", "difficulty": "hard", "category": "reasoning"},
    {"query_id": "Q006", "query": "Dove vengono persistiti i chunk dopo embedding?",
     "relevant": "code::class::store.VectorStore", "difficulty": "medium", "category": "retrieval"},
    {"query_id": "Q007", "query": "Come funziona il delta update dell indice?",
     "relevant": "code::function::embed_chunks.incremental_update", "difficulty": "medium", "category": "retrieval"},
    {"query_id": "Q008", "query": "Quali test coprono il parser TypeScript?",
     "relevant": "code::function::tests.test_typescript", "difficulty": "easy", "category": "retrieval"},
    {"query_id": "Q009", "query": "Come ottenere un token API?",
     "relevant": "doc::section::APIRef.Autenticazione", "difficulty": "easy", "category": "retrieval"},
    {"query_id": "Q010", "query": "Rate limit piano Team?",
     "relevant": "doc::section::APIRef.RateLimiting", "difficulty": "easy", "category": "retrieval"},
    {"query_id": "Q011", "query": "Cosa fare se deploy fallisce entro 30 minuti?",
     "relevant": "doc::section::DeployProc.Rollback", "difficulty": "medium", "category": "reasoning"},
    {"query_id": "Q012", "query": "Perche pgvector invece di Pinecone?",
     "relevant": "doc::section::ADR007.Decisione", "difficulty": "hard", "category": "reasoning"},
    {"query_id": "Q013", "query": "Prerequisiti obbligatori prima di un deploy?",
     "relevant": "doc::section::DeployProc.PreRequisiti", "difficulty": "medium", "category": "retrieval"},
    {"query_id": "Q014", "query": "Latenza P99 garantita con escalation?",
     "relevant": "doc::section::APIRef.SLA", "difficulty": "easy", "category": "retrieval"},
    {"query_id": "Q015", "query": "Config rate limiting codice e documentazione?",
     "relevant": ["code::class::middleware.RateLimiter", "doc::section::APIRef.RateLimiting"],
     "difficulty": "hard", "category": "cross-domain"},
    {"query_id": "Q016", "query": "Rollback in procedura corrisponde al codice?",
     "relevant": ["doc::section::DeployProc.Rollback", "code::function::deploy.rollback"],
     "difficulty": "hard", "category": "cross-domain"},
]

KPI_THRESHOLDS = {
    "code":   {"hit_at_1": 0.60, "hit_at_5": 0.85, "mrr": 0.70, "ndcg_at_5": 0.75,
               "latency_p50_ms": 300, "latency_p99_ms": 1000},
    "doc":    {"hit_at_1": 0.55, "hit_at_5": 0.80, "mrr": 0.65, "ndcg_at_5": 0.70,
               "latency_p50_ms": 400, "latency_p99_ms": 1200},
    "system": {"escalation_rate": 0.15, "hallucination_rate": 0.05, "citation_precision": 0.90},
}


class TestKPIThresholds:

    @pytest.fixture(scope="class")
    def retrieval_system(self):
        try:
            from intelligence_core.retriever import Retriever
            r = Retriever.load_default()
            if r.store.count() == 0:
                pytest.skip("Nessun chunk indicizzato — esegui prima ci-parse + ci-embed")
            return r
        except (ImportError, Exception):
            pytest.skip("Sistema di retrieval non disponibile")

    def _run(self, retrieval_system, domain_filter=None):
        dataset = [q for q in BENCHMARK_DATASET
                   if domain_filter is None
                   or (domain_filter == "code" and int(q["query_id"][1:]) <= 8)
                   or (domain_filter == "doc"  and int(q["query_id"][1:]) >= 9)]
        results, latencies = [], []
        for item in dataset:
            t0 = time.perf_counter()
            retrieved = retrieval_system.search(item["query"], top_k=5)
            latencies.append((time.perf_counter() - t0) * 1000)
            results.append({
                "query_id":  item["query_id"],
                "retrieved": [r.chunk.get("id", "") for r in retrieved],
                "relevant":  item["relevant"],
            })
        metrics = compute_metrics(results, k_values=[1, 3, 5])
        latencies.sort()
        metrics["latency_p50_ms"] = latencies[len(latencies) // 2]
        metrics["latency_p99_ms"] = latencies[int(len(latencies) * 0.99)]
        return metrics

    def test_code_hit_at_5_above_threshold(self, retrieval_system):
        m = self._run(retrieval_system, "code")
        t = KPI_THRESHOLDS["code"]["hit_at_5"]
        assert m["hit_at_5"] >= t, f"Hit@5 code {m['hit_at_5']:.2%} < {t:.2%}"

    def test_doc_hit_at_5_above_threshold(self, retrieval_system):
        m = self._run(retrieval_system, "doc")
        t = KPI_THRESHOLDS["doc"]["hit_at_5"]
        assert m["hit_at_5"] >= t, f"Hit@5 doc {m['hit_at_5']:.2%} < {t:.2%}"

    def test_code_mrr_above_threshold(self, retrieval_system):
        m = self._run(retrieval_system, "code")
        t = KPI_THRESHOLDS["code"]["mrr"]
        assert m["mrr"] >= t, f"MRR code {m['mrr']:.3f} < {t}"

    def test_latency_p50_under_threshold(self, retrieval_system):
        m = self._run(retrieval_system)
        t = KPI_THRESHOLDS["code"]["latency_p50_ms"]
        assert m["latency_p50_ms"] <= t, f"P50 {m['latency_p50_ms']:.0f}ms > {t}ms"

    def test_latency_p99_under_threshold(self, retrieval_system):
        m = self._run(retrieval_system)
        t = KPI_THRESHOLDS["code"]["latency_p99_ms"]
        assert m["latency_p99_ms"] <= t, f"P99 {m['latency_p99_ms']:.0f}ms > {t}ms"


# ═══════════════════════════════════════════════════════════════════
# SEZIONE 6 — ESCALATION POLICY
# ═══════════════════════════════════════════════════════════════════

class TestEscalationPolicy:

    @pytest.fixture
    def policy(self):
        try:
            from intelligence_core.escalation import EscalationPolicy
            return EscalationPolicy(threshold=0.7, max_local_tokens=4096)
        except ImportError:
            pytest.skip("intelligence_core non ancora installato")

    def test_high_confidence_stays_local(self, policy):
        assert policy.should_escalate(confidence=0.85, query_tokens=100) is False

    def test_low_confidence_triggers_escalation(self, policy):
        assert policy.should_escalate(confidence=0.50, query_tokens=100) is True

    def test_long_query_triggers_escalation(self, policy):
        assert policy.should_escalate(confidence=0.80, query_tokens=5000) is True

    def test_threshold_is_configurable(self):
        try:
            from intelligence_core.escalation import EscalationPolicy
            strict  = EscalationPolicy(threshold=0.9)
            lenient = EscalationPolicy(threshold=0.4)
            assert strict.should_escalate(confidence=0.75, query_tokens=100)  is True
            assert lenient.should_escalate(confidence=0.75, query_tokens=100) is False
        except ImportError:
            pytest.skip("intelligence_core non ancora installato")


# ═══════════════════════════════════════════════════════════════════
# FIXTURE CONDIVISE
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_chunk():
    text = (
        "Section: Autenticazione (in api_reference_v2.pdf)\n"
        "Path: API Reference > Autenticazione\n"
        "---\n"
        "Autenticazione via JWT Bearer Token. "
        "Header richiesto: Authorization: Bearer TOKEN. "
        "Per ottenere un token: POST /api/v1/auth/token con client_id e client_secret."
    )
    return {
        "id":       "doc::section::APIRef.Autenticazione",
        "domain":   "doc",
        "type":     "section",
        "text":     text,
        "source":   "api_reference_v2.pdf",
        "language": "pdf",
        "metadata": {
            "page_start":   2,
            "page_end":     3,
            "heading_path": ["API Reference", "Autenticazione"],
            "has_tables":   False,
            "has_code":     False,
            "word_count":   45,
        },
        "checksum": hashlib.sha256(text.encode()).hexdigest(),
    }


@pytest.fixture
def sample_pdf_chunk(sample_chunk):     return sample_chunk
@pytest.fixture
def sample_section_chunk(sample_chunk): return sample_chunk


@pytest.fixture
def chunks_from_same_doc(sample_chunk):
    c2 = sample_chunk.copy()
    c2["id"] = "doc::section::APIRef.RateLimiting"
    c2["metadata"] = {**sample_chunk["metadata"],
                      "heading_path": ["API Reference", "Rate Limiting"]}
    return [sample_chunk, c2]


# ═══════════════════════════════════════════════════════════════════
# SEZIONE 7 — MENTOR INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════

class TestMentorProfileDetector:

    @pytest.fixture
    def detector(self):
        try:
            from MentorIntelligence.profile_detector import detect_profile, Profile
            return detect_profile, Profile
        except ImportError:
            pytest.skip("MentorIntelligence non ancora installato")

    def test_developer_intro_detected(self, detector):
        detect_profile, Profile = detector
        r = detect_profile("Sono uno sviluppatore Python, lavoro su backend da 3 anni")
        assert r.profile == Profile.DEVELOPER

    def test_non_developer_intro_detected(self, detector):
        detect_profile, Profile = detector
        r = detect_profile("Sono il product manager, mi occupo di roadmap e stakeholder")
        assert r.profile == Profile.NON_DEVELOPER

    def test_mixed_intro_detected(self, detector):
        detect_profile, Profile = detector
        r = detect_profile("Sono tech lead, scrivo codice ma gestisco anche il team e i processi")
        assert r.profile in (Profile.MIXED, Profile.DEVELOPER)

    def test_role_hint_overrides_detection(self, detector):
        detect_profile, Profile = detector
        r = detect_profile("Nuovo in azienda", role_hint="non_developer")
        assert r.profile == Profile.NON_DEVELOPER

    def test_result_has_confidence(self, detector):
        detect_profile, Profile = detector
        r = detect_profile("Sviluppo microservizi in Go")
        assert 0.0 <= r.confidence <= 1.0
        assert len(r.signals) > 0


class TestMentorSession:

    @pytest.fixture
    def session_manager(self):
        try:
            from MentorIntelligence import session_manager
            return session_manager
        except ImportError:
            pytest.skip("MentorIntelligence non ancora installato")

    def test_create_session(self, session_manager):
        s = session_manager.create_session("Mario", "developer")
        assert s.user_name == "Mario"
        assert s.profile == "developer"
        assert s.current_step == 0
        assert s.session_id != ""

    def test_save_and_load_session(self, session_manager, tmp_path, monkeypatch):
        monkeypatch.setattr(session_manager, "SESSIONS_DIR", tmp_path)
        s = session_manager.create_session("Giulia", "non_developer")
        session_manager.save_session(s)
        loaded = session_manager.load_session(s.session_id)
        assert loaded.user_name == "Giulia"
        assert loaded.profile == "non_developer"

    def test_mark_step_complete(self, session_manager):
        s = session_manager.create_session("Test", "developer")
        session_manager.mark_step_complete(s, "dev_01")
        assert "dev_01" in s.completed_steps

    def test_record_question(self, session_manager):
        s = session_manager.create_session("Test", "developer")
        session_manager.record_question(
            s, "Come funziona l'auth?", "Usa JWT con validate_token",
            ["code::function::auth.validate_token"],
        )
        assert len(s.questions_asked) == 1
        assert s.questions_asked[0]["query"] == "Come funziona l'auth?"


class TestMentorPathBuilder:

    @pytest.fixture
    def path_builder(self):
        try:
            from MentorIntelligence import path_builder
            return path_builder
        except ImportError:
            pytest.skip("MentorIntelligence non ancora installato")

    def test_developer_path_has_steps(self, path_builder):
        path = path_builder.build_path("developer")
        assert len(path) >= 3
        for step in path:
            assert "id" in step
            assert "title" in step
            assert "sources" in step

    def test_non_developer_path_has_steps(self, path_builder):
        path = path_builder.build_path("non_developer")
        assert len(path) >= 2

    def test_developer_path_includes_code_source(self, path_builder):
        path = path_builder.build_path("developer")
        all_sources = [s for step in path for s in step.get("sources", [])]
        assert "code" in all_sources

    def test_non_developer_path_no_code_source(self, path_builder):
        path = path_builder.build_path("non_developer")
        all_sources = [s for step in path for s in step.get("sources", [])]
        assert "code" not in all_sources

    def test_progress_starts_at_zero(self, path_builder):
        try:
            from MentorIntelligence.session_manager import create_session
            s = create_session("Test", "developer")
            p = path_builder.compute_progress(s)
            assert p["percent"] == 0.0
            assert p["completed"] == 0
        except ImportError:
            pytest.skip("session_manager non disponibile")

    def test_progress_updates_on_completion(self, path_builder):
        try:
            from MentorIntelligence.session_manager import create_session, mark_step_complete
            s = create_session("Test", "developer")
            mark_step_complete(s, "dev_01")
            p = path_builder.compute_progress(s)
            assert p["completed"] == 1
            assert p["percent"] > 0.0
        except ImportError:
            pytest.skip("session_manager non disponibile")


class TestMentorChunkFormat:

    def test_mentor_chunk_valid(self):
        try:
            from intelligence_core.chunk import make_chunk, validate_chunk
        except ImportError:
            pytest.skip("intelligence_core non disponibile")

        chunk = make_chunk(
            domain="mentor", type_="practice",
            locator="git.naming_convention",
            text=(
                "Practice: Naming convention Git (in practices/git_convention.md)\n"
                "Categoria: sviluppo | Priorita: alta\n"
                "---\n"
                "Formato obbligatorio: tipo/ticket-descrizione\n"
                "Esempi: feat/IS-42-add-pdf-parser, fix/IS-99-chunk-id.\n"
                "Non usare: master, develop, nomi personali, date."
            ),
            source="practices/git_convention.md",
            language="markdown",
            metadata={"category": "sviluppo", "priority": "alta", "audience": ["developer"]},
        )
        errors = validate_chunk(chunk)
        assert not errors, f"Chunk mentor non valido: {errors}"

    def test_mentor_chunk_id_format(self):
        try:
            from intelligence_core.chunk import make_chunk_id
        except ImportError:
            pytest.skip("intelligence_core non disponibile")

        chunk_id = make_chunk_id("mentor", "practice", "git.naming_convention")
        assert chunk_id == "mentor::practice::git.naming_convention"
        parts = chunk_id.split("::")
        assert len(parts) == 3

    def test_onboarding_step_chunk_valid(self):
        try:
            from intelligence_core.chunk import make_chunk, validate_chunk
        except ImportError:
            pytest.skip("intelligence_core non disponibile")

        chunk = make_chunk(
            domain="mentor", type_="onboarding_step",
            locator="developer.step_03_auth",
            text=(
                "OnboardingStep: Capire il sistema di autenticazione (passo 3)\n"
                "Profilo: developer\n"
                "---\n"
                "In questo passo capisci come funziona il JWT auth flow.\n"
                "Cosa fare: query CodeIntelligence con 'autenticazione JWT'.\n"
                "Checkpoint: sai chi chiama validate_token e da dove."
            ),
            source="path_templates.json",
            language="json",
            metadata={"step_id": "dev_03", "profile": "developer",
                      "sources": ["code", "doc"], "position": 3},
        )
        errors = validate_chunk(chunk)
        assert not errors, f"Chunk onboarding_step non valido: {errors}"
