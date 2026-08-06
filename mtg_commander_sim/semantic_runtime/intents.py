from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypeAlias

from ..drawing.model import (
    DiscardDrawnCardUnlessType,
    DrawnCardAction,
    RevealDrawnCard,
)
from ..replacement.immutable import FrozenMap


@dataclass(frozen=True, slots=True)
class DrawCardsIntent:
    player: str
    count: int
    reason: str
    private: bool = False
    post_draw_actions: tuple[DrawnCardAction, ...] = ()

    def __post_init__(self) -> None:
        actions = tuple(self.post_draw_actions)
        if any(
            not isinstance(
                action,
                (RevealDrawnCard, DiscardDrawnCardUnlessType),
            )
            for action in actions
        ):
            raise TypeError("Draw intents require typed post-draw actions")
        object.__setattr__(self, "post_draw_actions", actions)


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
    logical_object_id: str | None = None


@dataclass(frozen=True, slots=True)
class UntapAllCreaturesIntent:
    actor: str
    reason: str


@dataclass(frozen=True, slots=True)
class AddManaIntent:
    player: str
    color: str
    amount: int
    actor: str
    reason: str
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class SetCardDesignationIntent:
    object_ref: str
    designation: Literal["chosen_name", "chosen_creature_type"]
    value: str
    actor: str
    reason: str
    apply_as_subtype: bool = False

    def __post_init__(self) -> None:
        if self.designation not in {
            "chosen_name",
            "chosen_creature_type",
        }:
            raise ValueError("Card designation kind is unsupported")
        if any(
            type(value) is not str or not value
            for value in (
                self.object_ref,
                self.value,
                self.actor,
                self.reason,
            )
        ):
            raise ValueError(
                "Card designation identifiers and text must be nonempty strings"
            )
        if type(self.apply_as_subtype) is not bool:
            raise ValueError("Designation subtype application must be boolean")
        if self.apply_as_subtype and self.designation != "chosen_creature_type":
            raise ValueError(
                "Only a chosen creature type may become a subtype"
            )


@dataclass(frozen=True, slots=True)
class RecordChoiceIntent:
    actor: str
    event_code: str
    message: str
    details: FrozenMap
    importance: int = 1
    visibility: tuple[str, ...] | None = None
    changed_object_refs: tuple[str, ...] = ()
    changed_players: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.details, FrozenMap):
            object.__setattr__(self, "details", FrozenMap(self.details))


@dataclass(frozen=True, slots=True)
class ZoneMoveIntent:
    actor: str
    object_ref: str
    expected_zones: tuple[str, ...]
    destination: str
    reason: str
    required_types: tuple[str, ...] = ()
    owned_only: bool = False
    controlled_only: bool = False
    new_controller: str | None = None
    tapped_policy: Literal[
        "preserve", "land_entry", "tapped", "untapped"
    ] = "preserve"
    semantic_events: bool = True
    optional_if_missing: bool = False


@dataclass(frozen=True, slots=True)
class MoveObjectsSimultaneouslyIntent:
    actor: str
    object_refs: tuple[str, ...]
    expected_zones: tuple[str, ...]
    destination: str
    reason: str
    owned_only: bool = False
    controlled_only: bool = False


@dataclass(frozen=True, slots=True)
class ChooseOneRestBottomRandomIntent:
    actor: str
    player: str
    chosen_ref: str
    looked_refs: tuple[str, ...]
    reason: str
    source_stack_ref: str
    event_code: str = "library.choose_one_rest_bottom_random"


@dataclass(frozen=True, slots=True)
class ShuffleLibraryIntent:
    actor: str
    player: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReturnCardsToLibraryTopIntent:
    actor: str
    player: str
    refs_top_first: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class RecordZoneMoveIntent:
    actor: str
    object_ref: str
    event_code: str
    message: str
    details: FrozenMap
    importance: int = 2
    changed_player: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.details, FrozenMap):
            object.__setattr__(self, "details", FrozenMap(self.details))


@dataclass(frozen=True, slots=True)
class LifeChangeIntent:
    actor: str
    player: str
    amount: int
    reason: str


@dataclass(frozen=True, slots=True)
class PayLifeIntent:
    actor: str
    player: str
    amount: int
    reason: str


