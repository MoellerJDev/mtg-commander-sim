from __future__ import annotations

from dataclasses import replace
import re
from typing import Any, Mapping, Protocol

from ..model import GameState
from ..replacement.immutable import thaw_value
from ..semantic_runtime.context import SemanticNodeError
from ..semantic_runtime.draw_replacements import (
    DrawReplacementHost,
    collect_draw_instruction_replacement_effects,
    collect_draw_replacement_effects,
)
from ..semantic_runtime.draw_restrictions import current_draw_permission
from .continuation import DrawDecisionContinuation, DrawResume
from .model import (
    DrawError,
    DrawEventRequest,
    DrawInstructionRequest,
    PreparedDrawEvent,
    QueuedDraw,
    prepare_draw_event,
    prepare_draw_instruction,
    prepare_ordinary_draw,
)
from .transaction import DrawCommitHost, commit_prepared_draw


_DREDGE_REASON_PREFIX = "Dred" + "ge "
_LIBRARY_ZONE = "lib" + "rary"
_PILOT_ROLE = "pi" + "lot"
_REASON_FIELD = "rea" + "son"


class DrawCoordinatorHost(
    DrawCommitHost,
    DrawReplacementHost,
    Protocol,
):
    state: GameState
    permissions: Any

    def _require_seat(self, seat: str, *, in_game: bool = False) -> Any: ...

    def _resolve_object(self, actor: str, ref: str, **kwargs: Any) -> Any: ...

    def card_record(self, value: Any) -> Any: ...

    def _complete_draw_step_entry(self, active: str) -> None: ...

    def _continue_resolution(self, **kwargs: Any) -> None: ...


def draw_event_id(host: DrawCoordinatorHost, seat: str, scope: str) -> str:
    return (
        f"draw:{host.state.game_id}:{host.state.turn_sequence}:"
        f"{host.state.event_sequence + 1}:{seat}:{scope}"
    )


def commit_unreplaced_draws(
    host: DrawCoordinatorHost,
    seat: str,
    count: int,
    *,
    reason: str,
    private: bool,
) -> tuple[str, ...]:
    """Commit setup draws whose enclosing procedure is not a game draw."""

    host._require_seat(seat)
    instruction = prepare_draw_instruction(
        DrawInstructionRequest(
            event_id=draw_event_id(host, seat, "unreplaced"),
            player=seat,
            count=count,
            reason=reason,
            private=private,
        ),
        apnap_order=host.apnap_order(),
    )
    drawn: list[str] = []
    for _ in range(instruction.count or 0):
        prepared = prepare_draw_event(
            DrawEventRequest(
                event_id=draw_event_id(host, seat, "event"),
                player=seat,
                library_size=len(host.state.players[seat].zones[_LIBRARY_ZONE]),
                reason=reason,
                private=private,
            ),
            apnap_order=host.apnap_order(),
        )
        committed = commit_prepared_draw(host, prepared)
        drawn.extend(committed)
        if not committed:
            break
    return tuple(drawn)


def begin_draw_sequence(
    host: DrawCoordinatorHost,
    seat: str,
    count: int,
    *,
    reason: str,
    private: bool = False,
    continuation: Mapping[str, Any] | None = None,
) -> None:
    """Resolve one draw instruction, then each draw independently."""

    resume = DrawResume.from_dict(dict(continuation or {"kind": "none"}))
    prepared_count = _prepare_runtime_draw_count(
        host,
        seat,
        count,
        reason=reason,
        private=private,
    )
    _continue_draw_sequence(
        host,
        seat,
        prepared_count,
        reason=reason,
        private=private,
        resume=resume,
    )


def _prepare_runtime_draw_count(
    host: DrawCoordinatorHost,
    seat: str,
    count: int,
    *,
    reason: str,
    private: bool,
) -> int:
    """Prepare one instruction before the iterative per-draw coordinator."""

    host._require_seat(seat)
    instruction_request = DrawInstructionRequest(
        event_id=draw_event_id(host, seat, "instruction"),
        player=seat,
        count=count,
        reason=reason,
        private=private,
    )
    instruction_effects = _instruction_replacement_effects(host, seat)
    instruction = _prepare_runtime_draw_instruction(
        host,
        instruction_request,
        instruction_effects,
    )
    return instruction.count or 0


