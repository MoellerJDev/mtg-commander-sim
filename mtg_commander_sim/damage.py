from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

from .replacement_effects import (
    AffectedObject,
    ReplaceableEvent,
    ReplacementChoiceRequired,
    ReplacementClass,
    ReplacementEffect,
    ReplacementEventBatch,
    ReplacementSelection,
    advance_replacement_batch,
)


DamageRecipientKind = Literal["player", "permanent"]


class DamageError(ValueError):
    """A represented damage proposal cannot be resolved exactly."""


class DamageHost(Protocol):
    state: Any
    semantics: Any
    active_seats: list[str]

    def _semantic_event_sources(
        self, *, zones: set[str] | None = None
    ) -> list[Any]: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...

    def apnap_order(self, *, start: str | None = None) -> list[str]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _resolve_object(
        self,
        actor: str,
        ref: str,
        *,
        zones: set[str] | None = None,
    ) -> Any: ...

    def _protection_colors(self, card: Any) -> set[str]: ...

    def _queue_siege_defeated_trigger(self, battle: Any) -> None: ...

    def _monarch_trigger(self, **kwargs: Any) -> Any: ...

    def _dispatch_semantic_event(
        self,
        event: str,
        context: Mapping[str, Any],
        **kwargs: Any,
    ) -> None: ...

    def _enqueue_semantic_trigger_batch(
        self, trigger_batch: Sequence[Any]
    ) -> None: ...

    def _semantic_pause_annotation(self) -> Mapping[str, Any] | None: ...

    def _record_turn_history(
        self,
        kind: str,
        *,
        actor: str | None = None,
        object_incarnation: str | None = None,
        target: str | None = None,
        target_kind: str | None = None,
        amount: int | None = None,
    ) -> None: ...

    def _log(
        self,
        actor: str | None,
        code: str,
        summary: str,
        details: Mapping[str, Any] | None = None,
        *,
        visibility: Sequence[str] | None = None,
        importance: int = 1,
        changed_objects: Sequence[str] = (),
        changed_players: Sequence[str] = (),
    ) -> None: ...


def _normalized_keywords(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                " ".join(str(value).casefold().split())
                for value in values
                if str(value).strip()
            }
        )
    )


@dataclass(frozen=True, slots=True)
class DamageSourceSnapshot:
    ref: str
    object_id: str
    logical_object_id: str
    controller: str
    owner: str
    types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    is_commander: bool = False

    def __post_init__(self) -> None:
        if not all(
            (
                self.ref,
                self.object_id,
                self.logical_object_id,
                self.controller,
                self.owner,
            )
        ):
            raise DamageError(
                "Damage sources require stable identity and controller facts"
            )


@dataclass(frozen=True, slots=True)
class DamageRecipientSnapshot:
    ref: str
    kind: DamageRecipientKind
    controller: str
    object_id: str | None = None
    logical_object_id: str | None = None
    owner: str | None = None
    types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"player", "permanent"}:
            raise DamageError(
                "Damage recipient kinds must be player or permanent"
            )
        if not self.ref or not self.controller:
            raise DamageError(
                "Damage recipients require stable identity and controller facts"
            )
        if self.kind == "player":
            if any(
                value is not None
                for value in (
                    self.object_id,
                    self.logical_object_id,
                    self.owner,
                )
            ):
                raise DamageError(
                    "Player damage recipients cannot carry object identity"
                )
        elif not all(
            (self.object_id, self.logical_object_id, self.owner)
        ):
            raise DamageError(
                "Permanent damage recipients require complete object identity"
            )

    @property
    def affected_object(self) -> AffectedObject | None:
        if self.kind == "player":
            return None
        assert self.object_id is not None and self.owner is not None
        return AffectedObject(
            object_id=self.object_id,
            owner=self.owner,
            controller=self.controller,
        )


