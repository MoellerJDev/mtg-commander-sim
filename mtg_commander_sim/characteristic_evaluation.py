from __future__ import annotations

import copy
import re
from typing import Any, Mapping, Sequence

from .continuous_effects import (
    CharacteristicState,
    ContinuousEffect,
    ContinuousEffectDuration,
    ContinuousOperation,
    Layer,
    evaluate_continuous_effects,
)
from .model import CardInstance
from .util import unique_preserving_order


_CARD_TYPES = {
    "artifact",
    "battle",
    "creature",
    "enchantment",
    "instant",
    "kindred",
    "land",
    "planeswalker",
    "sorcery",
}
_SUPERTYPES = frozenset("basic legendary ongoing snow world".split())


def type_parts(type_line: str) -> tuple[set[str], set[str], set[str]]:
    """Parse the public type-line vocabulary used by characteristic layers."""

    normalized = type_line.replace("—", "-")
    left, _, right = normalized.partition("-")
    word_pattern = r"[A-Za-z]+(?:[-'][A-Za-z]+)*"
    words = {
        word.casefold() for word in re.findall(word_pattern, left)
    }
    return (
        words.intersection(_CARD_TYPES),
        {
            word.casefold()
            for word in re.findall(word_pattern, right)
        },
        words.intersection(_SUPERTYPES),
    )


