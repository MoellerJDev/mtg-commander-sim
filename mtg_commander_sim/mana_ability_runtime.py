from __future__ import annotations

"""Runtime output selection for activated mana abilities.

The fixed-output CardProgram family is consumed first.  Legacy dynamic modes
remain isolated here until their own typed capability families replace them.
"""

from dataclasses import replace
from typing import Any, Mapping, Protocol

from .abilities import ActivatedAbility
from .color_set_mana_abilities import (
    ColorSetRelation,
    ColorSetSelection,
)
from .errors import GameRuleError
from .mana import (
    effective_mana_record,
    extract_mana_modes,
    ManaMode,
)
from .object_query import object_query_result, query_objects
from .util import mana_cost_to_vector, normalize_mana_bundle


class ManaAbilityRuntimeHost(Protocol):
    active_seats: list[str]
    state: Any

    def card_record(self, card: Any) -> Any: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _commander_identity(self, seat: str) -> set[str]: ...


def _color_set_mana_modes(
    host: ManaAbilityRuntimeHost,
    seat: str,
    ability: ActivatedAbility,
) -> tuple[ManaMode, ...]:
    spec = ability.color_set_mana_output
    if spec is None:
        return ()
    query = replace(
        spec.query,
        controller=(
            seat if spec.relation is ColorSetRelation.CONTROLLER else None
        ),
        owner=(seat if spec.relation is ColorSetRelation.OWNER else None),
    )
    rows = []
    for card in host.state.cards.values():
        if card.zone not in spec.query.zones:
            continue
        if (
            spec.relation is ColorSetRelation.CONTROLLER
            and card.controller != seat
        ):
            continue
        if spec.relation is ColorSetRelation.OWNER and card.owner != seat:
            continue
        effective = host._effective_card_data(card)
        rows.append(
            object_query_result(
                card,
                effective,
                type_parts=host._type_parts(
                    str(effective.get("type_line") or "")
                ),
                known_to_actor=True,
                attached_to_ref=None,
            )
        )
    matches = query_objects(rows, query)
    colors = tuple(
        color
        for color in "WUBRG"
        if any(color in row.colors for row in matches)
    )
    if spec.selection is ColorSetSelection.ONE_EACH:
        return (
            ManaMode(
                normalize_mana_bundle({color: 1 for color in colors})
            ),
        )
    if spec.selection is ColorSetSelection.CHOOSE_ONE:
        if not colors:
            return (ManaMode(normalize_mana_bundle(None)),)
        return tuple(
            ManaMode(normalize_mana_bundle({color: 1}))
            for color in colors
        )
    raise GameRuleError("Unsupported typed color-set mana selection")


def mana_modes_for_ability(
    host: ManaAbilityRuntimeHost,
    seat: str,
    source: Any,
    ability: ActivatedAbility,
) -> tuple[ManaMode, ...]:
    """Return the output modes for one selected activated mana ability."""

    if ability.color_set_mana_output is not None:
        return _color_set_mana_modes(host, seat, ability)
    if ability.fixed_mana_outputs:
        fixed_outputs = tuple(ability.fixed_mana_outputs)
        if all(
            sum(1 for amount in mode.bundle.values() if amount) == 1
            for mode in fixed_outputs
        ):
            color_order = {color: index for index, color in enumerate("WUBRGC")}
            fixed_outputs = tuple(
                sorted(
                    fixed_outputs,
                    key=lambda mode: min(
                        color_order[color]
                        for color, amount in mode.bundle.items()
                        if amount
                    ),
                )
            )
        return tuple(
            ManaMode(mode.bundle) for mode in fixed_outputs
        )
    record = host.card_record(source)
    if record is None:
        effect = ability.effect_text.casefold()
        if "one mana of any type" in effect:
            colors = "WUBRGC"
        elif "one mana of any color" in effect:
            colors = "WUBRG"
        else:
            return ()
        return tuple(
            ManaMode(
                {
                    **normalize_mana_bundle(None),
                    color: 1,
                }
            )
            for color in colors
        )
    effect = ability.effect_text.casefold()
    if (
        "one mana of any color that a land an opponent controls "
        "could produce"
        in effect
    ):
        colors: set[str] = set()
        for opponent in host.active_seats:
            if opponent == seat:
                continue
            for object_id in host.state.players[opponent].zones[
                "battlefield"
            ]:
                land = host.state.cards[object_id]
                land_record = effective_mana_record(
                    host.card_record(land),
                    host._effective_card_data(land),
                )
                if (
                    land.controller != opponent
                    or land.phased_out
                    or land_record is None
                ):
                    continue
                for mode in extract_mana_modes(
                    land_record,
                    host._commander_identity(opponent),
                ):
                    colors.update(
                        color
                        for color, amount in mode.bundle.items()
                        if color in "WUBRG" and amount
                    )
        return tuple(
            ManaMode(
                {
                    **normalize_mana_bundle(None),
                    color: 1,
                }
            )
            for color in sorted(colors)
        )
    ability_record = replace(
        record,
        oracle_text=f"{{T}}: {ability.effect_text}",
        type_line="",
        produced_mana=(),
    )
    return extract_mana_modes(
        ability_record,
        host._commander_identity(seat),
    )


