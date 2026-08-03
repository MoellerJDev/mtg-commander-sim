from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ...life_state import LifeStateError, pay_life_cost
from ...model import StackItem, YieldPolicy
from ...tap_state import set_permanent_tapped
from ..action_proposals import CastProposal, thaw_json
from .model import CastProposalError


class CastCommitHost(Protocol):
    state: Any
    semantics: Any
    seats: list[str]

    def _resolve_object(
        self,
        actor: str,
        ref: str,
        *,
        zones: set[str],
        controlled_only: bool = False,
        owned_only: bool = False,
    ) -> Any: ...

    def card_record(self, card: Any) -> Any: ...

    def _pay_for_cost(
        self,
        seat: str,
        requirements: Mapping[str, int],
        response: Mapping[str, Any],
        *,
        exclude_sources: set[str] | None = None,
        spend_context: Any = None,
    ) -> tuple[dict[str, int], list[dict[str, Any]]]: ...

    def _spell_mana_spend_context(self, type_line: str) -> Any: ...

    def _log(self, actor: str | None, code: str, summary: str, details: Any = None, **kwargs: Any) -> None: ...

    def move_card(self, object_id: str, zone: str, **kwargs: Any) -> Any: ...

    def _semantic_event_sources(self) -> list[Any]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _remove_from_zone(self, card: Any) -> None: ...

    def _reset_zone_change(self, card: Any, zone: str) -> None: ...

    def _next_ref(self, prefix: str) -> str: ...

    def _stable_runtime_id(self, kind: str, ref: str) -> str: ...

    def _current_turn_history(self, kind: str) -> Sequence[Any]: ...

    def _stack_target_schema(self, item: Any, program: Any) -> Any: ...

    def _dispatch_zone_change_events(self, *args: Any, **kwargs: Any) -> None: ...

    def _type_parts(self, type_line: str) -> tuple[set[str], set[str], set[str]]: ...

    def _record_turn_history(self, kind: str, **kwargs: Any) -> None: ...

    def _dispatch_semantic_event(self, event: str, context: Mapping[str, Any], **kwargs: Any) -> None: ...

    def _enqueue_semantic_trigger_batch(self, items: Sequence[Any]) -> None: ...

    def _queue_ward_triggers_for_targets(self, item: Any) -> Any: ...

    def _stabilize(self) -> bool: ...


@dataclass(slots=True)
class _AdditionalCostCommit:
    deferred_events: list[tuple[Any, str, str, str, dict[str, Any], list[str]]]
    source_snapshots: list[Any]
    source_zones: dict[str, str]
    paid_refs: list[str]


def _revalidate_source(host: CastCommitHost, proposal: CastProposal) -> tuple[Any, Any, Any]:
    card = host._resolve_object(
        proposal.seat,
        proposal.card_ref,
        zones={proposal.origin},
        owned_only=False,
    )
    if card.object_id != proposal.object_id or card.zone != proposal.origin:
        raise CastProposalError(
            "The casting source changed after proposal construction",
            reason="stale_source",
        )
    record = host.card_record(card)
    if record is None:
        raise CastProposalError("The casting card record is unavailable")
    program = host.semantics.get(proposal.semantic_key)
    return card, record, program


def _commit_tap_costs(
    host: CastCommitHost, proposal: CastProposal, card: Any
) -> list[Any]:
    result = []
    for ref in proposal.tap_cost_refs:
        tapped = host._resolve_object(
            proposal.seat,
            ref,
            zones={"battlefield"},
            controlled_only=True,
        )
        if tapped.tapped:
            raise CastProposalError(
                f"{tapped.ref} is no longer available for a tap cost",
                status="unpayable",
                reason="tap_cost_unpayable",
            )
        set_permanent_tapped(
            host,
            tapped.ref,
            actor=proposal.seat,
            tapped=True,
            reason=f"{card.printed_name} casting cost",
            log=False,
        )
        host._log(
            proposal.seat,
            "cost.tap",
            f"{proposal.seat} tapped {tapped.ref} to help cast {card.printed_name}.",
            {
                "spell": card.ref,
                "object": tapped.ref,
                "cost_option": proposal.cost_option_id,
            },
            importance=1,
            changed_objects=[tapped.object_id],
            changed_players=[proposal.seat],
        )
        result.append(tapped)
    return result


