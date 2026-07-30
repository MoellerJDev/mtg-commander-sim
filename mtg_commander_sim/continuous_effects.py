from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable, Mapping, Sequence


class ContinuousEffectError(ValueError):
    pass


class Layer(IntEnum):
    COPY = 1
    CONTROL = 2
    TEXT = 3
    TYPE = 4
    COLOR = 5
    ABILITY = 6
    POWER_TOUGHNESS = 7


_SUBLAYER_ORDER = {
    (Layer.COPY, "1a"): 0,
    (Layer.COPY, "1b"): 1,
    (Layer.POWER_TOUGHNESS, "7a"): 0,
    (Layer.POWER_TOUGHNESS, "7b"): 1,
    (Layer.POWER_TOUGHNESS, "7c"): 2,
    (Layer.POWER_TOUGHNESS, "7d"): 3,
}


@dataclass(frozen=True, slots=True)
class ContinuousOperation:
    op: str
    value: Any = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class ContinuousEffect:
    effect_id: str
    source_id: str
    layer: Layer
    sublayer: str
    timestamp: int
    operations: tuple[ContinuousOperation, ...]
    depends_on: tuple[str, ...] = ()
    characteristic_defining: bool = False
    duration: str = "while_source_present"
    source_present: bool = True
    applies: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.effect_id or not self.source_id:
            raise ContinuousEffectError(
                "Continuous effects require stable effect/source IDs"
            )
        if self.timestamp < 0:
            raise ContinuousEffectError(
                "Continuous effect timestamps must be nonnegative"
            )
        expected_prefix = str(int(self.layer))
        if not self.sublayer.startswith(expected_prefix):
            raise ContinuousEffectError(
                f"Sublayer {self.sublayer!r} is not in layer {self.layer}"
            )
        if not self.operations:
            raise ContinuousEffectError(
                "Continuous effects require at least one operation"
            )


@dataclass(slots=True)
class CharacteristicState:
    name: str
    controller: str | None = None
    mana_cost: str = ""
    mana_value: float = 0.0
    text: str = ""
    supertypes: set[str] = field(default_factory=set)
    card_types: set[str] = field(default_factory=set)
    subtypes: set[str] = field(default_factory=set)
    colors: set[str] = field(default_factory=set)
    abilities: list[str] = field(default_factory=list)
    power: int | None = None
    toughness: int | None = None
    copiable_values: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "controller": self.controller,
            "mana_cost": self.mana_cost,
            "mana_value": self.mana_value,
            "text": self.text,
            "supertypes": sorted(self.supertypes),
            "card_types": sorted(self.card_types),
            "subtypes": sorted(self.subtypes),
            "colors": sorted(self.colors),
            "abilities": list(self.abilities),
            "power": self.power,
            "toughness": self.toughness,
            "copiable_values": dict(self.copiable_values),
        }


@dataclass(frozen=True, slots=True)
class ContinuousEvaluation:
    characteristics: Mapping[str, Any]
    applied_effects: tuple[str, ...]
    dependency_cycles: tuple[tuple[str, ...], ...]
    inapplicable_effects: tuple[str, ...]


def _matches(
    condition: Mapping[str, Any],
    state: CharacteristicState,
    context: Mapping[str, Any],
) -> bool:
    for field_name, expected in condition.items():
        if field_name.startswith("context."):
            actual = context.get(field_name.removeprefix("context."))
        else:
            actual = getattr(state, field_name, None)
        if isinstance(expected, Mapping):
            if "contains" in expected:
                if expected["contains"] not in (actual or ()):
                    return False
                continue
            if "contains_any" in expected:
                if not set(actual or ()).intersection(
                    expected["contains_any"]
                ):
                    return False
                continue
            if "eq" in expected:
                if actual != expected["eq"]:
                    return False
                continue
            raise ContinuousEffectError(
                f"Unsupported applicability predicate for {field_name}"
            )
        if actual != expected:
            return False
    return True


def _dependency_order(
    effects: Sequence[ContinuousEffect],
) -> tuple[list[ContinuousEffect], list[tuple[str, ...]]]:
    """Order one layer/sublayer by CDA, dependency, then timestamp.

    Cyclic dependency components fall back to timestamp order, matching the
    CR rule that dependencies inside the loop do not determine their order.
    """

    by_id = {effect.effect_id: effect for effect in effects}
    remaining = set(by_id)
    ordered: list[ContinuousEffect] = []
    cycles: list[tuple[str, ...]] = []
    while remaining:
        ready = [
            by_id[effect_id]
            for effect_id in remaining
            if not (
                set(by_id[effect_id].depends_on).intersection(remaining)
            )
        ]
        if ready:
            ready.sort(
                key=lambda effect: (
                    not effect.characteristic_defining,
                    effect.timestamp,
                    effect.effect_id,
                )
            )
            for effect in ready:
                ordered.append(effect)
                remaining.remove(effect.effect_id)
            continue
        cycle = tuple(
            sorted(
                remaining,
                key=lambda effect_id: (
                    not by_id[effect_id].characteristic_defining,
                    by_id[effect_id].timestamp,
                    effect_id,
                ),
            )
        )
        cycles.append(cycle)
        ordered.extend(by_id[effect_id] for effect_id in cycle)
        remaining.clear()
    return ordered, cycles


