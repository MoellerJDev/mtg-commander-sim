from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ..action_proposals import CastCostOption


class CastCostHost(Protocol):
    state: Any
    semantics: Any

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...

    def card_record(self, card: Any) -> Any: ...

    def _temporary_play_permission(
        self, seat: str, card: Any
    ) -> Mapping[str, Any] | None: ...

    def _compiled_printed_cost_options(
        self,
        seat: str,
        card: Any,
        *,
        x_value: int | None,
        hint: bool,
    ) -> tuple[list[dict[str, Any]], bool]: ...

    def _mana_vector(self, value: Any) -> dict[str, int]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _spell_mana_spend_context(self, type_line: str) -> Any: ...

    def _cost_payment_mechanics(
        self, record: Any, schema: Mapping[str, Any]
    ) -> list[dict[str, Any]]: ...

    def _alternate_cost_condition_met(
        self, seat: str, condition: Mapping[str, Any]
    ) -> bool: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _exile_cost_candidates(
        self, seat: str, card: Any, specification: Mapping[str, Any]
    ) -> list[str]: ...

    def _payment_mechanic_candidates(
        self, seat: str, kind: str
    ) -> list[Any]: ...

    def _tap_payment_plan(
        self,
        seat: str,
        requirements: Mapping[str, int],
        kind: str,
        candidates: Sequence[Any],
        *,
        spend_context: Any,
    ) -> tuple[dict[str, int], list[Any]] | None: ...

    def _convoke_reduction(
        self, requirements: Mapping[str, int], cards: Sequence[Any]
    ) -> dict[str, int] | None: ...

    def _cost_is_affordable(
        self,
        seat: str,
        requirements: Mapping[str, int],
        *,
        exclude_sources: set[str] | None = None,
        spend_context: Any = None,
    ) -> bool: ...

    def _maximum_affordable_x_with_mechanics(
        self, seat: str, card: Any, mechanics: Sequence[Mapping[str, Any]]
    ) -> int: ...

    def _maximum_affordable_x(self, seat: str, card: Any) -> int: ...

    def _additional_cost_candidates(
        self, seat: str, card: Any, specification: Mapping[str, Any]
    ) -> list[str]: ...


def _initial_options(
    host: CastCostHost,
    seat: str,
    card: Any,
    program: Any,
    response: Mapping[str, Any],
    *,
    hint: bool,
    force_without_mana_cost: bool,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    Any,
    bool,
] | None:
    x_value = response.get("x")
    temporary_permission = host._temporary_play_permission(seat, card)
    cast_without_mana = force_without_mana_cost or bool(
        temporary_permission and temporary_permission.get("without_mana_cost")
    )
    if cast_without_mana:
        if x_value is not None and int(x_value) != 0:
            return None
        printed = [
            {
                "id": "without_mana_cost",
                "kind": "alternate",
                "label": "Cast without paying its mana cost",
                "requirements": host._mana_vector({}),
            }
        ]
        has_x = False
    else:
        printed, has_x = host._compiled_printed_cost_options(
            seat,
            card,
            x_value=int(x_value) if x_value is not None else None,
            hint=hint,
        )
    schema = dict(program.cost_schema or {}) if program else {}
    record = host.card_record(card)
    if record is None:
        return None
    spend_context = host._spell_mana_spend_context(
        str(host._effective_card_data(card).get("type_line") or "")
    )
    mechanics = host._cost_payment_mechanics(record, schema)
    if host.state.players[seat].stats.get("next_spell_improvise") and not any(
        str(value.get("kind") or "").casefold() == "improvise"
        for value in mechanics
    ):
        mechanics.append({"kind": "improvise"})
    commander_tax = (
        2 * host.state.players[seat].commander_casts.get(card.oracle_id, 0)
        if card.zone == "command" and card.is_commander
        else 0
    )
    base = list(printed)
    for raw in [] if cast_without_mana else schema.get("alternate_costs", []):
        alternative = dict(raw)
        if not host._alternate_cost_condition_met(
            seat, dict(alternative.get("condition") or {})
        ):
            continue
        requirements = host._mana_vector(alternative.get("requirements"))
        requirements["GENERIC"] += commander_tax
        base.append(
            {
                **alternative,
                "id": str(alternative["id"]),
                "kind": str(alternative.get("kind") or "alternate"),
                "requirements": requirements,
            }
        )
    expanded = list(base)
    for raw in schema.get("optional_costs", []):
        additional = dict(raw)
        additional_vector = host._mana_vector(additional.get("requirements"))
        for base_option in base:
            combined = host._mana_vector(base_option["requirements"])
            for symbol, amount in additional_vector.items():
                combined[symbol] += amount
            expanded.append(
                {
                    **base_option,
                    **{
                        key: copy.deepcopy(value)
                        for key, value in additional.items()
                        if key not in {"requirements", "id"}
                    },
                    "id": str(additional["id"]),
                    "kind": str(
                        additional.get("kind") or "optional_additional"
                    ),
                    "requirements": combined,
                    "base_cost_option": base_option["id"],
                }
            )
    mandatory = [dict(value) for value in schema.get("additional_costs", [])]
    return expanded, mandatory, mechanics, spend_context, has_x


