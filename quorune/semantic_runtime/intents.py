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


_EXPLORE_LABEL = "Ex" + "plore"
_REASON_FIELD = "rea" + "son"


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
class ExploreCompletedIntent:
    actor: str
    player: str
    explorer_ref: str
    explorer_logical_object_id: str
    result: Literal[
        "empty_library",
        "land_revealed",
        "nonland_graveyard_choice",
        "nonland_top_choice",
    ]
    reason: str
    revealed_card_ref: str | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("actor", self.actor),
            ("player", self.player),
            ("explorer_ref", self.explorer_ref),
            ("explorer_logical_object_id", self.explorer_logical_object_id),
            (_REASON_FIELD, self.reason),
        ):
            if type(value) is not str or not value:
                raise ValueError(
                    f"{_EXPLORE_LABEL} {label} must be a nonempty string"
                )
        if self.revealed_card_ref is not None and (
            type(self.revealed_card_ref) is not str
            or not self.revealed_card_ref
        ):
            raise ValueError(
                "Explore revealed-card reference must be nonempty or null"
            )


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
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                tuple(self.replacement_selections),
                family="Zone move",
            ),
        )


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
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                tuple(self.replacement_selections),
                family="Counter placement",
            ),
        )


@dataclass(frozen=True, slots=True)
class PlacePlayerCountersIntent:
    actor: str
    player_ids: tuple[str, ...]
    counter_name: str
    amount: int
    reason: str
    source_ref: str | None = None
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.player_ids, (list, tuple)):
            raise ValueError(
                "Player counter intent subjects must be an ordered sequence"
            )
        players = tuple(self.player_ids)
        if type(self.counter_name) is not str:
            raise ValueError(
                "Player counter intents require actor, counter, and reason"
            )
        normalized = " ".join(self.counter_name.casefold().split())
        if any(
            type(value) is not str or not value
            for value in (self.actor, normalized, self.reason)
        ):
            raise ValueError(
                "Player counter intents require actor, counter, and reason"
            )
        if (
            not players
            or any(type(player) is not str or not player for player in players)
            or len(players) != len(set(players))
        ):
            raise ValueError(
                "Player counter intent subjects must be unique nonempty seats"
            )
        if type(self.amount) is not int or self.amount <= 0:
            raise ValueError(
                "Player counter intent amount must be a positive integer"
            )
        if self.source_ref is not None and (
            type(self.source_ref) is not str or not self.source_ref
        ):
            raise ValueError(
                "Player counter intent source must be a nonempty reference"
            )
        object.__setattr__(self, "player_ids", players)
        object.__setattr__(self, "counter_name", normalized)
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                tuple(self.replacement_selections),
                family="Player counter placement",
            ),
        )


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
class ProliferateSubject:
    subject_kind: Literal["player", "permanent"]
    subject_id: str
    ref: str
    counter_names: tuple[str, ...]
    logical_object_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.subject_kind) is not str or self.subject_kind not in {
            "player",
            "permanent",
        }:
            raise ValueError(
                "Proliferate subjects must be players or permanents"
            )
        if any(
            type(value) is not str or not value
            for value in (self.subject_id, self.ref)
        ):
            raise ValueError(
                "Proliferate subjects require stable IDs and references"
            )
        if not isinstance(self.counter_names, (list, tuple)) or any(
            type(value) is not str or not value
            for value in self.counter_names
        ):
            raise ValueError(
                "Proliferate counter names must be nonempty strings"
            )
        names = tuple(
            " ".join(value.casefold().split())
            for value in self.counter_names
        )
        if (
            not names
            or any(not value for value in names)
            or names != tuple(sorted(set(names)))
        ):
            raise ValueError(
                "Proliferate counter names must be unique canonical strings"
            )
        if self.subject_kind == "player":
            if self.subject_id != self.ref or self.logical_object_id is not None:
                raise ValueError(
                    "Player Proliferate subjects cannot carry object identity"
                )
        elif not self.logical_object_id:
            raise ValueError(
                "Permanent Proliferate subjects require logical identity"
            )
        object.__setattr__(self, "counter_names", names)


@dataclass(frozen=True, slots=True)
class ProliferateIntent:
    actor: str
    subjects: tuple[ProliferateSubject, ...]
    reason: str
    source_ref: str | None = None
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if any(
            type(value) is not str or not value
            for value in (self.actor, self.reason)
        ):
            raise ValueError(
                "Proliferate intents require an actor and reason"
            )
        if self.source_ref is not None and (
            type(self.source_ref) is not str or not self.source_ref
        ):
            raise ValueError(
                "Proliferate source references must be nonempty or null"
            )
        if any(
            not isinstance(subject, ProliferateSubject)
            for subject in self.subjects
        ):
            raise ValueError(
                "Proliferate intents require typed subject snapshots"
            )
        identities = tuple(
            (subject.subject_kind, subject.subject_id)
            for subject in self.subjects
        )
        if len(identities) != len(set(identities)):
            raise ValueError("Proliferate subject snapshots must be unique")
        object.__setattr__(
            self,
            "replacement_selections",
            _freeze_replacement_selections(
                tuple(self.replacement_selections),
                family="Proliferate",
            ),
        )

    @property
    def selections(self) -> tuple[str, ...]:
        return tuple(subject.ref for subject in self.subjects)


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
    | PlacePlayerCountersIntent
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