@dataclass(frozen=True, slots=True)
class DamageProposal:
    proposal_id: str
    source: DamageSourceSnapshot
    recipient: DamageRecipientSnapshot
    amount: int
    combat: bool
    reason: str
    unpreventable: bool = False
    deathtouch: bool = False
    damage_step: int | None = None
    first_strike_step: bool = False

    def __post_init__(self) -> None:
        if not self.proposal_id or not self.reason:
            raise DamageError("Damage proposals require stable IDs and reasons")
        if type(self.amount) is not int or self.amount < 0:
            raise DamageError("Damage cannot be negative")
        if self.damage_step is not None and self.damage_step < 1:
            raise DamageError("Damage step indexes must be positive")

    def event(self) -> ReplaceableEvent:
        if self.amount < 1:
            raise DamageError("Zero damage has no replaceable event")
        payload = {
            "source": self.source.ref,
            "source_object_id": self.source.object_id,
            "source_logical_object_id": self.source.logical_object_id,
            "source_controller": self.source.controller,
            "source_owner": self.source.owner,
            "source_types": list(self.source.types),
            "source_subtypes": list(self.source.subtypes),
            "source_characteristics": sorted(
                {*self.source.types, *self.source.subtypes}
            ),
            "source_colors": list(self.source.colors),
            "source_keywords": list(self.source.keywords),
            "source_is_commander": self.source.is_commander,
            "target": self.recipient.ref,
            "target_kind": self.recipient.kind,
            "target_object_id": self.recipient.object_id,
            "target_logical_object_id": self.recipient.logical_object_id,
            "target_controller": self.recipient.controller,
            "target_owner": self.recipient.owner,
            "target_types": list(self.recipient.types),
            "target_subtypes": list(self.recipient.subtypes),
            "target_characteristics": sorted(
                {*self.recipient.types, *self.recipient.subtypes}
            ),
            "proposed_amount": self.amount,
            "amount": self.amount,
            "prevented": 0,
            "combat": self.combat,
            "reason": self.reason,
            "unpreventable": self.unpreventable,
            "deathtouch": self.deathtouch,
            "damage_step": self.damage_step,
            "first_strike_step": self.first_strike_step,
        }
        return ReplaceableEvent(
            event_id=self.proposal_id,
            kind="damage",
            affected_player=(
                self.recipient.ref
                if self.recipient.kind == "player"
                else None
            ),
            affected_object=self.recipient.affected_object,
            payload=payload,
        )


@dataclass(frozen=True, slots=True)
class DamageEvent:
    """One final source-recipient result from an authoritative damage batch.

    ``assigned_amount`` is the positive amount proposed by the producer before
    CR 614/615 processing. Replacement and prevention effects may increase,
    decrease, or prevent damage in an interleaved order, so dealt plus
    prevented damage is intentionally not required to equal the proposal.
    """

    source: str
    source_object_id: str
    source_logical_object_id: str
    source_controller: str
    source_owner: str
    source_types: tuple[str, ...]
    source_subtypes: tuple[str, ...]
    source_colors: tuple[str, ...]
    source_keywords: tuple[str, ...]
    source_is_commander: bool
    target: str
    target_kind: DamageRecipientKind
    target_object_id: str | None
    target_controller: str | None
    target_types: tuple[str, ...]
    target_subtypes: tuple[str, ...]
    assigned_amount: int
    dealt_amount: int
    prevented_amount: int
    combat: bool
    damage_step: int | None = None
    first_strike_step: bool = False
    unpreventable: bool = False
    applied_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.target_kind not in {"player", "permanent"}:
            raise ValueError(
                "Damage target kinds must be player or permanent"
            )
        if self.assigned_amount <= 0:
            raise ValueError("A damage event requires a positive assignment")
        if self.dealt_amount < 0 or self.prevented_amount < 0:
            raise ValueError("Damage event results cannot be negative")
        if self.target_kind == "player" and self.target_object_id is not None:
            raise ValueError("Player damage cannot have a target object id")
        if self.target_kind == "permanent" and not self.target_object_id:
            raise ValueError("Permanent damage requires a target object id")
        if len(self.applied_effects) != len(set(self.applied_effects)):
            raise ValueError(
                "A damage event cannot apply one replacement effect twice"
            )

    @property
    def was_dealt(self) -> bool:
        return self.dealt_amount > 0

    def semantic_context(self) -> dict[str, Any]:
        """Return the stable normalized context consumed by trigger programs."""

        return {
            # ``card`` is the established self-event identity field used by
            # ``damage.dealt.self`` programs.
            "card": self.source,
            "source": self.source,
            "source_object_id": self.source_object_id,
            "source_logical_object_id": self.source_logical_object_id,
            "source_controller": self.source_controller,
            "source_owner": self.source_owner,
            "source_types": list(self.source_types),
            "source_subtypes": list(self.source_subtypes),
            "source_colors": list(self.source_colors),
            "source_keywords": list(self.source_keywords),
            "source_is_commander": self.source_is_commander,
            "target": self.target,
            "target_kind": self.target_kind,
            "target_object_id": self.target_object_id,
            "target_controller": self.target_controller,
            "target_types": list(self.target_types),
            "target_subtypes": list(self.target_subtypes),
            "player": self.target if self.target_kind == "player" else None,
            "amount": self.dealt_amount,
            "assigned_amount": self.assigned_amount,
            "prevented_amount": self.prevented_amount,
            "combat": self.combat,
            "damage_step": self.damage_step,
            "first_strike_step": self.first_strike_step,
            "unpreventable": self.unpreventable,
            "applied_effects": list(self.applied_effects),
        }


