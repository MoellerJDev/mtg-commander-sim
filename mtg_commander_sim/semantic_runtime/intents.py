from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


@dataclass(frozen=True, slots=True)
class DrawCardsIntent:
    player: str
    count: int
    reason: str
    private: bool = False


@dataclass(frozen=True, slots=True)
class BecomeMonarchIntent:
    player: str
    reason: str


@dataclass(frozen=True, slots=True)
class SetPermanentTappedIntent:
    object_ref: str
    actor: str
    tapped: bool
    reason: str


@dataclass(frozen=True, slots=True)
class UntapAllCreaturesIntent:
    actor: str
    reason: str


SemanticIntent: TypeAlias = (
    DrawCardsIntent
    | BecomeMonarchIntent
    | SetPermanentTappedIntent
    | UntapAllCreaturesIntent
)
ResultShape: TypeAlias = Literal["single", "by_player"]


@dataclass(frozen=True, slots=True)
class IntentPlan:
    operation: str
    handler_id: str
    intents: tuple[SemanticIntent, ...]
    result_shape: ResultShape = "single"

    def __post_init__(self) -> None:
        if self.result_shape not in {"single", "by_player"}:
            raise ValueError(f"Unknown intent result shape {self.result_shape!r}")
        if self.result_shape == "single" and len(self.intents) != 1:
            raise ValueError("A single-result plan must contain one intent")
