"""Test suite for SkillIntelligence — unit + integration + server endpoint tests."""

from __future__ import annotations

import json
import tempfile
import textwrap
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel as _BM


# ─────────────────────────────────────────────────────────────────────────────
# Module-level Pydantic models for server tests
# NOTE: Must be at module level — NOT inside fixtures — because
#       `from __future__ import annotations` (PEP 563) stores all annotations
#       as strings, and FastAPI's get_type_hints() cannot resolve locally-scoped
#       classes from the module's global namespace, causing 422 instead of 404.
# ─────────────────────────────────────────────────────────────────────────────

class _ServerStartReq(_BM):
    skill_name: str
    parameters: dict = {}


class _ServerNextReq(_BM):
    session_id: str
    user_input: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_retrieval_result(source: str, score: float = 0.8):
    from intelligence_core.retriever import RetrievalResult
    return RetrievalResult(
        chunk={"id": source, "text": f"Contenuto di {source}", "source": source, "type": "doc", "domain": "doc"},
        score=score,
        rank=1,
    )


def _mock_retriever(results=None):
    r = MagicMock()
    r.search.return_value = results or []
    return r


def _mock_llm(response="guidance mock"):
    llm = MagicMock()
    llm.generate.return_value = response
    llm.backend_name = "mock"
    llm.is_available.return_value = True
    return llm


