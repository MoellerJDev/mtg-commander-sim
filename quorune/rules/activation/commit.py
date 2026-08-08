from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from ...abilities import ActivatedAbility
from ...counter_state import (
    CounterChange,
    commit_counter_changes,
    plan_counter_changes,
)
from ...life_state import LifeStateError, pay_life_cost
from ...mana_activation import complete_mana_activation
from ...mana_undo import clear_mana_undo_stack
from ...model import StackItem, YieldPolicy
from ...tap_state import set_permanent_tapped
from ..action_proposals import ActivationProposal, thaw_json
from .model import ActivationProposalError


class ActivationCommitHost(Protocol):
    state: Any
    seats: list[str]

    def _resolve_object(self, actor: str, ref: str, *, zones: set[str], **kwargs: Any) -> Any: ...

    def _activated_abilities(self, source: Any) -> tuple[ActivatedAbility, ...]: ...

    def _crew_threshold(self, ability: ActivatedAbility) -> int | None: ...

    def _pay_crew_cost(
        self,
        seat: str,
        source: Any,
        ability: ActivatedAbility,
        response: Mapping[str, Any],
    ) -> list[str]: ...

    def _pay_ability_choice_costs(
        self,
        seat: str,
        source: Any,
        ability: ActivatedAbility,
        response: Mapping[str, Any],
    ) -> list[str]: ...

    def _target_snapshot(self, ref: str) -> Mapping[str, Any]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(self, type_line: str) -> tuple[set[str], set[str], set[str]]: ...

    def _pay_for_cost(self, seat: str, requirements: Mapping[str, int], response: Mapping[str, Any], **kwargs: Any) -> tuple[dict[str, int], list[dict[str, Any]]]: ...

    def move_card(self, object_id: str, zone: str, **kwargs: Any) -> Any: ...

    def _next_ref(self, prefix: str) -> str: ...

    def _stable_runtime_id(self, kind: str, ref: str) -> str: ...

    def display_name(self, object_id: str) -> str: ...

    def _queue_ward_triggers_for_targets(self, item: StackItem) -> Any: ...

    def _log(self, actor: str | None, code: str, summary: str, details: Any = None, **kwargs: Any) -> None: ...

    def _stabilize(self) -> bool: ...


def _revalidate_activation(
    host: ActivationCommitHost, proposal: ActivationProposal
) -> tuple[Any, ActivatedAbility]:
    source = host._resolve_object(
        proposal.seat,
        proposal.source_ref,
        zones={proposal.source_zone},
        controlled_only=False,
        owned_only=False,
    )
    if source.object_id != proposal.source_object_id:
        raise ActivationProposalError(
            "The activation source changed after proposal construction",
            reason="stale_source",
        )
    ability = next(
        (
            value
            for value in host._activated_abilities(source)
            if value.ability_id == proposal.ability_id
            and source.zone in value.zones
        ),
        None,
    )
    if ability is None:
        raise ActivationProposalError(
            "The selected ability is no longer available",
            reason="stale_ability",
        )
    return source, ability


def _commit_symbol_costs(
    host: ActivationCommitHost,
    proposal: ActivationProposal,
    source: Any,
    ability: ActivatedAbility,
) -> None:
    if ability.tap_source:
        set_permanent_tapped(
            host,
            source.ref,
            actor=proposal.seat,
            tapped=True,
            reason=f"{ability.ability_id} activation cost",
            log=False,
        )
    if ability.untap_source:
        set_permanent_tapped(
            host,
            source.ref,
            actor=proposal.seat,
            tapped=False,
            revert=True,
            reason=f"{ability.ability_id} activation cost",
            log=False,
        )


def _commit_resource_costs(
    host: ActivationCommitHost,
    proposal: ActivationProposal,
    source: Any,
    ability: ActivatedAbility,
) -> None:
    if ability.life_payment:
        try:
            pay_life_cost(host, proposal.seat, ability.life_payment)
        except LifeStateError as exc:
            raise ActivationProposalError(
                "Cannot pay more life than the player has",
                status="unpayable",
                reason="life_cost_unpayable",
            ) from exc
    counter_changes = []
    if ability.energy_payment:
        counter_changes.append(
            CounterChange(
                "player", proposal.seat, "energy", -ability.energy_payment
            )
        )
    if ability.loyalty_delta is not None:
        counter_changes.append(
            CounterChange(
                "permanent",
                source.object_id,
                "loyalty",
                ability.loyalty_delta,
                expected_zone="battlefield",
                expected_logical_object_id=source.logical_object_id,
            )
        )
    if not counter_changes:
        return
    plans = plan_counter_changes(host, counter_changes)
    for transition in plans.transitions:
        if transition.after != transition.before + transition.requested_delta:
            resource = transition.counter_name
            raise ActivationProposalError(
                f"The source no longer has enough {resource}",
                status="unpayable",
                reason=f"{resource}_cost_unpayable",
            )
    commit_counter_changes(host, plans)
    if ability.loyalty_delta is not None:
        source.annotations["loyalty_initialized"] = True
        source.annotations["loyalty_activated_turn_sequence"] = host.state.turn_sequence
        host._log(
            proposal.seat,
            "cost.loyalty",
            f"{proposal.seat} changed {source.ref}'s loyalty by {ability.loyalty_delta}.",
            {
                "source": source.ref,
                "delta": ability.loyalty_delta,
                "loyalty": source.counters.get("loyalty", 0),
            },
            importance=1,
            changed_objects=[source.object_id],
            changed_players=[proposal.seat],
        )


