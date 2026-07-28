from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .deck import DeckDefinition

BUILTIN_PROFILE_DIRECTORY = Path(__file__).resolve().parent / "deck_profiles"


def deck_profile_fingerprint(deck: DeckDefinition) -> str:
    payload = {
        "commanders": sorted(deck.commanders),
        "cards": sorted(
            (entry.name, int(entry.quantity), entry.board)
            for entry in deck.entries
            if entry.board in {"mainboard", "commander"}
        ),
    }
    compact = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class DeckPilotProfile:
    deck_fingerprint: str
    commander: list[str]
    archetype: str
    primary_game_plan: str
    secondary_game_plan: str
    primary_engine_pieces: list[str] = field(default_factory=list)
    primary_win_lines: list[str] = field(default_factory=list)
    common_tutor_priorities: list[str] = field(default_factory=list)
    cards_commonly_used_as_fodder: list[str] = field(default_factory=list)
    interaction_priorities: list[str] = field(default_factory=list)
    mulligan_requirements: list[str] = field(default_factory=list)
    cards_normally_preserved: list[str] = field(default_factory=list)
    cards_that_require_setup: list[str] = field(default_factory=list)
    known_color_requirements: list[str] = field(default_factory=list)
    expected_development_turns: list[str] = field(default_factory=list)
    threat_assessment: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeckPilotProfile":
        return cls(
            deck_fingerprint=str(value["deck_fingerprint"]),
            commander=[str(item) for item in value.get("commander", [])],
            archetype=str(value.get("archetype") or ""),
            primary_game_plan=str(value.get("primary_game_plan") or ""),
            secondary_game_plan=str(value.get("secondary_game_plan") or ""),
            primary_engine_pieces=[
                str(item) for item in value.get("primary_engine_pieces", [])
            ],
            primary_win_lines=[
                str(item) for item in value.get("primary_win_lines", [])
            ],
            common_tutor_priorities=[
                str(item) for item in value.get("common_tutor_priorities", [])
            ],
            cards_commonly_used_as_fodder=[
                str(item)
                for item in value.get("cards_commonly_used_as_fodder", [])
            ],
            interaction_priorities=[
                str(item) for item in value.get("interaction_priorities", [])
            ],
            mulligan_requirements=[
                str(item) for item in value.get("mulligan_requirements", [])
            ],
            cards_normally_preserved=[
                str(item) for item in value.get("cards_normally_preserved", [])
            ],
            cards_that_require_setup=[
                str(item) for item in value.get("cards_that_require_setup", [])
            ],
            known_color_requirements=[
                str(item) for item in value.get("known_color_requirements", [])
            ],
            expected_development_turns=[
                str(item) for item in value.get("expected_development_turns", [])
            ],
            threat_assessment=str(value.get("threat_assessment") or ""),
            schema_version=int(value.get("schema_version", 1)),
        )


class DeckProfileCache:
    """Load each deck's advisory profile once into its isolated seat context."""

    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory or BUILTIN_PROFILE_DIRECTORY)
        self._cache: dict[str, DeckPilotProfile | None] = {}

    def load(self, fingerprint: str) -> DeckPilotProfile | None:
        if fingerprint in self._cache:
            return self._cache[fingerprint]
        path = self.directory / f"{fingerprint}.json"
        profile = (
            DeckPilotProfile.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if path.exists()
            else None
        )
        if profile and profile.deck_fingerprint != fingerprint:
            raise ValueError(
                f"Profile {path} declares fingerprint "
                f"{profile.deck_fingerprint}, expected {fingerprint}"
            )
        self._cache[fingerprint] = profile
        return profile

    def load_for_deck(self, deck: DeckDefinition) -> DeckPilotProfile | None:
        return self.load(deck_profile_fingerprint(deck))
