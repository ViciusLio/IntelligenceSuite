"""Deploy Checklist Skill — guides through a service deploy step by step."""

from SkillIntelligence.base import BaseSkill, SkillStep


class DeployChecklist(BaseSkill):
    name = "deploy_checklist"
    description = (
        "Guida attraverso il processo di deploy di un servizio verificando "
        "dipendenze, configurazione, checklist pre-deploy e piano di rollback."
    )
    parameters = {
        "service_name": {"type": "str", "required": True},
        "environment":  {"type": "str", "required": True, "enum": ["staging", "production"]},
    }
    steps = [
        SkillStep(
            id="step_1",
            title="Verifica dipendenze",
            description=(
                "Analisi delle dipendenze del servizio nel codice sorgente e nella "
                "documentazione tecnica per l'ambiente target."
            ),
            knowledge_query="dipendenze e requisiti di {service_name} per ambiente {environment}",
            domains=["code", "doc"],
        ),
        SkillStep(
            id="step_2",
            title="Configurazione ambiente",
            description=(
                "Verifica della configurazione corretta per l'ambiente target: "
                "variabili d'ambiente, secrets, endpoint e parametri specifici."
            ),
            knowledge_query=(
                "configurazione {environment} variabili d'ambiente {service_name}"
            ),
            domains=["doc"],
        ),
        SkillStep(
            id="step_3",
            title="Checklist pre-deploy",
            description=(
                "Verifica della checklist pre-deploy con le best practice del team: "
                "test, code review, monitoring e approvazioni necessarie."
            ),
            knowledge_query=(
                "checklist pre-deploy best practice {service_name} {environment}"
            ),
            domains=["doc", "mentor"],
        ),
        SkillStep(
            id="step_4",
            title="Piano di rollback",
            description=(
                "Definizione del piano di rollback in caso di problemi post-deploy: "
                "procedura, responsabili e criteri di attivazione."
            ),
            knowledge_query=(
                "piano rollback procedura ripristino {service_name} {environment}"
            ),
            domains=["doc"],
        ),
    ]
