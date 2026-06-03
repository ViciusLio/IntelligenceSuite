"""Interfaccia comune per i parser strutturali."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypedDict


class ChunkDict(TypedDict):
    id: str
    text: str
    type: str
    source: str
    domain: str
    metadata: dict


class BaseParser(ABC):
    language: str = ""
    extensions: list[str] = []

    @abstractmethod
    def parse_file(self, path: Path) -> list[ChunkDict]:
        """Legge un file e ritorna chunk nel formato standard.

        Non deve mai sollevare eccezioni su file malformati: logga un
        warning e ritorna lista vuota.
        """
        ...

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions
