from __future__ import annotations

from typing import Any, Protocol

from ...abilities import ActivatedAbility, reduced_requirements


class ActivationAvailabilityHost(Protocol):
    state: Any

    def _nonmana_ability_prohibited_by_name(self, card: Any) -> bool: ...

    def _activation_condition_status(
        self, seat: str, ability: ActivatedAbility, card: Any
    ) -> tuple[str, str | None]: ...

    def _loyalty_cost_modifier_present(self) -> bool: ...

    def _is_summoning_sick(self, card: Any) -> bool: ...

    def _effective_card_data(self, card: Any) -> dict[str, Any]: ...

    def _may_activate_creature_as_haste(self, seat: str, card: Any) -> bool: ...

    def _ability_choice_payable(
        self, seat: str, source: Any, ability: ActivatedAbility
    ) -> bool: ...

    def _crew_threshold(self, ability: ActivatedAbility) -> int | None: ...

    def _crew_candidates(self, seat: str, source: Any) -> list[Any]: ...

    def _numeric_stat(self, object_id: str, stat: str) -> int: ...

    def _legendary_creatures_controlled(self, seat: str) -> int: ...

    def _cost_is_affordable(
        self,
        seat: str,
        requirements: dict[str, int],
        *,
        exclude_sources: set[str] | None = None,
    ) -> bool: ...


def activation_availability(
    host: ActivationAvailabilityHost,
    seat: str,
    card: Any,
    ability: ActivatedAbility,
) -> tuple[str, str | None]:
    """Return the read-only payable status for one typed ability."""

    player = host.state.players[seat]
    zone = card.zone
    if zone not in ability.zones:
        return "unavailable", "wrong_zone"
    if not ability.compiled_cost:
        return "unresolved", "unresolved_cost_semantics"
    if not ability.mana_ability and host._nonmana_ability_prohibited_by_name(card):
        return "unavailable", "named_ability_prohibition"
    condition_status, condition_reason = host._activation_condition_status(
        seat, ability, card
    )
    if condition_status != "payable":
        return condition_status, condition_reason
    if ability.sorcery_speed and not _main_phase_timing(host, seat):
        return "unavailable", "sorcery_timing"
    loyalty_status = _loyalty_availability(host, seat, card, ability)
    if loyalty_status is not None:
        return loyalty_status
    source_status = _source_cost_availability(host, seat, card, ability)
    if source_status is not None:
        return source_status
    if ability.life_payment and player.life < ability.life_payment:
        return "unpayable", "insufficient_life"
    if ability.energy_payment and player.energy < ability.energy_payment:
        return "unpayable", "insufficient_energy"
    if ability.choices and not host._ability_choice_payable(seat, card, ability):
        return "unpayable", "mandatory_cost_object_unavailable"
    crew_threshold = host._crew_threshold(ability)
    if crew_threshold is not None and sum(
        max(0, host._numeric_stat(candidate.object_id, "power"))
        for candidate in host._crew_candidates(seat, card)
    ) < crew_threshold:
        return "unpayable", "insufficient_crew_power"
    requirements = reduced_requirements(
        ability,
        legendary_creatures=host._legendary_creatures_controlled(seat),
    )
    excluded = {card.object_id} if ability.tap_source else set()
    if sum(requirements.values()) and not host._cost_is_affordable(
        seat, requirements, exclude_sources=excluded
    ):
        return "unpayable", "insufficient_mana"
    return "payable", None


def _main_phase_timing(host: ActivationAvailabilityHost, seat: str) -> bool:
    return bool(
        seat == host.state.active_player
        and not host.state.stack
        and (host.state.phase, host.state.step)
        in {
            ("precombat_main", "main"),
            ("postcombat_main", "main"),
        }
    )


def _loyalty_availability(
    host: ActivationAvailabilityHost,
    seat: str,
    card: Any,
    ability: ActivatedAbility,
) -> tuple[str, str] | None:
    if ability.loyalty_delta is None:
        return None
    if host._loyalty_cost_modifier_present():
        return "unresolved", "unresolved_loyalty_cost_modification"
    if not _main_phase_timing(host, seat):
        return "unavailable", "loyalty_timing"
    if card.annotations.get("loyalty_activated_turn_sequence") == host.state.turn_sequence:
        return "unavailable", "loyalty_already_activated"
    if (
        ability.loyalty_delta < 0
        and int(card.counters.get("loyalty", 0)) < -ability.loyalty_delta
    ):
        return "unpayable", "insufficient_loyalty"
    return None


def _source_cost_availability(
    host: ActivationAvailabilityHost,
    seat: str,
    card: Any,
    ability: ActivatedAbility,
) -> tuple[str, str] | None:
    zone = card.zone
    if ability.tap_source:
        if zone != "battlefield":
            return "unavailable", "tap_cost_wrong_zone"
        if card.tapped:
            return "unavailable", "source_tapped"
    if ability.untap_source and (
        zone != "battlefield"
        or not card.tapped
        or int(card.counters.get("stun", 0)) > 0
    ):
        return "unavailable", "untap_cost_unavailable"
    if (
        (ability.tap_source or ability.untap_source)
        and zone == "battlefield"
        and host._is_summoning_sick(card)
        and "Haste" not in host._effective_card_data(card).get("keywords", [])
        and not host._may_activate_creature_as_haste(seat, card)
    ):
        return "unavailable", "summoning_sickness"
    if ability.discard_source and zone != "hand":
        return "unavailable", "discard_source_wrong_zone"
    if ability.sacrifice_source and zone != "battlefield":
        return "unavailable", "sacrifice_source_wrong_zone"
    return None


__all__ = ["ActivationAvailabilityHost", "activation_availability"]