def _pay_life_additional_cost(
    host: CastCommitHost,
    proposal: CastProposal,
    response: Mapping[str, Any],
    card: Any,
    selected_option: Mapping[str, Any],
) -> None:
    amount = int(response.get("x", 0))
    try:
        pay_life_cost(host, proposal.seat, amount)
    except LifeStateError as exc:
        raise CastProposalError(
            "The selected life payment is no longer payable",
            status="unpayable",
            reason="life_cost_unpayable",
        ) from exc
    host._log(
        proposal.seat,
        "cost.life",
        f"{proposal.seat} paid {amount} life to cast {card.printed_name}.",
        {
            "object": card.ref,
            "amount": amount,
            "cost_option": selected_option["id"],
        },
        importance=1,
        changed_players=[proposal.seat],
    )


def _commit_additional_costs(
    host: CastCommitHost,
    proposal: CastProposal,
    response: Mapping[str, Any],
    card: Any,
    selected_option: Mapping[str, Any],
) -> _AdditionalCostCommit:
    result = _AdditionalCostCommit([], [], {}, [])
    selected_exile = selected_option.get("selected_exile_card")
    if selected_exile:
        exiled = host._resolve_object(
            proposal.seat,
            str(selected_exile),
            zones={"hand"},
            owned_only=True,
        )
        host.move_card(
            exiled.object_id,
            "exile",
            reason=f"{card.printed_name} alternate cost",
            semantic_events=True,
        )
    for additional in selected_option.get("additional_costs", []):
        if additional.get("kind") == "life_x":
            _pay_life_additional_cost(
                host, proposal, response, card, selected_option
            )
    selections = list(selected_option.get("selected_additional_costs", []))
    if not selections:
        return result
    result.source_snapshots = host._semantic_event_sources()
    result.source_zones = {
        source.object_id: source.zone for source in result.source_snapshots
    }
    changes = []
    for selected in selections:
        kind = str(selected["kind"])
        zone = "hand" if kind == "discard" else "battlefield"
        for ref in selected.get("cards", []):
            paid = host._resolve_object(
                proposal.seat,
                str(ref),
                zones={zone},
                controlled_only=zone == "battlefield",
                owned_only=zone != "battlefield",
            )
            changes.append(
                (
                    paid,
                    paid.zone,
                    paid.controller,
                    paid.logical_object_id,
                    copy.deepcopy(host._effective_card_data(paid)),
                    [
                        host.state.cards[attachment_id].ref
                        for attachment_id in paid.attachments
                        if attachment_id in host.state.cards
                    ],
                    kind,
                )
            )
    for paid, origin, controller, logical_id, data, attachments, kind in changes:
        host.move_card(
            paid.object_id,
            "graveyard",
            reason=f"{card.printed_name} {kind} cost",
            semantic_events=False,
        )
        result.paid_refs.append(paid.ref)
        result.deferred_events.append(
            (paid, origin, controller, logical_id, data, attachments)
        )
        host._log(
            proposal.seat,
            f"cost.{kind}",
            f"{proposal.seat} paid {paid.ref} as a {kind} cost.",
            {"spell": card.ref, "object": paid.ref},
            importance=1,
            changed_objects=[paid.object_id],
            changed_players=[proposal.seat],
        )
    return result