@dataclass(frozen=True, slots=True)
class StaticCastCostModifier:
    spell_type: str
    generic_reduction: int

    @classmethod
    def from_descriptor(
        cls, value: Mapping[str, Any]
    ) -> "StaticCastCostModifier":
        if set(value) != {"spell_type", "generic_reduction"}:
            raise ValueError("Static cast-cost modifier fields are closed")
        spell_type = str(value.get("spell_type") or "").casefold()
        amount = value.get("generic_reduction")
        if not spell_type or type(amount) is not int or amount < 1:
            raise ValueError("Static cast-cost reductions require a type and positive amount")
        return cls(spell_type=spell_type, generic_reduction=amount)


def _static_generic_reduction(
    host: CastCostHost, seat: str, card: Any
) -> int:
    spell_types, _, _ = host._type_parts(
        str(host._effective_card_data(card).get("type_line") or "")
    )
    total = 0
    for object_id in host.state.players[seat].zones["battlefield"]:
        source = host.state.cards[object_id]
        if source.controller != seat or source.phased_out:
            continue
        program = host.semantics.get(f"{source.oracle_id}:spell:front")
        if program is None or not host.semantic_program_is_current_trusted(program):
            continue
        schema = dict(program.cost_schema or {})
        for raw in schema.get("static_modifiers", []):
            modifier = StaticCastCostModifier.from_descriptor(dict(raw))
            if modifier.spell_type in spell_types:
                total += modifier.generic_reduction
    return total


def _apply_static_reductions(
    host: CastCostHost, seat: str, card: Any, option: dict[str, Any]
) -> None:
    reduction = _static_generic_reduction(host, seat, card)
    if not reduction:
        return
    applied = min(int(option["requirements"]["GENERIC"]), reduction)
    option["requirements"]["GENERIC"] -= applied
    option.setdefault("cost_reductions", []).append(
        {
            "kind": "static_spell_type",
            "count": applied,
        }
    )


def _apply_affinity(
    host: CastCostHost,
    seat: str,
    option: dict[str, Any],
    mechanic: Mapping[str, Any],
) -> None:
    card_type = str(mechanic.get("card_type") or "artifact").casefold()
    count = sum(
        1
        for object_id in host.state.players[seat].zones["battlefield"]
        if host.state.cards[object_id].controller == seat
        and card_type
        in host._type_parts(
            str(
                host._effective_card_data(host.state.cards[object_id]).get(
                    "type_line"
                )
                or ""
            )
        )[0]
    )
    option["requirements"]["GENERIC"] = max(
        0, int(option["requirements"]["GENERIC"]) - count
    )
    option.setdefault("cost_reductions", []).append(
        {"kind": "affinity", "count": count, "card_type": card_type}
    )


