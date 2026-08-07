from __future__ import annotations

"""Read-only mana-source discovery for authoritative auto-payment.

New component families arrive as typed abilities. Narrow legacy compatibility
adapters remain here until their corresponding granted-mana families are
compiled, and are kept separate from typed mode discovery.
"""

from typing import Any, Mapping, Protocol, Sequence

from .abilities import ActivatedAbility
from .haste import summoning_sickness_prohibits_tap_or_untap_cost
from .mana import ManaMode, ManaSource, extract_effective_mana_modes
from .mana_ability_runtime import (
    payable_mana_modes,
    typed_mana_modes_for_abilities,
)
from .rules.activation.conditions import activation_condition_status
from .util import normalize_mana_bundle


class ManaSourceDiscoveryHost(Protocol):
    state: Any

    def _commander_identity(self, seat: str) -> set[str]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _may_activate_creature_as_haste(
        self, seat: str, card: Any
    ) -> bool: ...

    def _controller_has_oracle_text(self, seat: str, text: str) -> bool: ...

    def display_name(self, object_id: str) -> str: ...

    def card_record(self, card: Any) -> Any: ...

    def _recordless_mana_modes(
        self, seat: str, card: Any
    ) -> Sequence[ManaMode]: ...

    def _activated_abilities(
        self, card: Any
    ) -> tuple[ActivatedAbility, ...]: ...

    def _compiled_mana_restriction(self, restriction: str) -> str | None: ...

    def _mana_mode_has_compiled_activation_condition(
        self, restriction: str
    ) -> bool: ...

    def _mana_restriction_allows(
        self, restriction: str, spend_context: str | None
    ) -> bool: ...


def _unrestricted_when_payable(
    host: ManaSourceDiscoveryHost,
    modes: tuple[ManaMode, ...],
    *,
    spend_context: str | None,
) -> tuple[ManaMode, ...]:
    result: list[ManaMode] = []
    for mode in modes:
        restriction = host._compiled_mana_restriction(mode.restriction)
        if restriction is None:
            if host._mana_mode_has_compiled_activation_condition(
                mode.restriction
            ):
                result.append(
                    ManaMode(
                        mode.bundle,
                        conditional=False,
                        restriction=mode.restriction,
                        side_effects=mode.side_effects,
                        requires_choice=mode.requires_choice,
                    )
                )
            else:
                result.append(mode)
            continue
        if host._mana_restriction_allows(restriction, spend_context):
            result.append(
                ManaMode(
                    mode.bundle,
                    conditional=False,
                    restriction=mode.restriction,
                    side_effects=mode.side_effects,
                    requires_choice=mode.requires_choice,
                )
            )
    return tuple(result)


def available_mana_sources(
    host: ManaSourceDiscoveryHost,
    seat: str,
    *,
    spend_context: str | None = None,
) -> list[ManaSource]:
    """Discover payable modes without mutating game state."""

    identity = host._commander_identity(seat)
    sources: list[ManaSource] = []
    for object_id in host.state.players[seat].zones["battlefield"]:
        card = host.state.cards[object_id]
        if card.controller != seat or card.tapped or card.phased_out:
            continue
        data = host._effective_card_data(card)
        card_types, _, _ = host._type_parts(str(data.get("type_line") or ""))
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
            continue
        granted_token_mana = bool(
            card.is_token
            and "creature" in card_types
            and host._controller_has_oracle_text(
                seat,
                'creature tokens you control have "{t}: add one '
                'mana of any color."',
            )
        )
        if granted_token_mana:
            modes = tuple(
                ManaMode(
                    {
                        **normalize_mana_bundle(None),
                        color: 1,
                    }
                )
                for color in "WUBRG"
            )
            sources.append(
                ManaSource(
                    object_id,
                    card.ref,
                    host.display_name(object_id),
                    modes,
                )
            )
            continue
        record = host.card_record(card)
        if not record:
            compiled_modes = host._recordless_mana_modes(seat, card)
            if compiled_modes:
                sources.append(
                    ManaSource(
                        object_id,
                        card.ref,
                        host.display_name(object_id),
                        tuple(compiled_modes),
                    )
                )
            continue
        mana_abilities = [
            ability
            for ability in host._activated_abilities(card)
            if ability.mana_ability and card.zone in ability.zones
        ]
        if (
            not mana_abilities
            and not record.is_land
            and "creature tokens you control have"
            in record.oracle_text.casefold()
        ):
            continue
        if mana_abilities and not any(
            activation_condition_status(host, seat, ability, card)[0]
            == "payable"
            for ability in mana_abilities
        ):
            continue
        modes = payable_mana_modes(
            typed_mana_modes_for_abilities(
                host, seat, card, mana_abilities
            ),
            extract_effective_mana_modes(record, data, identity),
        )
        modes = _unrestricted_when_payable(
            host,
            modes,
            spend_context=spend_context,
        )
        if modes:
            sources.append(
                ManaSource(
                    object_id,
                    card.ref,
                    host.display_name(object_id),
                    modes,
                )
            )
    return sources


__all__ = ["ManaSourceDiscoveryHost", "available_mana_sources"]
