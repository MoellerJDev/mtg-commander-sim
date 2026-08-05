from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from .abilities import ActivatedAbility
from .errors import GameRuleError
from .haste import summoning_sickness_prohibits_tap_or_untap_cost
from .mana import ManaMode, extract_effective_mana_modes
from .mana_undo import (
    clear_mana_undo_stack,
    push_mana_undo,
    ReversibleManaActivation,
)
from .mana_mode_effects import apply_mana_mode_effects
from .util import normalize_mana_bundle
from .tap_state import set_permanent_tapped


class ManaActivationHost(Protocol):
    state: Any

    def _mana_output_for_ability(
        self,
        seat: str,
        source: Any,
        ability: ActivatedAbility,
        response: Mapping[str, Any],
    ) -> dict[str, int]: ...

    def _mana_modes_for_ability(
        self, seat: str, source: Any, ability: ActivatedAbility
    ) -> tuple[ManaMode, ...]: ...

    def _compiled_mana_restriction(self, restriction: str) -> str | None: ...

    def _add_restricted_mana(
        self, seat: str, restriction: str, bundle: Mapping[str, int]
    ) -> None: ...

    def _log(self, *args: Any, **kwargs: Any) -> Any: ...

    def _stabilize(self) -> bool: ...

    def _resolve_object(self, actor: str, ref: str, **kwargs: Any) -> Any: ...

    def card_record(self, card: Any) -> Any: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(self, type_line: str) -> tuple[set[str], set[str], set[str]]: ...

    def _may_activate_creature_as_haste(
        self, seat: str, card: Any
    ) -> bool: ...

    def _controller_has_oracle_text(self, seat: str, text: str) -> bool: ...

    def _recordless_mana_modes(self, seat: str, card: Any) -> Sequence[ManaMode]: ...

    def _activated_abilities(self, card: Any) -> tuple[ActivatedAbility, ...]: ...

    def _commander_identity(self, seat: str) -> set[str]: ...

    def _activation_condition_status(
        self, seat: str, ability: ActivatedAbility, card: Any
    ) -> tuple[str, str | None]: ...

    def _mana_restriction_allows(
        self, restriction: str, spend_context: str | None
    ) -> bool: ...

    def _mana_mode_has_compiled_activation_condition(
        self, restriction: str
    ) -> bool: ...


def complete_mana_activation(
    host: ManaActivationHost,
    *,
    seat: str,
    source: Any,
    ability: ActivatedAbility,
    response: Mapping[str, Any],
    origin: str,
    paid_objects: Sequence[str],
    payment_activations: Sequence[Mapping[str, Any]],
) -> None:
    """Commit one activated mana ability and its reversible UI boundary."""

    bundle = host._mana_output_for_ability(seat, source, ability, response)
    for color, amount in bundle.items():
        host.state.players[seat].mana_pool[color] += amount
    selected_mode = next(
        (
            mode
            for mode in host._mana_modes_for_ability(seat, source, ability)
            if normalize_mana_bundle(mode.bundle) == bundle
        ),
        None,
    )
    if selected_mode is not None:
        apply_mana_mode_effects(
            host,
            seat,
            selected_mode.side_effects,
            source=source,
            payment_id=str(response.get("_mana_payment_id") or "") or None,
            replacement_selections_by_event=(
                response.get("_mana_replacement_selections")
                if isinstance(
                    response.get("_mana_replacement_selections"), Mapping
                )
                else None
            ),
        )
    restriction = host._compiled_mana_restriction(ability.effect_text)
    if restriction:
        host._add_restricted_mana(seat, restriction, bundle)
    host._log(
        seat,
        "mana.ability",
        f"{seat} activated {source.ref} {ability.ability_id} for mana.",
        {
            "source": source.ref,
            "ability": ability.ability_id,
            "from": origin,
            "bundle": {key: value for key, value in bundle.items() if value},
            "cost_objects": [
                host.state.cards[object_id].ref
                for object_id in paid_objects
            ],
        },
        importance=0,
        changed_objects=[source.object_id, *paid_objects],
        changed_players=[seat],
    )
    reversible = bool(
        ability.tap_source
        and not sum(ability.mana.values())
        and not ability.choices
        and not any(
            (
                ability.untap_source,
                ability.discard_source,
                ability.sacrifice_source,
                ability.exile_source,
                ability.life_payment,
                ability.energy_payment,
                ability.loyalty_delta is not None,
                paid_objects,
                payment_activations,
                restriction,
                selected_mode is not None and bool(selected_mode.side_effects),
            )
        )
        and source.zone == "battlefield"
    )
    if reversible:
        push_mana_undo(
            host.state.players[seat].stats,
            ReversibleManaActivation.create(
                source_object_id=source.object_id,
                source_logical_object_id=source.logical_object_id,
                source_ref=source.ref,
                ability_id=ability.ability_id,
                bundle=bundle,
                turn_sequence=host.state.turn_sequence,
                phase=host.state.phase,
                step=host.state.step,
                priority_epoch=host.state.priority_epoch,
            ),
        )
    else:
        clear_mana_undo_stack(host.state.players[seat].stats)
    if host._stabilize():
        clear_mana_undo_stack(host.state.players[seat].stats)
        return
    host.state.priority_player = seat
    host.state.priority_passes = []


