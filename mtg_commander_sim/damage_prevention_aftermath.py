from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .counter_placement import (
    commit_counter_placement_plan,
    CounterPlacementCommitPlan,
    CounterPlacementError,
    CounterPlacementRequest,
    plan_prepared_counter_placement_commit,
    prepare_counter_placements,
    validate_counter_placement_commit,
)
from .damage_modifier_state import (
    DamagePreventionShield,
    GainLifePreventionAftermath,
    PlaceCountersPreventionAftermath,
)
from .life_state import (
    commit_life_changes,
    LifeChange,
    LifeStateError,
    plan_life_changes,
)
from .replacement import ReplaceableEvent


class PreventionAftermathError(ValueError):
    """A CR 615.5 immediately-after result is malformed or stale."""


class PreventionAftermathHost(Protocol):
    state: Any

    def _semantic_event_sources(
        self, *, zones: set[str] | None = None
    ) -> list[Any]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def apnap_order(self, *, start: str | None = None) -> list[str]: ...

    def _log(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class PreventionApplication:
    effect_id: str
    source_id: str
    prevented_amount: int
    damage_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedAftermathInstruction:
    effect_id: str
    source_id: str
    kind: str
    subject: str
    prevented_amount: int
    requested_amount: int
    damage_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedPreventionAftermath:
    applications: tuple[PreventionApplication, ...] = ()
    instructions: tuple[PreparedAftermathInstruction, ...] = ()
    life_changes: tuple[LifeChange, ...] = ()
    counter_plan: CounterPlacementCommitPlan | None = None
    consumed_selections: int = 0


@dataclass(frozen=True, slots=True)
class PreventionAftermathEvent:
    effect_id: str
    source_id: str
    kind: str
    subject: str
    prevented_amount: int
    applied_amount: int
    damage_event_ids: tuple[str, ...]

    def semantic_context(self) -> dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "source": self.source_id,
            "kind": self.kind,
            "subject": self.subject,
            "prevented_amount": self.prevented_amount,
            "applied_amount": self.applied_amount,
            "damage_event_ids": list(self.damage_event_ids),
        }


@dataclass(frozen=True, slots=True)
class PreventionAftermathResult:
    events: tuple[PreventionAftermathEvent, ...] = ()
    changed_players: tuple[str, ...] = ()
    changed_objects: tuple[str, ...] = ()


def prevention_applications(
    host: PreventionAftermathHost,
    events: Sequence[ReplaceableEvent],
) -> tuple[PreventionApplication, ...]:
    """Aggregate one shield application across a simultaneous damage batch."""

    shields = {
        shield.effect_id: shield
        for shield in host.state.damage_prevention_shields
        if shield.aftermath
    }
    amounts: dict[str, int] = {}
    event_ids: dict[str, list[str]] = {}
    applied: set[str] = set()
    for event in events:
        by_effect = event.payload.get("prevention_applied") or {}
        if not isinstance(by_effect, Mapping):
            raise PreventionAftermathError(
                "Resolved prevention application data is malformed"
            )
        for effect_id in event.applied_effects:
            if effect_id in shields:
                applied.add(effect_id)
                event_ids.setdefault(effect_id, []).append(event.event_id)
        for raw_id, raw_amount in by_effect.items():
            effect_id = str(raw_id)
            if effect_id not in shields:
                continue
            if type(raw_amount) is not int or raw_amount < 0:
                raise PreventionAftermathError(
                    "Resolved prevention amount is malformed"
                )
            applied.add(effect_id)
            amounts[effect_id] = amounts.get(effect_id, 0) + raw_amount
            if event.event_id not in event_ids.setdefault(effect_id, []):
                event_ids[effect_id].append(event.event_id)
    return tuple(
        PreventionApplication(
            effect_id=effect_id,
            source_id=shields[effect_id].source_id,
            prevented_amount=amounts.get(effect_id, 0),
            damage_event_ids=tuple(sorted(set(event_ids.get(effect_id, ())))),
        )
        for effect_id in sorted(applied)
    )


