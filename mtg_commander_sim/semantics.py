from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .util import stable_json

TRUST_LEVELS = {
    "trusted",
    "provisional",
    "unresolved",
    "intentionally_ignored",
}
SEMANTIC_SCHEMA_VERSION = 2
BUILTIN_PACK_DIRECTORY = Path(__file__).resolve().parent / "semantic_packs"
VALID_EFFECT_OPERATIONS = {
    "bounce",
    "change_control",
    "choose_cards_apnap",
    "choose_mana",
    "choose_warform",
    "counter",
    "counter_or_destroy_blue",
    "counter_stack",
    "create_token",
    "create_treasure",
    "damage",
    "delayed_trigger",
    "destroy",
    "discard",
    "drain_opponent",
    "draw",
    "draw_optional_land",
    "energy",
    "exile",
    "extra_turn",
    "field_of_dead_token",
    "life",
    "look_top",
    "move",
    "note",
    "reorder_top",
    "sacrifice",
    "sacrifice_if_present",
    "tap",
    "untap",
}


@dataclass(slots=True)
class SemanticProgram:
    key: str
    label: str
    effects: list[dict[str, Any]] = field(default_factory=list)
    destination: str | None = None
    requires_arbiter: bool = False
    notes: str = ""
    version: int = 1
    oracle_id: str | None = None
    ability_id: str = "spell:front"
    active_zone: str = "stack"
    event: str = "resolve"
    semantic_schema_version: int = SEMANTIC_SCHEMA_VERSION
    trust_level: str = "provisional"
    provenance: dict[str, Any] = field(default_factory=dict)
    tests: list[str] = field(default_factory=list)
    handlers: list[dict[str, Any]] = field(default_factory=list)
    target_schema: dict[str, Any] | None = None
    coverage: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.trust_level not in TRUST_LEVELS:
            raise ValueError(f"Unknown semantic trust level {self.trust_level!r}")
        if self.version < 1 or self.semantic_schema_version < 1:
            raise ValueError("Semantic versions must be positive")
        for effect in self.effects:
            operation = str(effect.get("op") or "")
            if operation not in VALID_EFFECT_OPERATIONS:
                raise ValueError(
                    f"Unsupported semantic effect operation {operation!r}"
                )
        if self.trust_level == "trusted":
            if not self.oracle_id:
                raise ValueError("Trusted semantics require an oracle_id")
            required_provenance = {
                "source_oracle_hash",
                "source_rulings_hash",
                "authored_by",
                "review_status",
            }
            missing = sorted(
                key
                for key in required_provenance
                if not self.provenance.get(key)
            )
            if missing:
                raise ValueError(
                    "Trusted semantics require provenance fields: "
                    + ", ".join(missing)
                )
            if not self.tests:
                raise ValueError("Trusted semantics require characterization tests")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "effects": self.effects,
            "destination": self.destination,
            "requires_arbiter": self.requires_arbiter,
            "notes": self.notes,
            "version": self.version,
            "oracle_id": self.oracle_id,
            "ability_id": self.ability_id,
            "active_zone": self.active_zone,
            "event": self.event,
            "semantic_schema_version": self.semantic_schema_version,
            "trust_level": self.trust_level,
            "provenance": self.provenance,
            "tests": self.tests,
            "handlers": self.handlers,
            "target_schema": self.target_schema,
            "coverage": self.coverage,
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
            oracle_id=data.get("oracle_id"),
            ability_id=str(data.get("ability_id") or "spell:front"),
            active_zone=str(data.get("active_zone") or "stack"),
            event=str(data.get("event") or "resolve"),
            semantic_schema_version=int(
                data.get("semantic_schema_version", SEMANTIC_SCHEMA_VERSION)
            ),
            trust_level=str(data.get("trust_level") or "provisional"),
            provenance=dict(data.get("provenance") or {}),
            tests=[str(value) for value in data.get("tests", [])],
            handlers=[dict(value) for value in data.get("handlers", [])],
            target_schema=(
                dict(data["target_schema"])
                if isinstance(data.get("target_schema"), Mapping)
                else None
            ),
            coverage=[str(value) for value in data.get("coverage", [])],
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

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        pack_paths: Iterable[str | Path] = (),
        include_builtin_packs: bool = True,
    ):
        self.path = Path(path) if path else None
        self._programs: dict[str, SemanticProgram] = {}
        self.loaded_packs: list[dict[str, Any]] = []
        if include_builtin_packs and BUILTIN_PACK_DIRECTORY.exists():
            self.load_packs([BUILTIN_PACK_DIRECTORY])
        if pack_paths:
            self.load_packs(pack_paths)
        if self.path and self.path.exists():
            self.load()

    def load(self) -> None:
        if not self.path:
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        programs = raw.get("programs", raw)
        for key, value in programs.items():
            self._programs[str(key)] = SemanticProgram.from_dict(value)

    @staticmethod
    def _source_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def load_packs(self, paths: Iterable[str | Path]) -> None:
        """Load declarative semantic packs without coupling them to the kernel."""

        candidates: list[Path] = []
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                candidates.extend(sorted(path.glob("*.json")))
            elif path.exists():
                candidates.append(path)
        for path in candidates:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if int(raw.get("schema_version", 0)) != SEMANTIC_SCHEMA_VERSION:
                raise ValueError(
                    f"{path} must use semantic pack schema "
                    f"{SEMANTIC_SCHEMA_VERSION}"
                )
            programs = raw.get("programs", [])
            if isinstance(programs, Mapping):
                items = [
                    {"key": key, **dict(value)}
                    for key, value in programs.items()
                ]
            else:
                items = [dict(value) for value in programs]
            for value in items:
                program = SemanticProgram.from_dict(value)
                self._programs[program.key] = program
            self.loaded_packs.append(
                {
                    "name": str(raw.get("name") or path.stem),
                    "path": str(path),
                    "schema_version": int(raw.get("schema_version", 1)),
                    "hash": self._source_hash(path),
                    "program_count": len(items),
                }
            )

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
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

    def programs_for_oracle(
        self,
        oracle_id: str,
        *,
        active_zone: str | None = None,
        event: str | None = None,
    ) -> list[SemanticProgram]:
        return [
            program
            for program in self._programs.values()
            if program.oracle_id == oracle_id
            and (active_zone is None or program.active_zone == active_zone)
            and (event is None or program.event == event)
        ]

    def trust_for_oracle(self, oracle_id: str) -> str:
        programs = self.programs_for_oracle(oracle_id)
        if not programs:
            return "unresolved"
        levels = {program.trust_level for program in programs}
        if "unresolved" in levels:
            return "unresolved"
        if "provisional" in levels:
            return "provisional"
        if levels == {"intentionally_ignored"}:
            return "intentionally_ignored"
        return "trusted"

    def programs(self) -> list[SemanticProgram]:
        return [self._programs[key] for key in sorted(self._programs)]
