from __future__ import annotations

from typing import Any, Protocol


class TapStateHost(Protocol):
    """Transitional mutation port exposed by the authoritative rules host."""

    state: Any

    @property
    def active_seats(self) -> list[str]: ...

    def _resolve_object(
        self, actor: str, ref: str, *, zones: set[str]
    ) -> Any: ...

    def _untap_permanent(
        self, card: Any, *, actor: str | None, reason: str
    ) -> bool: ...

    def _effective_card_data(self, card: Any) -> dict[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _log(
        self,
        actor: str | None,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        importance: int = 1,
        changed_objects: list[str] | None = None,
    ) -> Any: ...


def set_permanent_tapped(
    host: TapStateHost,
    object_ref: str,
    *,
    actor: str,
    tapped: bool,
    reason: str,
    logical_object_id: str | None = None,
    revert: bool = False,
    log: bool = True,
) -> str:
    """Commit one validated tap-state intent through authoritative state."""

    card = next(
        (
            candidate
            for candidate in host.state.cards.values()
            if candidate.ref == object_ref
        ),
        None,
    )
    if card is None:
        card = host._resolve_object(
            actor,
            object_ref,
            zones={"battlefield"},
        )
    if (
        logical_object_id is not None
        and card.logical_object_id != logical_object_id
    ):
        return card.ref
    if card.zone != "battlefield":
        return card.ref
    if tapped:
        changed = not card.tapped
        card.tapped = True
    elif revert:
        changed = card.tapped
        card.tapped = False
    else:
        changed = host._untap_permanent(
            card,
            actor=actor,
            reason=reason,
        )
    if changed and log:
        operation = "tap" if tapped else "untap"
        host._log(
            actor,
            f"permanent.{operation}",
            f"{card.ref} was {operation}ped.",
            dict(object=card.ref, reason=reason),
            importance=1,
            changed_objects=[card.object_id],
        )
    return card.ref


def untap_all_creatures(
    host: TapStateHost, *, actor: str, reason: str
) -> list[str]:
    """Commit the represented phased-in effective-creature untap set."""

    changed: list[str] = []
    for seat in host.active_seats:
        for object_id in host.state.players[seat].zones["battlefield"]:
            card = host.state.cards[object_id]
            card_types = host._type_parts(
                str(host._effective_card_data(card).get("type_line") or "")
            )[0]
            if card.phased_out or "creature" not in card_types:
                continue
            if host._untap_permanent(card, actor=actor, reason=reason):
                changed.append(object_id)
    if changed:
        host._log(
            actor,
            "permanent.untap",
            f"Untapped {len(changed)} creature(s).",
            dict(
                objects=[
                    host.state.cards[object_id].ref
                    for object_id in changed
                ],
                reason=reason,
            ),
            importance=2,
            changed_objects=changed,
        )
    return [host.state.cards[object_id].ref for object_id in changed]