def _draw_batch_resume(draws: tuple[QueuedDraw, ...]) -> DrawResume:
    return (
        DrawResume(kind="draw_batch", draws=draws)
        if draws
        else DrawResume.none()
    )


def begin_draw_batch(
    host: DrawCoordinatorHost,
    draws: tuple[QueuedDraw, ...],
) -> None:
    """Resolve queued instructions in order without bypassing replacements."""

    if any(not isinstance(draw, QueuedDraw) for draw in draws):
        raise DrawError("Draw batch requires typed queued draws")
    if not draws:
        return
    current, remaining = draws[0], draws[1:]
    begin_draw_sequence(
        host,
        current.player,
        current.count,
        reason=current.reason,
        private=current.private,
        continuation=_draw_batch_resume(remaining).to_dict(),
    )


def _replacement_effects(
    host: DrawCoordinatorHost,
    seat: str,
) -> tuple[Any, ...]:
    try:
        return collect_draw_replacement_effects(host, seat)
    except SemanticNodeError as exc:
        raise DrawError(str(exc)) from exc


def _instruction_replacement_effects(
    host: DrawCoordinatorHost,
    seat: str,
) -> tuple[Any, ...]:
    try:
        return collect_draw_instruction_replacement_effects(host, seat)
    except SemanticNodeError as exc:
        raise DrawError(str(exc)) from exc


def _prepare_runtime_draw_instruction(
    host: DrawCoordinatorHost,
    request: DrawInstructionRequest,
    effects: tuple[Any, ...],
) -> Any:
    """Resolve the closed commutative draw-doubling family canonically."""

    selections: list[str] = []
    while True:
        prepared = prepare_draw_instruction(
            request,
            apnap_order=host.apnap_order(),
            effects=effects,
            selections=selections,
            require_all_selections=False,
        )
        pending = prepared.pending
        if pending is None:
            return prepared
        by_id = {effect.effect_id: effect for effect in effects}
        options = tuple(pending.choice.options)
        if (
            pending.choice.optional_options
            or not options
            or any(
                effect_id not in by_id
                or len(by_id[effect_id].operations) != 1
                or by_id[effect_id].operations[0].to_dict()
                != {"op": "multiply", "field": "count", "factor": 2}
                for effect_id in options
            )
        ):
            raise DrawError(
                "A draw instruction requires an unsupported material replacement choice"
            )
        selections.append(sorted(options)[0])


def _draw_permission(host: DrawCoordinatorHost, seat: str) -> Any:
    try:
        return current_draw_permission(host, seat)
    except SemanticNodeError as exc:
        raise DrawError(str(exc)) from exc


def _continue_draw_sequence(
    host: DrawCoordinatorHost,
    seat: str,
    remaining: int,
    *,
    reason: str,
    private: bool,
    resume: DrawResume,
) -> None:
    """Drain draw events and queued instructions without Python recursion."""

    while True:
        while remaining > 0:
            request = DrawEventRequest(
                event_id=draw_event_id(host, seat, "event"),
                player=seat,
                library_size=len(
                    host.state.players[seat].zones[_LIBRARY_ZONE]
                ),
                reason=reason,
                private=private,
            )
            permission = _draw_permission(host, seat)
            if not permission.allows_individual_draw():
                prepared = prepare_draw_event(
                    request,
                    apnap_order=host.apnap_order(),
                    prohibition_ids=permission.restriction_ids,
                )
                commit_prepared_draw(host, prepared)
                remaining -= 1
                continue
            effects = _replacement_effects(host, seat)
            prepared = prepare_draw_event(
                request,
                apnap_order=host.apnap_order(),
                effects=effects,
                require_all_selections=False,
            )
            if prepared.pending is not None:
                _issue_draw_replacement_choice(
                    host,
                    DrawDecisionContinuation(
                        event_id=request.event_id,
                        seat=seat,
                        remaining_draws=remaining,
                        library_size=request.library_size,
                        reason=reason,
                        private=private,
                        effects=effects,
                        selections=(),
                        after=resume,
                    ),
                    prepared,
                )
                return
            commit_prepared_draw(host, prepared)
            remaining -= 1

        if resume.kind != "draw_batch":
            resume_after_draw(host, resume)
            return

        current, queued = resume.draws[0], resume.draws[1:]
        seat = current.player
        reason = current.reason
        private = current.private
        remaining = _prepare_runtime_draw_count(
            host,
            seat,
            current.count,
            reason=reason,
            private=private,
        )
        resume = _draw_batch_resume(queued)


