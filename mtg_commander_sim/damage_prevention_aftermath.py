from __future__ import annotations

from dataclasses import dataclass, replace
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
from .life_change import (
    commit_life_change_batch,
    LifeChangeError,
    LifeChangeRequest,
    PreparedLifeChangeBatch,
    prepare_life_change_batch,
    replan_life_change_batch,
    validate_life_change_batch,
)
from .replacement import (
    ReplaceableEvent,
    ReplacementChoiceRequired,
    ReplacementEventBatch,
)
from .semantic_runtime.damage_results import (
    collect_life_change_replacement_effects,
)


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
    life_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedPreventionAftermath:
    applications: tuple[PreventionApplication, ...] = ()
    instructions: tuple[PreparedAftermathInstruction, ...] = ()
    life_batch: PreparedLifeChangeBatch | None = None
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
    life_requests: list[LifeChangeRequest] = []
    counter_requests: list[CounterPlacementRequest] = []
    for application in applications:
        shield = shields.get(application.effect_id)
        if shield is None:
            raise PreventionAftermathError(
                "Prevention aftermath lost its durable shield"
            )
        for aftermath_index, aftermath in enumerate(shield.aftermath):
            amount = aftermath.amount(application.prevented_amount)
            if amount == 0:
                continue
            if isinstance(aftermath, GainLifePreventionAftermath):
                life_event_id = (
                    "damage.prevention.aftermath:life:"
                    f"{application.effect_id}:{aftermath_index}"
                )
                life_requests.append(
                    LifeChangeRequest(
                        event_id=life_event_id,
                        player=aftermath.player,
                        amount=amount,
                        source=application.source_id,
                        source_controller=shield.controller,
                        cause="damage_prevention_aftermath",
                    )
                )
                kind = "gain_life"
                subject = aftermath.player
            elif isinstance(aftermath, PlaceCountersPreventionAftermath):
                life_event_id = None
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
                    life_event_id=life_event_id,
                )
            )
    life_effects = collect_life_change_replacement_effects(
        host,
        sources=sources,
        source_zones=source_zones,
    )
    try:
        life_batch = prepare_life_change_batch(
            host,
            tuple(life_requests),
            effects=life_effects,
            selections=selections,
            require_all_selections=False,
            batch_id=(
                f"replacement:damage.prevention.aftermath.life:"
                f"{host.state.revision}:{host.state.event_sequence + 1}"
            ),
        )
    except LifeChangeError as exc:
        raise PreventionAftermathError(str(exc)) from exc
    if life_batch.pending is not None:
        raise ReplacementChoiceRequired(
            batch=ReplacementEventBatch(
                batch_id=life_batch.batch_id,
                events=life_batch.events,
                apnap_order=tuple(host.apnap_order()),
                journal=life_batch.journal,
            ),
            effects=life_batch.effects,
            pending=life_batch.pending,
        )
    counter_selections = tuple(
        selections[life_batch.consumed_selections:]
    )
    try:
        prepared_counters = prepare_counter_placements(
            host,
            tuple(counter_requests),
            selections=counter_selections,
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
    if counter_selections and not counter_requests:
        raise PreventionAftermathError(
            "Replacement selections were supplied without counter aftermath"
        )
    return PreparedPreventionAftermath(
        applications=applications,
        instructions=tuple(instructions),
        life_batch=life_batch,
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
    if prepared.life_batch is not None:
        try:
            validate_life_change_batch(host, prepared.life_batch)
        except LifeChangeError as exc:
            raise PreventionAftermathError(str(exc)) from exc
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

    if prepared.life_batch is not None:
        try:
            prepared = replace(
                prepared,
                life_batch=replan_life_change_batch(
                    host, prepared.life_batch
                ),
            )
        except LifeChangeError as exc:
            raise PreventionAftermathError(str(exc)) from exc
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
        life_commit = (
            commit_life_change_batch(host, prepared.life_batch)
            if prepared.life_batch is not None
            else None
        )
    except LifeChangeError as exc:
        raise PreventionAftermathError(str(exc)) from exc

    counter_index = 0
    life_records = {
        record.event_id: record
        for record in (() if life_commit is None else life_commit.records)
    }
    events: list[PreventionAftermathEvent] = []
    for instruction in prepared.instructions:
        applied = instruction.requested_amount
        if instruction.kind == "gain_life":
            record = life_records.get(str(instruction.life_event_id or ""))
            if record is None:
                raise PreventionAftermathError(
                    "Prevention life aftermath lost its resolved event"
                )
            applied = record.amount
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
                (() if life_commit is None else life_commit.changed_players)
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