def _create_spell_item(
    host: CastCommitHost,
    proposal: CastProposal,
    card: Any,
    record: Any,
    program: Any,
    selected_option: Mapping[str, Any],
    details: Mapping[str, Any],
) -> StackItem:
    card.annotations.pop("temporary_play_permission", None)
    host._remove_from_zone(card)
    host._reset_zone_change(card, "stack")
    card.zone = "stack"
    card.controller = proposal.seat
    card.active_face = proposal.face
    destination = (
        "battlefield"
        if any(
            word in proposal.type_line.casefold()
            for word in (
                "artifact",
                "battle",
                "creature",
                "enchantment",
                "planeswalker",
            )
        )
        else "graveyard"
    )
    ref = host._next_ref("S")
    used_improvise = bool(
        host.state.players[proposal.seat].stats.pop("next_spell_improvise", False)
    )
    used_uncounterable = bool(
        host.state.players[proposal.seat].stats.pop(
            "next_spell_uncounterable", False
        )
    )
    return StackItem(
        stack_id=host._stable_runtime_id("stack", ref),
        ref=ref,
        kind="spell",
        controller=proposal.seat,
        label=card.active_face or record.name,
        card_object_id=card.object_id,
        semantic_key=proposal.semantic_key,
        targets=list(proposal.targets),
        modes=list(details.get("selected_modes") or []),
        x_value=details.get("x_value"),
        chosen_face=card.active_face,
        notes=str(details.get("note") or ""),
        default_destination=destination,
        visibility=list(host.seats),
        context={
            "target_groups": thaw_json(proposal.target_groups),
            "target_snapshots": thaw_json(proposal.target_snapshots),
            "targets_revalidated": False,
            "targets_chosen_at_creation": True,
            "cant_be_countered": used_uncounterable,
            "granted_improvise": used_improvise,
            "cost_option": proposal.cost_option_id,
            **(
                {"target_schema_override": details["target_schema_override"]}
                if details.get("target_schema_override") is not None
                else {}
            ),
            **(
                {
                    "cast_option_effects": copy.deepcopy(
                        list(selected_option.get("effects", []))
                    )
                }
                if "effects" in selected_option
                else {}
            ),
        },
    )


def _queue_storm(host: CastCommitHost, proposal: CastProposal, item: StackItem, card: Any, program: Any) -> None:
    if not program or "storm" not in program.coverage:
        return
    prior_spells = (
        len(host._current_turn_history("spell_cast"))
        if host.state.turn_history is not None
        else sum(
            event.code == "stack.cast"
            and event.turn_sequence == host.state.turn_sequence
            for event in host.state.events
        )
    )
    ref = host._next_ref("S")
    target_groups = thaw_json(proposal.target_groups)
    target_snapshots = thaw_json(proposal.target_snapshots)
    storm = StackItem(
        stack_id=host._stable_runtime_id("stack", ref),
        ref=ref,
        kind="triggered_ability",
        controller=proposal.seat,
        label=f"{item.label} — Storm",
        source_object_id=card.object_id,
        semantic_key="builtin:storm",
        visibility=list(host.seats),
        context={
            "copy_count": prior_spells,
            "copy_template": {
                "label": item.label,
                "controller": item.controller,
                "card_object_id": item.card_object_id,
                "semantic_key": item.semantic_key,
                "targets": copy.deepcopy(item.targets),
                "modes": copy.deepcopy(item.modes),
                "x_value": item.x_value,
                "default_destination": item.default_destination,
                "referred_object_ids": copy.deepcopy(
                    item.referred_object_ids
                ),
                "target_groups": copy.deepcopy(target_groups),
                "target_snapshots": copy.deepcopy(target_snapshots),
                "target_schema": copy.deepcopy(
                    host._stack_target_schema(item, program)
                ),
            },
        },
    )
    host.state.stack.append(storm)
    host._log(
        proposal.seat,
        "stack.trigger",
        f"Queued {storm.ref}: {storm.label}.",
        {"stack": storm.ref, "source_stack": item.ref, "copy_count": prior_spells},
        importance=2,
    )


def _record_cast(
    host: CastCommitHost,
    proposal: CastProposal,
    card: Any,
    item: StackItem,
    spent: Mapping[str, int],
    activations: Sequence[Mapping[str, Any]],
    selected_option: Mapping[str, Any],
    costs: _AdditionalCostCommit,
) -> None:
    host._log(
        proposal.seat,
        "stack.cast",
        f"{proposal.seat} cast {item.ref} {item.label}.",
        {
            "stack": item.ref,
            "object": card.ref,
            "colors": [
                str(value).upper()
                for value in host._effective_card_data(card).get("colors", [])
            ],
            "from": proposal.origin,
            "requirements": thaw_json(proposal.requirements),
            "payment": {key: value for key, value in spent.items() if value},
            "mana_sources": [
                {
                    "source": activation.get("source_ref")
                    or activation.get("source"),
                    "bundle": activation.get("bundle"),
                }
                for activation in activations
            ],
            "targets": item.targets,
            "modes": item.modes,
            "x": item.x_value,
            "commander_tax": thaw_json(proposal.details).get("commander_tax", 0),
            "cost_option": proposal.cost_option_id,
            "exiled_for_cost": selected_option.get("selected_exile_card"),
            "additional_cost_objects": costs.paid_refs,
            "tap_cost_objects": list(proposal.tap_cost_refs),
        },
        importance=2,
        changed_objects=[card.object_id],
        changed_players=[proposal.seat],
    )


