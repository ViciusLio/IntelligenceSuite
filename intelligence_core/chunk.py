"""Schema chunk unificato e funzioni di serializzazione per Intelligence Suite."""

from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

VALID_DOMAINS    = {"code", "doc", "api", "data", "mentor", "qa"}
VALID_CODE_TYPES = {"function", "class", "interface", "config_block", "module", "file"}
VALID_DOC_TYPES  = {"section", "table", "procedure", "definition", "code_example", "file"}
VALID_API_TYPES  = {"endpoint", "schema", "example", "parameter"}
VALID_MENTOR_TYPES = {
    "practice",
    "onboarding_step",
    "role_guide",
    "faq",
    "glossary",
}
# qa: coppie Domanda/Risposta in stile (ProposalIntelligence — questionari / gare)
VALID_QA_TYPES = {"qa_pair"}


def make_chunk_id(domain: str, type_: str, locator: str) -> str:
    """Costruisce l'ID nel formato domain::type::locator."""
    return f"{domain}::{type_}::{locator}"


def compute_checksum(text: str) -> str:
    """SHA-256 del testo del chunk."""
    return hashlib.sha256(text.encode()).hexdigest()


def validate_chunk(chunk: dict) -> list[str]:
    """
    Valida un chunk rispetto allo schema Intelligence Suite.
    Ritorna lista di errori — lista vuota significa chunk valido.
    """
    errors = []
    required = {"id", "domain", "type", "text", "source", "language", "metadata"}
    for field in required:
        if field not in chunk:
            errors.append(f"Campo mancante: {field}")

    if "id" in chunk:
        parts = chunk["id"].split("::")
        if len(parts) < 3:
            errors.append(f"ID malformato (atteso domain::type::locator): {chunk['id']}")

    if "domain" in chunk and chunk["domain"] not in VALID_DOMAINS:
        errors.append(f"Domain non valido: {chunk['domain']}")

    if "text" in chunk:
        text = chunk["text"]
        if len(text.strip()) < 20:
            errors.append(f"Testo troppo corto ({len(text)} chars)")
        if len(text) > 8000:
            errors.append(f"Testo troppo lungo ({len(text)} chars) — rivedi il chunking")

    if "source" in chunk and chunk["source"].startswith("/"):
        errors.append("Source deve essere path relativo, non assoluto")

    if "metadata" in chunk and not isinstance(chunk["metadata"], dict):
        errors.append("Metadata deve essere un dict")

    return errors


def make_chunk(
    domain: str,
    type_: str,
    locator: str,
    text: str,
    source: str,
    language: str,
    metadata: dict,
) -> dict:
    """Factory: crea un chunk valido con checksum e timestamp."""
    return {
        "id":         make_chunk_id(domain, type_, locator),
        "domain":     domain,
        "type":       type_,
        "text":       text,
        "source":     source,
        "language":   language,
        "metadata":   metadata,
        "embedding":  None,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "checksum":   compute_checksum(text),
    }


def chunk_to_jsonl(chunk: dict) -> str:
    """Serializza un chunk in una riga JSONL."""
    return json.dumps(chunk, ensure_ascii=False)


def chunk_from_jsonl(line: str) -> dict:
    """Deserializza una riga JSONL in un chunk."""
    return json.loads(line.strip())
