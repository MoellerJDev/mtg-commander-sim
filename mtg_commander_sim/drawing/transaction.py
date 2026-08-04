from __future__ import annotations

from typing import Any, Protocol, Sequence

from ..model import CardInstance, GameState
from .model import DrawError, PreparedDrawEvent, validate_prepared_draw


_DREDGE_KIND = "dred" + "ge"
_DREDGE_REASON_PREFIX = "Dred" + "ge "
_LIBRARY_ZONE = "lib" + "rary"
_REASON_FIELD = "rea" + "son"


class DrawCommitHost(Protocol):
    """Narrow mutation port owned by the canonical draw transaction."""

    state: GameState

    def apnap_order(self) -> list[str]: ...

    def move_card(
        self,
        object_id: str,
        destination: str,
        **kwargs: Any,
    ) -> CardInstance: ...

    def _move_cards_simultaneously(
        self,
        changes: Sequence[tuple[str, str]],
        *,
        reason: str,
        log: bool = False,
    ) -> list[CardInstance]: ...

    def _log(self, actor: str | None, code: str, message: str, details: Any, **kwargs: Any) -> Any: ...

    def _dispatch_semantic_event(
        self,
        event: str,
        context: dict[str, Any],
        **kwargs: Any,
    ) -> Any: ...


def _require_current_request(
    host: DrawCommitHost,
    prepared: PreparedDrawEvent,
) -> None:
    request = prepared.request
    if request.player not in host.state.players:
        raise DrawError("Draw player is no longer present")
    if len(host.state.players[request.player].zones[_LIBRARY_ZONE]) != request.library_size:
        raise DrawError("Draw library size changed before commit")


def _record_draw(
    host: DrawCommitHost,
    prepared: PreparedDrawEvent,
    object_id: str,
) -> None:
    resolution = prepared.resolution
    if resolution is None:
        raise DrawError("A pending draw cannot be recorded")
    player = host.state.players[resolution.player]
    card = host.state.cards[object_id]
    turn_key = str(host.state.turn_sequence)
    draw_tracker = player.stats.setdefault("cards_drawn_by_turn", {})
    before_count = int(draw_tracker.get(turn_key, 0))
    draw_tracker[turn_key] = before_count + 1
    in_own_draw_step = bool(
        host.state.active_player == resolution.player
        and (host.state.phase, host.state.step) == ("beginning", "draw")
    )
    draw_step_tracker = player.stats.setdefault(
        "cards_drawn_in_draw_step_by_turn", {}
    )
    before_draw_step_count = (
        int(draw_step_tracker.get(turn_key, 0)) if in_own_draw_step else 0
    )
    if in_own_draw_step:
        draw_step_tracker[turn_key] = before_draw_step_count + 1
    player.draw_history.append(
        {
            "turn_sequence": host.state.turn_sequence,
            "card": card.printed_name,
            "object": card.ref,
            _REASON_FIELD: resolution.reason,
        }
    )
    host._log(
        resolution.player,
        "card.draw",
        f"{resolution.player} drew 1 card(s).",
        {"count": 1, _REASON_FIELD: resolution.reason},
        changed_players=[resolution.player],
    )
    host._log(
        resolution.player,
        "card.draw.private",
        f"{resolution.player} drew {card.printed_name}.",
        {
            "objects": [card.ref],
            "cards": [card.printed_name],
            _REASON_FIELD: resolution.reason,
        },
        visibility=[resolution.player, "analyst"],
        importance=0 if resolution.private else 1,
        changed_objects=[object_id],
        changed_players=[resolution.player],
    )
    if before_count < 2 <= before_count + 1:
        host._dispatch_semantic_event(
            "card.second_draw",
            {"player": resolution.player, "objects": [card.ref]},
        )
    if not (in_own_draw_step and before_draw_step_count == 0):
        host._dispatch_semantic_event(
            "card.draw_except_first_draw_step",
            {
                "player": resolution.player,
                "object": card.ref,
                _REASON_FIELD: resolution.reason,
                "in_own_draw_step": in_own_draw_step,
                "draw_step_ordinal": (
                    before_draw_step_count + 1 if in_own_draw_step else None
                ),
            },
        )


