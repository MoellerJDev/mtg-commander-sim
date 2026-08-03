from __future__ import annotations

from typing import Any, Mapping

from ..damage import DamageError, recipient_snapshot
from ..damage_modifier_state import (
    DamageModifierDuration,
    DamageRedirectionEffect,
    DamageSubject,
    PreventionMode,
)
from ..damage_prevention_creation import (
    DamagePreventionCreationError,
    GainLifeAftermathRequest,
    PlaceCountersAftermathRequest,
    PreventionShieldCreationRequest,
    PreventionSubjectAllocation,
    commit_prevention_shield_creation,
    pin_chosen_damage_source,
    plan_prevention_shield_creation,
)
from ..effect_contracts import effect_family_contract
from ..errors import GameRuleError


OPERATIONS = effect_family_contract("damage-modifiers.v1").operations
_REASON_FIELD = "".join(("rea", "son"))


def _damage_subject(snapshot: Any) -> DamageSubject:
    return DamageSubject(
        ref=snapshot.ref,
        kind=snapshot.kind,
        controller=snapshot.controller,
        object_id=snapshot.object_id,
        logical_object_id=snapshot.logical_object_id,
        owner=snapshot.owner,
    )


def _positive_amount(value: Any, *, field: str) -> int:
    if type(value) is not int or value < 1:
        raise GameRuleError(f"{field} must be a positive integer")
    return value


def _selected_prevention_subjects(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    mode: PreventionMode,
) -> tuple[PreventionSubjectAllocation, ...]:
    amount = effect.get("amount") if mode == PreventionMode.AMOUNT else None
    if mode == PreventionMode.AMOUNT:
        amount = _positive_amount(amount, field="Prevention amount")
    raw_allocations = effect.get("allocations")
    if raw_allocations is not None:
        if mode != PreventionMode.AMOUNT or not isinstance(
            raw_allocations, Mapping
        ):
            raise GameRuleError(
                "Divided prevention requires an amount-shield allocation object"
            )
        if effect.get("subjects") is not None or effect.get("selector") is not None:
            raise GameRuleError(
                "Divided prevention cannot also declare subjects or a selector"
            )
        allocations = tuple(
            PreventionSubjectAllocation(
                str(ref), _positive_amount(value, field="Prevention allocation")
            )
            for ref, value in sorted(raw_allocations.items())
        )
        if not allocations or sum(value.amount or 0 for value in allocations) != amount:
            raise GameRuleError(
                "Divided prevention allocations must equal the resolved amount"
            )
        return allocations

    raw_subjects = effect.get("subjects")
    if raw_subjects is not None:
        if not isinstance(raw_subjects, (list, tuple)) or not raw_subjects:
            raise GameRuleError("Prevention subjects must be a nonempty array")
        refs = tuple(str(ref) for ref in raw_subjects)
        if any(not ref for ref in refs) or len(refs) != len(set(refs)):
            raise GameRuleError(
                "Prevention subjects must be unique nonempty references"
            )
        return tuple(PreventionSubjectAllocation(ref, amount) for ref in refs)

    selector = effect.get("selector")
    if selector is not None:
        if not isinstance(selector, Mapping) or set(selector) != {
            "kind",
            "anchor",
            "types_all",
        }:
            raise GameRuleError("The prevention subject selector is malformed")
        if selector["kind"] != "shares_color_with":
            raise GameRuleError("The prevention subject selector is unsupported")
        raw_types = selector["types_all"]
        if not isinstance(raw_types, (list, tuple)) or any(
            not isinstance(value, str) or not value for value in raw_types
        ):
            raise GameRuleError("The prevention subject selector types are malformed")
        anchor = host._resolve_object(
            actor,
            str(selector["anchor"]),
            zones={"battlefield"},
        )
        anchor_data = host._effective_card_data(anchor)
        anchor_colors = {
            str(value).upper() for value in anchor_data.get("colors", ())
        }
        if not anchor_colors:
            return ()
        required_types = {str(value).casefold() for value in raw_types}
        refs: list[str] = []
        for card in host.state.cards.values():
            if card.zone != "battlefield" or card.phased_out:
                continue
            data = host._effective_card_data(card)
            types, _subtypes, _supertypes = host._type_parts(
                str(data.get("type_line") or "")
            )
            colors = {str(value).upper() for value in data.get("colors", ())}
            if required_types.issubset(types) and anchor_colors.intersection(colors):
                refs.append(card.ref)
        return tuple(
            PreventionSubjectAllocation(ref, amount)
            for ref in sorted(set(refs))
        )

    subject_ref = str(effect.get("subject") or actor)
    return (PreventionSubjectAllocation(subject_ref, amount),)