def typed_mana_modes_for_abilities(
    host: ManaAbilityRuntimeHost,
    seat: str,
    source: Any,
    abilities: tuple[ActivatedAbility, ...] | list[ActivatedAbility],
) -> tuple[ManaMode, ...]:
    """Return deduplicated modes owned by typed mana descriptors."""

    result: dict[tuple[tuple[str, int], ...], ManaMode] = {}
    for ability in abilities:
        if not (
            ability.fixed_mana_outputs
            or ability.color_set_mana_output is not None
        ):
            continue
        for mode in mana_modes_for_ability(host, seat, source, ability):
            key = tuple(
                (color, int(mode.bundle.get(color, 0)))
                for color in "WUBRGC"
                if int(mode.bundle.get(color, 0))
            )
            result.setdefault(key, mode)
    return tuple(result.values())


def payable_mana_modes(
    *groups: tuple[ManaMode, ...] | list[ManaMode],
) -> tuple[ManaMode, ...]:
    """Merge source modes canonically, excluding outputs that cannot pay."""

    result: dict[tuple[tuple[str, int], ...], ManaMode] = {}
    for mode in (mode for group in groups for mode in group):
        key = tuple(
            (color, int(mode.bundle.get(color, 0)))
            for color in "WUBRGC"
            if int(mode.bundle.get(color, 0))
        )
        if key:
            result.setdefault(key, mode)
    return tuple(result.values())


def mana_output_for_ability(
    host: ManaAbilityRuntimeHost,
    seat: str,
    source: Any,
    ability: ActivatedAbility,
    response: Mapping[str, Any],
) -> dict[str, int]:
    """Validate the submitted output against the advertised mode set."""

    effect_lower = ability.effect_text.casefold()
    if (
        "one mana of any color that a land an opponent controls "
        "could produce"
        in effect_lower
    ):
        legal_colors: set[str] = set()
        for opponent in host.active_seats:
            if opponent == seat:
                continue
            for object_id in host.state.players[opponent].zones[
                "battlefield"
            ]:
                land = host.state.cards[object_id]
                record = effective_mana_record(
                    host.card_record(land),
                    host._effective_card_data(land),
                )
                if (
                    land.controller != opponent
                    or land.phased_out
                    or record is None
                    or not record.is_land
                ):
                    continue
                for mode in extract_mana_modes(
                    record,
                    host._commander_identity(opponent),
                ):
                    legal_colors.update(
                        color
                        for color, amount in mode.bundle.items()
                        if color in "WUBRG" and amount
                    )
        raw_choice = str(response.get("mana_choice") or "").upper()
        declared = normalize_mana_bundle(response.get("mana_output"))
        if raw_choice in "WUBRG" and len(raw_choice) == 1:
            declared[raw_choice] += 1
        selected = [
            color for color in "WUBRG" if declared[color] == 1
        ]
        if (
            len(selected) != 1
            or sum(declared.values()) != 1
            or selected[0] not in legal_colors
        ):
            raise GameRuleError(
                "Declared Fellwar/Orchard mana is not a color an "
                "opponent's land could produce"
            )
        return declared
    legal_modes = mana_modes_for_ability(host, seat, source, ability)
    declared = normalize_mana_bundle(response.get("mana_output"))
    raw_choice = str(response.get("mana_choice") or "").upper()
    if raw_choice in "WUBRGC" and len(raw_choice) == 1:
        declared[raw_choice] += 1
    if legal_modes:
        if sum(declared.values()):
            if not any(
                normalize_mana_bundle(mode.bundle) == declared
                for mode in legal_modes
            ):
                raise GameRuleError(
                    "Declared mana output is not a currently legal mana mode"
                )
            return declared
        if len(legal_modes) == 1:
            return normalize_mana_bundle(legal_modes[0].bundle)
        raise GameRuleError("Choose which mana this ability produces")

    output_text = ability.effect_text.split(".", 1)[0]
    output, complex_symbols = mana_cost_to_vector(output_text)
    bundle = {color: int(output.get(color, 0)) for color in "WUBRGC"}
    if output.get("GENERIC"):
        bundle["C"] += int(output["GENERIC"])
    if sum(bundle.values()) and not complex_symbols:
        return normalize_mana_bundle(bundle)
    raw_choice = str(response.get("mana_choice") or "").upper()
    declared = normalize_mana_bundle(response.get("mana_output"))
    if raw_choice in "WUBRGC" and len(raw_choice) == 1:
        declared[raw_choice] += 1
    record = host.card_record(source)
    if not record:
        if (
            "one mana of any color" in ability.effect_text.casefold()
            and sum(declared.values()) == 1
            and declared["C"] == 0
        ):
            return declared
        raise GameRuleError("Custom mana ability needs compiled semantics")
    legacy_modes = extract_mana_modes(
        record, host._commander_identity(seat)
    )
    if not any(
        normalize_mana_bundle(mode.bundle) == declared
        for mode in legacy_modes
    ):
        raise GameRuleError(
            "Declared mana output is not a recognized Oracle mana mode"
        )
    return declared


__all__ = [
    "ManaAbilityRuntimeHost",
    "mana_modes_for_ability",
    "mana_output_for_ability",
    "payable_mana_modes",
    "typed_mana_modes_for_abilities",
]