def _dispatch_cast_events(
    host: CastCommitHost,
    proposal: CastProposal,
    card: Any,
    item: StackItem,
    costs: _AdditionalCostCommit,
) -> None:
    trigger_batch: list[StackItem] = []
    for paid, origin, controller, logical_id, data, attachments in costs.deferred_events:
        host._dispatch_zone_change_events(
            paid,
            origin=origin,
            destination="graveyard",
            origin_controller=controller,
            origin_logical_object_id=logical_id,
            origin_data=data,
            origin_attachments=attachments,
            departure_sources=costs.source_snapshots,
            departure_source_zones=costs.source_zones,
            reason=f"{card.printed_name} additional cost",
            trigger_batch=trigger_batch,
        )
    cast_types, _, _ = host._type_parts(proposal.type_line)
    host._record_turn_history(
        "spell_cast",
        actor=proposal.seat,
        object_incarnation=card.logical_object_id,
        types=cast_types,
    )
    context = {
        "card": card.ref,
        "controller": proposal.seat,
        "player": proposal.seat,
        "from": proposal.origin,
        "to": "stack",
        "types": sorted(cast_types),
        "stack": item.ref,
    }
    host._dispatch_semantic_event("spell.cast", context, trigger_batch=trigger_batch)
    if "artifact" in cast_types:
        host._dispatch_semantic_event(
            "artifact.cast", context, trigger_batch=trigger_batch
        )
    host._enqueue_semantic_trigger_batch(trigger_batch)


def commit_cast(
    host: CastCommitHost,
    proposal: CastProposal,
    response: Mapping[str, Any],
) -> None:
    """Commit one revalidated cast proposal through authoritative owners."""

    card, record, program = _revalidate_source(host, proposal)
    details = dict(thaw_json(proposal.details))
    selected_option = dict(details["selected_cost_option"])
    requirements = dict(thaw_json(proposal.requirements))
    tap_cards = [
        host._resolve_object(
            proposal.seat,
            ref,
            zones={"battlefield"},
            controlled_only=True,
        )
        for ref in proposal.tap_cost_refs
    ]
    spent, activations = host._pay_for_cost(
        proposal.seat,
        requirements,
        response,
        exclude_sources={card.object_id for card in tap_cards},
        spend_context=host._spell_mana_spend_context(proposal.type_line),
    )
    _commit_tap_costs(host, proposal, card)
    costs = _commit_additional_costs(
        host, proposal, response, card, selected_option
    )
    item = _create_spell_item(
        host, proposal, card, record, program, selected_option, details
    )
    item.x_value = response.get("x")
    item.notes = str(response.get("note") or "")
    host.state.stack.append(item)
    _queue_storm(host, proposal, item, card, program)
    if proposal.origin == "command" and card.is_commander:
        player = host.state.players[proposal.seat]
        player.commander_casts[card.oracle_id] = (
            player.commander_casts.get(card.oracle_id, 0) + 1
        )
    _record_cast(
        host, proposal, card, item, spent, activations, selected_option, costs
    )
    _dispatch_cast_events(host, proposal, card, item, costs)
    host._queue_ward_triggers_for_targets(item)
    host.state.players[proposal.seat].yield_policy = YieldPolicy()
    if bool(details.get("during_resolution")):
        return
    if host._stabilize():
        return
    host.state.priority_player = proposal.seat
    host.state.priority_passes = []


__all__ = ["CastCommitHost", "commit_cast"]
