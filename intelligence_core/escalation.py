"""Policy di escalation locale→Claude API per Intelligence Suite."""

import logging
import os

logger = logging.getLogger(__name__)


class EscalationPolicy:
    """
    Decide se rispondere con modello locale o escalare a Claude API.
    Configurabile via costruttore o variabili d'ambiente.
    """

    def __init__(
        self,
        threshold: float = None,
        max_local_tokens: int = None,
        timeout_seconds: float = 30.0,
    ):
        self.threshold = threshold if threshold is not None else float(
            os.getenv("ESCALATION_THRESHOLD", "0.70")
        )
        self.max_local_tokens = max_local_tokens if max_local_tokens is not None else int(
            os.getenv("ESCALATION_MAX_TOKENS", "4096")
        )
        self.timeout_seconds = timeout_seconds

    def should_escalate(
        self,
        confidence: float,
        query_tokens: int,
        elapsed_ms: float = 0.0,
    ) -> bool:
        """
        True se la query deve essere escalata a Claude API.
        Criteri: confidence bassa, troppi token, timeout superato.
        """
        if confidence < self.threshold:
            logger.info(
                "Escalation: confidence %.2f sotto threshold %.2f",
                confidence, self.threshold,
            )
            return True

        if query_tokens > self.max_local_tokens:
            logger.info(
                "Escalation: %d token sopra max %d",
                query_tokens, self.max_local_tokens,
            )
            return True

        if elapsed_ms > self.timeout_seconds * 1000:
            logger.info(
                "Escalation: timeout %.0fms sopra %.0fms",
                elapsed_ms, self.timeout_seconds * 1000,
            )
            return True

        return False