def order_continuous_effects(
    effects: Iterable[ContinuousEffect],
) -> tuple[list[ContinuousEffect], list[tuple[str, ...]]]:
    groups: dict[tuple[int, int], list[ContinuousEffect]] = {}
    for effect in effects:
        sublayer_rank = _SUBLAYER_ORDER.get(
            (effect.layer, effect.sublayer),
            0,
        )
        groups.setdefault(
            (int(effect.layer), sublayer_rank), []
        ).append(effect)
    ordered: list[ContinuousEffect] = []
    cycles: list[tuple[str, ...]] = []
    for key in sorted(groups):
        group, group_cycles = _dependency_order(groups[key])
        ordered.extend(group)
        cycles.extend(group_cycles)
    return ordered, cycles


def _as_words(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def _apply_operation(
    state: CharacteristicState,
    operation: ContinuousOperation,
) -> None:
    op = operation.op
    value = operation.value
    if op == "copy_values":
        if not isinstance(value, Mapping):
            raise ContinuousEffectError(
                "copy_values requires an object"
            )
        for key, replacement in value.items():
            if key == "text":
                state.text = str(replacement)
            elif key in {"supertypes", "card_types", "subtypes", "colors"}:
                setattr(state, key, _as_words(replacement))
            elif key == "abilities":
                state.abilities = [str(item) for item in replacement]
            elif hasattr(state, key):
                setattr(state, key, replacement)
            else:
                raise ContinuousEffectError(
                    f"Unknown copiable field {key!r}"
                )
        return
    if op == "face_down":
        values = dict(value or {})
        state.name = str(values.get("name") or "")
        state.mana_cost = str(values.get("mana_cost") or "")
        state.mana_value = float(values.get("mana_value") or 0)
        state.text = str(values.get("text") or "")
        state.supertypes = _as_words(values.get("supertypes"))
        state.card_types = _as_words(
            values.get("card_types", ["Creature"])
        )
        state.subtypes = _as_words(values.get("subtypes"))
        state.colors = _as_words(values.get("colors"))
        state.abilities = [
            str(item) for item in values.get("abilities", [])
        ]
        state.power = int(values.get("power", 2))
        state.toughness = int(values.get("toughness", 2))
        return
    if op == "set_controller":
        state.controller = str(value)
        return
    if op == "replace_text":
        if not isinstance(value, Mapping):
            raise ContinuousEffectError(
                "replace_text requires from/to"
            )
        state.text = state.text.replace(
            str(value.get("from") or ""),
            str(value.get("to") or ""),
        )
        return
    if op in {"set_types", "add_types", "remove_types"}:
        target = (
            "card_types"
            if operation.field in {None, "card_types"}
            else str(operation.field)
        )
        if target not in {"supertypes", "card_types", "subtypes"}:
            raise ContinuousEffectError(
                f"Invalid type field {target!r}"
            )
        values = _as_words(value)
        current = getattr(state, target)
        if op == "set_types":
            setattr(state, target, values)
        elif op == "add_types":
            current.update(values)
        else:
            current.difference_update(values)
        return
    if op in {"set_colors", "add_colors", "remove_colors"}:
        values = {item.upper() for item in _as_words(value)}
        if op == "set_colors":
            state.colors = values
        elif op == "add_colors":
            state.colors.update(values)
        else:
            state.colors.difference_update(values)
        return
    if op == "add_ability":
        ability = str(value)
        if ability.casefold() not in {
            item.casefold() for item in state.abilities
        }:
            state.abilities.append(ability)
        return
    if op == "remove_ability":
        state.abilities = [
            ability
            for ability in state.abilities
            if ability.casefold() != str(value).casefold()
        ]
        return
    if op == "remove_all_abilities":
        state.abilities = []
        return
    if op == "set_power_toughness":
        if not isinstance(value, Sequence) or len(value) != 2:
            raise ContinuousEffectError(
                "set_power_toughness requires [power, toughness]"
            )
        state.power = int(value[0])
        state.toughness = int(value[1])
        return
    if op == "modify_power_toughness":
        if not isinstance(value, Sequence) or len(value) != 2:
            raise ContinuousEffectError(
                "modify_power_toughness requires [power, toughness]"
            )
        if state.power is not None:
            state.power += int(value[0])
        if state.toughness is not None:
            state.toughness += int(value[1])
        return
    if op == "switch_power_toughness":
        state.power, state.toughness = state.toughness, state.power
        return
    raise ContinuousEffectError(
        f"Unsupported continuous operation {op!r}"
    )


def evaluate_continuous_effects(
    base: CharacteristicState,
    effects: Iterable[ContinuousEffect],
    *,
    context: Mapping[str, Any] | None = None,
) -> ContinuousEvaluation:
    context = dict(context or {})
    applicable: list[ContinuousEffect] = []
    inapplicable: list[str] = []
    for effect in effects:
        if effect.duration == "while_source_present" and not (
            effect.source_present
        ):
            inapplicable.append(effect.effect_id)
            continue
        if not _matches(effect.applies, base, context):
            inapplicable.append(effect.effect_id)
            continue
        applicable.append(effect)
    ordered, cycles = order_continuous_effects(applicable)
    applied: list[str] = []
    for effect in ordered:
        for operation in effect.operations:
            _apply_operation(base, operation)
        if effect.layer == Layer.COPY and effect.sublayer == "1a":
            base.copiable_values = base.snapshot()
        applied.append(effect.effect_id)
    return ContinuousEvaluation(
        characteristics=base.snapshot(),
        applied_effects=tuple(applied),
        dependency_cycles=tuple(cycles),
        inapplicable_effects=tuple(inapplicable),
    )