@dataclass(frozen=True, slots=True)
class PreparedDamageBatch:
    events: tuple[ReplaceableEvent, ...]
    effects: tuple[ReplacementEffect, ...]
    journal: tuple[ReplacementSelection, ...]


@dataclass(frozen=True, slots=True)
class DamageLifeGain:
    player: str
    source: str
    amount: int


@dataclass(frozen=True, slots=True)
class DamageBatchResult:
    events: tuple[DamageEvent, ...]
    changed_objects: tuple[str, ...]
    changed_players: tuple[str, ...]
    lifelink_gains: tuple[DamageLifeGain, ...]

    @property
    def dealt_amount(self) -> int:
        return sum(event.dealt_amount for event in self.events)


def source_snapshot(
    host: DamageHost,
    source_ref: str | None,
    *,
    controller: str,
) -> DamageSourceSnapshot:
    """Capture CR 120.1/120.2 source facts before event transformation."""

    source = next(
        (
            card
            for card in host.state.cards.values()
            if card.ref == source_ref
        ),
        None,
    )
    if source is None:
        # Direct low-level effect calls and legacy checkpoints may not carry a
        # card handle. Keep their deterministic identity while withholding all
        # source characteristics; ordinary compiled damage always supplies the
        # exact source. This compatibility source does not claim CR 120.2
        # coverage for arbitrary off-battlefield objects.
        ref = str(source_ref or f"legacy-effect:{controller}")
        return DamageSourceSnapshot(
            ref=ref,
            object_id=f"unrepresented:{ref}",
            logical_object_id=f"unrepresented:{ref}",
            controller=controller,
            owner=controller,
        )
    data = host._effective_card_data(source)
    card_types, subtypes, _supertypes = host._type_parts(
        str(data.get("type_line") or "")
    )
    return DamageSourceSnapshot(
        ref=source.ref,
        object_id=source.object_id,
        logical_object_id=source.logical_object_id,
        controller=(
            source.controller
            if source.controller in host.state.players
            else controller
        ),
        owner=source.owner,
        types=tuple(sorted(card_types)),
        subtypes=tuple(sorted(subtypes)),
        colors=tuple(
            sorted(str(value).upper() for value in data.get("colors", ()))
        ),
        keywords=_normalized_keywords(data.get("keywords", ())),
        is_commander=bool(source.is_commander),
    )


def recipient_snapshot(
    host: DamageHost,
    target: str,
    *,
    actor: str,
) -> DamageRecipientSnapshot:
    if target in host.state.players:
        if target not in host.active_seats:
            raise DamageError("Damage cannot be dealt to a player who left")
        return DamageRecipientSnapshot(
            ref=target,
            kind="player",
            controller=target,
        )
    card = host._resolve_object(actor, target, zones={"battlefield"})
    data = host._effective_card_data(card)
    card_types, subtypes, _supertypes = host._type_parts(
        str(data.get("type_line") or "")
    )
    if not card_types.intersection({"battle", "creature", "planeswalker"}):
        raise DamageError(
            f"Damage cannot be dealt to {card.ref}; it is not a Battle, "
            "creature, or planeswalker"
        )
    return DamageRecipientSnapshot(
        ref=card.ref,
        kind="permanent",
        controller=card.controller,
        object_id=card.object_id,
        logical_object_id=card.logical_object_id,
        owner=card.owner,
        types=tuple(sorted(card_types)),
        subtypes=tuple(sorted(subtypes)),
    )


