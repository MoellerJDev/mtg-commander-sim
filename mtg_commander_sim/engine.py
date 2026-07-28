from __future__ import annotations

import copy
import random
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .abilities import ActivatedAbility, choose_ability, parse_activated_abilities, reduced_requirements
from .carddb import CardDatabase, CardRecord
from .deck import DeckDefinition
from .mana import ManaPlanError, ManaSource, auto_plan_payment, extract_mana_modes, parsed_cost
from .model import (
    CardInstance,
    CombatState,
    DelayedTrigger,
    Event,
    GameConfig,
    GameState,
    PlayerState,
    StackItem,
    TurnEntry,
    YieldPolicy,
)
from .permissions import AuthorizedCommand, CapabilityManager, PermissionDenied
from .semantics import SemanticProgram, SemanticRegistry
from .util import (
    mana_cost_to_vector,
    normalize_mana_bundle,
    pay_mana_from_pool,
    unique_preserving_order,
)

TURN_STEPS: list[tuple[str, str]] = [
    ("beginning", "untap"),
    ("beginning", "upkeep"),
    ("beginning", "draw"),
    ("precombat_main", "main"),
    ("combat", "beginning_combat"),
    ("combat", "declare_attackers"),
    ("combat", "declare_blockers"),
    ("combat", "combat_damage"),
    ("combat", "end_combat"),
    ("postcombat_main", "main"),
    ("ending", "end_step"),
    ("ending", "cleanup"),
]

PUBLIC_ZONES = {"battlefield", "graveyard", "exile", "command", "stack", "outside"}
HIDDEN_ZONES = {"hand", "library"}


class GameRuleError(RuntimeError):
    pass


class StateInvariantError(RuntimeError):
    pass


@dataclass(slots=True)
class ActionResult:
    ok: bool
    summary: str
    event_ids: list[int]
    state_changed: bool = True
    warnings: list[str] | None = None


