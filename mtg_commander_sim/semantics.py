from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .util import stable_json


@dataclass(slots=True)
class SemanticProgram:
    key: str
    label: str
    effects: list[dict[str, Any]] = field(default_factory=list)
    destination: str | None = None
    requires_arbiter: bool = False
    notes: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "effects": self.effects,
            "destination": self.destination,
            "requires_arbiter": self.requires_arbiter,
            "notes": self.notes,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticProgram":
        return cls(
            key=str(data["key"]),
            label=str(data.get("label") or data["key"]),
            effects=[dict(effect) for effect in data.get("effects", [])],
            destination=data.get("destination"),
            requires_arbiter=bool(data.get("requires_arbiter", False)),
            notes=str(data.get("notes") or ""),
            version=int(data.get("version", 1)),
        )


class SemanticRegistry:
    """
    Cache of card/ability semantics expressed in the engine's generic effect DSL.

    The registry is deliberately outside the rules kernel.  A rules model can
    compile an Oracle ability once, store it here, and all later simulations can
    resolve the same object without another LLM call.  A production client may
    replace this JSON registry with generated code or a database without changing
    pilot permissions or the command protocol.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._programs: dict[str, SemanticProgram] = {}
        if self.path and self.path.exists():
            self.load()

    def load(self) -> None:
        if not self.path:
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        programs = raw.get("programs", raw)
        self._programs = {
            str(key): SemanticProgram.from_dict(value)
            for key, value in programs.items()
        }

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "programs": {
                key: program.to_dict() for key, program in sorted(self._programs.items())
            },
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(stable_json(payload), encoding="utf-8")
        temporary.replace(self.path)

    def get(self, key: str | None) -> SemanticProgram | None:
        if not key:
            return None
        return self._programs.get(key)

    def put(self, program: SemanticProgram | Mapping[str, Any]) -> SemanticProgram:
        if not isinstance(program, SemanticProgram):
            program = SemanticProgram.from_dict(program)
        self._programs[program.key] = program
        self.save()
        return program

    def remove(self, key: str) -> None:
        self._programs.pop(key, None)
        self.save()

    def keys(self) -> list[str]:
        return sorted(self._programs)