def _choice_id(effect: Any) -> str:
    return next(
        (
            str(source_ref)
            for operation in effect.operations
            if (source_ref := getattr(operation, "source_ref", None))
        ),
        effect.effect_id,
    )


def _issue_draw_replacement_choice(
    host: DrawCoordinatorHost,
    continuation: DrawDecisionContinuation,
    prepared: PreparedDrawEvent,
) -> None:
    pending = prepared.pending
    if pending is None or pending.choice.chooser != continuation.seat:
        raise DrawError("Draw replacement choice has the wrong affected player")
    by_id = {effect.effect_id: effect for effect in continuation.effects}
    options = [
        {
            "id": _choice_id(by_id[effect_id]),
            "label": by_id[effect_id].label or effect_id,
        }
        for effect_id in pending.choice.options
    ]
    if set(pending.choice.options) == set(pending.choice.optional_options):
        options.insert(0, {"id": "draw", "label": "Draw a card"})
    legal_values = [str(option["id"]) for option in options]
    host.permissions.issue(
        kind="draw.replacement",
        role=_PILOT_ROLE,
        actors=[continuation.seat],
        allowed_actions=["choose"],
        payload_by_actor={
            continuation.seat: {
                _REASON_FIELD: continuation.reason,
                "remaining_draws": continuation.remaining_draws,
                "options": options,
                "legal_actions": [
                    {
                        "id": "choose",
                        "action": "choose",
                        "choice_schema": {
                            "field": "choice",
                            "legal_values": legal_values,
                        },
                    }
                ],
            }
        },
        continuation=continuation.to_dict(),
    )


def _selected_effect_id(
    continuation: DrawDecisionContinuation,
    pending: PreparedDrawEvent,
    choice: str,
) -> str | None:
    if pending.pending is None:
        return None
    by_id = {effect.effect_id: effect for effect in continuation.effects}
    return next(
        (
            effect_id
            for effect_id in pending.pending.choice.options
            if effect_id == choice or _choice_id(by_id[effect_id]) == choice
        ),
        None,
    )


def complete_draw_replacement(
    host: DrawCoordinatorHost,
    decision: Any,
) -> None:
    raw_continuation = decision.continuation
    if "schema_version" not in raw_continuation:
        _complete_legacy_draw_replacement(host, decision)
        return
    continuation = DrawDecisionContinuation.from_dict(raw_continuation)
    seat = decision.actors[0]
    if seat != continuation.seat:
        raise DrawError("Draw continuation seat changed")
    response = decision.responses[seat]
    choice = response.get("choice")
    if type(choice) is not str or not choice:
        raise DrawError("Draw replacement choice is required")
    current_effects = _replacement_effects(host, seat)
    if current_effects != continuation.effects:
        raise DrawError("Draw replacement sources changed before completion")
    current = prepare_draw_event(
        continuation.request,
        apnap_order=host.apnap_order(),
        effects=continuation.effects,
        selections=continuation.selections,
        require_all_selections=False,
    )
    if current.pending is None:
        raise DrawError("Draw replacement continuation is already closed")
    if choice == "draw":
        prepared = prepare_ordinary_draw(
            continuation.request,
            apnap_order=host.apnap_order(),
            effects=continuation.effects,
            selections=continuation.selections,
        )
        selections = tuple(
            selection.effect_id for selection in prepared.journal
        )
    else:
        selected_effect = _selected_effect_id(continuation, current, choice)
        if selected_effect is None:
            raise DrawError("Selected draw replacement is not available")
        selections = (*continuation.selections, selected_effect)
        prepared = prepare_draw_event(
            continuation.request,
            apnap_order=host.apnap_order(),
            effects=continuation.effects,
            selections=selections,
            require_all_selections=False,
        )
    if prepared.pending is not None:
        _issue_draw_replacement_choice(
            host,
            replace(continuation, selections=tuple(selections)),
            prepared,
        )
        return
    commit_prepared_draw(host, prepared)
    _continue_draw_sequence(
        host,
        seat,
        continuation.remaining_draws - 1,
        reason=continuation.reason,
        private=continuation.private,
        resume=continuation.after,
    )


