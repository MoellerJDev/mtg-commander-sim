from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable, Mapping


class ReplacementEffectError(ValueError):
    pass


class ReplacementClass(IntEnum):
    SELF_REPLACEMENT = 1
    ENTERS_CONTROL = 2
    ENTERS_COPY = 3
    ENTERS_BACK_FACE = 4
    OTHER = 5


@dataclass(frozen=True, slots=True)
class ReplaceableEvent:
    event_id: str
    kind: str
    affected_player: str
    payload: Mapping[str, Any]
    applied_effects: tuple[str, ...] = ()

    def with_payload(
        self,
        payload: Mapping[str, Any],
        *,
        applied_effect: str,
    ) -> "ReplaceableEvent":
        return ReplaceableEvent(
            event_id=self.event_id,
            kind=self.kind,
            affected_player=self.affected_player,
            payload=dict(payload),
            applied_effects=(
                *self.applied_effects,
                applied_effect,
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

    def __post_init__(self) -> None:
        if not self.effect_id or not self.source_id:
            raise ReplacementEffectError(
                "Replacement effects require stable IDs"
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


@dataclass(frozen=True, slots=True)
class ReplacementChoice:
    event: ReplaceableEvent
    chooser: str
    options: tuple[str, ...]
    optional_options: tuple[str, ...]
    replacement_class: ReplacementClass


def _condition_matches(
    conditions: Mapping[str, Any],
    event: ReplaceableEvent,
) -> bool:
    for field, expected in conditions.items():
        actual = (
            event.kind
            if field == "kind"
            else event.affected_player
            if field == "affected_player"
            else event.payload.get(field)
        )
        if isinstance(expected, Mapping):
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
            continue
        if actual != expected:
            return False
    return True


def replacement_choice(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
) -> ReplacementChoice | None:
    applicable = [
        effect
        for effect in effects
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
        chooser=event.affected_player,
        options=tuple(effect.effect_id for effect in options),
        optional_options=tuple(
            effect.effect_id for effect in options if effect.optional
        ),
        replacement_class=selected_class,
    )


def apply_replacement(
    choice: ReplacementChoice,
    effects: Iterable[ReplacementEffect],
    selected_effect_id: str | None,
) -> ReplaceableEvent:
    by_id = {effect.effect_id: effect for effect in effects}
    if selected_effect_id is None:
        if not choice.options or any(
            option not in choice.optional_options
            for option in choice.options
        ):
            raise ReplacementEffectError(
                "A mandatory replacement effect must be chosen"
            )
        return ReplaceableEvent(
            event_id=choice.event.event_id,
            kind=choice.event.kind,
            affected_player=choice.event.affected_player,
            payload=dict(choice.event.payload),
            applied_effects=(
                *choice.event.applied_effects,
                *choice.options,
            ),
        )
    if selected_effect_id not in choice.options:
        raise ReplacementEffectError(
            "Selected replacement is not currently applicable"
        )
    effect = by_id[selected_effect_id]
    payload = dict(choice.event.payload)
    for operation in effect.operations:
        op = str(operation.get("op") or "")
        if op == "set":
            field = str(operation.get("field") or "")
            if not field:
                raise ReplacementEffectError(
                    "Replacement set operation requires a field"
                )
            payload[field] = operation.get("value")
        elif op == "prevent":
            available = int(payload.get("amount", 0))
            requested = int(
                operation.get("amount", available)
            )
            amount = min(available, requested)
            payload["amount"] = max(
                0, available - amount
            )
            payload["prevented"] = (
                int(payload.get("prevented", 0)) + amount
            )
        elif op == "multiply":
            field = str(operation.get("field") or "amount")
            payload[field] = int(payload.get(field, 0)) * int(
                operation.get("factor", 1)
            )
        elif op == "add":
            field = str(operation.get("field") or "amount")
            payload[field] = int(payload.get(field, 0)) + int(
                operation.get("amount", 0)
            )
        else:
            raise ReplacementEffectError(
                f"Unsupported replacement operation {op!r}"
            )
    return choice.event.with_payload(
        payload,
        applied_effect=effect.effect_id,
    )


def resolve_replacements(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
    *,
    selections: Iterable[str | None],
) -> ReplaceableEvent:
    """Resolve a predetermined, auditable choice sequence.

    The engine-facing form returns a choice whenever multiple effects apply;
    replay supplies the same ordered selections and can therefore verify the
    exact modified event.
    """

    all_effects = tuple(effects)
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