def _apply_tap_payment_mechanic(
    host: CastCostHost,
    seat: str,
    option: dict[str, Any],
    mechanic: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    hint: bool,
    spend_context: Any,
    selected_cards: list[Any],
    choice_schema: dict[str, Any],
) -> bool:
    kind = str(mechanic.get("kind") or "").casefold()
    candidates = [
        card
        for card in host._payment_mechanic_candidates(seat, kind)
        if card not in selected_cards
    ]
    field = f"{kind}_cards"
    choice_schema[field] = {
        "type": "object_ref_array",
        "minimum": 0,
        "maximum": min(
            len(candidates), sum(option["requirements"].values())
        ),
        "legal_refs": [card.ref for card in candidates],
        "payment": kind,
    }
    if hint:
        plan = host._tap_payment_plan(
            seat,
            option["requirements"],
            kind,
            candidates,
            spend_context=spend_context,
        )
        if plan is None:
            return False
        option["requirements"] = plan[0]
        option.setdefault("recommended_payment_refs", {})[field] = [
            card.ref for card in plan[1]
        ]
        selected_cards.extend(plan[1])
        return True
    raw_values = response.get(field) or []
    if isinstance(raw_values, (str, bytes)):
        return False
    values = [str(value) for value in raw_values]
    by_ref = {candidate.ref: candidate for candidate in candidates}
    if len(values) != len(set(values)) or any(
        value not in by_ref for value in values
    ):
        return False
    selected = [by_ref[value] for value in values]
    if kind == "convoke":
        reduced = host._convoke_reduction(option["requirements"], selected)
        if reduced is None:
            return False
        option["requirements"] = reduced
    else:
        if len(selected) > int(option["requirements"]["GENERIC"]):
            return False
        option["requirements"]["GENERIC"] -= len(selected)
    selected_cards.extend(selected)
    return True


def _apply_payment_mechanics(
    host: CastCostHost,
    seat: str,
    option: dict[str, Any],
    mechanics: Sequence[Mapping[str, Any]],
    response: Mapping[str, Any],
    *,
    hint: bool,
    spend_context: Any,
) -> tuple[dict[str, Any], list[Any]] | None:
    choice_schema: dict[str, Any] = {}
    selected_cards: list[Any] = []
    for mechanic in mechanics:
        kind = str(mechanic.get("kind") or "").casefold()
        if kind == "affinity":
            _apply_affinity(host, seat, option, mechanic)
            continue
        if kind not in {"convoke", "improvise"}:
            return None
        if not _apply_tap_payment_mechanic(
            host,
            seat,
            option,
            mechanic,
            response,
            hint=hint,
            spend_context=spend_context,
            selected_cards=selected_cards,
            choice_schema=choice_schema,
        ):
            return None
    return choice_schema, selected_cards


def _apply_additional_costs(
    host: CastCostHost,
    seat: str,
    card: Any,
    option: dict[str, Any],
    mandatory_costs: Sequence[Mapping[str, Any]],
    response: Mapping[str, Any],
    *,
    hint: bool,
    choice_schema: dict[str, Any],
) -> bool:
    selected_nonmana: list[dict[str, Any]] = []
    selected_refs: set[str] = set()
    for index, raw in enumerate(mandatory_costs):
        additional = dict(raw)
        kind = str(additional.get("kind") or "")
        if kind == "life_x":
            selected_x = int(response["x"]) if response.get("x") is not None else 0
            minimum = int(additional.get("minimum", 0))
            maximum = host.state.players[seat].life
            if maximum < minimum or not minimum <= selected_x <= maximum:
                return False
            choice_schema["x"] = {
                "type": "integer",
                "minimum": minimum,
                "maximum": maximum,
                "payment": "life",
            }
            continue
        if kind not in {"sacrifice", "discard"}:
            return not kind
        count = int(additional.get("count", 1))
        candidates = [
            ref
            for ref in host._additional_cost_candidates(seat, card, additional)
            if ref not in selected_refs
        ]
        if len(candidates) < count:
            return False
        field = str(additional.get("choice_field") or f"{kind}_cards")
        choice_schema[field] = {
            "type": "object_ref_array",
            "count": count,
            "legal_refs": candidates,
            "zone": "hand" if kind == "discard" else "battlefield",
            "destination": "graveyard",
        }
        if hint:
            continue
        raw_values = response.get(field)
        if raw_values is None and len(mandatory_costs) == 1:
            raw_values = response.get("cost_cards")
        values = [str(value) for value in (raw_values or [])]
        if (
            len(values) != count
            or len(set(values)) != count
            or any(value not in candidates for value in values)
        ):
            return False
        selected_refs.update(values)
        selected_nonmana.append({"kind": kind, "cards": values, "index": index})
    option["additional_costs"] = [dict(value) for value in mandatory_costs]
    if selected_nonmana:
        option["selected_additional_costs"] = selected_nonmana
    return True


