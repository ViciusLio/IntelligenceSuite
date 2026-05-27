"""Base types for SkillIntelligence: SkillStep, SkillContext, SkillResult, BaseSkill."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

Domain = Literal["code", "doc", "mentor", "all"]

VALID_DOMAINS: set[str] = {"code", "doc", "mentor", "all"}


@dataclass
class SkillStep:
    id: str
    title: str
    description: str
    knowledge_query: str
    domains: list[Domain]
    requires_confirmation: bool = False
    use_agent: bool = False


@dataclass
class SkillContext:
    skill_name: str
    parameters: dict[str, Any]
    completed_steps: list[str] = field(default_factory=list)
    step_outputs: dict[str, str] = field(default_factory=dict)
    current_step_index: int = 0


@dataclass
class SkillResult:
    step_id: str
    title: str
    guidance: str
    sources: list[dict]
    requires_confirmation: bool
    is_last_step: bool
    session_id: str


class BaseSkill:
    """Base class for all Skills — extend and set class attributes."""

    name: str = ""
    description: str = ""
    parameters: dict[str, dict] = {}
    steps: list[SkillStep] = []

    def validate_parameters(self, params: dict[str, Any]) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        for param_name, spec in self.parameters.items():
            required = spec.get("required", False)
            if required and param_name not in params:
                errors.append(f"Parametro obbligatorio mancante: '{param_name}'")
                continue
            value = params.get(param_name)
            if value is not None and "enum" in spec:
                allowed = spec["enum"]
                if value not in allowed:
                    errors.append(
                        f"Valore non valido per '{param_name}': '{value}'. "
                        f"Valori ammessi: {allowed}"
                    )
        return errors

    def interpolate(self, template: str, params: dict[str, Any]) -> str:
        """Replace {param} placeholders with actual values from params."""
        result = template
        for key, value in params.items():
            result = result.replace(f"{{{key}}}", str(value))
        # Leave unresolved {placeholders} as-is rather than crashing
        return result

    @classmethod
    def source_type(cls) -> str:
        return "python"

    def to_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source_type(),
            "steps_count": len(self.steps),
            "parameters": self.parameters,
        }