def _mana_plan_modes(
    host: ManaActivationHost,
    seat: str,
    card: Any,
    data: Mapping[str, Any],
    card_types: set[str],
) -> tuple[ManaMode, ...]:
    granted_token_mana = bool(
        card.is_token
        and "creature" in card_types
        and host._controller_has_oracle_text(
            seat,
            'creature tokens you control have "{t}: add one mana of any color."',
        )
    )
    if granted_token_mana:
        return tuple(
            ManaMode({**normalize_mana_bundle(None), color: 1})
            for color in "WUBRG"
        )
    record = host.card_record(card)
    if not record:
        modes = tuple(host._recordless_mana_modes(seat, card))
        if not modes:
            raise GameRuleError(f"{card.ref} has no compiled mana mode")
        return modes
    mana_abilities = [
        ability
        for ability in host._activated_abilities(card)
        if ability.mana_ability and card.zone in ability.zones
    ]
    if (
        not mana_abilities
        and not record.is_land
        and "creature tokens you control have" in record.oracle_text.casefold()
    ):
        raise GameRuleError(f"{card.ref} does not itself have that mana ability")
    return extract_effective_mana_modes(
        record, data, host._commander_identity(seat)
    )


def _selected_plan_mode(
    host: ManaActivationHost,
    seat: str,
    card: Any,
    modes: Sequence[ManaMode],
    bundle: Mapping[str, int],
    *,
    allow_conditional: bool,
    spend_context: str | None,
) -> tuple[ManaMode, str | None]:
    mode = next(
        (
            value
            for value in modes
            if normalize_mana_bundle(value.bundle) == bundle
        ),
        None,
    )
    if mode is None:
        raise GameRuleError(
            f"Declared output is not a recognized mana mode of {card.printed_name}"
        )
    mana_abilities = [
        ability
        for ability in host._activated_abilities(card)
        if ability.mana_ability and card.zone in ability.zones
    ]
    if mana_abilities and not any(
        host._activation_condition_status(seat, ability, card)[0] == "payable"
        for ability in mana_abilities
    ):
        raise GameRuleError(
            f"{card.printed_name}'s mana ability has an unmet or unresolved activation condition"
        )
    compiled = host._compiled_mana_restriction(mode.restriction)
    condition_compiled = host._mana_mode_has_compiled_activation_condition(
        mode.restriction
    )
    restriction_allows = bool(
        compiled and host._mana_restriction_allows(compiled, spend_context)
    )
    if mode.requires_choice:
        raise GameRuleError(
            f"{card.printed_name}'s selected mana mode has a nonmana choice/cost; "
            "activate that Oracle ability explicitly."
        )
    if (
        mode.conditional
        and host.state.config.strict_mana
        and not restriction_allows
        and not condition_compiled
    ):
        raise GameRuleError(
            f"{card.printed_name}'s selected mana mode is conditional/restricted "
            "and has no compiled validator."
        )
    if (
        mode.conditional
        and not allow_conditional
        and not restriction_allows
        and not condition_compiled
    ):
        raise GameRuleError(
            f"{card.printed_name}'s selected mana mode requires an explicit condition"
        )
    return mode, compiled


