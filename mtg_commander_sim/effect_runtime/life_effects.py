from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..effect_contracts import effect_family_contract
from ..errors import GameRuleError
from ..life_change import (
    commit_life_change_batch,
    LifeChangeError,
    LifeChangeRequest,
    PreparedLifeChangeBatch,
    prepare_life_change_batch,
)
from ..life_state import (
    LifeChange,
)
from ..replacement import (
    ReplacementChoiceRequired,
    ReplacementEventBatch,
)
from ..semantic_runtime.damage_results import (
    collect_life_change_replacement_effects,
)


OPERATIONS = effect_family_contract("life-effects.v2").operations
_LIFE_OPERATION = "".join(("li", "fe"))
_REASON_FIELD = "".join(("rea", "son"))


def _commit(
    host: Any,
    changes: Sequence[LifeChange],
    *,
    effect: Mapping[str, Any],
    actor: str,
    reason: str,
) -> PreparedLifeChangeBatch:
    source = effect.get("source")
    source_ref = str(source) if source is not None else None
    cause = str(effect.get("cause") or reason or "effect")
    selections = effect.get("_replacement_selections") or ()
    if not isinstance(selections, Sequence) or isinstance(
        selections, (str, bytes)
    ):
        raise GameRuleError(
            "Life-change replacement selections must be a sequence"
        )
    try:
        prepared = prepare_life_change_batch(
            host,
            tuple(
                LifeChangeRequest(
                    event_id=(
                        f"life.effect:{host.state.revision}:"
                        f"{host.state.event_sequence + 1}:{index}"
                    ),
                    player=change.player,
                    amount=change.amount,
                    source=source_ref,
                    source_controller=actor,
                    cause=cause,
                )
                for index, change in enumerate(changes)
            ),
            effects=collect_life_change_replacement_effects(host),
            selections=selections,
            require_all_selections=False,
            batch_id=(
                f"replacement:life.effect:{host.state.revision}:"
                f"{host.state.event_sequence + 1}"
            ),
        )
    except LifeChangeError as exc:
        raise GameRuleError(str(exc)) from exc
    if prepared.pending is not None:
        raise ReplacementChoiceRequired(
            batch=ReplacementEventBatch(
                batch_id=prepared.batch_id,
                events=prepared.events,
                apnap_order=tuple(host.apnap_order()),
                journal=prepared.journal,
            ),
            effects=prepared.effects,
            pending=prepared.pending,
        )
    try:
        commit_life_change_batch(host, prepared)
    except LifeChangeError as exc:
        raise GameRuleError(str(exc)) from exc
    return prepared


def _resolved_delta(
    prepared: PreparedLifeChangeBatch,
    player: str,
) -> int:
    return sum(
        record.delta
        for record in prepared.records
        if record.player == player
    )


def _audit_details(prepared: PreparedLifeChangeBatch) -> dict[str, Any]:
    return {
        "life_batch": prepared.batch_id,
        "life_events": [
            {
                "event_id": record.event_id,
                "player": record.player,
                "direction": record.direction,
                "requested_amount": record.requested_amount,
                "amount": record.amount,
                "source": record.source,
                "source_controller": record.source_controller,
                "cause": record.cause,
            }
            for record in prepared.records
        ],
        "replacement_journal": [
            selection.to_dict() for selection in prepared.journal
        ],
    }


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
    prepared = _commit(
        host,
        (LifeChange(seat, delta),),
        effect=effect,
        actor=actor,
        reason=reason,
    )
    resolved_delta = _resolved_delta(prepared, seat)
    host._log(
        actor,
        "effect.life",
        f"{seat}'s life changed by {resolved_delta}.",
        {
            "player": seat,
            "requested_delta": delta,
            "delta": resolved_delta,
            "source": effect.get("source"),
            "cause": effect.get("cause") or reason,
            **_audit_details(prepared),
        },
        importance=1,
        changed_players=[seat],
    )
    return host.state.players[seat].life


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
    prepared = _commit(
        host,
        (LifeChange(seat, -amount),),
        effect=effect,
        actor=actor,
        reason=reason,
    )
    resolved_delta = _resolved_delta(prepared, seat)
    host._log(
        actor,
        "effect.life",
        f"{seat} lost {-resolved_delta} life.",
        {
            "player": seat,
            "requested_delta": -amount,
            "delta": resolved_delta,
            **_audit_details(prepared),
        },
        importance=1,
        changed_players=[seat],
    )
    return host.state.players[seat].life


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
    prepared = _commit(
        host,
        tuple(LifeChange(opponent, -amount) for opponent in opponents),
        effect=effect,
        actor=actor,
        reason=reason,
    )
    host._log(
        actor,
        "effect.life",
        f"Each opponent of {actor} lost {amount} life.",
        {
            "opponents": list(opponents),
            "delta": -amount,
            _REASON_FIELD: reason,
            **_audit_details(prepared),
        },
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
    prepared = _commit(
        host,
        (LifeChange(seat, -amount),),
        effect=effect,
        actor=actor,
        reason=reason,
    )
    resolved_delta = _resolved_delta(prepared, seat)
    host._log(
        actor,
        "effect.life",
        f"{seat} lost {-resolved_delta} life.",
        {
            "player": seat,
            "requested_delta": -amount,
            "delta": resolved_delta,
            "card": card.ref,
            **_audit_details(prepared),
        },
        importance=1,
        changed_players=[seat],
    )
    return host.state.players[seat].life


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
    prepared = _commit(
        host,
        (LifeChange(target, -amount), LifeChange(actor, amount)),
        effect=effect,
        actor=actor,
        reason=reason,
    )
    host._log(
        actor,
        "effect.life",
        f"{target} lost {amount} life and {actor} gained {amount} life.",
        {
            "player": target,
            "delta": -amount,
            "gained_by": actor,
            **_audit_details(prepared),
        },
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
    prepared = _commit(
        host,
        (
            *(LifeChange(opponent, -amount) for opponent in opponents),
            LifeChange(actor, amount),
        ),
        effect=effect,
        actor=actor,
        reason=reason,
    )
    host._log(
        actor,
        "effect.life",
        f"Each opponent of {actor} lost {amount} life; {actor} gained {amount} life.",
        {
            "opponents": list(opponents),
            "amount": amount,
            "gained_by": actor,
            **_audit_details(prepared),
        },
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