def damage_proposal(
    host: DamageHost,
    *,
    proposal_id: str,
    actor: str,
    source_ref: str | None,
    target: str,
    amount: int,
    combat: bool,
    reason: str,
    unpreventable: bool = False,
    deathtouch: bool = False,
    damage_step: int | None = None,
    first_strike_step: bool = False,
) -> DamageProposal:
    return DamageProposal(
        proposal_id=proposal_id,
        source=source_snapshot(host, source_ref, controller=actor),
        recipient=recipient_snapshot(host, target, actor=actor),
        amount=amount,
        combat=combat,
        reason=reason,
        unpreventable=unpreventable,
        deathtouch=deathtouch,
        damage_step=damage_step,
        first_strike_step=first_strike_step,
    )


def _protection_prevention_effects(
    host: DamageHost,
    proposals: Sequence[DamageProposal],
) -> tuple[ReplacementEffect, ...]:
    effects: dict[str, ReplacementEffect] = {}
    for proposal in proposals:
        recipient = proposal.recipient
        source = proposal.source
        protected = False
        source_id = ""
        if recipient.kind == "player":
            protected = bool(
                host.state.players[recipient.ref].stats.get(
                    "protection_from_everything_until_next_turn"
                )
            )
            source_id = f"rules:protection:{recipient.ref}"
        else:
            assert recipient.object_id is not None
            card = host.state.cards.get(recipient.object_id)
            if card is not None:
                protected = bool(
                    host._protection_colors(card).intersection(source.colors)
                )
            source_id = f"rules:protection:{recipient.object_id}"
        if not protected:
            continue
        effect_id = (
            f"prevention.protection:{recipient.ref}:{source.ref}"
        )
        effects[effect_id] = ReplacementEffect(
            effect_id=effect_id,
            source_id=source_id,
            event_kind="damage",
            replacement_class=ReplacementClass.OTHER,
            conditions={
                "amount": {"not_in": [0]},
                "source": {"eq": source.ref},
                "target": {"eq": recipient.ref},
            },
            operations=({"op": "prevent"},),
            label=f"Protection prevents damage to {recipient.ref}",
        )
    return tuple(effects[key] for key in sorted(effects))


def prepare_damage_batch(
    host: DamageHost,
    proposals: Sequence[DamageProposal],
    *,
    selections: Sequence[str | None] = (),
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
) -> PreparedDamageBatch:
    """Resolve one simultaneous CR 120.4b batch before any state mutation."""

    nonzero = tuple(proposal for proposal in proposals if proposal.amount > 0)
    if not nonzero:
        if selections:
            raise DamageError(
                "Replacement selections were supplied without damage"
            )
        return PreparedDamageBatch(events=(), effects=(), journal=())

    # Imported lazily to keep the immutable event model independent from the
    # CardProgram runtime registry that lowers ambient battlefield abilities.
    from .semantic_runtime.damage_replacements import (
        collect_damage_replacement_effects,
    )

    effects = (
        *collect_damage_replacement_effects(
            host,
            sources=sources,
            source_zones=source_zones,
        ),
        *_protection_prevention_effects(host, nonzero),
    )
    events = tuple(proposal.event() for proposal in nonzero)
    if not effects:
        if selections:
            raise DamageError(
                "Replacement selections were supplied without an applicable "
                "damage replacement"
            )
        return PreparedDamageBatch(events=events, effects=(), journal=())
    progress = advance_replacement_batch(
        ReplacementEventBatch(
            batch_id=(
                f"replacement:damage:{host.state.revision}:"
                f"{host.state.event_sequence + 1}"
            ),
            events=events,
            apnap_order=tuple(host.apnap_order()),
        ),
        effects,
        selections=selections,
    )
    if progress.pending is not None:
        raise ReplacementChoiceRequired(
            batch=progress.batch,
            effects=effects,
            pending=progress.pending,
        )
    return PreparedDamageBatch(
        events=progress.batch.events,
        effects=tuple(effects),
        journal=progress.batch.journal,
    )