def _finalize_option(
    host: CastCostHost,
    seat: str,
    card: Any,
    option: dict[str, Any],
    mandatory_costs: Sequence[Mapping[str, Any]],
    mechanics: Sequence[Mapping[str, Any]],
    response: Mapping[str, Any],
    *,
    hint: bool,
    spend_context: Any,
    has_x: bool,
) -> CastCostOption | None:
    option = copy.deepcopy(option)
    option["base_requirements"] = host._mana_vector(option["requirements"])
    _apply_static_reductions(host, seat, card, option)
    exile_spec = option.get("exile_from_hand")
    if isinstance(exile_spec, Mapping):
        candidates = host._exile_cost_candidates(seat, card, exile_spec)
        if not candidates:
            return None
        option["exile_candidates"] = candidates
    payment = _apply_payment_mechanics(
        host,
        seat,
        option,
        mechanics,
        response,
        hint=hint,
        spend_context=spend_context,
    )
    if payment is None:
        return None
    choice_schema, selected_cards = payment
    if not host._cost_is_affordable(
        seat,
        option["requirements"],
        exclude_sources={card.object_id for card in selected_cards},
        spend_context=spend_context,
    ):
        return None
    if selected_cards:
        option["selected_tap_cost_cards"] = [card.ref for card in selected_cards]
    if has_x:
        maximum = (
            host._maximum_affordable_x_with_mechanics(seat, card, mechanics)
            if mechanics
            else host._maximum_affordable_x(seat, card)
        )
        if maximum < 0:
            return None
        choice_schema["x"] = {"type": "integer", "minimum": 0, "maximum": maximum}
    if not _apply_additional_costs(
        host,
        seat,
        card,
        option,
        mandatory_costs,
        response,
        hint=hint,
        choice_schema=choice_schema,
    ):
        return None
    if isinstance(exile_spec, Mapping):
        choice_schema["exile_card"] = {
            "type": "object_ref",
            "legal_refs": list(option["exile_candidates"]),
            "zone": "hand",
            "destination": "exile",
        }
        if not hint:
            selected = str(
                response.get("exile_card")
                or list(response.get("exile_cards") or [None])[0]
                or ""
            )
            if selected not in option["exile_candidates"]:
                return None
            option["selected_exile_card"] = selected
    if choice_schema:
        option["choice_schema"] = choice_schema
    return CastCostOption.from_dict(option)


def build_cast_cost_options(
    host: CastCostHost,
    seat: str,
    card: Any,
    program: Any,
    *,
    response: Mapping[str, Any] | None = None,
    hint: bool,
    force_without_mana_cost: bool = False,
) -> tuple[CastCostOption, ...]:
    """Return immutable, currently payable server-authoritative cost choices."""

    submission = dict(response or {})
    initial = _initial_options(
        host,
        seat,
        card,
        program,
        submission,
        hint=hint,
        force_without_mana_cost=force_without_mana_cost,
    )
    if initial is None:
        return ()
    expanded, mandatory, mechanics, spend_context, has_x = initial
    result = []
    for option in expanded:
        finalized = _finalize_option(
            host,
            seat,
            card,
            option,
            mandatory,
            mechanics,
            submission,
            hint=hint,
            spend_context=spend_context,
            has_x=has_x,
        )
        if finalized is not None:
            result.append(finalized)
    return tuple(result)


__all__ = ["CastCostHost", "build_cast_cost_options"]