def _complete_legacy_draw_replacement(
    host: DrawCoordinatorHost,
    decision: Any,
) -> None:
    """Explicit Game Record v3 compatibility for pre-transaction saves."""

    seat = decision.actors[0]
    response = decision.responses[seat]
    continuation = dict(decision.continuation)
    choice = response.get("choice")
    if type(choice) is not str or not choice:
        raise DrawError("Legacy draw replacement choice is required")
    candidate_values = continuation.get("candidates")
    if not isinstance(candidate_values, list) or any(
        not isinstance(value, Mapping) for value in candidate_values
    ):
        raise DrawError("Legacy draw candidates are malformed")
    candidates = {
        value.get("id"): value
        for value in candidate_values
        if type(value.get("id")) is str
    }
    reason = continuation.get(_REASON_FIELD)
    private = continuation.get("private")
    remaining = continuation.get("remaining_draws")
    if (
        type(reason) is not str
        or not reason
        or type(private) is not bool
        or type(remaining) is not int
        or remaining < 1
    ):
        raise DrawError("Legacy draw continuation is malformed")
    if choice == "draw":
        commit_unreplaced_draws(
            host, seat, 1, reason=reason, private=private
        )
    elif choice in candidates:
        candidate = candidates[choice]
        mill_count = candidate.get("mill")
        if type(mill_count) is not int or mill_count < 1:
            raise DrawError("Legacy Dredge count is malformed")
        card = host._resolve_object(
            seat,
            choice,
            zones={"graveyard"},
            owned_only=True,
        )
        record = host.card_record(card)
        match = (
            re.search(
                r"\bDredge\s+(?P<count>\d+)\b",
                record.oracle_text,
                re.IGNORECASE,
            )
            if record is not None
            else None
        )
        library = host.state.players[seat].zones[_LIBRARY_ZONE]
        if (
            match is None
            or int(match.group("count")) != mill_count
            or len(library) < mill_count
        ):
            raise DrawError(
                "The legacy Dredge replacement is no longer available"
            )
        milled_ids = list(reversed(library[-mill_count:]))
        host._move_cards_simultaneously(
            [(object_id, "graveyard") for object_id in milled_ids],
            reason=f"{_DREDGE_REASON_PREFIX}{mill_count}",
            log=False,
        )
        host.move_card(
            card.object_id,
            "hand",
            reason=f"{_DREDGE_REASON_PREFIX}{mill_count}",
            semantic_events=True,
        )
        host._log(
            seat,
            "draw.replaced.dredge",
            (
                f"{seat} replaced a draw by milling {mill_count} "
                f"and returning {card.ref}."
            ),
            {
                "player": seat,
                "card": card.ref,
                "mill": mill_count,
                "objects": [
                    host.state.cards[value].ref for value in milled_ids
                ],
                _REASON_FIELD: reason,
            },
            visibility=[seat, "analyst"],
            importance=2,
            changed_objects=[card.object_id, *milled_ids],
            changed_players=[seat],
        )
    else:
        raise DrawError(
            "Choose the normal draw or an available legacy Dredge card"
        )
    resume = DrawResume.from_dict(
        dict(continuation.get("after") or {"kind": "none"})
    )
    _continue_draw_sequence(
        host,
        seat,
        remaining - 1,
        reason=reason,
        private=private,
        resume=resume,
    )


def resume_after_draw(
    host: DrawCoordinatorHost,
    continuation: DrawResume | Mapping[str, Any],
) -> None:
    resume = (
        continuation
        if isinstance(continuation, DrawResume)
        else DrawResume.from_dict(continuation)
    )
    if resume.kind == "none":
        return
    if resume.kind == "turn_draw":
        host._complete_draw_step_entry(resume.seat)
        return
    if resume.kind == "semantic_resolution":
        host._continue_resolution(
            stack_ref=resume.stack_ref,
            effects=[thaw_value(value) for value in resume.effects],
            destination=resume.destination,
            note=resume.note,
            instruction_pointer=resume.instruction_pointer,
        )
        return
    if resume.kind == "draw_batch":
        begin_draw_batch(host, resume.draws)
        return
    raise DrawError(f"Unsupported post-draw continuation {resume.kind!r}")


__all__ = [
    "begin_draw_batch",
    "begin_draw_sequence",
    "commit_unreplaced_draws",
    "complete_draw_replacement",
    "DrawCoordinatorHost",
    "draw_event_id",
    "resume_after_draw",
]