def _permanent_result_plan(
    host: DamageHost,
    event: ReplaceableEvent,
    amount: int,
) -> tuple[Any, set[str]]:
    object_id = str(event.payload.get("target_object_id") or "")
    card = host.state.cards.get(object_id)
    if card is None or card.zone != "battlefield" or card.phased_out:
        raise DamageError("Damage recipient is no longer on the battlefield")
    if card.logical_object_id != str(
        event.payload.get("target_logical_object_id") or ""
    ):
        raise DamageError("Damage recipient changed object identity")
    data = host._effective_card_data(card)
    card_types, _subtypes, _supertypes = host._type_parts(
        str(data.get("type_line") or "")
    )
    damageable = card_types.intersection(
        {"battle", "creature", "planeswalker"}
    )
    if not damageable:
        raise DamageError(
            f"Damage cannot be dealt to {card.ref}; it is not damageable"
        )
    source_keywords = set(event.payload.get("source_keywords") or ())
    if "creature" in card_types and source_keywords.intersection(
        {"infect", "wither"}
    ):
        raise DamageError(
            "Infect and wither creature-damage results are not yet represented"
        )
    if amount < 0:
        raise DamageError("Resolved damage cannot be negative")
    return card, damageable


def apply_damage_results_to_permanent(
    host: DamageHost,
    card: Any,
    amount: int,
    *,
    deathtouch: bool = False,
    source_keywords: Sequence[str] = (),
) -> dict[str, Any]:
    """Commit the represented CR 120.3 permanent results at one owner."""

    damage = int(amount)
    if damage < 0:
        raise DamageError("Damage cannot be negative")
    data = host._effective_card_data(card)
    card_types, _subtypes, _supertypes = host._type_parts(
        str(data.get("type_line") or "")
    )
    damageable_types = card_types.intersection(
        {"battle", "creature", "planeswalker"}
    )
    if not damageable_types:
        raise DamageError(
            f"Damage cannot be dealt to {card.ref}; it is not a Battle, "
            "creature, or planeswalker"
        )
    keywords = set(_normalized_keywords(source_keywords))
    if "creature" in card_types and keywords.intersection(
        {"infect", "wither"}
    ):
        raise DamageError(
            "Infect and wither creature-damage results are not yet represented"
        )
    result: dict[str, Any] = {
        "amount": damage,
        "types": sorted(damageable_types),
    }
    if damage == 0:
        return result
    if "creature" in card_types:
        card.marked_damage += damage
        card.deathtouch_damage = card.deathtouch_damage or deathtouch
        result["marked_damage"] = damage
    for card_type, counter_name, result_name in (
        ("planeswalker", "loyalty", "loyalty_removed"),
        ("battle", "defense", "defense_removed"),
    ):
        if card_type not in card_types:
            continue
        before = max(0, int(card.counters.get(counter_name, 0)))
        after = max(0, before - damage)
        if after:
            card.counters[counter_name] = after
        else:
            card.counters.pop(counter_name, None)
        result[result_name] = before - after
        if counter_name == "defense" and before > 0 and after == 0:
            host._queue_siege_defeated_trigger(card)
    return result


def _event_result(event: ReplaceableEvent) -> tuple[int, int, int]:
    proposed = int(event.payload.get("proposed_amount", -1))
    amount = int(event.payload.get("amount", -1))
    prevented = int(event.payload.get("prevented", 0))
    if proposed < 1 or amount < 0 or prevented < 0:
        raise DamageError("Resolved damage event produced invalid amounts")
    return proposed, amount, prevented


