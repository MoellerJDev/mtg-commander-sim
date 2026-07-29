from __future__ import annotations

import copy
import hashlib
import random
import re
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
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
from .targets import (
    TargetGroup,
    TargetPlan,
    available_modes,
    mode_effects,
    target_plan,
)
from .util import (
    mana_cost_to_vector,
    normalize_mana_bundle,
    parse_mana_symbols,
    pay_mana_from_pool,
    stable_json,
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
        self._semantic_trust_cache: dict[tuple[str, str], bool] = {}
        self._assert_invariants()

    def semantic_program_is_current_trusted(
        self,
        program: SemanticProgram | None,
    ) -> bool:
        if program is None or program.trust_level != "trusted":
            return False
        program_hash = hashlib.sha256(
            stable_json(program.to_dict()).encode("utf-8")
        ).hexdigest()
        cache_key = (program.key, program_hash)
        cached = self._semantic_trust_cache.get(cache_key)
        if cached is not None:
            return cached
        if not program.oracle_id:
            self._semantic_trust_cache[cache_key] = False
            return False
        try:
            record = self.card_db.by_oracle_id(program.oracle_id)
        except KeyError:
            self._semantic_trust_cache[cache_key] = False
            return False
        oracle_hash = hashlib.sha256(
            record.oracle_text.encode("utf-8")
        ).hexdigest()
        rulings_hash = hashlib.sha256(
            stable_json(
                sorted(
                    (
                        asdict(ruling)
                        for ruling in self.card_db.rulings(record)
                    ),
                    key=lambda row: (
                        str(row["published_at"]),
                        str(row["source"]),
                        str(row["comment"]),
                        str(row["oracle_id"]),
                    ),
                )
            ).encode("utf-8")
        ).hexdigest()
        result = (
            program.provenance.get("source_oracle_hash")
            == oracle_hash
            and program.provenance.get("source_rulings_hash")
            == rulings_hash
        )
        self._semantic_trust_cache[cache_key] = result
        return result

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
        if config.semantic_policy not in {
            "arbitrate_or_pause",
            "trusted_only",
        }:
            raise ValueError(
                f"Unsupported semantic policy {config.semantic_policy!r}"
            )
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
                "keywords": list(
                    card.annotations.get("token_characteristics", {}).get(
                        "keywords", []
                    )
                ),
                "colors": list(
                    card.annotations.get("token_characteristics", {}).get(
                        "colors", []
                    )
                ),
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
                "colors": list(record.colors),
                "produced_mana": list(record.produced_mana),
            }
        overrides = dict(card.annotations.get("copy_overrides") or {})
        base.update({key: copy.deepcopy(value) for key, value in overrides.items() if key in base or key in {"name", "type_line", "power", "toughness", "oracle_text", "mana_value", "mana_cost", "colors"}})
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
        semantic_events: bool = False,
    ) -> CardInstance:
        if destination not in {"library", "hand", "battlefield", "graveyard", "exile", "command", "outside"}:
            raise GameRuleError(f"Unsupported destination {destination}")
        card = self.state.cards[object_id]
        origin = card.zone
        origin_controller = card.controller
        origin_data = (
            copy.deepcopy(self._effective_card_data(card))
            if semantic_events
            else {}
        )
        departure_sources = (
            self._semantic_event_sources()
            if semantic_events and origin == "battlefield"
            else []
        )
        departure_source_zones = {
            source.object_id: source.zone for source in departure_sources
        }
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
        if semantic_events:
            self._dispatch_zone_change_events(
                card,
                origin=origin,
                destination=destination,
                origin_controller=origin_controller,
                origin_data=origin_data,
                departure_sources=departure_sources,
                departure_source_zones=departure_source_zones,
                reason=reason,
            )
        return card

    def _semantic_event_sources(
        self,
        *,
        zones: set[str] | None = None,
    ) -> list[CardInstance]:
        """Return cards whose visible zone can host a semantic event handler.

        Library cards are deliberately excluded.  Hand handlers are allowed so
        long as their semantic program explicitly declares ``active_zone=hand``;
        the resulting trigger remains controlled and visible through the normal
        projected stack protocol.
        """

        active_zones = zones or {
            "battlefield",
            "graveyard",
            "exile",
            "command",
            "hand",
        }
        return [
            card
            for card in self.state.cards.values()
            if card.zone in active_zones
            and (card.controller in self.active_seats or card.owner in self.active_seats)
        ]

    def _dispatch_zone_change_events(
        self,
        card: CardInstance,
        *,
        origin: str,
        destination: str | None,
        origin_controller: str,
        origin_data: Mapping[str, Any],
        departure_sources: Sequence[CardInstance],
        departure_source_zones: Mapping[str, str],
        reason: str,
        trigger_batch: list[StackItem] | None = None,
    ) -> None:
        """Emit normalized semantic events for one authoritative zone change.

        Departure handlers receive the battlefield source set and active zones
        captured before the move.  That last-known-information snapshot is what
        lets a permanent see itself die or leave while still keeping the actual
        zone mutation atomic from the perspective of effect resolution.
        """

        owns_trigger_batch = trigger_batch is None
        event_triggers = trigger_batch if trigger_batch is not None else []
        origin_types, _, _ = self._type_parts(
            str(origin_data.get("type_line") or "")
        )
        event_destination = destination or card.zone
        common = {
            "card": card.ref,
            "owner": card.owner,
            "controller": card.controller,
            "previous_controller": origin_controller,
            "from": origin,
            "to": event_destination,
            "reason": reason,
            "token": card.is_token,
        }
        if origin == "battlefield" and event_destination != "battlefield":
            departure_context = {
                **common,
                "controller": origin_controller,
                "types": sorted(origin_types),
            }
            for event in (
                "permanent.leave",
                *(
                    ("creature.dies",)
                    if event_destination == "graveyard" and "creature" in origin_types
                    else ()
                ),
                *(
                    ("artifact.graveyard",)
                    if event_destination == "graveyard" and "artifact" in origin_types
                    else ()
                ),
                *(("permanent.graveyard",) if event_destination == "graveyard" else ()),
            ):
                self._dispatch_semantic_event(
                    event,
                    departure_context,
                    sources=departure_sources,
                    source_zones=departure_source_zones,
                    trigger_batch=event_triggers,
                )
        if origin == "graveyard" and event_destination != "graveyard":
            self._dispatch_semantic_event(
                "card.leave_graveyard",
                common,
                trigger_batch=event_triggers,
            )
        if origin == "hand" and event_destination == "graveyard":
            self._dispatch_semantic_event(
                "card.discarded",
                common,
                trigger_batch=event_triggers,
            )
        if event_destination != "battlefield" or origin == "battlefield":
            if owns_trigger_batch:
                self._enqueue_semantic_trigger_batch(event_triggers)
            return
        entered_data = self._effective_card_data(card)
        entered_types, _, _ = self._type_parts(
            str(entered_data.get("type_line") or "")
        )
        entered_context = {
            **common,
            "controller": card.controller,
            "types": sorted(entered_types),
            "tapped": card.tapped,
        }
        self._dispatch_semantic_event(
            "permanent.enter",
            entered_context,
            trigger_batch=event_triggers,
        )
        for card_type in ("artifact", "creature", "land", "enchantment"):
            if card_type in entered_types:
                self._dispatch_semantic_event(
                    f"{card_type}.enter",
                    entered_context,
                    trigger_batch=event_triggers,
                )
        if owns_trigger_batch:
            self._enqueue_semantic_trigger_batch(event_triggers)

    def _move_cards_simultaneously(
        self,
        changes: Sequence[tuple[str, str]],
        *,
        reason: str,
        log: bool = False,
    ) -> list[CardInstance]:
        """Move a set of objects before emitting any resulting trigger event."""

        sources = self._semantic_event_sources()
        source_zones = {source.object_id: source.zone for source in sources}
        snapshots: list[
            tuple[CardInstance, str, str, dict[str, Any], str]
        ] = []
        for object_id, destination in changes:
            card = self.state.cards[object_id]
            snapshots.append(
                (
                    card,
                    card.zone,
                    card.controller,
                    copy.deepcopy(self._effective_card_data(card)),
                    destination,
                )
            )
            self.move_card(
                object_id,
                destination,
                reason=reason,
                log=log,
                semantic_events=False,
            )
        trigger_batch: list[StackItem] = []
        for (
            card,
            origin,
            origin_controller,
            origin_data,
            destination,
        ) in snapshots:
            self._dispatch_zone_change_events(
                card,
                origin=origin,
                destination=destination,
                origin_controller=origin_controller,
                origin_data=origin_data,
                departure_sources=sources,
                departure_source_zones=source_zones,
                reason=reason,
                trigger_batch=trigger_batch,
            )
        self._enqueue_semantic_trigger_batch(trigger_batch)
        return [card for card, *_ in snapshots]

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
            draw_tracker = player.stats.setdefault("cards_drawn_by_turn", {})
            turn_key = str(self.state.turn_sequence)
            before_count = int(draw_tracker.get(turn_key, 0))
            draw_tracker[turn_key] = before_count + len(drawn)
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
            if before_count < 2 <= before_count + len(drawn):
                self._dispatch_semantic_event(
                    "card.second_draw",
                    {
                        "player": seat,
                        "objects": [
                            self.state.cards[object_id].ref
                            for object_id in drawn
                        ],
                    },
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
        elif kind == "semantic.target":
            self._complete_semantic_target(decision)
        elif kind == "semantic.choice":
            self._complete_semantic_choice(decision)
        elif kind == "semantic.search":
            self._complete_semantic_search(decision)
        elif kind == "semantic.storm":
            self._complete_storm_choice(decision)
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
        if player.yield_policy.mode != "none":
            self._increment_optimization(
                entry.player, "yields_invalidated_by_phase"
            )
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
        self._dispatch_semantic_event(
            "step.begin",
            {"phase": phase, "step": step, "player": active},
        )
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

    def _issue_priority(
        self, seat: str, hints: Mapping[str, Any] | None = None
    ) -> Any:
        hints = dict(hints or self._priority_action_hints(seat))
        payload = {
            "stack": [{"id": item.ref, "label": item.label, "controller": item.controller} for item in reversed(self.state.stack)],
            "legal": hints,
            "yield_modes": ["none", "until_public_change", "until_my_turn", "auto_if_no_response"],
        }
        return self.permissions.issue(
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
        signature = self.meaningful_action_signature(seat)
        self.state.players[seat].yield_policy = YieldPolicy(
            mode=mode,
            created_revision=self.state.revision,
            created_event_sequence=self.state.event_sequence,
            created_turn_sequence=self.state.turn_sequence,
            created_priority_epoch=self.state.priority_epoch,
            created_active_player=self.state.active_player,
            created_phase=self.state.phase,
            created_step=self.state.step,
            created_land_plays_remaining=self.state.players[
                seat
            ].land_plays_remaining,
            action_signature=signature,
            stack_signature=self._stack_signature(),
            note="Pilot-issued priority yield",
        )

    @staticmethod
    def _signature_hash(value: Any) -> str:
        return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()

    def _stack_signature(self) -> str:
        return self._signature_hash(
            [
                {
                    "ref": item.ref,
                    "kind": item.kind,
                    "controller": item.controller,
                    "source": item.source_object_id,
                    "card": item.card_object_id,
                    "semantic": item.semantic_key,
                    "targets": item.targets,
                    "modes": item.modes,
                    "x": item.x_value,
                }
                for item in self.state.stack
            ]
        )

    def meaningful_action_signature(
        self,
        seat: str,
        hints: Mapping[str, Any] | None = None,
    ) -> str:
        """Hash the currently executable strategic choices visible to ``seat``.

        Ordinary tap-for-mana actions are deliberately absent. They are payment
        mechanics for the cast/activation choices that do appear here and must
        not turn every empty priority pass into an LLM task.
        """

        hints = dict(hints or self._priority_action_hints(seat))
        meaningful_actions = []
        ordinary_mana_ids = {
            f"activate:{item['s']}:{item['a']}"
            for item in hints.get("mana_abilities", [])
            if item not in hints.get("abilities", [])
        }
        for action in hints.get("actions", []):
            if action.get("id") == "pass" or action.get("id") in ordinary_mana_ids:
                continue
            meaningful_actions.append(copy.deepcopy(action))
        payload: dict[str, Any] = {
            "algorithm": "meaningful-action-signature/v1",
            "actions": sorted(
                meaningful_actions,
                key=lambda item: stable_json(item),
            ),
        }
        decision = self.state.pending_decision
        if decision is not None and seat in decision.actors:
            payload["mandatory_or_optional_choice"] = {
                "kind": decision.kind,
                "allowed": list(decision.allowed_actions),
                "context": copy.deepcopy(decision.payload_by_actor.get(seat, {})),
            }
        return self._signature_hash(payload)

    def _optimization_stats(self, seat: str) -> dict[str, Any]:
        telemetry = self.state.players[seat].stats.setdefault(
            "decision_optimization", {}
        )
        for key in (
            "priority_windows_considered",
            "pass_only_windows_skipped",
            "yield_covered_windows",
            "suppressed_empty_windows",
            "suppressed_meaningful_windows",
            "yields_invalidated_by_phase",
            "yields_invalidated_by_draw",
            "yields_invalidated_by_action_change",
            "yields_invalidated_by_stack",
            "yields_invalidated_by_public_change",
            "illegal_target_actions_prevented",
            "illegal_target_actions_advertised",
            "actions_removed_for_no_targets",
            "actions_removed_for_mode_target_failure",
            "target_candidates_generated",
            "target_submissions_rejected",
            "targets_became_illegal_on_resolution",
            "spells_countered_by_rules",
            "spells_countered_by_effect",
            "stack_interaction_windows_created",
            "stack_interaction_windows_auto_passed",
        ):
            telemetry.setdefault(key, 0)
        return telemetry

    def _increment_optimization(self, seat: str, key: str) -> None:
        telemetry = self._optimization_stats(seat)
        telemetry[key] = int(telemetry.get(key, 0)) + 1

    def _yield_stop_reason(
        self, seat: str, action_signature: str | None = None
    ) -> str | None:
        policy = self.state.players[seat].yield_policy
        if policy.mode == "none":
            return "none"
        if (
            policy.stop_phase is not None
            and self.state.phase == policy.stop_phase
            and (
                policy.stop_step is None
                or self.state.step == policy.stop_step
            )
        ):
            return "phase"
        if self.state.active_player == seat and (
            policy.created_active_player != seat
            or policy.created_turn_sequence != self.state.turn_sequence
            or policy.created_priority_epoch != self.state.priority_epoch
            or (
                self.state.phase
                in {"precombat_main", "postcombat_main"}
                and (
                    policy.created_phase != self.state.phase
                    or policy.created_step != "main"
                )
            )
        ):
            return "phase"
        if policy.mode == "until_my_turn" and self.state.active_player == seat:
            return "phase"
        if policy.stack_signature != self._stack_signature():
            return "stack"
        stack_codes = {
            "stack.cast",
            "stack.activate",
            "stack.trigger",
            "stack.resolve",
            "stack.counter",
        }
        public_codes = {
            "land.play",
            "zone.move",
            "card.draw.private",
            "token.create",
            "control.change",
            "player.eliminated",
            "permanent.untap",
        }
        for event in self.state.events:
            if event.event_id <= policy.created_event_sequence:
                continue
            if event.code == "card.draw.private":
                if seat in event.visibility:
                    return "draw"
                continue
            if event.code in stack_codes:
                return "stack"
            if event.code == "zone.move":
                details = event.details
                if (
                    seat in event.changed_players
                    and (
                        details.get("from") == "hand"
                        or details.get("to") == "hand"
                    )
                ):
                    return "action_change"
                return "public_change"
            if event.code in public_codes:
                return (
                    "action_change"
                    if event.code == "permanent.untap"
                    and seat in event.changed_players
                    else "public_change"
                )
        if (
            policy.created_land_plays_remaining
            != self.state.players[seat].land_plays_remaining
        ):
            return "action_change"
        current_signature = action_signature or self.meaningful_action_signature(
            seat
        )
        if policy.action_signature != current_signature:
            return "action_change"
        if policy.mode == "auto_if_no_response" and self._signature_has_actions(
            seat
        ):
            return "action_change"
        return None

    def _yield_stopped(self, seat: str) -> bool:
        return self._yield_stop_reason(seat) is not None

    def _has_conservative_response(self, seat: str) -> bool:
        player = self.state.players[seat]
        for object_id in player.zones["hand"]:
            record = self.card_record(object_id)
            if record and (record.is_instant or record.has_flash):
                return True
        return bool(self._ability_hints(seat))

    def _can_auto_pass(
        self,
        seat: str,
        *,
        action_signature: str,
        meaningful: bool,
    ) -> tuple[bool, str | None]:
        policy = self.state.players[seat].yield_policy
        if policy.mode == "none":
            return False, None
        reason = self._yield_stop_reason(seat, action_signature)
        if reason is not None:
            self.state.players[seat].yield_policy = YieldPolicy()
            if reason != "none":
                self._increment_optimization(
                    seat, f"yields_invalidated_by_{reason}"
                )
            return False, reason
        if policy.mode == "auto_if_no_response" and meaningful:
            self.state.players[seat].yield_policy = YieldPolicy()
            self._increment_optimization(
                seat, "yields_invalidated_by_action_change"
            )
            return False, "action_change"
        return True, None

    def _signature_has_actions(
        self, seat: str, hints: Mapping[str, Any] | None = None
    ) -> bool:
        hints = dict(hints or self._priority_action_hints(seat))
        return any(
            hints.get(key) for key in ("cast", "lands", "abilities")
        )

    def _record_action_opportunity(
        self,
        seat: str,
        *,
        hints: Mapping[str, Any],
        action_signature: str,
        outcome: str,
        yield_invalidation: str | None = None,
    ) -> dict[str, Any]:
        self.state.opportunity_sequence += 1
        meaningful_ids = [
            action["id"]
            for action in hints.get("actions", [])
            if action.get("id") != "pass"
            and action.get("kind") != "mana"
            and (
                action.get("kind") != "activate"
                or any(
                    item.get("s") == action.get("source")
                    and item.get("a") == action.get("ability")
                    for item in hints.get("abilities", [])
                )
            )
        ]
        diagnostics = copy.deepcopy(hints.get("diagnostic") or {})
        meaningful = bool(meaningful_ids)
        row = {
                "sequence": self.state.opportunity_sequence,
                "revision": self.state.revision,
                "event_sequence": self.state.event_sequence,
                "turn_sequence": self.state.turn_sequence,
                "active_player": self.state.active_player,
                "phase": self.state.phase,
                "step": self.state.step,
                "priority_epoch": self.state.priority_epoch,
                "seat": seat,
                "action_signature": action_signature,
                "action_signature_algorithm": "meaningful-action-signature/v1",
                "meaningful_action_ids": meaningful_ids,
                "meaningful_action_count": len(meaningful_ids),
                "meaningful_actions_exist": meaningful,
                "pilot_task_issued": outcome == "pilot_task_issued",
                "safe_yield_covered": outcome == "safe_yield",
                "pass_only_auto_pass": outcome == "pass_only_auto_pass",
                "ordered_plan_covered": outcome == "ordered_plan",
                "incorrectly_suppressed": outcome
                == "incorrectly_suppressed",
                "outcome": outcome,
                "yield_invalidated_by": yield_invalidation,
                "diagnostic": diagnostics,
            }
        self.state.action_opportunities.append(row)
        return row

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
            if (
                self.state.game_over
                or self.state.pending_decision is not None
                or self._semantic_pause_annotation() is not None
            ):
                return
            if not self.state.started:
                return
            if self.state.priority_player is not None:
                seat = self.state.priority_player
                hints = self._priority_action_hints(seat)
                action_signature = self.meaningful_action_signature(
                    seat, hints
                )
                meaningful = self._signature_has_actions(seat, hints)
                self._increment_optimization(
                    seat, "priority_windows_considered"
                )
                if self.state.stack:
                    self._increment_optimization(
                        seat,
                        (
                            "stack_interaction_windows_created"
                            if meaningful
                            else "stack_interaction_windows_auto_passed"
                        ),
                    )
                can_yield, invalidation = self._can_auto_pass(
                    seat,
                    action_signature=action_signature,
                    meaningful=meaningful,
                )
                if (
                    self.state.config.auto_pass_empty_priority
                    and not meaningful
                ):
                    self._increment_optimization(
                        seat, "pass_only_windows_skipped"
                    )
                    self._increment_optimization(
                        seat, "suppressed_empty_windows"
                    )
                    self._record_action_opportunity(
                        seat,
                        hints=hints,
                        action_signature=action_signature,
                        outcome="pass_only_auto_pass",
                        yield_invalidation=invalidation,
                    )
                    self._pass_priority(seat, automatic=True)
                    continue
                if can_yield:
                    self._increment_optimization(
                        seat, "yield_covered_windows"
                    )
                    self._record_action_opportunity(
                        seat,
                        hints=hints,
                        action_signature=action_signature,
                        outcome="safe_yield",
                    )
                    self._pass_priority(seat, automatic=True)
                    continue
                row = self._record_action_opportunity(
                    seat,
                    hints=hints,
                    action_signature=action_signature,
                    outcome="pilot_task_issued",
                    yield_invalidation=invalidation,
                )
                decision = self._issue_priority(seat, hints)
                row["decision_id"] = decision.decision_id
                return
            # Step handlers normally either advance or grant priority. Re-enter
            # only as a fail-safe for a loaded state between transitions.
            self._enter_step()
        raise StateInvariantError("Automatic transition limit exceeded")

    def _semantic_pause_annotation(self) -> dict[str, Any] | None:
        return next(
            (
                annotation
                for annotation in reversed(self.state.annotations)
                if annotation.get("kind") == "semantic_unsupported"
                and annotation.get("active", True)
            ),
            None,
        )

    def _pause_for_unsupported_semantic(
        self,
        *,
        item: StackItem | None = None,
        program: SemanticProgram | None = None,
        event: str | None = None,
        source: CardInstance | None = None,
    ) -> None:
        if self._semantic_pause_annotation() is not None:
            return
        label = (
            item.label
            if item is not None
            else source.printed_name
            if source is not None
            else "unsupported material semantic"
        )
        semantic_key = (
            item.semantic_key
            if item is not None
            else program.key
            if program is not None
            else None
        )
        trust_level = (
            program.trust_level if program is not None else "unresolved"
        )
        if (
            program is not None
            and program.trust_level == "trusted"
            and not self.semantic_program_is_current_trusted(program)
        ):
            trust_level = "source_hash_drift"
        annotation = {
            "kind": "semantic_unsupported",
            "active": True,
            "label": label,
            "semantic_key": semantic_key,
            "trust_level": trust_level,
            "stack": item.ref if item is not None else None,
            "event": event,
            "turn_sequence": self.state.turn_sequence,
            "phase": self.state.phase,
            "step": self.state.step,
            "semantic_policy": self.state.config.semantic_policy,
        }
        self.state.annotations.append(annotation)
        self.state.priority_player = None
        self._log(
            None,
            "fidelity.semantic_unsupported",
            (
                f"Paused before resolving material behavior for {label} "
                "under trusted-only semantic policy."
            ),
            annotation,
            importance=3,
        )

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
            if isinstance(expected, (list, tuple, set)):
                if context.get(key) not in expected:
                    return False
                continue
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
        semantic_batch_id = decision.continuation.get(
            "semantic_trigger_batch_id"
        )
        if semantic_batch_id:
            batch = next(
                (
                    value
                    for value in self.state.pending_trigger_batches
                    if value.get("batch_id") == semantic_batch_id
                ),
                None,
            )
            if batch is None or not batch.get("groups"):
                raise GameRuleError(
                    "Semantic trigger batch is no longer pending"
                )
            group = batch["groups"][0]
            if group.get("controller") != controller:
                raise GameRuleError(
                    "Only the trigger controller may order this group"
                )
            items = list(group.get("items") or [])
            by_ref = {
                str(item["ref"]): item
                for item in items
            }
            refs = [str(value) for value in values]
            if sorted(refs) != sorted(by_ref):
                raise GameRuleError(
                    "Trigger order must contain every listed trigger "
                    "exactly once"
                )
            self._place_semantic_trigger_items(
                [by_ref[ref] for ref in refs]
            )
            batch["groups"] = list(batch["groups"])[1:]
            if self._begin_pending_semantic_trigger_batch():
                return
            self._grant_priority(self.state.active_player)
            return
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
            context=copy.deepcopy(dict(template.get("context") or {})),
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
            mana_abilities = [
                ability
                for ability in self._activated_abilities(card)
                if ability.mana_ability and card.zone in ability.zones
            ]
            if mana_abilities and not any(
                self._activation_condition_status(seat, ability)[0] == "payable"
                for ability in mana_abilities
            ):
                # A source whose only Oracle mana abilities have an unmet or
                # unresolved activation condition must not make dependent
                # spells appear payable.
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
            mana_abilities = [
                ability
                for ability in self._activated_abilities(card)
                if ability.mana_ability and card.zone in ability.zones
            ]
            if mana_abilities and not any(
                self._activation_condition_status(seat, ability)[0] == "payable"
                for ability in mana_abilities
            ):
                raise GameRuleError(
                    f"{card.printed_name}'s mana ability has an unmet or unresolved activation condition"
                )
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
        *,
        exclude_sources: set[str] | None = None,
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        activations: list[dict[str, Any]] = []
        pay_mode = response.get("pay", "auto")
        if pay_mode == "auto":
            plan = auto_plan_payment(
                requirements,
                [
                    source
                    for source in self.available_mana_sources(seat)
                    if source.object_id not in (exclude_sources or set())
                ],
                allow_conditional=(
                    bool(response.get("allow_conditional_mana", False))
                    and not self.state.config.strict_mana
                ),
                reserve=normalize_mana_bundle(response.get("reserve")),
                starting_pool=self.state.players[seat].mana_pool,
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
        controlled_type = re.search(
            r"enters (?:the battlefield )?tapped unless you control an? "
            r"(plains|island|swamp|mountain|forest)",
            oracle,
        )
        if controlled_type:
            required_type = controlled_type.group(1)
            return not any(
                required_type
                in str(
                    self._effective_card_data(oid).get("type_line") or ""
                ).casefold()
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
        self.move_card(
            card.object_id,
            "battlefield",
            controller=seat,
            tapped=tapped,
            reason="land play",
            log=False,
            semantic_events=True,
        )
        player.land_plays_remaining -= 1
        self._log(
            seat,
            "land.play",
            f"{seat} played {card.ref} {card.printed_name}{' tapped' if tapped else ''}.",
            {
                "object": card.ref,
                "tapped": tapped,
                "life_paid": 2 if response.get("pay_life") else 0,
            },
            importance=2,
            changed_objects=[card.object_id],
            changed_players=[seat],
        )
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

    @staticmethod
    def _trusted_generic_spell(record: CardRecord) -> bool:
        """Whether this permanent resolves entirely through closed core rules."""

        if not record.is_permanent_spell:
            return False
        oracle = record.oracle_text.casefold()
        if not oracle.strip():
            return True
        return bool(
            record.produced_mana
            and not any(
                marker in oracle
                for marker in (
                    "when ",
                    "whenever ",
                    "at the beginning",
                    "instead",
                    "sacrifice another",
                )
            )
        )

    def _cast(self, seat: str, response: Mapping[str, Any]) -> None:
        self._check_priority(seat)
        if response.get("semantic_key") is not None:
            raise GameRuleError(
                "Pilots cannot select semantic program identifiers"
            )
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
        semantic_key = str(
            f"{record.oracle_id}:spell:"
            f"{str(face.get('name')) if face else 'front'}"
        )
        program = self.semantics.get(semantic_key)
        selected_cost_option: dict[str, Any] | None = None
        target_schema_override: dict[str, Any] | None = None
        if declared_cost and self.state.config.strict_mana:
            printed_options, _ = self._compiled_printed_cost_options(
                seat,
                card,
                x_value=(
                    int(response["x"])
                    if response.get("x") is not None
                    else None
                ),
                hint=False,
            )
            supplied = {
                "GENERIC": int(declared_cost.get("GENERIC", 0))
                + commander_tax
            }
            supplied.update(
                {
                    color: int(declared_cost.get(color, 0))
                    for color in "WUBRGC"
                }
            )
            if not any(
                supplied == self._mana_vector(option["requirements"])
                for option in printed_options
            ):
                authoritative = [
                    self._mana_vector(option["requirements"])
                    for option in printed_options
                ]
                raise GameRuleError(
                    f"Pilot-declared casting cost {supplied} does not match "
                    f"authoritative cost {authoritative}."
                )
        options = self._cast_cost_options(
            seat,
            card,
            program,
            response=response,
            hint=False,
        )
        if options:
            requested_option = str(
                response.get("cost_option")
                or (
                    "normal"
                    if any(option["id"] == "normal" for option in options)
                    else options[0]["id"]
                    if len(options) == 1
                    else ""
                )
            )
            selected_cost_option = next(
                (
                    option
                    for option in options
                    if option["id"] == requested_option
                ),
                None,
            )
            if selected_cost_option is None:
                raise GameRuleError(
                    "The selected casting-cost option is not currently legal "
                    "and payable"
                )
            requirements = self._mana_vector(
                selected_cost_option["requirements"]
            )
            if "target_schema" in selected_cost_option:
                target_schema_override = copy.deepcopy(
                    dict(selected_cost_option["target_schema"])
                )
        elif self.state.config.strict_mana:
            raise GameRuleError(
                f"{card.printed_name} has no currently payable compiled "
                f"casting cost ({mana_cost})."
            )
        elif declared_cost:
            requirements = {
                "GENERIC": int(declared_cost.get("GENERIC", 0))
            }
            for color in "WUBRGC":
                requirements[color] = int(declared_cost.get(color, 0))
            requirements["GENERIC"] += commander_tax
        else:
            raise GameRuleError(
                f"Supply declared_cost for {card.printed_name} in "
                "non-strict mode."
            )
        if declared_cost and self.state.config.strict_mana:
            supplied = {"GENERIC": int(declared_cost.get("GENERIC", 0)) + commander_tax}
            supplied.update({color: int(declared_cost.get(color, 0)) for color in "WUBRGC"})
            if supplied != requirements:
                raise GameRuleError(
                    f"Pilot-declared casting cost {supplied} does not match authoritative cost {requirements}."
                )
        selected_modes = [str(value) for value in response.get("modes") or []]
        validated_targets, target_groups = self._validate_semantic_targets(
            seat,
            program,
            list(response.get("targets") or []),
            modes=selected_modes,
            source_ref=card.ref,
            target_schema=target_schema_override,
        )
        target_snapshots = {
            ref: self._target_snapshot(ref) for ref in validated_targets
        }
        tap_cost_cards: list[CardInstance] = []
        if selected_cost_option is not None:
            for tap_ref in selected_cost_option.get(
                "selected_tap_cost_cards", []
            ):
                tap_card = self._resolve_object(
                    seat,
                    str(tap_ref),
                    zones={"battlefield"},
                    controlled_only=True,
                )
                if tap_card.tapped:
                    raise GameRuleError(
                        f"{tap_card.ref} is no longer available for a tap cost"
                    )
                tap_cost_cards.append(tap_card)
        spent, activations = self._pay_for_cost(
            seat,
            requirements,
            response,
            exclude_sources={
                tap_card.object_id for tap_card in tap_cost_cards
            },
        )
        for tap_card in tap_cost_cards:
            tap_card.tapped = True
            self._log(
                seat,
                "cost.tap",
                f"{seat} tapped {tap_card.ref} to help cast "
                f"{card.printed_name}.",
                {
                    "spell": card.ref,
                    "object": tap_card.ref,
                    "cost_option": selected_cost_option["id"],
                },
                importance=1,
                changed_objects=[tap_card.object_id],
                changed_players=[seat],
            )
        deferred_cost_events: list[
            tuple[CardInstance, str, str, dict[str, Any]]
        ] = []
        deferred_cost_sources: list[CardInstance] = []
        deferred_cost_source_zones: dict[str, str] = {}
        paid_additional_refs: list[str] = []
        if selected_cost_option is not None:
            selected_exile = selected_cost_option.get(
                "selected_exile_card"
            )
            if selected_exile:
                exiled = self._resolve_object(
                    seat,
                    str(selected_exile),
                    zones={"hand"},
                    owned_only=True,
                )
                self.move_card(
                    exiled.object_id,
                    "exile",
                    reason=f"{card.printed_name} alternate cost",
                    semantic_events=True,
                )
            for additional in selected_cost_option.get(
                "additional_costs", []
            ):
                if additional.get("kind") == "life_x":
                    life_paid = int(response.get("x", 0))
                    if life_paid > self.state.players[seat].life:
                        raise GameRuleError(
                            "The selected life payment is no longer payable"
                        )
                    self.state.players[seat].life -= life_paid
                    self._log(
                        seat,
                        "cost.life",
                        f"{seat} paid {life_paid} life to cast "
                        f"{card.printed_name}.",
                        {
                            "object": card.ref,
                            "amount": life_paid,
                            "cost_option": selected_cost_option["id"],
                        },
                        importance=1,
                        changed_players=[seat],
                    )
            selected_additional = list(
                selected_cost_option.get("selected_additional_costs", [])
            )
            if selected_additional:
                deferred_cost_sources = self._semantic_event_sources()
                deferred_cost_source_zones = {
                    source.object_id: source.zone
                    for source in deferred_cost_sources
                }
                changes: list[
                    tuple[CardInstance, str, str, dict[str, Any], str]
                ] = []
                for selected in selected_additional:
                    kind = str(selected["kind"])
                    zone = "hand" if kind == "discard" else "battlefield"
                    for ref_value in selected.get("cards", []):
                        paid_card = self._resolve_object(
                            seat,
                            str(ref_value),
                            zones={zone},
                            controlled_only=zone == "battlefield",
                            owned_only=zone != "battlefield",
                        )
                        changes.append(
                            (
                                paid_card,
                                paid_card.zone,
                                paid_card.controller,
                                copy.deepcopy(
                                    self._effective_card_data(paid_card)
                                ),
                                kind,
                            )
                        )
                for (
                    paid_card,
                    paid_origin,
                    paid_controller,
                    paid_data,
                    kind,
                ) in changes:
                    self.move_card(
                        paid_card.object_id,
                        "graveyard",
                        reason=f"{card.printed_name} {kind} cost",
                        semantic_events=False,
                    )
                    paid_additional_refs.append(paid_card.ref)
                    deferred_cost_events.append(
                        (
                            paid_card,
                            paid_origin,
                            paid_controller,
                            paid_data,
                        )
                    )
                    self._log(
                        seat,
                        f"cost.{kind}",
                        f"{seat} paid {paid_card.ref} as a {kind} cost.",
                        {
                            "spell": card.ref,
                            "object": paid_card.ref,
                        },
                        importance=1,
                        changed_objects=[paid_card.object_id],
                        changed_players=[seat],
                    )
        origin = card.zone
        self._remove_from_zone(card)
        card.zone = "stack"
        card.controller = seat
        card.active_face = str(face.get("name")) if face else None
        default_destination = "battlefield" if any(word in type_line.casefold() for word in ("artifact", "battle", "creature", "enchantment", "planeswalker")) else "graveyard"
        ref = self._next_ref("S")
        item = StackItem(
            stack_id=self._stable_runtime_id("stack", ref),
            ref=ref,
            kind="spell",
            controller=seat,
            label=card.active_face or record.name,
            card_object_id=card.object_id,
            semantic_key=semantic_key,
            targets=validated_targets,
            modes=selected_modes,
            x_value=response.get("x"),
            chosen_face=card.active_face,
            notes=str(response.get("note") or ""),
            default_destination=default_destination,
            visibility=list(self.seats),
            context={
                "target_groups": target_groups,
                "target_snapshots": target_snapshots,
                "targets_revalidated": False,
                "targets_chosen_at_creation": True,
                "cost_option": (
                    selected_cost_option["id"]
                    if selected_cost_option
                    else "normal"
                ),
                **(
                    {"target_schema_override": target_schema_override}
                    if target_schema_override is not None
                    else {}
                ),
                **(
                    {
                        "cast_option_effects": copy.deepcopy(
                            list(
                                selected_cost_option.get("effects", [])
                            )
                        )
                    }
                    if selected_cost_option
                    and "effects" in selected_cost_option
                    else {}
                ),
            },
        )
        self.state.stack.append(item)
        if program and "storm" in program.coverage:
            prior_spells = sum(
                event.code == "stack.cast"
                and event.turn_sequence == self.state.turn_sequence
                for event in self.state.events
            )
            storm_ref = self._next_ref("S")
            storm_item = StackItem(
                stack_id=self._stable_runtime_id("stack", storm_ref),
                ref=storm_ref,
                kind="triggered_ability",
                controller=seat,
                label=f"{item.label} — Storm",
                source_object_id=card.object_id,
                semantic_key="builtin:storm",
                visibility=list(self.seats),
                context={
                    "copy_count": prior_spells,
                    "copy_template": {
                        "label": item.label,
                        "controller": item.controller,
                        "semantic_key": item.semantic_key,
                        "targets": copy.deepcopy(item.targets),
                        "modes": copy.deepcopy(item.modes),
                        "x_value": item.x_value,
                        "target_groups": copy.deepcopy(target_groups),
                        "target_snapshots": copy.deepcopy(
                            target_snapshots
                        ),
                        "target_schema": copy.deepcopy(
                            self._stack_target_schema(item, program)
                        ),
                    },
                },
            )
            self.state.stack.append(storm_item)
            self._log(
                seat,
                "stack.trigger",
                f"Queued {storm_item.ref}: {storm_item.label}.",
                {
                    "stack": storm_item.ref,
                    "source_stack": item.ref,
                    "copy_count": prior_spells,
                },
                importance=2,
            )
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
                "modes": item.modes,
                "x": item.x_value,
                "commander_tax": commander_tax,
                "cost_option": item.context["cost_option"],
                "exiled_for_cost": (
                    selected_cost_option.get("selected_exile_card")
                    if selected_cost_option
                    else None
                ),
                "additional_cost_objects": paid_additional_refs,
                "tap_cost_objects": [
                    tap_card.ref for tap_card in tap_cost_cards
                ],
            },
            importance=2,
            changed_objects=[card.object_id],
            changed_players=[seat],
        )
        for (
            paid_card,
            paid_origin,
            paid_controller,
            paid_data,
        ) in deferred_cost_events:
            self._dispatch_zone_change_events(
                paid_card,
                origin=paid_origin,
                destination="graveyard",
                origin_controller=paid_controller,
                origin_data=paid_data,
                departure_sources=deferred_cost_sources,
                departure_source_zones=deferred_cost_source_zones,
                reason=f"{card.printed_name} additional cost",
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
                self.move_card(
                    card.object_id,
                    destination,
                    reason="activated ability cost",
                    semantic_events=True,
                )
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
        if response.get("semantic_key") is not None:
            raise GameRuleError(
                "Pilots cannot select semantic program identifiers"
            )
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
        availability, availability_reason = self._ability_availability(
            seat, source, ability
        )
        if availability != "payable":
            raise GameRuleError(
                f"{source.printed_name} {ability.ability_id} is not currently payable"
                + (f": {availability_reason}" if availability_reason else "")
            )
        if self.state.config.strict_mana and any(
            key in response for key in ("mana_cost", "declared_cost", "costs", "cost_effects", "tap")
        ):
            raise GameRuleError(
                "Pilot-supplied activation costs are disabled in strict mode; select the Oracle ability and cost objects only."
            )
        if ability.sorcery_speed:
            self._sorcery_timing(seat)

        candidate_semantic_key = (
            f"{source.oracle_id}:ability:{ability.ability_id}"
        )
        target_program = self.semantics.get(candidate_semantic_key)
        selected_modes = [str(value) for value in response.get("modes") or []]
        validated_targets, target_groups = self._validate_semantic_targets(
            seat,
            target_program,
            list(response.get("targets") or []),
            modes=selected_modes,
            source_ref=source.ref,
        )
        target_snapshots = {
            ref: self._target_snapshot(ref) for ref in validated_targets
        }
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
        if ability.energy_payment:
            if self.state.players[seat].energy < ability.energy_payment:
                raise GameRuleError(
                    "Cannot pay more energy than the player has"
                )
            self.state.players[seat].energy -= ability.energy_payment

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
            self.move_card(
                source.object_id,
                "graveyard",
                reason="activated ability cost",
                semantic_events=True,
            )
        elif ability.sacrifice_source:
            if source.zone != "battlefield":
                raise GameRuleError("Sacrifice-source cost requires the source on the battlefield")
            self.move_card(
                source.object_id,
                "graveyard",
                reason="activated ability cost",
                semantic_events=True,
            )
        elif ability.exile_source:
            self.move_card(
                source.object_id,
                "exile",
                reason="activated ability cost",
                semantic_events=True,
            )

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
            "builtin:fetch_land"
            if builtin_context
            else candidate_semantic_key
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
            targets=validated_targets,
            modes=selected_modes,
            notes=str(response.get("note") or ""),
            visibility=list(self.seats),
            context={
                **builtin_context,
                "target_groups": target_groups,
                "target_snapshots": target_snapshots,
                "targets_revalidated": False,
                "targets_chosen_at_creation": True,
            },
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
                "modes": item.modes,
                "life_paid": ability.life_payment,
                "energy_paid": ability.energy_payment,
            },
            importance=2,
            changed_objects=[source.object_id, *paid_objects],
            changed_players=[seat],
        )
        self.state.priority_player = seat
        self.state.priority_passes = []
        self.state.players[seat].yield_policy = YieldPolicy()

    def _ability_choice_payable(
        self,
        seat: str,
        source: CardInstance,
        ability: ActivatedAbility,
    ) -> bool:
        slots: list[list[str]] = []
        player = self.state.players[seat]
        for choice in ability.choices:
            candidates: list[str] = []
            for object_id in player.zones.get(choice.zone, []):
                card = self.state.cards[object_id]
                if choice.zone == "battlefield":
                    if card.controller != seat or card.phased_out:
                        continue
                elif card.owner != seat:
                    continue
                if choice.another and card.object_id == source.object_id:
                    continue
                if choice.card_type:
                    type_line = str(
                        self._effective_card_data(card).get("type_line") or ""
                    ).casefold()
                    if choice.card_type not in type_line:
                        continue
                candidates.append(card.object_id)
            for _ in range(choice.count):
                slots.append(candidates)

        def assign(index: int, used: set[str]) -> bool:
            if index >= len(slots):
                return True
            for object_id in slots[index]:
                if object_id in used:
                    continue
                used.add(object_id)
                if assign(index + 1, used):
                    return True
                used.remove(object_id)
            return False

        return assign(0, set())

    def _ability_availability(
        self,
        seat: str,
        card: CardInstance,
        ability: ActivatedAbility,
    ) -> tuple[str, str | None]:
        """Return payable, unpayable, unresolved, or unavailable."""

        player = self.state.players[seat]
        zone = card.zone
        if zone not in ability.zones:
            return "unavailable", "wrong_zone"
        if not ability.compiled_cost:
            return "unresolved", "unresolved_cost_semantics"
        if (
            not ability.mana_ability
            and self._nonmana_ability_prohibited_by_name(card)
        ):
            return "unavailable", "named_ability_prohibition"
        condition_status, condition_reason = self._activation_condition_status(
            seat, ability
        )
        if condition_status != "payable":
            return condition_status, condition_reason
        if ability.sorcery_speed and not (
            seat == self.state.active_player
            and not self.state.stack
            and (self.state.phase, self.state.step)
            in {
                ("precombat_main", "main"),
                ("postcombat_main", "main"),
            }
        ):
            return "unavailable", "sorcery_timing"
        if ability.tap_source:
            if zone != "battlefield":
                return "unavailable", "tap_cost_wrong_zone"
            if card.tapped:
                return "unavailable", "source_tapped"
            if (
                self._is_summoning_sick(card)
                and "Haste"
                not in self._effective_card_data(card).get("keywords", [])
            ):
                return "unavailable", "summoning_sickness"
        if ability.untap_source and (
            zone != "battlefield" or not card.tapped
        ):
            return "unavailable", "untap_cost_unavailable"
        if ability.discard_source and zone != "hand":
            return "unavailable", "discard_source_wrong_zone"
        if ability.sacrifice_source and zone != "battlefield":
            return "unavailable", "sacrifice_source_wrong_zone"
        if ability.life_payment and player.life < ability.life_payment:
            return "unpayable", "insufficient_life"
        if (
            ability.energy_payment
            and player.energy < ability.energy_payment
        ):
            return "unpayable", "insufficient_energy"
        if ability.choices and not self._ability_choice_payable(
            seat, card, ability
        ):
            return "unpayable", "mandatory_cost_object_unavailable"
        requirements = reduced_requirements(
            ability,
            legendary_creatures=self._legendary_creatures_controlled(seat),
        )
        excluded = {card.object_id} if ability.tap_source else set()
        if sum(requirements.values()) and not self._cost_is_affordable(
            seat, requirements, exclude_sources=excluded
        ):
            return "unpayable", "insufficient_mana"
        return "payable", None

    def _nonmana_ability_prohibited_by_name(
        self,
        source: CardInstance,
    ) -> bool:
        source_name = str(
            self._effective_card_data(source).get("name")
            or source.printed_name
        ).casefold()
        for seat in self.active_seats:
            for object_id in self.state.players[seat].zones["battlefield"]:
                permanent = self.state.cards[object_id]
                chosen_name = str(
                    permanent.annotations.get("chosen_name") or ""
                ).casefold()
                if not chosen_name or chosen_name != source_name:
                    continue
                oracle = str(
                    self._effective_card_data(permanent).get("oracle_text")
                    or ""
                ).casefold()
                if (
                    "activated abilities of sources with the chosen name "
                    "can't be activated unless they're mana abilities"
                    in oracle
                ):
                    return True
        return False

    def _activation_condition_status(
        self,
        seat: str,
        ability: ActivatedAbility,
    ) -> tuple[str, str | None]:
        """Evaluate the small compiled activation-condition grammar.

        Conditions outside this grammar are unresolved rather than guessed.
        This deliberately covers Metalcraft-style minimum-permanent checks
        without claiming general Oracle condition support.
        """

        effect = ability.effect_text.casefold()
        if "activate only if" not in effect:
            return "payable", None
        match = re.search(
            r"activate only if you control "
            r"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten) "
            r"or more (?P<kind>artifacts?|creatures?|lands?)",
            effect,
        )
        if not match:
            return "unresolved", "unresolved_activation_condition"
        words = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        raw_count = match.group("count")
        required = int(raw_count) if raw_count.isdigit() else words[raw_count]
        kind = match.group("kind").removesuffix("s")
        controlled = 0
        for object_id in self.state.players[seat].zones["battlefield"]:
            permanent = self.state.cards[object_id]
            if permanent.controller != seat or permanent.phased_out:
                continue
            type_line = str(
                self._effective_card_data(permanent).get("type_line") or ""
            ).casefold()
            if kind in type_line:
                controlled += 1
        if controlled < required:
            return "unavailable", f"requires_{required}_{kind}s"
        return "payable", None

    def _classified_ability_hints(
        self, seat: str
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        player = self.state.players[seat]
        strategic: list[dict[str, Any]] = []
        mana: list[dict[str, Any]] = []
        unpayable: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
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
                    hint = ability.compact(source_ref=card.ref, zone=zone)
                    status, reason = self._ability_availability(
                        seat, card, ability
                    )
                    if status == "unresolved":
                        unresolved.append(
                            {
                                **hint,
                                "status": status,
                                "reason": reason,
                            }
                        )
                        continue
                    if status == "unpayable":
                        unpayable.append(
                            {
                                **hint,
                                "status": status,
                                "reason": reason,
                            }
                        )
                        continue
                    if status != "payable":
                        continue
                    # Ordinary tap-for-one mana abilities do not justify an LLM
                    # call. Mana abilities with sacrifices, life payments, or
                    # other strategic costs remain visible so the player can
                    # float mana before a subsequent action (for example,
                    # Phyrexian Tower).
                    ordinary_mana = ability.mana_ability and not (
                        ability.choices
                        or ability.life_payment
                        or ability.energy_payment
                        or ability.discard_source
                        or ability.sacrifice_source
                        or ability.exile_source
                        or ability.uncompiled_costs
                    )
                    fetch_types = self._fetch_land_types(ability.effect_text)
                    if fetch_types:
                        hint["search_types"] = list(fetch_types)
                    if ability.mana_ability:
                        mana.append(hint)
                    if not ordinary_mana:
                        strategic.append(hint)
        return strategic, mana, unpayable, unresolved

    def _ability_hints(self, seat: str) -> list[dict[str, Any]]:
        strategic, _, _, _ = self._classified_ability_hints(seat)
        return strategic

    def _mana_ability_hints(self, seat: str) -> list[dict[str, Any]]:
        _, mana, _, _ = self._classified_ability_hints(seat)
        return mana

    def _cost_is_affordable(
        self,
        seat: str,
        requirements: Mapping[str, int],
        *,
        exclude_sources: set[str] | None = None,
    ) -> bool:
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
            sources = [
                source
                for source in self.available_mana_sources(seat)
                if source.object_id not in (exclude_sources or set())
            ]
            auto_plan_payment(remaining, sources)
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

    @staticmethod
    def _mana_vector(value: Mapping[str, Any] | None) -> dict[str, int]:
        return {
            key: int((value or {}).get(key, 0))
            for key in ("GENERIC", "W", "U", "B", "R", "G", "C")
        }

    def _controls_commander(self, seat: str) -> bool:
        return any(
            self.state.cards[object_id].controller == seat
            and self.state.cards[object_id].is_commander
            for object_id in self.state.players[seat].zones["battlefield"]
        )

    def _alternate_cost_condition_met(
        self,
        seat: str,
        condition: Mapping[str, Any],
    ) -> bool:
        if condition.get("not_your_turn") and self.state.active_player == seat:
            return False
        if condition.get("your_turn") and self.state.active_player != seat:
            return False
        if condition.get("control_commander") and not self._controls_commander(
            seat
        ):
            return False
        return True

    def _exile_cost_candidates(
        self,
        seat: str,
        source: CardInstance,
        specification: Mapping[str, Any],
    ) -> list[str]:
        colors = {
            str(value).upper()
            for value in specification.get("colors_any", [])
        }
        candidates: list[str] = []
        for object_id in self.state.players[seat].zones["hand"]:
            card = self.state.cards[object_id]
            if (
                specification.get("exclude_source", True)
                and card.object_id == source.object_id
            ):
                continue
            record = self.card_record(card)
            if record is None:
                continue
            if colors and not colors.intersection(
                {str(value).upper() for value in record.colors}
            ):
                continue
            candidates.append(card.ref)
        return candidates

    def _additional_cost_candidates(
        self,
        seat: str,
        source: CardInstance,
        specification: Mapping[str, Any],
    ) -> list[str]:
        kind = str(specification.get("kind") or "")
        zone = str(
            specification.get("zone")
            or ("hand" if kind == "discard" else "battlefield")
        )
        types = {
            str(value).casefold()
            for value in (
                specification.get("types_any")
                or (
                    [specification["card_type"]]
                    if specification.get("card_type")
                    else []
                )
            )
        }
        candidates: list[str] = []
        for object_id in self.state.players[seat].zones.get(zone, []):
            card = self.state.cards[object_id]
            if zone == "battlefield":
                if card.controller != seat or card.phased_out:
                    continue
            elif card.owner != seat:
                continue
            if (
                specification.get("exclude_source")
                or specification.get("another")
            ) and card.object_id == source.object_id:
                continue
            if types:
                card_types, _, _ = self._type_parts(
                    str(
                        self._effective_card_data(card).get("type_line")
                        or ""
                    )
                )
                if not types.intersection(card_types):
                    continue
            candidates.append(card.ref)
        return candidates

    def _payment_mechanic_candidates(
        self,
        seat: str,
        mechanic: str,
    ) -> list[CardInstance]:
        candidates: list[CardInstance] = []
        for object_id in self.state.players[seat].zones["battlefield"]:
            card = self.state.cards[object_id]
            if (
                card.controller != seat
                or card.phased_out
                or card.tapped
            ):
                continue
            types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if mechanic == "convoke" and "creature" in types:
                candidates.append(card)
            elif mechanic == "improvise" and "artifact" in types:
                candidates.append(card)
        return candidates

    def _convoke_reduction(
        self,
        requirements: Mapping[str, int],
        cards: Sequence[CardInstance],
    ) -> dict[str, int] | None:
        remaining = self._mana_vector(requirements)
        if len(cards) > sum(remaining.values()):
            return None
        card_colors = [
            [
                str(color).upper()
                for color in self._effective_card_data(card).get("colors", [])
                if (
                    str(color).upper() in "WUBRG"
                    and len(str(color)) == 1
                )
            ]
            for card in cards
        ]
        keys = ("GENERIC", "W", "U", "B", "R", "G", "C")

        def assign(
            index: int,
            values: tuple[int, ...],
        ) -> tuple[int, ...] | None:
            if index >= len(card_colors):
                return values
            state = dict(zip(keys, values))
            choices = [
                color
                for color in card_colors[index]
                if state[color] > 0
            ]
            if state["GENERIC"] > 0:
                choices.append("GENERIC")
            for choice in unique_preserving_order(choices):
                next_state = dict(state)
                next_state[choice] -= 1
                result = assign(
                    index + 1,
                    tuple(next_state[key] for key in keys),
                )
                if result is not None:
                    return result
            return None

        result = assign(
            0,
            tuple(remaining[key] for key in keys),
        )
        if result is None:
                return None
        return dict(zip(keys, result))

    def _tap_payment_plan(
        self,
        seat: str,
        requirements: Mapping[str, int],
        mechanic: str,
        candidates: Sequence[CardInstance],
    ) -> tuple[dict[str, int], list[CardInstance]] | None:
        """Find a payable minimum-card convoke or improvise plan."""

        base = self._mana_vector(requirements)
        best: tuple[dict[str, int], list[CardInstance]] | None = None

        def search(
            index: int,
            selected: list[CardInstance],
        ) -> None:
            nonlocal best
            if best is not None and len(selected) >= len(best[1]):
                return
            if mechanic == "convoke":
                reduced = self._convoke_reduction(base, selected)
            else:
                reduced = self._mana_vector(base)
                if len(selected) > reduced["GENERIC"]:
                    return
                reduced["GENERIC"] -= len(selected)
            if reduced is None:
                return
            excluded = {card.object_id for card in selected}
            if self._cost_is_affordable(
                seat,
                reduced,
                exclude_sources=excluded,
            ):
                best = (reduced, list(selected))
                return
            if index >= len(candidates):
                return
            search(index + 1, selected)
            selected.append(candidates[index])
            search(index + 1, selected)
            selected.pop()

        search(0, [])
        return best

    def _cost_payment_mechanics(
        self,
        record: CardRecord,
        schema: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        declared = schema.get("payment_mechanics") or []
        mechanics = [
            dict(value) if isinstance(value, Mapping) else {"kind": str(value)}
            for value in declared
        ]
        declared_kinds = {
            str(value.get("kind") or "").casefold()
            for value in mechanics
        }
        keyword_values = {
            str(value).casefold() for value in record.keywords
        }
        oracle = record.oracle_text.casefold()
        if "convoke" in keyword_values and "convoke" not in declared_kinds:
            mechanics.append({"kind": "convoke"})
        if "improvise" in keyword_values and "improvise" not in declared_kinds:
            mechanics.append({"kind": "improvise"})
        if (
            "affinity" in keyword_values
            and "affinity" not in declared_kinds
            and "affinity for artifacts" in oracle
        ):
            mechanics.append(
                {"kind": "affinity", "card_type": "artifact"}
            )
        return mechanics

    def _compiled_printed_cost(
        self,
        seat: str,
        card: CardInstance,
        *,
        x_value: int | None,
        hint: bool,
    ) -> tuple[dict[str, int] | None, bool]:
        record = self.card_record(card)
        if record is None:
            return None, False

    def _compiled_printed_cost_options(
        self,
        seat: str,
        card: CardInstance,
        *,
        x_value: int | None,
        hint: bool,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Expand an ordinary or hybrid printed cost into exact alternatives."""

        record = self.card_record(card)
        if record is None:
            return [], False
        variants = [self._mana_vector(None)]
        has_x = False
        for symbol in parse_mana_symbols(record.mana_cost):
            if symbol.isdigit():
                for variant in variants:
                    variant["GENERIC"] += int(symbol)
                continue
            if symbol in "WUBRGC" and len(symbol) == 1:
                for variant in variants:
                    variant[symbol] += 1
                continue
            if symbol == "X":
                has_x = True
                if x_value is None and not hint:
                    raise GameRuleError(
                        f"Casting {record.name} requires an explicit X value"
                    )
                selected_x = 0 if x_value is None else int(x_value)
                if selected_x < 0:
                    raise GameRuleError("X cannot be negative")
                for variant in variants:
                    variant["GENERIC"] += selected_x
                continue
            hybrid = symbol.split("/")
            if len(hybrid) == 2 and all(
                part in "WUBRGC" and len(part) == 1
                for part in hybrid
            ):
                expanded: list[dict[str, int]] = []
                for variant in variants:
                    for color in hybrid:
                        choice = self._mana_vector(variant)
                        choice[color] += 1
                        expanded.append(choice)
                variants = expanded
                continue
            two_hybrid = symbol.split("/")
            if (
                len(two_hybrid) == 2
                and "2" in two_hybrid
                and any(
                    part in "WUBRGC" and len(part) == 1
                    for part in two_hybrid
                )
            ):
                color = next(part for part in two_hybrid if part != "2")
                expanded = []
                for variant in variants:
                    generic_choice = self._mana_vector(variant)
                    generic_choice["GENERIC"] += 2
                    expanded.append(generic_choice)
                    color_choice = self._mana_vector(variant)
                    color_choice[color] += 1
                    expanded.append(color_choice)
                variants = expanded
                continue
            return [], has_x
        commander_tax = (
            2
            * self.state.players[seat].commander_casts.get(card.oracle_id, 0)
            if card.zone == "command" and card.is_commander
            else 0
        )
        unique: list[dict[str, int]] = []
        seen: set[tuple[int, ...]] = set()
        for variant in variants:
            variant["GENERIC"] += commander_tax
            identity = tuple(
                variant[key]
                for key in ("GENERIC", "W", "U", "B", "R", "G", "C")
            )
            if identity not in seen:
                seen.add(identity)
                unique.append(variant)
        return [
            {
                "id": "normal" if len(unique) == 1 else f"hybrid-{index}",
                "kind": "mana" if len(unique) == 1 else "hybrid",
                "requirements": variant,
            }
            for index, variant in enumerate(unique, start=1)
        ], has_x
        commander_tax = (
            2
            * self.state.players[seat].commander_casts.get(card.oracle_id, 0)
            if card.zone == "command" and card.is_commander
            else 0
        )
        try:
            return parsed_cost(record.mana_cost, commander_tax), False
        except ManaPlanError:
            fixed, complex_symbols = mana_cost_to_vector(record.mana_cost)
            if complex_symbols and set(complex_symbols) == {"X"}:
                if x_value is None and not hint:
                    raise GameRuleError(
                        f"Casting {record.name} requires an explicit X value"
                    )
                selected_x = 0 if x_value is None else int(x_value)
                if selected_x < 0:
                    raise GameRuleError("X cannot be negative")
                fixed["GENERIC"] += (
                    selected_x * complex_symbols.count("X") + commander_tax
                )
                return self._mana_vector(fixed), True
            return None, False

    def _maximum_affordable_x(
        self,
        seat: str,
        card: CardInstance,
        *,
        limit: int = 100,
    ) -> int:
        maximum = -1
        for value in range(limit + 1):
            options, _ = self._compiled_printed_cost_options(
                seat,
                card,
                x_value=value,
                hint=False,
            )
            if not any(
                self._cost_is_affordable(
                    seat,
                    option["requirements"],
                )
                for option in options
            ):
                break
            maximum = value
        return maximum

    def _maximum_affordable_x_with_mechanics(
        self,
        seat: str,
        card: CardInstance,
        mechanics: Sequence[Mapping[str, Any]],
        *,
        limit: int = 100,
    ) -> int:
        maximum = -1
        for value in range(limit + 1):
            options, _ = self._compiled_printed_cost_options(
                seat,
                card,
                x_value=value,
                hint=False,
            )
            value_payable = False
            for raw_option in options:
                requirements = self._mana_vector(
                    raw_option["requirements"]
                )
                selected: list[CardInstance] = []
                valid = True
                for mechanic in mechanics:
                    kind = str(
                        mechanic.get("kind") or ""
                    ).casefold()
                    if kind == "affinity":
                        card_type = str(
                            mechanic.get("card_type") or "artifact"
                        ).casefold()
                        count = sum(
                            1
                            for object_id in self.state.players[seat].zones[
                                "battlefield"
                            ]
                            if self.state.cards[object_id].controller == seat
                            and card_type
                            in self._type_parts(
                                str(
                                    self._effective_card_data(
                                        self.state.cards[object_id]
                                    ).get("type_line")
                                    or ""
                                )
                            )[0]
                        )
                        requirements["GENERIC"] = max(
                            0, requirements["GENERIC"] - count
                        )
                    elif kind in {"convoke", "improvise"}:
                        candidates = [
                            candidate
                            for candidate in self._payment_mechanic_candidates(
                                seat, kind
                            )
                            if candidate not in selected
                        ]
                        plan = self._tap_payment_plan(
                            seat,
                            requirements,
                            kind,
                            candidates,
                        )
                        if plan is None:
                            valid = False
                            break
                        requirements, plan_cards = plan
                        selected.extend(plan_cards)
                    else:
                        valid = False
                        break
                if valid:
                    value_payable = True
                    break
            if not value_payable:
                break
            maximum = value
        return maximum

    def _cast_cost_options(
        self,
        seat: str,
        card: CardInstance,
        program: SemanticProgram | None,
        *,
        response: Mapping[str, Any] | None = None,
        hint: bool,
    ) -> list[dict[str, Any]]:
        """Compile server-authoritative payable casting-cost alternatives.

        Semantic packs describe reusable cost families.  The returned options
        contain only costs that are currently payable and whose nonmana cost
        objects are currently available to this seat.
        """

        response = dict(response or {})
        x_value = response.get("x")
        printed_options, has_x = self._compiled_printed_cost_options(
            seat,
            card,
            x_value=(int(x_value) if x_value is not None else None),
            hint=hint,
        )
        schema = dict(program.cost_schema or {}) if program else {}
        record = self.card_record(card)
        if record is None:
            return []
        payment_mechanics = self._cost_payment_mechanics(record, schema)
        base_options: list[dict[str, Any]] = printed_options
        commander_tax = (
            2
            * self.state.players[seat].commander_casts.get(card.oracle_id, 0)
            if card.zone == "command" and card.is_commander
            else 0
        )
        for raw in schema.get("alternate_costs", []):
            alternative = dict(raw)
            if not self._alternate_cost_condition_met(
                seat, dict(alternative.get("condition") or {})
            ):
                continue
            option_requirements = self._mana_vector(
                alternative.get("requirements")
            )
            option_requirements["GENERIC"] += commander_tax
            base_options.append(
                {
                    **alternative,
                    "id": str(alternative["id"]),
                    "kind": str(
                        alternative.get("kind") or "alternate"
                    ),
                    "requirements": option_requirements,
                }
            )
        expanded = list(base_options)
        for raw in schema.get("optional_costs", []):
            additional = dict(raw)
            additional_vector = self._mana_vector(
                additional.get("requirements")
            )
            for base in list(base_options):
                combined = self._mana_vector(base["requirements"])
                for symbol, amount in additional_vector.items():
                    combined[symbol] += amount
                expanded.append(
                    {
                        **base,
                        **{
                            key: copy.deepcopy(value)
                            for key, value in additional.items()
                            if key
                            not in {
                                "requirements",
                                "id",
                            }
                        },
                        "id": str(additional["id"]),
                        "kind": str(
                            additional.get("kind")
                            or "optional_additional"
                        ),
                        "requirements": combined,
                        "base_cost_option": base["id"],
                    }
                )
        mandatory_costs = [
            dict(value) for value in schema.get("additional_costs", [])
        ]
        payable: list[dict[str, Any]] = []
        for option in expanded:
            option = copy.deepcopy(option)
            option["base_requirements"] = self._mana_vector(
                option["requirements"]
            )
            exile_spec = option.get("exile_from_hand")
            if isinstance(exile_spec, Mapping):
                candidates = self._exile_cost_candidates(
                    seat, card, exile_spec
                )
                if not candidates:
                    continue
                option["exile_candidates"] = candidates
            choice_schema: dict[str, Any] = {}
            selected_tap_cards: list[CardInstance] = []
            payment_mechanics_valid = True
            for mechanic in payment_mechanics:
                kind = str(mechanic.get("kind") or "").casefold()
                if kind == "affinity":
                    card_type = str(
                        mechanic.get("card_type") or "artifact"
                    ).casefold()
                    count = sum(
                        1
                        for object_id in self.state.players[seat].zones[
                            "battlefield"
                        ]
                        if self.state.cards[object_id].controller == seat
                        and card_type
                        in self._type_parts(
                            str(
                                self._effective_card_data(
                                    self.state.cards[object_id]
                                ).get("type_line")
                                or ""
                            )
                        )[0]
                    )
                    option["requirements"]["GENERIC"] = max(
                        0,
                        int(option["requirements"]["GENERIC"]) - count,
                    )
                    option.setdefault("cost_reductions", []).append(
                        {
                            "kind": "affinity",
                            "count": count,
                            "card_type": card_type,
                        }
                    )
                    continue
                if kind not in {"convoke", "improvise"}:
                    payment_mechanics_valid = False
                    break
                candidates = [
                    candidate
                    for candidate in self._payment_mechanic_candidates(
                        seat, kind
                    )
                    if candidate not in selected_tap_cards
                ]
                field = f"{kind}_cards"
                choice_schema[field] = {
                    "type": "object_ref_array",
                    "minimum": 0,
                    "maximum": min(
                        len(candidates),
                        sum(option["requirements"].values()),
                    ),
                    "legal_refs": [
                        candidate.ref for candidate in candidates
                    ],
                    "payment": kind,
                }
                if hint:
                    plan = self._tap_payment_plan(
                        seat,
                        option["requirements"],
                        kind,
                        candidates,
                    )
                    if plan is None:
                        payment_mechanics_valid = False
                        break
                    option["requirements"] = plan[0]
                    option.setdefault(
                        "recommended_payment_refs", {}
                    )[field] = [card.ref for card in plan[1]]
                    selected_tap_cards.extend(plan[1])
                else:
                    raw_values = response.get(field) or []
                    if isinstance(raw_values, (str, bytes)):
                        payment_mechanics_valid = False
                        break
                    values = [str(value) for value in raw_values]
                    by_ref = {
                        candidate.ref: candidate
                        for candidate in candidates
                    }
                    if (
                        len(values) != len(set(values))
                        or any(value not in by_ref for value in values)
                    ):
                        payment_mechanics_valid = False
                        break
                    selected = [by_ref[value] for value in values]
                    if kind == "convoke":
                        reduced = self._convoke_reduction(
                            option["requirements"],
                            selected,
                        )
                        if reduced is None:
                            payment_mechanics_valid = False
                            break
                        option["requirements"] = reduced
                    else:
                        if len(selected) > int(
                            option["requirements"]["GENERIC"]
                        ):
                            payment_mechanics_valid = False
                            break
                        option["requirements"]["GENERIC"] -= len(selected)
                    selected_tap_cards.extend(selected)
            if not payment_mechanics_valid:
                continue
            excluded_tap_sources = {
                candidate.object_id for candidate in selected_tap_cards
            }
            if not self._cost_is_affordable(
                seat,
                option["requirements"],
                exclude_sources=excluded_tap_sources,
            ):
                continue
            if selected_tap_cards:
                option["selected_tap_cost_cards"] = [
                    candidate.ref for candidate in selected_tap_cards
                ]
            if has_x:
                maximum_x = (
                    self._maximum_affordable_x_with_mechanics(
                        seat,
                        card,
                        payment_mechanics,
                    )
                    if payment_mechanics
                    else self._maximum_affordable_x(seat, card)
                )
                if maximum_x < 0:
                    continue
                choice_schema["x"] = {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": maximum_x,
                }
            valid_additional = True
            selected_nonmana: list[dict[str, Any]] = []
            selected_refs: set[str] = set()
            for additional_index, additional in enumerate(mandatory_costs):
                additional_kind = str(additional.get("kind") or "")
                if additional_kind == "life_x":
                    selected_x = (
                        int(response["x"])
                        if response.get("x") is not None
                        else 0
                    )
                    minimum = int(additional.get("minimum", 0))
                    maximum = self.state.players[seat].life
                    if maximum < minimum:
                        valid_additional = False
                        break
                    if selected_x < minimum or selected_x > maximum:
                        valid_additional = False
                        break
                    choice_schema["x"] = {
                        "type": "integer",
                        "minimum": minimum,
                        "maximum": maximum,
                        "payment": "life",
                    }
                elif additional_kind in {"sacrifice", "discard"}:
                    count = int(additional.get("count", 1))
                    candidates = [
                        ref
                        for ref in self._additional_cost_candidates(
                            seat,
                            card,
                            additional,
                        )
                        if ref not in selected_refs
                    ]
                    if len(candidates) < count:
                        valid_additional = False
                        break
                    field = str(
                        additional.get("choice_field")
                        or f"{additional_kind}_cards"
                    )
                    choice_schema[field] = {
                        "type": "object_ref_array",
                        "count": count,
                        "legal_refs": candidates,
                        "zone": (
                            "hand"
                            if additional_kind == "discard"
                            else "battlefield"
                        ),
                        "destination": "graveyard",
                    }
                    if not hint:
                        raw_values = response.get(field)
                        if raw_values is None and len(mandatory_costs) == 1:
                            raw_values = response.get("cost_cards")
                        values = [
                            str(value)
                            for value in (raw_values or [])
                        ]
                        if (
                            len(values) != count
                            or len(set(values)) != count
                            or any(
                                value not in candidates
                                for value in values
                            )
                        ):
                            valid_additional = False
                            break
                        selected_refs.update(values)
                        selected_nonmana.append(
                            {
                                "kind": additional_kind,
                                "cards": values,
                                "index": additional_index,
                            }
                        )
                elif additional_kind:
                    valid_additional = False
                    break
            if not valid_additional:
                continue
            if isinstance(exile_spec, Mapping):
                choice_schema["exile_card"] = {
                    "type": "object_ref",
                    "legal_refs": list(option["exile_candidates"]),
                    "zone": "hand",
                    "destination": "exile",
                }
                if not hint:
                    selected = str(
                        response.get("exile_card")
                        or (
                            list(response.get("exile_cards") or [None])[0]
                        )
                        or ""
                    )
                    if selected not in option["exile_candidates"]:
                        continue
                    option["selected_exile_card"] = selected
            option["additional_costs"] = mandatory_costs
            if selected_nonmana:
                option["selected_additional_costs"] = selected_nonmana
            if choice_schema:
                option["choice_schema"] = choice_schema
            payable.append(option)
        return payable

    def _priority_action_hints(self, seat: str) -> dict[str, Any]:
        player = self.state.players[seat]
        candidate_zones = [*player.zones["hand"], *player.zones["command"]]
        castable: list[str] = []
        cast_target_schemas: dict[str, dict[str, Any]] = {}
        cast_cost_options: dict[str, list[dict[str, Any]]] = {}
        unpayable_casts: list[dict[str, Any]] = []
        unresolved_casts: list[dict[str, Any]] = []
        for oid in candidate_zones:
            record = self.card_record(oid)
            if not record or record.is_land:
                continue
            main_timing = seat == self.state.active_player and not self.state.stack and self.state.step == "main"
            program = self.semantics.get(
                f"{record.oracle_id}:spell:front"
            )
            timing_available = record.is_instant or record.has_flash or main_timing
            if (
                timing_available
                and self.state.config.semantic_policy == "trusted_only"
                and (
                    (
                        program is not None
                        and not self.semantic_program_is_current_trusted(
                            program
                        )
                    )
                    or (
                        program is None
                        and not self._trusted_generic_spell(record)
                    )
                )
            ):
                unresolved_casts.append(
                    {
                        "id": f"cast:{self.state.cards[oid].ref}",
                        "kind": "cast",
                        "card": self.state.cards[oid].ref,
                        "from": self.state.cards[oid].zone,
                        "status": "unresolved",
                        "reason": "semantic_policy_requires_trusted",
                    }
                )
                continue
            if timing_available:
                options = self._cast_cost_options(
                    seat,
                    self.state.cards[oid],
                    program,
                    hint=True,
                )
                legal_options: list[dict[str, Any]] = []
                for option in options:
                    target_specification = (
                        dict(option["target_schema"])
                        if isinstance(
                            option.get("target_schema"), Mapping
                        )
                        else (
                            program.target_schema
                            if program is not None
                            else None
                        )
                    )
                    public_target_schema = None
                    if target_specification is not None:
                        public_target_schema = self._public_target_schema(
                            seat,
                            target_specification,
                            source_ref=self.state.cards[oid].ref,
                        )
                        if public_target_schema is None:
                            continue
                    public_option = {
                        key: copy.deepcopy(value)
                        for key, value in option.items()
                        if key
                        in {
                            "id",
                            "kind",
                            "requirements",
                            "choice_schema",
                            "label",
                        }
                    }
                    if public_target_schema is not None:
                        public_option["target_schema"] = (
                            public_target_schema
                        )
                    legal_options.append(public_option)
                if not legal_options:
                    unpayable_casts.append(
                        {
                            "id": f"cast:{self.state.cards[oid].ref}",
                            "kind": "cast",
                            "card": self.state.cards[oid].ref,
                            "from": self.state.cards[oid].zone,
                            "status": "unavailable",
                            "reason": (
                                "mandatory_target_unavailable"
                                if options
                                else "mandatory_cost_unpayable"
                            ),
                        }
                    )
                    continue
                ref = self.state.cards[oid].ref
                cast_cost_options[ref] = legal_options
                if (
                    len(legal_options) == 1
                    and legal_options[0].get("target_schema")
                ):
                    cast_target_schemas[ref] = copy.deepcopy(
                        legal_options[0]["target_schema"]
                    )
                castable.append(ref)
                continue
            requirements = self._card_cast_requirements(seat, self.state.cards[oid])
            if timing_available and requirements is None:
                unresolved_casts.append(
                    {
                        "id": f"cast:{self.state.cards[oid].ref}",
                        "kind": "cast",
                        "card": self.state.cards[oid].ref,
                        "from": self.state.cards[oid].zone,
                        "status": "unresolved",
                        "reason": "unresolved_cost_semantics",
                    }
                )
                continue
            if (
                timing_available
                and requirements is not None
                and not self._cost_is_affordable(seat, requirements)
            ):
                unpayable_casts.append(
                    {
                        "id": f"cast:{self.state.cards[oid].ref}",
                        "kind": "cast",
                        "card": self.state.cards[oid].ref,
                        "from": self.state.cards[oid].zone,
                        "status": "unpayable",
                        "reason": "insufficient_mana",
                    }
                )
                continue
            if (
                timing_available
                and requirements is not None
            ):
                if program and program.target_schema:
                    public_target_schema = self._public_target_schema(
                        seat,
                        program.target_schema,
                        source_ref=self.state.cards[oid].ref,
                    )
                    if public_target_schema is None:
                        unpayable_casts.append(
                            {
                                "id": f"cast:{self.state.cards[oid].ref}",
                                "kind": "cast",
                                "card": self.state.cards[oid].ref,
                                "from": self.state.cards[oid].zone,
                                "status": "unavailable",
                                "reason": "mandatory_target_unavailable",
                            }
                        )
                        continue
                    cast_target_schemas[
                        self.state.cards[oid].ref
                    ] = public_target_schema
                castable.append(self.state.cards[oid].ref)
        lands: list[str] = []
        if seat == self.state.active_player and not self.state.stack and self.state.step == "main" and player.land_plays_remaining:
            lands = [
                self.state.cards[oid].ref
                for oid in player.zones["hand"]
                if (self.card_record(oid) and self.card_record(oid).is_land)
            ]
        (
            abilities,
            mana_abilities,
            unpayable_abilities,
            unresolved_abilities,
        ) = self._classified_ability_hints(seat)
        ability_target_schemas: dict[str, dict[str, Any]] = {}
        ability_target_status: dict[str, bool] = {}

        def target_available(ability_hint: Mapping[str, Any]) -> bool:
            action_id = (
                f"activate:{ability_hint['s']}:{ability_hint['a']}"
            )
            if action_id in ability_target_status:
                return ability_target_status[action_id]
            source = next(
                (
                    value
                    for value in self.state.cards.values()
                    if value.ref == ability_hint["s"]
                ),
                None,
            )
            program = (
                self.semantics.get(
                    f"{source.oracle_id}:ability:{ability_hint['a']}"
                )
                if source
                else None
            )
            if (
                program is not None
                and self.state.config.semantic_policy == "trusted_only"
                and not self.semantic_program_is_current_trusted(program)
            ):
                ability_target_status[action_id] = False
                unresolved_abilities.append(
                    {
                        **dict(ability_hint),
                        "id": action_id,
                        "status": "unresolved",
                        "reason": "semantic_policy_requires_trusted",
                    }
                )
                return False
            if not program or not program.target_schema:
                ability_target_status[action_id] = True
                return True
            public_schema = self._public_target_schema(
                seat,
                program.target_schema,
                source_ref=source.ref,
            )
            if public_schema is None:
                ability_target_status[action_id] = False
                unpayable_abilities.append(
                    {
                        **dict(ability_hint),
                        "id": action_id,
                        "status": "unavailable",
                        "reason": "mandatory_target_unavailable",
                    }
                )
                return False
            ability_target_status[action_id] = True
            ability_target_schemas[action_id] = public_schema
            return True

        abilities = [
            ability for ability in abilities if target_available(ability)
        ]
        mana_abilities = [
            ability
            for ability in mana_abilities
            if target_available(ability)
        ]
        actions: list[dict[str, Any]] = [{"id": "pass", "action": "pass"}]
        for ref in lands:
            card = next(
                value for value in self.state.cards.values() if value.ref == ref
            )
            record = self.card_record(card)
            action = {
                "id": f"play-land:{ref}",
                "action": "play_land",
                "kind": "play_land",
                "card": ref,
            }
            if (
                record
                and "you may pay 2 life. if you don't, it enters tapped"
                in record.oracle_text.casefold()
            ):
                action["choice_schema"] = {
                    "pay_life": {
                        "type": "boolean",
                        "life": 2,
                        "effect": "enters untapped",
                    }
                }
            actions.append(action)
        for ref in castable:
            card = next(
                value for value in self.state.cards.values() if value.ref == ref
            )
            record = self.card_record(card)
            program = (
                self.semantics.get(f"{record.oracle_id}:spell:front")
                if record
                else None
            )
            action: dict[str, Any] = {
                "id": f"cast:{ref}",
                "action": "cast",
                "kind": "cast",
                "card": ref,
                "from": card.zone,
                "cost": record.mana_cost if record else "",
                "auto_pay": True,
            }
            if ref in cast_target_schemas:
                action["target_schema"] = copy.deepcopy(
                    cast_target_schemas[ref]
                )
            if ref in cast_cost_options:
                action["cost_options"] = copy.deepcopy(
                    cast_cost_options[ref]
                )
            actions.append(action)
        seen_ability_actions: set[str] = set()
        for ability in [*abilities, *mana_abilities]:
            action_id = f"activate:{ability['s']}:{ability['a']}"
            if action_id in seen_ability_actions:
                continue
            seen_ability_actions.add(action_id)
            action = {
                "id": action_id,
                "action": "activate",
                "kind": "activate",
                "source": ability["s"],
                "ability": ability["a"],
                "from": ability["z"],
                "cost_summary": {
                    key: copy.deepcopy(value)
                    for key, value in ability.items()
                    if key
                    in {
                        "m",
                        "tap",
                        "life",
                        "sac_self",
                        "discard_self",
                        "exile_self",
                        "choose_cost",
                    }
                },
            }
            if ability.get("search_types"):
                action["choice_schema"] = {
                    "resolution_time": True,
                    "search_types": copy.deepcopy(ability["search_types"]),
                }
            if action_id in ability_target_schemas:
                action["target_schema"] = copy.deepcopy(
                    ability_target_schemas[action_id]
                )
            actions.append(action)
        return {
            "cast": castable,
            "lands": lands,
            "abilities": abilities,
            "mana_abilities": mana_abilities,
            "actions": actions,
            "diagnostic": {
                "unpayable": [
                    *unpayable_casts,
                    *unpayable_abilities,
                ],
                "unresolved_cost_semantics": [
                    *unresolved_casts,
                    *unresolved_abilities,
                ],
            },
        }

    def _priority_window_empty(
        self, seat: str, hints: Mapping[str, Any] | None = None
    ) -> bool:
        """Whether the implemented action grammar exposes no priority action.

        Concede is deliberately ignored: the simulator should not spend an LLM
        call merely to offer concession at every priority window. The setting
        can be disabled for debugging or for a future client that implements
        additional special actions not yet represented by the kernel.
        """

        hints = dict(hints or self._priority_action_hints(seat))
        return not any(hints.get(key) for key in ("cast", "lands", "abilities"))

    # ------------------------------------------------------------------
    # Stack resolution and arbiter role
    # ------------------------------------------------------------------
    def _semantic_event_value(
        self,
        value: Any,
        *,
        source: CardInstance,
        context: Mapping[str, Any],
    ) -> Any:
        substitutions = {
            "$source.controller": source.controller,
            "$source.owner": source.owner,
            "$source.ref": source.ref,
            "$source.object_id": source.object_id,
            "$active_player": self.state.active_player,
        }
        if isinstance(value, str) and value in substitutions:
            return substitutions[value]
        if isinstance(value, str) and value.startswith("$context."):
            return context.get(value.removeprefix("$context."))
        if isinstance(value, list):
            return [
                self._semantic_event_value(
                    item,
                    source=source,
                    context=context,
                )
                for item in value
            ]
        return value

    def _semantic_event_condition_matches(
        self,
        condition: Mapping[str, Any],
        *,
        source: CardInstance,
        context: Mapping[str, Any],
    ) -> bool:
        """Evaluate a declarative trigger condition against event context.

        Conditions deliberately read only normalized event fields and stable
        source identity. They cannot mutate state or execute semantic effects.
        """

        if "all" in condition:
            values = condition.get("all")
            if not isinstance(values, Sequence) or isinstance(
                values, (str, bytes)
            ):
                raise GameRuleError("Semantic event 'all' must be a list")
            return all(
                self._semantic_event_condition_matches(
                    dict(item),
                    source=source,
                    context=context,
                )
                for item in values
                if isinstance(item, Mapping)
            )
        if "any" in condition:
            values = condition.get("any")
            if not isinstance(values, Sequence) or isinstance(
                values, (str, bytes)
            ):
                raise GameRuleError("Semantic event 'any' must be a list")
            return any(
                self._semantic_event_condition_matches(
                    dict(item),
                    source=source,
                    context=context,
                )
                for item in values
                if isinstance(item, Mapping)
            )
        if "not" in condition:
            nested = condition.get("not")
            if not isinstance(nested, Mapping):
                raise GameRuleError("Semantic event 'not' must be an object")
            return not self._semantic_event_condition_matches(
                nested,
                source=source,
                context=context,
            )

        field = str(condition.get("field") or "")
        if not field:
            raise GameRuleError("Semantic event condition requires a field")
        actual = context.get(field)
        expected = self._semantic_event_value(
            condition.get("value"),
            source=source,
            context=context,
        )
        op = str(condition.get("op") or "eq")
        if op == "eq":
            return actual == expected
        if op == "ne":
            return actual != expected
        if op == "in":
            return actual in (expected or [])
        if op == "not_in":
            return actual not in (expected or [])
        if op == "gte":
            return actual is not None and actual >= expected
        if op == "gt":
            return actual is not None and actual > expected
        if op == "lte":
            return actual is not None and actual <= expected
        if op == "lt":
            return actual is not None and actual < expected
        if op == "truthy":
            return bool(actual)
        if op == "falsy":
            return not bool(actual)
        raise GameRuleError(
            f"Unsupported semantic event condition operator {op!r}"
        )

    def _semantic_event_matches(
        self,
        program: SemanticProgram,
        source: CardInstance,
        event: str,
        context: Mapping[str, Any],
        *,
        source_zone: str | None = None,
    ) -> bool:
        self_event = program.event.endswith(".self")
        program_event = (
            program.event.removesuffix(".self")
            if self_event
            else program.event
        )
        if (
            program_event != event
            or program.active_zone != (source_zone or source.zone)
        ):
            return False
        if self_event and str(context.get("card") or "") != source.ref:
            return False
        if source.controller not in self.active_seats:
            return False
        if program.event_condition is not None:
            return self._semantic_event_condition_matches(
                program.event_condition,
                source=source,
                context=context,
            )
        if event == "land.enter":
            entered = self._resolve_object(
                source.controller,
                str(context.get("card")),
                zones={"battlefield"},
            )
            return entered.controller == source.controller
        if event == "card.second_draw":
            return context.get("player") == source.controller
        if event == "step.begin":
            return (
                context.get("player") == source.controller
                and context.get("step") == "beginning_combat"
            )
        if event == "artifact.enter":
            entered = self._resolve_object(
                source.controller,
                str(context.get("card")),
                zones={"battlefield"},
            )
            return entered.controller == source.controller
        if event == "creature.dies":
            return (
                context.get("previous_controller")
                == source.controller
            )
        return True

    def _dispatch_semantic_event(
        self,
        event: str,
        context: Mapping[str, Any],
        *,
        sources: Sequence[CardInstance] | None = None,
        source_zones: Mapping[str, str] | None = None,
        trigger_batch: list[StackItem] | None = None,
    ) -> list[str]:
        """Queue data-driven triggers for a normalized authoritative event."""

        triggered: list[StackItem] = []
        candidates = list(sources) if sources is not None else self._semantic_event_sources()
        for source in candidates:
            active_zone = (
                source_zones.get(source.object_id, source.zone)
                if source_zones is not None
                else source.zone
            )
            for program in self.semantics.programs_for_oracle(
                source.oracle_id,
                active_zone=active_zone,
            ):
                if program.trust_level == "unresolved":
                    continue
                if not self._semantic_event_matches(
                    program,
                    source,
                    event,
                    context,
                    source_zone=active_zone,
                ):
                    continue
                if (
                    self.state.config.semantic_policy == "trusted_only"
                    and not self.semantic_program_is_current_trusted(program)
                ):
                    self._pause_for_unsupported_semantic(
                        program=program,
                        event=event,
                        source=source,
                    )
                    return [item.ref for item in triggered]
                ref = self._next_ref("S")
                item = StackItem(
                    stack_id=self._stable_runtime_id("stack", ref),
                    ref=ref,
                    kind="triggered_ability",
                    controller=source.controller,
                    label=program.label,
                    source_object_id=source.object_id,
                    semantic_key=program.key,
                    visibility=list(self.seats),
                    context={
                        "event": event,
                        **copy.deepcopy(dict(context)),
                        **(
                            {"trigger_target_selection_pending": True}
                            if program.target_schema
                            else {}
                        ),
                    },
                )
                triggered.append(item)
        if trigger_batch is not None:
            trigger_batch.extend(triggered)
        elif triggered:
            self._enqueue_semantic_trigger_batch(triggered)
        return [item.ref for item in triggered]

    def _enqueue_semantic_trigger_batch(
        self,
        items: Sequence[StackItem],
    ) -> None:
        if not items:
            return
        groups: list[dict[str, Any]] = []
        for controller in self.apnap_order():
            controlled = [
                item.to_dict()
                for item in items
                if item.controller == controller
            ]
            if controlled:
                groups.append(
                    {
                        "controller": controller,
                        "items": controlled,
                    }
                )
        if not groups:
            return
        batch_ref = self._next_ref("TB")
        self.state.pending_trigger_batches.append(
            {
                "batch_id": self._stable_runtime_id(
                    "trigger-batch",
                    batch_ref,
                ),
                "ref": batch_ref,
                "apnap_order": self.apnap_order(),
                "groups": groups,
                "turn_sequence": self.state.turn_sequence,
            }
        )

    def _place_semantic_trigger_items(
        self,
        values: Sequence[Mapping[str, Any]],
    ) -> None:
        for value in values:
            item = StackItem.from_dict(copy.deepcopy(dict(value)))
            self.state.stack.append(item)
            source = (
                self.state.cards.get(item.source_object_id)
                if item.source_object_id
                else None
            )
            self._log(
                item.controller,
                "stack.trigger",
                f"Queued {item.ref}: {item.label}.",
                {
                    "stack": item.ref,
                    "source": source.ref if source else None,
                    "semantic_program": item.semantic_key,
                    "event": item.context.get("event"),
                },
                importance=2,
                changed_objects=(
                    [source.object_id] if source is not None else []
                ),
            )

    def _begin_pending_semantic_trigger_batch(self) -> bool:
        while self.state.pending_trigger_batches:
            batch = self.state.pending_trigger_batches[0]
            groups = list(batch.get("groups") or [])
            if not groups:
                self.state.pending_trigger_batches.pop(0)
                continue
            group = groups[0]
            controller = str(group["controller"])
            items = list(group.get("items") or [])
            if len(items) > 1:
                self.permissions.issue(
                    kind="trigger.order",
                    role="pilot",
                    actors=[controller],
                    allowed_actions=["order"],
                    payload_by_actor={
                        controller: {
                            "triggers": [
                                {
                                    "id": str(item["ref"]),
                                    "label": str(item["label"]),
                                }
                                for item in items
                            ],
                            "instruction": (
                                "Order bottom-to-top on the stack."
                            ),
                        }
                    },
                    continuation={
                        "semantic_trigger_batch_id": batch["batch_id"],
                        "trigger_refs": [
                            str(item["ref"]) for item in items
                        ],
                    },
                )
                return True
            self._place_semantic_trigger_items(items)
            batch["groups"] = groups[1:]
        return False

    def _semantic_target_options(
        self,
        controller: str,
        schema: Mapping[str, Any],
        *,
        modes: Sequence[str] = (),
        source_ref: str | None = None,
    ) -> list[str]:
        """Return the candidate-set union for a declarative target plan.

        Candidate sets are intentionally returned rather than target tuples.
        The submitted grouping/count/distinctness constraints are validated by
        the authoritative engine.
        """

        try:
            plan = target_plan(
                schema,
                modes,
                require_modes=bool(available_modes(schema)),
            )
        except ValueError:
            return []
        options: list[str] = []
        for group in plan.groups:
            options.extend(
                self._target_candidates(
                    controller,
                    group,
                    source_ref=source_ref,
                )
            )
        return unique_preserving_order(options)

    @staticmethod
    def _type_parts(type_line: str) -> tuple[set[str], set[str], set[str]]:
        normalized = type_line.replace("—", "-")
        left, _, right = normalized.partition("-")
        words = {word.casefold() for word in re.findall(r"[A-Za-z]+", left)}
        card_types = {
            "artifact",
            "battle",
            "creature",
            "enchantment",
            "instant",
            "kindred",
            "land",
            "planeswalker",
            "sorcery",
        }
        supertypes = {"basic", "legendary", "ongoing", "snow", "world"}
        return (
            words.intersection(card_types),
            {
                word.casefold()
                for word in re.findall(r"[A-Za-z]+", right)
            },
            words.intersection(supertypes),
        )

    @staticmethod
    def _relation_matches(
        value: str | None,
        controller: str,
        relation: str,
    ) -> bool:
        if relation == "any":
            return True
        if relation == "you":
            return value == controller
        return value is not None and value != controller

    def _target_candidate_rows(
        self,
        controller: str,
        group: TargetGroup,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if "player" in group.zones:
            for seat in self.active_seats:
                rows.append(
                    {
                        "ref": seat,
                        "zone": "player",
                        "category": "player",
                        "controller": seat,
                        "owner": seat,
                        "types": set(),
                        "subtypes": set(),
                        "supertypes": set(),
                        "colors": set(),
                        "mana_value": 0.0,
                        "card": None,
                    }
                )
        if "stack" in group.zones:
            for item in self.state.stack:
                card = self.state.cards.get(item.card_object_id or "")
                data = self._effective_card_data(card) if card else {}
                types, subtypes, supertypes = self._type_parts(
                    str(data.get("type_line") or "")
                )
                rows.append(
                    {
                        "ref": item.ref,
                        "zone": "stack",
                        "category": (
                            "spell" if item.kind == "spell" else "ability"
                        ),
                        "controller": item.controller,
                        "owner": card.owner if card else item.controller,
                        "types": types,
                        "subtypes": subtypes,
                        "supertypes": supertypes,
                        "colors": {
                            str(color).upper()
                            for color in data.get("colors", [])
                        },
                        "mana_value": float(
                            data.get(
                                "mana_value",
                                data.get("cmc", 0),
                            )
                            or 0
                        ),
                        "card": card,
                        "stack_item": item,
                    }
                )
        for zone in (
            "battlefield",
            "graveyard",
            "exile",
            "command",
        ):
            if zone not in group.zones:
                continue
            for seat in self.active_seats:
                for object_id in self.state.players[seat].zones.get(zone, []):
                    card = self.state.cards[object_id]
                    if card.face_down and controller not in card.known_to:
                        # A face-down object in a public zone remains a public,
                        # targetable object.  Candidate generation must use only
                        # its public characteristics and never its hidden front.
                        data = {
                            "type_line": (
                                "Creature" if zone == "battlefield" else ""
                            ),
                            "colors": [],
                            "mana_value": 0,
                        }
                    else:
                        data = self._effective_card_data(card)
                    types, subtypes, supertypes = self._type_parts(
                        str(data.get("type_line") or "")
                    )
                    rows.append(
                        {
                            "ref": card.ref,
                            "zone": zone,
                            "category": (
                                "permanent" if zone == "battlefield" else "card"
                            ),
                            "controller": card.controller,
                            "owner": card.owner,
                            "types": types,
                            "subtypes": subtypes,
                            "supertypes": supertypes,
                            "colors": {
                                str(color).upper()
                                for color in data.get("colors", [])
                            },
                            "mana_value": float(
                                data.get(
                                    "mana_value",
                                    data.get("cmc", 0),
                                )
                                or 0
                            ),
                            "card": card,
                        }
                    )
        return rows

    def _target_row_matches(
        self,
        controller: str,
        group: TargetGroup,
        row: Mapping[str, Any],
        *,
        source_ref: str | None,
        as_target: bool = True,
    ) -> bool:
        ref = str(row["ref"])
        if (group.source_exclusion or group.another) and ref == source_ref:
            return False
        card = row.get("card")
        if as_target and row.get("zone") == "battlefield" and isinstance(
            card, CardInstance
        ):
            keywords = {
                str(value).casefold()
                for value in self._effective_card_data(card).get(
                    "keywords", []
                )
            }
            if "shroud" in keywords:
                return False
            if (
                "hexproof" in keywords
                and card.controller != controller
            ):
                return False
        if group.categories and str(row["category"]) not in {
            value.casefold() for value in group.categories
        }:
            return False
        if not self._relation_matches(
            str(row.get("controller")),
            controller,
            group.controller_relation,
        ):
            return False
        if not self._relation_matches(
            str(row.get("owner")),
            controller,
            group.owner_relation,
        ):
            return False
        if row["category"] == "player" and not self._relation_matches(
            str(row["ref"]),
            controller,
            group.player_relation,
        ):
            return False
        types = set(row.get("types") or ())
        subtypes = set(row.get("subtypes") or ())
        supertypes = set(row.get("supertypes") or ())
        types_any = {value.casefold() for value in group.types_any}
        types_all = {value.casefold() for value in group.types_all}
        if types_any and not types.intersection(types_any):
            return False
        if types_all and not types_all.issubset(types):
            return False
        if group.subtypes_any and not subtypes.intersection(
            value.casefold() for value in group.subtypes_any
        ):
            return False
        if group.supertypes_any and not supertypes.intersection(
            value.casefold() for value in group.supertypes_any
        ):
            return False
        colors = set(row.get("colors") or ())
        if group.colors_any and not colors.intersection(group.colors_any):
            return False
        if group.colors_all and not set(group.colors_all).issubset(colors):
            return False
        if group.colorless is not None and (not colors) != group.colorless:
            return False
        mana_value = float(row.get("mana_value", 0) or 0)
        if (
            group.mana_value_equal is not None
            and mana_value != group.mana_value_equal
        ):
            return False
        if (
            group.mana_value_min is not None
            and mana_value < group.mana_value_min
        ):
            return False
        if (
            group.mana_value_max is not None
            and mana_value > group.mana_value_max
        ):
            return False
        card = row.get("card")
        if group.attacking is not None and (
            bool(card and card.attacking is not None) != group.attacking
        ):
            return False
        if group.blocking is not None and (
            bool(card and card.blocking is not None) != group.blocking
        ):
            return False
        if group.tapped is not None and (
            bool(card and card.tapped) != group.tapped
        ):
            return False
        if group.commander is not None and (
            bool(card and card.is_commander) != group.commander
        ):
            return False
        if group.token is not None and (
            bool(card and card.is_token) != group.token
        ):
            return False
        derived = {
            "land": "land" in types,
            "creature": "creature" in types,
            "artifact": "artifact" in types,
            "enchantment": "enchantment" in types,
            "permanent": row["category"] == "permanent",
        }
        if group.predicate:
            if group.predicate == "artifact_or_enchantment_or_nonbasic_land":
                if not (
                    derived["artifact"]
                    or derived["enchantment"]
                    or (
                        derived["land"]
                        and "basic" not in supertypes
                    )
                ):
                    return False
            else:
                raise GameRuleError(
                    f"Unsupported target predicate {group.predicate!r}"
                )
        for name in (
            "land",
            "creature",
            "artifact",
            "enchantment",
            "permanent",
        ):
            expected = getattr(group, name)
            if expected is not None and derived[name] != expected:
                return False
        return True

    def _target_candidates(
        self,
        controller: str,
        group: TargetGroup,
        *,
        source_ref: str | None = None,
    ) -> list[str]:
        values = [
            str(row["ref"])
            for row in self._target_candidate_rows(controller, group)
            if self._target_row_matches(
                controller,
                group,
                row,
                source_ref=source_ref,
            )
        ]
        values = unique_preserving_order(values)
        self._optimization_stats(controller)["target_candidates_generated"] += len(
            values
        )
        return values

    def _target_snapshot(self, ref: str) -> dict[str, Any]:
        if ref in self.state.players:
            return {
                "ref": ref,
                "category": "player",
                "controller": ref,
                "owner": ref,
                "colors": [],
                "mana_value": 0,
                "type_line": "Player",
            }
        item = next(
            (candidate for candidate in self.state.stack if candidate.ref == ref),
            None,
        )
        if item is not None:
            card = self.state.cards.get(item.card_object_id or "")
            data = self._effective_card_data(card) if card else {}
            return {
                "ref": ref,
                "category": (
                    "spell" if item.kind == "spell" else "ability"
                ),
                "controller": item.controller,
                "owner": card.owner if card else item.controller,
                "colors": list(data.get("colors", [])),
                "mana_value": float(
                    data.get("mana_value", data.get("cmc", 0)) or 0
                ),
                "type_line": str(data.get("type_line") or ""),
            }
        card = next(
            (
                candidate
                for candidate in self.state.cards.values()
                if candidate.ref == ref
            ),
            None,
        )
        if card is None:
            return {"ref": ref}
        data = self._effective_card_data(card)
        return {
            "ref": ref,
            "category": (
                "permanent" if card.zone == "battlefield" else "card"
            ),
            "controller": card.controller,
            "owner": card.owner,
            "colors": list(data.get("colors", [])),
            "mana_value": float(
                data.get("mana_value", data.get("cmc", 0)) or 0
            ),
            "type_line": str(data.get("type_line") or ""),
        }

    def _target_candidate_map(
        self,
        controller: str,
        plan: TargetPlan,
        *,
        source_ref: str | None,
    ) -> dict[str, list[str]]:
        return {
            group.group_id: self._target_candidates(
                controller,
                group,
                source_ref=source_ref,
            )
            for group in plan.groups
        }

    @staticmethod
    def _target_plan_feasible(
        plan: TargetPlan,
        candidates: Mapping[str, Sequence[str]],
    ) -> bool:
        for group in plan.groups:
            if len(candidates.get(group.group_id, ())) < group.min_targets:
                return False
        slots = [
            group
            for group in plan.groups
            for _ in range(group.min_targets)
        ]

        def choose(
            index: int,
            selected: dict[str, list[str]],
            globally_used: set[str],
        ) -> bool:
            if index >= len(slots):
                return True
            group = slots[index]
            for ref in candidates.get(group.group_id, ()):
                own = selected.setdefault(group.group_id, [])
                if group.distinct and not group.allow_reuse and ref in own:
                    continue
                if plan.globally_distinct and ref in globally_used:
                    continue
                if any(
                    ref in selected.get(other, ())
                    for other in group.different_from_groups
                ):
                    continue
                own.append(ref)
                added_global = ref not in globally_used
                if added_global:
                    globally_used.add(ref)
                if choose(index + 1, selected, globally_used):
                    return True
                own.pop()
                if added_global:
                    globally_used.remove(ref)
            return False

        return choose(0, {}, set())

    def _public_target_schema(
        self,
        controller: str,
        schema: Mapping[str, Any],
        *,
        source_ref: str | None,
    ) -> dict[str, Any] | None:
        modes = available_modes(schema)
        if modes:
            legal_modes: list[str] = []
            mode_schemas: dict[str, Any] = {}
            for mode in modes:
                try:
                    plan = target_plan(schema, [mode], require_modes=True)
                except ValueError:
                    continue
                candidates = self._target_candidate_map(
                    controller,
                    plan,
                    source_ref=source_ref,
                )
                if not self._target_plan_feasible(plan, candidates):
                    continue
                legal_modes.append(mode)
                mode_schemas[mode] = {
                    "groups": [
                        group.public_dict(candidates[group.group_id])
                        for group in plan.groups
                    ]
                }
            if not legal_modes:
                self._increment_optimization(
                    controller, "illegal_target_actions_prevented"
                )
                self._increment_optimization(
                    controller, "actions_removed_for_mode_target_failure"
                )
                return None
            legal_refs = unique_preserving_order(
                ref
                for mode in legal_modes
                for group in mode_schemas[mode]["groups"]
                for ref in group["legal_refs"]
            )
            return {
                "mode_count": int(schema.get("mode_count", 1)),
                "min_modes": int(
                    schema.get("min_modes", schema.get("mode_count", 1))
                ),
                "max_modes": int(
                    schema.get("max_modes", schema.get("mode_count", 1))
                ),
                "legal_modes": legal_modes,
                "mode_schemas": mode_schemas,
                "legal_refs": legal_refs,
            }
        try:
            plan = target_plan(schema)
        except ValueError:
            return None
        candidates = self._target_candidate_map(
            controller,
            plan,
            source_ref=source_ref,
        )
        if not self._target_plan_feasible(plan, candidates):
            self._increment_optimization(
                controller, "illegal_target_actions_prevented"
            )
            self._increment_optimization(
                controller, "actions_removed_for_no_targets"
            )
            return None
        result = copy.deepcopy(dict(schema))
        result["groups"] = [
            group.public_dict(candidates[group.group_id])
            for group in plan.groups
        ]
        if len(plan.groups) == 1:
            result["legal_refs"] = list(candidates[plan.groups[0].group_id])
        return result

    @staticmethod
    def _group_target_submission(
        plan: TargetPlan,
        targets: Sequence[Any],
    ) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {
            group.group_id: [] for group in plan.groups
        }
        if targets and all(isinstance(value, Mapping) for value in targets):
            for value in targets:
                group_id = str(value.get("group") or value.get("group_id") or "")
                ref = value.get("ref", value.get("target"))
                if group_id not in grouped or ref is None:
                    raise GameRuleError("Grouped target selection is malformed")
                grouped[group_id].append(str(ref))
            return grouped
        if len(plan.groups) == 1:
            grouped[plan.groups[0].group_id] = [str(value) for value in targets]
            return grouped
        cursor = 0
        if all(group.min_targets == group.max_targets for group in plan.groups):
            for group in plan.groups:
                grouped[group.group_id] = [
                    str(value)
                    for value in targets[
                        cursor : cursor + group.min_targets
                    ]
                ]
                cursor += group.min_targets
            if cursor == len(targets):
                return grouped
        raise GameRuleError(
            "Multiple variable target groups require "
            "{group, ref} target selections"
        )

    def _validate_semantic_targets(
        self,
        controller: str,
        program: SemanticProgram | None,
        targets: Sequence[Any],
        *,
        modes: Sequence[str] = (),
        source_ref: str | None = None,
        target_schema: Mapping[str, Any] | None = None,
    ) -> tuple[list[str], dict[str, list[str]]]:
        schema = (
            target_schema
            if target_schema is not None
            else program.target_schema
            if program is not None
            else None
        )
        if schema is None:
            if targets or modes:
                self._increment_optimization(
                    controller, "target_submissions_rejected"
                )
                raise GameRuleError(
                    "This semantic program does not accept targets or modes"
                )
            return [], {}
        try:
            plan = target_plan(
                schema,
                modes,
                require_modes=bool(available_modes(schema)),
            )
            candidates = self._target_candidate_map(
                controller,
                plan,
                source_ref=source_ref,
            )
            grouped = self._group_target_submission(plan, targets)
            used_global: set[str] = set()
            for group in plan.groups:
                chosen = grouped[group.group_id]
                if not (
                    group.min_targets
                    <= len(chosen)
                    <= group.max_targets
                ):
                    raise GameRuleError(
                        f"Target group {group.group_id} requires between "
                        f"{group.min_targets} and {group.max_targets} target(s)"
                    )
                if (
                    group.distinct
                    and not group.allow_reuse
                    and len(set(chosen)) != len(chosen)
                ):
                    raise GameRuleError(
                        f"Target group {group.group_id} requires distinct targets"
                    )
                legal = set(candidates[group.group_id])
                if any(ref not in legal for ref in chosen):
                    raise GameRuleError(
                        "Selected target is not legal for this target group"
                    )
                if any(
                    ref in grouped.get(other, ())
                    for other in group.different_from_groups
                    for ref in chosen
                ):
                    raise GameRuleError(
                        "Selected targets violate a different-target restriction"
                    )
                if plan.globally_distinct and any(
                    ref in used_global for ref in chosen
                ):
                    raise GameRuleError(
                        "Target groups require globally distinct targets"
                    )
                used_global.update(chosen)
            flattened = [
                ref
                for group in plan.groups
                for ref in grouped[group.group_id]
            ]
            return flattened, grouped
        except (GameRuleError, ValueError) as exc:
            self._increment_optimization(
                controller, "target_submissions_rejected"
            )
            if isinstance(exc, GameRuleError):
                raise
            raise GameRuleError(str(exc)) from exc

    @staticmethod
    def _stack_target_schema(
        item: StackItem,
        program: SemanticProgram | None,
    ) -> Mapping[str, Any] | None:
        if "target_schema_override" in item.context:
            return dict(item.context["target_schema_override"])
        return program.target_schema if program is not None else None

    def _stack_source_ref(self, item: StackItem) -> str:
        if (
            item.source_object_id
            and item.source_object_id in self.state.cards
        ):
            return self.state.cards[item.source_object_id].ref
        if (
            item.card_object_id
            and item.card_object_id in self.state.cards
        ):
            return self.state.cards[item.card_object_id].ref
        return item.ref

    def _begin_pending_trigger_target_selection(self) -> bool:
        for item in self.state.stack:
            if not item.context.get("trigger_target_selection_pending"):
                continue
            program = self.semantics.get(item.semantic_key)
            target_schema = self._stack_target_schema(item, program)
            if program is None or not target_schema:
                item.context.pop("trigger_target_selection_pending", None)
                continue
            public_schema = self._public_target_schema(
                item.controller,
                target_schema,
                source_ref=self._stack_source_ref(item),
            )
            if public_schema is None:
                self.state.stack.remove(item)
                self._log(
                    item.controller,
                    "stack.trigger.removed",
                    (
                        f"Removed {item.ref}: {item.label}; its mandatory "
                        "targets could not be chosen."
                    ),
                    {"stack": item.ref, "reason": "no_legal_targets"},
                    importance=2,
                )
                return self._begin_pending_trigger_target_selection()
            self.permissions.issue(
                kind="semantic.target",
                role="pilot",
                actors=[item.controller],
                allowed_actions=["choose"],
                payload_by_actor={
                    item.controller: {
                        "stack": item.ref,
                        "prompt": f"Choose legal targets for {program.label}.",
                        "target_schema": public_schema,
                        "legal_actions": [
                            {
                                "id": "choose",
                                "action": "choose",
                                "target_schema": public_schema,
                            }
                        ],
                    }
                },
                continuation={
                    "stack_ref": item.ref,
                    "trigger_creation": True,
                },
            )
            return True
        return False

    def _program_can_auto_resolve(self, item: StackItem) -> bool:
        program = self.semantics.get(item.semantic_key)
        target_schema = self._stack_target_schema(item, program)
        if (
            program
            and target_schema
            and not item.targets
            and not item.context.get("targets_chosen_at_creation")
        ):
            public_schema = self._public_target_schema(
                item.controller,
                target_schema,
                source_ref=self._stack_source_ref(item),
            )
            if public_schema is None:
                self._counter_stack_item(
                    item.ref,
                    destination=item.default_destination or "graveyard",
                    reason="no legal targets",
                    as_rule=True,
                    countered_by=item.controller,
                )
                self._grant_priority(self.state.active_player)
                return
            self.permissions.issue(
                kind="semantic.target",
                role="pilot",
                actors=[item.controller],
                allowed_actions=["choose"],
                payload_by_actor={
                    item.controller: {
                        "stack": item.ref,
                        "prompt": f"Choose legal targets for {program.label}.",
                        "target_schema": public_schema,
                        "legal_actions": [
                            {
                                "id": "choose",
                                "action": "choose",
                                "target_schema": public_schema,
                            }
                        ],
                    }
                },
                continuation={"stack_ref": item.ref},
            )
            return
        if (
            program
            and program.trust_level in {"trusted", "provisional", "intentionally_ignored"}
            and not program.requires_arbiter
        ):
            return True
        if item.kind == "spell" and item.card_object_id:
            record = self.card_record(item.card_object_id)
            if record and item.default_destination == "battlefield":
                oracle = record.oracle_text.casefold()
                semantic_markers = ("when ", "whenever ", "as ~ enters", "as this", "enters with", "you may have")
                return not any(marker in oracle for marker in semantic_markers)
        return False

    def _prepare_stack_resolution(self) -> None:
        if self.state.pending_trigger_batches and self._stabilize():
            return
        if not self.state.stack:
            self._advance_step()
            return
        item = self.state.stack[-1]
        if item.semantic_key == "builtin:storm":
            self._prepare_storm_resolution(item)
            return
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
                            "legal_actions": [
                                {
                                    "id": "choose",
                                    "action": "choose",
                                    "choice_schema": {
                                        "search_candidates": [
                                            option["id"] for option in options
                                        ],
                                        "may_fail_to_find": True,
                                        "entry_pay_life": "boolean",
                                    },
                                }
                            ],
                        }
                    },
                    continuation={"stack_ref": item.ref},
                )
                return
            self._resolve_fetch_land(item)
            return
        if item.semantic_key == "builtin:sacrifice-source":
            self._begin_resolve_item(
                item,
                [{"op": "sacrifice_if_present", "card": "$source"}],
                None,
                note="Mishra delayed sacrifice",
            )
            return
        program = self.semantics.get(item.semantic_key)
        trusted_generic_resolution = False
        if (
            program is None
            and item.kind == "spell"
            and item.card_object_id
        ):
            record = self.card_record(item.card_object_id)
            trusted_generic_resolution = bool(
                record and self._trusted_generic_spell(record)
            )
        if (
            self.state.config.semantic_policy == "trusted_only"
            and (
                (
                    program is None
                    and not trusted_generic_resolution
                )
                or (
                    program is not None
                    and (
                        not self.semantic_program_is_current_trusted(
                            program
                        )
                        or program.requires_arbiter
                    )
                )
            )
            and item.context.get("dynamic_effects") is None
        ):
            self._pause_for_unsupported_semantic(
                item=item,
                program=program,
            )
            return
        target_schema = self._stack_target_schema(item, program)
        if (
            program
            and target_schema
            and not item.targets
            and not item.context.get("targets_chosen_at_creation")
        ):
            # Triggered semantics acquire controller-chosen targets when the
            # trigger is put onto/processed from the stack. Spell targets were
            # already validated at cast time.
            self._program_can_auto_resolve(item)
            return
        if (
            program
            and program.trust_level in {"trusted", "provisional", "intentionally_ignored"}
            and not program.requires_arbiter
        ):
            option_effects = item.context.get("cast_option_effects")
            self._begin_resolve_item(
                item,
                (
                    [dict(effect) for effect in option_effects]
                    if option_effects is not None
                    else [
                        *program.effects,
                        *(
                            mode_effects(target_schema, item.modes)
                            if target_schema
                            else []
                        ),
                    ]
                ),
                program.destination or item.default_destination,
                note=program.notes,
            )
            return
        if item.context.get("dynamic_effects") is not None:
            self._begin_resolve_item(
                item,
                list(item.context.get("dynamic_effects") or []),
                item.default_destination,
                note=item.notes,
            )
            return
        if self._program_can_auto_resolve(item):
            self._begin_resolve_item(
                item,
                [],
                item.default_destination,
                note=(
                    "Permanent spell resolved to the battlefield; no entry "
                    "trigger semantics applied"
                ),
            )
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

    def _prepare_storm_resolution(self, item: StackItem) -> None:
        count = max(0, int(item.context.get("copy_count", 0)))
        template = dict(item.context.get("copy_template") or {})
        if count == 0:
            self.state.stack.remove(item)
            self._log(
                item.controller,
                "stack.resolve",
                f"Resolved {item.ref} {item.label} with no copies.",
                {"stack": item.ref, "copy_count": 0},
                importance=2,
            )
            self._grant_priority(self.state.active_player)
            return
        target_schema = template.get("target_schema")
        public_schema = (
            self._public_target_schema(
                item.controller,
                target_schema,
                source_ref=item.ref,
            )
            if isinstance(target_schema, Mapping)
            else None
        )
        copies = [
            {
                "copy_index": index,
                "default_targets": copy.deepcopy(
                    template.get("targets") or []
                ),
                "target_schema": copy.deepcopy(public_schema),
            }
            for index in range(count)
        ]
        self.permissions.issue(
            kind="semantic.storm",
            role="pilot",
            actors=[item.controller],
            allowed_actions=["choose"],
            payload_by_actor={
                item.controller: {
                    "stack": item.ref,
                    "prompt": (
                        "Choose targets for each storm copy, or keep the "
                        "copied targets."
                    ),
                    "copies": copies,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "copy_targets",
                                "copy_count": count,
                                "may_keep_default": True,
                            },
                        }
                    ],
                }
            },
            continuation={"stack_ref": item.ref},
        )

    def _complete_storm_choice(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        stack_ref = str(decision.continuation.get("stack_ref") or "")
        trigger = next(
            (
                candidate
                for candidate in self.state.stack
                if candidate.ref == stack_ref
                and candidate.semantic_key == "builtin:storm"
            ),
            None,
        )
        if trigger is None:
            raise GameRuleError("The storm trigger is no longer on the stack")
        count = max(0, int(trigger.context.get("copy_count", 0)))
        template = dict(trigger.context.get("copy_template") or {})
        submitted = response.get("copy_targets")
        if submitted is None:
            submitted = [
                copy.deepcopy(template.get("targets") or [])
                for _ in range(count)
            ]
        if not isinstance(submitted, list) or len(submitted) != count:
            raise GameRuleError(
                "Storm target selection must contain one entry per copy"
            )
        program = self.semantics.get(template.get("semantic_key"))
        target_schema = template.get("target_schema")
        copies: list[StackItem] = []
        for index, raw_targets in enumerate(submitted):
            selected = [
                str(value) for value in (raw_targets or [])
            ]
            defaults = [
                str(value)
                for value in template.get("targets") or []
            ]
            if selected == defaults:
                grouped = copy.deepcopy(
                    dict(template.get("target_groups") or {})
                )
            else:
                selected, grouped = self._validate_semantic_targets(
                    seat,
                    program,
                    selected,
                    modes=list(template.get("modes") or []),
                    source_ref=trigger.ref,
                    target_schema=(
                        target_schema
                        if isinstance(target_schema, Mapping)
                        else None
                    ),
                )
            copy_ref = self._next_ref("S")
            copies.append(
                StackItem(
                    stack_id=self._stable_runtime_id(
                        "stack", copy_ref
                    ),
                    ref=copy_ref,
                    kind="spell_copy",
                    controller=seat,
                    label=f"{template.get('label') or 'Spell'} copy",
                    semantic_key=template.get("semantic_key"),
                    targets=selected,
                    modes=list(template.get("modes") or []),
                    x_value=template.get("x_value"),
                    visibility=list(self.seats),
                    context={
                        "target_groups": grouped,
                        "target_snapshots": {
                            ref: self._target_snapshot(ref)
                            for ref in selected
                            if ref is not None
                        },
                        "targets_revalidated": False,
                    },
                )
            )
        self.state.stack.remove(trigger)
        self.state.stack.extend(copies)
        self._log(
            seat,
            "stack.storm.copy",
            f"{seat} created {len(copies)} storm copy/copies.",
            {
                "source_trigger": trigger.ref,
                "copies": [copy_item.ref for copy_item in copies],
                "targets": [
                    copy.deepcopy(copy_item.targets)
                    for copy_item in copies
                ],
            },
            importance=2,
        )
        self._grant_priority(self.state.active_player)

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
        item.context["pay_life"] = bool(
            response.get("entry_pay_life", response.get("pay_life", False))
        )
        self._resolve_fetch_land(item)

    def _complete_semantic_target(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        stack_ref = str(decision.continuation.get("stack_ref") or "")
        item = next(
            (candidate for candidate in self.state.stack if candidate.ref == stack_ref),
            None,
        )
        if item is None:
            raise GameRuleError("The targeted semantic object is no longer on the stack")
        program = self.semantics.get(item.semantic_key)
        targets = list(response.get("targets") or [])
        modes = [str(value) for value in response.get("modes") or []]
        validated, grouped = self._validate_semantic_targets(
            seat,
            program,
            targets,
            modes=modes,
            source_ref=self._stack_source_ref(item),
            target_schema=self._stack_target_schema(item, program),
        )
        item.targets = validated
        item.modes = modes
        item.context["target_groups"] = grouped
        item.context["target_snapshots"] = {
            ref: self._target_snapshot(ref) for ref in validated
        }
        item.context["targets_revalidated"] = False
        if decision.continuation.get("trigger_creation"):
            item.context.pop("trigger_target_selection_pending", None)
            item.context["targets_chosen_at_creation"] = True
            self._grant_priority(self.state.active_player)
        else:
            self._prepare_stack_resolution()

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
                semantic_events=True,
            )
            self._log(
                seat,
                "library.search",
                f"{seat} found {found.ref} {found.printed_name}.",
                {
                    "source": item.ref,
                    "object": found.ref,
                    "tapped": tapped,
                    "life_paid": (
                        2 if item.context.get("pay_life") and not tapped else 0
                    ),
                },
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
            self._counter_stack_item(
                item.ref,
                destination=str(response.get("destination") or "graveyard"),
                reason=action,
                as_rule=True,
                countered_by="arbiter",
            )
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
        if not self._revalidate_resolution_targets(item):
            return
        self._continue_resolution(
            stack_ref=item.ref,
            effects=[dict(effect) for effect in effects],
            destination=destination,
            note=note,
            instruction_pointer=0,
        )

    def _revalidate_resolution_targets(self, item: StackItem) -> bool:
        if item.context.get("targets_revalidated"):
            return True
        program = self.semantics.get(item.semantic_key)
        target_schema = self._stack_target_schema(item, program)
        if not program or target_schema is None:
            item.context["targets_revalidated"] = True
            return True
        try:
            plan = target_plan(
                target_schema,
                item.modes,
                require_modes=bool(available_modes(target_schema)),
            )
            candidates = self._target_candidate_map(
                item.controller,
                plan,
                source_ref=item.ref,
            )
            grouped = dict(item.context.get("target_groups") or {})
            if not grouped:
                grouped = self._group_target_submission(plan, item.targets)
        except (ValueError, GameRuleError):
            self._counter_stack_item(
                item.ref,
                destination=item.default_destination or "graveyard",
                reason="target schema invalid at resolution",
                as_rule=True,
                countered_by=item.controller,
            )
            self._grant_priority(self.state.active_player)
            return False
        updated: list[Any] = []
        valid_count = 0
        selected_count = 0
        current_groups: dict[str, list[Any]] = {}
        for group in plan.groups:
            legal = set(candidates[group.group_id])
            current: list[Any] = []
            for raw_ref in grouped.get(group.group_id, []):
                selected_count += 1
                ref = str(raw_ref)
                if ref in legal:
                    current.append(ref)
                    updated.append(ref)
                    valid_count += 1
                    continue
                current.append(None)
                updated.append(None)
                self._increment_optimization(
                    item.controller,
                    "targets_became_illegal_on_resolution",
                )
                self._log(
                    item.controller,
                    "target.illegal",
                    f"{ref} is no longer a legal target for {item.ref}.",
                    {
                        "stack": item.ref,
                        "target": ref,
                        "group": group.group_id,
                        "reason": "candidate_no_longer_matches",
                    },
                    importance=2,
                )
            current_groups[group.group_id] = current
        item.targets = updated
        item.context["target_groups_current"] = current_groups
        item.context["targets_revalidated"] = True
        if selected_count and valid_count == 0:
            self._counter_stack_item(
                item.ref,
                destination=item.default_destination or "graveyard",
                reason="all targets illegal on resolution",
                as_rule=True,
                countered_by=item.controller,
            )
            self._grant_priority(self.state.active_player)
            return False
        return True

    def _semantic_frame(
        self,
        item: StackItem,
        *,
        instruction_pointer: int,
        locals: Mapping[str, Any] | None = None,
        pending_choice_id: str | None = None,
    ) -> dict[str, Any]:
        program = self.semantics.get(item.semantic_key)
        return {
            "schema_version": 1,
            "semantic_program_id": item.semantic_key,
            "semantic_program_version": program.version if program else None,
            "stack_object": item.ref,
            "instruction_pointer": instruction_pointer,
            "locals": copy.deepcopy(dict(locals or {})),
            "controller": item.controller,
            "pending_choice_id": pending_choice_id,
        }

    def _validate_semantic_frame(
        self,
        frame: Mapping[str, Any],
        item: StackItem,
    ) -> None:
        if str(frame.get("stack_object") or "") != item.ref:
            raise GameRuleError("Semantic continuation stack object changed")
        if frame.get("semantic_program_id") != item.semantic_key:
            raise GameRuleError("Semantic continuation program changed")
        program = self.semantics.get(item.semantic_key)
        expected_version = program.version if program else None
        if frame.get("semantic_program_version") != expected_version:
            raise GameRuleError("Semantic continuation program version changed")

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
        if value == "$turn_sequence":
            return self.state.turn_sequence
        if value == "$targets":
            return [
                target
                for target in item.targets
                if target is not None
            ]
        attribute_match = re.fullmatch(
            r"\$target\.(?P<attribute>controller|owner|mana_value|colors|type_line)"
            r"[.\[](?P<index>\d+)\]?",
            value,
        )
        if attribute_match:
            index = int(attribute_match.group("index"))
            if index >= len(item.targets):
                raise GameRuleError(
                    f"Semantic program requested missing target {index}"
                )
            target_ref = item.targets[index]
            if target_ref is None:
                return None
            snapshot = dict(
                item.context.get("target_snapshots", {}).get(
                    str(target_ref),
                    self._target_snapshot(str(target_ref)),
                )
            )
            return snapshot.get(attribute_match.group("attribute"))
        target_match = re.fullmatch(r"\$target[.\[](?P<index>\d+)\]?", value)
        if target_match:
            index = int(target_match.group("index"))
            if index >= len(item.targets):
                raise GameRuleError(f"Semantic program requested missing target {index}")
            return item.targets[index]
        return value

    @staticmethod
    def _effect_has_missing_target(effect: Mapping[str, Any]) -> bool:
        return any(
            key in effect and effect.get(key) is None
            for key in ("target", "stack", "card", "object")
        )

    def _continue_resolution(
        self,
        *,
        stack_ref: str,
        effects: list[dict[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int = 0,
    ) -> None:
        item = next((candidate for candidate in self.state.stack if candidate.ref == stack_ref), None)
        if item is None:
            raise GameRuleError(f"Stack object {stack_ref} no longer exists")
        index = 0
        while index < len(effects):
            effect = self._semantic_value(effects[index], item)
            if self._effect_has_missing_target(effect):
                self._log(
                    item.controller,
                    "effect.target.skipped",
                    f"Skipped a target-dependent part of {item.ref}.",
                    {
                        "stack": item.ref,
                        "operation": effect.get("op"),
                        "reason": "that target is illegal",
                    },
                    importance=1,
                )
                index += 1
                continue
            if effect.get("op") == "choose_cards_apnap":
                self._issue_apnap_choice(
                    effect=effect,
                    continuation={
                        "stack_ref": stack_ref,
                        "effects": effects[index + 1 :],
                        "destination": destination,
                        "note": note,
                        "semantic_frame": self._semantic_frame(
                            item,
                            instruction_pointer=instruction_pointer + index,
                        ),
                    },
                )
                return
            if effect.get("op") == "search":
                self._begin_semantic_search(
                    item=item,
                    effect=effect,
                    remaining=effects[index + 1 :],
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + index,
                )
                return
            if effect.get("op") in {
                "choose_card_name",
                "choose_mana",
                "counter_unless_pay",
                "draw_optional_land",
                "choose_warform",
                "look_reorder_top",
                "pay_or_lose",
                "proliferate",
            }:
                self._begin_semantic_choice(
                    item=item,
                    effect=effect,
                    remaining=effects[index + 1 :],
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + index,
                )
                return
            self.apply_effect(effect, actor=item.controller, as_cost=False)
            index += 1
        # Remove the resolving object from stack only when all player choices
        # and effects have completed.
        self.state.stack.remove(item)
        entered: CardInstance | None = None
        if item.card_object_id:
            card = self.state.cards[item.card_object_id]
            if card.zone == "stack":
                entered = self.move_card(
                    card.object_id,
                    destination or item.default_destination or "graveyard",
                    controller=item.controller,
                    reason="spell resolved",
                    log=False,
                    semantic_events=True,
                )
        self._log(item.controller, "stack.resolve", f"Resolved {item.ref} {item.label}.", {"stack": item.ref, "effects": effects, "destination": destination, "note": note}, importance=2, changed_players=[item.controller])
        if self._stabilize():
            return
        self._grant_priority(self.state.active_player)

    def _begin_semantic_choice(
        self,
        *,
        item: StackItem,
        effect: Mapping[str, Any],
        remaining: Sequence[Mapping[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int = 0,
    ) -> None:
        op = str(effect["op"])
        seat = str(effect.get("player") or item.controller)
        context: dict[str, Any] = {"stack": item.ref, "operation": op}
        if op == "choose_mana":
            context.update(
                {
                    "prompt": "Choose a mana color.",
                    "options": list("WUBRGC"),
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "choice",
                                "legal_values": list("WUBRGC"),
                            },
                        }
                    ],
                }
            )
        elif op == "choose_card_name":
            context.update(
                {
                    "prompt": "Choose a Magic card name.",
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "card_name",
                                "type": "card_name",
                                "nonempty": True,
                            },
                        }
                    ],
                }
            )
        elif op == "look_reorder_top":
            count = max(0, int(effect.get("count", 1)))
            looked = self.apply_effect(
                {
                    "op": "look_top",
                    "player": seat,
                    "viewer": seat,
                    "count": count,
                    "reason": item.label,
                },
                actor=item.controller,
            )
            options = [str(value) for value in (looked or [])]
            if not options:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {**dict(effect), "_looked_refs": options}
            context.update(
                {
                    "prompt": (
                        "Put the looked-at cards back in top-to-bottom "
                        "order."
                    ),
                    "cards": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat,
                                ref,
                                zones={"library"},
                            ).printed_name,
                        }
                        for ref in options
                    ],
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "cards",
                                "legal_refs": options,
                                "minimum": len(options),
                                "maximum": len(options),
                                "distinct": True,
                                "order": "top_to_bottom",
                            },
                        }
                    ],
                }
            )
        elif op == "counter_unless_pay":
            requirements = {
                key: int((effect.get("cost") or {}).get(key, 0))
                for key in (
                    "GENERIC",
                    "W",
                    "U",
                    "B",
                    "R",
                    "G",
                    "C",
                )
            }
            payable = self._cost_is_affordable(seat, requirements)
            context.update(
                {
                    "prompt": "Pay the stated cost to prevent the spell from being countered.",
                    "cost": requirements,
                    "payable": payable,
                    "target_stack": effect.get("stack"),
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "pay",
                                "legal_values": (
                                    [True, False] if payable else [False]
                                ),
                            },
                        }
                    ],
                }
            )
        elif op == "proliferate":
            objects = [
                self.state.cards[object_id].ref
                for active_seat in self.active_seats
                for object_id in self.state.players[
                    active_seat
                ].zones["battlefield"]
                if any(
                    amount > 0
                    for amount in self.state.cards[
                        object_id
                    ].counters.values()
                )
            ]
            players = [
                active_seat
                for active_seat in self.active_seats
                if self.state.players[active_seat].poison > 0
                or self.state.players[active_seat].energy > 0
            ]
            context.update(
                {
                    "prompt": "Choose any number of permanents and/or players with counters to proliferate.",
                    "options": [*objects, *players],
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "objects",
                                "minimum": 0,
                                "maximum": len(objects) + len(players),
                                "legal_refs": [*objects, *players],
                                "distinct": True,
                            },
                        }
                    ],
                }
            )
        elif op == "pay_or_lose":
            requirements = {
                key: int((effect.get("cost") or {}).get(key, 0))
                for key in ("GENERIC", "W", "U", "B", "R", "G", "C")
            }
            payable = self._cost_is_affordable(seat, requirements)
            context.update(
                {
                    "prompt": (
                        "Pay the delayed Pact cost or lose the game."
                    ),
                    "cost": requirements,
                    "payable": payable,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "pay",
                                "legal_values": (
                                    [True, False] if payable else [False]
                                ),
                            },
                        }
                    ],
                }
            )
        elif op == "draw_optional_land":
            self.draw(seat, 1, reason=item.label)
            options = [
                self.state.cards[object_id].ref
                for object_id in self.state.players[seat].zones["hand"]
                if (
                    self.card_record(object_id)
                    and self.card_record(object_id).is_land
                )
            ]
            repeat_threshold = effect.get("repeat_if_land_count")
            repeat = bool(
                repeat_threshold
                and sum(
                    bool(self.card_record(object_id) and self.card_record(object_id).is_land)
                    for object_id in self.state.players[seat].zones["battlefield"]
                    if self.state.cards[object_id].controller == seat
                )
                >= int(repeat_threshold)
            )
            if not options:
                resumed = list(remaining)
                if repeat:
                    repeated = dict(effect)
                    repeated.pop("repeat_if_land_count", None)
                    resumed.insert(0, repeated)
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=resumed,
                    destination=destination,
                    note=note,
                )
                return
            context.update(
                {
                    "prompt": "You may put a land card from your hand onto the battlefield tapped.",
                    "optional": True,
                    "options": options,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "card",
                                "legal_refs": options,
                                "optional": True,
                            },
                        }
                    ],
                }
            )
            effect = {**dict(effect), "_repeat": repeat}
        else:
            options = [
                self.state.cards[object_id].ref
                for object_id in self.state.players[seat].zones["battlefield"]
                if self.state.cards[object_id].controller == seat
                and "artifact"
                in str(
                    self._effective_card_data(object_id).get("type_line") or ""
                ).casefold()
                and "creature"
                not in str(
                    self._effective_card_data(object_id).get("type_line") or ""
                ).casefold()
            ]
            if not options:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                )
                return
            context.update(
                {
                    "prompt": "Choose a noncreature artifact you control for Mishra's Warform.",
                    "options": options,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "card",
                                "legal_refs": options,
                            },
                        }
                    ],
                }
            )
        decision = self.permissions.issue(
            kind="semantic.choice",
            role="pilot",
            actors=[seat],
            allowed_actions=["choose"],
            payload_by_actor={seat: context},
            continuation={
                "stack_ref": item.ref,
                "effect": copy.deepcopy(dict(effect)),
                "remaining": copy.deepcopy(list(remaining)),
                "destination": destination,
                "note": note,
                "semantic_frame": self._semantic_frame(
                    item,
                    instruction_pointer=instruction_pointer,
                ),
            },
        )
        decision.continuation["semantic_frame"]["pending_choice_id"] = (
            decision.decision_id
        )

    def _complete_semantic_choice(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        continuation = decision.continuation
        stack_ref = str(continuation["stack_ref"])
        item = next(
            (candidate for candidate in self.state.stack if candidate.ref == stack_ref),
            None,
        )
        if item is None:
            raise GameRuleError("The semantic choice's stack object no longer exists")
        frame = dict(continuation.get("semantic_frame") or {})
        if frame:
            self._validate_semantic_frame(frame, item)
        effect = dict(continuation["effect"])
        op = str(effect["op"])
        if op == "choose_mana":
            choice = str(
                response.get("choice")
                or response.get("color")
                or response.get("mana")
                or ""
            ).upper()
            if choice not in "WUBRGC" or len(choice) != 1:
                raise GameRuleError("Choose one of W, U, B, R, G, or C")
            amount = int(effect.get("amount", 1))
            self.state.players[seat].mana_pool[choice] += amount
            self._log(
                seat,
                "mana.semantic",
                f"{seat} added {amount} {choice} from {item.label}.",
                {"source": item.ref, "bundle": {choice: amount}},
                importance=1,
                changed_players=[seat],
            )
        elif op == "choose_card_name":
            raw_name = str(response.get("card_name") or "").strip()
            if not raw_name:
                raise GameRuleError("A card name is required")
            try:
                chosen = self.card_db.lookup(raw_name).name
            except KeyError as exc:
                raise GameRuleError(
                    f"{raw_name!r} is not a recognized Magic card name"
                ) from exc
            source_id = item.card_object_id or item.source_object_id
            if source_id not in self.state.cards:
                raise GameRuleError(
                    "The naming effect no longer has a source object"
                )
            source = self.state.cards[source_id]
            source.annotations["chosen_name"] = chosen
            self._log(
                seat,
                "card.name.chosen",
                f"{seat} chose {chosen} for {source.ref}.",
                {"source": source.ref, "card_name": chosen},
                importance=2,
                changed_objects=[source.object_id],
            )
        elif op == "look_reorder_top":
            expected = [
                str(value)
                for value in effect.get("_looked_refs", [])
            ]
            selected = [
                str(value)
                for value in response.get(
                    "cards",
                    response.get("order", []),
                )
            ]
            if (
                len(selected) != len(set(selected))
                or sorted(selected) != sorted(expected)
            ):
                raise GameRuleError(
                    "Top-card order must contain every looked-at card "
                    "exactly once"
                )
            self.apply_effect(
                {
                    "op": "reorder_top",
                    "player": seat,
                    "viewer": seat,
                    "cards": selected,
                    "reason": item.label,
                },
                actor=item.controller,
            )
        elif op == "counter_unless_pay":
            requirements = {
                key: int((effect.get("cost") or {}).get(key, 0))
                for key in (
                    "GENERIC",
                    "W",
                    "U",
                    "B",
                    "R",
                    "G",
                    "C",
                )
            }
            target_stack = str(effect.get("stack") or "")
            if bool(response.get("pay", False)):
                if not self._cost_is_affordable(seat, requirements):
                    raise GameRuleError(
                        "The counter-prevention cost is no longer payable"
                    )
                self._pay_for_cost(
                    seat,
                    requirements,
                    {"pay": "auto"},
                )
                self._log(
                    seat,
                    "counter.unless.paid",
                    f"{seat} paid to prevent {target_stack} from being countered.",
                    {"stack": target_stack, "cost": requirements},
                    importance=2,
                    changed_players=[seat],
                )
            elif any(
                candidate.ref == target_stack
                for candidate in self.state.stack
            ):
                self._counter_stack_item(
                    target_stack,
                    reason=item.label,
                    countered_by=item.controller,
                )
        elif op == "proliferate":
            selected = [
                str(value)
                for value in response.get(
                    "objects", response.get("choices", [])
                )
            ]
            legal = set(
                decision.payload_by_actor.get(seat, {}).get(
                    "options", []
                )
            )
            if (
                len(selected) != len(set(selected))
                or any(value not in legal for value in selected)
            ):
                raise GameRuleError(
                    "Proliferate choices must be distinct eligible objects"
                )
            changed_objects: list[str] = []
            changed_players: list[str] = []
            for value in selected:
                if value in self.state.players:
                    player = self.state.players[value]
                    if player.poison > 0:
                        player.poison += 1
                    if player.energy > 0:
                        player.energy += 1
                    changed_players.append(value)
                    continue
                card = self._resolve_object(
                    seat, value, zones={"battlefield"}
                )
                for name, amount in list(card.counters.items()):
                    if amount > 0:
                        card.counters[name] = amount + 1
                changed_objects.append(card.object_id)
            self._log(
                seat,
                "counter.proliferate",
                f"{seat} proliferated {len(selected)} object(s).",
                {"objects": selected},
                importance=2,
                changed_objects=changed_objects,
                changed_players=changed_players,
            )
        elif op == "pay_or_lose":
            requirements = {
                key: int((effect.get("cost") or {}).get(key, 0))
                for key in ("GENERIC", "W", "U", "B", "R", "G", "C")
            }
            if bool(response.get("pay", False)):
                if not self._cost_is_affordable(seat, requirements):
                    raise GameRuleError(
                        "The delayed Pact cost is no longer payable"
                    )
                self._pay_for_cost(
                    seat,
                    requirements,
                    {"pay": "auto"},
                )
                self._log(
                    seat,
                    "pact.paid",
                    f"{seat} paid the delayed Pact cost.",
                    {"cost": requirements, "stack": item.ref},
                    importance=2,
                    changed_players=[seat],
                )
            else:
                self._eliminate_players(
                    [seat],
                    reason="failed to pay Pact of Negation",
                )
        elif op == "draw_optional_land":
            selected = response.get("card")
            options = set(
                decision.payload_by_actor.get(seat, {}).get("options") or []
            )
            if selected is not None:
                if str(selected) not in options:
                    raise GameRuleError("Selected land is not a legal option")
                card = self._resolve_object(
                    seat, str(selected), zones={"hand"}, owned_only=True
                )
                self.move_card(
                    card.object_id,
                    "battlefield",
                    controller=seat,
                    tapped=True,
                    reason=item.label,
                    semantic_events=True,
                )
        elif op == "choose_warform":
            selected = str(response.get("card") or "")
            options = set(
                decision.payload_by_actor.get(seat, {}).get("options") or []
            )
            if selected not in options:
                raise GameRuleError("Selected artifact is not a legal Warform target")
            self._create_mishra_warform(
                seat,
                selected,
                reason=item.label,
            )
        if item not in self.state.stack:
            return
        remaining = [dict(value) for value in continuation.get("remaining", [])]
        if op == "draw_optional_land" and effect.get("_repeat"):
            repeated = dict(effect)
            repeated.pop("_repeat", None)
            repeated.pop("repeat_if_land_count", None)
            remaining.insert(0, repeated)
        self._continue_resolution(
            stack_ref=stack_ref,
            effects=remaining,
            destination=continuation.get("destination"),
            note=str(continuation.get("note") or ""),
            instruction_pointer=int(frame.get("instruction_pointer", 0)) + 1,
        )

    def _create_mishra_warform(
        self,
        seat: str,
        selected: str,
        *,
        reason: str,
    ) -> str:
        original = self._resolve_object(
            seat,
            selected,
            zones={"battlefield"},
            controlled_only=True,
        )
        types, _, _ = self._type_parts(
            str(
                self._effective_card_data(original).get("type_line")
                or ""
            )
        )
        if "artifact" not in types or "creature" in types:
            raise GameRuleError(
                "Mishra's Warform requires a noncreature artifact you control"
            )
        created_ref = self.create_token(
            seat,
            name="Mishra's Warform",
            copy_of=selected,
            characteristics={
                "name": "Mishra's Warform",
                "type_line": "Artifact Creature — Construct",
                "power": "4",
                "toughness": "4",
                "mana_value": 0,
            },
            temporary_keywords=["Haste"],
            reason=reason,
        )[0]
        created = self._resolve_object(
            seat,
            created_ref,
            zones={"battlefield"},
            controlled_only=True,
        )
        self.schedule_delayed_trigger(
            controller=seat,
            label=f"Sacrifice {created_ref}",
            event_kind="step.begin",
            condition={
                "phase": "ending",
                "step": "end_step",
                "player": "$controller",
            },
            stack_template={
                "label": f"Sacrifice {created_ref}",
                "semantic_key": "builtin:sacrifice-source",
            },
            source_object_id=created.object_id,
            once=True,
        )
        return created_ref

    @staticmethod
    def _search_type_words(type_line: str) -> tuple[set[str], set[str]]:
        normalized = type_line.replace("—", "-")
        left, _, right = normalized.partition("-")
        return (
            {word.casefold() for word in re.findall(r"[A-Za-z]+", left)},
            {word.casefold() for word in re.findall(r"[A-Za-z]+", right)},
        )

    def _search_candidate_matches(
        self,
        card: CardInstance,
        selector: Mapping[str, Any],
    ) -> bool:
        record = self.card_record(card)
        if record is None:
            return False
        type_words, subtype_words = self._search_type_words(record.type_line)
        required_types = {
            str(value).casefold() for value in selector.get("types") or []
        }
        required_subtypes = {
            str(value).casefold() for value in selector.get("subtypes") or []
        }
        required_supertypes = {
            str(value).casefold()
            for value in selector.get("supertypes") or []
        }
        if not required_types.issubset(type_words):
            return False
        if not required_subtypes.issubset(subtype_words):
            return False
        if not required_supertypes.issubset(type_words):
            return False
        names = {
            str(value).casefold() for value in selector.get("names") or []
        }
        if names and record.name.casefold() not in names:
            return False
        colors = {str(value).upper() for value in selector.get("colors") or []}
        if colors and not colors.issubset(set(record.colors)):
            return False
        mana_value = selector.get("mana_value")
        if mana_value is not None:
            constraint = (
                dict(mana_value)
                if isinstance(mana_value, Mapping)
                else {"equal": mana_value}
            )
            if (
                constraint.get("equal") is not None
                and record.mana_value != float(constraint["equal"])
            ):
                return False
            if (
                constraint.get("minimum") is not None
                and record.mana_value < float(constraint["minimum"])
            ):
                return False
            if (
                constraint.get("maximum") is not None
                and record.mana_value > float(constraint["maximum"])
            ):
                return False
        predicate = selector.get("predicate")
        if predicate in {None, ""}:
            return True
        if predicate == "noncreature":
            return "creature" not in type_words
        if predicate == "instant_or_sorcery":
            return bool(type_words.intersection({"instant", "sorcery"}))
        if predicate == "mana_cost_0_or_1":
            return record.mana_cost in {"{0}", "{1}"}
        if predicate == "land_with_basic_land_type":
            return (
                "land" in type_words
                and bool(
                    subtype_words.intersection(
                        {"plains", "island", "swamp", "mountain", "forest"}
                    )
                )
            )
        raise GameRuleError(f"Unsupported search predicate {predicate!r}")

    def _semantic_search_options(
        self,
        seat: str,
        effect: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        raw_zone = effect.get("zone") or "library"
        zones = (
            [str(value) for value in raw_zone]
            if isinstance(raw_zone, Sequence)
            and not isinstance(raw_zone, (str, bytes))
            else [str(raw_zone)]
        )
        if any(
            zone not in {"library", "graveyard", "hand", "exile"}
            for zone in zones
        ):
            raise GameRuleError(
                f"Unsupported semantic search zone {raw_zone!r}"
            )
        selector = dict(effect.get("selector") or {})
        return [
            {
                "id": self.state.cards[object_id].ref,
                "name": self.state.cards[object_id].printed_name,
            }
            for zone in zones
            for object_id in self.state.players[seat].zones[zone]
            if self._search_candidate_matches(self.state.cards[object_id], selector)
        ]

    @staticmethod
    def _search_is_restrictive(selector: Mapping[str, Any]) -> bool:
        return any(
            selector.get(key)
            for key in (
                "types",
                "subtypes",
                "supertypes",
                "colors",
                "names",
                "mana_value",
                "mana_value_total",
                "predicate",
            )
        )

    def _begin_semantic_search(
        self,
        *,
        item: StackItem,
        effect: Mapping[str, Any],
        remaining: Sequence[Mapping[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int,
    ) -> None:
        seat = str(effect.get("searching_player") or item.controller)
        self._require_seat(seat, in_game=True)
        options = self._semantic_search_options(seat, effect)
        count = dict(effect.get("count") or {})
        minimum = max(0, int(count.get("minimum", 1)))
        maximum = max(minimum, int(count.get("maximum", minimum)))
        maximum = min(maximum, len(options))
        selector = dict(effect.get("selector") or {})
        raw_search_zone = effect.get("zone") or "library"
        search_zones = (
            [str(value) for value in raw_search_zone]
            if isinstance(raw_search_zone, Sequence)
            and not isinstance(raw_search_zone, (str, bytes))
            else [str(raw_search_zone)]
        )
        rules_may_fail = bool(effect.get("optional", False)) or (
            "library" in search_zones
            and self._search_is_restrictive(selector)
        )
        minimum_choice = 0 if rules_may_fail else min(minimum, len(options))
        entry_choice = any(
            (
                (record := self.card_record(
                    next(
                        card.object_id
                        for card in self.state.cards.values()
                        if card.ref == option["id"]
                    )
                ))
                is not None
                and "you may pay 2 life. if you don't, it enters tapped"
                in record.oracle_text.casefold()
            )
            for option in options
        )
        choice_schema: dict[str, Any] = {
            "field": "search_cards",
            "minimum": minimum_choice,
            "maximum": maximum,
            "legal_refs": [option["id"] for option in options],
            "rules_may_fail_to_find": rules_may_fail,
        }
        if entry_choice and str(effect.get("destination")) == "battlefield":
            choice_schema["entry_pay_life"] = "boolean"
        frame = self._semantic_frame(
            item,
            instruction_pointer=instruction_pointer,
            locals={
                "searching_player": seat,
                "source_object": (
                    self.state.cards[item.source_object_id].ref
                    if item.source_object_id in self.state.cards
                    else (
                        self.state.cards[item.card_object_id].ref
                        if item.card_object_id in self.state.cards
                        else None
                    )
                ),
            },
        )
        decision = self.permissions.issue(
            kind="semantic.search",
            role="pilot",
            actors=[seat],
            allowed_actions=["choose"],
            payload_by_actor={
                seat: {
                    "stack": item.ref,
                    "operation": "search",
                    "instruction": str(
                        effect.get("instruction")
                        or "Choose card(s) matching the search specification."
                    ),
                    "search_cards": options,
                    "search_spec": {
                        "zone": copy.deepcopy(raw_search_zone),
                        "selector": selector,
                        "count": {
                            "minimum": minimum_choice,
                            "maximum": maximum,
                        },
                        "destination": effect.get("destination"),
                        "reveal": bool(effect.get("reveal", False)),
                        "shuffle_after": bool(
                            effect.get("shuffle_after", True)
                        ),
                        "rules_may_fail_to_find": rules_may_fail,
                    },
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": choice_schema,
                        }
                    ],
                }
            },
            continuation={
                "stack_ref": item.ref,
                "effect": copy.deepcopy(dict(effect)),
                "remaining": copy.deepcopy(list(remaining)),
                "destination": destination,
                "note": note,
                "semantic_frame": frame,
            },
        )
        decision.continuation["semantic_frame"]["pending_choice_id"] = (
            decision.decision_id
        )

    def _complete_semantic_search(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        continuation = decision.continuation
        stack_ref = str(continuation.get("stack_ref") or "")
        item = next(
            (
                candidate
                for candidate in self.state.stack
                if candidate.ref == stack_ref
            ),
            None,
        )
        if item is None:
            raise GameRuleError(
                "The semantic search's stack object no longer exists"
            )
        frame = dict(continuation.get("semantic_frame") or {})
        self._validate_semantic_frame(frame, item)
        effect = dict(continuation.get("effect") or {})
        options = {
            option["id"]
            for option in self._semantic_search_options(seat, effect)
        }
        raw_values = (
            response.get("search_cards")
            or response.get("cards")
            or (
                [response.get("search_card") or response.get("card")]
                if response.get("search_card") is not None
                or response.get("card") is not None
                else []
            )
        )
        values = [str(value) for value in raw_values if value is not None]
        if len(values) != len(set(values)) or any(
            value not in options for value in values
        ):
            raise GameRuleError(
                "Selected search result is no longer a legal candidate"
            )
        count = dict(effect.get("count") or {})
        minimum = max(0, int(count.get("minimum", 1)))
        maximum = max(minimum, int(count.get("maximum", minimum)))
        selector = dict(effect.get("selector") or {})
        raw_search_zone = effect.get("zone") or "library"
        search_zones = (
            [str(value) for value in raw_search_zone]
            if isinstance(raw_search_zone, Sequence)
            and not isinstance(raw_search_zone, (str, bytes))
            else [str(raw_search_zone)]
        )
        rules_may_fail = bool(effect.get("optional", False)) or (
            "library" in search_zones
            and self._search_is_restrictive(selector)
        )
        required = 0 if rules_may_fail else min(minimum, len(options))
        if not required <= len(values) <= min(maximum, len(options)):
            raise GameRuleError(
                f"Search requires between {required} and "
                f"{min(maximum, len(options))} selection(s)"
            )
        total_constraint = selector.get("mana_value_total")
        if total_constraint is not None:
            constraint = (
                dict(total_constraint)
                if isinstance(total_constraint, Mapping)
                else {"maximum": total_constraint}
            )
            total = sum(
                float(
                    self.card_record(
                        self._resolve_object(
                            seat,
                            ref,
                            zones=set(search_zones),
                            owned_only=True,
                        )
                    ).mana_value
                )
                for ref in values
            )
            if (
                constraint.get("minimum") is not None
                and total < float(constraint["minimum"])
            ) or (
                constraint.get("maximum") is not None
                and total > float(constraint["maximum"])
            ):
                raise GameRuleError(
                    "Selected search cards do not satisfy the aggregate "
                    "mana-value constraint"
                )
        destination_spec = str(effect.get("destination") or "hand")
        position = str(effect.get("destination_position") or "top")
        destination = destination_spec
        if destination_spec in {"library_top", "top_of_library"}:
            destination, position = "library", "top"
        elif destination_spec in {"library_bottom", "bottom_of_library"}:
            destination, position = "library", "bottom"
        if destination not in {
            "hand",
            "battlefield",
            "graveyard",
            "exile",
            "library",
        }:
            raise GameRuleError(
                f"Unsupported semantic search destination {destination_spec!r}"
            )
        reveal = bool(effect.get("reveal", False))
        moved: list[CardInstance] = []
        for ref in values:
            card = self._resolve_object(
                seat,
                ref,
                zones=set(search_zones),
                owned_only=True,
            )
            tapped = bool(effect.get("enters_tapped_override", False))
            if (
                destination == "battlefield"
                and effect.get("enters_tapped_override") is None
            ):
                record = self.card_record(card)
                tapped = bool(
                    record
                    and record.is_land
                    and self._land_enters_tapped(
                        seat,
                        record,
                        {
                            "pay_life": bool(
                                response.get(
                                    "entry_pay_life",
                                    response.get("pay_life", False),
                                )
                            )
                        },
                    )
                )
                if (
                    record
                    and "you may pay 2 life. if you don't, it enters tapped"
                    in record.oracle_text.casefold()
                    and bool(
                        response.get(
                            "entry_pay_life",
                            response.get("pay_life", False),
                        )
                    )
                    and not tapped
                ):
                    self.state.players[seat].life -= 2
            moved.append(
                self.move_card(
                    card.object_id,
                    destination,
                    controller=seat if destination == "battlefield" else None,
                    tapped=tapped,
                    position=position,
                    reveal_to=self.seats if reveal else None,
                    reason=f"{item.label} search",
                    log=False,
                    semantic_events=destination == "battlefield",
                )
            )
        public_choice = reveal or destination in {
            "battlefield",
            "graveyard",
            "exile",
        }
        public_details: dict[str, Any] = {
            "source": item.ref,
            "destination": destination_spec,
            "count": len(moved),
            "revealed": reveal,
        }
        if public_choice:
            public_details["objects"] = [card.ref for card in moved]
            if len(moved) == 1:
                public_details["object"] = moved[0].ref
        self._log(
            seat,
            "library.search",
            f"{seat} searched {effect.get('zone', 'library')} and found "
            f"{len(moved)} card(s).",
            public_details,
            importance=2,
            changed_objects=[card.object_id for card in moved],
            changed_players=[seat],
        )
        self._log(
            seat,
            "library.search.private",
            f"{seat} selected {len(moved)} private search object(s).",
            {
                **public_details,
                "objects": [card.ref for card in moved],
            },
            visibility=[seat, "analyst"],
            importance=0,
            changed_objects=[card.object_id for card in moved],
            changed_players=[seat],
        )
        if bool(effect.get("shuffle_after", True)):
            self.shuffle_library(seat, reason=f"{item.label} resolved")
        item.context.setdefault("semantic_continuations", []).append(
            {
                **frame,
                "pending_choice_id": decision.decision_id,
                "choice_result": [card.ref for card in moved],
                "resumed": True,
            }
        )
        self._continue_resolution(
            stack_ref=stack_ref,
            effects=[
                dict(value)
                for value in continuation.get("remaining", [])
            ],
            destination=continuation.get("destination"),
            note=str(continuation.get("note") or ""),
            instruction_pointer=int(frame.get("instruction_pointer", 0)) + 1,
        )

    def _stack_item_can_be_countered(self, item: StackItem) -> bool:
        if item.context.get("cant_be_countered"):
            return False
        if item.card_object_id:
            card = self.state.cards[item.card_object_id]
            if card.annotations.get("cant_be_countered"):
                return False
            record = self.card_record(card)
            if (
                record
                and "this spell can't be countered"
                in record.oracle_text.casefold()
            ):
                return False
        return True

    def _counter_stack_item(
        self,
        value: str,
        *,
        destination: str = "graveyard",
        reason: str = "countered",
        as_rule: bool = False,
        countered_by: str | None = None,
    ) -> StackItem:
        item = next((candidate for candidate in self.state.stack if candidate.ref == value or candidate.stack_id == value), None)
        if item is None:
            raise GameRuleError(f"No stack object {value}")
        if not as_rule and not self._stack_item_can_be_countered(item):
            self._log(
                countered_by,
                "stack.counter.failed",
                f"{item.ref} {item.label} could not be countered.",
                {
                    "stack": item.ref,
                    "reason": reason,
                    "cant_be_countered": True,
                },
                importance=2,
            )
            return item
        self.state.stack.remove(item)
        if item.card_object_id:
            card = self.state.cards[item.card_object_id]
            if card.zone == "stack":
                self.move_card(card.object_id, destination, reason=reason, log=False)
        telemetry_seat = (
            countered_by
            if countered_by in self.state.players
            else item.controller
        )
        self._increment_optimization(
            telemetry_seat,
            (
                "spells_countered_by_rules"
                if as_rule
                else "spells_countered_by_effect"
            ),
        )
        self._log(
            countered_by,
            "stack.counter",
            f"{item.ref} {item.label} was countered.",
            {
                "stack": item.ref,
                "destination": destination,
                "reason": reason,
                "counter_kind": "rules" if as_rule else "effect",
            },
            importance=2,
        )
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
        destination = {
            "sacrifice": "graveyard",
            "discard": "graveyard",
            "exile": "exile",
        }.get(then)
        if destination is None:
            raise GameRuleError(f"Unsupported APNAP continuation {then}")
        self._move_cards_simultaneously(
            [(object_id, destination) for object_id in selected_objects],
            reason=(
                f"simultaneous APNAP {then}"
                if then != "exile"
                else "simultaneous APNAP choice"
            ),
            log=False,
        )
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
        if not any(
            not candidate["sick"] or candidate["haste"]
            for candidate in candidates
        ):
            self.state.combat.attackers_declared = True
            self.state.combat.defending_players = []
            self._grant_priority(active)
            return
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
        self._move_cards_simultaneously(
            [(object_id, "graveyard") for object_id in objects],
            reason="cleanup discard",
            log=False,
        )
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
        base += int(
            dict(card.annotations.get("until_end_of_turn") or {}).get(
                stat, 0
            )
        )
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
                simultaneous = [
                    (object_id, "graveyard")
                    for object_id in unique_preserving_order(move_to_grave)
                    if self.state.cards[object_id].zone == "battlefield"
                ]
                self._move_cards_simultaneously(
                    simultaneous,
                    reason="state-based action",
                    log=False,
                )
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
            if self._begin_pending_semantic_trigger_batch():
                return True
            if self._begin_pending_trigger_target_selection():
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
        moved = [
            object_id
            for object_id in ids
            if object_id != card.object_id
            and self.state.cards[object_id].zone == "battlefield"
        ]
        self._move_cards_simultaneously(
            [(object_id, "graveyard") for object_id in moved],
            reason="legend rule",
            log=False,
        )
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
                    hidden_identity = card.zone in HIDDEN_ZONES or card.face_down
                    if card.zone == "stack":
                        self.state.stack = [item for item in self.state.stack if item.card_object_id != card.object_id]
                        card.zone = "outside"
                    elif hidden_identity:
                        # A player leaving is not a reveal instruction. Preserve
                        # object identity authoritatively while retaining only
                        # knowledge that existed before the player left.
                        self._remove_from_zone(card)
                        self._reset_zone_change(card, "outside")
                        card.zone = "outside"
                        card.annotations["hidden_after_owner_left"] = True
                        card.known_to = sorted(set(card.known_to).union({card.owner}))
                        card.revealed_to = [
                            viewer
                            for viewer in card.revealed_to
                            if viewer in card.known_to
                        ]
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
        if op == "mana":
            seat = str(effect.get("player") or actor)
            color = str(effect.get("color") or "C").upper()
            amount = int(effect.get("amount", 1))
            if color not in "WUBRGC" or len(color) != 1 or amount < 0:
                raise GameRuleError("Invalid semantic mana effect")
            self.state.players[seat].mana_pool[color] += amount
            self._log(
                actor,
                "mana.semantic",
                f"{seat} added {amount} {color}.",
                {"bundle": {color: amount}, "reason": reason},
                importance=1,
                changed_players=[seat],
            )
            return amount
        if op == "delayed_mana":
            seat = str(effect.get("player") or actor)
            amount = int(effect.get("amount", 0))
            return self.schedule_delayed_trigger(
                controller=seat,
                label=str(effect.get("label") or "Delayed mana"),
                event_kind="step.begin",
                condition={
                    "player": seat,
                    "phase": ["precombat_main", "postcombat_main"],
                    "step": "main",
                },
                stack_template={
                    "label": str(effect.get("label") or "Delayed mana"),
                    "context": {
                        "dynamic_effects": [
                            {
                                "op": "mana",
                                "player": seat,
                                "color": str(effect.get("color") or "C"),
                                "amount": amount,
                            }
                        ]
                    },
                },
                once=True,
            ).ref
        if op == "delayed_pact_payment":
            seat = str(effect.get("player") or actor)
            cost = dict(effect.get("cost") or {})
            return self.schedule_delayed_trigger(
                controller=seat,
                label=str(
                    effect.get("label")
                    or "Pact of Negation delayed payment"
                ),
                event_kind="step.begin",
                condition={
                    "player": seat,
                    "phase": "beginning",
                    "step": "upkeep",
                    "after_turn_sequence": self.state.turn_sequence,
                },
                stack_template={
                    "label": str(
                        effect.get("label")
                        or "Pact of Negation delayed payment"
                    ),
                    "context": {
                        "dynamic_effects": [
                            {
                                "op": "pay_or_lose",
                                "player": seat,
                                "cost": cost,
                            }
                        ]
                    },
                },
                once=True,
            ).ref
        if op in {"move", "sacrifice", "destroy", "exile", "bounce", "discard"}:
            card = self._resolve_object(actor, str(effect["card"]))
            if op == "destroy":
                keywords = {
                    str(value).casefold()
                    for value in self._effective_card_data(card).get(
                        "keywords", []
                    )
                }
                if "indestructible" in keywords:
                    self._log(
                        actor,
                        "effect.destroy.prevented",
                        f"{card.ref} was not destroyed because it is indestructible.",
                        {"object": card.ref, "reason": reason},
                        importance=1,
                    )
                    return None
            destination = {
                "sacrifice": "graveyard",
                "destroy": "graveyard",
                "exile": "exile",
                "bounce": "hand",
                "discard": "graveyard",
            }.get(op, str(effect.get("destination") or "graveyard"))
            return self.move_card(
                card.object_id,
                destination,
                controller=effect.get("controller"),
                tapped=bool(effect.get("tapped", False)),
                reason=reason,
                semantic_events=True,
            )
        if op == "reanimate":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"graveyard"},
            )
            types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if "creature" not in types:
                raise GameRuleError(
                    "Reanimate effect requires a creature card"
                )
            return self.move_card(
                card.object_id,
                "battlefield",
                controller=str(effect.get("controller") or actor),
                reason=reason,
                semantic_events=True,
            )
        if op in {"destroy_all", "exile_all"}:
            specification = dict(effect.get("filter") or {})
            specification.setdefault("zones", ["battlefield"])
            specification.setdefault("categories", ["permanent"])
            specification.setdefault("min", 0)
            specification.setdefault("max", 10000)
            group = TargetGroup.from_mapping(
                specification,
                default_id="affected",
            )
            source_ref = str(effect.get("source") or "") or None
            refs = [
                str(row["ref"])
                for row in self._target_candidate_rows(actor, group)
                if self._target_row_matches(
                    actor,
                    group,
                    row,
                    source_ref=source_ref,
                    as_target=False,
                )
            ]
            changes: list[tuple[str, str]] = []
            for ref in refs:
                try:
                    card = self._resolve_object(
                        actor, ref, zones={"battlefield"}
                    )
                except GameRuleError:
                    continue
                if op == "destroy_all":
                    keywords = {
                        str(value).casefold()
                        for value in self._effective_card_data(card).get(
                            "keywords", []
                        )
                    }
                    if "indestructible" in keywords:
                        continue
                changes.append(
                    (
                        card.object_id,
                        "graveyard" if op == "destroy_all" else "exile",
                    )
                )
            self._move_cards_simultaneously(
                changes,
                reason=reason,
                log=True,
            )
            return [self.state.cards[object_id].ref for object_id, _ in changes]
        if op == "exile_opponent_graveyards":
            changes: list[tuple[str, str]] = []
            for opponent in self.active_seats:
                if opponent == actor:
                    continue
                for object_id in list(
                    self.state.players[opponent].zones["graveyard"]
                ):
                    changes.append((object_id, "exile"))
            self._move_cards_simultaneously(
                changes,
                reason=reason,
                log=True,
            )
            return [self.state.cards[object_id].ref for object_id, _ in changes]
        if op == "exile_graveyard":
            player = str(effect["player"])
            if player not in self.active_seats:
                raise GameRuleError(
                    "Graveyard exile requires an active player"
                )
            changes = [
                (object_id, "exile")
                for object_id in list(
                    self.state.players[player].zones["graveyard"]
                )
            ]
            self._move_cards_simultaneously(
                changes,
                reason=reason,
                log=True,
            )
            return [
                self.state.cards[object_id].ref
                for object_id, _ in changes
            ]
        if op == "destroy_selected":
            changes: list[tuple[str, str]] = []
            for raw_ref in effect.get("cards") or []:
                if raw_ref is None:
                    continue
                try:
                    card = self._resolve_object(
                        actor,
                        str(raw_ref),
                        zones={"battlefield"},
                    )
                except GameRuleError:
                    continue
                keywords = {
                    str(value).casefold()
                    for value in self._effective_card_data(card).get(
                        "keywords", []
                    )
                }
                if "indestructible" in keywords:
                    continue
                changes.append((card.object_id, "graveyard"))
            self._move_cards_simultaneously(
                changes,
                reason=reason,
                log=True,
            )
            return [self.state.cards[object_id].ref for object_id, _ in changes]
        if op == "toxic_deluge":
            amount = int(effect.get("amount", 0))
            if amount < 0:
                raise GameRuleError("Toxic Deluge X cannot be negative")
            affected_ids: list[str] = []
            for seat in self.active_seats:
                for object_id in list(
                    self.state.players[seat].zones["battlefield"]
                ):
                    card = self.state.cards[object_id]
                    if "creature" not in str(
                        self._effective_card_data(card).get("type_line")
                        or ""
                    ).casefold():
                        continue
                    until_end = card.annotations.setdefault(
                        "until_end_of_turn", {}
                    )
                    until_end["power"] = int(
                        until_end.get("power", 0)
                    ) - amount
                    until_end["toughness"] = int(
                        until_end.get("toughness", 0)
                    ) - amount
                    affected_ids.append(card.object_id)
            self._log(
                actor,
                "effect.toxic_deluge",
                f"Creatures got -{amount}/-{amount} until end of turn.",
                {
                    "amount": amount,
                    "objects": [
                        self.state.cards[object_id].ref
                        for object_id in affected_ids
                    ],
                },
                importance=2,
                changed_objects=affected_ids,
            )
            return [
                self.state.cards[object_id].ref
                for object_id in affected_ids
            ]
        if op == "pump_controlled_creatures":
            amount = int(effect.get("amount", 0))
            minimum = int(effect.get("minimum_amount", 0))
            if amount < minimum:
                return []
            keywords = [
                str(value)
                for value in effect.get("keywords", [])
            ]
            changed: list[str] = []
            for object_id in self.state.players[actor].zones["battlefield"]:
                card = self.state.cards[object_id]
                if card.controller != actor:
                    continue
                types, _, _ = self._type_parts(
                    str(
                        self._effective_card_data(card).get("type_line")
                        or ""
                    )
                )
                if "creature" not in types:
                    continue
                until_end = card.annotations.setdefault(
                    "until_end_of_turn", {}
                )
                until_end["power"] = int(
                    until_end.get("power", 0)
                ) + amount
                until_end["toughness"] = int(
                    until_end.get("toughness", 0)
                ) + amount
                card.temporary_keywords = unique_preserving_order(
                    [*card.temporary_keywords, *keywords]
                )
                changed.append(card.object_id)
            self._log(
                actor,
                "effect.creature_pump",
                f"{actor}'s creatures got +{amount}/+{amount}.",
                {
                    "amount": amount,
                    "keywords": keywords,
                    "objects": [
                        self.state.cards[object_id].ref
                        for object_id in changed
                    ],
                },
                importance=2,
                changed_objects=changed,
                changed_players=[actor],
            )
            return [
                self.state.cards[object_id].ref
                for object_id in changed
            ]
        if op == "shuffle_into_library":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={
                    "battlefield",
                    "graveyard",
                    "exile",
                    "stack",
                },
            )
            owner = card.owner
            moved = self.move_card(
                card.object_id,
                "library",
                reason=reason,
                semantic_events=True,
            )
            self.shuffle_library(owner, reason=reason)
            return moved.ref
        if op == "reveal_top_permanent":
            seat = str(effect.get("player") or actor)
            library = self.state.players[seat].zones["library"]
            if not library:
                return None
            card = self.state.cards[library[-1]]
            card.known_to = list(self.seats)
            card.revealed_to = list(self.seats)
            self._log(
                actor,
                "library.reveal",
                f"{seat} revealed {card.ref} {card.printed_name}.",
                {"player": seat, "object": card.ref},
                importance=2,
                changed_objects=[card.object_id],
            )
            data = self._effective_card_data(card)
            types, _, _ = self._type_parts(
                str(data.get("type_line") or "")
            )
            if types.intersection(
                {
                    "artifact",
                    "battle",
                    "creature",
                    "enchantment",
                    "land",
                    "planeswalker",
                }
            ):
                self.move_card(
                    card.object_id,
                    "battlefield",
                    controller=seat,
                    reason=reason,
                    semantic_events=True,
                )
            return card.ref
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
        if op == "damage_each_opponent":
            amount = max(0, int(effect.get("amount", 0)))
            opponents = [
                seat
                for seat in self.active_seats
                if seat != actor
            ]
            for opponent in opponents:
                self.state.players[opponent].life -= amount
            self._log(
                actor,
                "effect.damage",
                f"Each opponent of {actor} took {amount} damage.",
                {
                    "opponents": opponents,
                    "amount": amount,
                    "reason": reason,
                },
                importance=2,
                changed_players=opponents,
            )
            return amount
        if op == "life":
            seat = str(effect.get("player") or actor)
            delta = int(effect.get("delta", 0))
            self.state.players[seat].life += delta
            self._log(actor, "effect.life", f"{seat}'s life changed by {delta}.", {"player": seat, "delta": delta}, importance=1, changed_players=[seat])
            return self.state.players[seat].life
        if op == "lose_life":
            seat = str(effect.get("player") or actor)
            amount = max(0, int(effect.get("amount", 0)))
            self.state.players[seat].life -= amount
            self._log(
                actor,
                "effect.life",
                f"{seat} lost {amount} life.",
                {"player": seat, "delta": -amount},
                importance=1,
                changed_players=[seat],
            )
            return self.state.players[seat].life
        if op == "lose_life_equal_mana_value":
            seat = str(effect.get("player") or actor)
            card = self._resolve_object(actor, str(effect["card"]))
            record = self.card_record(card)
            amount = int(record.mana_value if record else 0)
            self.state.players[seat].life -= amount
            self._log(
                actor,
                "effect.life",
                f"{seat} lost {amount} life.",
                {
                    "player": seat,
                    "delta": -amount,
                    "card": card.ref,
                },
                importance=1,
                changed_players=[seat],
            )
            return self.state.players[seat].life
        if op == "energy":
            seat = str(effect.get("player") or actor)
            delta = int(effect.get("delta", 0))
            self.state.players[seat].energy += delta
            self._log(actor, "effect.energy", f"{seat}'s energy changed by {delta}.", {"player": seat, "delta": delta}, importance=1, changed_players=[seat])
            return self.state.players[seat].energy
        if op == "drain_opponent":
            target = str(effect["target"])
            amount = int(effect.get("amount", 1))
            if target not in self.active_seats or target == actor:
                raise GameRuleError("Drain effect requires an active opponent")
            self.state.players[target].life -= amount
            self.state.players[actor].life += amount
            self._log(
                actor,
                "effect.life",
                f"{target} lost {amount} life and {actor} gained {amount}.",
                {"player": target, "delta": -amount, "gained_by": actor},
                importance=2,
                changed_players=[actor, target],
            )
            return amount
        if op == "drain_each_opponent":
            amount = int(effect.get("amount", 1))
            opponents = [
                seat
                for seat in self.active_seats
                if seat != actor
            ]
            for opponent in opponents:
                self.state.players[opponent].life -= amount
            self.state.players[actor].life += amount
            self._log(
                actor,
                "effect.life",
                f"Each opponent of {actor} lost {amount} life; "
                f"{actor} gained {amount} life.",
                {
                    "opponents": opponents,
                    "amount": amount,
                    "gained_by": actor,
                },
                importance=2,
                changed_players=[actor, *opponents],
            )
            return amount
        if op == "create_treasure":
            return self.create_token(
                str(effect.get("controller") or actor),
                name="Treasure",
                characteristics={
                    "type_line": "Token Artifact — Treasure",
                    "oracle_text": "{T}, Sacrifice this token: Add one mana of any color.",
                },
                reason=reason,
            )
        if op == "create_warform":
            return self._create_mishra_warform(
                str(effect.get("controller") or actor),
                str(effect["card"]),
                reason=reason,
            )
        if op == "field_of_dead_token":
            land_names = {
                self.display_name(object_id)
                for object_id in self.state.players[actor].zones["battlefield"]
                if self.state.cards[object_id].controller == actor
                and self.card_record(object_id)
                and self.card_record(object_id).is_land
            }
            if len(land_names) < 7:
                return []
            return self.create_token(
                actor,
                name="Zombie",
                characteristics={
                    "type_line": "Token Creature — Zombie",
                    "power": "2",
                    "toughness": "2",
                    "colors": ["B"],
                },
                reason="Field of the Dead",
            )
        if op == "counter_or_destroy_blue":
            target = str(effect["target"])
            stack_item = next(
                (
                    candidate
                    for candidate in self.state.stack
                    if candidate.ref == target
                ),
                None,
            )
            if stack_item is not None:
                if not stack_item.card_object_id:
                    return None
                record = self.card_record(stack_item.card_object_id)
                if not record or "U" not in record.colors:
                    return None
                return self._counter_stack_item(
                    target,
                    reason="Red/Pyroblast semantic",
                    countered_by=actor,
                ).ref
            try:
                card = self._resolve_object(
                    actor, target, zones={"battlefield"}
                )
            except GameRuleError:
                return None
            record = self.card_record(card)
            if not record or "U" not in record.colors:
                return None
            self.move_card(
                card.object_id,
                "graveyard",
                reason="Red/Pyroblast semantic",
                semantic_events=True,
            )
            return card.ref
        if op == "sacrifice_if_present":
            value = effect.get("card")
            if not value:
                return None
            try:
                card = self._resolve_object(
                    actor, str(value), zones={"battlefield"}
                )
            except GameRuleError:
                return None
            self.move_card(
                card.object_id,
                "graveyard",
                reason=reason,
                semantic_events=True,
            )
            return card.ref
        if op == "counter_stack":
            return self._counter_stack_item(
                str(effect["stack"]),
                destination=str(effect.get("destination") or "graveyard"),
                reason=reason,
                countered_by=actor,
            ).ref
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
        if op == "grant_keyword_until_end_of_turn":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            keyword = str(effect["keyword"])
            card.temporary_keywords = unique_preserving_order(
                [*card.temporary_keywords, keyword]
            )
            self._log(
                actor,
                "permanent.keyword",
                f"{card.ref} gained {keyword} until end of turn.",
                {
                    "object": card.ref,
                    "keyword": keyword,
                    "reason": reason,
                },
                importance=1,
                changed_objects=[card.object_id],
            )
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
        trigger_batch: list[StackItem] = []
        for object_id in created:
            card = self.state.cards[object_id]
            data = self._effective_card_data(card)
            types, _, _ = self._type_parts(
                str(data.get("type_line") or "")
            )
            context = {
                "card": card.ref,
                "controller": controller,
                "owner": controller,
                "from": "outside",
                "to": "battlefield",
                "types": sorted(types),
                "token": True,
                "tapped": card.tapped,
                "reason": reason,
            }
            self._dispatch_semantic_event(
                "token.created",
                context,
                trigger_batch=trigger_batch,
            )
            self._dispatch_semantic_event(
                "permanent.enter",
                context,
                trigger_batch=trigger_batch,
            )
            for card_type in ("artifact", "creature", "land", "enchantment"):
                if card_type in types:
                    self._dispatch_semantic_event(
                        f"{card_type}.enter",
                        context,
                        trigger_batch=trigger_batch,
                    )
        self._enqueue_semantic_trigger_batch(trigger_batch)
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

    def apply_shortcut(
        self,
        seat: str,
        proposal: Mapping[str, Any],
    ) -> dict[str, Any]:
        from .shortcuts import execute_shortcut

        self._require_seat(seat, in_game=True)
        return execute_shortcut(self, seat, proposal)

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
