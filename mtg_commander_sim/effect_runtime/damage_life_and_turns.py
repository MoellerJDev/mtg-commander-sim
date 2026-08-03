from __future__ import annotations

from typing import Any, Mapping

from ..damage import (
    DamageError,
    damage_proposal,
    recipient_snapshot,
    resolve_damage_batch,
    source_snapshot,
)
from ..damage_prevention import (
    ChosenDamageSource,
    DamageModifierDuration,
    DamagePreventionShield,
    DamageRedirectionEffect,
    DamageSubject,
    PreventionMode,
)
from ..errors import GameRuleError
from ..effect_contracts import effect_family_contract
from ..semantic_runtime.intents import PlaceCountersIntent


OPERATIONS = effect_family_contract("damage-life-and-turns.v1").operations


def _apply_damage(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    target = str(effect["target"])
    amount = int(effect.get("amount", 0))
    if amount < 0:
        raise GameRuleError("Damage cannot be negative")
    if amount == 0:
        return 0
    try:
        replacement_event_ids = list(
            effect.get("_replacement_event_ids") or ()
        )
        if replacement_event_ids and len(replacement_event_ids) != 1:
            raise GameRuleError(
                "Damage replacement event identity count is stale"
            )
        proposal = damage_proposal(
            host,
            proposal_id=(
                str(replacement_event_ids[0])
                if replacement_event_ids
                else (
                    f"damage.effect:{host.state.revision}:"
                    f"{host.state.event_sequence + 1}:0"
                )
            ),
            actor=actor,
            source_ref=(
                str(effect["source"])
                if effect.get("source") is not None
                else None
            ),
            target=target,
            amount=amount,
            combat=False,
            reason=reason,
            unpreventable=bool(effect.get("unpreventable", False)),
            deathtouch=bool(effect.get("deathtouch", False)),
        )
        result = resolve_damage_batch(
            host,
            (proposal,),
            replacement_selections=tuple(
                effect.get("_replacement_selections") or ()
            ),
        )
    except DamageError as exc:
        raise GameRuleError(str(exc)) from exc
    event = result.events[0]
    host._log(
        actor,
        (
            "effect.damage"
            if event.was_dealt
            else "effect.damage.prevented"
        ),
        (
            f"{event.target} took {event.dealt_amount} damage."
            if event.was_dealt
            else f"Damage to {event.target} was prevented."
        ),
        {
            "source": event.source,
            "target": event.target,
            "assigned_amount": event.assigned_amount,
            "amount": event.dealt_amount,
            "prevented_amount": event.prevented_amount,
            "reason": reason,
            "applied_effects": list(event.applied_effects),
            "damage_event": event.semantic_context(),
        },
        importance=2,
        changed_objects=result.changed_objects,
        changed_players=result.changed_players,
    )
    return event.dealt_amount



def _apply_damage_each_opponent(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    amount = int(effect.get("amount", 0))
    if amount < 0:
        raise GameRuleError("Damage cannot be negative")
    if amount == 0:
        return 0
    opponents = [
        seat
        for seat in host.active_seats
        if seat != actor
    ]
    try:
        replacement_event_ids = list(
            effect.get("_replacement_event_ids") or ()
        )
        if replacement_event_ids and len(replacement_event_ids) != len(
            opponents
        ):
            raise GameRuleError(
                "Damage replacement event identity count is stale"
            )
        proposals = tuple(
            damage_proposal(
                host,
                proposal_id=(
                    str(replacement_event_ids[index])
                    if replacement_event_ids
                    else (
                        f"damage.effect:{host.state.revision}:"
                        f"{host.state.event_sequence + 1}:{index}"
                    )
                ),
                actor=actor,
                source_ref=(
                    str(effect["source"])
                    if effect.get("source") is not None
                    else None
                ),
                target=opponent,
                amount=amount,
                combat=False,
                reason=reason,
                unpreventable=bool(
                    effect.get("unpreventable", False)
                ),
            )
            for index, opponent in enumerate(opponents)
        )
        result = resolve_damage_batch(
            host,
            proposals,
            replacement_selections=tuple(
                effect.get("_replacement_selections") or ()
            ),
        )
    except DamageError as exc:
        raise GameRuleError(str(exc)) from exc
    host._log(
        actor,
        "effect.damage",
        f"Each opponent of {actor} was dealt damage.",
        {
            "opponents": opponents,
            "assigned_amount": amount,
            "dealt_amount": result.dealt_amount,
            "reason": reason,
            "damage_events": [
                event.semantic_context() for event in result.events
            ],
        },
        importance=2,
        changed_players=result.changed_players,
    )
    return result.dealt_amount


def _damage_subject(snapshot: Any) -> DamageSubject:
    return DamageSubject(
        ref=snapshot.ref,
        kind=snapshot.kind,
        controller=snapshot.controller,
        object_id=snapshot.object_id,
        logical_object_id=snapshot.logical_object_id,
        owner=snapshot.owner,
    )


def _chosen_damage_source(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
) -> ChosenDamageSource | None:
    chosen_ref = effect.get("chosen_source")
    if chosen_ref is None:
        return None
    snapshot = source_snapshot(host, str(chosen_ref), controller=actor)
    if snapshot.object_id.startswith("unrepresented:"):
        raise GameRuleError(
            "A chosen damage source must have authoritative object identity"
        )
    return ChosenDamageSource(
        ref=snapshot.ref,
        object_id=snapshot.object_id,
        required_colors=tuple(
            str(value) for value in effect.get("source_colors") or ()
        ),
        required_types=tuple(
            str(value) for value in effect.get("source_types") or ()
        ),
    )


def _apply_create_damage_prevention_shield(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> str:
    del operation
    subject_ref = str(effect.get("subject") or actor)
    try:
        subject = (
            DamageSubject(ref="*", kind="any", controller=actor)
            if subject_ref == "*"
            else _damage_subject(
                recipient_snapshot(host, subject_ref, actor=actor)
            )
        )
        mode = PreventionMode(str(effect.get("mode") or "amount"))
        duration = DamageModifierDuration(
            str(effect.get("duration") or "until_end_of_turn")
        )
        remaining = effect.get("amount") if mode == PreventionMode.AMOUNT else None
        shield = DamagePreventionShield(
            shield_id=host._next_ref("PS"),
            source_id=str(effect.get("source") or reason),
            controller=actor,
            subject=subject,
            mode=mode,
            remaining=remaining,
            duration=duration,
            created_turn_sequence=host.state.turn_sequence,
            chosen_source=_chosen_damage_source(host, effect, actor=actor),
            label=str(effect.get("label") or reason),
        )
    except (DamageError, ValueError) as exc:
        raise GameRuleError(str(exc)) from exc
    if any(
        existing.shield_id == shield.shield_id
        for existing in host.state.damage_prevention_shields
    ):
        raise GameRuleError("Prevention shield identity collision")
    host.state.damage_prevention_shields.append(shield)
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
            **dict(reason=reason),
        },
        importance=2,
        changed_players=[subject.controller],
        changed_objects=(
            [subject.object_id] if subject.object_id is not None else []
        ),
    )
    return shield.shield_id


def _apply_create_damage_redirection(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> str:
    del operation
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
            chosen_source=_chosen_damage_source(host, effect, actor=actor),
            consume_on_application=bool(
                effect.get("consume_on_application", True)
            ),
            label=str(effect.get("label") or reason),
        )
    except (DamageError, ValueError) as exc:
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
            **dict(reason=reason),
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



def _apply_life(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    seat = str(effect.get("player") or actor)
    delta = int(effect.get("delta", 0))
    host.state.players[seat].life += delta
    host._log(actor, "effect.life", f"{seat}'s life changed by {delta}.", {"player": seat, "delta": delta}, importance=1, changed_players=[seat])
    return host.state.players[seat].life



def _apply_lose_life(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    seat = str(effect.get("player") or actor)
    amount = max(0, int(effect.get("amount", 0)))
    host.state.players[seat].life -= amount
    host._log(
        actor,
        "effect.life",
        f"{seat} lost {amount} life.",
        {"player": seat, "delta": -amount},
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
) -> Any:
    op = operation
    amount = max(0, int(effect.get("amount", 0)))
    opponents = [
        seat
        for seat in host.active_seats
        if seat != actor
    ]
    for opponent in opponents:
        host.state.players[opponent].life -= amount
    host._log(
        actor,
        "effect.life",
        f"Each opponent of {actor} lost {amount} life.",
        {
            "opponents": opponents,
            "delta": -amount,
            "reason": reason,
        },
        importance=2,
        changed_players=opponents,
    )
    return amount



def _apply_lose_life_equal_mana_value(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    seat = str(effect.get("player") or actor)
    card = host._resolve_object(actor, str(effect["card"]))
    record = host.card_record(card)
    amount = int(record.mana_value if record else 0)
    host.state.players[seat].life -= amount
    host._log(
        actor,
        "effect.life",
        f"{seat} lost {amount} life.",
        {
            "player": seat,
            "delta": -amount,
            "card": card.ref,
        },
        importance=1,
        changed_players=[seat],
    )
    return host.state.players[seat].life



def _apply_energy(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    seat = str(effect.get("player") or actor)
    delta = int(effect.get("delta", 0))
    host.state.players[seat].energy += delta
    host._log(actor, "effect.energy", f"{seat}'s energy changed by {delta}.", {"player": seat, "delta": delta}, importance=1, changed_players=[seat])
    return host.state.players[seat].energy



def _apply_drain_opponent(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    target = str(effect["target"])
    amount = int(effect.get("amount", 1))
    if target not in host.active_seats or target == actor:
        raise GameRuleError("Drain effect requires an active opponent")
    host.state.players[target].life -= amount
    host.state.players[actor].life += amount
    host._log(
        actor,
        "effect.life",
        f"{target} lost {amount} life and {actor} gained {amount}.",
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
) -> Any:
    op = operation
    amount = int(effect.get("amount", 1))
    opponents = [
        seat
        for seat in host.active_seats
        if seat != actor
    ]
    for opponent in opponents:
        host.state.players[opponent].life -= amount
    host.state.players[actor].life += amount
    host._log(
        actor,
        "effect.life",
        f"Each opponent of {actor} lost {amount} life; "
        f"{actor} gained {amount} life.",
        {
            "opponents": opponents,
            "amount": amount,
            "gained_by": actor,
        },
        importance=2,
        changed_players=[actor, *opponents],
    )
    return amount



def _apply_create_treasure(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    return host.create_token(
        str(effect.get("controller") or actor),
        name="Treasure",
        characteristics={
            "type_line": "Token Artifact — Treasure",
            "oracle_text": "{T}, Sacrifice this token: Add one mana of any color.",
        },
        reason=reason,
    )



def _apply_create_modified_token_copy(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    controller = str(effect.get("controller") or actor)
    created = host.create_token(
        controller,
        name=str(effect.get("name") or ""),
        copy_of=str(effect["card"]),
        characteristics=dict(effect.get("characteristics") or {}),
        temporary_keywords=tuple(effect.get("temporary_keywords") or ()),
        reason=reason,
    )
    if not effect.get("sacrifice_on_controller_end_step"):
        return created
    for ref in created:
        token = host._resolve_object(
            actor, ref, zones={"battlefield"}, controlled_only=True
        )
        host.schedule_delayed_trigger(
            controller=controller,
            label=f"Sacrifice {token.ref}",
            event_kind="step.begin",
            condition={
                "phase": "ending",
                "step": "end_step",
                "player": "$controller",
            },
            stack_template={
                "label": f"Sacrifice {token.ref}",
                "semantic_key": "builtin:sacrifice-source",
            },
            source_object_id=token.object_id,
            once=True,
        )
    return created



def _apply_create_token_if_distinct_controlled_names(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    required_type = str(effect.get("required_type") or "land").casefold()
    names = {
        host.display_name(object_id)
        for object_id in host.state.players[actor].zones["battlefield"]
        if host.state.cards[object_id].controller == actor
        and host.card_record(object_id)
        and required_type
        in host._type_parts(
            str(host._effective_card_data(object_id).get("type_line") or "")
        )[0]
    }
    if len(names) < int(effect.get("minimum_distinct_names", 1)):
        return []
    token = dict(effect.get("token") or {})
    return host.create_token(
        str(effect.get("controller") or actor),
        name=str(token.get("name") or ""),
        quantity=int(token.get("quantity", 1)),
        characteristics=dict(token.get("characteristics") or {}),
        reason=reason,
    )



def _apply_create_token_copy_if_controlled_count(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    controller = str(effect.get("controller") or actor)
    required_type = str(effect.get("required_type") or "land").casefold()
    count = sum(
        1
        for object_id in host.state.players[
            controller
        ].zones["battlefield"]
        if host.state.cards[object_id].controller == controller
        and required_type
        in host._type_parts(
            str(
                host._effective_card_data(object_id).get(
                    "type_line"
                )
                or ""
            )
        )[0]
    )
    if count >= int(effect.get("threshold", 1)):
        return host.create_token(
            controller,
            name=str(effect.get("copy_name") or ""),
            copy_of=str(effect["copy_of"]),
            reason=reason,
        )
    fallback = dict(effect.get("fallback_token") or {})
    return host.create_token(
        controller,
        name=str(fallback.get("name") or ""),
        quantity=int(fallback.get("quantity", 1)),
        characteristics=dict(fallback.get("characteristics") or {}),
        reason=reason,
    )



def _apply_counter_or_destroy_blue(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    target = str(effect["target"])
    stack_item = next(
        (
            candidate
            for candidate in host.state.stack
            if candidate.ref == target
        ),
        None,
    )
    if stack_item is not None:
        if not stack_item.card_object_id:
            return None
        record = host.card_record(stack_item.card_object_id)
        if not record or "U" not in record.colors:
            return None
        return host._counter_stack_item(
            target,
            reason="Red/Pyroblast semantic",
            countered_by=actor,
        ).ref
    try:
        card = host._resolve_object(
            actor, target, zones={"battlefield"}
        )
    except GameRuleError:
        return None
    record = host.card_record(card)
    if not record or "U" not in record.colors:
        return None
    host.move_card(
        card.object_id,
        "graveyard",
        reason="Red/Pyroblast semantic",
        semantic_events=True,
    )
    return card.ref



def _apply_sacrifice_if_present(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    value = effect.get("card")
    if not value:
        return None
    try:
        card = host._resolve_object(
            actor, str(value), zones={"battlefield"}
        )
    except GameRuleError:
        return None
    host.move_card(
        card.object_id,
        "graveyard",
        reason=reason,
        semantic_events=True,
    )
    return card.ref



def _apply_counter_stack(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    return host._counter_stack_item(
        str(effect["stack"]),
        destination=str(effect.get("destination") or "graveyard"),
        reason=reason,
        countered_by=actor,
    ).ref



def _apply_extra_turn(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    return host.schedule_extra_turn(str(effect.get("player") or actor), source=str(effect.get("source") or reason)).turn_id



def _apply_control_next_turn(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    target = str(effect.get("player") or "")
    if target not in host.active_seats:
        raise GameRuleError(
            "Turn-control effect requires an active player"
        )
    host.state.players[target].stats[
        "next_turn_controlled_by"
    ] = actor
    host._log(
        actor,
        "turn.control.scheduled",
        (
            f"{actor} will control {target} during that "
            "player's next turn."
        ),
        {
            "controller": actor,
            "player": target,
            "reason": reason,
        },
        importance=3,
        changed_players=[actor, target],
    )
    return target



def _apply_protection_from_everything_until_next_turn(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    seat = str(effect.get("player") or actor)
    host._require_seat(seat, in_game=True)
    host.state.players[seat].stats[
        "protection_from_everything_until_next_turn"
    ] = True
    host._log(
        actor,
        "player.protection",
        (
            f"{seat} gained protection from everything until "
            "their next turn."
        ),
        {
            "player": seat,
            "duration": "until_next_turn",
            "reason": reason,
        },
        importance=2,
        changed_players=[seat],
    )
    return seat



def _apply_end_turn(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    host._end_turn_now(actor=actor, reason=reason)
    return None



def _apply_create_emblem(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    controller = str(effect.get("controller") or actor)
    result = host.create_emblem(
        controller,
        abilities=tuple(str(value) for value in effect.get("abilities") or ()),
        display_label=str(effect.get("display_label") or "Emblem"),
        semantic_key=str(effect.get("semantic_key") or ""),
        reason=reason,
    )
    stats_counter = str(effect.get("stats_counter") or "")
    if stats_counter:
        player = host.state.players[controller]
        player.stats[stats_counter] = (
            int(player.stats.get(stats_counter, 0)) + 1
        )
    return result



def _apply_grant_ability_marker(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    source = host._resolve_object(
        actor,
        str(effect.get("source") or ""),
        zones={"battlefield"},
        controlled_only=True,
    )
    marker = str(effect.get("marker") or "").strip()
    if not marker:
        raise GameRuleError("Ability markers require a stable marker")
    source.annotations[marker] = True
    host._log(
        actor,
        "saga.ability.gained",
        f"{source.ref} gained an ability marker.",
        {
            "source": source.ref,
            "marker": marker,
            "reason": reason,
        },
        importance=2,
        changed_objects=[source.object_id],
        changed_players=[actor],
    )
    return marker



def _apply_return_transformed(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    source = host._resolve_object(
        actor,
        str(effect.get("card") or effect.get("source") or ""),
        zones={"exile"},
    )
    record = host.card_record(source)
    if record is None or len(record.faces) < 2:
        raise GameRuleError(
            "Return transformed requires a transforming card"
        )
    host.move_card(
        source.object_id,
        "battlefield",
        controller=source.owner,
        enter_face=str(record.faces[1].get("name") or ""),
        reason=reason,
        semantic_events=True,
    )
    return source.ref



def _apply_destroy_selected_and_reward_source(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    op = operation
    source = host._resolve_object(
        actor,
        str(effect.get("source") or ""),
    )
    changes: list[tuple[str, str]] = []
    destroyed_controlled = False
    for raw_ref in effect.get("cards") or []:
        if raw_ref is None:
            continue
        try:
            creature = host._resolve_object(
                actor,
                str(raw_ref),
                zones={"battlefield"},
            )
        except GameRuleError:
            continue
        types, _, _ = host._type_parts(
            str(
                host._effective_card_data(creature).get(
                    "type_line"
                )
                or ""
            )
        )
        keywords = {
            str(value).casefold()
            for value in host._effective_card_data(creature).get(
                "keywords", []
            )
        }
        if (
            "creature" not in types
            or "indestructible" in keywords
        ):
            continue
        destroyed_controlled = (
            destroyed_controlled
            or creature.controller == actor
        )
        changes.append((creature.object_id, "graveyard"))
    if changes:
        host._move_cards_simultaneously(
            changes,
            reason=reason,
            log=True,
        )
    if (
        destroyed_controlled
        and source.zone == "battlefield"
        and source.controller == actor
    ):
        counter_name = str(effect.get("counter") or "+1/+1")
        counter_amount = int(effect.get("counter_amount", 0))
        host.place_counters_intent(
            PlaceCountersIntent(
                actor=actor,
                object_refs=(source.ref,),
                counter_name=counter_name,
                amount=counter_amount,
                reason=reason,
                source_ref=source.ref,
            )
        )
    return [
        host.state.cards[object_id].ref
        for object_id, _ in changes
    ]


HANDLERS = {
    'control_next_turn': _apply_control_next_turn,
    'counter_or_destroy_blue': _apply_counter_or_destroy_blue,
    'counter_stack': _apply_counter_stack,
    'create_emblem': _apply_create_emblem,
    'create_damage_prevention_shield': _apply_create_damage_prevention_shield,
    'create_damage_redirection': _apply_create_damage_redirection,
    'create_treasure': _apply_create_treasure,
    'create_modified_token_copy': _apply_create_modified_token_copy,
    'create_token_copy_if_controlled_count': _apply_create_token_copy_if_controlled_count,
    'create_token_if_distinct_controlled_names': _apply_create_token_if_distinct_controlled_names,
    'damage': _apply_damage,
    'damage_each_opponent': _apply_damage_each_opponent,
    'destroy_selected_and_reward_source': _apply_destroy_selected_and_reward_source,
    'drain_each_opponent': _apply_drain_each_opponent,
    'drain_opponent': _apply_drain_opponent,
    'end_turn': _apply_end_turn,
    'energy': _apply_energy,
    'extra_turn': _apply_extra_turn,
    'grant_ability_marker': _apply_grant_ability_marker,
    'life': _apply_life,
    'lose_life': _apply_lose_life,
    'lose_life_each_opponent': _apply_lose_life_each_opponent,
    'lose_life_equal_mana_value': _apply_lose_life_equal_mana_value,
    'protection_from_everything_until_next_turn': _apply_protection_from_everything_until_next_turn,
    'return_transformed': _apply_return_transformed,
    'sacrifice_if_present': _apply_sacrifice_if_present,
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
        raise GameRuleError(
            f"Unsupported owned effect {operation!r}"
        )
    return handler(
        host,
        effect,
        actor=actor,
        operation=operation,
        reason=reason,
    )