def _final_event(
    event: ReplaceableEvent,
    *,
    proposed: int,
    dealt: int,
    prevented: int,
) -> DamageEvent:
    payload = event.payload
    target_kind = str(payload.get("target_kind") or "")
    if target_kind not in {"player", "permanent"}:
        raise DamageError("Resolved damage event lost its recipient kind")
    return DamageEvent(
        source=str(payload.get("source") or ""),
        source_object_id=str(payload.get("source_object_id") or ""),
        source_logical_object_id=str(
            payload.get("source_logical_object_id") or ""
        ),
        source_controller=str(payload.get("source_controller") or ""),
        source_owner=str(payload.get("source_owner") or ""),
        source_types=tuple(str(value) for value in payload.get("source_types", ())),
        source_subtypes=tuple(
            str(value) for value in payload.get("source_subtypes", ())
        ),
        source_colors=tuple(
            str(value) for value in payload.get("source_colors", ())
        ),
        source_keywords=tuple(
            str(value) for value in payload.get("source_keywords", ())
        ),
        source_is_commander=bool(payload.get("source_is_commander")),
        target=str(payload.get("target") or ""),
        target_kind=target_kind,  # type: ignore[arg-type]
        target_object_id=(
            str(payload["target_object_id"])
            if payload.get("target_object_id") is not None
            else None
        ),
        target_controller=(
            str(payload["target_controller"])
            if payload.get("target_controller") is not None
            else None
        ),
        target_types=tuple(
            str(value) for value in payload.get("target_types", ())
        ),
        target_subtypes=tuple(
            str(value) for value in payload.get("target_subtypes", ())
        ),
        assigned_amount=proposed,
        dealt_amount=dealt,
        prevented_amount=prevented,
        combat=bool(payload.get("combat")),
        damage_step=(
            int(payload["damage_step"])
            if payload.get("damage_step") is not None
            else None
        ),
        first_strike_step=bool(payload.get("first_strike_step")),
        unpreventable=bool(payload.get("unpreventable")),
        applied_effects=event.applied_effects,
    )


def _log_replacement_journal(
    host: DamageHost,
    prepared: PreparedDamageBatch,
) -> None:
    effects = {effect.effect_id: effect for effect in prepared.effects}
    events = {event.event_id: event for event in prepared.events}
    for selection in prepared.journal:
        selected_id = str(selection.effect_id or "")
        if selected_id.startswith("decline:"):
            continue
        effect = effects.get(selected_id)
        event = events.get(selection.event_id)
        if effect is None or event is None:
            raise DamageError(
                "Damage replacement journal does not match its snapshot"
            )
        host._log(
            None,
            "replacement.apply",
            f"{effect.source_id} modified a damage event.",
            {
                "source": effect.source_id,
                "effect_id": effect.effect_id,
                "damage_source": event.payload.get("source"),
                "target": event.payload.get("target"),
                "proposed": event.payload.get("proposed_amount"),
                "dealt": event.payload.get("amount"),
                "prevented": event.payload.get("prevented"),
            },
            importance=2,
        )


