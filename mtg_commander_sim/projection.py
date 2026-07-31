from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .carddb import CardDatabase
from .choice_forms import build_action_form
from .model import CardInstance, Event, GameState
from .protocol import PROTOCOL_VERSION, json_patch, view_hash
from .util import stable_json, truncate


@dataclass(slots=True)
class ProjectionCursor:
    """Per-principal protocol memory.

    The cursor belongs to the delivery layer, not the rules engine. A network
    client can persist these three values as its resume token.
    """

    event_id: int = 0
    snapshot: dict[str, Any] | None = None
    seen_oracles: set[str] = field(default_factory=set)
    packet_no: int = 0
    view_hash: str | None = None


class StateProjector:
    """Build small, permission-aware LLM/client views of authoritative state."""

    def __init__(self, card_db: CardDatabase, state: GameState):
        self.card_db = card_db
        self.state = state

    @staticmethod
    def seat_for(principal: str) -> str | None:
        return principal.split(":", 1)[1] if principal.startswith("pilot:") else None

    def _view_seats_for(self, principal: str) -> set[str]:
        """Return every seat whose private information this principal may see.

        A pilot always remains the player for their authenticated seat.  If a
        current capability authorizes that pilot to make decisions for a
        controlled player, CR 723.4 additionally exposes that controlled
        player's information; it does not replace access to the controller's
        own hand or other private information (CR 723.8).
        """

        seats: set[str] = set()
        own_seat = self.seat_for(principal)
        if own_seat in self.state.players:
            seats.add(own_seat)
            seats.update(
                player_seat
                for player_seat, player in self.state.players.items()
                if player.stats.get("turn_controlled_by") == own_seat
            )
        decision = self.state.pending_decision
        if decision is not None:
            capability = next(
                (
                    value
                    for value in self.state.capabilities.values()
                    if value.decision_id == decision.decision_id
                    and value.principal == principal
                    and not value.consumed
                ),
                None,
            )
            if (
                capability is not None
                and capability.actor in self.state.players
            ):
                seats.add(capability.actor)
        return seats

    def _event_visible(self, event: Event, principal: str) -> bool:
        if principal in {"analyst", "admin"}:
            return True
        seats = self._view_seats_for(principal)
        if not event.visibility:
            return True
        return principal in event.visibility or any(
            seat in event.visibility for seat in seats
        )

    def _card_visible(self, card: CardInstance, principal: str) -> bool:
        if principal in {"analyst", "admin"}:
            return True
        if card.annotations.get("hidden_after_owner_left"):
            seats = self._view_seats_for(principal)
            return any(
                seat == card.owner
                or seat in card.known_to
                or seat in card.revealed_to
                for seat in seats
            )
        if card.zone in {
            "battlefield",
            "graveyard",
            "exile",
            "command",
            "stack",
        }:
            if not card.face_down:
                return True
            seats = self._view_seats_for(principal)
            return any(
                seat == card.owner
                or seat in card.known_to
                or seat in card.revealed_to
                for seat in seats
            )
        seats = self._view_seats_for(principal)
        return any(
            seat == card.owner
            or seat in card.known_to
            or seat in card.revealed_to
            for seat in seats
        )

    def _effective(self, card: CardInstance) -> dict[str, Any]:
        try:
            record = self.card_db.by_oracle_id(card.oracle_id)
            data: dict[str, Any] = {
                "n": record.name,
                "m": record.mana_cost,
                "mv": record.mana_value,
                "t": record.type_line,
                "o": record.oracle_text,
                "p": record.power,
                "q": record.toughness,
                "k": list(record.keywords),
            }
        except KeyError:
            token = (
                card.annotations.get("object_characteristics")
                or card.annotations.get("token_characteristics")
                or {}
            )
            data = {
                "n": card.printed_name,
                "m": token.get("mana_cost", ""),
                "mv": token.get("mana_value", 0),
                "t": token.get("type_line", "Token"),
                "o": token.get("oracle_text", ""),
                "p": token.get("power"),
                "q": token.get("toughness"),
                "k": list(token.get("keywords") or []),
            }
        overrides = card.annotations.get("copy_overrides") or {}
        if overrides:
            key_map = {
                "name": "n", "mana_cost": "m", "mana_value": "mv",
                "type_line": "t", "oracle_text": "o", "power": "p",
                "toughness": "q", "keywords": "k",
            }
            for key, value in overrides.items():
                if key in key_map:
                    data[key_map[key]] = value
        if card.temporary_keywords:
            data["k"] = sorted(set(data.get("k") or []).union(card.temporary_keywords))
        return data

    def _obj(self, card: CardInstance, principal: str) -> dict[str, Any]:
        visible = self._card_visible(card, principal)
        obj: dict[str, Any] = {"id": card.ref}
        if visible and card.object_kind == "emblem":
            obj["n"] = str(
                card.annotations.get("display_label") or "Emblem"
            )
            obj["kind"] = "emblem"
        elif visible:
            obj["cid"] = card.oracle_id[:8]
            obj["n"] = self._effective(card)["n"]
        else:
            obj["n"] = "?"
        if card.tapped:
            obj["tap"] = 1
        if card.face_down:
            obj["fd"] = 1
        if card.counters:
            obj["ctr"] = dict(card.counters)
        if card.marked_damage:
            obj["dmg"] = card.marked_damage
        if card.is_token:
            obj["tok"] = 1
        if card.is_commander:
            obj["cmd"] = 1
        if card.controller != card.owner:
            obj["ctl"] = card.controller
        if card.attached_to:
            attached = self.state.cards.get(card.attached_to)
            obj["at"] = attached.ref if attached else card.attached_to
        if card.attacking:
            obj["atk"] = card.attacking
        if card.battle_protector:
            obj["protect"] = card.battle_protector
        return obj

    def _zone(self, object_ids: Iterable[str], principal: str) -> list[dict[str, Any]]:
        return [self._obj(self.state.cards[oid], principal) for oid in object_ids]

    def _decision(self, principal: str) -> dict[str, Any] | None:
        decision = self.state.pending_decision
        if decision is None:
            return None
        capability = next(
            (
                cap for cap in self.state.capabilities.values()
                if cap.decision_id == decision.decision_id
                and cap.principal == principal
                and not cap.consumed
            ),
            None,
        )
        if capability is None:
            return None
        actor_key = capability.actor or principal
        context = copy.deepcopy(decision.payload_by_actor.get(actor_key, {}))
        raw_actions = list(
            (context.get("legal") or {}).get("actions")
            or context.get("legal_actions")
            or (
                {"id": action, "action": action}
                for action in capability.allowed_actions
            )
        )
        legal_actions: list[dict[str, Any]] = []
        for raw_action in raw_actions:
            if not isinstance(raw_action, Mapping):
                continue
            action = copy.deepcopy(dict(raw_action))
            form = build_action_form(
                action,
                decision_kind=decision.kind,
                context=context,
            )
            if form is not None:
                action["form"] = form
            legal_actions.append(action)
        return {
            "cap": capability.token,
            "id": decision.decision_id,
            "kind": decision.kind,
            "actor": capability.actor,
            "allow": list(capability.allowed_actions),
            "legal_actions": legal_actions,
            "sim": 1 if decision.simultaneous else 0,
            "ctx": context,
        }

    def _snapshot(self, principal: str) -> dict[str, Any]:
        view_seats = self._view_seats_for(principal)
        players: dict[str, Any] = {}
        for player_seat in self.state.turn_order:
            p = self.state.players[player_seat]
            summary: dict[str, Any] = {
                "life": p.life,
                "poison": p.poison,
                "energy": p.energy,
                "in": 1 if p.in_game else 0,
                "hand_n": len(p.zones["hand"]),
                "lib_n": len(p.zones["library"]),
                "mana": {k: v for k, v in p.mana_pool.items() if v},
                "lands": p.land_plays_remaining,
                "bf": self._zone(p.zones["battlefield"], principal),
                "gy": self._zone(p.zones["graveyard"], principal),
                "ex": self._zone(p.zones["exile"], principal),
                "cmd": self._zone(p.zones["command"], principal),
            }
            restricted_mana = p.stats.get("restricted_mana")
            if restricted_mana:
                summary["restricted_mana"] = restricted_mana
            if not p.in_game:
                publicly_known_left = [
                    card
                    for card in self.state.cards.values()
                    if card.owner == player_seat
                    and card.zone == "outside"
                    and self._card_visible(card, principal)
                ]
                if publicly_known_left:
                    summary["left"] = [
                        self._obj(card, principal)
                        for card in sorted(
                            publicly_known_left, key=lambda value: value.ref
                        )
                    ]
            if (
                player_seat in view_seats
                or principal in {"analyst", "admin"}
            ):
                summary["hand"] = self._zone(p.zones["hand"], principal)
                known_top = []
                if view_seats:
                    for object_id in reversed(p.zones["library"]):
                        card = self.state.cards[object_id]
                        if not any(
                            seat in card.known_to
                            or seat in card.revealed_to
                            for seat in view_seats
                        ):
                            break
                        known_top.append(card)
                if known_top:
                    summary["known_top"] = [self._obj(card, principal) for card in known_top[:5]]
            elif view_seats:
                known = [
                    self.state.cards[oid] for oid in p.zones["hand"]
                    if any(
                        seat in self.state.cards[oid].known_to
                        or seat in self.state.cards[oid].revealed_to
                        for seat in view_seats
                    )
                ]
                if known:
                    summary["known_hand"] = [self._obj(card, principal) for card in known]
            players[player_seat] = summary

        turn = {
            "seq": self.state.turn_sequence,
            "active": self.state.active_player,
            "phase": self.state.phase,
            "step": self.state.step,
            "priority": self.state.priority_player,
            "passes": list(self.state.priority_passes),
            "extra_q": [entry.player for entry in reversed(self.state.extra_turns)],
        }
        stack = [
            {
                "id": item.ref,
                "kind": item.kind,
                "ctl": item.controller,
                "label": item.label,
                **({"targets": item.targets} if item.targets else {}),
            }
            for item in reversed(self.state.stack)
        ]
        combat = {
            "atk": {
                self.state.cards[oid].ref: defender
                for oid, defender in self.state.combat.attackers.items()
                if oid in self.state.cards
            },
            "blk": {
                self.state.cards[attacker].ref: [self.state.cards[bid].ref for bid in blockers]
                for attacker, blockers in self.state.combat.blockers.items()
                if attacker in self.state.cards
            },
        }
        return {
            "rev": self.state.revision,
            "event": self.state.event_sequence,
            "game": {
                "id": self.state.game_id,
                "over": self.state.game_over,
                "winner": self.state.winner,
            },
            "turn": turn,
            "players": players,
            "stack": stack,
            "combat": combat,
        }

    def _visible_oracles(self, snapshot: Mapping[str, Any]) -> set[str]:
        found: set[str] = set()
        def walk(value: Any) -> None:
            if isinstance(value, dict):
                cid = value.get("cid")
                if cid:
                    # Resolve prefix against state because Oracle IDs are UUIDs.
                    for card in self.state.cards.values():
                        if card.oracle_id.startswith(str(cid)):
                            found.add(card.oracle_id)
                            break
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(snapshot)
        return found

    def _definition(self, oracle_id: str) -> dict[str, Any]:
        try:
            record = self.card_db.by_oracle_id(oracle_id)
            return {
                "cid": oracle_id[:8],
                "n": record.name,
                "m": record.mana_cost,
                "mv": record.mana_value,
                "t": record.type_line,
                "o": truncate(record.oracle_text.replace("\n", " / "), 520),
                **({"p": record.power, "q": record.toughness} if record.power is not None else {}),
                **({"k": list(record.keywords)} if record.keywords else {}),
            }
        except KeyError:
            return {"cid": oracle_id[:8], "n": "Custom token"}

    def _events(self, principal: str, after: int) -> list[dict[str, Any]]:
        result = []
        for event in self.state.events:
            if event.event_id <= after or not self._event_visible(event, principal):
                continue
            if event.importance <= 0 and event.code not in {"decision.response", "action.rejected"}:
                continue
            result.append({
                "id": event.event_id,
                "c": event.code,
                "a": event.actor,
                "s": event.summary,
                **({"d": event.details} if event.importance >= 3 else {}),
            })
        return result[-24:]

    def packet(
        self,
        principal: str,
        cursor: ProjectionCursor,
        *,
        force_full: bool = False,
    ) -> dict[str, Any]:
        snapshot = self._snapshot(principal)
        current_view_hash = view_hash(snapshot)
        full = force_full or cursor.snapshot is None or cursor.packet_no == 0
        if full:
            payload: dict[str, Any] = {
                "v": PROTOCOL_VERSION,
                "mode": "full",
                "principal": principal,
                "base": None,
                "view": current_view_hash,
                "state": copy.deepcopy(snapshot),
            }
        else:
            payload = {
                "v": PROTOCOL_VERSION,
                "mode": "delta",
                "principal": principal,
                "base": cursor.view_hash,
                "view": current_view_hash,
                "rev": snapshot["rev"],
                "event": snapshot["event"],
                "patch": json_patch(cursor.snapshot, snapshot),
            }

        # Decision capabilities are delivery metadata rather than persistent
        # view state. Repeat the live capability until it is consumed, and send
        # null explicitly so a client clears a stale decision after a delta.
        payload["decision"] = self._decision(principal)
        payload["view_revision"] = snapshot["rev"]

        visible = self._visible_oracles(snapshot)
        new_oracles = sorted(visible - cursor.seen_oracles)
        if new_oracles:
            payload["defs"] = [self._definition(oracle_id) for oracle_id in new_oracles]
        events = self._events(principal, cursor.event_id)
        if events:
            payload["events"] = events

        cursor.snapshot = copy.deepcopy(snapshot)
        cursor.view_hash = current_view_hash
        cursor.event_id = self.state.event_sequence
        cursor.seen_oracles.update(visible)
        cursor.packet_no += 1
        payload["pkt"] = cursor.packet_no
        return payload

    @staticmethod
    def measure(packet: Mapping[str, Any]) -> dict[str, int]:
        compact = json.dumps(packet, separators=(",", ":"), ensure_ascii=False)
        pretty = stable_json(packet)
        return {
            "compact_chars": len(compact),
            "compact_bytes": len(compact.encode("utf-8")),
            "pretty_chars": len(pretty),
            "estimated_tokens": max(1, len(compact) // 4),
        }
