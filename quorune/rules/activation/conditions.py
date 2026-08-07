from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol

from ...abilities import ActivatedAbility


class ActivationConditionHost(Protocol):
    state: Any

    def _effective_card_data(self, card: Any) -> dict[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...


_COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "s" + "ix": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_COUNT_PATTERN = "|".join(
    (r"\d+", *(re.escape(word) for word in _COUNT_WORDS))
)


def _effective_card_types(
    host: ActivationConditionHost,
    card: Any,
) -> frozenset[str] | None:
    """Return the canonical effective card types or fail closed."""

    try:
        data = host._effective_card_data(card)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    if not isinstance(data, Mapping):
        return None
    type_line = data.get("type_line")
    if not isinstance(type_line, str) or not type_line.strip():
        return None
    try:
        parts = host._type_parts(type_line)
    except (AttributeError, TypeError, ValueError):
        return None
    if not isinstance(parts, tuple) or len(parts) != 3:
        return None
    card_types = parts[0]
    if not isinstance(card_types, (set, frozenset)) or any(
        not isinstance(value, str) or not value.strip()
        for value in card_types
    ):
        return None
    return frozenset(value.casefold() for value in card_types)


def activation_condition_status(
    host: ActivationConditionHost,
    seat: str,
    ability: ActivatedAbility,
    source: Any | None = None,
) -> tuple[str, str | None]:
    """Evaluate the closed activation-condition grammar without mutation."""

    effect = ability.effect_text.casefold()
    if (
        "activate only during your turn" in effect
        and host.state.active_player != seat
    ):
        return "unavailable", "only_during_your_turn"
    if "only once each turn" in effect:
        if source is None:
            return "unresolved", "activation_source_required"
        activations = dict(
            source.annotations.get("once_per_turn_activations", {})
        )
        if activations.get(ability.ability_id) == host.state.turn_sequence:
            return "unavailable", "already_activated_this_turn"
    if "activate only if" not in effect:
        return "payable", None
    if "created a token this turn" in effect:
        created = int(
            host.state.players[seat].stats.get(
                "tokens_created_by_turn", {}
            ).get(str(host.state.turn_sequence), 0)
        )
        return (
            ("payable", None)
            if created > 0
            else ("unavailable", "requires_token_created_this_turn")
        )
    if "activate only if it's not your turn" in effect:
        return (
            ("unavailable", "only_during_another_players_turn")
            if host.state.active_player == seat
            else ("payable", None)
        )
    if "activate only if you control an artifact" in effect:
        controls_artifact = False
        for object_id in host.state.players[seat].zones["battlefield"]:
            permanent = host.state.cards[object_id]
            if permanent.controller != seat or permanent.phased_out:
                continue
            card_types = _effective_card_types(host, object_id)
            if card_types is None:
                return "unresolved", "malformed_effective_type_line"
            controls_artifact = controls_artifact or "artifact" in card_types
        return (
            ("payable", None)
            if controls_artifact
            else ("unavailable", "requires_controlled_artifact")
        )
    if (
        "activate only if there are four or more card types among "
        "cards in your graveyard"
    ) in effect:
        card_types: set[str] = set()
        for object_id in host.state.players[seat].zones["graveyard"]:
            object_types = _effective_card_types(host, object_id)
            if object_types is None:
                return "unresolved", "malformed_effective_type_line"
            card_types.update(object_types)
        return (
            ("payable", None)
            if len(card_types) >= 4
            else ("unavailable", "requires_delirium")
        )
    match = re.search(
        r"activate only if you control "
        rf"(?P<count>{_COUNT_PATTERN}) "
        r"or more (?P<kind>artifacts?|creatures?|lands?)",
        effect,
    )
    if match is None:
        return "unresolved", "unresolved_activation_condition"
    raw_count = match.group("count")
    required = (
        int(raw_count) if raw_count.isdigit() else _COUNT_WORDS[raw_count]
    )
    kind = match.group("kind").removesuffix("s")
    controlled = 0
    for object_id in host.state.players[seat].zones["battlefield"]:
        permanent = host.state.cards[object_id]
        if permanent.controller != seat or permanent.phased_out:
            continue
        card_types = _effective_card_types(host, permanent)
        if card_types is None:
            return "unresolved", "malformed_effective_type_line"
        if kind in card_types:
            controlled += 1
    if controlled < required:
        return "unavailable", f"requires_{required}_{kind}s"
    return "payable", None


__all__ = ["ActivationConditionHost", "activation_condition_status"]
