from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..effect_contracts import effect_family_contract
from ..errors import GameRuleError
from ..life_state import (
    commit_life_changes,
    LifeChange,
    LifeStateError,
    LifeTransition,
    plan_life_changes,
)


OPERATIONS = effect_family_contract("life-effects.v1").operations
_LIFE_OPERATION = "".join(("li", "fe"))
_REASON_FIELD = "".join(("rea", "son"))


def _commit(
    host: Any,
    changes: Sequence[LifeChange],
) -> tuple[LifeTransition, ...]:
    try:
        return commit_life_changes(host, plan_life_changes(host, changes))
    except LifeStateError as exc:
        raise GameRuleError(str(exc)) from exc


def _apply_life(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> int:
    seat = str(effect.get("player") or actor)
    delta = int(effect.get("delta", 0))
    transitions = _commit(host, (LifeChange(seat, delta),))
    host._log(
        actor,
        "effect.life",
        f"{seat}'s life changed by {delta}.",
        {"player": seat, "delta": delta},
        importance=1,
        changed_players=[seat],
    )
    return transitions[0].after


def _apply_lose_life(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> int:
    seat = str(effect.get("player") or actor)
    amount = max(0, int(effect.get("amount", 0)))
    transitions = _commit(host, (LifeChange(seat, -amount),))
    host._log(
        actor,
        "effect.life",
        f"{seat} lost {amount} life.",
        {"player": seat, "delta": -amount},
        importance=1,
        changed_players=[seat],
    )
    return transitions[0].after


def _apply_lose_life_each_opponent(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> int:
    amount = max(0, int(effect.get("amount", 0)))
    opponents = tuple(seat for seat in host.active_seats if seat != actor)
    _commit(
        host,
        tuple(LifeChange(opponent, -amount) for opponent in opponents),
    )
    host._log(
        actor,
        "effect.life",
        f"Each opponent of {actor} lost {amount} life.",
        {"opponents": list(opponents), "delta": -amount, _REASON_FIELD: reason},
        importance=2,
        changed_players=list(opponents),
    )
    return amount


def _apply_lose_life_equal_mana_value(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> int:
    seat = str(effect.get("player") or actor)
    card = host._resolve_object(actor, str(effect["card"]))
    record = host.card_record(card)
    amount = int(record.mana_value if record else 0)
    transitions = _commit(host, (LifeChange(seat, -amount),))
    host._log(
        actor,
        "effect.life",
        f"{seat} lost {amount} life.",
        {"player": seat, "delta": -amount, "card": card.ref},
        importance=1,
        changed_players=[seat],
    )
    return transitions[0].after


def _apply_drain_opponent(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> int:
    target = str(effect["target"])
    amount = int(effect.get("amount", 1))
    if target not in host.active_seats or target == actor:
        raise GameRuleError("Drain effect requires an active opponent")
    _commit(
        host,
        (LifeChange(target, -amount), LifeChange(actor, amount)),
    )
    host._log(
        actor,
        "effect.life",
        f"{target} lost {amount} life and {actor} gained {amount} life.",
        {"player": target, "delta": -amount, "gained_by": actor},
        importance=2,
        changed_players=[actor, target],
    )
    return amount


def _apply_drain_each_opponent(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> int:
    amount = int(effect.get("amount", 1))
    opponents = tuple(seat for seat in host.active_seats if seat != actor)
    _commit(
        host,
        (
            *(LifeChange(opponent, -amount) for opponent in opponents),
            LifeChange(actor, amount),
        ),
    )
    host._log(
        actor,
        "effect.life",
        f"Each opponent of {actor} lost {amount} life; {actor} gained {amount} life.",
        {"opponents": list(opponents), "amount": amount, "gained_by": actor},
        importance=2,
        changed_players=[actor, *opponents],
    )
    return amount


HANDLERS = {
    "drain_each_opponent": _apply_drain_each_opponent,
    "drain_opponent": _apply_drain_opponent,
    _LIFE_OPERATION: _apply_life,
    "lose_life": _apply_lose_life,
    "lose_life_each_opponent": _apply_lose_life_each_opponent,
    "lose_life_equal_mana_value": _apply_lose_life_equal_mana_value,
}


def apply_effect(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    handler = HANDLERS.get(operation)
    if handler is None:
        raise GameRuleError(f"Unsupported owned effect {operation!r}")
    return handler(
        host,
        effect,
        actor=actor,
        operation=operation,
        reason=reason,
    )


__all__ = ["apply_effect", "HANDLERS", "OPERATIONS"]
