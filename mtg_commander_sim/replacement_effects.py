from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable, Mapping, Sequence


class ReplacementEffectError(ValueError):
    pass


def _sequence(value: Any, *, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReplacementEffectError(
            f"Replacement {field_name} must be an array"
        )
    return value


def _mapping_sequence(
    value: Any, *, field_name: str
) -> tuple[Mapping[str, Any], ...]:
    items = _sequence(value, field_name=field_name)
    if any(not isinstance(item, Mapping) for item in items):
        raise ReplacementEffectError(
            f"Replacement {field_name} must contain only objects"
        )
    return tuple(items)


def _string_sequence(
    value: Any, *, field_name: str
) -> tuple[str, ...]:
    items = _sequence(value, field_name=field_name)
    if any(not isinstance(item, str) or not item for item in items):
        raise ReplacementEffectError(
            f"Replacement {field_name} must contain nonempty strings"
        )
    return tuple(items)


class ReplacementClass(IntEnum):
    SELF_REPLACEMENT = 1
    ENTERS_CONTROL = 2
    ENTERS_COPY = 3
    ENTERS_BACK_FACE = 4
    OTHER = 5


@dataclass(frozen=True, slots=True)
class AffectedObject:
    """Authoritative controller/owner facts used by CR 616.1.

    A permanent's controller chooses the replacement order.  An object without
    a controller uses its owner.  These facts are captured before replacement
    selection so replay never has to infer them from later mutable state.
    """

    object_id: str
    owner: str
    controller: str | None = None

    def __post_init__(self) -> None:
        if not self.object_id or not self.owner:
            raise ReplacementEffectError(
                "An affected object requires stable object and owner IDs"
            )

    @property
    def chooser(self) -> str:
        return self.controller or self.owner

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "owner": self.owner,
            "controller": self.controller,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AffectedObject":
        return cls(
            object_id=str(value.get("object_id") or ""),
            owner=str(value.get("owner") or ""),
            controller=(
                str(value["controller"])
                if value.get("controller") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class EntryReplacementScope:
    """Objects unavailable to as-enters zone-changing choices.

    The scope is immutable so each chosen replacement records the precise CR
    614.13 reservation state.  ``entering_from_library`` also provides the
    filtered library view required by CR 614.13c without mutating or exposing
    the authoritative library order.
    """

    entering_objects: tuple[str, ...]
    entering_from_library: tuple[str, ...] = ()
    reserved_zone_changes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, values in (
            ("entering objects", self.entering_objects),
            ("library entrants", self.entering_from_library),
            ("reserved zone changes", self.reserved_zone_changes),
        ):
            if any(not value for value in values) or len(values) != len(
                set(values)
            ):
                raise ReplacementEffectError(
                    f"Entry replacement {label} must be unique stable IDs"
                )
        if not set(self.entering_from_library).issubset(
            self.entering_objects
        ):
            raise ReplacementEffectError(
                "Library entrants must also be entering objects"
            )
        if set(self.reserved_zone_changes).intersection(
            self.entering_objects
        ):
            raise ReplacementEffectError(
                "Entering objects cannot be reserved for another zone change"
            )

    def eligible_zone_choices(
        self, candidates: Iterable[str]
    ) -> tuple[str, ...]:
        unavailable = {
            *self.entering_objects,
            *self.reserved_zone_changes,
        }
        return tuple(
            value for value in candidates if value not in unavailable
        )

    def reserve_zone_changes(
        self, object_ids: Iterable[str]
    ) -> "EntryReplacementScope":
        selected = tuple(object_ids)
        if any(not value for value in selected) or len(selected) != len(
            set(selected)
        ):
            raise ReplacementEffectError(
                "Entry replacement zone-change choices must be unique IDs"
            )
        eligible = set(self.eligible_zone_choices(selected))
        invalid = [value for value in selected if value not in eligible]
        if invalid:
            raise ReplacementEffectError(
                "Entry replacement object(s) are not eligible for another "
                "zone change: " + ", ".join(invalid)
            )
        return EntryReplacementScope(
            entering_objects=self.entering_objects,
            entering_from_library=self.entering_from_library,
            reserved_zone_changes=(
                *self.reserved_zone_changes,
                *selected,
            ),
        )

    def library_order_for_replacement(
        self, library_order: Iterable[str]
    ) -> tuple[str, ...]:
        entering = set(self.entering_from_library)
        return tuple(
            object_id
            for object_id in library_order
            if object_id not in entering
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entering_objects": list(self.entering_objects),
            "entering_from_library": list(self.entering_from_library),
            "reserved_zone_changes": list(self.reserved_zone_changes),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "EntryReplacementScope":
        return cls(
            entering_objects=_string_sequence(
                value.get("entering_objects", ()),
                field_name="entering_objects",
            ),
            entering_from_library=_string_sequence(
                value.get("entering_from_library", ()),
                field_name="entering_from_library",
            ),
            reserved_zone_changes=_string_sequence(
                value.get("reserved_zone_changes", ()),
                field_name="reserved_zone_changes",
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplaceableEvent:
    event_id: str
    kind: str
    affected_player: str | None
    payload: Mapping[str, Any]
    applied_effects: tuple[str, ...] = ()
    affected_object: AffectedObject | None = None
    children: tuple["ReplaceableEvent", ...] = ()
    entry_scope: EntryReplacementScope | None = None

    def __post_init__(self) -> None:
        if not self.event_id or not self.kind:
            raise ReplacementEffectError(
                "Replaceable events require stable IDs and kinds"
            )
        if (self.affected_player is None) == (self.affected_object is None):
            raise ReplacementEffectError(
                "A replaceable event requires exactly one affected subject"
            )
        if self.affected_player == "":
            raise ReplacementEffectError(
                "An affected player must have a stable seat ID"
            )
        if len(self.applied_effects) != len(set(self.applied_effects)):
            raise ReplacementEffectError(
                "A replacement effect cannot be journaled twice on one event"
            )
        child_ids = [child.event_id for child in self.children]
        if len(child_ids) != len(set(child_ids)):
            raise ReplacementEffectError(
                "Nested replaceable event IDs must be unique"
            )

    @property
    def chooser(self) -> str:
        if self.affected_player is not None:
            return self.affected_player
        assert self.affected_object is not None
        return self.affected_object.chooser

    def with_payload(
        self,
        payload: Mapping[str, Any],
        *,
        applied_effect: str,
        children: Sequence["ReplaceableEvent"] | None = None,
        entry_scope: EntryReplacementScope | None = None,
    ) -> "ReplaceableEvent":
        return ReplaceableEvent(
            event_id=self.event_id,
            kind=self.kind,
            affected_player=self.affected_player,
            payload=copy.deepcopy(dict(payload)),
            applied_effects=(
                *self.applied_effects,
                applied_effect,
            ),
            affected_object=self.affected_object,
            children=tuple(self.children if children is None else children),
            entry_scope=(
                self.entry_scope if entry_scope is None else entry_scope
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "affected_player": self.affected_player,
            "affected_object": (
                self.affected_object.to_dict()
                if self.affected_object is not None
                else None
            ),
            "payload": copy.deepcopy(dict(self.payload)),
            "applied_effects": list(self.applied_effects),
            "children": [child.to_dict() for child in self.children],
            "entry_scope": (
                self.entry_scope.to_dict()
                if self.entry_scope is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReplaceableEvent":
        affected_object = value.get("affected_object")
        entry_scope = value.get("entry_scope")
        if affected_object is not None and not isinstance(
            affected_object, Mapping
        ):
            raise ReplacementEffectError(
                "Replacement affected_object must be an object or null"
            )
        if entry_scope is not None and not isinstance(entry_scope, Mapping):
            raise ReplacementEffectError(
                "Replacement entry_scope must be an object or null"
            )
        payload = value.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise ReplacementEffectError(
                "Replacement event payload must be an object"
            )
        return cls(
            event_id=str(value.get("event_id") or ""),
            kind=str(value.get("kind") or ""),
            affected_player=(
                str(value["affected_player"])
                if value.get("affected_player") is not None
                else None
            ),
            affected_object=(
                AffectedObject.from_dict(affected_object)
                if isinstance(affected_object, Mapping)
                else None
            ),
            payload=copy.deepcopy(dict(payload)),
            applied_effects=_string_sequence(
                value.get("applied_effects", ()),
                field_name="applied_effects",
            ),
            children=tuple(
                cls.from_dict(child)
                for child in _mapping_sequence(
                    value.get("children", ()),
                    field_name="event children",
                )
            ),
            entry_scope=(
                EntryReplacementScope.from_dict(entry_scope)
                if isinstance(entry_scope, Mapping)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplacementEffect:
    effect_id: str
    source_id: str
    event_kind: str
    replacement_class: ReplacementClass
    conditions: Mapping[str, Any] = field(default_factory=dict)
    operations: tuple[Mapping[str, Any], ...] = ()
    optional: bool = False
    chooser: str = "affected_player"
    label: str = ""

    def __post_init__(self) -> None:
        if not self.effect_id or not self.source_id:
            raise ReplacementEffectError(
                "Replacement effects require stable IDs"
            )
        if self.effect_id.startswith("decline:"):
            raise ReplacementEffectError(
                "Replacement effect IDs cannot use the decline namespace"
            )
        if not self.event_kind:
            raise ReplacementEffectError(
                "Replacement effects require an event kind"
            )
        if not self.operations:
            raise ReplacementEffectError(
                "Replacement effects require operations"
            )
        if self.chooser != "affected_player":
            raise ReplacementEffectError(
                "Only affected-player/object-controller choice is compiled"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "source_id": self.source_id,
            "event_kind": self.event_kind,
            "replacement_class": int(self.replacement_class),
            "conditions": copy.deepcopy(dict(self.conditions)),
            "operations": [
                copy.deepcopy(dict(operation))
                for operation in self.operations
            ],
            "optional": self.optional,
            "chooser": self.chooser,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReplacementEffect":
        conditions = value.get("conditions") or {}
        if not isinstance(conditions, Mapping):
            raise ReplacementEffectError(
                "Replacement effect conditions must be an object"
            )
        return cls(
            effect_id=str(value.get("effect_id") or ""),
            source_id=str(value.get("source_id") or ""),
            event_kind=str(value.get("event_kind") or ""),
            replacement_class=ReplacementClass(
                int(value.get("replacement_class", ReplacementClass.OTHER))
            ),
            conditions=copy.deepcopy(dict(conditions)),
            operations=tuple(
                copy.deepcopy(dict(operation))
                for operation in _mapping_sequence(
                    value.get("operations", ()),
                    field_name="effect operations",
                )
            ),
            optional=bool(value.get("optional", False)),
            chooser=str(value.get("chooser") or "affected_player"),
            label=str(value.get("label") or ""),
        )


@dataclass(frozen=True, slots=True)
class ReplacementChoice:
    event: ReplaceableEvent
    chooser: str
    options: tuple[str, ...]
    optional_options: tuple[str, ...]
    replacement_class: ReplacementClass

    @property
    def legal_selections(self) -> tuple[str, ...]:
        values: list[str] = []
        for option in self.options:
            values.append(option)
            if option in self.optional_options:
                values.append(f"decline:{option}")
        return tuple(values)


@dataclass(frozen=True, slots=True)
class ReplacementTreeChoice:
    path: tuple[int, ...]
    choice: ReplacementChoice


@dataclass(frozen=True, slots=True)
class ReplacementSelection:
    event_id: str
    path: tuple[int, ...]
    chooser: str
    effect_id: str | None

    def __post_init__(self) -> None:
        if not self.event_id or not self.chooser:
            raise ReplacementEffectError(
                "Replacement selections require event and chooser IDs"
            )
        if any(index < 0 for index in self.path):
            raise ReplacementEffectError(
                "Replacement selection paths cannot contain negative indexes"
            )
        if self.effect_id == "":
            raise ReplacementEffectError(
                "Replacement selection effect IDs cannot be empty"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "path": list(self.path),
            "chooser": self.chooser,
            "effect_id": self.effect_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReplacementSelection":
        return cls(
            event_id=str(value.get("event_id") or ""),
            path=tuple(
                int(item)
                for item in _sequence(
                    value.get("path", ()), field_name="selection path"
                )
            ),
            chooser=str(value.get("chooser") or ""),
            effect_id=(
                str(value["effect_id"])
                if value.get("effect_id") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplacementEventBatch:
    """A replayable set of simultaneous events resolved in APNAP order."""

    batch_id: str
    events: tuple[ReplaceableEvent, ...]
    apnap_order: tuple[str, ...]
    journal: tuple[ReplacementSelection, ...] = ()

    def __post_init__(self) -> None:
        if not self.batch_id or not self.events:
            raise ReplacementEffectError(
                "A replacement batch requires an ID and at least one event"
            )
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ReplacementEffectError(
                "Replacement batch event IDs must be unique"
            )
        if not self.apnap_order or len(self.apnap_order) != len(
            set(self.apnap_order)
        ):
            raise ReplacementEffectError(
                "Replacement batch APNAP order must contain unique seats"
            )
        unknown = sorted(
            {
                event.chooser
                for event in self.events
                if event.chooser not in self.apnap_order
            }
        )
        if unknown:
            raise ReplacementEffectError(
                "Affected chooser(s) are missing from APNAP order: "
                + ", ".join(unknown)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "events": [event.to_dict() for event in self.events],
            "apnap_order": list(self.apnap_order),
            "journal": [selection.to_dict() for selection in self.journal],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReplacementEventBatch":
        return cls(
            batch_id=str(value.get("batch_id") or ""),
            events=tuple(
                ReplaceableEvent.from_dict(event)
                for event in _mapping_sequence(
                    value.get("events", ()), field_name="batch events"
                )
            ),
            apnap_order=_string_sequence(
                value.get("apnap_order", ()), field_name="APNAP order"
            ),
            journal=tuple(
                ReplacementSelection.from_dict(selection)
                for selection in _mapping_sequence(
                    value.get("journal", ()), field_name="batch journal"
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplacementBatchChoice:
    batch_id: str
    event_index: int
    event_id: str
    tree_choice: ReplacementTreeChoice
    prior_public_choices: tuple[ReplacementSelection, ...]

    @property
    def choice(self) -> ReplacementChoice:
        return self.tree_choice.choice

    @property
    def path(self) -> tuple[int, ...]:
        return self.tree_choice.path


@dataclass(frozen=True, slots=True)
class ReplacementBatchProgress:
    batch: ReplacementEventBatch
    pending: ReplacementBatchChoice | None


class ReplacementChoiceRequired(ReplacementEffectError):
    """Raised only at an engine suspension boundary before event commit."""

    def __init__(
        self,
        *,
        batch: ReplacementEventBatch,
        effects: Sequence[ReplacementEffect],
        pending: ReplacementBatchChoice,
    ) -> None:
        super().__init__(
            f"{pending.choice.chooser} must choose a replacement effect"
        )
        self.batch = batch
        # Applicable replacements are an unordered rules set.  Canonicalize
        # the suspension payload so a checkpoint restored from sorted JSON
        # produces the same decision and authoritative hash as the live run.
        self.effects = _canonical_effects(effects)
        self.pending = pending


def _canonical_effects(
    effects: Iterable[ReplacementEffect],
) -> tuple[ReplacementEffect, ...]:
    values = tuple(effects)
    effect_ids = [effect.effect_id for effect in values]
    if len(effect_ids) != len(set(effect_ids)):
        raise ReplacementEffectError(
            "Replacement effect IDs must be unique within an event boundary"
        )
    return tuple(sorted(values, key=lambda effect: effect.effect_id))


def _event_field(event: ReplaceableEvent, field_name: str) -> Any:
    if field_name == "kind":
        return event.kind
    if field_name == "affected_player":
        return event.affected_player
    if field_name == "chooser":
        return event.chooser
    return event.payload.get(field_name)


def _condition_matches(
    conditions: Mapping[str, Any],
    event: ReplaceableEvent,
) -> bool:
    for field_name, expected in conditions.items():
        actual = _event_field(event, field_name)
        if isinstance(expected, Mapping):
            supported_predicates = {
                "in",
                "not_in",
                "eq",
                "contains",
                "contains_all",
            }
            unsupported = sorted(
                str(predicate)
                for predicate in expected
                if predicate not in supported_predicates
            )
            if unsupported:
                raise ReplacementEffectError(
                    "Unsupported replacement condition predicate(s): "
                    + ", ".join(unsupported)
                )
            if not expected:
                raise ReplacementEffectError(
                    "Replacement condition predicates cannot be empty"
                )
            if "in" in expected and actual not in expected["in"]:
                return False
            if "not_in" in expected and actual in expected["not_in"]:
                return False
            if "eq" in expected and actual != expected["eq"]:
                return False
            if "contains" in expected and expected["contains"] not in (
                actual or ()
            ):
                return False
            if "contains_all" in expected and not set(
                expected["contains_all"]
            ).issubset(set(actual or ())):
                return False
            continue
        if actual != expected:
            return False
    return True


def replacement_choice(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
) -> ReplacementChoice | None:
    all_effects = _canonical_effects(effects)
    applicable = [
        effect
        for effect in all_effects
        if effect.event_kind == event.kind
        and effect.effect_id not in event.applied_effects
        and _condition_matches(effect.conditions, event)
    ]
    if not applicable:
        return None
    selected_class = min(
        effect.replacement_class for effect in applicable
    )
    options = sorted(
        (
            effect
            for effect in applicable
            if effect.replacement_class == selected_class
        ),
        key=lambda effect: effect.effect_id,
    )
    return ReplacementChoice(
        event=event,
        chooser=event.chooser,
        options=tuple(effect.effect_id for effect in options),
        optional_options=tuple(
            effect.effect_id for effect in options if effect.optional
        ),
        replacement_class=selected_class,
    )


def _nested_event_from_mapping(
    parent: ReplaceableEvent,
    value: Mapping[str, Any],
    *,
    suffix: str,
) -> ReplaceableEvent:
    allowed = {
        "event_id",
        "kind",
        "affected_player",
        "affected_object",
        "payload",
        "applied_effects",
        "children",
        "entry_scope",
    }
    unknown = sorted(str(field) for field in set(value) - allowed)
    if unknown:
        raise ReplacementEffectError(
            "Nested replacement event has unknown field(s): "
            + ", ".join(unknown)
        )
    affected_object_value = value.get("affected_object")
    if affected_object_value is not None and not isinstance(
        affected_object_value, Mapping
    ):
        raise ReplacementEffectError(
            "Nested affected_object must be an object or null"
        )
    has_player = "affected_player" in value
    has_object = isinstance(affected_object_value, Mapping)
    if has_player and has_object:
        raise ReplacementEffectError(
            "A nested event cannot specify both affected subjects"
        )
    affected_player: str | None
    affected_object: AffectedObject | None
    if has_player:
        affected_player = (
            str(value["affected_player"])
            if value.get("affected_player") is not None
            else None
        )
        affected_object = None
    elif has_object:
        affected_player = None
        affected_object = AffectedObject.from_dict(affected_object_value)
    else:
        affected_player = parent.affected_player
        affected_object = parent.affected_object
    event_id = str(value.get("event_id") or f"{parent.event_id}/{suffix}")
    payload = value.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise ReplacementEffectError(
            "Nested replacement event payload must be an object"
        )
    event = ReplaceableEvent(
        event_id=event_id,
        kind=str(value.get("kind") or ""),
        affected_player=affected_player,
        affected_object=affected_object,
        payload=copy.deepcopy(dict(payload)),
        applied_effects=_string_sequence(
            value.get("applied_effects", ()),
            field_name="nested applied_effects",
        ),
        entry_scope=(
            EntryReplacementScope.from_dict(value["entry_scope"])
            if isinstance(value.get("entry_scope"), Mapping)
            else None
        ),
    )
    children = tuple(
        _nested_event_from_mapping(
            event,
            child,
            suffix=str(index),
        )
        for index, child in enumerate(
            _mapping_sequence(
                value.get("children", ()),
                field_name="nested event children",
            )
        )
    )
    if not children:
        return event
    return ReplaceableEvent(
        event_id=event.event_id,
        kind=event.kind,
        affected_player=event.affected_player,
        affected_object=event.affected_object,
        payload=event.payload,
        applied_effects=event.applied_effects,
        children=children,
        entry_scope=event.entry_scope,
    )


def apply_replacement(
    choice: ReplacementChoice,
    effects: Iterable[ReplacementEffect],
    selected_effect_id: str | None,
) -> ReplaceableEvent:
    all_effects = _canonical_effects(effects)
    by_id = {effect.effect_id: effect for effect in all_effects}
    selection = selected_effect_id
    if selection is None:
        if len(choice.options) != 1 or choice.options[0] not in (
            choice.optional_options
        ):
            raise ReplacementEffectError(
                "A decline must identify one currently optional replacement"
            )
        selection = f"decline:{choice.options[0]}"

    if selection.startswith("decline:"):
        declined = selection.removeprefix("decline:")
        if (
            declined not in choice.options
            or declined not in choice.optional_options
        ):
            raise ReplacementEffectError(
                "Selected replacement cannot currently be declined"
            )
        return choice.event.with_payload(
            choice.event.payload,
            applied_effect=declined,
        )

    if selection not in choice.options:
        raise ReplacementEffectError(
            "Selected replacement is not currently applicable"
        )
    effect = by_id[selection]
    payload = copy.deepcopy(dict(choice.event.payload))
    children = list(choice.event.children)
    entry_scope = choice.event.entry_scope
    for operation in effect.operations:
        op = str(operation.get("op") or "")
        if op == "set":
            field_name = str(operation.get("field") or "")
            if not field_name:
                raise ReplacementEffectError(
                    "Replacement set operation requires a field"
                )
            payload[field_name] = copy.deepcopy(operation.get("value"))
        elif op == "prevent":
            available = int(payload.get("amount", 0))
            requested = int(operation.get("amount", available))
            if available < 0 or requested < 0:
                raise ReplacementEffectError(
                    "Damage and prevention amounts cannot be negative"
                )
            amount = (
                0
                if bool(payload.get("unpreventable"))
                else min(available, requested)
            )
            payload["amount"] = available - amount
            payload["prevented"] = (
                int(payload.get("prevented", 0)) + amount
            )
        elif op == "multiply":
            field_name = str(operation.get("field") or "amount")
            payload[field_name] = int(payload.get(field_name, 0)) * int(
                operation.get("factor", 1)
            )
        elif op == "add":
            field_name = str(operation.get("field") or "amount")
            payload[field_name] = int(payload.get(field_name, 0)) + int(
                operation.get("amount", 0)
            )
        elif op == "append":
            field_name = str(operation.get("field") or "")
            values = operation.get("values")
            if not field_name or not isinstance(values, Sequence) or isinstance(
                values, (str, bytes)
            ):
                raise ReplacementEffectError(
                    "Replacement append operation requires a field and values"
                )
            current = payload.get(field_name, [])
            if not isinstance(current, Sequence) or isinstance(
                current, (str, bytes)
            ):
                raise ReplacementEffectError(
                    "Replacement append destination must be a sequence"
                )
            payload[field_name] = [
                *copy.deepcopy(list(current)),
                *copy.deepcopy(list(values)),
            ]
        elif op == "union":
            field_name = str(operation.get("field") or "")
            values = operation.get("values")
            if not field_name or not isinstance(values, Sequence) or isinstance(
                values, (str, bytes)
            ):
                raise ReplacementEffectError(
                    "Replacement union operation requires a field and values"
                )
            payload[field_name] = sorted(
                {
                    *list(payload.get(field_name, [])),
                    *copy.deepcopy(list(values)),
                },
                key=str,
            )
        elif op == "nested_event":
            nested = operation.get("event")
            if not isinstance(nested, Mapping):
                raise ReplacementEffectError(
                    "Nested replacement operation requires an event object"
                )
            children.append(
                _nested_event_from_mapping(
                    choice.event,
                    nested,
                    suffix=str(len(children)),
                )
            )
        elif op == "reserve_zone_change":
            if entry_scope is None:
                raise ReplacementEffectError(
                    "Zone-change reservation requires an entry replacement scope"
                )
            values = operation.get("objects")
            if values is None and operation.get("from_field"):
                values = payload.get(str(operation["from_field"]), ())
            if not isinstance(values, Sequence) or isinstance(
                values, (str, bytes)
            ):
                raise ReplacementEffectError(
                    "Zone-change reservation requires object IDs"
                )
            entry_scope = entry_scope.reserve_zone_changes(
                str(value) for value in values
            )
        else:
            raise ReplacementEffectError(
                f"Unsupported replacement operation {op!r}"
            )
    return choice.event.with_payload(
        payload,
        applied_effect=effect.effect_id,
        children=children,
        entry_scope=entry_scope,
    )


def resolve_replacements(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
    *,
    selections: Iterable[str | None],
) -> ReplaceableEvent:
    """Resolve one event from an exact, replayable selection sequence."""

    all_effects = _canonical_effects(effects)
    iterator = iter(selections)
    current = event
    while choice := replacement_choice(current, all_effects):
        try:
            selected = next(iterator)
        except StopIteration as exc:
            raise ReplacementEffectError(
                "Replacement choice sequence ended early"
            ) from exc
        current = apply_replacement(choice, all_effects, selected)
    try:
        next(iterator)
    except StopIteration:
        return current
    raise ReplacementEffectError(
        "Replacement choice sequence contains unused choices"
    )


def replacement_tree_choice(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
) -> ReplacementTreeChoice | None:
    """Return the first current choice, keeping children suspended.

    A parent event is always exhausted before traversal enters a child.  That
    preorder is the explicit CR 616.1g boundary: a replacement for a contained
    event cannot be selected before replacements for the containing event.
    """

    all_effects = _canonical_effects(effects)

    def visit(
        current: ReplaceableEvent, path: tuple[int, ...]
    ) -> ReplacementTreeChoice | None:
        choice = replacement_choice(current, all_effects)
        if choice is not None:
            return ReplacementTreeChoice(path=path, choice=choice)
        for index, child in enumerate(current.children):
            nested = visit(child, (*path, index))
            if nested is not None:
                return nested
        return None

    return visit(event, ())


def _replace_event_at_path(
    event: ReplaceableEvent,
    path: tuple[int, ...],
    replacement: ReplaceableEvent,
) -> ReplaceableEvent:
    if not path:
        return replacement
    index = path[0]
    if index < 0 or index >= len(event.children):
        raise ReplacementEffectError(
            "Replacement event path is no longer valid"
        )
    children = list(event.children)
    children[index] = _replace_event_at_path(
        children[index], path[1:], replacement
    )
    return ReplaceableEvent(
        event_id=event.event_id,
        kind=event.kind,
        affected_player=event.affected_player,
        affected_object=event.affected_object,
        payload=event.payload,
        applied_effects=event.applied_effects,
        children=tuple(children),
        entry_scope=event.entry_scope,
    )


def apply_tree_replacement(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
    pending: ReplacementTreeChoice,
    selected_effect_id: str | None,
) -> ReplaceableEvent:
    all_effects = _canonical_effects(effects)
    current = replacement_tree_choice(event, all_effects)
    if current is None or current != pending:
        raise ReplacementEffectError(
            "Replacement tree choice is stale or out of order"
        )
    changed = apply_replacement(
        pending.choice,
        all_effects,
        selected_effect_id,
    )
    return _replace_event_at_path(event, pending.path, changed)


def next_batch_replacement_choice(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
) -> ReplacementBatchChoice | None:
    all_effects = _canonical_effects(effects)
    order = {seat: index for index, seat in enumerate(batch.apnap_order)}
    candidates: list[tuple[int, str, int, ReplacementTreeChoice]] = []
    for event_index, event in enumerate(batch.events):
        pending = replacement_tree_choice(event, all_effects)
        if pending is None:
            continue
        candidates.append(
            (
                order[pending.choice.chooser],
                event.event_id,
                event_index,
                pending,
            )
        )
    if not candidates:
        return None
    _, event_id, event_index, pending = min(
        candidates,
        key=lambda value: (
            value[0],
            value[1],
            value[3].path,
            value[2],
        ),
    )
    return ReplacementBatchChoice(
        batch_id=batch.batch_id,
        event_index=event_index,
        event_id=event_id,
        tree_choice=pending,
        prior_public_choices=batch.journal,
    )


def apply_batch_replacement(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
    pending: ReplacementBatchChoice,
    selected_effect_id: str | None,
) -> ReplacementEventBatch:
    all_effects = _canonical_effects(effects)
    current = next_batch_replacement_choice(batch, all_effects)
    if current is None or current != pending:
        raise ReplacementEffectError(
            "Replacement batch choice is stale or violates APNAP order"
        )
    events = list(batch.events)
    events[pending.event_index] = apply_tree_replacement(
        events[pending.event_index],
        all_effects,
        pending.tree_choice,
        selected_effect_id,
    )
    return ReplacementEventBatch(
        batch_id=batch.batch_id,
        events=tuple(events),
        apnap_order=batch.apnap_order,
        journal=(
            *batch.journal,
            ReplacementSelection(
                event_id=pending.event_id,
                path=pending.path,
                chooser=pending.choice.chooser,
                effect_id=selected_effect_id,
            ),
        ),
    )


def resolve_replacement_batch(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
    *,
    selections: Iterable[ReplacementSelection],
) -> ReplacementEventBatch:
    all_effects = _canonical_effects(effects)
    current = batch
    for selection in selections:
        pending = next_batch_replacement_choice(current, all_effects)
        if pending is None:
            raise ReplacementEffectError(
                "Replacement replay contains unused selections"
            )
        if (
            selection.event_id != pending.event_id
            or selection.path != pending.path
            or selection.chooser != pending.choice.chooser
        ):
            raise ReplacementEffectError(
                "Replacement replay selection path or chooser diverged"
            )
        current = apply_batch_replacement(
            current,
            all_effects,
            pending,
            selection.effect_id,
        )
    if next_batch_replacement_choice(current, all_effects) is not None:
        raise ReplacementEffectError(
            "Replacement replay selection sequence ended early"
        )
    return current


def advance_replacement_batch(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
    *,
    selections: Iterable[str | None] = (),
) -> ReplacementBatchProgress:
    """Apply supplied choices and every forced singleton replacement.

    A single mandatory option is not a player choice.  Multiple options or an
    optional singleton produce a pending request before the event commits.
    This is the engine suspension boundary; replay still records the full event
    path and chooser in the batch journal.
    """

    all_effects = _canonical_effects(effects)
    supplied = iter(selections)
    current = batch
    while pending := next_batch_replacement_choice(current, all_effects):
        if (
            len(pending.choice.options) == 1
            and not pending.choice.optional_options
        ):
            selected = pending.choice.options[0]
        else:
            try:
                selected = next(supplied)
            except StopIteration:
                return ReplacementBatchProgress(
                    batch=current,
                    pending=pending,
                )
        current = apply_batch_replacement(
            current,
            all_effects,
            pending,
            selected,
        )
    try:
        next(supplied)
    except StopIteration:
        return ReplacementBatchProgress(batch=current, pending=None)
    raise ReplacementEffectError(
        "Replacement selection sequence contains unused choices"
    )


def replacement_choice_payload(
    pending: ReplacementBatchChoice,
    effects: Iterable[ReplacementEffect],
) -> dict[str, Any]:
    """Build a seat-safe choice packet without authoritative event payload."""

    all_effects = _canonical_effects(effects)
    by_id = {effect.effect_id: effect for effect in all_effects}
    options: list[dict[str, Any]] = []
    for value in pending.choice.legal_selections:
        declined = value.startswith("decline:")
        effect_id = value.removeprefix("decline:") if declined else value
        effect = by_id[effect_id]
        label = effect.label or effect.effect_id
        options.append(
            {
                "id": value,
                "label": f"Decline {label}" if declined else label,
                "source": effect.source_id,
                "decline": declined,
            }
        )
    legal_values = [option["id"] for option in options]
    return {
        "chooser": pending.choice.chooser,
        "prompt": "Choose the next replacement or prevention effect.",
        "options": options,
        "legal_actions": [
            {
                "id": "choose",
                "action": "choose",
                "label": "Choose replacement",
                "choice_schema": {
                    "replacement": {
                        "legal_values": legal_values,
                    }
                },
            }
        ],
    }
