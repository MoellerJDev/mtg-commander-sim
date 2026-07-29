from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .deck import DeckDefinition, extract_moxfield_id, is_moxfield_source

BUILTIN_PROFILE_DIRECTORY = Path(__file__).resolve().parent / "deck_profiles"
FINGERPRINT_ALGORITHM_VERSION = 1
PROFILE_SCHEMA_VERSION = 2


def _hash(value: Any) -> str:
    compact = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def deck_list_payload(deck: DeckDefinition) -> dict[str, Any]:
    return {
        "commanders": sorted(deck.commanders),
        "cards": sorted(
            (entry.name, int(entry.quantity), entry.board)
            for entry in deck.entries
            if entry.board in {"mainboard", "commander"}
        ),
    }


def deck_list_fingerprint(deck: DeckDefinition) -> str:
    """Fingerprint the exact validated Commander list, independent of labels."""

    return _hash(deck_list_payload(deck))


def deck_profile_fingerprint(deck: DeckDefinition) -> str:
    """Compatibility alias for the v0.4 profile-list fingerprint."""

    return deck_list_fingerprint(deck)


def deck_source_fingerprint(deck: DeckDefinition) -> str | None:
    """Fingerprint stable source provenance when a source is available."""

    if not deck.source:
        return None
    source = str(deck.source)
    source_identity = (
        f"moxfield:{extract_moxfield_id(source)}"
        if is_moxfield_source(source)
        else str(Path(source).resolve())
    )
    metadata = {
        key: deck.metadata[key]
        for key in (
            "id",
            "publicId",
            "format",
            "createdAtUtc",
            "lastUpdatedAtUtc",
        )
        if deck.metadata.get(key) is not None
    }
    return _hash(
        {
            "algorithm_version": FINGERPRINT_ALGORITHM_VERSION,
            "source": source_identity,
            "metadata": metadata,
            "deck_list_fingerprint": deck_list_fingerprint(deck),
        }
    )


def profile_source_fingerprint(value: Mapping[str, Any]) -> str:
    """Integrity hash for advisory profile content, excluding runtime status."""

    payload = {
        key: child
        for key, child in dict(value).items()
        if key
        not in {
            "profile_source_fingerprint",
            "validation",
            "deck_fingerprint",
            "schema_version",
        }
    }
    return _hash(payload)


@dataclass(slots=True)
class DeckPilotProfile:
    deck_list_fingerprint: str
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
    deck_source_fingerprint: str | None = None
    profile_source_fingerprint: str = ""
    profile_schema_version: int = PROFILE_SCHEMA_VERSION
    fingerprint_algorithm_version: int = FINGERPRINT_ALGORITHM_VERSION

    @property
    def deck_fingerprint(self) -> str:
        return self.deck_list_fingerprint

    @property
    def schema_version(self) -> int:
        return self.profile_schema_version

    def to_dict(self) -> dict[str, Any]:
        payload = {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }
        # Explicitly named compatibility aliases remain readable but are never
        # used to establish an exact match.
        payload["deck_fingerprint"] = self.deck_list_fingerprint
        payload["schema_version"] = self.profile_schema_version
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeckPilotProfile":
        return cls(
            deck_list_fingerprint=str(
                value.get("deck_list_fingerprint")
                or value.get("deck_fingerprint")
                or ""
            ),
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
            deck_source_fingerprint=(
                str(value["deck_source_fingerprint"])
                if value.get("deck_source_fingerprint")
                else None
            ),
            profile_source_fingerprint=str(
                value.get("profile_source_fingerprint") or ""
            ),
            profile_schema_version=int(
                value.get(
                    "profile_schema_version",
                    value.get("schema_version", 1),
                )
            ),
            fingerprint_algorithm_version=int(
                value.get("fingerprint_algorithm_version", 0)
            ),
        )


@dataclass(frozen=True, slots=True)
class ProfileLoadResult:
    profile: DeckPilotProfile | None
    status: str
    profile_fingerprint_match: bool
    warning: str | None = None


class DeckProfileCache:
    """Load an advisory profile only with explicit list-fingerprint fidelity."""

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
        if profile:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if profile.deck_list_fingerprint != fingerprint:
                raise ValueError(
                    f"Profile {path} declares deck_list_fingerprint "
                    f"{profile.deck_list_fingerprint}, expected {fingerprint}"
                )
            if profile.profile_schema_version != PROFILE_SCHEMA_VERSION:
                raise ValueError(
                    f"Profile {path} schema {profile.profile_schema_version} is "
                    f"not compatible with {PROFILE_SCHEMA_VERSION}"
                )
            if (
                profile.fingerprint_algorithm_version
                != FINGERPRINT_ALGORITHM_VERSION
            ):
                raise ValueError(
                    f"Profile {path} fingerprint algorithm is incompatible"
                )
            expected_source = profile_source_fingerprint(raw)
            if profile.profile_source_fingerprint != expected_source:
                raise ValueError(
                    f"Profile {path} content fingerprint does not match"
                )
        self._cache[fingerprint] = profile
        return profile

    def load_validated(
        self,
        deck: DeckDefinition,
        *,
        allow_commander_fallback: bool = False,
    ) -> ProfileLoadResult:
        fingerprint = deck_list_fingerprint(deck)
        exact = self.load(fingerprint)
        if exact is not None:
            return ProfileLoadResult(exact, "exact", True)
        if not allow_commander_fallback:
            return ProfileLoadResult(
                None,
                "missing",
                False,
                "No exact compatible profile exists for this deck list.",
            )
        commander_key = sorted(name.casefold() for name in deck.commanders)
        for path in sorted(self.directory.glob("*.json")):
            candidate = self.load(path.stem)
            if candidate is None:
                continue
            if sorted(name.casefold() for name in candidate.commander) == commander_key:
                return ProfileLoadResult(
                    candidate,
                    "commander_fallback",
                    False,
                    "Loaded by commander/archetype only; tutor, mulligan, and "
                    "combo assumptions are not exact-list validated.",
                )
        return ProfileLoadResult(
            None,
            "missing",
            False,
            "No exact or commander-fallback profile exists.",
        )

    def load_for_deck(
        self, deck: DeckDefinition
    ) -> DeckPilotProfile | None:
        return self.load_validated(deck).profile