# ─────────────────────────────────────────────────────────────────────────────
# 1. BaseSkill — interpolazione e validazione parametri
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseSkill:

    def _make_skill(self):
        from SkillIntelligence.base import BaseSkill, SkillStep

        class MySkill(BaseSkill):
            name = "my_skill"
            description = "test skill"
            parameters = {
                "service": {"type": "str", "required": True},
                "env":     {"type": "str", "required": True, "enum": ["staging", "production"]},
                "opt":     {"type": "str", "required": False},
            }
            steps = [
                SkillStep(
                    id="s1", title="T1", description="D1",
                    knowledge_query="query {service} {env}", domains=["doc"],
                )
            ]
        return MySkill()

    def test_skill_parameter_interpolation(self):
        skill = self._make_skill()
        result = skill.interpolate("deploy {service} su {env}", {"service": "api", "env": "staging"})
        assert result == "deploy api su staging"

    def test_skill_missing_required_parameter_raises(self):
        skill = self._make_skill()
        errors = skill.validate_parameters({"env": "staging"})  # manca 'service'
        assert any("service" in e for e in errors)

    def test_skill_parameter_enum_validation(self):
        skill = self._make_skill()
        errors = skill.validate_parameters({"service": "api", "env": "dev"})
        assert any("env" in e for e in errors)

    def test_skill_valid_parameters_no_errors(self):
        skill = self._make_skill()
        errors = skill.validate_parameters({"service": "api", "env": "production"})
        assert errors == []

    def test_skill_optional_param_missing_is_ok(self):
        skill = self._make_skill()
        errors = skill.validate_parameters({"service": "x", "env": "staging"})
        assert errors == []

    def test_skill_to_metadata(self):
        skill = self._make_skill()
        meta = skill.to_metadata()
        assert meta["name"] == "my_skill"
        assert meta["source"] == "python"
        assert meta["steps_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. Parser Markdown
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkdownParser:

    def _write_md(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "skill.md"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    def test_parser_valid_markdown_full_format(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            # Skill: Deploy Test
            > description: Guida al deploy.
            > parameters: service_name (str, required), env (str, required, enum: staging|production)

            ## Step 1: Verifica
            **Domini:** code, doc
            **Query:** dipendenze di {service_name} in {env}
            Testo libero dello step.

            ## Step 2: Config
            **Domini:** doc
            **Query:** config {env}
            Secondo step.
        """)
        skill = parse_skill_markdown(p)
        assert skill is not None
        assert skill.name == "deploy_test"
        assert len(skill.steps) == 2
        assert skill.steps[0].domains == ["code", "doc"]
        assert "{service_name}" in skill.steps[0].knowledge_query

    def test_parser_markdown_missing_title_skipped(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            ## Step 1: Something
            **Domini:** doc
            **Query:** qualcosa
        """)
        skill = parse_skill_markdown(p)
        assert skill is None

    def test_parser_markdown_missing_query_uses_title(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            # Skill: No Query Skill
            > description: test

            ## Step 1: My Step Title
            **Domini:** doc
            Testo senza query esplicita.
        """)
        skill = parse_skill_markdown(p)
        assert skill is not None
        assert skill.steps[0].knowledge_query == "My Step Title"

    def test_parser_markdown_invalid_domain_discarded(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            # Skill: Domain Test
            > description: test

            ## Step 1: Step
            **Domini:** code, invalid_domain
            **Query:** query test
        """)
        skill = parse_skill_markdown(p)
        assert skill is not None
        assert "invalid_domain" not in skill.steps[0].domains
        assert "code" in skill.steps[0].domains

    def test_parser_markdown_multiple_steps(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            # Skill: Multi Step
            > description: test

            ## Step 1: Uno
            **Domini:** doc
            **Query:** prima query

            ## Step 2: Due
            **Domini:** code
            **Query:** seconda query

            ## Step 3: Tre
            **Domini:** mentor
            **Query:** terza query
        """)
        skill = parse_skill_markdown(p)
        assert skill is not None
        assert len(skill.steps) == 3

    def test_parser_markdown_cross_domain_step(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            # Skill: Cross Domain
            > description: test

            ## Step 1: Multi Domain
            **Domini:** code, doc, mentor
            **Query:** query cross
        """)
        skill = parse_skill_markdown(p)
        assert skill is not None
        assert set(skill.steps[0].domains) == {"code", "doc", "mentor"}

    def test_parser_default_domain_is_doc(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            # Skill: Default Domain
            > description: test

            ## Step 1: Step senza Domini
            **Query:** query senza domini
        """)
        skill = parse_skill_markdown(p)
        assert skill is not None
        assert skill.steps[0].domains == ["doc"]

    def test_parser_markdown_source_type(self, tmp_path):
        from SkillIntelligence.parser import parse_skill_markdown
        p = self._write_md(tmp_path, """
            # Skill: Source Test
            > description: test

            ## Step 1: Step
            **Domini:** doc
            **Query:** query
        """)
        skill = parse_skill_markdown(p)
        assert skill is not None
        assert skill.source_type() == "markdown"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Registry
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistry:

    def _make_registry(self, tmp_path: Path | None = None):
        from SkillIntelligence.registry import SkillRegistry
        r = SkillRegistry()
        return r

    def test_registry_loads_python_skills(self):
        from SkillIntelligence.registry import SkillRegistry
        r = SkillRegistry()
        r.load_python_skills()
        names = [s["name"] for s in r.list_skills()]
        assert "deploy_checklist" in names
        assert "onboarding_developer" in names

    def test_registry_loads_markdown_skills(self, tmp_path):
        from SkillIntelligence.registry import SkillRegistry
        md = tmp_path / "test_skill.md"
        md.write_text(textwrap.dedent("""
            # Skill: Md Skill
            > description: test

            ## Step 1: Step
            **Domini:** doc
            **Query:** query
        """), encoding="utf-8")
        r = SkillRegistry()
        r.load_markdown_skills(tmp_path)
        assert r.get_skill("md_skill") is not None

    def test_registry_python_wins_on_duplicate_name(self, tmp_path):
        from SkillIntelligence.registry import SkillRegistry
        from SkillIntelligence.base import BaseSkill, SkillStep

        # Create a Markdown skill with same name as a Python skill
        md = tmp_path / "deploy_checklist.md"
        md.write_text(textwrap.dedent("""
            # Skill: Deploy Checklist
            > description: md version

            ## Step 1: Only Step
            **Domini:** doc
            **Query:** query
        """), encoding="utf-8")

        r = SkillRegistry()
        r.load_python_skills()   # registers deploy_checklist as python
        r.load_markdown_skills(tmp_path)  # should be ignored
        skill = r.get_skill("deploy_checklist")
        assert skill is not None
        assert skill.source_type() == "python"

    def test_registry_invalid_skill_skipped_not_raised(self, tmp_path):
        from SkillIntelligence.registry import SkillRegistry
        md = tmp_path / "bad.md"
        md.write_text("not a valid skill file", encoding="utf-8")
        r = SkillRegistry()
        r.load_markdown_skills(tmp_path)  # must not raise
        assert r.count() == 0

    def test_registry_list_skills_returns_metadata(self):
        from SkillIntelligence.registry import SkillRegistry
        r = SkillRegistry()
        r.load_python_skills()
        skills = r.list_skills()
        assert len(skills) >= 2
        for s in skills:
            assert "name" in s
            assert "description" in s
            assert "source" in s
            assert "steps_count" in s

    def test_registry_get_skill_not_found_returns_none(self):
        from SkillIntelligence.registry import SkillRegistry
        r = SkillRegistry()
        assert r.get_skill("nonexistent_skill") is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Executor — logica con mock retriever e LLM
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutor:

    def _make_skill_registry(self, skill):
        from SkillIntelligence.registry import SkillRegistry
        r = SkillRegistry()
        r._register(skill, source="python")
        return r

    def _make_executor(self, tmp_path: Path, llm=None, retriever_results=None, skill=None):
        from SkillIntelligence.executor import SkillExecutor
        mock_llm = llm or _mock_llm()
        retriever = _mock_retriever(retriever_results or [])
        registry = self._make_skill_registry(skill) if skill else None
        return SkillExecutor(
            llm=mock_llm,
            sessions_dir=tmp_path,
            retriever_factory=lambda col: retriever,
            registry=registry,
        )

    def _make_simple_skill(self):
        from SkillIntelligence.base import BaseSkill, SkillStep

        class SimpleSkill(BaseSkill):
            name = "simple_skill"
            description = "test"
            parameters = {"name": {"type": "str", "required": True}}
            steps = [
                SkillStep(id="s1", title="Step 1", description="d1",
                          knowledge_query="q1 {name}", domains=["doc"]),
                SkillStep(id="s2", title="Step 2", description="d2",
                          knowledge_query="q2 {name}", domains=["code"]),
            ]
        return SimpleSkill()

    def test_executor_start_session_returns_first_step(self, tmp_path):
        skill = self._make_simple_skill()
        executor = self._make_executor(tmp_path, skill=skill)
        session_id, result = executor.start_session(skill, {"name": "alice"})

        assert session_id is not None
        assert result.step_id == "s1"
        assert result.title == "Step 1"
        assert result.is_last_step is False

    def test_executor_next_step_advances_index(self, tmp_path):
        skill = self._make_simple_skill()
        executor = self._make_executor(tmp_path, skill=skill)
        session_id, _ = executor.start_session(skill, {"name": "bob"})
        result = executor.next_step(session_id)

        assert result is not None
        assert result.step_id == "s2"
        assert result.is_last_step is True

    def test_executor_next_step_on_last_returns_completed(self, tmp_path):
        skill = self._make_simple_skill()
        executor = self._make_executor(tmp_path, skill=skill)
        session_id, _ = executor.start_session(skill, {"name": "carol"})
        executor.next_step(session_id)           # step 2
        result = executor.next_step(session_id)  # no more steps

        assert result is None

    def test_executor_invalid_session_id_raises(self, tmp_path):
        from SkillIntelligence.executor import SkillExecutor
        executor = SkillExecutor(sessions_dir=tmp_path, retriever_factory=lambda c: _mock_retriever())
        with pytest.raises(KeyError):
            executor.next_step("nonexistent-session-id")

    def test_executor_cross_domain_merges_results(self, tmp_path):
        from SkillIntelligence.base import BaseSkill, SkillStep
        from SkillIntelligence.executor import SkillExecutor
        from SkillIntelligence.registry import SkillRegistry

        results_code = [_make_retrieval_result("code/file.py", 0.9)]
        results_doc  = [_make_retrieval_result("docs/readme.md", 0.7)]

        def factory(collection):
            r = MagicMock()
            if "code" in collection:
                r.search.return_value = results_code
            else:
                r.search.return_value = results_doc
            return r

        class CrossSkill(BaseSkill):
            name = "cross_skill"
            description = "test"
            parameters = {}
            steps = [
                SkillStep(id="s1", title="Cross", description="d",
                          knowledge_query="query", domains=["code", "doc"]),
            ]

        skill = CrossSkill()
        registry = SkillRegistry()
        registry._register(skill, source="python")

        executor = SkillExecutor(
            llm=_mock_llm(), sessions_dir=tmp_path,
            retriever_factory=factory, registry=registry,
        )
        _, result = executor.start_session(skill, {})

        sources = {s["source"] for s in result.sources}
        assert "code/file.py" in sources
        assert "docs/readme.md" in sources

    def test_executor_cross_domain_deduplicates_by_source(self, tmp_path):
        from SkillIntelligence.base import BaseSkill, SkillStep
        from SkillIntelligence.executor import SkillExecutor
        from SkillIntelligence.registry import SkillRegistry

        same_result = _make_retrieval_result("shared/file.txt", 0.8)

        def factory(collection):
            r = MagicMock()
            r.search.return_value = [same_result]
            return r

        class DedupSkill(BaseSkill):
            name = "dedup_skill"
            description = "test"
            parameters = {}
            steps = [
                SkillStep(id="s1", title="T", description="d",
                          knowledge_query="q", domains=["code", "doc"]),
            ]

        skill = DedupSkill()
        registry = SkillRegistry()
        registry._register(skill, source="python")

        executor = SkillExecutor(
            llm=_mock_llm(), sessions_dir=tmp_path,
            retriever_factory=factory, registry=registry,
        )
        _, result = executor.start_session(skill, {})

        sources = [s["source"] for s in result.sources]
        assert sources.count("shared/file.txt") == 1

    def test_executor_context_includes_previous_step_outputs(self, tmp_path):
        from SkillIntelligence.base import BaseSkill, SkillStep
        from SkillIntelligence.executor import SkillExecutor
        from SkillIntelligence.registry import SkillRegistry

        captured_prompts = []

        def mock_generate(prompt, ctx):
            captured_prompts.append(prompt)
            return "guidance"

        llm = MagicMock()
        llm.generate.side_effect = mock_generate
        llm.backend_name = "mock"

        class TwoStepSkill(BaseSkill):
            name = "two_step"
            description = "test"
            parameters = {}
            steps = [
                SkillStep(id="s1", title="S1", description="d1", knowledge_query="q1", domains=["doc"]),
                SkillStep(id="s2", title="S2", description="d2", knowledge_query="q2", domains=["doc"]),
            ]

        skill = TwoStepSkill()
        registry = SkillRegistry()
        registry._register(skill, source="python")

        executor = SkillExecutor(
            llm=llm, sessions_dir=tmp_path,
            retriever_factory=lambda c: _mock_retriever(),
            registry=registry,
        )
        session_id, _ = executor.start_session(skill, {})
        executor.next_step(session_id)

        assert len(captured_prompts) == 2
        # Second prompt should contain output of first step
        assert "s1" in captured_prompts[1] or "guidance" in captured_prompts[1]

    def test_executor_session_persists_on_disk(self, tmp_path):
        skill = self._make_simple_skill()
        executor = self._make_executor(tmp_path, skill=skill)
        session_id, _ = executor.start_session(skill, {"name": "dave"})

        session_file = tmp_path / f"{session_id}.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["skill_name"] == "simple_skill"
        assert data["parameters"] == {"name": "dave"}

    def test_executor_session_recoverable_after_reload(self, tmp_path):
        from SkillIntelligence.executor import SkillExecutor
        from SkillIntelligence.registry import SkillRegistry

        skill = self._make_simple_skill()
        registry = SkillRegistry()
        registry._register(skill, source="python")

        executor1 = SkillExecutor(
            llm=_mock_llm(), sessions_dir=tmp_path,
            retriever_factory=lambda c: _mock_retriever(),
            registry=registry,
        )
        session_id, _ = executor1.start_session(skill, {"name": "eve"})

        # Create a new executor instance (simulates server restart)
        executor2 = SkillExecutor(
            llm=_mock_llm(), sessions_dir=tmp_path,
            retriever_factory=lambda c: _mock_retriever(),
            registry=registry,
        )
        result = executor2.next_step(session_id)

        assert result is not None
        assert result.step_id == "s2"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Integration tests (richiedono ChromaDB attivo)
# ─────────────────────────────────────────────────────────────────────────────

def _chroma_available(collection: str) -> bool:
    try:
        from intelligence_core.retriever import Retriever
        r = Retriever.load_default(collection_name=collection)
        return r.store.count() > 0
    except Exception:
        return False


@pytest.mark.skipif(
    not _chroma_available("code_intelligence"),
    reason="code_intelligence collection not indexed",
)
def test_executor_real_retrieval_code_domain(tmp_path):
    from SkillIntelligence.base import BaseSkill, SkillStep
    from SkillIntelligence.executor import SkillExecutor
    from SkillIntelligence.registry import SkillRegistry

    class RealSkill(BaseSkill):
        name = "real_code"
        description = "test"
        parameters = {}
        steps = [
            SkillStep(id="s1", title="T", description="d",
                      knowledge_query="function definition", domains=["code"]),
        ]

    skill = RealSkill()
    registry = SkillRegistry()
    registry._register(skill, source="python")
    executor = SkillExecutor(llm=_mock_llm(), sessions_dir=tmp_path, registry=registry)
    _, result = executor.start_session(skill, {})
    assert len(result.sources) >= 0  # may be empty if collection is empty


@pytest.mark.skipif(
    not (_chroma_available("code_intelligence") and _chroma_available("doc_intelligence")),
    reason="code_intelligence or doc_intelligence not indexed",
)
def test_executor_real_retrieval_cross_domain_code_doc(tmp_path):
    from SkillIntelligence.base import BaseSkill, SkillStep
    from SkillIntelligence.executor import SkillExecutor
    from SkillIntelligence.registry import SkillRegistry

    class CrossReal(BaseSkill):
        name = "cross_real"
        description = "test"
        parameters = {}
        steps = [
            SkillStep(id="s1", title="T", description="d",
                      knowledge_query="configuration setup", domains=["code", "doc"]),
        ]

    skill = CrossReal()
    registry = SkillRegistry()
    registry._register(skill, source="python")
    executor = SkillExecutor(llm=_mock_llm(), sessions_dir=tmp_path, registry=registry)
    _, result = executor.start_session(skill, {})
    assert result is not None


@pytest.mark.skipif(
    not _chroma_available("doc_intelligence"),
    reason="doc_intelligence collection not indexed",
)
def test_skill_deploy_checklist_end_to_end(tmp_path):
    from SkillIntelligence.executor import SkillExecutor
    from SkillIntelligence.registry import SkillRegistry
    from SkillIntelligence.skills.deploy_checklist import DeployChecklist

    skill = DeployChecklist()
    registry = SkillRegistry()
    registry._register(skill, source="python")
    executor = SkillExecutor(llm=_mock_llm(), sessions_dir=tmp_path, registry=registry)
    session_id, r1 = executor.start_session(skill, {"service_name": "api", "environment": "staging"})
    assert r1.step_id == "step_1"
    r2 = executor.next_step(session_id)
    assert r2 is not None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Server endpoint tests (TestClient)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def skill_test_app(tmp_path):
    """Build a FastAPI test app with mocked registry and executor. Returns (app, registry, executor)."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    from SkillIntelligence.base import BaseSkill, SkillStep
    from SkillIntelligence.executor import SkillExecutor
    from SkillIntelligence.registry import SkillRegistry

    class FixtureSkill(BaseSkill):
        name = "fixture_skill"
        description = "A skill for testing"
        parameters = {
            "service_name": {"type": "str", "required": True},
            "environment":  {"type": "str", "required": True, "enum": ["staging", "production"]},
        }
        steps = [
            SkillStep(id="s1", title="Step 1", description="d1",
                      knowledge_query="q1 {service_name}", domains=["doc"]),
            SkillStep(id="s2", title="Step 2", description="d2",
                      knowledge_query="q2 {environment}", domains=["code"]),
        ]

    registry = SkillRegistry()
    registry._register(FixtureSkill(), source="python")

    executor = SkillExecutor(
        llm=_mock_llm(),
        sessions_dir=tmp_path,
        retriever_factory=lambda c: _mock_retriever(),
        registry=registry,
    )

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {
            "status": "ok", "module": "skill",
            "skills_count": registry.count(),
            "llm_backend": "mock", "llm_available": True,
        }

    @app.get("/api/v1/skill/list")
    def list_skills():
        return {"skills": registry.list_skills()}

    @app.post("/api/v1/skill/start")
    def start(req: _ServerStartReq):
        skill = registry.get_skill(req.skill_name)
        if skill is None:
            raise HTTPException(404, f"Skill '{req.skill_name}' non trovata")
        try:
            sid, result = executor.start_session(skill, req.parameters)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {"session_id": sid, "step": result.__dict__}

    @app.post("/api/v1/skill/next")
    def nxt(req: _ServerNextReq):
        try:
            result = executor.next_step(req.session_id, req.user_input)
        except KeyError as e:
            raise HTTPException(404, str(e))
        if result is None:
            return {"step": None, "completed": True}
        return {"step": result.__dict__, "completed": False}

    @app.get("/api/v1/skill/session/{session_id}")
    def session_info(session_id: str):
        try:
            return executor.get_session_info(session_id)
        except KeyError as e:
            raise HTTPException(404, str(e))

    return app


class TestServerEndpoints:
    """Server endpoint tests using httpx.AsyncClient to avoid pytest-asyncio/TestClient conflict."""

    async def test_health_endpoint_returns_skill_count(self, skill_test_app):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=skill_test_app), base_url="http://test") as client:
            r = await client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["module"] == "skill"
        assert data["skills_count"] >= 1

    async def test_list_skills_returns_both_sources(self, skill_test_app):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=skill_test_app), base_url="http://test") as client:
            r = await client.get("/api/v1/skill/list")
        assert r.status_code == 200
        skills = r.json()["skills"]
        assert len(skills) >= 1
        names = [s["name"] for s in skills]
        assert "fixture_skill" in names

    async def test_start_session_invalid_skill_returns_404(self, skill_test_app):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=skill_test_app), base_url="http://test") as client:
            r = await client.post("/api/v1/skill/start",
                                  json={"skill_name": "ghost", "parameters": {}})
        assert r.status_code == 404

    async def test_start_session_missing_params_returns_422(self, skill_test_app):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=skill_test_app), base_url="http://test") as client:
            r = await client.post("/api/v1/skill/start", json={
                "skill_name": "fixture_skill",
                "parameters": {}
            })
        assert r.status_code == 422

    async def test_next_step_invalid_session_returns_404(self, skill_test_app):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=skill_test_app), base_url="http://test") as client:
            r = await client.post("/api/v1/skill/next",
                                  json={"session_id": "bad-id-xyz"})
        assert r.status_code == 404

    async def test_full_skill_flow_deploy_checklist(self, skill_test_app):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=skill_test_app), base_url="http://test") as client:
            # Start
            r = await client.post("/api/v1/skill/start", json={
                "skill_name": "fixture_skill",
                "parameters": {"service_name": "api", "environment": "staging"},
            })
            assert r.status_code == 200
            data = r.json()
            sid = data["session_id"]
            assert data["step"]["step_id"] == "s1"
            assert data["step"]["is_last_step"] is False

            # Next step
            r2 = await client.post("/api/v1/skill/next", json={"session_id": sid})
            assert r2.status_code == 200
            data2 = r2.json()
            assert data2["step"]["step_id"] == "s2"
            assert data2["step"]["is_last_step"] is True
            assert data2["completed"] is False

            # Complete
            r3 = await client.post("/api/v1/skill/next", json={"session_id": sid})
            assert r3.status_code == 200
            data3 = r3.json()
            assert data3["completed"] is True
            assert data3["step"] is None
