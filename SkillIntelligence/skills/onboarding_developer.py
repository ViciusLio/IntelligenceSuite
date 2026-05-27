"""Onboarding Developer Skill — guides a new developer through team onboarding."""

from SkillIntelligence.base import BaseSkill, SkillStep


class OnboardingDeveloper(BaseSkill):
    name = "onboarding_developer"
    description = (
        "Guida un nuovo sviluppatore attraverso il processo di onboarding: "
        "setup ambiente, esplorazione codebase e prima task con le convenzioni del team."
    )
    parameters = {
        "developer_name": {"type": "str", "required": True},
        "focus":          {"type": "str", "required": True, "enum": ["backend", "frontend", "data"]},
    }
    steps = [
        SkillStep(
            id="step_1",
            title="Setup ambiente di sviluppo",
            description=(
                "Configurazione dell'ambiente di sviluppo locale: prerequisiti, "
                "installazione dipendenze, variabili d'ambiente e verifica setup."
            ),
            knowledge_query=(
                "setup ambiente sviluppo prerequisiti installazione {focus}"
            ),
            domains=["doc", "mentor"],
        ),
        SkillStep(
            id="step_2",
            title="Primo giro del codebase",
            description=(
                "Panoramica della struttura del codebase, moduli principali, "
                "pattern architetturali e punti di ingresso rilevanti per {focus}."
            ),
            knowledge_query=(
                "struttura codebase architettura moduli principali {focus}"
            ),
            domains=["code"],
        ),
        SkillStep(
            id="step_3",
            title="Prima task e convenzioni del team",
            description=(
                "Introduzione alle convenzioni di sviluppo del team, workflow git, "
                "code review e indicazioni per la prima task assegnata."
            ),
            knowledge_query=(
                "convenzioni sviluppo workflow git code review onboarding {focus}"
            ),
            domains=["code", "mentor"],
        ),
    ]