def _numeric(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _annotation_terms(
    card: CardInstance,
) -> tuple[dict[str, Any], list[str], list[str]]:
    temporary = dict(card.annotations.get("until_end_of_turn") or {})
    overrides = dict(card.annotations.get("copy_overrides") or {})
    added_types = [
        str(value).strip()
        for value in card.annotations.get("continuous_add_types", [])
        if str(value).strip()
    ] + [
        str(value).strip()
        for value in temporary.get("add_types", [])
        if str(value).strip()
    ]
    chosen_subtype = (
        [str(card.annotations["chosen_creature_type"])]
        if card.annotations.get("chosen_creature_type_adds_subtype")
        and card.annotations.get("chosen_creature_type")
        else []
    )
    added_subtypes = chosen_subtype + [
        str(value).strip()
        for value in card.annotations.get("continuous_add_subtypes", [])
        if str(value).strip()
    ] + [
        str(value).strip()
        for value in temporary.get("add_subtypes", [])
        if str(value).strip()
    ]
    return overrides, added_types, added_subtypes


def _base_characteristic_state(
    card: CardInstance, result: Mapping[str, Any]
) -> CharacteristicState:
    card_types, subtypes, supertypes = type_parts(
        str(result.get("type_line") or "")
    )
    return CharacteristicState(
        name=str(result.get("name") or card.printed_name),
        controller=card.controller,
        mana_cost=str(result.get("mana_cost") or ""),
        mana_value=float(result.get("mana_value") or 0),
        text=str(result.get("oracle_text") or ""),
        supertypes=set(supertypes),
        card_types=set(card_types),
        subtypes=set(subtypes),
        colors={str(value).upper() for value in result.get("colors", [])},
        abilities=[str(value) for value in result.get("keywords", [])],
        power=_numeric(result.get("power")),
        toughness=_numeric(result.get("toughness")),
        loyalty=_numeric(result.get("loyalty")),
        defense=_numeric(result.get("defense")),
    )


def _copy_effect(
    card: CardInstance,
    overrides: Mapping[str, Any],
) -> ContinuousEffect | None:
    copy_values: dict[str, Any] = {}
    field_map = {
        "name": "name",
        "mana_cost": "mana_cost",
        "mana_value": "mana_value",
        "oracle_text": "text",
        "power": "power",
        "toughness": "toughness",
        "loyalty": "loyalty",
        "defense": "defense",
        "colors": "colors",
        "keywords": "abilities",
    }
    numeric_fields = {"power", "toughness", "loyalty", "defense"}
    for source_field, target_field in field_map.items():
        if source_field not in overrides:
            continue
        value = copy.deepcopy(overrides[source_field])
        if target_field in numeric_fields:
            value = _numeric(value)
            if value is None:
                continue
        copy_values[target_field] = value
    if overrides.get("type_line") is not None:
        copied_types, copied_subtypes, copied_supertypes = type_parts(
            str(overrides["type_line"])
        )
        copy_values.update(
            {
                "card_types": sorted(copied_types),
                "subtypes": sorted(copied_subtypes),
                "supertypes": sorted(copied_supertypes),
            }
        )
    if not copy_values:
        return None
    return ContinuousEffect(
        effect_id=f"{card.object_id}:copy",
        source_id=card.object_id,
        layer=Layer.COPY,
        sublayer="1a",
        timestamp=0,
        operations=(ContinuousOperation("copy_values", copy_values),),
        duration=ContinuousEffectDuration.ZONE_OBJECT,
    )


def _legacy_annotation_effects(
    card: CardInstance,
    overrides: Mapping[str, Any],
    added_types: Sequence[str],
    added_subtypes: Sequence[str],
) -> list[ContinuousEffect]:
    effects: list[ContinuousEffect] = []
    copy_effect = _copy_effect(card, overrides)
    if copy_effect is not None:
        effects.append(copy_effect)
    type_operations: list[ContinuousOperation] = []
    if card.annotations.get("bestowed") and card.attached_to:
        type_operations.extend(
            (
                ContinuousOperation(
                    "set_types", ["Enchantment"], field="card_types"
                ),
                ContinuousOperation(
                    "set_types", ["Aura"], field="subtypes"
                ),
            )
        )
    if added_types:
        type_operations.append(
            ContinuousOperation("add_types", added_types, field="card_types")
        )
    if added_subtypes:
        type_operations.append(
            ContinuousOperation(
                "add_types", added_subtypes, field="subtypes"
            )
        )
    if type_operations:
        effects.append(
            ContinuousEffect(
                effect_id=f"{card.object_id}:types",
                source_id=card.object_id,
                layer=Layer.TYPE,
                sublayer="4",
                timestamp=len(effects),
                operations=tuple(type_operations),
                duration=ContinuousEffectDuration.ZONE_OBJECT,
            )
        )
    if card.temporary_keywords:
        effects.append(
            ContinuousEffect(
                effect_id=f"{card.object_id}:keywords",
                source_id=card.object_id,
                layer=Layer.ABILITY,
                sublayer="6",
                timestamp=len(effects),
                operations=tuple(
                    ContinuousOperation("add_ability", keyword)
                    for keyword in card.temporary_keywords
                ),
                duration=ContinuousEffectDuration.UNTIL_END_OF_TURN,
            )
        )
    return effects


def _ordered_words(
    values_to_order: Sequence[str], preferred: Sequence[str]
) -> list[str]:
    by_lower = {
        str(value).casefold(): str(value).title()
        for value in values_to_order
    }
    preferred_lower = {value.casefold() for value in preferred}
    return [
        value for value in preferred if value.casefold() in by_lower
    ] + [
        by_lower[key]
        for key in sorted(by_lower)
        if key not in preferred_lower
    ]


def _render_characteristics(
    card: CardInstance,
    result: dict[str, Any],
    values: Mapping[str, Any],
    *,
    render_type_line: bool,
) -> dict[str, Any]:
    result.update(
        {
            "name": values["name"],
            "mana_cost": values["mana_cost"],
            "mana_value": values["mana_value"],
            "oracle_text": values["text"],
            "colors": [
                color for color in "WUBRGC" if color in set(values["colors"])
            ],
            "keywords": unique_preserving_order(values["abilities"]),
        }
    )
    for field in ("power", "toughness", "loyalty", "defense"):
        if values[field] is not None:
            result[field] = str(values[field])
    if render_type_line:
        left = [
            *_ordered_words(
                values["supertypes"], "Basic Legendary Snow World".split()
            ),
            *_ordered_words(
                values["card_types"],
                (
                    "Artifact Battle Creature Enchantment Instant Kindred Land "
                    "Planeswalker Sorcery"
                ).split(),
            ),
        ]
        right = [str(value).title() for value in values["subtypes"]]
        result["type_line"] = " ".join(left) + (
            f" — {' '.join(right)}" if right else ""
        )
    if card.annotations.get("bestowed") and card.attached_to:
        result["oracle_text"] = (
            "Enchant creature\nEnchanted creature gets +1/+1."
        )
    return result


def evaluate_card_characteristics(
    card: CardInstance,
    base: Mapping[str, Any],
    *,
    runtime_effects: Sequence[ContinuousEffect] = (),
) -> dict[str, Any]:
    """Evaluate one object's declarative CR 613 characteristic state.

    The owner is independent of CommanderEngine so authoritative rules and
    permission-aware projections can render the same committed result. Legacy
    annotation-backed records remain readable while new resolution effects use
    the immutable continuous-effect journal.
    """

    result = copy.deepcopy(dict(base))
    overrides, added_types, added_subtypes = _annotation_terms(card)
    layered = bool(
        overrides
        or added_types
        or added_subtypes
        or card.temporary_keywords
        or card.annotations.get("bestowed")
        or runtime_effects
    )
    if not layered:
        result["keywords"] = unique_preserving_order(
            list(result.get("keywords") or [])
        )
        return result

    state = _base_characteristic_state(card, result)
    effects = _legacy_annotation_effects(
        card, overrides, added_types, added_subtypes
    )
    effects.extend(runtime_effects)
    evaluated = evaluate_continuous_effects(
        state,
        effects,
        context={
            "object_id": card.object_id,
            "logical_object_id": card.logical_object_id,
            "ref": card.ref,
            "owner": card.owner,
            "controller": card.controller,
            "zone": card.zone,
            "token": card.is_token,
            "tapped": card.tapped,
            "phased_out": card.phased_out,
            "known_to_actor": True,
        },
    )
    values = evaluated.characteristics
    applied = set(evaluated.applied_effects)
    render_type_line = any(
        effect.effect_id in applied
        and (
            effect.layer is Layer.TYPE
            or any(
                operation.op == "face_down"
                or (
                    operation.op == "copy_values"
                    and bool(
                        {"supertypes", "card_types", "subtypes"}.intersection(
                            operation.value
                        )
                    )
                )
                for operation in effect.operations
            )
        )
        for effect in effects
    )
    return _render_characteristics(
        card,
        result,
        values,
        render_type_line=render_type_line,
    )