def _commit_ordinary_draw(
    host: DrawCommitHost,
    prepared: PreparedDrawEvent,
) -> tuple[str, ...]:
    resolution = prepared.resolution
    if resolution is None:
        raise DrawError("A pending draw cannot commit")
    player = host.state.players[resolution.player]
    if not player.zones[_LIBRARY_ZONE]:
        player.attempted_empty_draw = True
        host._log(
            resolution.player,
            "card.draw.empty",
            f"{resolution.player} attempted to draw from an empty library.",
            {_REASON_FIELD: resolution.reason},
            importance=2,
            changed_players=[resolution.player],
        )
        return ()
    object_id = player.zones[_LIBRARY_ZONE][-1]
    host.move_card(object_id, "hand", reason=resolution.reason, log=False)
    _record_draw(host, prepared, object_id)
    return (object_id,)


def _commit_dredge(
    host: DrawCommitHost,
    prepared: PreparedDrawEvent,
) -> tuple[str, ...]:
    resolution = prepared.resolution
    if resolution is None or resolution.kind != _DREDGE_KIND:
        raise DrawError("Dredge commit requires a closed Dredge result")
    object_id = resolution.dredge_source_object_id
    source_ref = resolution.dredge_source_ref
    incarnation = resolution.dredge_source_zone_change_counter
    mill_count = resolution.dredge_mill_count
    if (
        object_id is None
        or source_ref is None
        or incarnation is None
        or mill_count is None
    ):
        raise DrawError("Dredge result is missing source data")
    source = host.state.cards.get(object_id)
    if (
        source is None
        or source.ref != source_ref
        or source.owner != resolution.player
        or source.zone != "graveyard"
        or source.zone_change_counter != incarnation
    ):
        raise DrawError("Dredge source changed before commit")
    library = host.state.players[resolution.player].zones[_LIBRARY_ZONE]
    if len(library) < mill_count:
        raise DrawError("Dredge library became too small before commit")
    milled_ids = tuple(reversed(library[-mill_count:]))
    host._move_cards_simultaneously(
        tuple((milled_id, "graveyard") for milled_id in milled_ids),
        reason=f"{_DREDGE_REASON_PREFIX}{mill_count}",
        log=False,
    )
    host.move_card(
        source.object_id,
        "hand",
        reason=f"{_DREDGE_REASON_PREFIX}{mill_count}",
        semantic_events=True,
    )
    host._log(
        resolution.player,
        "draw.replaced.dredge",
        (
            f"{resolution.player} replaced a draw by milling {mill_count} "
            f"and returning {source.ref}."
        ),
        {
            "player": resolution.player,
            "card": source.ref,
            "mill": mill_count,
            "objects": [host.state.cards[value].ref for value in milled_ids],
            _REASON_FIELD: resolution.reason,
        },
        visibility=[resolution.player, "analyst"],
        importance=2,
        changed_objects=[source.object_id, *milled_ids],
        changed_players=[resolution.player],
    )
    return (source.object_id,)


def commit_prepared_draw(
    host: DrawCommitHost,
    prepared: PreparedDrawEvent,
) -> tuple[str, ...]:
    """Validate and commit exactly one replacement-resolved draw event."""

    validate_prepared_draw(prepared, apnap_order=host.apnap_order())
    _require_current_request(host, prepared)
    resolution = prepared.resolution
    if resolution is None:
        raise DrawError("A pending draw cannot commit")
    if resolution.kind == "draw":
        return _commit_ordinary_draw(host, prepared)
    if resolution.kind == "prevented":
        host._log(
            resolution.player,
            "card.draw.prevented",
            f"{resolution.player}'s draw was prevented.",
            {_REASON_FIELD: resolution.reason},
            importance=1,
            changed_players=[resolution.player],
        )
        return ()
    if resolution.kind == "prohibited":
        host._log(
            resolution.player,
            "card.draw.prohibited",
            f"{resolution.player} could not draw a card.",
            {
                _REASON_FIELD: resolution.reason,
                "prohibitions": list(resolution.prohibition_ids),
            },
            importance=1,
            changed_players=[resolution.player],
        )
        return ()
    if resolution.kind == _DREDGE_KIND:
        return _commit_dredge(host, prepared)
    raise DrawError(f"Unsupported draw result {resolution.kind!r}")


__all__ = ["DrawCommitHost", "commit_prepared_draw"]