def commit_prepared_damage_batch(
    host: DamageHost,
    prepared: PreparedDamageBatch,
    *,
    log_replacements: bool = True,
) -> DamageBatchResult:
    """Atomically validate and commit a choice-complete damage batch."""

    plans: list[tuple[ReplaceableEvent, int, int, int, Any | None]] = []
    for event in prepared.events:
        proposed, amount, prevented = _event_result(event)
        target_kind = str(event.payload.get("target_kind") or "")
        target = str(event.payload.get("target") or "")
        source_keywords = set(event.payload.get("source_keywords") or ())
        if target_kind == "player":
            if target not in host.active_seats:
                raise DamageError("Damage recipient is no longer in the game")
            if "infect" in source_keywords:
                raise DamageError(
                    "Infect player-damage results are not yet represented"
                )
            if (
                bool(event.payload.get("combat"))
                and "toxic" in source_keywords
            ):
                raise DamageError(
                    "Toxic combat-damage results are not yet represented"
                )
            plans.append((event, proposed, amount, prevented, None))
            continue
        if target_kind != "permanent":
            raise DamageError("Resolved damage event lost its recipient")
        card, _damageable = _permanent_result_plan(host, event, amount)
        plans.append((event, proposed, amount, prevented, card))

    changed_objects: list[str] = []
    changed_players: list[str] = []
    final_events: list[DamageEvent] = []
    lifelink: dict[tuple[str, str], int] = {}
    for event, proposed, amount, prevented, card in plans:
        payload = event.payload
        target = str(payload.get("target") or "")
        if card is None:
            host.state.players[target].life -= amount
            if amount:
                changed_players.append(target)
            if (
                amount
                and bool(payload.get("combat"))
                and bool(payload.get("source_is_commander"))
            ):
                commander_key = str(payload.get("source_object_id") or "")
                # Existing records key commander damage by Oracle ID. The
                # source object remains authoritative and resolves that ID.
                source_card = host.state.cards.get(commander_key)
                if source_card is not None:
                    commander_key = source_card.oracle_id
                received = host.state.players[target].commander_damage_received
                received[commander_key] = received.get(commander_key, 0) + amount
        else:
            apply_damage_results_to_permanent(
                host,
                card,
                amount,
                deathtouch=bool(payload.get("deathtouch")) and amount > 0,
                source_keywords=tuple(payload.get("source_keywords") or ()),
            )
            if amount:
                changed_objects.append(card.object_id)
        final = _final_event(
            event,
            proposed=proposed,
            dealt=amount,
            prevented=prevented,
        )
        final_events.append(final)
        if amount and "lifelink" in final.source_keywords:
            key = (final.source_controller, final.source)
            lifelink[key] = lifelink.get(key, 0) + amount
        if amount and final.target_kind == "player":
            host._record_turn_history(
                "player_damaged",
                actor=final.source_controller,
                object_incarnation=final.source_logical_object_id,
                target=final.target,
                target_kind="player",
                amount=amount,
            )

    gains: list[DamageLifeGain] = []
    for (player, source), amount in sorted(lifelink.items()):
        if player not in host.active_seats:
            continue
        host.state.players[player].life += amount
        changed_players.append(player)
        gains.append(DamageLifeGain(player=player, source=source, amount=amount))

    if log_replacements:
        _log_replacement_journal(host, prepared)
    return DamageBatchResult(
        events=tuple(final_events),
        changed_objects=tuple(dict.fromkeys(changed_objects)),
        changed_players=tuple(dict.fromkeys(changed_players)),
        lifelink_gains=tuple(gains),
    )


def resolve_damage_batch(
    host: DamageHost,
    proposals: Sequence[DamageProposal],
    *,
    replacement_selections: Sequence[str | None] = (),
) -> DamageBatchResult:
    """Resolve one typed damage batch through results and trigger discovery."""

    trigger_sources = host._semantic_event_sources()
    trigger_source_zones = {
        source.object_id: source.zone for source in trigger_sources
    }
    prepared = prepare_damage_batch(
        host,
        proposals,
        selections=replacement_selections,
        sources=trigger_sources,
        source_zones=trigger_source_zones,
    )
    result = commit_prepared_damage_batch(host, prepared)

    for gain in result.lifelink_gains:
        host._log(
            gain.player,
            "damage.lifelink",
            f"{gain.player} gained {gain.amount} life from {gain.source}.",
            {
                "player": gain.player,
                "source": gain.source,
                "amount": gain.amount,
            },
            importance=1,
            changed_players=[gain.player],
        )

    trigger_batch: list[Any] = []
    for event in result.events:
        if not event.was_dealt:
            continue
        if (
            host.state.monarch is not None
            and event.target_kind == "player"
            and event.target == host.state.monarch
            and event.combat
            and "creature" in event.source_types
            and event.source_controller in host.active_seats
        ):
            old_monarch = str(host.state.monarch)
            new_monarch = event.source_controller
            trigger_batch.append(
                host._monarch_trigger(
                    controller=old_monarch,
                    label=(
                        "The monarch — "
                        f"{new_monarch} becomes the monarch"
                    ),
                    effects=(
                        {
                            "op": "become_monarch",
                            "player": new_monarch,
                            "reason": (
                                "a creature dealt combat damage to "
                                "the monarch"
                            ),
                        },
                    ),
                    context={
                        "event": "damage.dealt",
                        "source": event.source,
                        "damaged_player": event.target,
                        "new_monarch": new_monarch,
                        "monarch_at_trigger": old_monarch,
                        "inherent_rule": "CR 725.2b",
                    },
                )
            )
        host._dispatch_semantic_event(
            "damage.dealt",
            event.semantic_context(),
            sources=trigger_sources,
            source_zones=trigger_source_zones,
            trigger_batch=trigger_batch,
        )
        if host._semantic_pause_annotation() is not None:
            break
    host._enqueue_semantic_trigger_batch(trigger_batch)
    return result