@dataclass(frozen=True, slots=True)
class RevealLibraryCardsIntent:
    actor: str
    player: str
    viewer: str
    refs_top_first: tuple[str, ...]
    reason: str
    public: bool = False


@dataclass(frozen=True, slots=True)
class MoveLibraryCardsToBottomIntent:
    actor: str
    player: str
    refs: tuple[str, ...]
    looked_count: int
    reason: str


@dataclass(frozen=True, slots=True)
class ReorderLibraryTopIntent:
    actor: str
    player: str
    viewer: str
    refs_top_first: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class PayManaCostIntent:
    actor: str
    player: str
    requirements: FrozenMap
    reason: str
    event_code: str
    message: str
    details: FrozenMap
    changed_object_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.requirements, FrozenMap):
            object.__setattr__(
                self,
                "requirements",
                FrozenMap(self.requirements),
            )
        if not isinstance(self.details, FrozenMap):
            object.__setattr__(self, "details", FrozenMap(self.details))


@dataclass(frozen=True, slots=True)
class PlaceCountersIntent:
    actor: str
    object_refs: tuple[str, ...]
    counter_name: str
    amount: int
    reason: str
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CounterStackIntent:
    actor: str
    stack_ref: str
    reason: str
    countered_by: str


@dataclass(frozen=True, slots=True)
class EliminatePlayersIntent:
    actor: str
    players: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class CopyStackItemIntent:
    actor: str
    controller: str
    target_stack_ref: str
    targets: tuple[str, ...]
    target_groups: FrozenMap
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_groups, FrozenMap):
            object.__setattr__(
                self,
                "target_groups",
                FrozenMap(self.target_groups),
            )


@dataclass(frozen=True, slots=True)
class RetargetStackItemIntent:
    actor: str
    target_stack_ref: str
    targets: tuple[str, ...]
    target_groups: FrozenMap
    source_stack_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_groups, FrozenMap):
            object.__setattr__(
                self,
                "target_groups",
                FrozenMap(self.target_groups),
            )


@dataclass(frozen=True, slots=True)
class CreateTokenIntent:
    actor: str
    controller: str
    name: str
    quantity: int
    reason: str
    characteristics: FrozenMap = field(default_factory=FrozenMap)
    copy_of: str | None = None
    temporary_keywords: tuple[str, ...] = ()
    sacrifice_at_end_step: bool = False
    sacrifice_on_controller_end_step: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.characteristics, FrozenMap):
            object.__setattr__(
                self,
                "characteristics",
                FrozenMap(self.characteristics),
            )


@dataclass(frozen=True, slots=True)
class CopyControlledTokensIntent:
    actor: str
    controller: str
    chosen_token_ref: str
    source_stack_ref: str
    reason: str


@dataclass(frozen=True, slots=True)
class AmassIntent:
    actor: str
    controller: str
    subtype: str
    amount: int
    reason: str
    army_ref: str | None = None


@dataclass(frozen=True, slots=True)
class AddSubtypeIntent:
    actor: str
    object_ref: str
    subtype: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProliferateIntent:
    actor: str
    selections: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class DomainEffectIntent:
    actor: str
    operation: str
    effect: FrozenMap
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.effect, FrozenMap):
            object.__setattr__(self, "effect", FrozenMap(self.effect))


SemanticIntent: TypeAlias = (
    DrawCardsIntent
    | BecomeMonarchIntent
    | SetPermanentTappedIntent
    | UntapAllCreaturesIntent
    | AddManaIntent
    | SetCardDesignationIntent
    | RecordChoiceIntent
    | ZoneMoveIntent
    | MoveObjectsSimultaneouslyIntent
    | ChooseOneRestBottomRandomIntent
    | ShuffleLibraryIntent
    | ReturnCardsToLibraryTopIntent
    | RecordZoneMoveIntent
    | LifeChangeIntent
    | PayLifeIntent
    | RevealLibraryCardsIntent
    | MoveLibraryCardsToBottomIntent
    | ReorderLibraryTopIntent
    | PayManaCostIntent
    | PlaceCountersIntent
    | CounterStackIntent
    | EliminatePlayersIntent
    | CopyStackItemIntent
    | RetargetStackItemIntent
    | CreateTokenIntent
    | CopyControlledTokensIntent
    | AmassIntent
    | AddSubtypeIntent
    | ProliferateIntent
    | DomainEffectIntent
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