class CommanderEngine:
    """Authoritative multiplayer Commander kernel.

    Pilots receive capability-scoped strategic decisions.  Card-text resolution
    is a separate arbiter role and may be cached as generic semantic programs.
    The split is deliberate: a future graphical/network client can authenticate
    seats and route the same command envelopes without granting players direct
    mutation access to game state.
    """

    def __init__(
        self,
        card_db: CardDatabase,
        state: GameState,
        semantics: SemanticRegistry | None = None,
    ):
        self.card_db = card_db
        self.state = state
        self.semantics = semantics or SemanticRegistry()
        self.permissions = CapabilityManager(self.state)
        self._assert_invariants()

    # ------------------------------------------------------------------
    # Construction, persistence, and transactions
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        card_db: CardDatabase,
        decks: Mapping[str, DeckDefinition],
        *,
        first_player: str | None = None,
        player_names: Mapping[str, str] | None = None,
        config: GameConfig | None = None,
        semantics: SemanticRegistry | None = None,
    ) -> "CommanderEngine":
        config = config or GameConfig()
        if not 2 <= len(decks) <= config.max_players:
            raise ValueError(f"CommanderEngine supports 2-{config.max_players} players")
        config.profile = config.effective_profile(len(decks))
        if config.review_profile != "commander_review":
            raise ValueError(f"Unsupported review profile {config.review_profile!r}")
        if config.profile not in {"commander_duel", "commander_multiplayer"}:
            raise ValueError(f"Unsupported Commander format profile {config.profile!r}")
        if config.trace_level not in {"minimal", "standard", "debug"}:
            raise ValueError(f"Unsupported trace level {config.trace_level!r}")
        turn_order = list(decks)
        first_player = first_player or turn_order[0]
        if first_player not in decks:
            raise ValueError("first_player must name one of the supplied seats")
        while turn_order[0] != first_player:
            turn_order.append(turn_order.pop(0))
        names = dict(player_names or {})
        all_seats = list(turn_order)
        players = {
            seat: PlayerState(
                seat=seat,
                name=names.get(seat, seat),
                life=config.starting_life,
            )
            for seat in all_seats
        }
        cards: dict[str, CardInstance] = {}
        commander_ids: dict[str, list[str]] = {seat: [] for seat in all_seats}
        deck_names = {seat: decks[seat].name for seat in all_seats}
        ref_counters: dict[str, int] = {}

        for seat in all_seats:
            deck = decks[seat]
            commander_names = list(deck.commanders) or [
                entry.name for entry in deck.entries if entry.board == "commander"
            ]
            commander_remaining: dict[str, int] = {}
            for commander in commander_names:
                canonical = card_db.lookup(commander).name
                commander_remaining[canonical] = commander_remaining.get(canonical, 0) + 1
            serial = 0
            for entry in deck.entries:
                if entry.board not in {"mainboard", "commander"}:
                    continue
                for _ in range(entry.quantity):
                    serial += 1
                    record = card_db.lookup(entry.name)
                    is_commander = entry.board == "commander"
                    if not is_commander and commander_remaining.get(record.name, 0) > 0:
                        is_commander = True
                    if is_commander and commander_remaining.get(record.name, 0) > 0:
                        commander_remaining[record.name] -= 1
                    object_id = uuid.uuid4().hex
                    ref = f"{seat}{serial:02d}"
                    zone = "command" if is_commander else "library"
                    card = CardInstance(
                        object_id=object_id,
                        ref=ref,
                        oracle_id=record.oracle_id,
                        printed_name=record.name,
                        owner=seat,
                        controller=seat,
                        zone=zone,
                        is_commander=is_commander,
                        known_to=(
                            []
                            if zone == "library"
                            else [seat]
                            if zone in HIDDEN_ZONES
                            else list(all_seats)
                        ),
                        revealed_to=list(all_seats) if zone in PUBLIC_ZONES else [],
                    )
                    cards[object_id] = card
                    players[seat].zones[zone].append(object_id)
                    if is_commander:
                        commander_ids[seat].append(record.oracle_id)
            randomizer = random.Random(f"{config.seed}|{seat}|initial")
            randomizer.shuffle(players[seat].zones["library"])

        state = GameState(
            game_id=uuid.uuid4().hex,
            config=config,
            players=players,
            cards=cards,
            deck_names=deck_names,
            commander_oracle_ids=commander_ids,
            turn_order=turn_order,
            current_turn=None,
            last_normal_turn_player=None,
            active_player=None,
            phase="setup",
            step="mulligan",
            ref_counters=ref_counters,
        )
        engine = cls(card_db, state, semantics)
        engine._log(
            None,
            "game.created",
            f"Created {len(turn_order)}-player Commander game; {first_player} starts.",
            {"decks": deck_names, "turn_order": turn_order, "seed": config.seed},
            importance=3,
        )
        for seat in turn_order:
            engine.draw(seat, config.opening_hand_size, reason="opening hand", private=True)
        engine._issue_mulligan_declaration()
        return engine

    @classmethod
    def load(
        cls,
        card_db: CardDatabase,
        path: str,
        semantics: SemanticRegistry | None = None,
    ) -> "CommanderEngine":
        return cls(card_db, GameState.load(path), semantics)

    def save(self, path: str) -> None:
        self.state.save(path)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        snapshot = copy.deepcopy(self.state)
        try:
            yield
            self._assert_invariants()
        except Exception:
            self.state = snapshot
            self.permissions = CapabilityManager(self.state)
            raise

    # ------------------------------------------------------------------
    # Basic state helpers
    # ------------------------------------------------------------------
    @property
    def seats(self) -> tuple[str, ...]:
        return tuple(self.state.turn_order)

    @property
    def active_seats(self) -> list[str]:
        return self.state.active_seats()

    def _all_visibility(self) -> list[str]:
        return [*self.seats, "arbiter", "analyst", "spectator"]

    def _require_seat(self, seat: str, *, in_game: bool = False) -> None:
        if seat not in self.state.players:
            raise GameRuleError(f"Unknown seat {seat!r}")
        if in_game and not self.state.players[seat].in_game:
            raise GameRuleError(f"{seat} is no longer in the game")

    def _next_ref(self, prefix: str) -> str:
        self.state.ref_counters[prefix] = self.state.ref_counters.get(prefix, 0) + 1
        return f"{prefix}{self.state.ref_counters[prefix]}"

    def _stable_runtime_id(self, kind: str, ref: str) -> str:
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"mtg-commander-sim:{self.state.game_id}:{kind}:{ref}",
        ).hex

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
    ) -> Event:
        self.state.event_sequence += 1
        event = Event(
            event_id=self.state.event_sequence,
            revision=self.state.revision,
            turn_sequence=self.state.turn_sequence,
            active_player=self.state.active_player,
            phase=self.state.phase,
            step=self.state.step,
            actor=actor,
            code=code,
            summary=summary,
            details=dict(details or {}),
            visibility=list(visibility or self._all_visibility()),
            importance=importance,
            changed_objects=list(changed_objects),
            changed_players=list(changed_players),
        )
        self.state.events.append(event)
        return event

    def _assert_invariants(self) -> None:
        membership: dict[str, list[tuple[str, str]]] = {}
        for seat, player in self.state.players.items():
            for zone, ids in player.zones.items():
                if len(ids) != len(set(ids)):
                    raise StateInvariantError(f"Duplicate object in {seat}/{zone}")
                for object_id in ids:
                    if object_id not in self.state.cards:
                        raise StateInvariantError(f"Unknown object {object_id} in {seat}/{zone}")
                    membership.setdefault(object_id, []).append((seat, zone))
        stack_cards = {item.card_object_id for item in self.state.stack if item.card_object_id}
        for object_id, card in self.state.cards.items():
            locations = membership.get(object_id, [])
            if card.zone == "stack":
                if object_id not in stack_cards or locations:
                    raise StateInvariantError(f"Invalid stack membership for {card.ref}")
            elif card.zone == "outside":
                if locations:
                    raise StateInvariantError(f"Outside-game object {card.ref} still appears in a zone")
            elif len(locations) != 1:
                raise StateInvariantError(f"{card.ref} appears in {locations}, expected exactly one zone")
            elif locations[0][1] != card.zone:
                raise StateInvariantError(f"{card.ref} zone mismatch {card.zone}/{locations[0]}")
        if self.state.priority_player is not None and self.state.priority_player not in self.active_seats:
            raise StateInvariantError("Priority belongs to a player who is not in the game")
        for player in self.state.players.values():
            if any(value < 0 for value in player.mana_pool.values()):
                raise StateInvariantError(f"Negative mana in {player.seat}'s pool")

    def card_record(self, value: str | CardInstance) -> CardRecord | None:
        card = value if isinstance(value, CardInstance) else self.state.cards[value]
        if card.oracle_id.startswith("custom-token:"):
            return None
        return self.card_db.by_oracle_id(card.oracle_id)

    def _effective_card_data(self, value: str | CardInstance) -> dict[str, Any]:
        card = value if isinstance(value, CardInstance) else self.state.cards[value]
        record = self.card_record(card)
        if record is None:
            base = {
                "name": card.printed_name,
                "mana_cost": "",
                "mana_value": 0,
                "type_line": str(card.annotations.get("token_characteristics", {}).get("type_line", "Token")),
                "oracle_text": "",
                "power": card.annotations.get("token_characteristics", {}).get("power"),
                "toughness": card.annotations.get("token_characteristics", {}).get("toughness"),
                "keywords": [],
                "produced_mana": [],
            }
        else:
            face = None
            if card.active_face:
                face = next(
                    (f for f in record.faces if str(f.get("name") or "") == card.active_face),
                    None,
                )
            base = {
                "name": str(face.get("name")) if face else record.name,
                "mana_cost": str(face.get("mana_cost") or "") if face else record.mana_cost,
                "mana_value": record.mana_value,
                "type_line": str(face.get("type_line") or "") if face else record.type_line,
                "oracle_text": str(face.get("oracle_text") or "") if face else record.oracle_text,
                "power": face.get("power") if face else record.power,
                "toughness": face.get("toughness") if face else record.toughness,
                "loyalty": face.get("loyalty") if face else record.loyalty,
                "keywords": list(record.keywords),
                "produced_mana": list(record.produced_mana),
            }
        overrides = dict(card.annotations.get("copy_overrides") or {})
        base.update({key: copy.deepcopy(value) for key, value in overrides.items() if key in base or key in {"name", "type_line", "power", "toughness", "oracle_text", "mana_value", "mana_cost"}})
        base["keywords"] = unique_preserving_order(
            list(base.get("keywords") or [])
            + list(overrides.get("keywords") or [])
            + list(card.temporary_keywords)
        )
        return base

    def display_name(self, object_id: str) -> str:
        return str(self._effective_card_data(object_id).get("name") or self.state.cards[object_id].printed_name)

    def _resolve_object(
        self,
        seat: str,
        value: str,
        *,
        zones: Iterable[str] | None = None,
        controlled_only: bool = False,
        owned_only: bool = False,
    ) -> CardInstance:
        self._require_seat(seat)
        zone_filter = set(zones) if zones is not None else None
        if value in self.state.cards:
            card = self.state.cards[value]
            candidates = [card]
        else:
            normalized = value.casefold().strip()
            candidates = [
                card
                for card in self.state.cards.values()
                if card.ref.casefold() == normalized
                or card.printed_name.casefold() == normalized
                or self.display_name(card.object_id).casefold() == normalized
            ]
        filtered: list[CardInstance] = []
        for card in candidates:
            if card.zone == "outside":
                continue
            if zone_filter is not None and card.zone not in zone_filter:
                continue
            if controlled_only and card.controller != seat:
                continue
            if owned_only and card.owner != seat:
                continue
            filtered.append(card)
        if not filtered:
            raise GameRuleError(f"Could not find {value!r} for {seat} in requested zones")
        if len(filtered) > 1:
            options = ", ".join(f"{card.ref}:{card.zone}" for card in filtered)
            raise GameRuleError(f"Ambiguous object {value!r}; use a ref: {options}")
        return filtered[0]

    def _next_active_after(self, seat: str) -> str:
        active = self.active_seats
        if not active:
            raise GameRuleError("No active players remain")
        if seat not in self.state.turn_order:
            return active[0]
        index = self.state.turn_order.index(seat)
        for offset in range(1, len(self.state.turn_order) + 1):
            candidate = self.state.turn_order[(index + offset) % len(self.state.turn_order)]
            if self.state.players[candidate].in_game:
                return candidate
        return active[0]

    def apnap_order(self) -> list[str]:
        if not self.active_seats:
            return []
        start = self.state.active_player if self.state.active_player in self.active_seats else self.active_seats[0]
        result = [start]
        while len(result) < len(self.active_seats):
            nxt = self._next_active_after(result[-1])
            if nxt in result:
                break
            result.append(nxt)
        return result

    # ------------------------------------------------------------------
    # Zone movement, draw, and knowledge
    # ------------------------------------------------------------------
    def _remove_from_zone(self, card: CardInstance) -> None:
        if card.zone == "stack":
            return
        for player in self.state.players.values():
            ids = player.zones.get(card.zone)
            if ids is not None and card.object_id in ids:
                ids.remove(card.object_id)
                return
        if card.zone != "outside":
            raise StateInvariantError(f"Could not remove {card.ref} from {card.zone}")

    def _reset_zone_change(self, card: CardInstance, destination: str) -> None:
        if card.attached_to and card.attached_to in self.state.cards:
            target = self.state.cards[card.attached_to]
            if card.object_id in target.attachments:
                target.attachments.remove(card.object_id)
        for attachment_id in list(card.attachments):
            if attachment_id in self.state.cards:
                self.state.cards[attachment_id].attached_to = None
        card.tapped = False
        card.marked_damage = 0
        card.deathtouch_damage = False
        card.temporary_keywords.clear()
        card.attacking = None
        card.blocking = None
        card.attached_to = None
        card.attachments.clear()
        card.phased_out = False
        if destination != "battlefield":
            card.controller = card.owner
            card.counters.clear()
            if destination != "stack":
                card.active_face = None

    def move_card(
        self,
        object_id: str,
        destination: str,
        *,
        controller: str | None = None,
        tapped: bool = False,
        position: str = "top",
        reveal_to: Iterable[str] | None = None,
        reason: str = "",
        log: bool = True,
    ) -> CardInstance:
        if destination not in {"library", "hand", "battlefield", "graveyard", "exile", "command", "outside"}:
            raise GameRuleError(f"Unsupported destination {destination}")
        card = self.state.cards[object_id]
        origin = card.zone
        if origin != "stack":
            self._remove_from_zone(card)
        self._reset_zone_change(card, destination)
        card.zone = destination
        if destination == "battlefield":
            card.controller = controller or card.owner
            self._require_seat(card.controller)
            card.tapped = tapped
            card.acquired_control_turn_count = self.state.players[card.controller].turns_begun
            card.entered_battlefield_turn_sequence = self.state.turn_sequence
            self.state.players[card.controller].zones["battlefield"].append(object_id)
            card.known_to = list(self.seats)
            card.revealed_to = list(self.seats)
        elif destination == "outside":
            card.known_to = list(self.seats)
            card.revealed_to = list(self.seats)
        else:
            owner_zone = self.state.players[card.owner].zones[destination]
            if destination == "library":
                if position == "bottom":
                    owner_zone.insert(0, object_id)
                else:
                    owner_zone.append(object_id)
                card.known_to = [card.owner]
                card.revealed_to = []
            else:
                owner_zone.append(object_id)
                if destination in PUBLIC_ZONES:
                    card.known_to = list(self.seats)
                    card.revealed_to = list(self.seats)
                else:
                    known = {card.owner, *(reveal_to or [])}
                    card.known_to = sorted(known)
                    card.revealed_to = sorted(set(reveal_to or []))
        if card.is_token and destination not in {"battlefield", "stack"}:
            if card.object_id in self.state.players[card.owner].zones.get(destination, []):
                self.state.players[card.owner].zones[destination].remove(card.object_id)
            card.zone = "outside"
        if log:
            self._log(
                None,
                "zone.move",
                f"{card.ref} {card.printed_name}: {origin} → {card.zone}.",
                {"object": card.ref, "from": origin, "to": card.zone, "reason": reason, "tapped": card.tapped},
                changed_objects=[object_id],
                changed_players=[card.owner, card.controller],
            )
        return card

    def shuffle_library(self, seat: str, *, reason: str = "shuffle") -> None:
        self._require_seat(seat)
        player = self.state.players[seat]
        count = int(player.stats.get("shuffle_count", 0)) + 1
        player.stats["shuffle_count"] = count
        randomizer = random.Random(f"{self.state.config.seed}|{seat}|shuffle|{count}")
        randomizer.shuffle(player.zones["library"])
        for object_id in player.zones["library"]:
            card = self.state.cards[object_id]
            card.known_to = []
            card.revealed_to = []
        self._log(seat, "library.shuffle", f"{seat} shuffled.", {"reason": reason, "count": count}, importance=0, changed_players=[seat])

    def draw(self, seat: str, count: int = 1, *, reason: str = "draw", private: bool = False) -> list[str]:
        self._require_seat(seat)
        player = self.state.players[seat]
        drawn: list[str] = []
        for _ in range(count):
            if not player.zones["library"]:
                player.attempted_empty_draw = True
                break
            object_id = player.zones["library"].pop()
            card = self.state.cards[object_id]
            card.zone = "hand"
            card.controller = card.owner
            card.known_to = [seat]
            card.revealed_to = []
            player.zones["hand"].append(object_id)
            player.draw_history.append(
                {"turn_sequence": self.state.turn_sequence, "card": card.printed_name, "object": card.ref, "reason": reason}
            )
            drawn.append(object_id)
        if drawn:
            self._log(
                seat,
                "card.draw",
                f"{seat} drew {len(drawn)} card(s).",
                {"count": len(drawn), "reason": reason},
                changed_players=[seat],
            )
            self._log(
                seat,
                "card.draw.private",
                f"{seat} drew {', '.join(self.state.cards[oid].printed_name for oid in drawn)}.",
                {"objects": [self.state.cards[oid].ref for oid in drawn], "cards": [self.state.cards[oid].printed_name for oid in drawn], "reason": reason},
                visibility=[seat, "analyst"],
                importance=0 if private else 1,
                changed_objects=drawn,
                changed_players=[seat],
            )
        return drawn

    # ------------------------------------------------------------------
    # Capability-scoped command entry point
    # ------------------------------------------------------------------
    def submit(
        self,
        *,
        token: str,
        principal: str,
        action: str,
        payload: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        payload_dict = dict(payload or {})
        start_event = self.state.event_sequence
        with self.transaction():
            authorized = self.permissions.authorize(
                token=token,
                principal=principal,
                action=action,
                payload=payload_dict,
            )
            self.state.revision += 1
            self.permissions.record_response(authorized)
            actor = authorized.capability.actor
            self._log(
                actor,
                "decision.response",
                f"{principal} submitted {action} for {authorized.decision.kind}.",
                {"decision": authorized.decision.decision_id, "action": action},
                visibility=[actor, "analyst"] if actor else [principal, "analyst"],
                importance=0,
                changed_players=[actor] if actor else [],
            )
            if self.permissions.decision_complete():
                decision = self.permissions.close_decision()
                self._dispatch_completed_decision(decision)
            self.pump()
        return ActionResult(
            True,
            f"Accepted {action}",
            list(range(start_event + 1, self.state.event_sequence + 1)),
        )

    def try_submit(self, **kwargs: Any) -> ActionResult:
        try:
            return self.submit(**kwargs)
        except (GameRuleError, PermissionDenied, ValueError, ManaPlanError) as exc:
            return ActionResult(False, str(exc), [], state_changed=False, warnings=["State was rolled back."])

    def _dispatch_completed_decision(self, decision: Any) -> None:
        kind = decision.kind
        if kind == "mulligan.declare":
            self._complete_mulligan_declaration(decision)
        elif kind == "mulligan.bottom":
            self._complete_mulligan_bottom(decision)
        elif kind == "priority":
            self._complete_priority(decision)
        elif kind == "combat.attackers":
            self._complete_attackers(decision)
        elif kind == "combat.blockers":
            self._complete_blockers(decision)
        elif kind == "combat.damage":
            self._complete_combat_damage(decision)
        elif kind == "cleanup.discard":
            self._complete_cleanup_discard(decision)
        elif kind == "state.legend":
            self._complete_legend_choice(decision)
        elif kind == "choice.apnap":
            self._complete_apnap_choice(decision)
        elif kind == "trigger.order":
            self._complete_trigger_order(decision)
        elif kind == "arbiter.resolve":
            self._complete_arbiter_resolution(decision)
        elif kind == "search.fetch":
            self._complete_fetch_choice(decision)
        else:
            raise GameRuleError(f"Unsupported completed decision {kind}")

    # ------------------------------------------------------------------
    # Multiplayer London mulligan
    # ------------------------------------------------------------------
    def _opening_hand_signals(self, seat: str) -> dict[str, Any]:
        player = self.state.players[seat]
        lands = 0
        early_mana = 0
        colored_sources: set[str] = set()
        early_actions = 0
        for object_id in player.zones["hand"]:
            record = self.card_record(object_id)
            if not record:
                continue
            if record.is_land:
                lands += 1
                for mode in extract_mana_modes(record, self._commander_identity(seat)):
                    if not mode.conditional:
                        colored_sources.update(color for color, amount in mode.bundle.items() if amount and color in "WUBRG")
            elif record.mana_value <= 2:
                early_actions += 1
                oracle = record.oracle_text.casefold()
                if "add " in oracle or "search your library for a basic land" in oracle or "search your library for a forest" in oracle:
                    early_mana += 1
        commander_colors = sorted(self._commander_identity(seat))
        red_flags: list[str] = []
        if lands == 0:
            red_flags.append("no lands")
        elif lands == 1 and early_mana == 0:
            red_flags.append("one land and no cheap acceleration")
        if lands >= 6:
            red_flags.append("six or more lands")
        missing = [color for color in commander_colors if color not in colored_sources]
        if missing and lands <= 2 and early_mana == 0:
            red_flags.append("thin early color access: " + "".join(missing))
        functional = not red_flags and (2 <= lands <= 5 or (lands == 1 and early_mana >= 1))
        return {
            "lands": lands,
            "cheap_mana": early_mana,
            "other_early_actions": early_actions,
            "visible_source_colors": sorted(colored_sources),
            "commander_colors": commander_colors,
            "red_flags": red_flags,
            "functional_baseline": functional,
        }

    def _mulligan_hand_payload(self, seat: str) -> dict[str, Any]:
        player = self.state.players[seat]
        free = self.state.config.effective_free_mulligans(len(self.seats))
        next_mulligans = player.mulligans_taken + 1
        next_penalty = max(0, next_mulligans - free)
        after_free = player.mulligans_taken >= free
        return {
            "hand": [
                {"id": self.state.cards[oid].ref, "name": self.state.cards[oid].printed_name}
                for oid in player.zones["hand"]
            ],
            "hand_size": len(player.zones["hand"]),
            "mulligans_taken": player.mulligans_taken,
            "free_mulligans": free,
            "signals": self._opening_hand_signals(seat),
            "if_mulligan": {
                "draw": self.state.config.opening_hand_size,
                "bottom": next_penalty,
                "resulting_hand_size": self.state.config.opening_hand_size - next_penalty,
            },
            "decision_policy": (
                "KEEP any functional hand after the free redraw. Do not chase an ideal seven: "
                "rejecting this hand means selecting the next opener from seven and immediately "
                f"bottoming {next_penalty}, for a {self.state.config.opening_hand_size - next_penalty}-card keep."
                if after_free
                else "This is the multiplayer free-mulligan decision. Mulligan only for a materially better chance at a functional opener, not a perfect one."
            ),
        }

    def _issue_mulligan_declaration(
        self,
        *,
        actors: Sequence[str] | None = None,
        index: int = 0,
        mulliganers: Sequence[str] = (),
        round_no: int | None = None,
    ) -> None:
        """Issue the next declaration in turn order for one mulligan round.

        Rule 103.5 has players declare in turn order. Only after every eligible
        player has declared do all mulliganers redraw at the same time. Keeping
        is final, so later rounds contain only players who mulliganed.
        """

        if actors is None:
            actors = [seat for seat in self.state.turn_order if not self.state.players[seat].kept_hand]
            if not actors:
                self._start_game()
                return
            self.state.mulligan_round += 1
            round_no = self.state.mulligan_round
            self._log(
                None,
                "mulligan.round",
                f"Mulligan round {round_no} declarations opened in turn order.",
                {"actors": list(actors)},
                importance=1,
            )
        actor_list = list(actors)
        if round_no is None:
            round_no = self.state.mulligan_round
        if index >= len(actor_list):
            self._perform_mulligan_redraws(list(mulliganers))
            return

        seat = actor_list[index]
        self.permissions.issue(
            kind="mulligan.declare",
            role="pilot",
            actors=[seat],
            allowed_actions=["keep", "mulligan"],
            payload_by_actor={seat: self._mulligan_hand_payload(seat)},
            simultaneous=False,
            continuation={
                "round": round_no,
                "actors": actor_list,
                "index": index,
                "mulliganers": list(mulliganers),
            },
        )

    def _complete_mulligan_declaration(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        action = response["action"]
        player = self.state.players[seat]
        mulliganers = list(decision.continuation.get("mulliganers") or [])

        if action == "keep":
            player.kept_hand = True
            player.mulligan_status = "kept"
            self._log(
                seat,
                "mulligan.keep",
                f"{seat} kept {len(player.zones['hand'])} cards after {player.mulligans_taken} mulligan(s).",
                {"hand_size": len(player.zones["hand"]), "mulligans": player.mulligans_taken},
                importance=2,
                changed_players=[seat],
            )
            self._log(
                seat,
                "mulligan.keep.private",
                f"{seat} kept: {', '.join(self.state.cards[oid].printed_name for oid in player.zones['hand'])}.",
                {"objects": [self.state.cards[oid].ref for oid in player.zones["hand"]]},
                visibility=[seat, "analyst"],
                importance=1,
            )
        elif action == "mulligan":
            free = self.state.config.effective_free_mulligans(len(self.seats))
            signals = self._opening_hand_signals(seat)
            if (
                self.state.config.realistic_mulligan_guard
                and player.mulligans_taken >= free
                and signals.get("functional_baseline")
                and not str(response.get("override_reason") or "").strip()
            ):
                raise GameRuleError(
                    f"{seat}'s post-free hand meets the functional baseline. "
                    "Keep it, or resubmit mulligan with override_reason explaining why a six-card hand is preferable."
                )
            mulliganers.append(seat)
            self._log(
                seat,
                "mulligan.declare",
                f"{seat} declared a mulligan in round {decision.continuation.get('round')}.",
                {"round": decision.continuation.get("round")},
                importance=1,
            )
        else:
            raise GameRuleError(f"Invalid mulligan declaration {action}")

        actors = list(decision.continuation.get("actors") or [seat])
        next_index = int(decision.continuation.get("index", 0)) + 1
        self._issue_mulligan_declaration(
            actors=actors,
            index=next_index,
            mulliganers=mulliganers,
            round_no=int(decision.continuation.get("round") or self.state.mulligan_round),
        )

    def _perform_mulligan_redraws(self, mulliganers: list[str]) -> None:
        """Apply every declared mulligan before asking for private bottom choices."""

        free = self.state.config.effective_free_mulligans(len(self.seats))
        bottomers: list[str] = []
        for seat in mulliganers:
            player = self.state.players[seat]
            for object_id in list(player.zones["hand"]):
                self.move_card(object_id, "library", log=False)
            self.shuffle_library(seat, reason="mulligan")
            player.mulligans_taken += 1
            player.mulligan_penalty = max(0, player.mulligans_taken - free)
            self.draw(seat, self.state.config.opening_hand_size, reason="mulligan", private=True)
            player.mulligan_status = "bottoming" if player.mulligan_penalty else "pending"
            self._log(
                seat,
                "mulligan.redraw",
                f"{seat} redrew seven; penalty is {player.mulligan_penalty} bottom card(s).",
                {"mulligans": player.mulligans_taken, "bottom": player.mulligan_penalty},
                importance=2,
                changed_players=[seat],
            )
            if player.mulligan_penalty:
                bottomers.append(seat)

        if bottomers:
            self.permissions.issue(
                kind="mulligan.bottom",
                role="pilot",
                actors=bottomers,
                allowed_actions=["bottom"],
                payload_by_actor={
                    seat: {
                        "count": self.state.players[seat].mulligan_penalty,
                        "hand": [
                            {"id": self.state.cards[oid].ref, "name": self.state.cards[oid].printed_name}
                            for oid in self.state.players[seat].zones["hand"]
                        ],
                    }
                    for seat in bottomers
                },
                simultaneous=True,
            )
            return
        if all(player.kept_hand for player in self.state.players.values()):
            self._start_game()
        else:
            self._issue_mulligan_declaration()

    def _complete_mulligan_bottom(self, decision: Any) -> None:
        for seat in decision.actors:
            player = self.state.players[seat]
            response = decision.responses[seat]
            values = list(response.get("cards") or response.get("bottom") or [])
            required = player.mulligan_penalty
            if len(values) != required:
                raise GameRuleError(f"{seat} must bottom exactly {required} card(s)")
            resolved: list[str] = []
            for value in values:
                card = self._resolve_object(seat, str(value), zones={"hand"}, owned_only=True)
                if card.object_id in resolved:
                    raise GameRuleError("The same card cannot be bottomed twice")
                resolved.append(card.object_id)
            for object_id in resolved:
                self.move_card(object_id, "library", position="bottom", log=False)
            player.mulligan_status = "pending"
            self._log(
                seat,
                "mulligan.bottom",
                f"{seat} bottomed {required} card(s); current hand size {len(player.zones['hand'])}.",
                {"count": required},
                importance=2,
                changed_objects=resolved,
                changed_players=[seat],
            )
        self._issue_mulligan_declaration()

    # ------------------------------------------------------------------
    # Turn scheduler, delayed triggers, and priority
    # ------------------------------------------------------------------
    def _start_game(self) -> None:
        self.state.started = True
        first = self.state.turn_order[0]
        entry = TurnEntry(turn_id=self._next_ref("N"), player=first, extra=False, created_sequence=self.state.turn_sequence)
        self._log(None, "game.start", f"The game began; {first} takes the first turn.", importance=3)
        self._begin_turn(entry)

    def schedule_extra_turn(self, seat: str, *, source: str | None = None) -> TurnEntry:
        self._require_seat(seat, in_game=True)
        entry = TurnEntry(
            turn_id=self._next_ref("X"),
            player=seat,
            extra=True,
            source=source,
            created_sequence=self.state.turn_sequence,
        )
        # Most recently created extra turn is taken first.
        self.state.extra_turns.insert(0, entry)
        self._log(seat, "turn.extra.scheduled", f"{seat} received an extra turn after this one.", {"turn": entry.turn_id, "source": source}, importance=2, changed_players=[seat])
        return entry

    def _next_normal_player(self) -> str:
        anchor = self.state.last_normal_turn_player or self.state.turn_order[0]
        return self._next_active_after(anchor)

    def _select_next_turn(self) -> TurnEntry:
        while self.state.extra_turns:
            entry = self.state.extra_turns.pop(0)
            if self.state.players[entry.player].in_game:
                return entry
        seat = self._next_normal_player()
        return TurnEntry(turn_id=self._next_ref("N"), player=seat, extra=False, created_sequence=self.state.turn_sequence)

    def _begin_turn(self, entry: TurnEntry) -> None:
        if not self.state.players[entry.player].in_game:
            self._begin_turn(self._select_next_turn())
            return
        self.state.current_turn = entry
        self.state.active_player = entry.player
        if not entry.extra:
            self.state.last_normal_turn_player = entry.player
        self.state.turn_sequence += 1
        player = self.state.players[entry.player]
        player.turns_begun += 1
        player.land_plays_remaining = 1
        player.yield_policy = YieldPolicy()
        self.state.combat = CombatState()
        self.state.phase_index = 0
        self.state.priority_player = None
        self.state.priority_passes = []
        self._log(
            entry.player,
            "turn.begin",
            f"Turn {self.state.turn_sequence} began for {entry.player}{' (extra)' if entry.extra else ''}.",
            {"turn_id": entry.turn_id, "extra": entry.extra, "source": entry.source},
            importance=2,
            changed_players=[entry.player],
        )
        self._enter_step()

    def _clear_mana(self, *, reason: str) -> None:
        for seat, player in self.state.players.items():
            if any(player.mana_pool.values()):
                lost = dict(player.mana_pool)
                player.mana_pool = normalize_mana_bundle(None)
                self._log(seat, "mana.empty", f"{seat}'s mana pool emptied.", {"lost": lost, "reason": reason}, importance=0, changed_players=[seat])

    def _enter_step(self) -> None:
        phase, step = TURN_STEPS[self.state.phase_index]
        self.state.phase = phase
        self.state.step = step
        self.state.priority_player = None
        self.state.priority_passes = []
        self._log(None, "step.begin", f"{self.state.turn_sequence}:{phase}/{step}.", importance=0)
        active = self.state.active_player
        if active is None:
            raise StateInvariantError("A turn has no active player")

        if step == "untap":
            if self.state.config.auto_untap:
                changed: list[str] = []
                for object_id in list(self.state.players[active].zones["battlefield"]):
                    card = self.state.cards[object_id]
                    if card.controller != active or card.phased_out:
                        continue
                    if card.annotations.pop("does_not_untap_next", False):
                        continue
                    if card.tapped:
                        card.tapped = False
                        changed.append(object_id)
                if changed:
                    self._log(active, "permanent.untap", f"{active} untapped {len(changed)} permanent(s).", {"objects": [self.state.cards[oid].ref for oid in changed]}, importance=0, changed_objects=changed, changed_players=[active])
            self._advance_step()
            return

        delayed = self._matching_delayed_triggers("step.begin", {"phase": phase, "step": step, "player": active})
        if delayed:
            self._start_trigger_batch(delayed, after="grant_priority")
            return

        if step == "draw":
            first_turn = self.state.turn_sequence == 1
            should_draw = not first_turn or self.state.config.effective_first_player_draws(len(self.seats))
            if self.state.config.auto_draw and should_draw:
                self.draw(active, 1, reason="turn-based draw")
            elif not should_draw:
                self._log(active, "draw.skip", f"{active} skipped the first-turn draw.", importance=0)
            self._grant_priority(active)
            return

        if step == "declare_attackers":
            self._issue_attackers()
            return
        if step == "declare_blockers":
            self._begin_blocker_decisions()
            return
        if step == "combat_damage":
            self._begin_combat_damage()
            return
        if step == "cleanup":
            hand = self.state.players[active].zones["hand"]
            excess = len(hand) - self.state.players[active].max_hand_size
            if excess > 0:
                self.permissions.issue(
                    kind="cleanup.discard",
                    role="pilot",
                    actors=[active],
                    allowed_actions=["discard"],
                    payload_by_actor={
                        active: {
                            "count": excess,
                            "hand": [{"id": self.state.cards[oid].ref, "name": self.state.cards[oid].printed_name} for oid in hand],
                        }
                    },
                )
                return
            self._finish_cleanup()
            return
        self._grant_priority(active)

    def _advance_step(self) -> None:
        self._clear_mana(reason="step or phase ended")
        self.state.phase_index += 1
        if self.state.phase_index >= len(TURN_STEPS):
            self._finish_cleanup()
            return
        self._enter_step()

    def _finish_cleanup(self) -> None:
        active = self.state.active_player
        for card in self.state.cards.values():
            card.marked_damage = 0
            card.deathtouch_damage = False
            card.temporary_keywords.clear()
            card.attacking = None
            card.blocking = None
            card.annotations.pop("until_end_of_turn", None)
        self._clear_mana(reason="cleanup")
        self._log(active, "turn.cleanup", f"{active} completed cleanup.", importance=0)
        if self.state.game_over:
            return
        self._begin_turn(self._select_next_turn())

    def _grant_priority(self, seat: str | None) -> None:
        if self._stabilize():
            return
        if not self.active_seats:
            return
        if seat not in self.active_seats:
            seat = self._next_active_after(seat or self.state.active_player or self.active_seats[0])
        self.state.priority_player = seat
        self.state.priority_passes = []
        self.state.priority_epoch += 1

    def _issue_priority(self, seat: str) -> None:
        payload = {
            "stack": [{"id": item.ref, "label": item.label, "controller": item.controller} for item in reversed(self.state.stack)],
            "legal": self._priority_action_hints(seat),
            "yield_modes": ["none", "until_public_change", "until_my_turn", "auto_if_no_response"],
        }
        self.permissions.issue(
            kind="priority",
            role="pilot",
            actors=[seat],
            allowed_actions=["pass", "play_land", "cast", "activate", "concede"],
            payload_by_actor={seat: payload},
        )

    def _complete_priority(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        action = response.pop("action")
        if action == "pass":
            self._set_yield(seat, response.get("yield"))
            self._pass_priority(seat)
        elif action == "play_land":
            self._play_land(seat, response)
        elif action == "cast":
            self._cast(seat, response)
        elif action == "activate":
            self._activate(seat, response)
        elif action == "concede":
            self._eliminate_players([seat], reason="conceded")
        else:
            raise GameRuleError(f"Unsupported priority action {action}")

    def _set_yield(self, seat: str, value: Any) -> None:
        mode = str(value or "none")
        if mode == "none":
            self.state.players[seat].yield_policy = YieldPolicy()
            return
        if mode not in {"until_public_change", "until_my_turn", "auto_if_no_response"}:
            raise GameRuleError(f"Unknown yield mode {mode}")
        self.state.players[seat].yield_policy = YieldPolicy(
            mode=mode,
            created_revision=self.state.revision,
            expires_turn_sequence=(self.state.turn_sequence + 1 if mode == "until_my_turn" else None),
            note="Pilot-issued priority yield",
        )

    def _yield_stopped(self, seat: str) -> bool:
        policy = self.state.players[seat].yield_policy
        if policy.mode == "none":
            return True
        if policy.mode == "until_my_turn" and self.state.active_player == seat:
            return True
        relevant_codes = {
            "stack.cast",
            "stack.activate",
            "stack.trigger",
            "stack.resolve",
            "stack.counter",
            "zone.move",
            "card.draw.private",
            "token.create",
            "control.change",
            "player.eliminated",
        }
        for event in self.state.events:
            if event.revision <= policy.created_revision:
                continue
            if event.code not in relevant_codes:
                continue
            if event.code == "card.draw.private" and seat not in event.visibility:
                continue
            return True
        return False

    def _has_conservative_response(self, seat: str) -> bool:
        player = self.state.players[seat]
        for object_id in player.zones["hand"]:
            record = self.card_record(object_id)
            if record and (record.is_instant or record.has_flash):
                return True
        return bool(self._ability_hints(seat))

    def _can_auto_pass(self, seat: str) -> bool:
        policy = self.state.players[seat].yield_policy
        if policy.mode == "none" or self._yield_stopped(seat):
            self.state.players[seat].yield_policy = YieldPolicy()
            return False
        if policy.mode == "auto_if_no_response" and self._has_conservative_response(seat):
            return False
        return True

    def _pass_priority(self, seat: str, *, automatic: bool = False) -> None:
        if self.state.priority_player != seat:
            raise GameRuleError(f"{seat} does not have priority")
        self.state.priority_passes.append(seat)
        if not automatic:
            self._log(seat, "priority.pass", f"{seat} passed priority.", importance=0)
        if len(self.state.priority_passes) >= len(self.active_seats):
            self.state.priority_player = None
            self.state.priority_passes = []
            if self.state.stack:
                self._prepare_stack_resolution()
            else:
                self._advance_step()
            return
        self.state.priority_player = self._next_active_after(seat)

    def pump(self, *, max_transitions: int = 1000) -> None:
        """Run deterministic system transitions until an external decision is needed."""
        for _ in range(max_transitions):
            if self.state.game_over or self.state.pending_decision is not None:
                return
            if not self.state.started:
                return
            if self.state.priority_player is not None:
                seat = self.state.priority_player
                if self.state.config.auto_pass_empty_priority and self._priority_window_empty(seat):
                    self._pass_priority(seat, automatic=True)
                    continue
                if self._can_auto_pass(seat):
                    self._pass_priority(seat, automatic=True)
                    continue
                self._issue_priority(seat)
                return
            # Step handlers normally either advance or grant priority. Re-enter
            # only as a fail-safe for a loaded state between transitions.
            self._enter_step()
        raise StateInvariantError("Automatic transition limit exceeded")

    # ------------------------------------------------------------------
    # Delayed triggers and trigger ordering
    # ------------------------------------------------------------------
    def schedule_delayed_trigger(
        self,
        *,
        controller: str,
        label: str,
        event_kind: str,
        condition: Mapping[str, Any],
        stack_template: Mapping[str, Any],
        source_object_id: str | None = None,
        once: bool = True,
        expires_turn_sequence: int | None = None,
    ) -> DelayedTrigger:
        ref = self._next_ref("DT")
        trigger = DelayedTrigger(
            trigger_id=self._stable_runtime_id("delayed-trigger", ref),
            ref=ref,
            controller=controller,
            label=label,
            source_object_id=source_object_id,
            event_kind=event_kind,
            condition=dict(condition),
            stack_template=dict(stack_template),
            once=once,
            created_turn_sequence=self.state.turn_sequence,
            expires_turn_sequence=expires_turn_sequence,
        )
        self.state.delayed_triggers.append(trigger)
        self._log(controller, "trigger.delayed.created", f"Created delayed trigger {trigger.ref}: {label}.", {"trigger": trigger.ref, "condition": dict(condition)}, importance=1)
        return trigger

    def _trigger_matches(self, trigger: DelayedTrigger, event_kind: str, context: Mapping[str, Any]) -> bool:
        if not trigger.active or trigger.event_kind != event_kind:
            return False
        if trigger.expires_turn_sequence is not None and self.state.turn_sequence > trigger.expires_turn_sequence:
            trigger.active = False
            return False
        for key, expected in trigger.condition.items():
            if key == "after_turn_sequence":
                if self.state.turn_sequence <= int(expected):
                    return False
                continue
            if key == "player" and expected == "controller":
                expected = trigger.controller
            if context.get(key) != expected:
                return False
        return True

    def _matching_delayed_triggers(self, event_kind: str, context: Mapping[str, Any]) -> list[DelayedTrigger]:
        matches = [trigger for trigger in self.state.delayed_triggers if self._trigger_matches(trigger, event_kind, context)]
        for trigger in matches:
            if trigger.once:
                trigger.active = False
        return matches

    def _start_trigger_batch(self, triggers: Sequence[DelayedTrigger], *, after: str) -> None:
        apnap = self.apnap_order()
        groups: list[dict[str, Any]] = []
        for controller in apnap:
            ids = [trigger.trigger_id for trigger in triggers if trigger.controller == controller]
            if ids:
                groups.append({"controller": controller, "trigger_ids": ids})
        self._process_trigger_groups(groups, after=after)

    def _process_trigger_groups(self, groups: list[dict[str, Any]], *, after: str) -> None:
        while groups:
            group = groups.pop(0)
            controller = group["controller"]
            ids = list(group["trigger_ids"])
            if len(ids) > 1:
                triggers = [next(t for t in self.state.delayed_triggers if t.trigger_id == trigger_id) for trigger_id in ids]
                self.permissions.issue(
                    kind="trigger.order",
                    role="pilot",
                    actors=[controller],
                    allowed_actions=["order"],
                    payload_by_actor={
                        controller: {
                            "triggers": [{"id": t.ref, "label": t.label} for t in triggers],
                            "instruction": "Order bottom-to-top on the stack.",
                        }
                    },
                    continuation={"groups": groups, "after": after, "trigger_ids": ids},
                )
                return
            self._queue_delayed_trigger(ids[0])
        if after == "grant_priority":
            self._grant_priority(self.state.active_player)

    def _complete_trigger_order(self, decision: Any) -> None:
        controller = decision.actors[0]
        values = list(decision.responses[controller].get("triggers") or decision.responses[controller].get("order") or [])
        ids = list(decision.continuation["trigger_ids"])
        by_ref = {trigger.ref: trigger.trigger_id for trigger in self.state.delayed_triggers if trigger.trigger_id in ids}
        resolved = [by_ref.get(str(value), str(value)) for value in values]
        if sorted(resolved) != sorted(ids):
            raise GameRuleError("Trigger order must contain every listed trigger exactly once")
        for trigger_id in resolved:
            self._queue_delayed_trigger(trigger_id)
        self._process_trigger_groups(list(decision.continuation.get("groups", [])), after=str(decision.continuation.get("after") or "grant_priority"))

    def _queue_delayed_trigger(self, trigger_id: str) -> None:
        trigger = next(t for t in self.state.delayed_triggers if t.trigger_id == trigger_id)
        template = trigger.stack_template
        ref = self._next_ref("S")
        item = StackItem(
            stack_id=self._stable_runtime_id("stack", ref),
            ref=ref,
            kind="triggered_ability",
            controller=trigger.controller,
            label=str(template.get("label") or trigger.label),
            source_object_id=trigger.source_object_id,
            semantic_key=template.get("semantic_key"),
            targets=list(template.get("targets") or []),
            notes=str(template.get("note") or ""),
            visibility=list(self.seats),
        )
        self.state.stack.append(item)
        self._log(trigger.controller, "stack.trigger", f"Queued {item.ref}: {item.label}.", {"stack": item.ref, "trigger": trigger.ref}, importance=2)

    # ------------------------------------------------------------------
    # Mana, land plays, spells, and abilities
    # ------------------------------------------------------------------
    def _commander_identity(self, seat: str) -> set[str]:
        colors: set[str] = set()
        for oracle_id in self.state.commander_oracle_ids[seat]:
            colors.update(self.card_db.by_oracle_id(oracle_id).color_identity)
        return colors

    def available_mana_sources(self, seat: str) -> list[ManaSource]:
        identity = self._commander_identity(seat)
        sources: list[ManaSource] = []
        for object_id in self.state.players[seat].zones["battlefield"]:
            card = self.state.cards[object_id]
            if card.controller != seat or card.tapped or card.phased_out:
                continue
            record = self.card_record(card)
            if not record:
                continue
            modes = extract_mana_modes(record, identity)
            if modes:
                sources.append(ManaSource(object_id, card.ref, self.display_name(object_id), modes))
        return sources

    def _activate_mana_plan(self, seat: str, activations: Sequence[Mapping[str, Any]]) -> None:
        for activation in activations:
            card = self._resolve_object(seat, str(activation["source"]), zones={"battlefield"}, controlled_only=True)
            if card.tapped:
                raise GameRuleError(f"{card.ref} is already tapped")
            bundle = normalize_mana_bundle(activation.get("bundle"))
            record = self.card_record(card)
            if not record:
                raise GameRuleError(f"{card.ref} is not a card-backed mana source")
            modes = extract_mana_modes(record, self._commander_identity(seat))
            matching = [mode for mode in modes if normalize_mana_bundle(mode.bundle) == bundle]
            if not matching:
                raise GameRuleError(f"Declared output is not a recognized mana mode of {card.printed_name}")
            mode = matching[0]
            if mode.requires_choice:
                raise GameRuleError(
                    f"{card.printed_name}'s selected mana mode has a nonmana choice/cost; activate that Oracle ability explicitly."
                )
            if mode.conditional and self.state.config.strict_mana:
                raise GameRuleError(
                    f"{card.printed_name}'s selected mana mode is conditional/restricted and has no compiled validator."
                )
            if mode.conditional and not activation.get("allow_conditional"):
                raise GameRuleError(f"{card.printed_name}'s selected mana mode requires an explicit condition")
            card.tapped = True
            for color, amount in bundle.items():
                self.state.players[seat].mana_pool[color] += amount
            for effect in activation.get("side_effects") or mode.side_effects:
                if effect.get("op") == "damage_self":
                    self.state.players[seat].life -= int(effect.get("amount", 1))
                elif effect.get("op") == "pay_life":
                    amount = int(effect.get("amount", 1))
                    if self.state.players[seat].life < amount:
                        raise GameRuleError("Cannot pay more life than the player has")
                    self.state.players[seat].life -= amount
            self._log(seat, "mana.produce", f"{seat} tapped {card.ref} for { {k:v for k,v in bundle.items() if v} }.", {"source": card.ref, "bundle": {k:v for k,v in bundle.items() if v}}, importance=0, changed_objects=[card.object_id], changed_players=[seat])

    def _pay_for_cost(
        self,
        seat: str,
        requirements: dict[str, int],
        response: Mapping[str, Any],
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        activations: list[dict[str, Any]] = []
        pay_mode = response.get("pay", "auto")
        if pay_mode == "auto":
            plan = auto_plan_payment(
                requirements,
                self.available_mana_sources(seat),
                allow_conditional=(
                    bool(response.get("allow_conditional_mana", False))
                    and not self.state.config.strict_mana
                ),
                reserve=normalize_mana_bundle(response.get("reserve")),
            )
            activations = plan.activations
            self._activate_mana_plan(seat, activations)
            payment = plan.payment
        else:
            activations = [dict(item) for item in response.get("mana") or []]
            self._activate_mana_plan(seat, activations)
            payment = normalize_mana_bundle(response.get("payment"))
        try:
            new_pool, spent = pay_mana_from_pool(self.state.players[seat].mana_pool, requirements, payment=payment)
        except ValueError as exc:
            raise GameRuleError(str(exc)) from exc
        self.state.players[seat].mana_pool = new_pool
        return spent, activations

    def _check_priority(self, seat: str) -> None:
        if self.state.priority_player != seat:
            raise GameRuleError(f"{seat} does not have priority")

    def _sorcery_timing(self, seat: str) -> None:
        if seat != self.state.active_player:
            raise GameRuleError("Sorcery-speed action requires the active player")
        if (self.state.phase, self.state.step) not in {("precombat_main", "main"), ("postcombat_main", "main")}:
            raise GameRuleError("Sorcery-speed action requires a main phase")
        if self.state.stack:
            raise GameRuleError("Sorcery-speed action requires an empty stack")

    def _land_enters_tapped(
        self,
        seat: str | CardRecord,
        record: CardRecord | Mapping[str, Any],
        choices: Mapping[str, Any] | None = None,
    ) -> bool:
        # Preserve the 0.2 internal probe signature used by downstream rules
        # tests while requiring a seat for contextual conditions in live play.
        if isinstance(seat, CardRecord):
            choices = record if isinstance(record, Mapping) else choices
            record = seat
            seat = self.state.active_player or self.seats[0]
        choices = choices or {}
        oracle = record.oracle_text.casefold()
        opponents = max(0, len(self.active_seats) - 1)
        if "enters tapped unless you have two or more opponents" in oracle:
            return opponents < 2
        if "you may pay 2 life. if you don't, it enters tapped" in oracle:
            if choices.get("pay_life"):
                if self.state.players[str(seat)].life < 2:
                    raise GameRuleError("Cannot pay more life than the player has")
                return False
            return True
        if "enters tapped unless you control a forest" in oracle:
            return not any(
                "forest" in str(self._effective_card_data(oid).get("type_line") or "").casefold()
                for oid in self.state.players[seat].zones["battlefield"]
                if self.state.cards[oid].controller == seat
            )
        if re.search(r"\benters (?:the battlefield )?tapped\b", oracle) and "unless" not in oracle:
            return True
        if "enters tapped unless" in oracle:
            raise GameRuleError(
                f"{record.name} has an entry condition the rules engine has not compiled"
            )
        return False

    def _play_land(self, seat: str, response: Mapping[str, Any]) -> None:
        self._check_priority(seat)
        self._sorcery_timing(seat)
        player = self.state.players[seat]
        if player.land_plays_remaining <= 0:
            raise GameRuleError("No land plays remain")
        card = self._resolve_object(seat, str(response.get("card") or response.get("id")), zones={"hand"}, owned_only=True)
        record = self.card_record(card)
        if not record or not record.is_land:
            raise GameRuleError(f"{card.printed_name} is not a land")
        if "enters_tapped" in response or "tapped" in response:
            raise GameRuleError("Land entry state is derived by the rules engine")
        tapped = self._land_enters_tapped(seat, record, response)
        if response.get("pay_life"):
            player.life -= 2
        self.move_card(card.object_id, "battlefield", controller=seat, tapped=tapped, reason="land play", log=False)
        player.land_plays_remaining -= 1
        self._log(seat, "land.play", f"{seat} played {card.ref} {card.printed_name}{' tapped' if tapped else ''}.", {"object": card.ref, "tapped": tapped}, importance=2, changed_objects=[card.object_id], changed_players=[seat])
        self.state.priority_passes = []
        self.state.priority_player = seat

    def _select_cast_face(self, record: CardRecord, face_name: str | None) -> dict[str, Any] | None:
        if not record.faces:
            return None
        if face_name:
            for face in record.faces:
                if str(face.get("name") or "").casefold() == face_name.casefold():
                    return dict(face)
            raise GameRuleError(f"{face_name!r} is not a face of {record.name}")
        return dict(record.faces[0])

    def _cast(self, seat: str, response: Mapping[str, Any]) -> None:
        self._check_priority(seat)
        raw_from = response.get("from")
        zones = ({str(raw_from)} if isinstance(raw_from, str) else set(raw_from or ["hand", "command"]))
        card = self._resolve_object(seat, str(response.get("card") or response.get("id")), zones=zones, owned_only=True)
        if card.zone == "command" and not card.is_commander:
            raise GameRuleError("Only this seat's commander cards may be cast from the command zone")
        if card.zone not in {"hand", "command"}:
            permissions = set(card.annotations.get("cast_from") or [])
            if card.zone not in permissions:
                raise GameRuleError(
                    f"Casting {card.printed_name} from {card.zone} is not authorized by a compiled zone permission."
                )
        record = self.card_record(card)
        if not record:
            raise GameRuleError("Cannot cast a custom token")
        face = self._select_cast_face(record, response.get("face"))
        type_line = str(face.get("type_line") or "") if face else record.type_line
        mana_cost = str(face.get("mana_cost") or "") if face else record.mana_cost
        is_instant = "instant" in type_line.casefold()
        has_flash = record.has_flash
        if self.state.config.strict_timing and not (is_instant or has_flash):
            self._sorcery_timing(seat)
        commander_tax = 0
        if card.zone == "command" and card.is_commander:
            commander_tax = 2 * self.state.players[seat].commander_casts.get(card.oracle_id, 0)
        declared_cost = response.get("declared_cost")
        try:
            requirements = parsed_cost(mana_cost, commander_tax)
        except ManaPlanError as exc:
            # X is an objective pilot choice and can be compiled without an
            # arbiter. Other alternate/hybrid/Phyrexian costs must become a
            # server-issued cost option; a pilot may not simply assert a cheap
            # declared_cost against authoritative state.
            fixed, complex_symbols = mana_cost_to_vector(mana_cost)
            if complex_symbols and set(complex_symbols) == {"X"} and response.get("x") is not None:
                x_value = int(response.get("x"))
                if x_value < 0:
                    raise GameRuleError("X cannot be negative")
                fixed["GENERIC"] += x_value * complex_symbols.count("X") + commander_tax
                requirements = fixed
            elif self.state.config.strict_mana:
                raise GameRuleError(
                    f"{card.printed_name} has an uncompiled casting cost ({mana_cost}). "
                    "The rules/cost compiler must issue a legal cost option; pilots cannot supply declared_cost."
                ) from exc
            elif declared_cost:
                requirements = {"GENERIC": int(declared_cost.get("GENERIC", 0))}
                for color in "WUBRGC":
                    requirements[color] = int(declared_cost.get(color, 0))
                requirements["GENERIC"] += commander_tax
            else:
                raise GameRuleError(f"Supply declared_cost for {card.printed_name} in non-strict mode: {exc}") from exc
        if declared_cost and self.state.config.strict_mana:
            supplied = {"GENERIC": int(declared_cost.get("GENERIC", 0)) + commander_tax}
            supplied.update({color: int(declared_cost.get(color, 0)) for color in "WUBRGC"})
            if supplied != requirements:
                raise GameRuleError(
                    f"Pilot-declared casting cost {supplied} does not match authoritative cost {requirements}."
                )
        spent, activations = self._pay_for_cost(seat, requirements, response)
        origin = card.zone
        self._remove_from_zone(card)
        card.zone = "stack"
        card.controller = seat
        card.active_face = str(face.get("name")) if face else None
        default_destination = "battlefield" if any(word in type_line.casefold() for word in ("artifact", "battle", "creature", "enchantment", "planeswalker")) else "graveyard"
        semantic_key = str(response.get("semantic_key") or f"{record.oracle_id}:spell:{card.active_face or 'front'}")
        ref = self._next_ref("S")
        item = StackItem(
            stack_id=self._stable_runtime_id("stack", ref),
            ref=ref,
            kind="spell",
            controller=seat,
            label=card.active_face or record.name,
            card_object_id=card.object_id,
            semantic_key=semantic_key,
            targets=list(response.get("targets") or []),
            modes=list(response.get("modes") or []),
            x_value=response.get("x"),
            chosen_face=card.active_face,
            notes=str(response.get("note") or ""),
            default_destination=default_destination,
            visibility=list(self.seats),
        )
        self.state.stack.append(item)
        if origin == "command" and card.is_commander:
            player = self.state.players[seat]
            player.commander_casts[card.oracle_id] = player.commander_casts.get(card.oracle_id, 0) + 1
        self._log(
            seat,
            "stack.cast",
            f"{seat} cast {item.ref} {item.label}.",
            {
                "stack": item.ref,
                "object": card.ref,
                "from": origin,
                "requirements": requirements,
                "payment": {k:v for k,v in spent.items() if v},
                "mana_sources": [{"source": a.get("source_ref"), "bundle": a.get("bundle")} for a in activations],
                "targets": item.targets,
                "commander_tax": commander_tax,
            },
            importance=2,
            changed_objects=[card.object_id],
            changed_players=[seat],
        )
        self.state.priority_player = seat
        self.state.priority_passes = []
        self.state.players[seat].yield_policy = YieldPolicy()

    def _activated_abilities(self, card: CardInstance) -> tuple[ActivatedAbility, ...]:
        data = self._effective_card_data(card)
        return parse_activated_abilities(
            card_name=str(data.get("name") or card.printed_name),
            oracle_text=str(data.get("oracle_text") or ""),
            keywords=tuple(data.get("keywords") or ()),
        )

    def _legendary_creatures_controlled(self, seat: str) -> int:
        total = 0
        for object_id in self.state.players[seat].zones["battlefield"]:
            card = self.state.cards[object_id]
            if card.controller != seat or card.phased_out:
                continue
            type_line = str(self._effective_card_data(card).get("type_line") or "").casefold()
            if "legendary" in type_line and "creature" in type_line:
                total += 1
        return total

    def _pay_ability_choice_costs(
        self,
        seat: str,
        source: CardInstance,
        ability: ActivatedAbility,
        response: Mapping[str, Any],
    ) -> list[str]:
        values = list(response.get("cost_cards") or response.get("cost_objects") or [])
        required = sum(choice.count for choice in ability.choices)
        if len(values) != required:
            if required:
                raise GameRuleError(f"Ability requires exactly {required} selected cost card(s)")
            if values:
                raise GameRuleError("This ability has no selectable card cost")
        used: list[str] = []
        cursor = 0
        for choice in ability.choices:
            for _ in range(choice.count):
                value = str(values[cursor])
                cursor += 1
                if choice.zone == "battlefield":
                    card = self._resolve_object(seat, value, zones={"battlefield"}, controlled_only=True)
                else:
                    card = self._resolve_object(seat, value, zones={choice.zone}, owned_only=True)
                if card.object_id in used:
                    raise GameRuleError("The same object cannot pay the same activation cost twice")
                if choice.another and card.object_id == source.object_id:
                    raise GameRuleError("An 'another' cost cannot use the ability source")
                if choice.card_type:
                    type_line = str(self._effective_card_data(card).get("type_line") or "").casefold()
                    if choice.card_type not in type_line:
                        raise GameRuleError(f"{card.ref} is not a {choice.card_type}")
                used.append(card.object_id)
                destination = "graveyard"
                self.move_card(card.object_id, destination, reason="activated ability cost")
        return used

    def _mana_output_for_ability(
        self,
        seat: str,
        source: CardInstance,
        ability: ActivatedAbility,
        response: Mapping[str, Any],
    ) -> dict[str, int]:
        output_text = ability.effect_text.split(".", 1)[0]
        output, complex_symbols = mana_cost_to_vector(output_text)
        bundle = {color: int(output.get(color, 0)) for color in "WUBRGC"}
        if output.get("GENERIC"):
            # Numeric symbols in an Add instruction represent colorless mana.
            bundle["C"] += int(output["GENERIC"])
        if sum(bundle.values()) and not complex_symbols:
            return normalize_mana_bundle(bundle)
        declared = normalize_mana_bundle(response.get("mana_output"))
        record = self.card_record(source)
        if not record:
            raise GameRuleError("Custom mana ability needs compiled semantics")
        legal_modes = extract_mana_modes(record, self._commander_identity(seat))
        if not any(normalize_mana_bundle(mode.bundle) == declared for mode in legal_modes):
            raise GameRuleError("Declared mana output is not a recognized Oracle mana mode")
        return declared

    @staticmethod
    def _fetch_land_types(effect_text: str) -> tuple[str, ...]:
        match = re.search(
            r"search your library for (?:an?|up to one) "
            r"(?P<types>[A-Za-z ]+?(?: or [A-Za-z ]+?)*) card, "
            r"put (?:it|that card) onto the battlefield",
            effect_text,
            re.IGNORECASE,
        )
        if not match:
            return ()
        value = match.group("types").casefold()
        return tuple(
            part.strip()
            for part in re.split(r"\s+or\s+", value)
            if part.strip() in {"plains", "island", "swamp", "mountain", "forest"}
        )

    def _fetch_land_options(self, seat: str, land_types: Sequence[str]) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        for object_id in self.state.players[seat].zones["library"]:
            card = self.state.cards[object_id]
            record = self.card_record(card)
            type_line = record.type_line.casefold() if record else ""
            if record and record.is_land and any(land_type in type_line for land_type in land_types):
                options.append({"id": card.ref, "name": record.name})
        return sorted(options, key=lambda item: (item["name"], item["id"]))

    def _fetch_context(
        self,
        seat: str,
        ability: ActivatedAbility,
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        land_types = self._fetch_land_types(ability.effect_text)
        if not land_types:
            return {}
        options = self._fetch_land_options(seat, land_types)
        selected = str(response.get("search_card") or "")
        if selected and selected not in {item["id"] for item in options}:
            raise GameRuleError("Selected fetchland result is not a legal card in your library")
        return {
            "builtin": "fetch_land",
            "land_types": list(land_types),
            "search_card": selected or None,
            "choice_made": bool(selected),
            "pay_life": bool(response.get("entry_pay_life", False)),
        }

    def _activate(self, seat: str, response: Mapping[str, Any]) -> None:
        self._check_priority(seat)
        raw_from = response.get("from")
        requested_zones = (
            {str(raw_from)}
            if isinstance(raw_from, str)
            else set(raw_from or {"battlefield", "hand", "graveyard", "exile"})
        )
        source = self._resolve_object(
            seat,
            str(response.get("source") or response.get("id")),
            zones=requested_zones,
            controlled_only=False,
            owned_only=False,
        )
        if source.zone == "battlefield":
            if source.controller != seat:
                raise GameRuleError("You do not control that ability source")
        elif source.owner != seat:
            raise GameRuleError("You do not own that nonbattlefield ability source")

        abilities = [ability for ability in self._activated_abilities(source) if source.zone in ability.zones]
        try:
            ability = choose_ability(abilities, response.get("ability", response.get("ability_index")))
        except ValueError as exc:
            raise GameRuleError(str(exc)) from exc
        if source.zone not in ability.zones:
            raise GameRuleError(f"{ability.ability_id} cannot be activated from {source.zone}")
        if not ability.compiled_cost:
            detail = list(ability.complex_symbols) + list(ability.uncompiled_costs)
            raise GameRuleError(
                f"Cost for {source.printed_name} {ability.ability_id} is not compiled: {detail}. "
                "Request a rules/cost semantic rather than declaring the cost as a pilot."
            )
        if self.state.config.strict_mana and any(
            key in response for key in ("mana_cost", "declared_cost", "costs", "cost_effects", "tap")
        ):
            raise GameRuleError(
                "Pilot-supplied activation costs are disabled in strict mode; select the Oracle ability and cost objects only."
            )
        if ability.sorcery_speed:
            self._sorcery_timing(seat)

        builtin_context = self._fetch_context(seat, ability, response)
        if ability.tap_source:
            if source.zone != "battlefield":
                raise GameRuleError("Tap costs require a battlefield permanent")
            if source.tapped:
                raise GameRuleError(f"{source.ref} is tapped")
            if self._is_summoning_sick(source) and "Haste" not in self._effective_card_data(source).get("keywords", []):
                raise GameRuleError(f"{source.ref} is summoning sick")
            source.tapped = True
        if ability.untap_source:
            if source.zone != "battlefield" or not source.tapped:
                raise GameRuleError("Untap-symbol cost requires a tapped battlefield permanent")
            source.tapped = False

        paid_objects = self._pay_ability_choice_costs(seat, source, ability, response)
        if ability.life_payment:
            if self.state.players[seat].life < ability.life_payment:
                raise GameRuleError("Cannot pay more life than the player has")
            self.state.players[seat].life -= ability.life_payment

        requirements = reduced_requirements(
            ability,
            legendary_creatures=self._legendary_creatures_controlled(seat),
        )
        spent: dict[str, int] = {}
        activations: list[dict[str, Any]] = []
        if sum(requirements.values()):
            spent, activations = self._pay_for_cost(seat, requirements, response)

        origin = source.zone
        if ability.discard_source:
            if source.zone != "hand":
                raise GameRuleError("Discard-this-card cost requires the source in hand")
            self.move_card(source.object_id, "graveyard", reason="activated ability cost")
        elif ability.sacrifice_source:
            if source.zone != "battlefield":
                raise GameRuleError("Sacrifice-source cost requires the source on the battlefield")
            self.move_card(source.object_id, "graveyard", reason="activated ability cost")
        elif ability.exile_source:
            self.move_card(source.object_id, "exile", reason="activated ability cost")

        if ability.mana_ability:
            bundle = self._mana_output_for_ability(seat, source, ability, response)
            for color, amount in bundle.items():
                self.state.players[seat].mana_pool[color] += amount
            self._log(
                seat,
                "mana.ability",
                f"{seat} activated {source.ref} {ability.ability_id} for mana.",
                {
                    "source": source.ref,
                    "ability": ability.ability_id,
                    "from": origin,
                    "bundle": {k: v for k, v in bundle.items() if v},
                    "cost_objects": [self.state.cards[oid].ref for oid in paid_objects],
                },
                importance=0,
                changed_objects=[source.object_id, *paid_objects],
                changed_players=[seat],
            )
            self.state.priority_player = seat
            self.state.priority_passes = []
            return

        semantic_key = str(
            response.get("semantic_key")
            or ("builtin:fetch_land" if builtin_context else f"{source.oracle_id}:ability:{ability.ability_id}")
        )
        ref = self._next_ref("S")
        item = StackItem(
            stack_id=self._stable_runtime_id("stack", ref),
            ref=ref,
            kind="activated_ability",
            controller=seat,
            label=str(response.get("label") or f"{self.display_name(source.object_id)} — {ability.effect_text}"),
            source_object_id=source.object_id,
            semantic_key=semantic_key,
            targets=list(response.get("targets") or []),
            modes=list(response.get("modes") or []),
            notes=str(response.get("note") or ""),
            visibility=list(self.seats),
            context=builtin_context,
        )
        self.state.stack.append(item)
        self._log(
            seat,
            "stack.activate",
            f"{seat} activated {item.ref}: {item.label}.",
            {
                "stack": item.ref,
                "source": source.ref,
                "ability": ability.ability_id,
                "from": origin,
                "requirements": requirements,
                "payment": {k: v for k, v in spent.items() if v},
                "mana_sources": [{"source": a.get("source_ref"), "bundle": a.get("bundle")} for a in activations],
                "cost_objects": [self.state.cards[oid].ref for oid in paid_objects],
                "targets": item.targets,
            },
            importance=2,
            changed_objects=[source.object_id, *paid_objects],
            changed_players=[seat],
        )
        self.state.priority_player = seat
        self.state.priority_passes = []
        self.state.players[seat].yield_policy = YieldPolicy()

    def _ability_hints(self, seat: str) -> list[dict[str, Any]]:
        player = self.state.players[seat]
        hints: list[dict[str, Any]] = []
        for zone in ("battlefield", "hand", "graveyard", "exile"):
            for object_id in player.zones[zone]:
                card = self.state.cards[object_id]
                if zone == "battlefield":
                    if card.controller != seat or card.phased_out:
                        continue
                elif card.owner != seat:
                    continue
                for ability in self._activated_abilities(card):
                    if zone not in ability.zones:
                        continue
                    if not ability.compiled_cost:
                        continue
                    if ability.tap_source and (zone != "battlefield" or card.tapped):
                        continue
                    if ability.life_payment and player.life < ability.life_payment:
                        continue
                    # Ordinary tap-for-one mana abilities do not justify an LLM
                    # call. Mana abilities with sacrifices, life payments, or
                    # other strategic costs remain visible so the player can
                    # float mana before a subsequent action (for example,
                    # Phyrexian Tower).
                    if ability.mana_ability and not (
                        ability.choices
                        or ability.life_payment
                        or ability.discard_source
                        or ability.sacrifice_source
                        or ability.exile_source
                        or ability.uncompiled_costs
                    ):
                        continue
                    hint = ability.compact(source_ref=card.ref, zone=zone)
                    fetch_types = self._fetch_land_types(ability.effect_text)
                    if fetch_types:
                        hint["search_types"] = list(fetch_types)
                    hints.append(hint)
        return hints

    def _mana_ability_hints(self, seat: str) -> list[dict[str, Any]]:
        player = self.state.players[seat]
        hints: list[dict[str, Any]] = []
        for object_id in player.zones["battlefield"]:
            card = self.state.cards[object_id]
            if card.controller != seat or card.phased_out or card.tapped:
                continue
            for ability in self._activated_abilities(card):
                if (
                    ability.mana_ability
                    and "battlefield" in ability.zones
                    and ability.compiled_cost
                    and (not ability.tap_source or not card.tapped)
                    and player.life >= ability.life_payment
                ):
                    hints.append(
                        ability.compact(source_ref=card.ref, zone="battlefield")
                    )
        return hints

    def _cost_is_affordable(self, seat: str, requirements: Mapping[str, int]) -> bool:
        remaining = {key: int(requirements.get(key, 0)) for key in ("GENERIC", "W", "U", "B", "R", "G", "C")}
        pool = normalize_mana_bundle(self.state.players[seat].mana_pool)
        for color in "WUBRGC":
            paid = min(pool[color], remaining[color])
            pool[color] -= paid
            remaining[color] -= paid
        generic_paid = min(sum(pool.values()), remaining["GENERIC"])
        remaining["GENERIC"] -= generic_paid
        if not sum(remaining.values()):
            return True
        try:
            auto_plan_payment(remaining, self.available_mana_sources(seat))
            return True
        except ManaPlanError:
            return False

    def _card_cast_requirements(self, seat: str, card: CardInstance) -> dict[str, int] | None:
        record = self.card_record(card)
        if not record:
            return None
        commander_tax = (
            2 * self.state.players[seat].commander_casts.get(card.oracle_id, 0)
            if card.zone == "command" and card.is_commander
            else 0
        )
        try:
            return parsed_cost(record.mana_cost, commander_tax)
        except ManaPlanError:
            return None

    def _priority_action_hints(self, seat: str) -> dict[str, Any]:
        player = self.state.players[seat]
        candidate_zones = [*player.zones["hand"], *player.zones["command"]]
        castable: list[str] = []
        for oid in candidate_zones:
            record = self.card_record(oid)
            if not record or record.is_land:
                continue
            main_timing = seat == self.state.active_player and not self.state.stack and self.state.step == "main"
            requirements = self._card_cast_requirements(seat, self.state.cards[oid])
            if (
                (record.is_instant or record.has_flash or main_timing)
                and requirements is not None
                and self._cost_is_affordable(seat, requirements)
            ):
                castable.append(self.state.cards[oid].ref)
        lands: list[str] = []
        if seat == self.state.active_player and not self.state.stack and self.state.step == "main" and player.land_plays_remaining:
            lands = [
                self.state.cards[oid].ref
                for oid in player.zones["hand"]
                if (self.card_record(oid) and self.card_record(oid).is_land)
            ]
        abilities = self._ability_hints(seat)
        mana_abilities = self._mana_ability_hints(seat)
        actions: list[dict[str, Any]] = [{"id": "pass", "action": "pass"}]
        actions.extend(
            {"id": f"play-land:{ref}", "action": "play_land", "card": ref}
            for ref in lands
        )
        actions.extend(
            {"id": f"cast:{ref}", "action": "cast", "card": ref}
            for ref in castable
        )
        seen_ability_actions: set[str] = set()
        for ability in [*abilities, *mana_abilities]:
            action_id = f"activate:{ability['s']}:{ability['a']}"
            if action_id in seen_ability_actions:
                continue
            seen_ability_actions.add(action_id)
            action = {
                "id": action_id,
                "action": "activate",
                "source": ability["s"],
                "ability": ability["a"],
                "from": ability["z"],
            }
            actions.append(action)
        return {
            "cast": castable,
            "lands": lands,
            "abilities": abilities,
            "mana_abilities": mana_abilities,
            "actions": actions,
        }

    def _priority_window_empty(self, seat: str) -> bool:
        """Whether the implemented action grammar exposes no priority action.

        Concede is deliberately ignored: the simulator should not spend an LLM
        call merely to offer concession at every priority window. The setting
        can be disabled for debugging or for a future client that implements
        additional special actions not yet represented by the kernel.
        """

        hints = self._priority_action_hints(seat)
        return not any(hints.get(key) for key in ("cast", "lands", "abilities"))

    # ------------------------------------------------------------------
    # Stack resolution and arbiter role
    # ------------------------------------------------------------------
    def _program_can_auto_resolve(self, item: StackItem) -> bool:
        program = self.semantics.get(item.semantic_key)
        if program and not program.requires_arbiter:
            return True
        if item.kind == "spell" and item.card_object_id:
            record = self.card_record(item.card_object_id)
            if record and item.default_destination == "battlefield":
                oracle = record.oracle_text.casefold()
                semantic_markers = ("when ", "whenever ", "as ~ enters", "as this", "enters with", "you may have")
                return not any(marker in oracle for marker in semantic_markers)
        return False

    def _prepare_stack_resolution(self) -> None:
        if not self.state.stack:
            self._advance_step()
            return
        item = self.state.stack[-1]
        if item.context.get("builtin") == "fetch_land":
            if not item.context.get("choice_made"):
                options = self._fetch_land_options(
                    item.controller,
                    item.context.get("land_types", []),
                )
                self.permissions.issue(
                    kind="search.fetch",
                    role="pilot",
                    actors=[item.controller],
                    allowed_actions=["choose"],
                    payload_by_actor={
                        item.controller: {
                            "stack": item.ref,
                            "instruction": "Choose a legal land to find, or omit search_card to fail to find.",
                            "search_types": list(item.context.get("land_types", [])),
                            "search_cards": options,
                        }
                    },
                    continuation={"stack_ref": item.ref},
                )
                return
            self._resolve_fetch_land(item)
            return
        program = self.semantics.get(item.semantic_key)
        if program and not program.requires_arbiter:
            self._begin_resolve_item(item, program.effects, program.destination or item.default_destination, note=program.notes)
            return
        if self._program_can_auto_resolve(item):
            self._begin_resolve_item(item, [], item.default_destination, note="Automatic vanilla/default resolution")
            return
        self.permissions.issue(
            kind="arbiter.resolve",
            role="arbiter",
            actors=["arbiter"],
            allowed_actions=["resolve", "register_and_resolve", "counter_as_rule", "fizzle"],
            payload_by_actor={
                "arbiter": {
                    "stack": item.ref,
                    "label": item.label,
                    "controller": item.controller,
                    "semantic_key": item.semantic_key,
                    "targets": item.targets,
                    "default_destination": item.default_destination,
                }
            },
        )

    def _complete_fetch_choice(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        stack_ref = str(decision.continuation.get("stack_ref") or "")
        item = next(
            (candidate for candidate in self.state.stack if candidate.ref == stack_ref),
            None,
        )
        if item is None or item.context.get("builtin") != "fetch_land":
            raise GameRuleError("The fetchland search object is no longer on the stack")
        selected = response.get("search_card") or response.get("card")
        options = {
            option["id"]
            for option in self._fetch_land_options(
                seat,
                item.context.get("land_types", []),
            )
        }
        if selected is not None and str(selected) not in options:
            raise GameRuleError("Selected fetchland result is no longer a legal library card")
        item.context["search_card"] = str(selected) if selected is not None else None
        item.context["choice_made"] = True
        self._resolve_fetch_land(item)

    def _resolve_fetch_land(self, item: StackItem) -> None:
        seat = item.controller
        selected = item.context.get("search_card")
        found: CardInstance | None = None
        if selected:
            try:
                candidate = self._resolve_object(
                    seat,
                    str(selected),
                    zones={"library"},
                    owned_only=True,
                )
            except GameRuleError:
                candidate = None
            if candidate is not None:
                record = self.card_record(candidate)
                type_line = record.type_line.casefold() if record else ""
                if record and record.is_land and any(
                    land_type in type_line
                    for land_type in item.context.get("land_types", [])
                ):
                    found = candidate
        if found is not None:
            record = self.card_record(found)
            assert record is not None
            tapped = self._land_enters_tapped(
                seat,
                record,
                {"pay_life": bool(item.context.get("pay_life"))},
            )
            if item.context.get("pay_life") and not tapped:
                self.state.players[seat].life -= 2
            self.move_card(
                found.object_id,
                "battlefield",
                controller=seat,
                tapped=tapped,
                reason=f"{item.label} search",
                log=False,
            )
            self._log(
                seat,
                "library.search",
                f"{seat} found {found.ref} {found.printed_name}.",
                {"source": item.ref, "object": found.ref, "tapped": tapped},
                importance=2,
                changed_objects=[found.object_id],
                changed_players=[seat],
            )
        else:
            self._log(
                seat,
                "library.search",
                f"{seat} did not find a card.",
                {"source": item.ref},
                importance=1,
                changed_players=[seat],
            )
        self.shuffle_library(seat, reason=f"{item.label} resolved")
        self._begin_resolve_item(
            item,
            [],
            None,
            note="Built-in fetchland search resolved",
        )

    def _complete_arbiter_resolution(self, decision: Any) -> None:
        response = decision.responses["arbiter"]
        action = response.pop("action")
        if not self.state.stack:
            raise GameRuleError("Stack became empty before arbiter resolution")
        item = self.state.stack[-1]
        if action == "counter_as_rule" or action == "fizzle":
            self._counter_stack_item(item.ref, destination=str(response.get("destination") or "graveyard"), reason=action)
            self._grant_priority(self.state.active_player)
            return
        effects = [dict(effect) for effect in response.get("effects") or []]
        destination = response.get("destination", item.default_destination)
        note = str(response.get("note") or "")
        if action == "register_and_resolve":
            key = str(response.get("semantic_key") or item.semantic_key or "")
            if not key:
                raise GameRuleError("A semantic_key is required to register a program")
            self.semantics.put(
                SemanticProgram(
                    key=key,
                    label=item.label,
                    effects=effects,
                    destination=destination,
                    notes=note,
                )
            )
            item.semantic_key = key
        self._begin_resolve_item(item, effects, destination, note=note)

    def _begin_resolve_item(
        self,
        item: StackItem,
        effects: Sequence[Mapping[str, Any]],
        destination: str | None,
        *,
        note: str = "",
    ) -> None:
        self._continue_resolution(
            stack_ref=item.ref,
            effects=[dict(effect) for effect in effects],
            destination=destination,
            note=note,
        )

    def _semantic_value(self, value: Any, item: StackItem) -> Any:
        """Resolve transport-safe runtime placeholders in cached semantics.

        Programs can be reused across games because they refer to `$controller`,
        `$active`, `$source`, `$card`, `$stack`, `$x`, or `$target.N` rather than
        physical object ids. Dict/list structures are resolved recursively.
        """
        if isinstance(value, list):
            return [self._semantic_value(child, item) for child in value]
        if isinstance(value, dict):
            return {key: self._semantic_value(child, item) for key, child in value.items()}
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        if value == "$controller":
            return item.controller
        if value == "$active":
            return self.state.active_player
        if value == "$source":
            source = self.state.cards.get(item.source_object_id or "")
            return source.ref if source else None
        if value == "$card":
            card = self.state.cards.get(item.card_object_id or "")
            return card.ref if card else None
        if value == "$stack":
            return item.ref
        if value == "$x":
            return item.x_value or 0
        target_match = re.fullmatch(r"\$target[.\[](?P<index>\d+)\]?", value)
        if target_match:
            index = int(target_match.group("index"))
            if index >= len(item.targets):
                raise GameRuleError(f"Semantic program requested missing target {index}")
            return item.targets[index]
        return value

    def _continue_resolution(
        self,
        *,
        stack_ref: str,
        effects: list[dict[str, Any]],
        destination: str | None,
        note: str,
    ) -> None:
        item = next((candidate for candidate in self.state.stack if candidate.ref == stack_ref), None)
        if item is None:
            raise GameRuleError(f"Stack object {stack_ref} no longer exists")
        index = 0
        while index < len(effects):
            effect = self._semantic_value(effects[index], item)
            if effect.get("op") == "choose_cards_apnap":
                self._issue_apnap_choice(
                    effect=effect,
                    continuation={
                        "stack_ref": stack_ref,
                        "effects": effects[index + 1 :],
                        "destination": destination,
                        "note": note,
                    },
                )
                return
            self.apply_effect(effect, actor=item.controller, as_cost=False)
            index += 1
        # Remove the resolving object from stack only when all player choices
        # and effects have completed.
        self.state.stack.remove(item)
        if item.card_object_id:
            card = self.state.cards[item.card_object_id]
            if card.zone == "stack":
                self.move_card(
                    card.object_id,
                    destination or item.default_destination or "graveyard",
                    controller=item.controller,
                    reason="spell resolved",
                    log=False,
                )
        self._log(item.controller, "stack.resolve", f"Resolved {item.ref} {item.label}.", {"stack": item.ref, "effects": effects, "destination": destination, "note": note}, importance=2, changed_players=[item.controller])
        if self._stabilize():
            return
        self._grant_priority(self.state.active_player)

    def _counter_stack_item(self, value: str, *, destination: str = "graveyard", reason: str = "countered") -> StackItem:
        item = next((candidate for candidate in self.state.stack if candidate.ref == value or candidate.stack_id == value), None)
        if item is None:
            raise GameRuleError(f"No stack object {value}")
        self.state.stack.remove(item)
        if item.card_object_id:
            card = self.state.cards[item.card_object_id]
            if card.zone == "stack":
                self.move_card(card.object_id, destination, reason=reason, log=False)
        self._log(None, "stack.counter", f"{item.ref} {item.label} was countered.", {"stack": item.ref, "destination": destination, "reason": reason}, importance=2)
        return item

    # ------------------------------------------------------------------
    # APNAP delegated choices during resolution
    # ------------------------------------------------------------------
    def _choice_options(self, seat: str, effect: Mapping[str, Any]) -> list[str]:
        zone = str(effect.get("zone") or "battlefield")
        card_type = str((effect.get("filter") or {}).get("type") or "").casefold()
        controller_only = bool((effect.get("filter") or {}).get("controlled", True))
        candidates: list[str] = []
        for object_id in self.state.players[seat].zones.get(zone, []):
            card = self.state.cards[object_id]
            if controller_only and zone == "battlefield" and card.controller != seat:
                continue
            if card_type and card_type not in str(self._effective_card_data(card).get("type_line") or "").casefold():
                continue
            candidates.append(card.ref)
        return candidates

    def _issue_apnap_choice(self, *, effect: Mapping[str, Any], continuation: Mapping[str, Any]) -> None:
        players_spec = effect.get("players", "all")
        if players_spec == "all":
            queue = self.apnap_order()
        elif players_spec == "opponents":
            actor = str(effect.get("actor") or self.state.stack[-1].controller)
            queue = [seat for seat in self.apnap_order() if seat != actor]
        else:
            queue = [seat for seat in players_spec if seat in self.active_seats]
        choice_state = {
            "queue": queue,
            "selected": {},
            "effect": dict(effect),
            "resume": dict(continuation),
        }
        self._issue_next_apnap_choice(choice_state)

    def _issue_next_apnap_choice(self, state: dict[str, Any]) -> None:
        queue = list(state["queue"])
        if not queue:
            self._apply_apnap_choices(state)
            return
        seat = queue[0]
        effect = state["effect"]
        options = self._choice_options(seat, effect)
        count = min(int(effect.get("count", 1)), len(options))
        self.permissions.issue(
            kind="choice.apnap",
            role="pilot",
            actors=[seat],
            allowed_actions=["choose"],
            payload_by_actor={
                seat: {
                    "prompt": str(effect.get("prompt") or "Choose card(s)"),
                    "count": count,
                    "options": options,
                    "prior_public_choices": dict(state["selected"]) if not effect.get("hidden") else {},
                }
            },
            continuation={"choice_state": state},
        )

    def _complete_apnap_choice(self, decision: Any) -> None:
        seat = decision.actors[0]
        state = dict(decision.continuation["choice_state"])
        response = decision.responses[seat]
        values = list(response.get("cards") or response.get("choices") or [])
        options = self._choice_options(seat, state["effect"])
        required = min(int(state["effect"].get("count", 1)), len(options))
        if len(values) != required:
            raise GameRuleError(f"{seat} must choose exactly {required} option(s)")
        refs: list[str] = []
        for value in values:
            card = self._resolve_object(seat, str(value), zones={str(state["effect"].get("zone") or "battlefield")})
            if card.ref not in options or card.ref in refs:
                raise GameRuleError("Invalid or duplicate APNAP choice")
            refs.append(card.ref)
        selected = dict(state["selected"])
        selected[seat] = refs
        queue = list(state["queue"])[1:]
        state["selected"] = selected
        state["queue"] = queue
        self._issue_next_apnap_choice(state)

    def _apply_apnap_choices(self, state: dict[str, Any]) -> None:
        effect = state["effect"]
        then = str(effect.get("then") or "sacrifice")
        # Choices were made in APNAP order, but the actions happen simultaneously.
        selected_objects: list[str] = []
        for refs in state["selected"].values():
            for ref in refs:
                card = next(card for card in self.state.cards.values() if card.ref == ref)
                selected_objects.append(card.object_id)
        origins = {oid: self.state.cards[oid].zone for oid in selected_objects}
        for object_id in selected_objects:
            if then == "sacrifice":
                self.move_card(object_id, "graveyard", reason="simultaneous APNAP sacrifice", log=False)
            elif then == "discard":
                self.move_card(object_id, "graveyard", reason="simultaneous APNAP discard", log=False)
            elif then == "exile":
                self.move_card(object_id, "exile", reason="simultaneous APNAP choice", log=False)
            else:
                raise GameRuleError(f"Unsupported APNAP continuation {then}")
        self._log(None, f"choice.{then}", f"Applied simultaneous {then} choices.", {"objects": [self.state.cards[oid].ref for oid in selected_objects], "origins": origins}, importance=2, changed_objects=selected_objects)
        resume = state["resume"]
        self._continue_resolution(
            stack_ref=str(resume["stack_ref"]),
            effects=[dict(item) for item in resume.get("effects", [])],
            destination=resume.get("destination"),
            note=str(resume.get("note") or ""),
        )

    # ------------------------------------------------------------------
    # Combat with multiple defenders
    # ------------------------------------------------------------------
    def _is_summoning_sick(self, card: CardInstance) -> bool:
        if "creature" not in str(self._effective_card_data(card).get("type_line") or "").casefold():
            return False
        return self.state.players[card.controller].turns_begun <= card.acquired_control_turn_count

    def _issue_attackers(self) -> None:
        active = self.state.active_player
        if active not in self.active_seats:
            self._advance_step()
            return
        candidates = []
        for oid in self.state.players[active].zones["battlefield"]:
            card = self.state.cards[oid]
            data = self._effective_card_data(card)
            if card.controller == active and not card.tapped and not card.phased_out and "creature" in str(data.get("type_line") or "").casefold():
                candidates.append({"id": card.ref, "name": self.display_name(oid), "sick": self._is_summoning_sick(card), "haste": "Haste" in data.get("keywords", [])})
        self.permissions.issue(
            kind="combat.attackers",
            role="pilot",
            actors=[active],
            allowed_actions=["attack"],
            payload_by_actor={active: {"candidates": candidates, "defenders": [seat for seat in self.active_seats if seat != active]}},
        )

    def _complete_attackers(self, decision: Any) -> None:
        active = decision.actors[0]
        response = decision.responses[active]
        declarations = response.get("attackers") or {}
        if isinstance(declarations, list):
            default_defender = response.get("defender")
            declarations = {value: default_defender for value in declarations}
        used: set[str] = set()
        for value, defender in dict(declarations).items():
            card = self._resolve_object(active, str(value), zones={"battlefield"}, controlled_only=True)
            if card.object_id in used:
                raise GameRuleError("A creature cannot be declared twice")
            if defender not in self.active_seats or defender == active:
                raise GameRuleError(f"Invalid defending player {defender}")
            data = self._effective_card_data(card)
            if "creature" not in str(data.get("type_line") or "").casefold():
                raise GameRuleError(f"{card.ref} is not a creature")
            if card.tapped:
                raise GameRuleError(f"{card.ref} is tapped")
            if self._is_summoning_sick(card) and "Haste" not in data.get("keywords", []):
                raise GameRuleError(f"{card.ref} is summoning sick")
            if "Vigilance" not in data.get("keywords", []):
                card.tapped = True
            card.attacking = str(defender)
            self.state.combat.attackers[card.object_id] = str(defender)
            used.add(card.object_id)
        self.state.combat.attackers_declared = True
        self.state.combat.defending_players = [seat for seat in self.apnap_order() if seat in set(self.state.combat.attackers.values())]
        self._log(active, "combat.attack", f"{active} attacked with {len(used)} creature(s).", {"attackers": {self.state.cards[oid].ref: defender for oid, defender in self.state.combat.attackers.items()}}, importance=2, changed_objects=list(used), changed_players=[active])
        self._grant_priority(active)

    def _begin_blocker_decisions(self) -> None:
        if not self.state.combat.attackers:
            self.state.combat.blockers_declared = True
            self._grant_priority(self.state.active_player)
            return
        self.state.combat.blocker_cursor = 0
        self._issue_next_blocker()

    def _issue_next_blocker(self) -> None:
        defenders = self.state.combat.defending_players
        if self.state.combat.blocker_cursor >= len(defenders):
            self.state.combat.blockers_declared = True
            self._grant_priority(self.state.active_player)
            return
        defender = defenders[self.state.combat.blocker_cursor]
        attackers = [self.state.cards[oid].ref for oid, target in self.state.combat.attackers.items() if target == defender]
        blockers = []
        for oid in self.state.players[defender].zones["battlefield"]:
            card = self.state.cards[oid]
            if card.controller != defender or card.tapped or card.phased_out:
                continue
            if "creature" in str(self._effective_card_data(card).get("type_line") or "").casefold():
                blockers.append(card.ref)
        self.permissions.issue(
            kind="combat.blockers",
            role="pilot",
            actors=[defender],
            allowed_actions=["block"],
            payload_by_actor={defender: {"attackers": attackers, "blockers": blockers}},
        )

    def _complete_blockers(self, decision: Any) -> None:
        defender = decision.actors[0]
        response = decision.responses[defender]
        assignments = dict(response.get("blocks") or {})  # blocker ref -> attacker ref
        used_blockers: set[str] = set()
        for blocker_value, attacker_value in assignments.items():
            blocker = self._resolve_object(defender, str(blocker_value), zones={"battlefield"}, controlled_only=True)
            attacker = self._resolve_object(defender, str(attacker_value), zones={"battlefield"})
            if blocker.object_id in used_blockers:
                raise GameRuleError("A blocker cannot block more than one attacker without an explicit rule")
            if attacker.object_id not in self.state.combat.attackers or self.state.combat.attackers[attacker.object_id] != defender:
                raise GameRuleError(f"{attacker.ref} is not attacking {defender}")
            if blocker.tapped or "creature" not in str(self._effective_card_data(blocker).get("type_line") or "").casefold():
                raise GameRuleError(f"{blocker.ref} cannot block")
            self.state.combat.blockers.setdefault(attacker.object_id, []).append(blocker.object_id)
            blocker.blocking = attacker.object_id
            used_blockers.add(blocker.object_id)
        self._log(defender, "combat.block", f"{defender} declared {len(used_blockers)} blocker(s).", {"blocks": {self.state.cards[b].ref: self.state.cards[a].ref for a, bs in self.state.combat.blockers.items() for b in bs if b in used_blockers}}, importance=2, changed_objects=list(used_blockers), changed_players=[defender])
        self.state.combat.blocker_cursor += 1
        self._issue_next_blocker()

    def _combat_is_simple(self) -> bool:
        for attacker_id, blockers in self.state.combat.blockers.items():
            data = self._effective_card_data(attacker_id)
            keywords = set(data.get("keywords") or [])
            if len(blockers) > 1 or keywords.intersection({"Trample", "First strike", "Double strike", "Deathtouch", "Lifelink"}):
                return False
        for blockers in self.state.combat.blockers.values():
            for blocker_id in blockers:
                keywords = set(self._effective_card_data(blocker_id).get("keywords") or [])
                if keywords.intersection({"First strike", "Double strike", "Deathtouch", "Lifelink"}):
                    return False
        return True

    def _begin_combat_damage(self) -> None:
        if self._combat_is_simple():
            assignments: list[dict[str, Any]] = []
            for attacker_id, defender in self.state.combat.attackers.items():
                power = self._numeric_stat(attacker_id, "power")
                blockers = self.state.combat.blockers.get(attacker_id, [])
                if not blockers:
                    assignments.append({"source": self.state.cards[attacker_id].ref, "target": defender, "amount": power})
                elif blockers:
                    assignments.append({"source": self.state.cards[attacker_id].ref, "target": self.state.cards[blockers[0]].ref, "amount": power})
                    blocker_power = self._numeric_stat(blockers[0], "power")
                    assignments.append({"source": self.state.cards[blockers[0]].ref, "target": self.state.cards[attacker_id].ref, "amount": blocker_power})
            self._apply_combat_assignments(assignments)
            self._grant_priority(self.state.active_player)
            return
        actors = unique_preserving_order([self.state.active_player, *self.state.combat.defending_players])
        self.permissions.issue(
            kind="combat.damage",
            role="pilot",
            actors=actors,
            allowed_actions=["assign_damage"],
            payload_by_actor={seat: {"combat": self._combat_payload(), "instruction": "Assign damage for sources you control."} for seat in actors},
            simultaneous=True,
        )

    def _complete_combat_damage(self, decision: Any) -> None:
        assignments: list[dict[str, Any]] = []
        for seat in decision.actors:
            for assignment in decision.responses[seat].get("assignments") or []:
                source = self._resolve_object(seat, str(assignment["source"]), zones={"battlefield"}, controlled_only=True)
                amount = int(assignment.get("amount", 0))
                if amount < 0:
                    raise GameRuleError("Damage cannot be negative")
                assignments.append({"source": source.ref, "target": assignment["target"], "amount": amount, "deathtouch": bool(assignment.get("deathtouch", False))})
        self._apply_combat_assignments(assignments)
        self._grant_priority(self.state.active_player)

    def _combat_payload(self) -> dict[str, Any]:
        return {
            "attackers": {self.state.cards[oid].ref: target for oid, target in self.state.combat.attackers.items()},
            "blockers": {self.state.cards[aid].ref: [self.state.cards[bid].ref for bid in bids] for aid, bids in self.state.combat.blockers.items()},
        }

    def _apply_combat_assignments(self, assignments: Sequence[Mapping[str, Any]]) -> None:
        changed_objects: list[str] = []
        changed_players: list[str] = []
        for assignment in assignments:
            source = next((card for card in self.state.cards.values() if card.ref == str(assignment["source"])), None)
            if source is None:
                raise GameRuleError(f"Unknown damage source {assignment['source']}")
            amount = int(assignment.get("amount", 0))
            target_value = str(assignment["target"])
            if target_value in self.state.players:
                target = self.state.players[target_value]
                target.life -= amount
                changed_players.append(target_value)
                if source.is_commander:
                    key = source.oracle_id
                    target.commander_damage_received[key] = target.commander_damage_received.get(key, 0) + amount
            else:
                target_card = next((card for card in self.state.cards.values() if card.ref == target_value), None)
                if target_card is None:
                    raise GameRuleError(f"Unknown combat target {target_value}")
                target_card.marked_damage += amount
                target_card.deathtouch_damage = target_card.deathtouch_damage or bool(assignment.get("deathtouch"))
                changed_objects.append(target_card.object_id)
        self.state.combat.damage_assignments.extend(dict(item) for item in assignments)
        self._log(None, "combat.damage", "Combat damage was dealt.", {"assignments": list(assignments)}, importance=2, changed_objects=changed_objects, changed_players=changed_players)
        self._stabilize()

    # ------------------------------------------------------------------
    # Cleanup, state-based actions, and player elimination
    # ------------------------------------------------------------------
    def _complete_cleanup_discard(self, decision: Any) -> None:
        seat = decision.actors[0]
        player = self.state.players[seat]
        values = list(decision.responses[seat].get("cards") or [])
        required = max(0, len(player.zones["hand"]) - player.max_hand_size)
        if len(values) != required:
            raise GameRuleError(f"{seat} must discard exactly {required} card(s)")
        objects: list[str] = []
        for value in values:
            card = self._resolve_object(seat, str(value), zones={"hand"}, owned_only=True)
            if card.object_id in objects:
                raise GameRuleError("Duplicate discard")
            objects.append(card.object_id)
        for object_id in objects:
            self.move_card(object_id, "graveyard", reason="cleanup discard", log=False)
        self._log(seat, "cleanup.discard", f"{seat} discarded {len(objects)} card(s) to maximum hand size.", {"objects": [self.state.cards[oid].ref for oid in objects]}, importance=1, changed_objects=objects, changed_players=[seat])
        self._finish_cleanup()

    def _numeric_stat(self, object_id: str, stat: str) -> int:
        card = self.state.cards[object_id]
        data = self._effective_card_data(card)
        raw = card.annotations.get(f"continuous_{stat}", data.get(stat))
        try:
            base = int(str(raw))
        except (TypeError, ValueError):
            return 0
        if stat == "toughness":
            base += card.counters.get("+1/+1", 0)
            base -= card.counters.get("-1/-1", 0)
        if stat == "power":
            base += card.counters.get("+1/+1", 0)
            base -= card.counters.get("-1/-1", 0)
        return base

    def _legend_groups(self) -> list[tuple[str, str, list[str]]]:
        groups: dict[tuple[str, str], list[str]] = {}
        for seat in self.active_seats:
            for object_id in self.state.players[seat].zones["battlefield"]:
                card = self.state.cards[object_id]
                if card.controller != seat:
                    continue
                data = self._effective_card_data(card)
                type_line = str(data.get("type_line") or "")
                if "legendary" not in type_line.casefold():
                    continue
                key = (seat, str(data.get("name") or card.printed_name))
                groups.setdefault(key, []).append(object_id)
        return [(seat, name, ids) for (seat, name), ids in groups.items() if len(ids) > 1]

    def _stabilize(self) -> bool:
        """Perform state-based actions until stable.

        Returns True when an external choice (currently the legend rule) or game
        end prevents priority from being granted.
        """
        for _ in range(100):
            if self.state.game_over:
                return True
            losers = []
            for seat in self.active_seats:
                player = self.state.players[seat]
                if player.life <= 0 or player.poison >= self.state.config.poison_to_lose or player.attempted_empty_draw:
                    losers.append(seat)
                    continue
                if any(value >= self.state.config.commander_damage_to_lose for value in player.commander_damage_received.values()):
                    losers.append(seat)
            if losers:
                self._eliminate_players(losers, reason="state-based loss")
                if self.state.game_over:
                    return True
                continue

            move_to_grave: list[str] = []
            for seat in self.active_seats:
                for object_id in list(self.state.players[seat].zones["battlefield"]):
                    card = self.state.cards[object_id]
                    data = self._effective_card_data(card)
                    type_line = str(data.get("type_line") or "").casefold()
                    keywords = set(data.get("keywords") or [])
                    if "creature" in type_line:
                        toughness = self._numeric_stat(object_id, "toughness")
                        if toughness <= 0:
                            move_to_grave.append(object_id)
                        elif (card.marked_damage >= toughness or card.deathtouch_damage) and "Indestructible" not in keywords:
                            move_to_grave.append(object_id)
                    elif "planeswalker" in type_line and card.counters.get("loyalty", 0) <= 0 and card.counters.get("loyalty_initialized"):
                        move_to_grave.append(object_id)
            if move_to_grave:
                for object_id in unique_preserving_order(move_to_grave):
                    if self.state.cards[object_id].zone == "battlefield":
                        self.move_card(object_id, "graveyard", reason="state-based action", log=False)
                self._log(None, "state.creatures_died", f"State-based actions moved {len(move_to_grave)} permanent(s) to graveyards.", {"objects": [self.state.cards[oid].ref for oid in move_to_grave]}, importance=2, changed_objects=move_to_grave)
                continue

            legends = self._legend_groups()
            if legends:
                seat, name, ids = legends[0]
                self.permissions.issue(
                    kind="state.legend",
                    role="pilot",
                    actors=[seat],
                    allowed_actions=["choose"],
                    payload_by_actor={seat: {"name": name, "keep_one": [self.state.cards[oid].ref for oid in ids]}},
                    continuation={"object_ids": ids},
                )
                return True
            return False
        raise StateInvariantError("State-based action loop did not stabilize")

    def _complete_legend_choice(self, decision: Any) -> None:
        seat = decision.actors[0]
        value = decision.responses[seat].get("card") or decision.responses[seat].get("keep")
        ids = list(decision.continuation["object_ids"])
        card = self._resolve_object(seat, str(value), zones={"battlefield"}, controlled_only=True)
        if card.object_id not in ids:
            raise GameRuleError("Legend choice must keep one of the listed permanents")
        moved = []
        for object_id in ids:
            if object_id != card.object_id and self.state.cards[object_id].zone == "battlefield":
                self.move_card(object_id, "graveyard", reason="legend rule", log=False)
                moved.append(object_id)
        self._log(seat, "state.legend", f"{seat} kept {card.ref}; {len(moved)} legendary permanent(s) went to graveyards.", {"kept": card.ref, "moved": [self.state.cards[oid].ref for oid in moved]}, importance=2, changed_objects=[card.object_id, *moved])
        self._stabilize()

    def _eliminate_players(self, seats: Sequence[str], *, reason: str) -> None:
        unique = [seat for seat in unique_preserving_order(seats) if seat in self.active_seats]
        if not unique:
            return
        for seat in unique:
            player = self.state.players[seat]
            player.in_game = False
            self.state.eliminated_players.append(seat)
            # Objects owned by the player leave the game.
            for card in list(self.state.cards.values()):
                if card.owner == seat and card.zone != "outside":
                    if card.zone == "stack":
                        self.state.stack = [item for item in self.state.stack if item.card_object_id != card.object_id]
                        card.zone = "outside"
                    else:
                        self.move_card(card.object_id, "outside", reason="owner left game", log=False)
            # A conservative baseline for ended control effects: surviving
            # objects owned by others return to their owners; any leftovers are
            # exiled. A compiled continuous-effect layer may refine this later.
            for card in list(self.state.cards.values()):
                if card.zone == "battlefield" and card.controller == seat and card.owner != seat:
                    owner = card.owner
                    if self.state.players[owner].in_game:
                        self.change_control(card.object_id, owner, reason="controller left game")
                    else:
                        self.move_card(card.object_id, "exile", reason="controller left game", log=False)
            self.state.stack = [item for item in self.state.stack if item.controller != seat or item.card_object_id is not None]
            self.state.extra_turns = [turn for turn in self.state.extra_turns if turn.player != seat]
            self.state.priority_passes = [passed for passed in self.state.priority_passes if passed != seat]
            self._log(seat, "player.eliminated", f"{seat} left the game: {reason}.", {"reason": reason}, importance=3, changed_players=[seat])

        remaining = self.active_seats
        if len(remaining) == 1:
            self.state.game_over = True
            self.state.winner = remaining[0]
            self.state.priority_player = None
            self.permissions.invalidate_current()
            self._log(remaining[0], "game.win", f"{remaining[0]} won the game.", importance=3, changed_players=remaining)
        elif not remaining:
            self.state.game_over = True
            self.state.draw = True
            self.state.priority_player = None
            self.permissions.invalidate_current()
            self._log(None, "game.draw", "All remaining players lost simultaneously.", importance=3)
        elif self.state.priority_player in unique:
            self.state.priority_player = self._next_active_after(unique[-1])

    # ------------------------------------------------------------------
    # Generic effect DSL used only by the arbiter/semantic executor
    # ------------------------------------------------------------------
    def apply_effect(self, effect: Mapping[str, Any], *, actor: str, as_cost: bool = False) -> Any:
        op = str(effect.get("op") or "").casefold()
        reason = str(effect.get("reason") or ("cost" if as_cost else "effect"))
        if op == "draw":
            return self.draw(str(effect.get("player") or actor), int(effect.get("count", 1)), reason=reason)
        if op in {"move", "sacrifice", "destroy", "exile", "bounce", "discard"}:
            card = self._resolve_object(actor, str(effect["card"]))
            destination = {
                "sacrifice": "graveyard",
                "destroy": "graveyard",
                "exile": "exile",
                "bounce": "hand",
                "discard": "graveyard",
            }.get(op, str(effect.get("destination") or "graveyard"))
            return self.move_card(card.object_id, destination, controller=effect.get("controller"), tapped=bool(effect.get("tapped", False)), reason=reason)
        if op == "damage":
            target = str(effect["target"])
            amount = int(effect.get("amount", 0))
            if target in self.state.players:
                self.state.players[target].life -= amount
                self._log(actor, "effect.damage", f"{target} took {amount} damage.", {"target": target, "amount": amount, "reason": reason}, importance=2, changed_players=[target])
            else:
                card = self._resolve_object(actor, target, zones={"battlefield"})
                card.marked_damage += amount
                card.deathtouch_damage = card.deathtouch_damage or bool(effect.get("deathtouch"))
                self._log(actor, "effect.damage", f"{card.ref} took {amount} damage.", {"target": card.ref, "amount": amount, "reason": reason}, importance=2, changed_objects=[card.object_id])
            return amount
        if op == "life":
            seat = str(effect.get("player") or actor)
            delta = int(effect.get("delta", 0))
            self.state.players[seat].life += delta
            self._log(actor, "effect.life", f"{seat}'s life changed by {delta}.", {"player": seat, "delta": delta}, importance=1, changed_players=[seat])
            return self.state.players[seat].life
        if op == "energy":
            seat = str(effect.get("player") or actor)
            delta = int(effect.get("delta", 0))
            self.state.players[seat].energy += delta
            self._log(actor, "effect.energy", f"{seat}'s energy changed by {delta}.", {"player": seat, "delta": delta}, importance=1, changed_players=[seat])
            return self.state.players[seat].energy
        if op == "counter_stack":
            return self._counter_stack_item(str(effect["stack"]), destination=str(effect.get("destination") or "graveyard"), reason=reason).ref
        if op == "extra_turn":
            return self.schedule_extra_turn(str(effect.get("player") or actor), source=str(effect.get("source") or reason)).turn_id
        if op == "delayed_trigger":
            source = effect.get("source")
            source_id = None
            if source:
                source_id = self._resolve_object(actor, str(source)).object_id
            return self.schedule_delayed_trigger(
                controller=str(effect.get("controller") or actor),
                label=str(effect["label"]),
                event_kind=str(effect.get("event") or "step.begin"),
                condition=dict(effect.get("condition") or {}),
                stack_template=dict(effect.get("stack") or {}),
                source_object_id=source_id,
                once=bool(effect.get("once", True)),
                expires_turn_sequence=effect.get("expires_turn_sequence"),
            ).ref
        if op == "create_token":
            return self.create_token(
                str(effect.get("controller") or actor),
                name=str(effect.get("name") or "Token"),
                quantity=int(effect.get("quantity", 1)),
                tapped=bool(effect.get("tapped", False)),
                attacking=effect.get("attacking"),
                copy_of=effect.get("copy_of"),
                characteristics=dict(effect.get("characteristics") or {}),
                temporary_keywords=list(effect.get("temporary_keywords") or []),
                reason=reason,
            )
        if op == "tap" or op == "untap":
            card = self._resolve_object(actor, str(effect["card"]), zones={"battlefield"})
            card.tapped = op == "tap"
            self._log(actor, f"permanent.{op}", f"{card.ref} was {op}ped.", {"object": card.ref, "reason": reason}, importance=1, changed_objects=[card.object_id])
            return card.ref
        if op == "counter":
            card = self._resolve_object(actor, str(effect["card"]), zones={"battlefield"})
            name = str(effect.get("counter") or "+1/+1")
            delta = int(effect.get("delta", 1))
            card.counters[name] = card.counters.get(name, 0) + delta
            self._log(actor, "permanent.counter", f"{card.ref} {name} changed by {delta}.", {"object": card.ref, "counter": name, "delta": delta}, importance=1, changed_objects=[card.object_id])
            return card.counters[name]
        if op == "look_top":
            seat = str(effect.get("player") or actor)
            viewer = str(effect.get("viewer") or actor)
            count = int(effect.get("count", 1))
            ids = list(reversed(self.state.players[seat].zones["library"][-count:]))
            for oid in ids:
                card = self.state.cards[oid]
                card.known_to = sorted(set(card.known_to).union({viewer}))
            self._log(actor, "library.look", f"{viewer} looked at the top {len(ids)} card(s) of {seat}'s library.", {"player": seat, "count": len(ids)}, visibility=[viewer, "analyst"], importance=1, changed_objects=ids)
            return [self.state.cards[oid].ref for oid in ids]
        if op == "reorder_top":
            seat = str(effect.get("player") or actor)
            viewer = str(effect.get("viewer") or actor)
            values = list(effect.get("cards") or [])  # top-first
            ids = [self._resolve_object(viewer, str(value), zones={"library"}).object_id for value in values]
            library = self.state.players[seat].zones["library"]
            if any(oid not in library or viewer not in self.state.cards[oid].known_to for oid in ids):
                raise GameRuleError("Can only reorder known cards currently in that library")
            for oid in ids:
                library.remove(oid)
            # Internal library order stores top at the end.
            library.extend(reversed(ids))
            self._log(actor, "library.reorder", f"{viewer} reordered {len(ids)} known top cards.", {"count": len(ids)}, visibility=[viewer, "analyst"], importance=1, changed_objects=ids)
            return [self.state.cards[oid].ref for oid in ids]
        if op == "change_control":
            card = self._resolve_object(actor, str(effect["card"]), zones={"battlefield"})
            self.change_control(card.object_id, str(effect["controller"]), reason=reason)
            return card.ref
        if op == "note":
            self._log(actor, "rules.note", str(effect.get("text") or ""), {"reason": reason}, visibility=["arbiter", "analyst"], importance=0)
            return None
        raise GameRuleError(f"Unsupported effect operation {op!r}")

    def create_token(
        self,
        controller: str,
        *,
        name: str,
        quantity: int = 1,
        tapped: bool = False,
        attacking: str | None = None,
        copy_of: str | None = None,
        characteristics: Mapping[str, Any] | None = None,
        temporary_keywords: Sequence[str] = (),
        reason: str = "token effect",
    ) -> list[str]:
        self._require_seat(controller, in_game=True)
        created: list[str] = []
        for _ in range(quantity):
            if copy_of:
                original = self._resolve_object(controller, str(copy_of), zones={"battlefield"})
                oracle_id = original.oracle_id
                printed_name = name or self.display_name(original.object_id)
                annotations = copy.deepcopy(original.annotations)
                annotations["copied_from"] = original.object_id
                overrides = dict(annotations.get("copy_overrides") or {})
                if name:
                    overrides["name"] = name
                overrides.update(dict(characteristics or {}))
                annotations["copy_overrides"] = overrides
            else:
                ref = self._next_ref("T")
                try:
                    record = self.card_db.lookup(name)
                    oracle_id = record.oracle_id
                    printed_name = record.name
                except KeyError:
                    oracle_id = f"custom-token:{self._stable_runtime_id('token-oracle', ref)}"
                    printed_name = name
                annotations = {"token_characteristics": dict(characteristics or {})}
            if copy_of:
                ref = self._next_ref("T")
            object_id = self._stable_runtime_id("token-object", ref)
            card = CardInstance(
                object_id=object_id,
                ref=ref,
                oracle_id=oracle_id,
                printed_name=printed_name,
                owner=controller,
                controller=controller,
                zone="battlefield",
                is_token=True,
                tapped=tapped,
                temporary_keywords=list(temporary_keywords),
                annotations=annotations,
                acquired_control_turn_count=self.state.players[controller].turns_begun,
                entered_battlefield_turn_sequence=self.state.turn_sequence,
                known_to=list(self.seats),
                revealed_to=list(self.seats),
                attacking=attacking,
            )
            self.state.cards[object_id] = card
            self.state.players[controller].zones["battlefield"].append(object_id)
            if attacking:
                self.state.combat.attackers[object_id] = attacking
            created.append(object_id)
        self._log(controller, "token.create", f"{controller} created {quantity} {name} token(s).", {"objects": [self.state.cards[oid].ref for oid in created], "reason": reason}, importance=1, changed_objects=created, changed_players=[controller])
        return [self.state.cards[oid].ref for oid in created]

    def change_control(self, object_id: str, new_controller: str, *, reason: str = "") -> None:
        self._require_seat(new_controller, in_game=True)
        card = self.state.cards[object_id]
        if card.zone != "battlefield":
            raise GameRuleError("Only battlefield permanents have controllers")
        old = card.controller
        self.state.players[old].zones["battlefield"].remove(object_id)
        self.state.players[new_controller].zones["battlefield"].append(object_id)
        card.controller = new_controller
        card.acquired_control_turn_count = self.state.players[new_controller].turns_begun
        self._log(None, "control.change", f"Control of {card.ref} changed {old} → {new_controller}.", {"object": card.ref, "from": old, "to": new_controller, "reason": reason}, importance=2, changed_objects=[object_id], changed_players=[old, new_controller])

    # ------------------------------------------------------------------
    # Safe testing helper
    # ------------------------------------------------------------------
    def advance_until(self, phase: str, step: str, *, max_transitions: int = 100) -> None:
        target = (phase, step)
        if target not in TURN_STEPS:
            raise ValueError(f"Unknown turn step {target}; valid values are {TURN_STEPS}")
        for _ in range(max_transitions):
            if (self.state.phase, self.state.step) == target:
                return
            if self.state.pending_decision is not None:
                raise GameRuleError(f"Cannot auto-advance through pending {self.state.pending_decision.kind}")
            if self.state.priority_player is not None:
                raise GameRuleError("Cannot auto-pass live priority; submit explicit pass/yield decisions")
            self._advance_step()
        raise GameRuleError(f"Did not reach {target} within {max_transitions} transitions")
