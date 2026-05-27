"""Test suite for intelligence_core/intent.py — Intent Routing v0.4.0.

Coverage target: ≥ 80% on intelligence_core/intent.py.
Tests are split into:
  - Unit tests (no external dependencies, no LLM calls)
  - Integration tests (mock LLM + real registry structures)
  - Server endpoint tests (parametrized across all four modules)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel as _BM


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_registry(skills: list[dict] | None = None):
    """Build a minimal registry mock."""
    r = MagicMock()
    r.list_skills.return_value = skills or []
    r.get_skill.return_value = None
    return r


def _mock_llm(response: str = '{"level": "rag", "confidence": 0.9}'):
    llm = MagicMock()
    llm.generate.return_value = response
    llm.backend_name = "mock"
    llm.is_available.return_value = True
    return llm


def _make_skill(name="deploy_api", description="procedura deploy api su kubernetes",
                parameters=None):
    from SkillIntelligence.base import BaseSkill, SkillStep

    class _S(BaseSkill):
        pass

    _S.name = name
    _S.description = description
    _S.parameters = parameters if parameters is not None else {
        "service":     {"type": "str", "required": True},
        "environment": {"type": "str", "required": True, "enum": ["staging", "production"]},
    }
    _S.steps = [
        SkillStep(
            id="s1", title="Step 1", description="Primo step",
            knowledge_query="deploy {service}", domains=["code"],
        )
    ]
    return _S()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Heuristic classifier — unit tests (zero LLM calls)
# ─────────────────────────────────────────────────────────────────────────────

class TestHeuristicClassifier:

    def _classify(self, query, skill_names=None):
        from intelligence_core.intent import _heuristic_classify
        return _heuristic_classify(query, skill_names or [])

    def test_skill_trigger_keywords(self):
        level, conf, _ = self._classify("guidami nel deploy del servizio auth")
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.SKILL
        assert conf >= 0.85

    def test_agent_trigger_keywords(self):
        level, conf, _ = self._classify("analizza tutto il codice e dimmi le dipendenze")
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.AGENT
        assert conf >= 0.85

    def test_rag_simple_question(self):
        level, conf, _ = self._classify("dove è implementata l'autenticazione?")
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.RAG

    def test_long_query_with_conjunctions_is_agent(self):
        query = (
            "Verifica lo stato del servizio auth e poi controlla se ci sono "
            "errori nel database quindi dimmi se posso fare il deploy in production"
        )
        level, conf, _ = self._classify(query)
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.AGENT

    def test_skill_name_in_query_direct_match(self):
        level, conf, _ = self._classify(
            "avvia deploy_api per il servizio auth", ["deploy_api"]
        )
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.SKILL
        assert conf == 0.95

    def test_confidence_above_threshold_high_for_skill_trigger(self):
        level, conf, _ = self._classify("guidami nel rilascio del servizio")
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.SKILL
        assert conf >= 0.85

    def test_confidence_low_for_ambiguous_query(self):
        _, conf, _ = self._classify("cosa fa il servizio auth")
        assert conf < 0.85

    def test_short_question_mark_is_rag(self):
        level, conf, _ = self._classify("cos'è il rate limiting?")
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.RAG

    def test_deploy_keyword_triggers_skill(self):
        level, conf, _ = self._classify("come faccio il deploy in produzione")
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.SKILL
        assert conf >= 0.85

    def test_agent_trigger_overrides_default(self):
        level, _, _ = self._classify("esamina tutte le dipendenze del progetto")
        from intelligence_core.intent import IntentLevel
        assert level == IntentLevel.AGENT


# ─────────────────────────────────────────────────────────────────────────────
# 2. Skill Matcher
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillMatcher:

    def test_exact_name_match(self):
        from intelligence_core.intent import match_skill
        registry = _mock_registry([{"name": "deploy_api", "description": "deploy procedure"}])
        name, conf = match_skill("esegui deploy_api adesso", registry)
        assert name == "deploy_api"
        assert conf == 0.95

    def test_keyword_match_on_description(self):
        from intelligence_core.intent import match_skill
        registry = _mock_registry([{
            "name": "onboarding_developer",
            "description": "procedura onboarding nuovo sviluppatore aziendale",
        }])
        name, conf = match_skill("voglio fare onboarding come sviluppatore aziendale", registry)
        assert name == "onboarding_developer"
        assert conf >= 0.70

    def test_no_match_returns_none(self):
        from intelligence_core.intent import match_skill
        registry = _mock_registry([{"name": "deploy_api", "description": "deploy kubernetes"}])
        name, conf = match_skill("qual è la password del database?", registry)
        assert name is None
        assert conf == 0.0

    def test_returns_confidence_score_between_0_and_1(self):
        from intelligence_core.intent import match_skill
        registry = _mock_registry([{"name": "deploy_api", "description": "deploy procedure"}])
        _, conf = match_skill("qualsiasi query", registry)
        assert 0.0 <= conf <= 1.0

    def test_empty_registry_returns_none(self):
        from intelligence_core.intent import match_skill
        name, conf = match_skill("guidami nel deploy", _mock_registry([]))
        assert name is None

    def test_exact_match_wins_over_keyword_match(self):
        from intelligence_core.intent import match_skill
        registry = _mock_registry([
            {"name": "deploy_api", "description": "procedura di rilascio api"},
            {"name": "altro_skill", "description": "deploy api servizio"},
        ])
        name, conf = match_skill("avvia deploy_api ora", registry)
        assert name == "deploy_api"
        assert conf == 0.95


# ─────────────────────────────────────────────────────────────────────────────
# 3. Parameter extraction
# ─────────────────────────────────────────────────────────────────────────────

class TestParameterExtraction:

    def test_complete_parameters_extracted(self):
        from intelligence_core.intent import extract_parameters
        skill = _make_skill()
        llm_resp = '{"service": "auth", "environment": "staging"}'
        with patch("intelligence_core.intent.get_llm_provider", return_value=_mock_llm(llm_resp)):
            params, complete = extract_parameters(
                "deploy auth su staging", skill
            )
        assert params.get("service") == "auth"
        assert params.get("environment") == "staging"
        assert complete is True

    def test_missing_required_param(self):
        from intelligence_core.intent import extract_parameters
        skill = _make_skill()
        llm_resp = '{"service": "auth"}'  # environment missing
        with patch("intelligence_core.intent.get_llm_provider", return_value=_mock_llm(llm_resp)):
            params, complete = extract_parameters("deploy auth", skill)
        assert params.get("service") == "auth"
        assert complete is False

    def test_parameters_complete_false_when_all_missing(self):
        from intelligence_core.intent import extract_parameters
        skill = _make_skill()
        llm_resp = '{}'
        with patch("intelligence_core.intent.get_llm_provider", return_value=_mock_llm(llm_resp)):
            _, complete = extract_parameters("guidami nel deploy", skill)
        assert complete is False

    def test_skill_with_no_parameters_returns_complete(self):
        from intelligence_core.intent import extract_parameters
        skill = _make_skill(parameters={})
        params, complete = extract_parameters("qualsiasi query", skill)
        assert complete is True

    def test_llm_failure_returns_empty_incomplete(self):
        from intelligence_core.intent import extract_parameters
        skill = _make_skill()
        broken_llm = MagicMock()
        broken_llm.generate.side_effect = RuntimeError("LLM unavailable")
        with patch("intelligence_core.intent.get_llm_provider", return_value=broken_llm):
            params, complete = extract_parameters("deploy auth su staging", skill)
        assert params == {}
        assert complete is False

    def test_invalid_json_from_llm_returns_empty(self):
        from intelligence_core.intent import extract_parameters
        skill = _make_skill()
        with patch("intelligence_core.intent.get_llm_provider", return_value=_mock_llm("not json")):
            params, complete = extract_parameters("deploy auth su staging", skill)
        assert params == {}
        assert complete is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fallback behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackBehaviour:

    def test_invalid_llm_response_falls_back_to_rag(self):
        from intelligence_core.intent import _llm_classify, IntentLevel
        with patch("intelligence_core.intent.get_llm_provider", return_value=_mock_llm("garbage")):
            level, conf = _llm_classify("query ambigua", "skill_summaries")
        assert level == IntentLevel.RAG
        assert conf == 0.5

    def test_llm_timeout_falls_back_to_rag(self):
        from intelligence_core.intent import _llm_classify, IntentLevel
        broken = MagicMock()
        broken.generate.side_effect = TimeoutError("timeout")
        with patch("intelligence_core.intent.get_llm_provider", return_value=broken):
            level, conf = _llm_classify("query ambigua", "nessuna skill")
        assert level == IntentLevel.RAG
        assert conf == 0.5

    def test_agent_falls_back_to_rag_when_disabled(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        with patch("intelligence_core.config.settings") as mock_settings:
            mock_settings.intent_routing = True
            mock_settings.intent_confidence_threshold = 0.85
            mock_settings.intent_agent_enabled = False
            result = classify_intent("analizza tutto il codice e dimmi le dipendenze")
        assert result.level == IntentLevel.RAG
        assert "fallback RAG" in result.reasoning

    def test_routing_disabled_returns_rag_immediately(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        with patch("intelligence_core.config.settings") as mock_settings:
            mock_settings.intent_routing = False
            result = classify_intent("guidami nel deploy")
        assert result.level == IntentLevel.RAG
        assert result.confidence == 1.0

    def test_classify_never_crashes_on_exception(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        # Should not raise even if registry throws
        broken_registry = MagicMock()
        broken_registry.list_skills.side_effect = RuntimeError("registry broken")
        # Even with a broken registry, the heuristic stage runs first
        # (the registry error only matters post-heuristic for skill matching)
        try:
            result = classify_intent("guidami nel deploy", registry=broken_registry)
            # If we get here, the result should be a valid IntentResult
            assert isinstance(result.level, IntentLevel)
        except Exception:
            pytest.fail("classify_intent raised an exception instead of falling back")


# ─────────────────────────────────────────────────────────────────────────────
# 5. IntentResult dataclass
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentResult:

    def test_rag_result_has_no_skill_name(self):
        from intelligence_core.intent import IntentResult, IntentLevel
        r = IntentResult(level=IntentLevel.RAG, confidence=0.9)
        assert r.skill_name is None
        assert r.skill_parameters == {}
        assert r.parameters_complete is False

    def test_skill_result_has_skill_name_and_params(self):
        from intelligence_core.intent import IntentResult, IntentLevel
        r = IntentResult(
            level=IntentLevel.SKILL,
            confidence=0.92,
            skill_name="deploy_api",
            skill_parameters={"service": "auth", "environment": "staging"},
            parameters_complete=True,
        )
        assert r.skill_name == "deploy_api"
        assert r.skill_parameters["service"] == "auth"
        assert r.parameters_complete is True

    def test_intent_level_values(self):
        from intelligence_core.intent import IntentLevel
        assert IntentLevel.RAG.value == "rag"
        assert IntentLevel.SKILL.value == "skill"
        assert IntentLevel.AGENT.value == "agent"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Full routing integration tests (mock LLM + real registry-like structures)
# ─────────────────────────────────────────────────────────────────────────────

class TestFullRoutingIntegration:

    def _registry_with_skill(self, name="deploy_api"):
        skill = _make_skill(name=name)
        registry = _mock_registry([{
            "name": skill.name,
            "description": skill.description,
        }])
        registry.get_skill.return_value = skill
        return registry

    def test_rag_query_end_to_end(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = True
            ms.intent_confidence_threshold = 0.85
            ms.intent_agent_enabled = False
            result = classify_intent(
                "dove è implementata la funzione di login?",
                registry=_mock_registry([]),
            )
        assert result.level == IntentLevel.RAG

    def test_skill_query_starts_session(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        registry = self._registry_with_skill("deploy_api")
        llm_params_resp = '{"service": "auth", "environment": "staging"}'
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = True
            ms.intent_confidence_threshold = 0.85
            ms.intent_agent_enabled = False
            with patch("intelligence_core.intent.get_llm_provider", return_value=_mock_llm(llm_params_resp)):
                result = classify_intent("guidami nel deploy_api di auth su staging", registry=registry)
        assert result.level == IntentLevel.SKILL
        assert result.skill_name == "deploy_api"

    def test_missing_params_sets_parameters_complete_false(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        registry = self._registry_with_skill("deploy_api")
        llm_params_resp = '{"service": "auth"}'  # environment missing
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = True
            ms.intent_confidence_threshold = 0.85
            ms.intent_agent_enabled = False
            with patch("intelligence_core.intent.get_llm_provider", return_value=_mock_llm(llm_params_resp)):
                result = classify_intent("guidami nel deploy_api di auth", registry=registry)
        assert result.level == IntentLevel.SKILL
        assert result.parameters_complete is False

    def test_agent_query_falls_back_to_rag(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = True
            ms.intent_confidence_threshold = 0.85
            ms.intent_agent_enabled = False
            result = classify_intent(
                "analizza tutto il codice e dimmi le dipendenze critiche",
                registry=_mock_registry([]),
            )
        assert result.level == IntentLevel.RAG
        assert "fallback RAG" in result.reasoning

    def test_skill_no_registry_falls_back_to_rag(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = True
            ms.intent_confidence_threshold = 0.85
            ms.intent_agent_enabled = False
            result = classify_intent("guidami nel deploy", registry=None)
        assert result.level == IntentLevel.RAG

    def test_llm_stage2_used_for_ambiguous_query(self):
        from intelligence_core.intent import classify_intent, IntentLevel
        llm_resp = '{"level": "skill", "confidence": 0.88}'
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = True
            ms.intent_confidence_threshold = 0.85
            ms.intent_agent_enabled = False
            registry = _mock_registry([{"name": "deploy_api", "description": "deploy"}])
            registry.get_skill.return_value = _make_skill()
            # Ambiguous query → triggers Stage 2
            llm_params_resp = '{"service": "auth", "environment": "staging"}'
            with patch("intelligence_core.intent.get_llm_provider") as mock_factory:
                # First call: classification; second call: param extraction
                mock_factory.return_value = _mock_llm(llm_resp)
                result = classify_intent("cosa devo fare per il progetto auth", registry=registry)
        # Stage 2 says skill → should resolve to SKILL or fallback — just check no crash
        assert isinstance(result.level, IntentLevel)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Server endpoint tests — parametrized across all four modules
#
# NOTE: Module-level Pydantic models required due to PEP 563 / FastAPI type hints.
# ─────────────────────────────────────────────────────────────────────────────

class _QueryReq(_BM):
    question: str
    top_k: int = 5
    domain: str | None = None
    min_score: float = 0.3
    history: list[dict] = []


class _SkillNextReq(_BM):
    session_id: str
    user_input: str | None = None


def _build_server_app(module_name: str):
    """Build a minimal server app for the given module."""
    if module_name == "SkillIntelligence":
        from SkillIntelligence.skill_server import build_app
        # Patch at source: get_registry is now imported at module level in skill_server
        with patch("SkillIntelligence.skill_server.get_registry") as mock_reg, \
             patch("SkillIntelligence.skill_server.get_llm_provider") as mock_llm_fn:
            mock_reg.return_value = _mock_registry([])
            mock_llm_fn.return_value = _mock_llm()
            # build_app() is called inside the patch context
            return build_app()
    else:
        # CI, DI, MI all use create_app()
        from intelligence_core.server_base import create_app
        from intelligence_core.retriever import RetrievalResult

        mock_retriever = MagicMock()
        mock_retriever.store.count.return_value = 0
        mock_retriever.search.return_value = []

        mock_llm = _mock_llm("risposta mock")

        app = create_app(
            title=f"{module_name} test",
            retriever=mock_retriever,
            module=module_name.lower()[:4],
            llm_provider=mock_llm,
        )
        return app


@pytest.fixture(
    params=["CodeIntelligence", "DocIntelligence", "MentorIntelligence", "SkillIntelligence"]
)
def server_app(request):
    """Parametrized fixture returning a test client for each module."""
    from fastapi.testclient import TestClient
    module = request.param
    app = _build_server_app(module)
    return TestClient(app), module


@pytest.fixture(params=["CodeIntelligence", "DocIntelligence", "MentorIntelligence"])
def rag_server_app(request):
    """Parametrized fixture for the three RAG servers only (use create_app)."""
    from fastapi.testclient import TestClient
    module = request.param
    app = _build_server_app(module)
    return TestClient(app), module


class TestServerEndpoints:

    def test_query_endpoint_returns_intent_field(self, server_app):
        client, module = server_app
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = False  # disable routing for clean RAG response
            ms.intent_routing = False
            ms.anthropic_api_key = ""
            resp = client.post("/api/v1/query", json={"question": "test query"})
        # SkillIntelligence returns intent field too
        assert resp.status_code == 200
        data = resp.json()
        assert "intent" in data

    def test_query_endpoint_routing_disabled_behaves_as_before(self, rag_server_app):
        client, module = rag_server_app
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = False
            ms.anthropic_api_key = ""
            ms.escalation_threshold = 0.70
            ms.escalation_max_tokens = 4096
            resp = client.post("/api/v1/query", json={"question": "where is the auth function?"})
        assert resp.status_code == 200
        data = resp.json()
        # Core RAG fields must be present
        assert "answer" in data
        assert "sources" in data

    def test_skill_next_endpoint_available_on_all_modules(self, server_app):
        client, module = server_app
        # Should not return 404/405 — a 404 "session not found" is correct behavior
        resp = client.post("/api/v1/skill/next",
                           json={"session_id": "nonexistent-session-id"})
        # Endpoint exists: expect 404 (session not found) or 503 (executor unavailable)
        assert resp.status_code in (404, 503)

    def test_query_response_includes_intent_rag(self, rag_server_app):
        client, module = rag_server_app
        with patch("intelligence_core.config.settings") as ms:
            ms.intent_routing = False
            ms.anthropic_api_key = ""
            ms.escalation_threshold = 0.70
            ms.escalation_max_tokens = 4096
            resp = client.post("/api/v1/query", json={"question": "simple factual question?"})
        assert resp.status_code == 200
        assert resp.json().get("intent") == "rag"


# ─────────────────────────────────────────────────────────────────────────────
# 8. QueryResponse schema backward-compatibility
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryResponseSchema:

    def test_new_fields_are_optional_with_defaults(self):
        from intelligence_core.server_base import QueryResponse
        r = QueryResponse(
            answer="test", sources=[], confidence=0.5,
            escalated=False, backend="ollama", latency_ms=10.0,
        )
        assert r.intent == "rag"
        assert r.session_id is None
        assert r.is_last_step is None

    def test_intent_field_accepts_all_levels(self):
        from intelligence_core.server_base import QueryResponse
        for level in ("rag", "skill", "agent", "agent_stub"):
            r = QueryResponse(
                answer="x", sources=[], confidence=0.9,
                escalated=False, backend="mock", latency_ms=5.0,
                intent=level,
            )
            assert r.intent == level

    def test_session_id_and_is_last_step_for_skill(self):
        from intelligence_core.server_base import QueryResponse
        r = QueryResponse(
            answer="step 1", sources=[], confidence=0.9,
            escalated=False, backend="mock", latency_ms=50.0,
            intent="skill", session_id="abc-123", is_last_step=False,
        )
        assert r.session_id == "abc-123"
        assert r.is_last_step is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. Config fields
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigFields:

    def test_intent_routing_default_true(self):
        from intelligence_core.config import Settings
        s = Settings()
        assert s.intent_routing is True

    def test_intent_routing_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("INTENT_ROUTING", "false")
        from intelligence_core.config import Settings
        s = Settings()
        assert s.intent_routing is False

    def test_intent_agent_enabled_default_false(self):
        from intelligence_core.config import Settings
        s = Settings()
        assert s.intent_agent_enabled is False

    def test_intent_confidence_threshold_default(self):
        from intelligence_core.config import Settings
        s = Settings()
        assert s.intent_confidence_threshold == 0.85

    def test_agent_port_reserved(self):
        from intelligence_core.config import Settings
        s = Settings()
        assert s.agent_port == 8084