def _prevention_aftermath_requests(
    effect: Mapping[str, Any],
    *,
    actor: str,
) -> tuple[GainLifeAftermathRequest | PlaceCountersAftermathRequest, ...]:
    raw = effect.get("aftermath")
    if raw is None:
        return ()
    values = raw if isinstance(raw, (list, tuple)) else (raw,)
    result: list[GainLifeAftermathRequest | PlaceCountersAftermathRequest] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise GameRuleError("Prevention aftermath entries must be objects")
        kind = value.get("kind")
        common = {"kind", "per_prevented", "fixed_amount"}
        if kind == "gain_life":
            if set(value) != common | {"player"}:
                raise GameRuleError("Prevention life aftermath is malformed")
            result.append(
                GainLifeAftermathRequest(
                    player=str(value["player"]),
                    per_prevented=value["per_prevented"],
                    fixed_amount=value["fixed_amount"],
                )
            )
            continue
        if kind == "place_counters":
            expected = common | {
                "counter_name",
                "placing_player",
                "subject",
            }
            if set(value) != expected:
                raise GameRuleError("Prevention counter aftermath is malformed")
            result.append(
                PlaceCountersAftermathRequest(
                    subject_ref=(
                        str(value["subject"])
                        if value["subject"] is not None
                        else None
                    ),
                    counter_name=str(value["counter_name"]),
                    placing_player=str(value.get("placing_player") or actor),
                    per_prevented=value["per_prevented"],
                    fixed_amount=value["fixed_amount"],
                )
            )
            continue
        raise GameRuleError("The prevention aftermath kind is unsupported")
    return tuple(result)


def _apply_create_damage_prevention_shield(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> str | list[str]:
    del operation
    try:
        mode = PreventionMode(str(effect.get("mode") or "amount"))
        duration = DamageModifierDuration(
            str(effect.get("duration") or "until_end_of_turn")
        )
        if mode == PreventionMode.AMOUNT and effect.get("amount") == 0:
            return []
        request = PreventionShieldCreationRequest(
            source_id=str(effect.get("source") or reason),
            controller=actor,
            mode=mode,
            duration=duration,
            subjects=_selected_prevention_subjects(
                host, effect, actor=actor, mode=mode
            ),
            chosen_source_ref=(
                str(effect["chosen_source"])
                if effect.get("chosen_source") is not None
                else None
            ),
            required_source_colors=tuple(
                str(value) for value in effect.get("source_colors") or ()
            ),
            required_source_types=tuple(
                str(value) for value in effect.get("source_types") or ()
            ),
            label=str(effect.get("label") or reason),
            aftermath=_prevention_aftermath_requests(effect, actor=actor),
        )
        plan = plan_prevention_shield_creation(host, request)
        shields = commit_prevention_shield_creation(host, plan)
    except (DamageError, DamagePreventionCreationError, ValueError) as exc:
        raise GameRuleError(str(exc)) from exc
    for shield in shields:
        host._log(
            actor,
            "damage.prevention.created",
            f"{shield.source_id} created a damage-prevention shield.",
            {
                "shield_id": shield.shield_id,
                "subject": shield.subject.ref,
                "mode": shield.mode.value,
                "remaining": shield.remaining,
                "duration": shield.duration.value,
                _REASON_FIELD: reason,
            },
            importance=2,
            changed_players=[shield.subject.controller],
            changed_objects=(
                [shield.subject.object_id]
                if shield.subject.object_id is not None
                else []
            ),
        )
    ids = [shield.shield_id for shield in shields]
    return ids[0] if len(ids) == 1 else ids


def _apply_create_damage_redirection(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> str:
    del operation
    consume = effect.get("consume_on_application", True)
    if type(consume) is not bool:
        raise GameRuleError("Damage redirection consumption must be boolean")
    try:
        subject = _damage_subject(
            recipient_snapshot(
                host,
                str(effect.get("subject") or actor),
                actor=actor,
            )
        )
        destination = _damage_subject(
            recipient_snapshot(
                host,
                str(effect.get("destination") or ""),
                actor=actor,
            )
        )
        redirection = DamageRedirectionEffect(
            redirection_id=host._next_ref("DR"),
            source_id=str(effect.get("source") or reason),
            controller=actor,
            subject=subject,
            destination=destination,
            duration=DamageModifierDuration(
                str(effect.get("duration") or "until_end_of_turn")
            ),
            created_turn_sequence=host.state.turn_sequence,
            chosen_source=pin_chosen_damage_source(
                host,
                source_ref=(
                    str(effect["chosen_source"])
                    if effect.get("chosen_source") is not None
                    else None
                ),
                controller=actor,
                required_colors=tuple(effect.get("source_colors") or ()),
                required_types=tuple(effect.get("source_types") or ()),
            ),
            consume_on_application=consume,
            label=str(effect.get("label") or reason),
        )
    except (DamageError, DamagePreventionCreationError, ValueError) as exc:
        raise GameRuleError(str(exc)) from exc
    host.state.damage_redirections.append(redirection)
    host._log(
        actor,
        "damage.redirection.created",
        f"{redirection.source_id} created a damage-redirection effect.",
        {
            "redirection_id": redirection.redirection_id,
            "subject": redirection.subject.ref,
            "destination": redirection.destination.ref,
            "duration": redirection.duration.value,
            _REASON_FIELD: reason,
        },
        importance=2,
        changed_players=[
            redirection.subject.controller,
            redirection.destination.controller,
        ],
        changed_objects=[
            value
            for value in (
                redirection.subject.object_id,
                redirection.destination.object_id,
            )
            if value is not None
        ],
    )
    return redirection.redirection_id


HANDLERS = {
    "create_damage_prevention_shield": _apply_create_damage_prevention_shield,
    "create_damage_redirection": _apply_create_damage_redirection,
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


__all__ = ["HANDLERS", "OPERATIONS", "apply_effect"]
