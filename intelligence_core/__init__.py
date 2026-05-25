"""intelligence_core — layer condiviso della Intelligence Suite v0.1.0."""

__version__ = "0.1.0"

from intelligence_core.chunk import make_chunk, validate_chunk, compute_checksum
from intelligence_core.escalation import EscalationPolicy
from intelligence_core.config import settings
