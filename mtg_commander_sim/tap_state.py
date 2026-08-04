from __future__ import annotations

from typing import Any, Iterable, Protocol


VIGILANCE_KEYWORD = "vigilance"


class TapStateError(ValueError):
    """A requested canonical tap-state transition is malformed."""


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


def tap_declared_attackers(
    host: TapStateHost,
    attackers: Iterable[Any],
) -> list[str]:
    """Apply CR 508.1f using the current effective keyword snapshot.

    The declaration coordinator has already established legality. This owner
    preflights the complete supplied set before mutation so a malformed entry
    cannot leave an earlier attacker tapped. Vigilance is a redundant static
    ability: one or several current instances produce the same no-tap result.
    """

    prepared: list[tuple[Any, bool]] = []
    seen: set[str] = set()
    for card in tuple(attackers):
        object_id = str(getattr(card, "object_id", ""))
        object_ref = str(getattr(card, "ref", ""))
        if not object_id or not object_ref:
            raise TapStateError("Declared attacker identity is required")
        if object_id in seen:
            raise TapStateError("A declared attacker may appear only once")
        seen.add(object_id)
        if getattr(card, "zone", None) != "battlefield":
            raise TapStateError("Declared attacker must be on the battlefield")
        if type(getattr(card, "tapped", None)) is not bool:
            raise TapStateError("Declared attacker tap state must be boolean")
        if card.tapped:
            raise TapStateError("A tapped permanent cannot be newly declared")
        data = host._effective_card_data(card)
        raw_keywords = data.get("keywords", ())
        if not isinstance(raw_keywords, (list, tuple, set, frozenset)) or any(
            not isinstance(keyword, str) for keyword in raw_keywords
        ):
            raise TapStateError("Effective attacker keywords are malformed")
        keywords = {keyword.casefold() for keyword in raw_keywords}
        prepared.append((card, VIGILANCE_KEYWORD not in keywords))

    tapped_refs: list[str] = []
    for card, should_tap in prepared:
        if should_tap:
            card.tapped = True
            tapped_refs.append(card.ref)
    return tapped_refs


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
