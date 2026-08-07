from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypeAlias

from ..affected_permanents import AffectedPermanentSetSpec
from ..drawing.model import (
    DiscardDrawnCardUnlessType,
    DrawnCardAction,
    RevealDrawnCard,
)
from ..fixed_damage_set_model import FixedDamageSetSpec
from ..replacement.immutable import FrozenMap, freeze_value


def _freeze_replacement_selections(
    values: tuple[str | FrozenMap, ...],
    *,
    family: str,
) -> tuple[str | FrozenMap, ...]:
    frozen: list[str | FrozenMap] = []
    for index, value in enumerate(values):
        if isinstance(value, str):
            if not value:
                raise ValueError(
                    f"{family} replacement selections must be nonempty"
                )
            frozen.append(value)
            continue
        result = freeze_value(
            value,
            field=f"replacement_selections[{index}]",
        )
        if not isinstance(result, FrozenMap):
            raise ValueError(
                f"{family} replacement selections must be objects"
            )
        frozen.append(result)
    return tuple(frozen)


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
class DestroyPermanentIntent:
    actor: str
    object_ref: str
    reason: str
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.actor, self.object_ref, self.reason)):
            raise ValueError(
                "Destruction intents require actor, object, and reason"
            )
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                self.replacement_selections,
                family="Destruction",
            ),
        )


@dataclass(frozen=True, slots=True)
class DestroyPermanentSetIntent:
    actor: str
    spec: AffectedPermanentSetSpec
    reason: str
    source_ref: str | None = None
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if any(type(value) is not str or not value for value in (self.actor, self.reason)):
            raise ValueError(
                "Destruction-set intents require actor and reason"
            )
        if not isinstance(self.spec, AffectedPermanentSetSpec):
            raise ValueError(
                "Destruction-set intents require a typed affected set"
            )
        if self.source_ref is not None and (
            type(self.source_ref) is not str or not self.source_ref
        ):
            raise ValueError(
                "Destruction-set source must be a nonempty reference"
            )
        if self.spec.exclude_source and self.source_ref is None:
            raise ValueError(
                "Source-excluding destruction sets require a source"
            )
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                self.replacement_selections,
                family="Destruction-set",
            ),
        )


@dataclass(frozen=True, slots=True)
class ReturnPermanentToOwnerHandIntent:
    actor: str
    object_ref: str
    reason: str
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.actor, self.object_ref, self.reason)):
            raise ValueError(
                "Return intents require actor, object, and reason"
            )
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                self.replacement_selections,
                family="return-to-owner-hand",
            ),
        )


@dataclass(frozen=True, slots=True)
class ExilePermanentIntent:
    actor: str
    object_ref: str
    reason: str
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.actor, self.object_ref, self.reason)):
            raise ValueError(
                "Permanent-exile intents require actor, object, and reason"
            )
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                self.replacement_selections,
                family="Permanent-exile",
            ),
        )


@dataclass(frozen=True, slots=True)
class DealFixedDamageSetIntent:
    actor: str
    source_ref: str
    amount: int
    spec: FixedDamageSetSpec
    reason: str
    replacement_selections: tuple[str | FrozenMap, ...] = ()
    replacement_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            type(value) is not str or not value
            for value in (self.actor, self.source_ref, self.reason)
        ):
            raise ValueError(
                "Fixed damage-set intents require actor, source, and reason"
            )
        if type(self.amount) is not int or self.amount <= 0:
            raise ValueError(
                "Fixed damage-set intent amount must be a positive integer"
            )
        if not isinstance(self.spec, FixedDamageSetSpec):
            raise ValueError(
                "Fixed damage-set intents require a typed recipient set"
            )
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                self.replacement_selections,
                family="Fixed damage-set",
            ),
        )
        event_ids = tuple(self.replacement_event_ids)
        if any(type(value) is not str or not value for value in event_ids):
            raise ValueError(
                "Fixed damage-set replacement event identities are invalid"
            )
        if len(event_ids) != len(set(event_ids)):
            raise ValueError(
                "Fixed damage-set replacement event identities must be unique"
            )
        object.__setattr__(self, "replacement_event_ids", event_ids)


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
    | DestroyPermanentIntent
    | DestroyPermanentSetIntent
    | ReturnPermanentToOwnerHandIntent
    | ExilePermanentIntent
    | DealFixedDamageSetIntent
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