def prepare_prevention_aftermath(
    host: PreventionAftermathHost,
    events: Sequence[ReplaceableEvent],
    *,
    selections: Sequence[str | None] = (),
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
) -> PreparedPreventionAftermath:
    applications = prevention_applications(host, events)
    shields: dict[str, DamagePreventionShield] = {
        shield.effect_id: shield
        for shield in host.state.damage_prevention_shields
    }
    instructions: list[PreparedAftermathInstruction] = []
    life_changes: list[LifeChange] = []
    counter_requests: list[CounterPlacementRequest] = []
    for application in applications:
        shield = shields.get(application.effect_id)
        if shield is None:
            raise PreventionAftermathError(
                "Prevention aftermath lost its durable shield"
            )
        for aftermath in shield.aftermath:
            amount = aftermath.amount(application.prevented_amount)
            if amount == 0:
                continue
            if isinstance(aftermath, GainLifePreventionAftermath):
                life_changes.append(LifeChange(aftermath.player, amount))
                kind = "gain_life"
                subject = aftermath.player
            elif isinstance(aftermath, PlaceCountersPreventionAftermath):
                assert aftermath.subject.object_id is not None
                counter_requests.append(
                    CounterPlacementRequest(
                        object_id=aftermath.subject.object_id,
                        counter_name=aftermath.counter_name,
                        amount=amount,
                        placing_player=aftermath.placing_player,
                        source_ref=application.source_id,
                    )
                )
                kind = "place_counters"
                subject = aftermath.subject.ref
            else:  # pragma: no cover - shield validation closes this union.
                raise PreventionAftermathError(
                    "Unsupported prevention aftermath operation"
                )
            instructions.append(
                PreparedAftermathInstruction(
                    effect_id=application.effect_id,
                    source_id=application.source_id,
                    kind=kind,
                    subject=subject,
                    prevented_amount=application.prevented_amount,
                    requested_amount=amount,
                    damage_event_ids=application.damage_event_ids,
                )
            )
    try:
        prepared_counters = prepare_counter_placements(
            host,
            tuple(counter_requests),
            selections=selections,
            sources=sources,
            source_zones=source_zones,
        )
        counter_plan = (
            plan_prepared_counter_placement_commit(host, prepared_counters)
            if prepared_counters.events
            else None
        )
    except CounterPlacementError as exc:
        raise PreventionAftermathError(str(exc)) from exc
    if selections and not counter_requests:
        raise PreventionAftermathError(
            "Replacement selections were supplied without counter aftermath"
        )
    return PreparedPreventionAftermath(
        applications=applications,
        instructions=tuple(instructions),
        life_changes=tuple(life_changes),
        counter_plan=counter_plan,
        consumed_selections=len(selections),
    )


def validate_prevention_aftermath(
    host: PreventionAftermathHost,
    prepared: PreparedPreventionAftermath,
) -> None:
    if not isinstance(prepared, PreparedPreventionAftermath):
        raise PreventionAftermathError(
            "Prevention aftermath requires a typed prepared value"
        )
    for change in prepared.life_changes:
        if change.player not in host.state.active_seats():
            raise PreventionAftermathError(
                "Prevention aftermath player is no longer active"
            )
    if prepared.counter_plan is not None:
        try:
            validate_counter_placement_commit(host, prepared.counter_plan)
        except CounterPlacementError as exc:
            raise PreventionAftermathError(str(exc)) from exc


def commit_prevention_aftermath(
    host: PreventionAftermathHost,
    prepared: PreparedPreventionAftermath,
) -> PreventionAftermathResult:
    """Commit CR 615.5 results immediately after the prevention batch."""

    validate_prevention_aftermath(host, prepared)
    counter_results = ()
    if prepared.counter_plan is not None:
        try:
            counter_results = commit_counter_placement_plan(
                host,
                prepared.counter_plan,
                reason="damage prevention aftermath",
            )
        except CounterPlacementError as exc:
            raise PreventionAftermathError(str(exc)) from exc
    try:
        life_transitions = commit_life_changes(
            host, plan_life_changes(host, prepared.life_changes)
        )
    except LifeStateError as exc:
        raise PreventionAftermathError(str(exc)) from exc

    counter_index = 0
    events: list[PreventionAftermathEvent] = []
    for instruction in prepared.instructions:
        applied = instruction.requested_amount
        if instruction.kind == "place_counters":
            applied = counter_results[counter_index].placed
            counter_index += 1
        events.append(
            PreventionAftermathEvent(
                effect_id=instruction.effect_id,
                source_id=instruction.source_id,
                kind=instruction.kind,
                subject=instruction.subject,
                prevented_amount=instruction.prevented_amount,
                applied_amount=applied,
                damage_event_ids=instruction.damage_event_ids,
            )
        )
    return PreventionAftermathResult(
        events=tuple(events),
        changed_players=tuple(
            sorted(
                transition.player
                for transition in life_transitions
                if transition.before != transition.after
            )
        ),
        changed_objects=tuple(
            sorted({result.object_id for result in counter_results})
        ),
    )


__all__ = [
    "PreparedPreventionAftermath",
    "PreventionAftermathError",
    "PreventionAftermathEvent",
    "PreventionAftermathResult",
    "commit_prevention_aftermath",
    "prepare_prevention_aftermath",
    "prevention_applications",
    "validate_prevention_aftermath",
]