def _commit_plan_mode(
    host: ManaActivationHost,
    seat: str,
    card: Any,
    mode: ManaMode,
    bundle: Mapping[str, int],
    restriction: str | None,
    *,
    payment_id: str | None,
    replacement_selections_by_event: Mapping[str, Any] | None,
) -> None:
    cost_effects = tuple(
        effect for effect in mode.side_effects
        if effect.get("op") == "sacrifice_source"
    )
    result_effects = tuple(
        effect for effect in mode.side_effects
        if effect.get("op") != "sacrifice_source"
    )
    set_permanent_tapped(
        host,
        card.ref,
        actor=seat,
        tapped=True,
        reason="mana ability cost",
        log=False,
    )
    apply_mana_mode_effects(
        host,
        seat,
        cost_effects,
        source=card,
        payment_id=payment_id,
        replacement_selections_by_event=replacement_selections_by_event,
    )
    for color, amount in bundle.items():
        host.state.players[seat].mana_pool[color] += amount
    if restriction:
        host._add_restricted_mana(seat, restriction, bundle)
    apply_mana_mode_effects(
        host,
        seat,
        result_effects,
        source=card,
        payment_id=payment_id,
        replacement_selections_by_event=replacement_selections_by_event,
    )
    public_bundle = {key: value for key, value in bundle.items() if value}
    host._log(
        seat,
        "mana.produce",
        f"{seat} tapped {card.ref} for {public_bundle}.",
        {"source": card.ref, "bundle": public_bundle},
        importance=0,
        changed_objects=[card.object_id],
        changed_players=[seat],
    )


def complete_mana_plan_activations(
    host: ManaActivationHost,
    seat: str,
    activations: Sequence[Mapping[str, Any]],
    *,
    spend_context: str | None = None,
    payment_id: str | None = None,
    replacement_selections_by_event: Mapping[str, Any] | None = None,
) -> None:
    """Validate and commit an authoritative derived mana-payment plan."""

    for activation in activations:
        card = host._resolve_object(
            seat,
            str(activation["source"]),
            zones={"battlefield"},
            controlled_only=True,
        )
        if card.tapped:
            raise GameRuleError(f"{card.ref} is already tapped")
        data = host._effective_card_data(card)
        card_types = host._type_parts(str(data.get("type_line") or ""))[0]
        if (
            "creature" in card_types
            and summoning_sickness_prohibits_tap_or_untap_cost(
                host,
                card,
                as_though_haste=host._may_activate_creature_as_haste(
                    seat, card
                ),
            )
        ):
            raise GameRuleError(f"{card.ref} is summoning sick")
        bundle = normalize_mana_bundle(activation.get("bundle"))
        modes = _mana_plan_modes(host, seat, card, data, card_types)
        mode, restriction = _selected_plan_mode(
            host,
            seat,
            card,
            modes,
            bundle,
            allow_conditional=bool(activation.get("allow_conditional")),
            spend_context=spend_context,
        )
        _commit_plan_mode(
            host,
            seat,
            card,
            mode,
            bundle,
            restriction,
            payment_id=payment_id,
            replacement_selections_by_event=replacement_selections_by_event,
        )


__all__ = [
    "ManaActivationHost",
    "complete_mana_activation",
    "complete_mana_plan_activations",
]
