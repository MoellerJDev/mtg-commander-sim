from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from .abilities import ActivatedAbility
from .mana import ManaMode
from .mana_undo import (
    clear_mana_undo_stack,
    push_mana_undo,
    ReversibleManaActivation,
)
from .util import normalize_mana_bundle


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

    def _apply_mana_mode_side_effects(
        self,
        seat: str,
        effects: Sequence[Mapping[str, Any]],
        *,
        source: Any,
    ) -> None: ...

    def _compiled_mana_restriction(self, restriction: str) -> str | None: ...

    def _add_restricted_mana(
        self, seat: str, restriction: str, bundle: Mapping[str, int]
    ) -> None: ...

    def _log(self, *args: Any, **kwargs: Any) -> Any: ...

    def _stabilize(self) -> bool: ...


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
        host._apply_mana_mode_side_effects(
            seat, selected_mode.side_effects, source=source
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