def _pay_object_and_mana_costs(
    host: ActivationCommitHost,
    proposal: ActivationProposal,
    source: Any,
    ability: ActivatedAbility,
    response: Mapping[str, Any],
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    paid_objects = (
        host._pay_crew_cost(proposal.seat, source, ability, response)
        if host._crew_threshold(ability) is not None
        else host._pay_ability_choice_costs(
            proposal.seat, source, ability, response
        )
    )
    requirements = dict(thaw_json(proposal.requirements))
    spent: dict[str, int] = {}
    activations: list[dict[str, Any]] = []
    if sum(requirements.values()):
        source_types = host._type_parts(
            str(host._effective_card_data(source).get("type_line") or "")
        )[0]
        spent, activations = host._pay_for_cost(
            proposal.seat,
            requirements,
            response,
            spend_context=(
                "artifact_ability" if "artifact" in source_types else "ability"
            ),
        )
    return paid_objects, activations, spent


def _commit_source_cost(
    host: ActivationCommitHost, source: Any, ability: ActivatedAbility
) -> str:
    origin = source.zone
    destination = None
    if ability.discard_source:
        if source.zone != "hand":
            raise ActivationProposalError(
                "Discard-this-card cost requires the source in hand"
            )
        destination = "graveyard"
    elif ability.sacrifice_source:
        if source.zone != "battlefield":
            raise ActivationProposalError(
                "Sacrifice-source cost requires the source on the battlefield"
            )
        destination = "graveyard"
    elif ability.exile_source:
        destination = "exile"
    if destination is not None:
        host.move_card(
            source.object_id,
            destination,
            reason="activated ability cost",
            semantic_events=True,
        )
    return origin


def _activation_stack_item(
    host: ActivationCommitHost,
    proposal: ActivationProposal,
    source: Any,
    ability: ActivatedAbility,
    response: Mapping[str, Any],
    paid_objects: Sequence[str],
) -> StackItem:
    details = dict(thaw_json(proposal.details))
    snapshots = [
        host._target_snapshot(host.state.cards[object_id].ref)
        for object_id in paid_objects
    ]
    ref = host._next_ref("S")
    return StackItem(
        stack_id=host._stable_runtime_id("stack", ref),
        ref=ref,
        kind="activated_ability",
        controller=proposal.seat,
        label=str(
            response.get("label")
            or f"{host.display_name(source.object_id)} — {ability.effect_text}"
        ),
        source_object_id=source.object_id,
        semantic_key=str(proposal.semantic_key or ""),
        targets=list(proposal.targets),
        modes=list(details.get("selected_modes") or []),
        notes=str(response.get("note") or ""),
        visibility=list(host.seats),
        context={
            "source_logical_object_id": source.logical_object_id,
            **dict(details.get("builtin_context") or {}),
            "target_groups": thaw_json(proposal.target_groups),
            "target_snapshots": thaw_json(proposal.target_snapshots),
            "targets_revalidated": False,
            "targets_chosen_at_creation": True,
            **(
                {"target_schema_override": details["target_schema_override"]}
                if details.get("target_schema_override") is not None
                else {}
            ),
            "cost_objects": [
                host.state.cards[object_id].ref for object_id in paid_objects
            ],
            "cost_object_snapshots": snapshots,
            "cost_mana_value_plus_one": (
                float(snapshots[0].get("mana_value", 0)) + 1
                if len(snapshots) == 1
                else None
            ),
        },
    )


def commit_activation(
    host: ActivationCommitHost,
    proposal: ActivationProposal,
    response: Mapping[str, Any],
) -> None:
    """Commit one revalidated activation proposal through typed state owners."""

    source, ability = _revalidate_activation(host, proposal)
    if not ability.mana_ability:
        clear_mana_undo_stack(host.state.players[proposal.seat].stats)
    _commit_symbol_costs(host, proposal, source, ability)
    paid_objects, activations, spent = _pay_object_and_mana_costs(
        host, proposal, source, ability, response
    )
    _commit_resource_costs(host, proposal, source, ability)
    if "only once each turn" in ability.effect_text.casefold():
        once = dict(source.annotations.get("once_per_turn_activations", {}))
        once[ability.ability_id] = host.state.turn_sequence
        source.annotations["once_per_turn_activations"] = once
    origin = _commit_source_cost(host, source, ability)
    if ability.mana_ability:
        complete_mana_activation(
            host,
            seat=proposal.seat,
            source=source,
            ability=ability,
            response=response,
            origin=origin,
            paid_objects=paid_objects,
            payment_activations=activations,
        )
        return
    item = _activation_stack_item(
        host, proposal, source, ability, response, paid_objects
    )
    host.state.stack.append(item)
    host._queue_ward_triggers_for_targets(item)
    host._log(
        proposal.seat,
        "stack.activate",
        f"{proposal.seat} activated {item.ref}: {item.label}.",
        {
            "stack": item.ref,
            "source": source.ref,
            "ability": ability.ability_id,
            "from": origin,
            "requirements": thaw_json(proposal.requirements),
            "payment": {key: value for key, value in spent.items() if value},
            "mana_sources": [
                {
                    "source": activation.get("source_ref"),
                    "bundle": activation.get("bundle"),
                }
                for activation in activations
            ],
            "cost_objects": [
                host.state.cards[object_id].ref for object_id in paid_objects
            ],
            "targets": item.targets,
            "modes": item.modes,
            "life_paid": ability.life_payment,
            "energy_paid": ability.energy_payment,
        },
        importance=2,
        changed_objects=[source.object_id, *paid_objects],
        changed_players=[proposal.seat],
    )
    if host._stabilize():
        return
    host.state.priority_player = proposal.seat
    host.state.priority_passes = []
    host.state.players[proposal.seat].yield_policy = YieldPolicy()


__all__ = ["ActivationCommitHost", "commit_activation"]
