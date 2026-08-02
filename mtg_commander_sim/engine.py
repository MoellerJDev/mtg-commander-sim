from __future__ import annotations

import copy
import hashlib
import random
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .abilities import (
    ActivatedAbility,
    CostChoice,
    choose_ability,
    parse_activated_abilities,
    reduced_requirements,
)
from .carddb import CardDatabase, CardRecord
from .card_programs.validation import (
    canonical_program_fingerprint,
    program_source_is_current,
)
from .card_programs.runtime import (
    collect_card_program_continuous_effects,
)
from .combat import (
    DEFENDER,
    DEATHTOUCH,
    LIFELINK,
    MENACE,
    TRAMPLE,
    CreatureDamageState,
    DamageAssignment,
    assigns_in_damage_step,
    first_strike_step_required,
    normalized_keywords,
    ordinary_second_step_combatants,
    trample_assignment_error,
)
from .continuous_effects import (
    CharacteristicState,
    ContinuousEffect,
    ContinuousOperation,
    Layer,
    evaluate_continuous_effects,
)
from .counter_placement import (
    commit_counter_events_from_resolution,
    CounterPlacementError,
    place_counters_on_controlled_subtype,
    place_counters_on_refs,
)
from .combat_constraints import (
    DeclarationConstraintError,
    DeclarationProblem,
    DeclarationRequirement,
    DeclarationRestriction,
    DeclarationSearchLimitError,
)
from .declaration_costs import (
    DeclarationCost,
    normalized_oracle_line,
    parse_declaration_cost_line,
)
from .declaration_restrictions import (
    DeclarationBattlefieldCondition,
    DeclarationCombatCondition,
    DeclarationCondition,
    DeclarationConditionPlayer,
    DeclarationObjectPredicate,
    DeclarationPlayerStateCondition,
    DeclarationRestrictionTemplate,
    DeclarationSharedSubtypeCondition,
    DeclarationTurnHistoryCondition,
    parse_declaration_restriction_line,
)
from .damage import (
    apply_damage_results_to_permanent,
    damage_proposal,
    DamageError,
    DamageProposal,
    resolve_damage_batch,
)
from .deck import DeckDefinition
from .mana import (
    ManaMode,
    ManaPlanError,
    ManaSource,
    auto_plan_payment,
    extract_mana_modes,
    parsed_cost,
)
from .model import (
    CardInstance,
    CombatState,
    DelayedTrigger,
    Event,
    GameConfig,
    GameState,
    GoadDesignation,
    PlayerState,
    StackItem,
    TurnEntry,
    TurnHistory,
    TurnHistoryEvent,
    TurnHistoryEventKind,
    YieldPolicy,
)
from .permissions import AuthorizedCommand, CapabilityManager, PermissionDenied
from .replacement_decisions import (
    apply_effect_with_replacement_choice,
    complete_replacement_order_choice,
    issue_combat_damage_replacement_choice,
)
from .replacement_effects import ReplacementChoiceRequired
from .semantics import SemanticProgram, SemanticRegistry
from .semantic_runtime import (
    SemanticNodeError,
    default_semantic_interpreter,
    execute_intent_plan,
    log_applied_zone_replacements,
    PreparedZoneChange,
    prepare_zone_change_replacement,
    prepare_draw_resolution,
)
from .state_based_actions import (
    ObjectSnapshot,
    PermanentSnapshot,
    counter_maximums_from_oracle,
    evaluate_state_based_actions,
)
from .targets import (
    TargetGroup,
    TargetPlan,
    available_modes,
    mode_effects,
    target_plan,
)
from .token_creation import TokenCreationError, create_tokens
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

PUBLIC_ZONES = {"battlefield", "graveyard", "exile", "command", "stack"}
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
        self._semantic_trust_cache: dict[tuple[str, str, str], bool] = {}
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
        card_fingerprint = canonical_program_fingerprint(
            self.semantics, program
        )
        if card_fingerprint is None:
            if not self.semantics.is_runtime_handler_compatibility_program(
                program
            ):
                return False
            card_fingerprint = f"runtime-compatibility:{program.key}"
        cache_key = (program.key, program_hash, card_fingerprint)
        cached = self._semantic_trust_cache.get(cache_key)
        if cached is not None:
            return cached
        result = program_source_is_current(self.card_db, program)
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

    def _record_turn_history(
        self,
        kind: TurnHistoryEventKind,
        *,
        actor: str | None = None,
        object_incarnation: str | None = None,
        target: str | None = None,
        target_kind: str | None = None,
        types: Iterable[str] = (),
        amount: int = 0,
    ) -> None:
        """Append one authoritative current-turn look-back fact.

        Legacy Game Record v3 checkpoints omit ``turn_history``.  They keep
        that feature disabled so loading and reserializing one cannot silently
        add a hashed rules field partway through its command replay.
        """

        history = self.state.turn_history
        if history is None:
            return
        if history.turn_sequence != self.state.turn_sequence:
            history = TurnHistory(turn_sequence=self.state.turn_sequence)
            self.state.turn_history = history
        history.events.append(
            TurnHistoryEvent(
                kind=kind,
                actor=actor,
                object_incarnation=object_incarnation,
                target=target,
                target_kind=target_kind,
                types=tuple(sorted({str(value).casefold() for value in types})),
                amount=max(0, int(amount)),
            )
        )

    def _current_turn_history(
        self,
        kind: TurnHistoryEventKind,
    ) -> tuple[TurnHistoryEvent, ...]:
        history = self.state.turn_history
        if (
            history is None
            or history.schema_version != 1
            or history.turn_sequence != self.state.turn_sequence
        ):
            return ()
        return tuple(event for event in history.events if event.kind == kind)

    def _player_cast_spell_this_turn(
        self,
        player: str,
        *,
        creature: bool | None = None,
    ) -> bool:
        for event in self._current_turn_history("spell_cast"):
            if event.actor != player:
                continue
            is_creature = "creature" in event.types
            if creature is None or is_creature == creature:
                return True
        return False

    def _creature_died_under_control_this_turn(self, player: str) -> bool:
        return any(
            event.actor == player
            for event in self._current_turn_history("creature_died")
        )

    def _opponent_was_dealt_damage_this_turn(self, player: str) -> bool:
        opponents = set(self.active_seats) - {player}
        return any(
            event.target in opponents and event.amount > 0
            for event in self._current_turn_history("player_damaged")
        )

    def _object_attacked_player_this_turn(
        self,
        object_incarnation: str,
        player: str,
    ) -> bool:
        return any(
            event.object_incarnation == object_incarnation
            and event.target_kind == "player"
            and event.target == player
            for event in self._current_turn_history("creature_attacked")
        )

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

    def _next_zone_timestamp(self) -> int:
        """Allocate one authoritative timestamp moment."""

        self.state.timestamp_sequence += 1
        return self.state.timestamp_sequence

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
        self._update_yield_change_epochs(event)
        return event

    def _yield_change_epoch(
        self,
        kind: str,
        seat: str | None = None,
    ) -> int:
        key = (
            f"yield_change:{kind}:{seat}"
            if seat is not None
            else f"yield_change:{kind}"
        )
        return int(self.state.ref_counters.get(key, 0))

    def _increment_yield_change_epoch(
        self,
        kind: str,
        seat: str | None = None,
    ) -> None:
        key = (
            f"yield_change:{kind}:{seat}"
            if seat is not None
            else f"yield_change:{kind}"
        )
        self.state.ref_counters[key] = (
            int(self.state.ref_counters.get(key, 0)) + 1
        )

    def _update_yield_change_epochs(self, event: Event) -> None:
        """Persist yield-invalidating changes independently of trace output.

        Standard Game Records intentionally omit some low-level events. Yield
        correctness therefore cannot depend on rescanning the in-memory event
        list after a save/load boundary.
        """

        stack_codes = {
            "stack.cast",
            "stack.activate",
            "stack.trigger",
            "stack.resolve",
            "stack.counter",
        }
        if event.code in stack_codes:
            self._increment_yield_change_epoch("stack")
            return
        if event.code == "card.draw.private":
            for seat in self.state.players:
                if seat in event.visibility:
                    self._increment_yield_change_epoch("draw", seat)
            return
        if event.code == "zone.move":
            if (
                event.details.get("from") == "hand"
                or event.details.get("to") == "hand"
            ):
                for seat in event.changed_players:
                    if seat in self.state.players:
                        self._increment_yield_change_epoch(
                            "action",
                            seat,
                        )
            self._increment_yield_change_epoch("public")
            return
        if event.code == "permanent.untap":
            for seat in event.changed_players:
                if seat in self.state.players:
                    self._increment_yield_change_epoch("action", seat)
            self._increment_yield_change_epoch("public")
            return
        if event.code in {
            "land.play",
            "monarch.change",
            "token.create",
            "control.change",
            "permanent.goad",
            "permanent.goad.expire",
            "player.eliminated",
        }:
            self._increment_yield_change_epoch("public")

    def become_monarch(self, seat: str, *, reason: str) -> str:
        """Make one active player the monarch under CR 725.1 and 725.3."""

        self._require_seat(seat, in_game=True)
        previous = self.state.monarch
        if previous == seat:
            return seat
        self.state.monarch = seat
        self._log(
            seat,
            "monarch.change",
            f"{seat} became the monarch.",
            {
                "player": seat,
                "previous": previous,
                "reason": reason,
            },
            importance=2,
            changed_players=unique_preserving_order(
                [value for value in (previous, seat) if value is not None]
            ),
        )
        return seat

    def _monarch_trigger(
        self,
        *,
        controller: str,
        label: str,
        effects: Sequence[Mapping[str, Any]],
        context: Mapping[str, Any],
    ) -> StackItem:
        """Materialize one CR 725.2 inherent triggered ability."""

        ref = self._next_ref("S")
        return StackItem(
            stack_id=self._stable_runtime_id("stack", ref),
            ref=ref,
            kind="triggered_ability",
            controller=controller,
            label=label,
            visibility=list(self.seats),
            context={
                **copy.deepcopy(dict(context)),
                "dynamic_effects": copy.deepcopy(
                    [dict(effect) for effect in effects]
                ),
            },
        )

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
        stack_cards = {
            item.card_object_id
            for item in self.state.stack
            if item.card_object_id
        }
        for item in self.state.stack:
            object_id = item.card_object_id
            if not object_id:
                continue
            if (
                object_id not in self.state.cards
                or (
                    self.state.cards[object_id].zone != "stack"
                    and not item.context.get("currently_resolving")
                )
            ):
                raise StateInvariantError(
                    f"Stack item references nonstack object {object_id}"
                )
        for object_id, card in self.state.cards.items():
            locations = membership.get(object_id, [])
            goading_players = [
                designation.player for designation in card.goaded_by
            ]
            if card.goaded_by and card.zone != "battlefield":
                raise StateInvariantError(
                    f"Nonbattlefield object {card.ref} is still goaded"
                )
            if len(goading_players) != len(set(goading_players)):
                raise StateInvariantError(
                    f"{card.ref} has duplicate goad designations"
                )
            if any(
                player not in self.state.players
                for player in goading_players
            ):
                raise StateInvariantError(
                    f"{card.ref} has a goad designation from an unknown player"
                )
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
            elif (
                card.zone == "battlefield"
                and locations[0][0] != card.controller
            ):
                raise StateInvariantError(
                    f"{card.ref} is indexed under {locations[0][0]} "
                    f"but controlled by {card.controller}"
                )
            elif (
                card.zone
                in {"library", "hand", "graveyard", "exile", "command"}
                and locations[0][0] != card.owner
            ):
                raise StateInvariantError(
                    f"{card.ref} is indexed under {locations[0][0]} "
                    f"but owned by {card.owner}"
                )
        if self.state.priority_player is not None and self.state.priority_player not in self.active_seats:
            raise StateInvariantError("Priority belongs to a player who is not in the game")
        if (
            self.state.monarch is not None
            and self.state.monarch not in self.active_seats
        ):
            raise StateInvariantError(
                "The monarch designation belongs to a player who is not in the game"
            )
        history = self.state.turn_history
        if history is not None:
            if history.schema_version != 1:
                raise StateInvariantError(
                    f"Unsupported turn-history schema {history.schema_version}"
                )
            # An empty journal carries no look-back facts, so direct fixture
            # setup may advance ``turn_sequence`` before the first writer
            # initializes it. A nonempty journal must never cross that
            # boundary because prior-turn facts would affect this turn.
            if (
                history.events
                and history.turn_sequence != self.state.turn_sequence
            ):
                raise StateInvariantError(
                    "Turn history does not belong to the current turn"
                )
            for event in history.events:
                if event.actor is not None and event.actor not in self.state.players:
                    raise StateInvariantError(
                        f"Turn history names unknown actor {event.actor}"
                    )
                if (
                    event.target_kind == "player"
                    and event.target not in self.state.players
                ):
                    raise StateInvariantError(
                        f"Turn history names unknown player target {event.target}"
                    )
        for player in self.state.players.values():
            if any(value < 0 for value in player.mana_pool.values()):
                raise StateInvariantError(f"Negative mana in {player.seat}'s pool")

    def card_record(self, value: str | CardInstance) -> CardRecord | None:
        card = value if isinstance(value, CardInstance) else self.state.cards[value]
        if card.oracle_id.startswith(
            ("custom-token:", "custom-copy:", "custom-emblem:")
        ):
            return None
        return self.card_db.by_oracle_id(card.oracle_id)

    def _apply_layered_characteristic_annotations(
        self,
        card: CardInstance,
        base: Mapping[str, Any],
        *,
        runtime_effects: Sequence[ContinuousEffect] = (),
    ) -> dict[str, Any]:
        """Evaluate the engine's declarative characteristic annotations.

        This is the runtime bridge into the CR 613 evaluator. Existing
        card-specific continuous checks below remain explicit until they are
        converted to contracts, but copy values, type additions, subtype
        additions, and temporary keyword grants now share one canonical layer
        order rather than relying on call-site order.
        """

        result = copy.deepcopy(dict(base))
        overrides = dict(card.annotations.get("copy_overrides") or {})
        added_types = [
            str(value).strip()
            for value in card.annotations.get(
                "continuous_add_types", []
            )
            if str(value).strip()
        ] + [
            str(value).strip()
            for value in dict(
                card.annotations.get("until_end_of_turn") or {}
            ).get("add_types", [])
            if str(value).strip()
        ]
        added_subtypes = (
            [
                str(card.annotations["chosen_creature_type"])
            ]
            if card.printed_name == "Roaming Throne"
            and card.annotations.get("chosen_creature_type")
            else []
        ) + [
            str(value).strip()
            for value in card.annotations.get(
                "continuous_add_subtypes", []
            )
            if str(value).strip()
        ] + [
            str(value).strip()
            for value in dict(
                card.annotations.get("until_end_of_turn") or {}
            ).get("add_subtypes", [])
            if str(value).strip()
        ]
        layered = bool(
            overrides
            or added_types
            or added_subtypes
            or card.temporary_keywords
            or card.annotations.get("bestowed")
            or runtime_effects
        )
        if not layered:
            result["keywords"] = unique_preserving_order(
                list(result.get("keywords") or [])
            )
            return result

        card_types, subtypes, supertypes = self._type_parts(
            str(result.get("type_line") or "")
        )

        def numeric(value: Any) -> int | None:
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return None

        state = CharacteristicState(
            name=str(result.get("name") or card.printed_name),
            controller=card.controller,
            mana_cost=str(result.get("mana_cost") or ""),
            mana_value=float(result.get("mana_value") or 0),
            text=str(result.get("oracle_text") or ""),
            supertypes=set(supertypes),
            card_types=set(card_types),
            subtypes=set(subtypes),
            colors={
                str(value).upper()
                for value in result.get("colors", [])
            },
            abilities=[
                str(value)
                for value in result.get("keywords", [])
            ],
            power=numeric(result.get("power")),
            toughness=numeric(result.get("toughness")),
            loyalty=numeric(result.get("loyalty")),
            defense=numeric(result.get("defense")),
        )
        effects: list[ContinuousEffect] = []
        timestamp = 0

        if overrides:
            copy_values: dict[str, Any] = {}
            field_map = {
                "name": "name",
                "mana_cost": "mana_cost",
                "mana_value": "mana_value",
                "oracle_text": "text",
                "power": "power",
                "toughness": "toughness",
                "loyalty": "loyalty",
                "defense": "defense",
                "colors": "colors",
                "keywords": "abilities",
            }
            for source_field, target_field in field_map.items():
                if source_field in overrides:
                    value = copy.deepcopy(overrides[source_field])
                    if target_field in {
                        "power",
                        "toughness",
                        "loyalty",
                        "defense",
                    }:
                        parsed = numeric(value)
                        if parsed is None:
                            continue
                        value = parsed
                    copy_values[target_field] = value
            if overrides.get("type_line") is not None:
                copied_types, copied_subtypes, copied_supertypes = (
                    self._type_parts(str(overrides["type_line"]))
                )
                copy_values.update(
                    {
                        "card_types": sorted(copied_types),
                        "subtypes": sorted(copied_subtypes),
                        "supertypes": sorted(copied_supertypes),
                    }
                )
            if copy_values:
                effects.append(
                    ContinuousEffect(
                        effect_id=f"{card.object_id}:copy",
                        source_id=card.object_id,
                        layer=Layer.COPY,
                        sublayer="1a",
                        timestamp=timestamp,
                        operations=(
                            ContinuousOperation(
                                "copy_values", copy_values
                            ),
                        ),
                        duration="zone_object",
                    )
                )
                timestamp += 1

        type_operations: list[ContinuousOperation] = []
        if card.annotations.get("bestowed") and card.attached_to:
            type_operations.extend(
                [
                    ContinuousOperation(
                        "set_types",
                        ["Enchantment"],
                        field="card_types",
                    ),
                    ContinuousOperation(
                        "set_types",
                        ["Aura"],
                        field="subtypes",
                    ),
                ]
            )
        if added_types:
            type_operations.append(
                ContinuousOperation(
                    "add_types",
                    added_types,
                    field="card_types",
                )
            )
        if added_subtypes:
            type_operations.append(
                ContinuousOperation(
                    "add_types",
                    added_subtypes,
                    field="subtypes",
                )
            )
        if type_operations:
            effects.append(
                ContinuousEffect(
                    effect_id=f"{card.object_id}:types",
                    source_id=card.object_id,
                    layer=Layer.TYPE,
                    sublayer="4",
                    timestamp=timestamp,
                    operations=tuple(type_operations),
                    duration="zone_object",
                )
            )
            timestamp += 1

        if card.temporary_keywords:
            effects.append(
                ContinuousEffect(
                    effect_id=f"{card.object_id}:keywords",
                    source_id=card.object_id,
                    layer=Layer.ABILITY,
                    sublayer="6",
                    timestamp=timestamp,
                    operations=tuple(
                        ContinuousOperation("add_ability", keyword)
                        for keyword in card.temporary_keywords
                    ),
                    duration="until_end_of_turn",
                )
            )

        effects.extend(runtime_effects)

        evaluated = evaluate_continuous_effects(state, effects)
        values = evaluated.characteristics
        result.update(
            {
                "name": values["name"],
                "mana_cost": values["mana_cost"],
                "mana_value": values["mana_value"],
                "oracle_text": values["text"],
                "colors": [
                    color
                    for color in "WUBRGC"
                    if color in set(values["colors"])
                ],
                "keywords": unique_preserving_order(
                    values["abilities"]
                ),
            }
        )
        if values["power"] is not None:
            result["power"] = str(values["power"])
        if values["toughness"] is not None:
            result["toughness"] = str(values["toughness"])
        if values["loyalty"] is not None:
            result["loyalty"] = str(values["loyalty"])
        if values["defense"] is not None:
            result["defense"] = str(values["defense"])

        supertype_order = ["Basic", "Legendary", "Snow", "World"]
        type_order = [
            "Artifact",
            "Battle",
            "Creature",
            "Enchantment",
            "Instant",
            "Kindred",
            "Land",
            "Planeswalker",
            "Sorcery",
        ]

        def ordered_words(
            values_to_order: Sequence[str],
            preferred: Sequence[str],
        ) -> list[str]:
            by_lower = {
                str(value).casefold(): str(value).title()
                for value in values_to_order
            }
            preferred_lower = {
                value.casefold() for value in preferred
            }
            return [
                value
                for value in preferred
                if value.casefold() in by_lower
            ] + [
                by_lower[key]
                for key in sorted(by_lower)
                if key not in preferred_lower
            ]

        left = [
            *ordered_words(values["supertypes"], supertype_order),
            *ordered_words(values["card_types"], type_order),
        ]
        right = [
            str(value).title()
            for value in values["subtypes"]
        ]
        result["type_line"] = " ".join(left) + (
            f" — {' '.join(right)}" if right else ""
        )
        if card.annotations.get("bestowed") and card.attached_to:
            result["oracle_text"] = (
                "Enchant creature\nEnchanted creature gets +1/+1."
            )
        return result

    def _effective_card_data(
        self,
        value: str | CardInstance,
        *,
        printed_entry_characteristics: bool = False,
    ) -> dict[str, Any]:
        card = value if isinstance(value, CardInstance) else self.state.cards[value]
        record = self.card_record(card)
        if record is None:
            object_characteristics = dict(
                card.annotations.get("object_characteristics")
                or card.annotations.get("token_characteristics")
                or {}
            )
            base = {
                "name": (
                    ""
                    if card.object_kind == "emblem"
                    else card.printed_name
                ),
                "mana_cost": "",
                "mana_value": object_characteristics.get(
                    "mana_value", 0
                ),
                "type_line": str(
                    object_characteristics.get("type_line", "Token")
                ),
                "oracle_text": str(
                    object_characteristics.get("oracle_text", "")
                ),
                "power": object_characteristics.get("power"),
                "toughness": object_characteristics.get("toughness"),
                "loyalty": object_characteristics.get("loyalty"),
                "defense": object_characteristics.get("defense"),
                "keywords": list(
                    object_characteristics.get("keywords", [])
                ),
                "colors": list(
                    object_characteristics.get("colors", [])
                ),
                "produced_mana": list(
                    object_characteristics.get("produced_mana", [])
                ),
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
                "defense": face.get("defense") if face else record.defense,
                "keywords": list(record.keywords),
                "colors": list(record.colors),
                "produced_mana": list(record.produced_mana),
            }
        runtime_effects = (
            collect_card_program_continuous_effects(
                self.state,
                self.semantics,
                self.semantic_program_is_current_trusted,
            )
            if card.zone == "battlefield"
            else ()
        )
        base = self._apply_layered_characteristic_annotations(
            card,
            base,
            runtime_effects=runtime_effects,
        )
        conditional_haste = re.search(
            r"has haste as long as an opponent has "
            r"(?P<life>\d+) or less life",
            str(base.get("oracle_text") or ""),
            re.IGNORECASE,
        )
        if (
            conditional_haste
            and any(
                seat != card.controller
                and player.in_game
                and player.life <= int(conditional_haste.group("life"))
                for seat, player in self.state.players.items()
            )
        ):
            base["keywords"] = unique_preserving_order(
                [*base["keywords"], "Haste"]
            )
        if card.zone == "battlefield":
            card_types, _, _ = self._type_parts(
                str(base.get("type_line") or "")
            )
            for permanent_id in self.state.players[
                card.controller
            ].zones["battlefield"]:
                source = self.state.cards[permanent_id]
                if source.controller != card.controller or source.phased_out:
                    continue
                source_record = self.card_record(source)
                source_oracle = (
                    str(source_record.oracle_text or "").casefold()
                    if source_record is not None
                    else str(
                        dict(
                            source.annotations.get(
                                "token_characteristics", {}
                            )
                        ).get("oracle_text")
                        or ""
                    ).casefold()
                )
                if (
                    "artifact" in card_types
                    and "artifacts you control have hexproof"
                    in source_oracle
                ):
                    base["keywords"] = unique_preserving_order(
                        [*base["keywords"], "Hexproof"]
                    )
                if (
                    card.is_token
                    and "creature" in card_types
                    and "creature tokens you control have haste"
                    in source_oracle
                ):
                    base["keywords"] = unique_preserving_order(
                        [*base["keywords"], "Haste"]
                    )
            for attachment_id in card.attachments:
                equipment = self.state.cards.get(attachment_id)
                if (
                    equipment is None
                    or equipment.zone != "battlefield"
                    or equipment.attached_to != card.object_id
                ):
                    continue
                equipment_record = self.card_record(equipment)
                equipment_oracle = (
                    str(equipment_record.oracle_text or "")
                    if equipment_record is not None
                    else ""
                )
                granted = re.search(
                    r"equipped creature has (?P<keywords>[^.]+)",
                    equipment_oracle,
                    re.IGNORECASE,
                )
                if granted:
                    keywords = [
                        value.strip().title()
                        for value in re.split(
                            r"\s+and\s+|,\s*",
                            granted.group("keywords"),
                        )
                        if value.strip()
                    ]
                    base["keywords"] = unique_preserving_order(
                        [*base["keywords"], *keywords]
                    )
                modifier = re.search(
                    r"equipped creature gets "
                    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)",
                    equipment_oracle,
                    re.IGNORECASE,
                )
                if modifier:
                    for stat in ("power", "toughness"):
                        try:
                            base[stat] = str(
                                int(str(base.get(stat)))
                                + int(modifier.group(stat))
                            )
                        except (TypeError, ValueError):
                            pass
                if equipment.printed_name == "Animate Dead":
                    try:
                        base["power"] = str(
                            int(str(base.get("power"))) - 1
                        )
                    except (TypeError, ValueError):
                        pass
                if (
                    equipment.printed_name == "Springheart Nantuko"
                    and equipment.annotations.get("bestowed")
                ):
                    for stat in ("power", "toughness"):
                        try:
                            base[stat] = str(
                                int(str(base.get(stat))) + 1
                            )
                        except (TypeError, ValueError):
                            pass
                if "equipped creature has" in equipment_oracle.casefold():
                    granted_lines = [
                        value.strip()
                        for value in re.findall(
                            r'["“]([^"”]+)["”]',
                            equipment_oracle,
                        )
                        if value.strip()
                    ]
                    if granted_lines:
                        base["oracle_text"] = "\n".join(
                            [
                                str(base.get("oracle_text") or ""),
                                *granted_lines,
                            ]
                        ).strip()
            oracle = str(base.get("oracle_text") or "").casefold()
            if (
                "gets +1/+1 for each artifact you control" in oracle
                and "creature" in card_types
            ):
                artifact_count = sum(
                    1
                    for object_id in self.state.players[
                        card.controller
                    ].zones["battlefield"]
                    if self.state.cards[object_id].controller
                    == card.controller
                    and not self.state.cards[object_id].phased_out
                    and "artifact"
                    in self._type_parts(
                        str(
                            dict(
                                self.state.cards[
                                    object_id
                                ].annotations.get(
                                    "copy_overrides", {}
                                )
                            ).get("type_line")
                            or dict(
                                self.state.cards[
                                    object_id
                                ].annotations.get(
                                    "token_characteristics", {}
                                )
                            ).get("type_line")
                            or (
                                self.card_record(object_id).type_line
                                if self.card_record(object_id)
                                is not None
                                else ""
                            )
                            or ""
                        )
                    )[0]
                )
                for stat in ("power", "toughness"):
                    try:
                        base[stat] = str(
                            int(str(base.get(stat))) + artifact_count
                        )
                    except (TypeError, ValueError):
                        pass
            graveyard_ids = self.state.players[card.owner].zones[
                "graveyard"
            ]
            if (
                "gets +2/+2 as long as there are three or more land "
                "cards in your graveyard"
            ) in oracle:
                land_count = sum(
                    1
                    for object_id in graveyard_ids
                    if "land"
                    in self._type_parts(
                        str(
                            self._effective_card_data(object_id).get(
                                "type_line"
                            )
                            or ""
                        )
                    )[0]
                )
                if land_count >= 3:
                    for stat in ("power", "toughness"):
                        try:
                            base[stat] = str(int(str(base.get(stat))) + 2)
                        except (TypeError, ValueError):
                            pass
            graveyard_creature_modifier = re.search(
                r"gets \+1/\+1 for each creature card in your graveyard",
                oracle,
            )
            if graveyard_creature_modifier:
                creature_count = sum(
                    1
                    for object_id in graveyard_ids
                    if "creature"
                    in self._type_parts(
                        str(
                            self._effective_card_data(object_id).get(
                                "type_line"
                            )
                            or ""
                        )
                    )[0]
                )
                for stat in ("power", "toughness"):
                    try:
                        base[stat] = str(
                            int(str(base.get(stat))) + creature_count
                        )
                    except (TypeError, ValueError):
                        pass
        if (
            card.zone == "battlefield"
            and not printed_entry_characteristics
            and "battle"
            in self._type_parts(
                str(base.get("type_line") or "")
            )[0]
        ):
            # CR 310.4c makes a battlefield Battle's defense equal to
            # its defense-counter count.  The printed number remains the
            # copiable/off-battlefield characteristic and is read explicitly
            # while applying the intrinsic as-enters counter effect.
            base["defense"] = str(
                max(0, int(card.counters.get("defense", 0)))
            )
        return base

    def display_name(self, object_id: str) -> str:
        return str(self._effective_card_data(object_id).get("name") or self.state.cards[object_id].printed_name)

    def _copyable_characteristics(
        self, card: CardInstance
    ) -> dict[str, Any]:
        record = self.card_record(card)
        if record is None:
            base = copy.deepcopy(
                dict(card.annotations.get("token_characteristics") or {})
            )
            base.setdefault("name", card.printed_name)
            base.setdefault("mana_cost", "")
            base.setdefault("mana_value", 0)
            base.setdefault("type_line", "Token")
            base.setdefault("oracle_text", "")
            base.setdefault("keywords", [])
            base.setdefault("colors", [])
            base.setdefault("produced_mana", [])
        else:
            face = None
            if card.active_face:
                face = next(
                    (
                        value
                        for value in record.faces
                        if str(value.get("name") or "")
                        == card.active_face
                    ),
                    None,
                )
            base = {
                "name": (
                    str(face.get("name"))
                    if face is not None
                    else record.name
                ),
                "mana_cost": (
                    str(face.get("mana_cost") or "")
                    if face is not None
                    else record.mana_cost
                ),
                "mana_value": record.mana_value,
                "type_line": (
                    str(face.get("type_line") or "")
                    if face is not None
                    else record.type_line
                ),
                "oracle_text": (
                    str(face.get("oracle_text") or "")
                    if face is not None
                    else record.oracle_text
                ),
                "power": (
                    face.get("power")
                    if face is not None
                    else record.power
                ),
                "toughness": (
                    face.get("toughness")
                    if face is not None
                    else record.toughness
                ),
                "loyalty": (
                    face.get("loyalty")
                    if face is not None
                    else record.loyalty
                ),
                "defense": (
                    face.get("defense")
                    if face is not None
                    else record.defense
                ),
                "keywords": list(record.keywords),
                "colors": list(record.colors),
                "produced_mana": list(record.produced_mana),
            }
        base.update(
            copy.deepcopy(dict(card.annotations.get("copy_overrides") or {}))
        )
        return base

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

    def _reset_zone_change(
        self,
        card: CardInstance,
        destination: str,
        *,
        zone_timestamp: int | None = None,
    ) -> None:
        origin = card.zone
        creates_new_object = (
            origin != destination
            or origin in {"exile", "command"}
        )
        if not creates_new_object:
            return

        self._remove_object_from_combat(
            card,
            reason=f"zone change to {destination}",
        )

        # CR 400.7a: a permanent spell that resolves remains the same
        # logical object as the permanent it becomes.  It still receives a
        # battlefield timestamp and has the ordinary spell-only state reset.
        stack_to_battlefield = (
            origin == "stack" and destination == "battlefield"
        )
        if not stack_to_battlefield:
            card.zone_change_counter += 1
        card.zone_timestamp = (
            int(zone_timestamp)
            if zone_timestamp is not None
            else self._next_zone_timestamp()
        )
        card.world_supertype_timestamp = None
        if (
            card.is_token
            and origin == "battlefield"
            and destination != "battlefield"
        ):
            card.has_left_battlefield = True

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
        card.goaded_by.clear()
        card.attacking = None
        card.blocking = None
        card.attached_to = None
        card.attachments.clear()
        card.phased_out = False
        if not stack_to_battlefield:
            card.battle_protector = None

        # CR 400.7 gives the destination a new logical object.  Retain only
        # state covered by an implemented exception or by the token's initial
        # copiable characteristics.
        retained_annotation_keys = {
            "object_characteristics",
            "token_characteristics",
        }
        if card.is_token or card.object_kind in {
            "spell_copy",
            "card_copy",
        }:
            retained_annotation_keys.update(
                {"copied_from", "copy_overrides"}
            )
        if stack_to_battlefield:
            retained_annotation_keys.update(
                {
                    "bestowed",
                    "chosen_creature_type",
                    "chosen_name",
                    "copy_overrides",
                    "evoked",
                    "pending_aura_target",
                    "pending_aura_zone",
                }
            )
        card.annotations = {
            key: value
            for key, value in card.annotations.items()
            if key in retained_annotation_keys
        }
        card.counters.clear()
        if not stack_to_battlefield:
            card.active_face = None
            card.face_down = False
        if destination != "battlefield":
            card.controller = card.owner

    def _unconditionally_enters_tapped(
        self,
        card: CardInstance,
    ) -> bool:
        """Recognize the exact unconditional entry replacement template.

        Conditional entry text remains in the dedicated land entry planner or
        fails closed. Matching whole Oracle lines here prevents a phrase in
        reminder text or a conditional sentence from changing entry state.
        """

        data = self._effective_card_data(card)
        name = re.escape(str(data.get("name") or card.printed_name))
        pattern = re.compile(
            rf"(?:this (?:artifact|creature|enchantment|land|permanent)"
            rf"|{name}) enters tapped\.?",
            re.IGNORECASE,
        )
        return any(
            pattern.fullmatch(line.strip()) is not None
            for line in str(data.get("oracle_text") or "").splitlines()
            if line.strip()
        )

    def _initialize_intrinsic_entry_counters(
        self,
        card: CardInstance,
    ) -> None:
        """Apply counter entry abilities intrinsic to represented card types."""

        if card.zone != "battlefield":
            return
        data = self._effective_card_data(
            card,
            printed_entry_characteristics=True,
        )
        card_types, subtypes, _ = self._type_parts(
            str(data.get("type_line") or "")
        )
        if "planeswalker" in card_types:
            try:
                loyalty = int(str(data.get("loyalty")))
            except (TypeError, ValueError):
                raise GameRuleError(
                    f"{self.display_name(card.object_id)} is a "
                    "planeswalker without represented starting loyalty"
                )
            if loyalty < 0:
                raise GameRuleError(
                    "Starting loyalty cannot be negative"
                )
            card.counters["loyalty"] = loyalty
            card.annotations["loyalty_initialized"] = True
        if "battle" not in card_types:
            card.battle_protector = None
            return
        if "siege" in subtypes:
            if (
                card.battle_protector not in self.active_seats
                or card.battle_protector == card.controller
            ):
                raise GameRuleError(
                    f"{self.display_name(card.object_id)} must enter with "
                    "one of its controller's opponents as protector"
                )
        elif subtypes:
            raise GameRuleError(
                "The protector predicate for Battle type(s) "
                f"{sorted(subtypes)} is not compiled"
            )
        else:
            card.battle_protector = card.controller
        try:
            defense = int(str(data.get("defense")))
        except (TypeError, ValueError):
            raise GameRuleError(
                f"{self.display_name(card.object_id)} is a Battle without "
                "a represented printed defense number"
            )
        if defense < 0:
            raise GameRuleError("Battle defense cannot be negative")
        card.counters["defense"] = defense

    @staticmethod
    def _trigger_item_matches_incarnation(
        card: CardInstance,
        item: StackItem | Mapping[str, Any],
    ) -> bool:
        """Whether one pending trigger was sourced by this exact object."""

        if isinstance(item, StackItem):
            source_object_id = item.source_object_id
            kind = item.kind
            context = item.context
        else:
            source_object_id = item.get("source_object_id")
            kind = str(item.get("kind") or "")
            context = dict(item.get("context") or {})
        if (
            source_object_id != card.object_id
            or "triggered" not in str(kind).casefold()
        ):
            return False
        source_incarnation = context.get("source_logical_object_id")
        return (
            source_incarnation is None
            or str(source_incarnation) == card.logical_object_id
        )

    def _battle_trigger_pending(self, card: CardInstance) -> bool:
        if any(
            self._trigger_item_matches_incarnation(card, item)
            for item in self.state.stack
        ):
            return True
        return any(
            self._trigger_item_matches_incarnation(card, item)
            for batch in self.state.pending_trigger_batches
            for group in batch.get("groups", [])
            for item in group.get("items", [])
        )

    def _queue_siege_defeated_trigger(
        self,
        battle: CardInstance,
    ) -> None:
        """Queue the intrinsic Siege trigger after its last defense counter."""

        if (
            battle.zone != "battlefield"
            or battle.phased_out
            or battle.controller not in self.active_seats
        ):
            return
        _, subtypes, _ = self._type_parts(
            str(
                self._effective_card_data(battle).get("type_line")
                or ""
            )
        )
        if "siege" not in subtypes:
            return
        pending_items: list[StackItem | Mapping[str, Any]] = [
            *self.state.stack,
            *[
                item
                for batch in self.state.pending_trigger_batches
                for group in batch.get("groups", [])
                for item in group.get("items", [])
            ],
        ]
        if any(
            self._trigger_item_matches_incarnation(battle, item)
            and (
                item.semantic_key
                if isinstance(item, StackItem)
                else item.get("semantic_key")
            )
            == "builtin:siege-defeated"
            for item in pending_items
        ):
            return
        ref = self._next_ref("S")
        self._enqueue_semantic_trigger_batch(
            [
                StackItem(
                    stack_id=self._stable_runtime_id("stack", ref),
                    ref=ref,
                    kind="triggered_ability",
                    controller=battle.controller,
                    label=f"{self.display_name(battle.object_id)} defeated",
                    source_object_id=battle.object_id,
                    semantic_key="builtin:siege-defeated",
                    visibility=list(self.seats),
                    context={
                        "event": "battle.last_defense_removed",
                        "battle": battle.ref,
                        "source_logical_object_id": (
                            battle.logical_object_id
                        ),
                        "native_transformed_cast": True,
                    },
                )
            ]
        )

    def _change_permanent_counter(
        self,
        card: CardInstance,
        name: str,
        delta: int,
    ) -> tuple[int, int]:
        """Change one counter kind without permitting negative counters."""

        counter = " ".join(str(name).casefold().split())
        if not counter:
            raise GameRuleError("Counter effects require a counter name")
        before = max(0, int(card.counters.get(counter, 0)))
        after = max(0, before + int(delta))
        if after:
            card.counters[counter] = after
        else:
            card.counters.pop(counter, None)
        if counter == "defense" and before > 0 and after == 0:
            self._queue_siege_defeated_trigger(card)
        return before, after

    def _apply_damage_results_to_permanent(
        self,
        card: CardInstance,
        amount: int,
        *,
        deathtouch: bool = False,
    ) -> dict[str, Any]:
        """Compatibility adapter for the dedicated damage mutation owner."""

        try:
            return apply_damage_results_to_permanent(
                self,
                card,
                amount,
                deathtouch=deathtouch,
            )
        except DamageError as exc:
            raise GameRuleError(str(exc)) from exc

    def move_card(
        self,
        object_id: str,
        destination: str,
        *,
        controller: str | None = None,
        tapped: bool | None = None,
        enter_face: str | None = None,
        battle_protector: str | None = None,
        zone_timestamp: int | None = None,
        position: str | int = "top",
        reveal_to: Iterable[str] | None = None,
        reason: str = "",
        log: bool = True,
        semantic_events: bool = False,
        replacement_sources: Sequence[CardInstance] | None = None,
        replacement_source_zones: Mapping[str, str] | None = None,
        replacement_selections: Sequence[str | None] = (),
        prepared_replacement: PreparedZoneChange | None = None,
    ) -> CardInstance:
        if destination not in {"library", "hand", "battlefield", "graveyard", "exile", "command", "outside"}:
            raise GameRuleError(f"Unsupported destination {destination}")
        card = self.state.cards[object_id]
        requested_destination = destination
        origin = card.zone
        library_position: str | int | None = None
        if destination == "library":
            library_position = self._library_position(position)
        if (
            origin == requested_destination
            and origin not in {"library", "exile", "command"}
        ):
            return card
        origin_identity_public = (
            origin in PUBLIC_ZONES and not card.face_down
        )
        if (
            card.is_token
            and card.has_left_battlefield
            and origin not in {"battlefield", "outside"}
            and requested_destination not in {origin, "outside"}
        ):
            if log:
                self._log(
                    None,
                    "zone.move.prevented",
                    (
                        f"{card.ref} remained in {origin}; a token that "
                        "left the battlefield cannot move again."
                    ),
                    {
                        "object": card.ref,
                        "from": origin,
                        "requested_destination": requested_destination,
                        "rule": "111.8",
                    },
                    importance=2,
                    changed_objects=[card.object_id],
                    changed_players=[card.owner],
                )
            return card
        destination_type_line = str(
            self._effective_card_data(card).get("type_line") or ""
        )
        if enter_face is not None:
            record = self.card_record(card)
            selected_face = next(
                (
                    face
                    for face in (record.faces if record else ())
                    if str(face.get("name") or "") == enter_face
                ),
                None,
            )
            if selected_face is not None:
                destination_type_line = str(
                    selected_face.get("type_line") or ""
                )
        if (
            destination == "battlefield"
            and card.is_card_object
            and self._type_parts(
                destination_type_line
            )[0].intersection({"instant", "sorcery"})
        ):
            if log:
                self._log(
                    None,
                    "zone.move.prevented",
                    (
                        f"{card.ref} remained in {origin}; an instant or "
                        "sorcery card cannot enter the battlefield."
                    ),
                    {
                        "object": card.ref,
                        "from": origin,
                        "requested_destination": requested_destination,
                        "rule": "400.4a",
                    },
                    importance=2,
                    changed_objects=[card.object_id],
                    changed_players=[card.owner],
                )
            return card
        if origin == "library" and requested_destination == "library":
            library = self.state.players[card.owner].zones["library"]
            if object_id not in library:
                raise GameRuleError(
                    "Library card is absent from its owner's library"
                )
            library.remove(object_id)
            library.insert(
                self._library_insertion_index(
                    len(library),
                    library_position,
                ),
                object_id,
            )
            if log:
                self._log(
                    card.owner,
                    "library.reorder",
                    f"{card.owner} changed a card's library position.",
                    {
                        "position": library_position,
                        "reason": reason,
                    },
                    visibility=[card.owner, "analyst"],
                    importance=1,
                    changed_objects=[card.object_id],
                    changed_players=[card.owner],
                )
            return card
        prepared_replacement = prepare_zone_change_replacement(
            self,
            card,
            destination,
            sources=replacement_sources,
            source_zones=replacement_source_zones,
            selections=tuple(replacement_selections),
            prepared=prepared_replacement,
            error_type=GameRuleError,
        )
        destination = prepared_replacement.destination
        origin_controller = card.controller
        origin_logical_object_id = card.logical_object_id
        origin_attachments = [
            self.state.cards[attachment_id].ref
            for attachment_id in card.attachments
            if attachment_id in self.state.cards
        ]
        origin_attached_to = (
            self.state.cards[card.attached_to].ref
            if card.attached_to in self.state.cards
            else None
        )
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
        if origin == "stack":
            # A resolving or countered spell has already had its StackItem
            # removed by that procedure.  A zone-changing effect can instead
            # exile a card spell directly; remove its associated stack object
            # at the same atomic boundary so no ghost spell remains.  A spell
            # that moves its own underlying card while resolving remains a
            # resolving stack object until every later instruction finishes.
            if not any(
                item.card_object_id == card.object_id
                and item.context.get("currently_resolving")
                for item in self.state.stack
            ):
                self.state.stack[:] = [
                    item
                    for item in self.state.stack
                    if item.card_object_id != card.object_id
                ]
        else:
            self._remove_from_zone(card)
        self._reset_zone_change(
            card,
            destination,
            zone_timestamp=zone_timestamp,
        )
        card.zone = destination
        if enter_face is not None:
            card.active_face = enter_face
        if destination == "battlefield":
            card.controller = controller or card.owner
            self._require_seat(card.controller)
            card.tapped = (
                self._unconditionally_enters_tapped(card)
                if tapped is None
                else bool(tapped)
            )
            card.acquired_control_turn_count = self.state.players[card.controller].turns_begun
            card.entered_battlefield_turn_sequence = self.state.turn_sequence
            if battle_protector is not None:
                card.battle_protector = str(battle_protector)
            self.state.players[card.controller].zones["battlefield"].append(
                object_id
            )
            self._initialize_intrinsic_entry_counters(card)
            pending_aura_target = card.annotations.pop(
                "pending_aura_target",
                None,
            )
            if pending_aura_target:
                pending_aura_zone = str(
                    card.annotations.pop(
                        "pending_aura_zone",
                        "graveyard",
                    )
                )
                try:
                    aura_target = self._resolve_object(
                        card.controller,
                        str(pending_aura_target),
                        zones={pending_aura_zone},
                    )
                except GameRuleError:
                    aura_target = None
                if aura_target is not None:
                    card.attached_to = aura_target.object_id
                    if card.object_id not in aura_target.attachments:
                        aura_target.attachments.append(card.object_id)
            card.known_to = list(self.seats)
            card.revealed_to = list(self.seats)
            self._refresh_world_supertype_timestamp(
                card,
                gained_at=card.zone_timestamp,
            )
        elif destination == "outside":
            known = set(card.known_to)
            known.add(card.owner)
            card.known_to = sorted(known)
            card.revealed_to = sorted(
                viewer
                for viewer in set(card.revealed_to)
                if viewer in known
            )
        else:
            owner_zone = self.state.players[card.owner].zones[destination]
            if destination == "library":
                owner_zone.insert(
                    self._library_insertion_index(
                        len(owner_zone),
                        library_position,
                    ),
                    object_id,
                )
                card.known_to = [card.owner]
                card.revealed_to = []
            else:
                owner_zone.append(object_id)
                if destination in PUBLIC_ZONES:
                    card.known_to = list(self.seats)
                    card.revealed_to = list(self.seats)
                else:
                    known = {card.owner, *(reveal_to or [])}
                    if destination == "hand":
                        if origin_identity_public:
                            known.update(self.seats)
                    card.known_to = sorted(known)
                    card.revealed_to = sorted(set(reveal_to or []))
        identity_became_hidden = (
            card.zone in HIDDEN_ZONES
            and not origin_identity_public
        )
        if log and identity_became_hidden:
            self._log(
                None,
                "zone.move",
                (
                    f"{card.owner} moved a card: "
                    f"{origin} → {card.zone}."
                ),
                {
                    "from": origin,
                    "to": card.zone,
                    "reason": reason,
                },
                changed_objects=[object_id],
                changed_players=[card.owner, card.controller],
            )
            identity_visibility = {
                card.owner,
                "analyst",
                *(reveal_to or []),
            }
            self._log(
                None,
                "zone.move.private",
                (
                    f"{card.ref} {card.printed_name}: "
                    f"{origin} → {card.zone}."
                ),
                {
                    "object": card.ref,
                    "from": origin,
                    "to": card.zone,
                    "reason": reason,
                    "tapped": card.tapped,
                },
                visibility=sorted(identity_visibility),
                changed_objects=[object_id],
                changed_players=[card.owner, card.controller],
            )
        elif log:
            self._log(
                None,
                "zone.move",
                f"{card.ref} {card.printed_name}: {origin} → {card.zone}.",
                {"object": card.ref, "from": origin, "to": card.zone, "reason": reason, "tapped": card.tapped},
                changed_objects=[object_id],
                changed_players=[card.owner, card.controller],
            )
        log_applied_zone_replacements(
            self,
            prepared_replacement,
            card,
            requested_destination=requested_destination,
            error_type=StateInvariantError,
        )
        commit_counter_events_from_resolution(self, prepared_replacement, reason=reason, log=log, error_type=StateInvariantError)
        if semantic_events:
            self._dispatch_zone_change_events(
                card,
                origin=origin,
                destination=destination,
                origin_controller=origin_controller,
                origin_logical_object_id=origin_logical_object_id,
                origin_data=origin_data,
                origin_attachments=origin_attachments,
                origin_attached_to=origin_attached_to,
                departure_sources=departure_sources,
                departure_source_zones=departure_source_zones,
                reason=reason,
            )
        return card

    @staticmethod
    def _library_position(position: str | int) -> str | int:
        if isinstance(position, bool):
            raise GameRuleError(
                "Library position must be top, bottom, or a positive N"
            )
        if isinstance(position, int):
            if position < 1:
                raise GameRuleError(
                    "Nth-from-top library position must be positive"
                )
            return position
        normalized = str(position).strip().casefold()
        if normalized not in {"top", "bottom"}:
            raise GameRuleError(
                "Library position must be top, bottom, or a positive N"
            )
        return normalized

    @staticmethod
    def _library_insertion_index(
        library_size: int,
        position: str | int | None,
    ) -> int:
        if position == "top":
            return library_size
        if position == "bottom":
            return 0
        if isinstance(position, int):
            # The internal list stores the top card last. If fewer than N
            # cards exist, CR 401.7 puts the incoming card on the bottom.
            return max(0, library_size - position + 1)
        raise GameRuleError("Validated library position is required")

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
        origin_logical_object_id: str,
        origin_data: Mapping[str, Any],
        origin_attachments: Sequence[str],
        origin_attached_to: str | None = None,
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
            "card_object_identity": origin_logical_object_id,
            "card_zone_change_counter": card.zone_change_counter,
            "owner": card.owner,
            "controller": card.controller,
            "previous_controller": origin_controller,
            "from": origin,
            "to": event_destination,
            "reason": reason,
            "token": card.is_token,
            "attachments": list(origin_attachments),
            "attached_to": origin_attached_to,
            "types": sorted(origin_types),
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
            if event_destination == "graveyard" and "creature" in origin_types:
                self._record_turn_history(
                    "creature_died",
                    actor=origin_controller,
                    object_incarnation=origin_logical_object_id,
                    types=origin_types,
                )
            if (
                event_destination == "graveyard"
                and "artifact" in origin_types
                and card.is_card_object
                and card.owner in self.active_seats
            ):
                emblem_owner = self.state.players[card.owner]
                emblem_sources: list[CardInstance | None] = [
                    self.state.cards[object_id]
                    for object_id in emblem_owner.zones["command"]
                    if (
                        self.state.cards[object_id].object_kind
                        == "emblem"
                        and self.state.cards[object_id].annotations.get(
                            "emblem_semantic_key"
                        )
                        == "builtin:daretti-emblem"
                    )
                ]
                if not emblem_owner.stats.get("emblem_objects_v1"):
                    emblem_sources.extend(
                        [None]
                        * int(
                            emblem_owner.stats.get(
                                "daretti_emblems", 0
                            )
                        )
                    )
                for emblem in emblem_sources:
                    ref = self._next_ref("S")
                    event_triggers.append(
                        StackItem(
                            stack_id=self._stable_runtime_id(
                                "stack", ref
                            ),
                            ref=ref,
                            kind="triggered_ability",
                            controller=card.owner,
                            label=(
                                "Daretti emblem — return artifact at "
                                "the next end step"
                            ),
                            semantic_key="builtin:daretti-emblem",
                            source_object_id=(
                                emblem.object_id
                                if emblem is not None
                                else None
                            ),
                            visibility=list(self.seats),
                            context={
                                "event": "artifact.graveyard",
                                "card": card.ref,
                                "card_zone_change_counter": (
                                    card.zone_change_counter
                                ),
                            },
                        )
                    )
            if (
                event_destination == "graveyard"
                and "creature" in origin_types
            ):
                for source in departure_sources:
                    source_data = self._effective_card_data(source)
                    source_types, _, _ = self._type_parts(
                        str(source_data.get("type_line") or "")
                    )
                    if "creature" not in source_types:
                        continue
                    has_thornbite_staff = any(
                        (
                            equipment := self.state.cards.get(
                                attachment_id
                            )
                        )
                        is not None
                        and equipment.printed_name == "Thornbite Staff"
                        for attachment_id in source.attachments
                    )
                    if not has_thornbite_staff:
                        continue
                    ref = self._next_ref("S")
                    event_triggers.append(
                        StackItem(
                            stack_id=self._stable_runtime_id(
                                "stack",
                                ref,
                            ),
                            ref=ref,
                            kind="triggered_ability",
                            controller=source.controller,
                            label=(
                                f"{self.display_name(source.object_id)} "
                                "Thornbite Staff untap trigger"
                            ),
                            source_object_id=source.object_id,
                            semantic_key="builtin:thornbite-untap",
                            visibility=list(self.seats),
                            context={
                                "event": "creature.dies",
                                "card": card.ref,
                            },
                        )
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
        entered_types, entered_subtypes, _ = self._type_parts(
            str(entered_data.get("type_line") or "")
        )
        entered_context = {
            **common,
            "controller": card.controller,
            "types": sorted(entered_types),
            "subtypes": sorted(entered_subtypes),
            "mana_value": float(
                entered_data.get("mana_value", 0) or 0
            ),
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
        if "saga" in entered_subtypes:
            self._add_saga_lore(
                card,
                trigger_batch=event_triggers,
                reason="Saga entered",
            )
        if owns_trigger_batch:
            self._enqueue_semantic_trigger_batch(event_triggers)

    def _add_saga_lore(
        self,
        saga: CardInstance,
        *,
        trigger_batch: list[StackItem] | None = None,
        reason: str,
    ) -> int:
        if saga.zone != "battlefield" or saga.phased_out:
            return int(saga.counters.get("lore", 0))
        _, subtypes, _ = self._type_parts(
            str(self._effective_card_data(saga).get("type_line") or "")
        )
        if "saga" not in subtypes:
            return int(saga.counters.get("lore", 0))
        chapter = int(saga.counters.get("lore", 0)) + 1
        saga.counters["lore"] = chapter
        self._log(
            saga.controller,
            "saga.lore",
            f"{saga.ref} received lore counter {chapter}.",
            {
                "source": saga.ref,
                "chapter": chapter,
                "reason": reason,
            },
            importance=1,
            changed_objects=[saga.object_id],
            changed_players=[saga.controller],
        )
        self._dispatch_semantic_event(
            f"saga.chapter.{chapter}",
            {
                "card": saga.ref,
                "controller": saga.controller,
                "chapter": chapter,
            },
            trigger_batch=trigger_batch,
        )
        return chapter

    def _advance_active_player_sagas(self, seat: str) -> None:
        trigger_batch: list[StackItem] = []
        for object_id in list(
            self.state.players[seat].zones["battlefield"]
        ):
            saga = self.state.cards[object_id]
            if saga.controller != seat:
                continue
            self._add_saga_lore(
                saga,
                trigger_batch=trigger_batch,
                reason="precombat main phase began",
            )
        self._enqueue_semantic_trigger_batch(trigger_batch)

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
        prepared_replacements = {
            object_id: prepare_zone_change_replacement(
                self,
                self.state.cards[object_id],
                destination,
                sources=sources,
                source_zones=source_zones,
                error_type=GameRuleError,
            )
            for object_id, destination in changes
        }
        snapshots: list[
            tuple[
                CardInstance,
                str,
                str,
                str,
                dict[str, Any],
                list[str],
                str | None,
                str,
            ]
        ] = []
        for object_id, destination in changes:
            card = self.state.cards[object_id]
            snapshots.append(
                (
                    card,
                    card.zone,
                    card.controller,
                    card.logical_object_id,
                    copy.deepcopy(self._effective_card_data(card)),
                    [
                        self.state.cards[attachment_id].ref
                        for attachment_id in card.attachments
                        if attachment_id in self.state.cards
                    ],
                    (
                        self.state.cards[card.attached_to].ref
                        if card.attached_to in self.state.cards
                        else None
                    ),
                    destination,
                )
            )
        # CR 704.8 last-known information comes from the state before any
        # object in the batch moves.  Keep discovery and mutation in separate
        # loops so a departing static source cannot change a later snapshot.
        destination_timestamp = self._next_zone_timestamp()
        for object_id, destination in changes:
            self.move_card(
                object_id,
                destination,
                zone_timestamp=destination_timestamp,
                reason=reason,
                log=log,
                semantic_events=False,
                replacement_sources=sources,
                replacement_source_zones=source_zones,
                prepared_replacement=prepared_replacements[object_id],
            )
        trigger_batch: list[StackItem] = []
        for (
            card,
            origin,
            origin_controller,
            origin_logical_object_id,
            origin_data,
            origin_attachments,
            origin_attached_to,
            _requested_destination,
        ) in snapshots:
            self._dispatch_zone_change_events(
                card,
                origin=origin,
                destination=card.zone,
                origin_controller=origin_controller,
                origin_logical_object_id=origin_logical_object_id,
                origin_data=origin_data,
                origin_attachments=origin_attachments,
                origin_attached_to=origin_attached_to,
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
            object_id = player.zones["library"][-1]
            card = self.move_card(
                object_id,
                "hand",
                reason=reason,
                log=False,
            )
            player.draw_history.append(
                {"turn_sequence": self.state.turn_sequence, "card": card.printed_name, "object": card.ref, "reason": reason}
            )
            drawn.append(object_id)
        if drawn:
            draw_tracker = player.stats.setdefault("cards_drawn_by_turn", {})
            turn_key = str(self.state.turn_sequence)
            before_count = int(draw_tracker.get(turn_key, 0))
            draw_tracker[turn_key] = before_count + len(drawn)
            in_own_draw_step = bool(
                self.state.active_player == seat
                and (self.state.phase, self.state.step)
                == ("beginning", "draw")
            )
            draw_step_tracker = player.stats.setdefault(
                "cards_drawn_in_draw_step_by_turn", {}
            )
            before_draw_step_count = (
                int(draw_step_tracker.get(turn_key, 0))
                if in_own_draw_step
                else 0
            )
            if in_own_draw_step:
                draw_step_tracker[turn_key] = (
                    before_draw_step_count + len(drawn)
                )
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
            for index, object_id in enumerate(drawn):
                if in_own_draw_step and before_draw_step_count + index == 0:
                    continue
                self._dispatch_semantic_event(
                    "card.draw_except_first_draw_step",
                    {
                        "player": seat,
                        "object": self.state.cards[object_id].ref,
                        "reason": reason,
                        "in_own_draw_step": in_own_draw_step,
                        "draw_step_ordinal": (
                            before_draw_step_count + index + 1
                            if in_own_draw_step
                            else None
                        ),
                    },
                )
        return drawn

    def _dredge_candidates(self, seat: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        library_size = len(self.state.players[seat].zones["library"])
        for object_id in self.state.players[seat].zones["graveyard"]:
            card = self.state.cards[object_id]
            record = self.card_record(card)
            if record is None:
                continue
            match = re.search(
                r"\bDredge\s+(?P<count>\d+)\b",
                record.oracle_text,
                re.IGNORECASE,
            )
            if match is None:
                continue
            count = int(match.group("count"))
            program = self.semantics.get(
                f"{record.oracle_id}:replacement:dredge"
            )
            if (
                count <= library_size
                and program is not None
                and self.semantic_program_is_current_trusted(program)
                and "draw_replacement" in program.coverage
            ):
                candidates.append(
                    {
                        "id": card.ref,
                        "name": card.printed_name,
                        "mill": count,
                    }
                )
        return candidates

    def _begin_draw_sequence(
        self,
        seat: str,
        count: int,
        *,
        reason: str,
        private: bool = False,
        continuation: Mapping[str, Any] | None = None,
    ) -> None:
        """Perform draws one at a time, pausing for trusted replacements."""

        if count <= 0:
            self._resume_after_draw(dict(continuation or {}))
            return
        candidates = self._dredge_candidates(seat)
        if candidates:
            self.permissions.issue(
                kind="draw.replacement",
                role="pilot",
                actors=[seat],
                allowed_actions=["choose"],
                payload_by_actor={
                    seat: {
                        "reason": reason,
                        "remaining_draws": count,
                        "options": [
                            {
                                "id": "draw",
                                "label": "Draw a card",
                            },
                            *[
                                {
                                    "id": candidate["id"],
                                    "label": (
                                        f"Dredge {candidate['mill']} — "
                                        f"{candidate['name']}"
                                    ),
                                }
                                for candidate in candidates
                            ],
                        ],
                        "legal_actions": [
                            {
                                "id": "choose",
                                "action": "choose",
                                "choice_schema": {
                                    "field": "choice",
                                    "legal_values": [
                                        "draw",
                                        *[
                                            candidate["id"]
                                            for candidate in candidates
                                        ],
                                    ],
                                },
                            }
                        ],
                    }
                },
                continuation={
                    "seat": seat,
                    "remaining_draws": count,
                    "reason": reason,
                    "private": private,
                    "candidates": candidates,
                    "after": copy.deepcopy(dict(continuation or {})),
                },
            )
            return
        self.draw(seat, 1, reason=reason, private=private)
        self._begin_draw_sequence(
            seat,
            count - 1,
            reason=reason,
            private=private,
            continuation=continuation,
        )

    def _complete_draw_replacement(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        continuation = dict(decision.continuation)
        choice = str(
            response.get("choice")
            or response.get("card")
            or response.get("option")
            or ""
        )
        candidates = {
            str(candidate["id"]): dict(candidate)
            for candidate in continuation.get("candidates", [])
        }
        reason = str(continuation.get("reason") or "draw")
        if choice == "draw":
            self.draw(
                seat,
                1,
                reason=reason,
                private=bool(continuation.get("private", False)),
            )
        elif choice in candidates:
            candidate = candidates[choice]
            card = self._resolve_object(
                seat,
                choice,
                zones={"graveyard"},
                owned_only=True,
            )
            current = next(
                (
                    value
                    for value in self._dredge_candidates(seat)
                    if value["id"] == card.ref
                ),
                None,
            )
            if current is None or int(current["mill"]) != int(
                candidate["mill"]
            ):
                raise GameRuleError(
                    "The selected Dredge replacement is no longer available"
                )
            mill_count = int(candidate["mill"])
            library = self.state.players[seat].zones["library"]
            milled_ids = list(reversed(library[-mill_count:]))
            self._move_cards_simultaneously(
                [
                    (object_id, "graveyard")
                    for object_id in milled_ids
                ],
                reason=f"Dredge {mill_count}",
                log=False,
            )
            self.move_card(
                card.object_id,
                "hand",
                reason=f"Dredge {mill_count}",
                semantic_events=True,
            )
            self._log(
                seat,
                "draw.replaced.dredge",
                (
                    f"{seat} replaced a draw by milling {mill_count} "
                    f"and returning {card.ref}."
                ),
                {
                    "player": seat,
                    "card": card.ref,
                    "mill": mill_count,
                    "objects": [
                        self.state.cards[object_id].ref
                        for object_id in milled_ids
                    ],
                    "reason": reason,
                },
                visibility=[seat, "analyst"],
                importance=2,
                changed_objects=[card.object_id, *milled_ids],
                changed_players=[seat],
            )
        else:
            raise GameRuleError(
                "Choose the normal draw or an available Dredge card"
            )
        self._begin_draw_sequence(
            seat,
            int(continuation.get("remaining_draws", 1)) - 1,
            reason=reason,
            private=bool(continuation.get("private", False)),
            continuation=dict(continuation.get("after") or {}),
        )

    def _resume_after_draw(self, continuation: Mapping[str, Any]) -> None:
        kind = str(continuation.get("kind") or "none")
        if kind == "none":
            return
        if kind == "turn_draw":
            self._complete_draw_step_entry(str(continuation["seat"]))
            return
        if kind == "semantic_resolution":
            self._continue_resolution(
                stack_ref=str(continuation["stack_ref"]),
                effects=[
                    dict(value)
                    for value in continuation.get("effects", [])
                ],
                destination=continuation.get("destination"),
                note=str(continuation.get("note") or ""),
                instruction_pointer=int(
                    continuation.get("instruction_pointer", 0)
                ),
            )
            return
        raise GameRuleError(
            f"Unsupported post-draw continuation {kind!r}"
        )

    def _complete_draw_step_entry(self, active: str) -> None:
        """Put draw-step triggers on the stack only after the turn draw.

        CR 504.1's draw is a turn-based action.  Beginning-of-draw-step
        triggers have already triggered, but CR 504.2 does not put them on
        the stack or grant priority until after that action and the ensuing
        state-based-action check.  Collect semantic and delayed triggers into
        one APNAP/order batch so neither source kind can preempt the draw.
        """

        context = {
            "phase": self.state.phase,
            "step": self.state.step,
            "player": active,
        }
        trigger_batch: list[StackItem] = []
        self._dispatch_semantic_event(
            "step.begin",
            context,
            trigger_batch=trigger_batch,
        )
        if self._semantic_pause_annotation() is not None:
            return
        trigger_batch.extend(
            self._delayed_trigger_stack_item(trigger)
            for trigger in self._matching_delayed_triggers(
                "step.begin",
                context,
            )
        )
        self._enqueue_semantic_trigger_batch(trigger_batch)
        if self._stabilize():
            return
        self._grant_priority(active)

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
        elif kind == "state.battle_protector":
            self._complete_battle_protector_choice(decision)
        elif kind == "battle.enter_protector":
            self._complete_battle_entry_protector_choice(decision)
        elif kind == "battle.siege_defeated":
            self._complete_siege_defeated_choice(decision)
        elif kind == "choice.apnap":
            self._complete_apnap_choice(decision)
        elif kind == "replacement.order":
            complete_replacement_order_choice(
                self,
                decision,
                error_type=GameRuleError,
            )
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
        elif kind == "draw.replacement":
            self._complete_draw_replacement(decision)
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
            values = list(
                response.get("cards")
                or response.get("card_ids")
                or response.get("bottom")
                or []
            )
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
        if entry.skip_steps:
            raise GameRuleError(
                "Skipped-step turn entries are not implemented; "
                "the turn cannot begin"
            )
        if not self.state.players[entry.player].in_game:
            self._begin_turn(self._select_next_turn())
            return
        self.state.current_turn = entry
        self.state.active_player = entry.player
        if not entry.extra:
            self.state.last_normal_turn_player = entry.player
        self.state.turn_sequence += 1
        if self.state.turn_history is not None:
            self.state.turn_history = TurnHistory(
                turn_sequence=self.state.turn_sequence
            )
        player = self.state.players[entry.player]
        player.stats.pop(
            "protection_from_everything_until_next_turn",
            None,
        )
        next_turn_controller = player.stats.pop(
            "next_turn_controlled_by",
            None,
        )
        if (
            next_turn_controller in self.active_seats
            and next_turn_controller != entry.player
        ):
            player.stats["turn_controlled_by"] = (
                next_turn_controller
            )
        else:
            player.stats.pop("turn_controlled_by", None)
        player.turns_begun += 1
        self._expire_goad_designations(entry.player)
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

    def _expire_goad_designations(self, player: str) -> None:
        """Expire CR 701.15 designations at the goading player's turn."""

        turns_begun = self.state.players[player].turns_begun
        changed: list[str] = []
        for card in self.state.cards.values():
            retained = [
                designation
                for designation in card.goaded_by
                if not (
                    designation.player == player
                    and designation.expires_at_turns_begun <= turns_begun
                )
            ]
            if len(retained) != len(card.goaded_by):
                card.goaded_by = retained
                changed.append(card.object_id)
        if changed:
            self._log(
                player,
                "permanent.goad.expire",
                f"{len(changed)} goad designation(s) expired as {player}'s turn began.",
                {
                    "player": player,
                    "turns_begun": turns_begun,
                    "objects": [
                        self.state.cards[object_id].ref
                        for object_id in changed
                    ],
                },
                importance=1,
                changed_objects=changed,
            )

    def _clear_mana(self, *, reason: str) -> None:
        for seat, player in self.state.players.items():
            if any(player.mana_pool.values()):
                lost = dict(player.mana_pool)
                player.mana_pool = normalize_mana_bundle(None)
                player.stats.pop("restricted_mana", None)
                self._log(seat, "mana.empty", f"{seat}'s mana pool emptied.", {"lost": lost, "reason": reason}, importance=0, changed_players=[seat])

    def _untap_permanent(
        self,
        card: CardInstance,
        *,
        actor: str | None,
        reason: str,
    ) -> bool:
        if not card.tapped:
            return False
        stun = int(card.counters.get("stun", 0))
        if stun > 0:
            if stun == 1:
                card.counters.pop("stun", None)
            else:
                card.counters["stun"] = stun - 1
            self._log(
                actor,
                "permanent.untap.replaced",
                f"A stun counter was removed from {card.ref} instead of untapping it.",
                {
                    "object": card.ref,
                    "counter": "stun",
                    "reason": reason,
                },
                importance=1,
                changed_objects=[card.object_id],
                changed_players=[card.controller],
            )
            return False
        card.tapped = False
        return True

    def _unsupported_phasing_source_at_untap(
        self,
        active: str,
    ) -> CardInstance | None:
        """Return a permanent whose CR 502.1 action cannot be approximated.

        The state model can hide an object with ``phased_out``, but it does
        not yet preserve indirect-phasing groups or the controller-at-phase-
        out fact required to execute phasing generically.  Silently leaving
        such an object phased out—or merely untapping a permanent with
        phasing—would be materially wrong, so the turn transition stops
        before any untap-step action mutates state.
        """

        for object_id in self.state.players[active].zones["battlefield"]:
            card = self.state.cards[object_id]
            if card.controller != active:
                continue
            keywords = {
                str(value).casefold()
                for value in self._effective_card_data(card).get(
                    "keywords", []
                )
            }
            if card.phased_out or "phasing" in keywords:
                return card
        return None

    def _unsupported_untap_selection_source(
        self,
    ) -> CardInstance | None:
        """Find a represented global untap limit that needs a player choice."""

        for seat in self.active_seats:
            for object_id in self.state.players[seat].zones["battlefield"]:
                card = self.state.cards[object_id]
                if card.phased_out:
                    continue
                oracle_text = str(
                    self._effective_card_data(card).get("oracle_text")
                    or ""
                ).casefold()
                if (
                    "can't untap more than" not in oracle_text
                    or "during their untap steps" not in oracle_text
                ):
                    continue
                if (
                    "as long as this artifact is untapped" in oracle_text
                    and card.tapped
                ):
                    continue
                return card
        return None

    def _enter_step(
        self,
        *,
        held_triggers: Sequence[StackItem] = (),
    ) -> None:
        phase, step = TURN_STEPS[self.state.phase_index]
        self.state.phase = phase
        self.state.step = step
        self.state.priority_player = None
        self.state.priority_passes = []
        self._log(None, "step.begin", f"{self.state.turn_sequence}:{phase}/{step}.", importance=0)
        active = self.state.active_player
        if active is None:
            raise StateInvariantError("A turn has no active player")

        if step == "beginning_combat":
            # The supported Commander multiplayer profile uses the attack-
            # multiple-players option (CR 802.2), so every active opponent
            # is a defending player as combat begins. Two-player Commander
            # has the same result with its single nonactive player. Variants
            # that require the CR 507.1 defending-player choice are rejected
            # at the profile boundary rather than guessed here.
            self.state.combat = CombatState(
                defending_players=[
                    seat
                    for seat in self.active_seats
                    if seat != active
                ]
            )

        if step == "untap":
            unsupported_phasing = (
                self._unsupported_phasing_source_at_untap(active)
            )
            if unsupported_phasing is not None:
                self._pause_for_unsupported_semantic(
                    event="untap.phasing",
                    source=unsupported_phasing,
                )
                return
            unsupported_selection = (
                self._unsupported_untap_selection_source()
            )
            if unsupported_selection is not None:
                self._pause_for_unsupported_semantic(
                    event="untap.selection_restriction",
                    source=unsupported_selection,
                )
                return
            # CR 502.4 and 503.1a hold every ability that triggers during
            # untap until the first priority opportunity in upkeep.  Untap
            # cannot be interrupted, so this batch can remain on the Python
            # call stack while the engine synchronously crosses the boundary;
            # no unserialized game state exists at a command/checkpoint
            # boundary.
            waiting_triggers: list[StackItem] = []
            untap_context = {
                "phase": phase,
                "step": step,
                "player": active,
            }
            self._dispatch_semantic_event(
                "step.begin",
                untap_context,
                trigger_batch=waiting_triggers,
            )
            waiting_triggers.extend(
                self._delayed_trigger_stack_item(trigger)
                for trigger in self._matching_delayed_triggers(
                    "step.begin",
                    untap_context,
                )
            )
            untapped_object_ids: list[str] = []
            if self.state.config.auto_untap:
                changed: list[str] = []
                intruder_alarm_active = any(
                    "creatures don't untap during their controllers' "
                    "untap steps"
                    in str(
                        self._effective_card_data(permanent).get(
                            "oracle_text"
                        )
                        or ""
                    ).casefold()
                    for permanent in self.state.cards.values()
                    if permanent.zone == "battlefield"
                    and not permanent.phased_out
                )
                for object_id in list(self.state.players[active].zones["battlefield"]):
                    card = self.state.cards[object_id]
                    if card.controller != active or card.phased_out:
                        continue
                    if card.annotations.pop("does_not_untap_next", False):
                        continue
                    if (
                        intruder_alarm_active
                        and "creature"
                        in self._type_parts(
                            str(
                                self._effective_card_data(card).get(
                                    "type_line"
                                )
                                or ""
                            )
                        )[0]
                    ):
                        continue
                    if self._untap_permanent(
                        card,
                        actor=active,
                        reason="untap step",
                    ):
                        changed.append(object_id)
                        untapped_object_ids.append(object_id)
                if changed:
                    self._log(active, "permanent.untap", f"{active} untapped {len(changed)} permanent(s).", {"objects": [self.state.cards[oid].ref for oid in changed]}, importance=0, changed_objects=changed, changed_players=[active])
                for seat in self.active_seats:
                    if seat == active or not self._controller_has_oracle_text(
                        seat,
                        "untap all permanents you control during each "
                        "other player's untap step",
                    ):
                        continue
                    extra_changed: list[str] = []
                    for object_id in list(
                        self.state.players[seat].zones["battlefield"]
                    ):
                        card = self.state.cards[object_id]
                        if (
                            card.controller == seat
                            and not card.phased_out
                            and self._untap_permanent(
                                card,
                                actor=seat,
                                reason="Seedborn Muse",
                            )
                        ):
                            extra_changed.append(object_id)
                            untapped_object_ids.append(object_id)
                    if extra_changed:
                        self._log(
                            seat,
                            "permanent.untap",
                            (
                                f"{seat} untapped {len(extra_changed)} "
                                "permanent(s) during another player's "
                                "untap step."
                            ),
                            {
                                "objects": [
                                    self.state.cards[object_id].ref
                                    for object_id in extra_changed
                                ],
                                "reason": "Seedborn Muse",
                            },
                            importance=1,
                            changed_objects=extra_changed,
                            changed_players=[seat],
                        )
            for object_id in untapped_object_ids:
                card = self.state.cards[object_id]
                event_context = {
                    "card": card.ref,
                    "player": active,
                    "controller": card.controller,
                    "phase": phase,
                    "step": step,
                    "reason": "untap step",
                }
                self._dispatch_semantic_event(
                    "permanent.untap",
                    event_context,
                    trigger_batch=waiting_triggers,
                )
                waiting_triggers.extend(
                    self._delayed_trigger_stack_item(trigger)
                    for trigger in self._matching_delayed_triggers(
                        "permanent.untap",
                        event_context,
                    )
                )
            self._advance_step(held_triggers=waiting_triggers)
            return

        if phase == "precombat_main" and step == "main":
            self._advance_active_player_sagas(active)

        if step == "cleanup":
            # Abilities can trigger at the beginning of cleanup, but CR
            # 514.1-2 happen before those waiting triggers are put on the
            # stack and before the exceptional priority window.  Enqueue
            # represented semantic triggers now without stabilizing them.
            self._dispatch_semantic_event(
                "step.begin",
                {"phase": phase, "step": step, "player": active},
            )
            hand = self.state.players[active].zones["hand"]
            excess = (
                len(hand)
                - self.state.players[active].max_hand_size
            )
            if excess > 0:
                self.permissions.issue(
                    kind="cleanup.discard",
                    role="pilot",
                    actors=[active],
                    allowed_actions=["discard"],
                    payload_by_actor={
                        active: {
                            "count": excess,
                            "hand": [
                                {
                                    "id": self.state.cards[oid].ref,
                                    "name": self.state.cards[
                                        oid
                                    ].printed_name,
                                }
                                for oid in hand
                            ],
                        }
                    },
                )
                return
            self._finish_cleanup()
            return

        if step in {"beginning_combat", "end_step", "end_combat"}:
            # None of these supported-profile boundaries has a turn-based
            # choice. Collect both permanent-based and delayed beginning-of-
            # step triggers before granting priority. A delayed trigger must
            # not cause semantic event dispatch to be skipped.
            context = {
                "phase": phase,
                "step": step,
                "player": active,
            }
            waiting_triggers: list[StackItem] = []
            self._dispatch_semantic_event(
                "step.begin",
                context,
                trigger_batch=waiting_triggers,
            )
            waiting_triggers.extend(
                self._delayed_trigger_stack_item(trigger)
                for trigger in self._matching_delayed_triggers(
                    "step.begin",
                    context,
                )
            )
            if step == "end_step" and self.state.monarch == active:
                monarch = str(self.state.monarch)
                waiting_triggers.append(
                    self._monarch_trigger(
                        controller=monarch,
                        label="The monarch — draw a card",
                        effects=(
                            {
                                "op": "draw",
                                "player": monarch,
                                "count": 1,
                                "private": True,
                                "reason": "the monarch's end-step trigger",
                            },
                        ),
                        context={
                            "event": "step.begin",
                            "phase": phase,
                            "step": step,
                            "player": active,
                            "monarch_at_trigger": monarch,
                            "inherent_rule": "CR 725.2a",
                        },
                    )
                )
            self._enqueue_semantic_trigger_batch(waiting_triggers)
            self._grant_priority(active)
            return

        if step == "upkeep":
            # All abilities that triggered since the last priority window,
            # including during untap, form one APNAP/controller-order batch.
            # A delayed trigger must not suppress permanent-based upkeep
            # triggers, and trigger time within the no-priority interval must
            # not determine stack order.
            context = {
                "phase": phase,
                "step": step,
                "player": active,
            }
            waiting_triggers = list(held_triggers)
            self._dispatch_semantic_event(
                "step.begin",
                context,
                trigger_batch=waiting_triggers,
            )
            waiting_triggers.extend(
                self._delayed_trigger_stack_item(trigger)
                for trigger in self._matching_delayed_triggers(
                    "step.begin",
                    context,
                )
            )
            self._enqueue_semantic_trigger_batch(waiting_triggers)
            self._grant_priority(active)
            return

        if step == "draw":
            first_turn = self.state.turn_sequence == 1
            should_draw = not first_turn or self.state.config.effective_first_player_draws(len(self.seats))
            if self.state.config.auto_draw and should_draw:
                self._begin_draw_sequence(
                    active,
                    1,
                    reason="turn-based draw",
                    continuation={
                        "kind": "turn_draw",
                        "seat": active,
                    },
                )
                return
            elif not should_draw:
                self._log(active, "draw.skip", f"{active} skipped the first-turn draw.", importance=0)
            self._complete_draw_step_entry(active)
            return

        delayed = self._matching_delayed_triggers(
            "step.begin",
            {
                "phase": phase,
                "step": step,
                "player": active,
            },
        )
        if delayed:
            self._start_trigger_batch(delayed, after="grant_priority")
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
        self._dispatch_semantic_event(
            "step.begin",
            {"phase": phase, "step": step, "player": active},
        )
        self._grant_priority(active)

    def _advance_step(
        self,
        *,
        held_triggers: Sequence[StackItem] = (),
    ) -> None:
        self._clear_mana(reason="step or phase ended")
        if (
            self.state.phase,
            self.state.step,
        ) == ("combat", "end_combat"):
            self._finish_combat_phase()
        if (
            self.state.phase,
            self.state.step,
        ) == ("combat", "declare_attackers") and not (
            self.state.combat.had_attacking_creature
            or self.state.combat.attackers
        ):
            # CR 508.8 skips both intervening combat steps when combat has
            # no attacking creatures. The post-declaration priority window
            # still happens; this branch runs only after that window ends.
            self.state.phase_index = TURN_STEPS.index(
                ("combat", "end_combat")
            )
            self._enter_step()
            return
        if (
            self.state.phase,
            self.state.step,
        ) == ("combat", "combat_damage") and (
            self.state.combat.first_strike_step
            and self.state.combat.damage_step_index == 0
        ):
            # CR 510.4 creates a second combat-damage step. It is a real
            # step boundary: mana has already emptied above, another
            # step.begin event is emitted, and the surviving participants
            # are recomputed before assignment.
            self.state.combat.damage_step_index = 1
            self._enter_step(held_triggers=held_triggers)
            return
        self.state.phase_index += 1
        if self.state.phase_index >= len(TURN_STEPS):
            if (
                self.state.phase,
                self.state.step,
            ) == ("ending", "cleanup"):
                # Priority during cleanup is exceptional.  Once its stack is
                # empty and every player passes, CR 514.3a starts another
                # cleanup step rather than the next turn.
                self.state.phase_index = TURN_STEPS.index(
                    ("ending", "cleanup")
                )
                self._enter_step()
                return
            self._finish_cleanup()
            return
        self._enter_step(held_triggers=held_triggers)

    def _finish_combat_phase(self) -> None:
        """Remove every represented object from combat at the CR 511.3 boundary."""

        changed_objects: list[str] = []
        for card in sorted(
            self.state.cards.values(),
            key=lambda candidate: (candidate.ref, candidate.object_id),
        ):
            if card.attacking is None and card.blocking is None:
                continue
            card.attacking = None
            card.blocking = None
            changed_objects.append(card.object_id)
        previous = self.state.combat
        self.state.combat = CombatState()
        self._log(
            None,
            "combat.end",
            "The combat phase ended and all objects were removed from combat.",
            {
                "attackers": len(previous.attackers),
                "blockers": sum(
                    len(blockers)
                    for blockers in previous.blockers.values()
                ),
                "defending_players": list(previous.defending_players),
            },
            importance=0,
            changed_objects=changed_objects,
        )

    def _remove_object_from_combat(
        self,
        card: CardInstance,
        *,
        reason: str,
    ) -> bool:
        """Clear one object's represented CR 506.4 combat relationships."""

        was_attacker = (
            card.attacking is not None
            or card.object_id in self.state.combat.attackers
        )
        was_blocker = card.blocking is not None
        removed_blocker_links = False
        for blocker_ids in self.state.combat.blockers.values():
            if card.object_id not in blocker_ids:
                continue
            blocker_ids[:] = [
                object_id
                for object_id in blocker_ids
                if object_id != card.object_id
            ]
            removed_blocker_links = True
        if not (was_attacker or was_blocker or removed_blocker_links):
            return False

        if was_attacker:
            self.state.combat.attackers.pop(card.object_id, None)
            self.state.combat.attack_target_context.pop(
                card.object_id, None
            )
        card.attacking = None
        card.blocking = None
        self._log(
            card.controller,
            "combat.remove",
            f"{card.ref} was removed from combat.",
            {
                "object": card.ref,
                "was_attacking": was_attacker,
                "was_blocking": was_blocker or removed_blocker_links,
                "reason": reason,
            },
            importance=1,
            changed_objects=[card.object_id],
            changed_players=[card.controller],
        )
        return True

    def _remove_invalid_combat_objects(self) -> bool:
        """Remove represented combatants invalidated by CR 506.4 state."""

        candidates: list[CardInstance] = []
        candidate_ids: set[str] = set()
        for object_id in self.state.combat.attackers:
            card = self.state.cards.get(object_id)
            if card is not None and object_id not in candidate_ids:
                candidates.append(card)
                candidate_ids.add(object_id)
        for blocker_ids in self.state.combat.blockers.values():
            for object_id in blocker_ids:
                card = self.state.cards.get(object_id)
                if card is not None and object_id not in candidate_ids:
                    candidates.append(card)
                    candidate_ids.add(object_id)

        changed = False
        for card in candidates:
            data = self._effective_card_data(card)
            card_types, _, _ = self._type_parts(
                str(data.get("type_line") or "")
            )
            invalid_reason: str | None = None
            if card.zone != "battlefield":
                invalid_reason = "left the battlefield"
            elif card.phased_out:
                invalid_reason = "phased out"
            elif "creature" not in card_types:
                invalid_reason = "stopped being a creature"
            elif "battle" in card_types:
                invalid_reason = "became a Battle"
            elif (
                card.object_id in self.state.combat.attackers
                and card.controller != self.state.active_player
            ):
                invalid_reason = "attacker control changed"
            if invalid_reason is not None:
                changed = (
                    self._remove_object_from_combat(
                        card,
                        reason=invalid_reason,
                    )
                    or changed
                )
        return changed

    def _active_cleanup_frame(self) -> dict[str, Any] | None:
        return next(
            (
                annotation
                for annotation in reversed(self.state.annotations)
                if annotation.get("kind") == "cleanup_exception_frame"
                and annotation.get("active", False)
            ),
            None,
        )

    def _remove_cleanup_frames(self) -> None:
        self.state.annotations = [
            annotation
            for annotation in self.state.annotations
            if annotation.get("kind") != "cleanup_exception_frame"
        ]

    def _finish_cleanup(self) -> None:
        active = self.state.active_player
        in_cleanup_step = (
            self.state.phase,
            self.state.step,
        ) == ("ending", "cleanup")
        self._remove_cleanup_frames()
        cleanup_iteration = 1 + sum(
            event.code == "turn.cleanup"
            and event.turn_sequence == self.state.turn_sequence
            for event in self.state.events
        )
        cleanup_delayed = (
            self._matching_delayed_triggers(
                "step.begin",
                {
                    "phase": "ending",
                    "step": "cleanup",
                    "player": active,
                },
            )
            if in_cleanup_step
            else []
        )
        frame = {
            "kind": "cleanup_exception_frame",
            "active": True,
            "turn_sequence": self.state.turn_sequence,
            "active_player": active,
            "iteration": cleanup_iteration,
            "delayed_trigger_ids": [
                trigger.trigger_id for trigger in cleanup_delayed
            ],
            "delayed_triggers_queued": False,
            "priority_granted": False,
            "exception_reasons": [],
        }
        if in_cleanup_step:
            self.state.annotations.append(frame)
        for card in self.state.cards.values():
            card.marked_damage = 0
            card.deathtouch_damage = False
            card.temporary_keywords.clear()
            card.attacking = None
            card.blocking = None
            until_end = dict(
                card.annotations.get("until_end_of_turn") or {}
            )
            if "copy_overrides_previous" in until_end:
                previous = until_end["copy_overrides_previous"]
                if previous is None:
                    card.annotations.pop("copy_overrides", None)
                else:
                    card.annotations["copy_overrides"] = copy.deepcopy(
                        previous
                    )
            previous_controller = until_end.get("control_previous")
            if (
                previous_controller in self.state.players
                and card.zone == "battlefield"
                and card.controller != previous_controller
            ):
                self.change_control(
                    card.object_id,
                    str(previous_controller),
                    reason="temporary control effect ended",
                )
            card.annotations.pop("until_end_of_turn", None)
        for player in self.state.players.values():
            player.stats.pop("next_spell_improvise", None)
            player.stats.pop("next_spell_uncounterable", None)
            player.stats.pop(
                "spells_cant_be_countered_until_end",
                None,
            )
            player.stats.pop("hexproof_from_colors_until_end", None)
        self._clear_mana(reason="cleanup")
        self._log(active, "turn.cleanup", f"{active} completed cleanup.", importance=0)
        if active in self.state.players:
            self.state.players[active].stats.pop(
                "turn_controlled_by",
                None,
            )
        if self.state.game_over:
            self._remove_cleanup_frames()
            return
        if in_cleanup_step:
            before_stabilize_event = self.state.event_sequence
            waiting = self._stabilize()
            stabilization_events = [
                event
                for event in self.state.events
                if event.event_id > before_stabilize_event
            ]
            reasons: list[str] = []
            if cleanup_delayed:
                reasons.append("cleanup_trigger")
            if waiting:
                reasons.append("state_or_trigger_choice")
            if any(
                event.code.startswith("state.")
                or event.code == "player.eliminated"
                for event in stabilization_events
            ):
                reasons.append("state_based_action")
            if (
                self.state.stack
                or self.state.pending_trigger_batches
                or any(
                    event.code == "stack.trigger"
                    for event in stabilization_events
                )
            ):
                reasons.append("trigger_waiting")
            frame["exception_reasons"] = (
                unique_preserving_order(reasons)
            )
            if reasons:
                self._log(
                    active,
                    "cleanup.priority_required",
                    (
                        "Cleanup created a state action or waiting "
                        "trigger; the active player receives priority."
                    ),
                    {
                        "iteration": cleanup_iteration,
                        "reasons": frame["exception_reasons"],
                    },
                    importance=2,
                    changed_players=[active] if active else [],
                )
                if waiting:
                    return
                self._grant_priority(active)
                return
            self._remove_cleanup_frames()
        self._begin_turn(self._select_next_turn())

    def _end_turn_now(self, *, actor: str, reason: str) -> None:
        """Perform the special action sequence used by end-the-turn effects."""

        exiled_cards: list[str] = []
        for stack_item in list(self.state.stack):
            if not stack_item.card_object_id:
                continue
            card = self.state.cards.get(stack_item.card_object_id)
            if card is None or card.zone != "stack":
                continue
            self.move_card(
                card.object_id,
                "exile",
                reason=reason,
                log=False,
                semantic_events=False,
            )
            exiled_cards.append(card.object_id)
        removed_items = list(self.state.stack)
        removed_stack = [item.ref for item in removed_items]
        self.state.stack.clear()
        for item in removed_items:
            self._maybe_sacrifice_completed_saga(item)
        self.state.pending_trigger_batches.clear()
        self.permissions.invalidate_current()
        self.state.priority_player = None
        self.state.priority_passes = []
        self.state.combat = CombatState()
        self._log(
            actor,
            "turn.ended",
            f"{actor} ended the turn.",
            {
                "stack_objects_exiled": removed_stack,
                "cards_exiled": [
                    self.state.cards[object_id].ref
                    for object_id in exiled_cards
                ],
                "reason": reason,
            },
            importance=3,
            changed_objects=exiled_cards,
        )
        self.state.phase_index = TURN_STEPS.index(
            ("ending", "cleanup")
        )
        self._enter_step()

    def _grant_priority(self, seat: str | None) -> None:
        if self._stabilize():
            return
        if not self.active_seats:
            return
        cleanup_frame = self._active_cleanup_frame()
        if (
            cleanup_frame is not None
            and not cleanup_frame.get(
                "delayed_triggers_queued",
                False,
            )
        ):
            cleanup_frame["delayed_triggers_queued"] = True
            delayed_ids = {
                str(value)
                for value in cleanup_frame.get(
                    "delayed_trigger_ids",
                    [],
                )
            }
            delayed = [
                trigger
                for trigger in self.state.delayed_triggers
                if trigger.trigger_id in delayed_ids
            ]
            if delayed:
                self._start_trigger_batch(
                    delayed,
                    after="grant_priority",
                )
                return
        if seat not in self.active_seats:
            seat = self._next_active_after(seat or self.state.active_player or self.active_seats[0])
        self.state.priority_player = seat
        self.state.priority_passes = []
        self.state.priority_epoch += 1
        if cleanup_frame is not None:
            cleanup_frame["priority_granted"] = True

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
            if response.get("confirm_concede") is not True:
                raise GameRuleError(
                    "Concession requires explicit confirmation"
                )
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
            created_stack_change_epoch=self._yield_change_epoch("stack"),
            created_public_change_epoch=self._yield_change_epoch("public"),
            created_draw_epoch=self._yield_change_epoch("draw", seat),
            created_action_change_epoch=self._yield_change_epoch(
                "action",
                seat,
            ),
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
            if action.get("id") in {"pass", "concede"} or action.get(
                "id"
            ) in ordinary_mana_ids:
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
        if (
            policy.created_stack_change_epoch
            != self._yield_change_epoch("stack")
        ):
            return "stack"
        if (
            policy.created_draw_epoch
            != self._yield_change_epoch("draw", seat)
        ):
            return "draw"
        if (
            policy.created_action_change_epoch
            != self._yield_change_epoch("action", seat)
        ):
            return "action_change"
        if (
            policy.created_public_change_epoch
            != self._yield_change_epoch("public")
        ):
            return "public_change"
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
            if action.get("id") not in {"pass", "concede"}
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
            if (
                self.state.priority_player is None
                and self._active_cleanup_frame() is not None
            ):
                self._grant_priority(self.state.active_player)
                continue
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
                    and not self._manual_active_main_phase_window(seat)
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

    def _manual_active_main_phase_window(self, seat: str) -> bool:
        """Keep browser play under the active player's explicit control.

        Simulation providers can retain empty-window auto-passing. Interactive
        games opt in so an empty stack never carries the active player through
        either main phase without an explicit pass.
        """

        return bool(
            self.state.config.manual_active_main_phase
            and seat == self.state.active_player
            and not self.state.stack
            and (self.state.phase, self.state.step)
            in {
                ("precombat_main", "main"),
                ("postcombat_main", "main"),
            }
        )

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
            if (
                key == "player"
                and expected in {"controller", "$controller"}
            ):
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

    def _delayed_trigger_stack_item(
        self,
        trigger: DelayedTrigger,
    ) -> StackItem:
        """Materialize a delayed ability without choosing its stack order.

        Step boundaries that combine delayed and permanent-based triggers need
        one common ``StackItem`` representation before APNAP/controller
        ordering.  Legacy delayed-only paths still call
        :meth:`_queue_delayed_trigger`, which appends the returned item
        immediately.
        """
        template = trigger.stack_template
        ref = self._next_ref("S")
        return StackItem(
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
            context={
                **copy.deepcopy(dict(template.get("context") or {})),
                "delayed_trigger_ref": trigger.ref,
            },
        )

    def _queue_delayed_trigger(self, trigger_id: str) -> None:
        trigger = next(t for t in self.state.delayed_triggers if t.trigger_id == trigger_id)
        item = self._delayed_trigger_stack_item(trigger)
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

    @staticmethod
    def _compiled_mana_restriction(restriction: str) -> str | None:
        lower = restriction.casefold()
        if (
            "spend this mana only to cast artifact spells or activate "
            "abilities of artifacts"
            in lower
        ):
            return "artifact_spell_or_ability"
        if "this mana can't be spent to cast nonartifact spells" in lower:
            return "nonartifact_spell_prohibited"
        if (
            "spend this mana only to cast a legendary spell"
            in lower
            and "that spell can't be countered" in lower
        ):
            return "legendary_spell_uncounterable"
        return None

    @staticmethod
    def _mana_restriction_allows(
        restriction: str,
        spend_context: str | None,
    ) -> bool:
        is_spell = bool(spend_context and "spell" in spend_context)
        is_artifact = bool(
            spend_context and spend_context.startswith("artifact")
        )
        is_legendary = bool(
            spend_context and "legendary" in spend_context
        )
        if restriction == "artifact_spell_or_ability":
            return (
                (is_spell and is_artifact)
                or spend_context == "artifact_ability"
            )
        if restriction == "nonartifact_spell_prohibited":
            return not (is_spell and not is_artifact)
        if restriction == "legendary_spell_uncounterable":
            return is_spell and is_legendary
        return False

    @staticmethod
    def _mana_mode_has_compiled_activation_condition(
        restriction: str,
    ) -> bool:
        return bool(
            re.search(
                r"activate only if you control "
                r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten) "
                r"or more (?:artifacts?|creatures?|lands?)",
                restriction.casefold(),
            )
        )

    def _spell_mana_spend_context(self, type_line: str) -> str:
        types, _, supertypes = self._type_parts(type_line)
        artifact = "artifact" in types
        legendary = "legendary" in supertypes
        if artifact and legendary:
            return "artifact_legendary_spell"
        if artifact:
            return "artifact_spell"
        if legendary:
            return "legendary_spell"
        return "nonartifact_spell"

    def _restricted_mana(self, seat: str) -> dict[str, dict[str, int]]:
        raw = self.state.players[seat].stats.setdefault(
            "restricted_mana",
            {},
        )
        return {
            str(key): normalize_mana_bundle(value)
            for key, value in dict(raw).items()
        }

    def _store_restricted_mana(
        self,
        seat: str,
        values: Mapping[str, Mapping[str, int]],
    ) -> None:
        compact = {
            key: {
                color: amount
                for color, amount in normalize_mana_bundle(bundle).items()
                if amount
            }
            for key, bundle in values.items()
            if sum(normalize_mana_bundle(bundle).values())
        }
        if compact:
            self.state.players[seat].stats["restricted_mana"] = compact
        else:
            self.state.players[seat].stats.pop("restricted_mana", None)

    def _add_restricted_mana(
        self,
        seat: str,
        restriction: str,
        bundle: Mapping[str, int],
    ) -> None:
        values = self._restricted_mana(seat)
        current = values.setdefault(
            restriction,
            normalize_mana_bundle(None),
        )
        for color, amount in normalize_mana_bundle(bundle).items():
            current[color] += amount
        self._store_restricted_mana(seat, values)

    def _spendable_mana_pool(
        self,
        seat: str,
        spend_context: str | None,
    ) -> dict[str, int]:
        pool = normalize_mana_bundle(self.state.players[seat].mana_pool)
        for restriction, bundle in self._restricted_mana(seat).items():
            if self._mana_restriction_allows(restriction, spend_context):
                continue
            for color, amount in bundle.items():
                pool[color] = max(0, pool[color] - amount)
        return pool

    def _apply_mana_spend(
        self,
        seat: str,
        spent: Mapping[str, int],
        spend_context: str | None,
    ) -> None:
        pool = normalize_mana_bundle(self.state.players[seat].mana_pool)
        restricted = self._restricted_mana(seat)
        for color, raw_amount in normalize_mana_bundle(spent).items():
            remaining = raw_amount
            for restriction in sorted(restricted):
                if not self._mana_restriction_allows(
                    restriction,
                    spend_context,
                ):
                    continue
                restricted_amount = restricted[restriction][color]
                use = min(remaining, restricted_amount)
                restricted[restriction][color] -= use
                if (
                    use
                    and restriction
                    == "legendary_spell_uncounterable"
                ):
                    self.state.players[seat].stats[
                        "next_spell_uncounterable"
                    ] = True
                remaining -= use
                if not remaining:
                    break
            pool[color] -= raw_amount
            if pool[color] < 0:
                raise GameRuleError(
                    "Mana payment exceeded the authoritative pool"
                )
        self.state.players[seat].mana_pool = pool
        self._store_restricted_mana(seat, restricted)

    def available_mana_sources(
        self,
        seat: str,
        *,
        spend_context: str | None = None,
    ) -> list[ManaSource]:
        identity = self._commander_identity(seat)
        sources: list[ManaSource] = []
        for object_id in self.state.players[seat].zones["battlefield"]:
            card = self.state.cards[object_id]
            if card.controller != seat or card.tapped or card.phased_out:
                continue
            data = self._effective_card_data(card)
            card_types, _, _ = self._type_parts(
                str(data.get("type_line") or "")
            )
            if (
                "creature" in card_types
                and self._is_summoning_sick(card)
                and "Haste" not in data.get("keywords", [])
            ):
                continue
            granted_token_mana = bool(
                card.is_token
                and "creature" in card_types
                and self._controller_has_oracle_text(
                    seat,
                    'creature tokens you control have "{t}: add one '
                    'mana of any color."',
                )
            )
            if granted_token_mana:
                modes = tuple(
                    ManaMode(
                        {
                            **normalize_mana_bundle(None),
                            color: 1,
                        }
                    )
                    for color in "WUBRG"
                )
                sources.append(
                    ManaSource(
                        object_id,
                        card.ref,
                        self.display_name(object_id),
                        modes,
                    )
                )
                continue
            record = self.card_record(card)
            if not record:
                compiled_modes = self._recordless_mana_modes(seat, card)
                if compiled_modes:
                    sources.append(
                        ManaSource(
                            object_id,
                            card.ref,
                            self.display_name(object_id),
                            tuple(compiled_modes),
                        )
                    )
                continue
            mana_abilities = [
                ability
                for ability in self._activated_abilities(card)
                if ability.mana_ability and card.zone in ability.zones
            ]
            if (
                not mana_abilities
                and not record.is_land
                and "creature tokens you control have"
                in record.oracle_text.casefold()
            ):
                continue
            if mana_abilities and not any(
                self._activation_condition_status(
                    seat,
                    ability,
                    card,
                )[0]
                == "payable"
                for ability in mana_abilities
            ):
                # A source whose only Oracle mana abilities have an unmet or
                # unresolved activation condition must not make dependent
                # spells appear payable.
                continue
            modes = extract_mana_modes(record, identity)
            compiled_modes: list[ManaMode] = []
            for mode in modes:
                restriction = self._compiled_mana_restriction(
                    mode.restriction
                )
                if restriction is None:
                    if self._mana_mode_has_compiled_activation_condition(
                        mode.restriction
                    ):
                        compiled_modes.append(
                            ManaMode(
                                mode.bundle,
                                conditional=False,
                                restriction=mode.restriction,
                                side_effects=mode.side_effects,
                                requires_choice=mode.requires_choice,
                            )
                        )
                    else:
                        compiled_modes.append(mode)
                    continue
                if self._mana_restriction_allows(
                    restriction,
                    spend_context,
                ):
                    compiled_modes.append(
                        ManaMode(
                            mode.bundle,
                            conditional=False,
                            restriction=mode.restriction,
                            side_effects=mode.side_effects,
                            requires_choice=mode.requires_choice,
                        )
                    )
            modes = tuple(compiled_modes)
            if modes:
                sources.append(ManaSource(object_id, card.ref, self.display_name(object_id), modes))
        return sources

    def _activate_mana_plan(
        self,
        seat: str,
        activations: Sequence[Mapping[str, Any]],
        *,
        spend_context: str | None = None,
    ) -> None:
        for activation in activations:
            card = self._resolve_object(seat, str(activation["source"]), zones={"battlefield"}, controlled_only=True)
            if card.tapped:
                raise GameRuleError(f"{card.ref} is already tapped")
            bundle = normalize_mana_bundle(activation.get("bundle"))
            record = self.card_record(card)
            data = self._effective_card_data(card)
            card_types, _, _ = self._type_parts(
                str(data.get("type_line") or "")
            )
            if (
                "creature" in card_types
                and self._is_summoning_sick(card)
                and "Haste" not in data.get("keywords", [])
            ):
                raise GameRuleError(f"{card.ref} is summoning sick")
            granted_token_mana = bool(
                card.is_token
                and "creature" in card_types
                and self._controller_has_oracle_text(
                    seat,
                    'creature tokens you control have "{t}: add one '
                    'mana of any color."',
                )
            )
            if granted_token_mana:
                modes = tuple(
                    ManaMode(
                        {
                            **normalize_mana_bundle(None),
                            color: 1,
                        }
                    )
                    for color in "WUBRG"
                )
            else:
                record = self.card_record(card)
                if not record:
                    modes = tuple(
                        self._recordless_mana_modes(seat, card)
                    )
                    if not modes:
                        raise GameRuleError(
                            f"{card.ref} has no compiled mana mode"
                        )
                else:
                    mana_abilities = [
                        ability
                        for ability in self._activated_abilities(card)
                        if ability.mana_ability
                        and card.zone in ability.zones
                    ]
                    if (
                        not mana_abilities
                        and not record.is_land
                        and "creature tokens you control have"
                        in record.oracle_text.casefold()
                    ):
                        raise GameRuleError(
                            f"{card.ref} does not itself have that mana ability"
                        )
                    modes = extract_mana_modes(
                        record,
                        self._commander_identity(seat),
                    )
            matching = [mode for mode in modes if normalize_mana_bundle(mode.bundle) == bundle]
            if not matching:
                raise GameRuleError(f"Declared output is not a recognized mana mode of {card.printed_name}")
            mana_abilities = [
                ability
                for ability in self._activated_abilities(card)
                if ability.mana_ability and card.zone in ability.zones
            ]
            if mana_abilities and not any(
                self._activation_condition_status(
                    seat,
                    ability,
                    card,
                )[0]
                == "payable"
                for ability in mana_abilities
            ):
                raise GameRuleError(
                    f"{card.printed_name}'s mana ability has an unmet or unresolved activation condition"
                )
            mode = matching[0]
            compiled_restriction = self._compiled_mana_restriction(
                mode.restriction
            )
            if mode.requires_choice:
                raise GameRuleError(
                    f"{card.printed_name}'s selected mana mode has a nonmana choice/cost; activate that Oracle ability explicitly."
                )
            if (
                mode.conditional
                and self.state.config.strict_mana
                and not (
                    compiled_restriction
                    and self._mana_restriction_allows(
                        compiled_restriction,
                        spend_context,
                    )
                )
                and not self._mana_mode_has_compiled_activation_condition(
                    mode.restriction
                )
            ):
                raise GameRuleError(
                    f"{card.printed_name}'s selected mana mode is conditional/restricted and has no compiled validator."
                )
            if (
                mode.conditional
                and not activation.get("allow_conditional")
                and not (
                    compiled_restriction
                    and self._mana_restriction_allows(
                        compiled_restriction,
                        spend_context,
                    )
                )
                and not self._mana_mode_has_compiled_activation_condition(
                    mode.restriction
                )
            ):
                raise GameRuleError(f"{card.printed_name}'s selected mana mode requires an explicit condition")
            # The selected authoritative mode, not the submitted mana-plan
            # payload, determines all costs and side effects.
            side_effects = tuple(mode.side_effects)
            cost_effects = tuple(
                effect
                for effect in side_effects
                if effect.get("op") == "sacrifice_source"
            )
            result_effects = tuple(
                effect
                for effect in side_effects
                if effect.get("op") != "sacrifice_source"
            )
            # Tap and sacrifice are paid before the mana ability resolves.
            # They are applied together without an intervening priority window.
            card.tapped = True
            self._apply_mana_mode_side_effects(
                seat,
                cost_effects,
                source=card,
            )
            for color, amount in bundle.items():
                self.state.players[seat].mana_pool[color] += amount
            if compiled_restriction:
                self._add_restricted_mana(
                    seat,
                    compiled_restriction,
                    bundle,
                )
            self._apply_mana_mode_side_effects(
                seat,
                result_effects,
                source=card,
            )
            self._log(seat, "mana.produce", f"{seat} tapped {card.ref} for { {k:v for k,v in bundle.items() if v} }.", {"source": card.ref, "bundle": {k:v for k,v in bundle.items() if v}}, importance=0, changed_objects=[card.object_id], changed_players=[seat])

    def _apply_mana_mode_side_effects(
        self,
        seat: str,
        effects: Iterable[Mapping[str, Any]],
        *,
        source: CardInstance | None = None,
    ) -> None:
        """Apply compiled effects coupled to one selected mana mode."""

        for effect_index, effect in enumerate(effects):
            if effect.get("op") == "damage_self":
                amount = int(effect.get("amount", 1))
                if amount < 0:
                    raise GameRuleError("Damage cannot be negative")
                if amount == 0:
                    continue
                try:
                    proposal = damage_proposal(
                        self,
                        proposal_id=(
                            f"damage.mana:{self.state.revision}:"
                            f"{self.state.event_sequence + 1}:"
                            f"{effect_index}"
                        ),
                        actor=seat,
                        source_ref=(source.ref if source is not None else None),
                        target=seat,
                        amount=amount,
                        combat=False,
                        reason="mana ability damage",
                    )
                    resolve_damage_batch(self, (proposal,))
                except ReplacementChoiceRequired as exc:
                    raise GameRuleError(
                        "Damage replacement choices during mana ability "
                        "resolution are not yet resumable"
                    ) from exc
                except DamageError as exc:
                    raise GameRuleError(str(exc)) from exc
            elif effect.get("op") == "pay_life":
                amount = int(effect.get("amount", 1))
                if self.state.players[seat].life < amount:
                    raise GameRuleError(
                        "Cannot pay more life than the player has"
                    )
                self.state.players[seat].life -= amount
            elif effect.get("op") == "sacrifice_source":
                if (
                    source is None
                    or source.controller != seat
                    or source.zone != "battlefield"
                ):
                    raise GameRuleError(
                        "The mana source cannot be sacrificed"
                    )
                self.move_card(
                    source.object_id,
                    "graveyard",
                    reason="mana ability cost",
                    semantic_events=True,
                )

    def _pay_for_cost(
        self,
        seat: str,
        requirements: dict[str, int],
        response: Mapping[str, Any],
        *,
        exclude_sources: set[str] | None = None,
        spend_context: str | None = None,
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        activations: list[dict[str, Any]] = []
        pay_mode = response.get("pay", "auto")
        if pay_mode == "auto":
            plan = auto_plan_payment(
                requirements,
                [
                    source
                    for source in self.available_mana_sources(
                        seat,
                        spend_context=spend_context,
                    )
                    if source.object_id not in (exclude_sources or set())
                ],
                allow_conditional=(
                    bool(response.get("allow_conditional_mana", False))
                    and not self.state.config.strict_mana
                ),
                reserve=normalize_mana_bundle(response.get("reserve")),
                starting_pool=self._spendable_mana_pool(
                    seat,
                    spend_context,
                ),
            )
            activations = plan.activations
            self._activate_mana_plan(
                seat,
                activations,
                spend_context=spend_context,
            )
            payment = plan.payment
        else:
            activations = [dict(item) for item in response.get("mana") or []]
            self._activate_mana_plan(
                seat,
                activations,
                spend_context=spend_context,
            )
            payment = normalize_mana_bundle(response.get("payment"))
        try:
            _, spent = pay_mana_from_pool(
                self._spendable_mana_pool(seat, spend_context),
                requirements,
                payment=payment,
            )
        except ValueError as exc:
            raise GameRuleError(str(exc)) from exc
        self._apply_mana_spend(
            seat,
            spent,
            spend_context,
        )
        return spent, activations

    def _check_priority(self, seat: str) -> None:
        if self.state.priority_player != seat:
            raise GameRuleError(f"{seat} does not have priority")

    def _is_main_phase(self) -> bool:
        """Return whether the scheduler is at either CR 505 main phase."""

        return (self.state.phase, self.state.step) in {
            ("precombat_main", "main"),
            ("postcombat_main", "main"),
        }

    def _sorcery_timing(self, seat: str) -> None:
        if seat != self.state.active_player:
            raise GameRuleError("Sorcery-speed action requires the active player")
        if not self._is_main_phase():
            raise GameRuleError("Sorcery-speed action requires a main phase")
        if self.state.stack:
            raise GameRuleError("Sorcery-speed action requires an empty stack")

    def _controller_has_oracle_text(
        self,
        seat: str,
        text: str,
    ) -> bool:
        needle = text.casefold()
        return any(
            permanent.controller == seat
            and not permanent.phased_out
            and needle
            in str(
                self._effective_card_data(permanent).get("oracle_text")
                or ""
            ).casefold()
            for permanent in (
                self.state.cards[object_id]
                for object_id in self.state.players[seat].zones[
                    "battlefield"
                ]
            )
        )

    def _lands_enter_untapped_for(self, seat: str) -> bool:
        return self._controller_has_oracle_text(
            seat,
            "lands you control enter untapped",
        )

    def _temporary_play_permission(
        self,
        seat: str,
        card: CardInstance,
    ) -> Mapping[str, Any] | None:
        permission = card.annotations.get("temporary_play_permission")
        if not isinstance(permission, Mapping):
            return None
        if (
            str(permission.get("player") or "") != seat
            or int(permission.get("turn_sequence", -1))
            != self.state.turn_sequence
            or str(permission.get("zone") or "") != card.zone
        ):
            return None
        return permission

    def _compiled_land_play_permission(
        self,
        seat: str,
        card: CardInstance,
    ) -> bool:
        permission = self._temporary_play_permission(seat, card)
        if permission is not None and bool(
            permission.get("allow_land", True)
        ):
            return True
        if card.owner != seat:
            return False
        if card.zone == "hand":
            return True
        return bool(
            card.zone == "graveyard"
            and self._controller_has_oracle_text(
                seat,
                "you may play lands from your graveyard",
            )
        )

    def _land_enters_tapped(
        self,
        seat: str | CardRecord,
        record: CardRecord | Mapping[str, Any],
        choices: Mapping[str, Any] | None = None,
        *,
        face: Mapping[str, Any] | None = None,
    ) -> bool:
        # Preserve the 0.2 internal probe signature used by downstream rules
        # tests while requiring a seat for contextual conditions in live play.
        if isinstance(seat, CardRecord):
            choices = record if isinstance(record, Mapping) else choices
            record = seat
            seat = self.state.active_player or self.seats[0]
        choices = choices or {}
        oracle = str(
            face.get("oracle_text") if face is not None else record.oracle_text
        ).casefold()
        display_name = str(
            face.get("name") if face is not None else record.name
        )
        if self._lands_enter_untapped_for(str(seat)):
            return False
        opponents = max(0, len(self.active_seats) - 1)
        if "enters tapped unless you have two or more opponents" in oracle:
            return opponents < 2
        optional_life = re.search(
            r"you may pay (?P<life>\d+) life\. if you don't, it enters tapped",
            oracle,
        )
        if optional_life:
            amount = int(optional_life.group("life"))
            if choices.get("pay_life"):
                if self.state.players[str(seat)].life < amount:
                    raise GameRuleError("Cannot pay more life than the player has")
                return False
            return True
        controlled_type = re.search(
            r"enters (?:the battlefield )?tapped unless you control "
            r"(?P<types>[^.\n]+)",
            oracle,
        )
        if controlled_type:
            required_types = set(
                re.findall(
                    r"\b(plains|island|swamp|mountain|forest)\b",
                    controlled_type.group("types"),
                )
            )
            if not required_types:
                raise GameRuleError(
                    f"{display_name} has an entry condition the rules engine "
                    "has not compiled"
                )
            return not any(
                required_types.intersection(
                    str(
                        self._effective_card_data(oid).get("type_line") or ""
                    ).casefold().split()
                )
                for oid in self.state.players[seat].zones["battlefield"]
                if self.state.cards[oid].controller == seat
            )
        if re.search(r"\benters (?:the battlefield )?tapped\b", oracle) and "unless" not in oracle:
            return True
        if "enters tapped unless" in oracle:
            raise GameRuleError(
                f"{display_name} has an entry condition the rules engine has not compiled"
            )
        return False

    @staticmethod
    def _land_play_faces(record: CardRecord) -> list[dict[str, Any] | None]:
        """Return the faces a player may choose for an ordinary land play."""

        if record.layout == "modal_dfc" and record.faces:
            return [
                dict(face)
                for face in record.faces
                if "land" in str(face.get("type_line") or "").casefold()
            ]
        if record.faces:
            front = dict(record.faces[0])
            if "land" in str(front.get("type_line") or "").casefold():
                return [front]
            return []
        return [None] if record.is_land else []

    @staticmethod
    def _land_entry_life_amount(
        record: CardRecord,
        face: Mapping[str, Any] | None = None,
    ) -> int:
        oracle = str(
            face.get("oracle_text") if face is not None else record.oracle_text
        ).casefold()
        match = re.search(
            r"you may pay (?P<life>\d+) life\. if you don't, it enters tapped",
            oracle,
        )
        return int(match.group("life")) if match else 0

    def _play_land(self, seat: str, response: Mapping[str, Any]) -> None:
        self._check_priority(seat)
        self._sorcery_timing(seat)
        player = self.state.players[seat]
        if player.land_plays_remaining <= 0:
            raise GameRuleError("No land plays remain")
        raw_from = str(response.get("from") or "hand")
        card = self._resolve_object(
            seat,
            str(response.get("card") or response.get("id")),
            zones={raw_from},
            owned_only=False,
        )
        record = self.card_record(card)
        if not record:
            raise GameRuleError(f"{card.printed_name} is not a land")
        requested_face = str(response.get("face") or "")
        legal_faces = self._land_play_faces(record)
        face = next(
            (
                candidate
                for candidate in legal_faces
                if candidate is not None
                and str(candidate.get("name") or "").casefold()
                == requested_face.casefold()
            ),
            None,
        )
        if requested_face and face is None:
            raise GameRuleError(
                f"{requested_face!r} is not a playable land face of {record.name}"
            )
        if not requested_face:
            if len(legal_faces) != 1:
                raise GameRuleError("Choose which land face to play")
            face = legal_faces[0]
        if not legal_faces:
            raise GameRuleError(f"{card.printed_name} is not a land")
        if not self._compiled_land_play_permission(seat, card):
            raise GameRuleError(
                f"Playing {card.printed_name} from {card.zone} is not "
                "authorized by a compiled zone permission."
            )
        if "enters_tapped" in response or "tapped" in response:
            raise GameRuleError("Land entry state is derived by the rules engine")
        tapped = self._land_enters_tapped(
            seat,
            record,
            response,
            face=face,
        )
        life_paid = (
            self._land_entry_life_amount(record, face)
            if response.get("pay_life")
            else 0
        )
        if response.get("pay_life"):
            if life_paid <= 0:
                raise GameRuleError(
                    "This land play does not authorize an entry life payment"
                )
            player.life -= life_paid
        card.annotations.pop("temporary_play_permission", None)
        self.move_card(
            card.object_id,
            "battlefield",
            controller=seat,
            tapped=tapped,
            enter_face=(str(face.get("name")) if face is not None else None),
            reason="land play",
            log=False,
            semantic_events=True,
        )
        player.land_plays_remaining -= 1
        self._log(
            seat,
            "land.play",
            f"{seat} played {card.ref} "
            f"{str(face.get('name')) if face is not None else card.printed_name}"
            f"{' tapped' if tapped else ''}.",
            {
                "object": card.ref,
                "tapped": tapped,
                "life_paid": life_paid,
                "face": str(face.get("name")) if face is not None else None,
            },
            importance=2,
            changed_objects=[card.object_id],
            changed_players=[seat],
        )
        # CR 117.5 and 704.3 require state-based actions and waiting triggers
        # to be handled before the active player receives priority after this
        # special action.  Without this boundary, an enters trigger created by
        # a land play could remain queued while the player cast another spell
        # or even advanced to the next step.
        self.state.priority_player = None
        self.state.priority_passes = []
        if self._stabilize():
            return
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
    def _front_face(record: CardRecord) -> dict[str, Any] | None:
        return dict(record.faces[0]) if record.faces else None

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

    def _compiled_zone_cast_permission(
        self,
        seat: str,
        card: CardInstance,
    ) -> bool:
        """Return whether a trusted static permission allows this zone cast."""

        permission = self._temporary_play_permission(seat, card)
        if permission is not None and bool(
            permission.get("allow_spell", True)
        ):
            return True
        if card.owner != seat:
            return False
        if card.zone in set(card.annotations.get("cast_from") or []):
            return True
        record = self.card_record(card)
        if record is None:
            return False
        oracle = record.oracle_text.casefold()
        if (
            card.zone == "graveyard"
            and "you may cast this card from your graveyard as long as "
            "you control a zombie"
            in oracle
        ):
            return any(
                candidate.controller == seat
                and not candidate.phased_out
                and "zombie"
                in self._type_parts(
                    str(
                        self._effective_card_data(candidate).get(
                            "type_line"
                        )
                        or ""
                    )
                )[1]
                for candidate in (
                    self.state.cards[object_id]
                    for object_id in self.state.players[seat].zones[
                        "battlefield"
                    ]
                )
            )
        return False

    def _cast(
        self,
        seat: str,
        response: Mapping[str, Any],
        *,
        authorized_from_zone: str | None = None,
        required_face: str | None = None,
        force_without_mana_cost: bool = False,
        ignore_priority: bool = False,
        ignore_timing: bool = False,
        during_resolution: bool = False,
    ) -> None:
        if not ignore_priority:
            self._check_priority(seat)
        if response.get("semantic_key") is not None:
            raise GameRuleError(
                "Pilots cannot select semantic program identifiers"
            )
        raw_from = response.get("from")
        zones = ({str(raw_from)} if isinstance(raw_from, str) else set(raw_from or ["hand", "command"]))
        card = self._resolve_object(
            seat,
            str(response.get("card") or response.get("id")),
            zones=zones,
            owned_only=False,
        )
        if card.zone in {"hand", "command"} and card.owner != seat:
            raise GameRuleError(
                "A player may cast only their own cards from this zone"
            )
        if card.zone == "command" and not card.is_commander:
            raise GameRuleError("Only this seat's commander cards may be cast from the command zone")
        internally_authorized_zone = (
            authorized_from_zone is not None
            and card.zone == authorized_from_zone
        )
        if (
            card.zone not in {"hand", "command"}
            and not internally_authorized_zone
        ):
            if not self._compiled_zone_cast_permission(seat, card):
                raise GameRuleError(
                    f"Casting {card.printed_name} from {card.zone} is not authorized by a compiled zone permission."
                )
        record = self.card_record(card)
        if not record:
            raise GameRuleError("Cannot cast a custom token")
        requested_face = (
            required_face
            if required_face is not None
            else response.get("face")
        )
        face = self._select_cast_face(record, requested_face)
        if (
            required_face is None
            and record.layout == "transform"
            and face is not None
            and record.faces
            and str(face.get("name") or "").casefold()
            != str(record.faces[0].get("name") or "").casefold()
        ):
            raise GameRuleError(
                "A transforming double-faced card's back face cannot be "
                "cast without a rules effect that specifically allows it"
            )
        if (
            required_face is not None
            and (
                face is None
                or str(face.get("name") or "").casefold()
                != required_face.casefold()
            )
        ):
            raise GameRuleError(
                "The rules effect no longer identifies that cast face"
            )
        type_line = str(face.get("type_line") or "") if face else record.type_line
        mana_cost = str(face.get("mana_cost") or "") if face else record.mana_cost
        if response.get("protector") is not None:
            raise GameRuleError(
                "A Battle protector is chosen as the Battle enters, not "
                "while its spell is cast"
            )
        is_instant = "instant" in type_line.casefold()
        has_flash = record.has_flash
        if (
            not ignore_timing
            and self.state.config.strict_timing
            and not (is_instant or has_flash)
        ):
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
            force_without_mana_cost=force_without_mana_cost,
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
            if selected_cost_option.get("cast_type_line"):
                type_line = str(
                    selected_cost_option["cast_type_line"]
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
            self._normalize_target_submission(response.get("targets")),
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
            spend_context=self._spell_mana_spend_context(type_line),
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
            tuple[
                CardInstance,
                str,
                str,
                str,
                dict[str, Any],
                list[str],
            ]
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
                    tuple[
                        CardInstance,
                        str,
                        str,
                        str,
                        dict[str, Any],
                        list[str],
                        str,
                    ]
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
                                paid_card.logical_object_id,
                                copy.deepcopy(
                                    self._effective_card_data(paid_card)
                                ),
                                [
                                    self.state.cards[
                                        attachment_id
                                    ].ref
                                    for attachment_id in paid_card.attachments
                                    if attachment_id in self.state.cards
                                ],
                                kind,
                            )
                        )
                for (
                    paid_card,
                    paid_origin,
                    paid_controller,
                    paid_logical_object_id,
                    paid_data,
                    paid_attachments,
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
                            paid_logical_object_id,
                            paid_data,
                            paid_attachments,
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
        card.annotations.pop("temporary_play_permission", None)
        self._remove_from_zone(card)
        self._reset_zone_change(card, "stack")
        card.zone = "stack"
        card.controller = seat
        card.active_face = str(face.get("name")) if face else None
        default_destination = "battlefield" if any(word in type_line.casefold() for word in ("artifact", "battle", "creature", "enchantment", "planeswalker")) else "graveyard"
        ref = self._next_ref("S")
        used_next_spell_improvise = bool(
            self.state.players[seat].stats.pop(
                "next_spell_improvise",
                False,
            )
        )
        used_next_spell_uncounterable = bool(
            self.state.players[seat].stats.pop(
                "next_spell_uncounterable",
                False,
            )
        )
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
                "cant_be_countered": used_next_spell_uncounterable,
                "granted_improvise": used_next_spell_improvise,
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
            prior_spells = (
                len(self._current_turn_history("spell_cast"))
                if self.state.turn_history is not None
                else sum(
                    event.code == "stack.cast"
                    and event.turn_sequence == self.state.turn_sequence
                    for event in self.state.events
                )
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
                        "card_object_id": item.card_object_id,
                        "semantic_key": item.semantic_key,
                        "targets": copy.deepcopy(item.targets),
                        "modes": copy.deepcopy(item.modes),
                        "x_value": item.x_value,
                        "default_destination": (
                            item.default_destination
                        ),
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
                "colors": [
                    str(value).upper()
                    for value in self._effective_card_data(card).get(
                        "colors", []
                    )
                ],
                "from": origin,
                "requirements": requirements,
                "payment": {k:v for k,v in spent.items() if v},
                "mana_sources": [
                    {
                        "source": a.get("source_ref") or a.get("source"),
                        "bundle": a.get("bundle"),
                    }
                    for a in activations
                ],
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
        cast_trigger_batch: list[StackItem] = []
        for (
            paid_card,
            paid_origin,
            paid_controller,
            paid_logical_object_id,
            paid_data,
            paid_attachments,
        ) in deferred_cost_events:
            self._dispatch_zone_change_events(
                paid_card,
                origin=paid_origin,
                destination="graveyard",
                origin_controller=paid_controller,
                origin_logical_object_id=paid_logical_object_id,
                origin_data=paid_data,
                origin_attachments=paid_attachments,
                departure_sources=deferred_cost_sources,
                departure_source_zones=deferred_cost_source_zones,
                reason=f"{card.printed_name} additional cost",
                trigger_batch=cast_trigger_batch,
            )
        cast_types, _, _ = self._type_parts(type_line)
        self._record_turn_history(
            "spell_cast",
            actor=seat,
            object_incarnation=card.logical_object_id,
            types=cast_types,
        )
        cast_context = {
            "card": card.ref,
            "controller": seat,
            "player": seat,
            "from": origin,
            "to": "stack",
            "types": sorted(cast_types),
            "stack": item.ref,
        }
        self._dispatch_semantic_event(
            "spell.cast",
            cast_context,
            trigger_batch=cast_trigger_batch,
        )
        if "artifact" in cast_types:
            self._dispatch_semantic_event(
                "artifact.cast",
                cast_context,
                trigger_batch=cast_trigger_batch,
            )
        self._enqueue_semantic_trigger_batch(cast_trigger_batch)
        self._queue_ward_triggers_for_targets(item)
        self.state.players[seat].yield_policy = YieldPolicy()
        if during_resolution:
            return
        # Casting is followed by a state-based-action check before any
        # player receives priority (CR 117.5, 704.3).  This is observable for
        # token and copy objects paid as additional costs.
        if self._stabilize():
            return
        self.state.priority_player = seat
        self.state.priority_passes = []

    def _activated_abilities(self, card: CardInstance) -> tuple[ActivatedAbility, ...]:
        data = self._effective_card_data(card)
        abilities = list(
            parse_activated_abilities(
            card_name=str(data.get("name") or card.printed_name),
            oracle_text=str(data.get("oracle_text") or ""),
            keywords=tuple(data.get("keywords") or ()),
            )
        )
        if card.printed_name == "Demonic Junker":
            crew_match = re.search(
                r"\bCrew\s+(?P<power>\d+)\b",
                str(data.get("oracle_text") or ""),
                re.IGNORECASE,
            )
            if crew_match is not None:
                threshold = int(crew_match.group("power"))
                abilities.append(
                    ActivatedAbility(
                        ability_id="crew",
                        line_index=10_000,
                        oracle_line=f"Crew {threshold}",
                        cost_text=f"Crew {threshold}",
                        effect_text=(
                            "This Vehicle becomes an artifact creature "
                            f"until end of turn. Crew {threshold}."
                        ),
                        zones=("battlefield",),
                        mana=normalize_mana_bundle(None),
                    )
                )
        if (
            card.oracle_id == "883a4180-9ede-4249-a4b8-3a29c998fb63"
            and card.active_face in {None, "Tithing Blade"}
            and card.zone == "battlefield"
        ):
            for ability_id, zone in (
                ("craft_battlefield", "battlefield"),
                ("craft_graveyard", "graveyard"),
            ):
                abilities.append(
                    ActivatedAbility(
                        ability_id=ability_id,
                        line_index=10_001 + len(abilities),
                        oracle_line=(
                            "{4}{B}, Exile this artifact, Exile a creature "
                            + (
                                "you control"
                                if zone == "battlefield"
                                else "card from your graveyard"
                            )
                            + ": Return this card transformed under its "
                            "owner's control. Activate only as a sorcery."
                        ),
                        cost_text="{4}{B}, Exile this artifact",
                        effect_text=(
                            "Return this card transformed under its owner's "
                            "control. Activate only as a sorcery."
                        ),
                        zones=("battlefield",),
                        mana={
                            **normalize_mana_bundle(None),
                            "GENERIC": 4,
                            "B": 1,
                        },
                        exile_source=True,
                        choices=(
                            CostChoice(
                                kind="exile",
                                count=1,
                                zone=zone,
                                card_type="creature",
                            ),
                        ),
                        sorcery_speed=True,
                    )
                )
        if card.printed_name == "Urza's Saga":
            if card.annotations.get("urzas_saga_chapter_1"):
                abilities.append(
                    ActivatedAbility(
                        ability_id="saga_mana",
                        line_index=10_010,
                        oracle_line="{T}: Add {C}.",
                        cost_text="{T}",
                        effect_text="Add {C}.",
                        zones=("battlefield",),
                        mana=normalize_mana_bundle(None),
                        tap_source=True,
                        mana_ability=True,
                    )
                )
            if card.annotations.get("urzas_saga_chapter_2"):
                abilities.append(
                    ActivatedAbility(
                        ability_id="saga_construct",
                        line_index=10_011,
                        oracle_line=(
                            "{2}, {T}: Create a 0/0 colorless Construct "
                            "artifact creature token with \"This token gets "
                            "+1/+1 for each artifact you control.\""
                        ),
                        cost_text="{2}, {T}",
                        effect_text=(
                            "Create a 0/0 colorless Construct artifact "
                            "creature token."
                        ),
                        zones=("battlefield",),
                        mana={
                            **normalize_mana_bundle(None),
                            "GENERIC": 2,
                        },
                        tap_source=True,
                    )
                )
        return tuple(abilities)

    def _queue_ward_triggers_for_targets(
        self,
        targeted_item: StackItem,
    ) -> list[str]:
        queued: list[str] = []
        seen: set[str] = set()
        for target_ref in targeted_item.targets:
            if target_ref in seen:
                continue
            seen.add(target_ref)
            try:
                permanent = self._resolve_object(
                    targeted_item.controller,
                    str(target_ref),
                    zones={"battlefield"},
                )
            except GameRuleError:
                continue
            if permanent.controller == targeted_item.controller:
                continue
            oracle = str(
                self._effective_card_data(permanent).get(
                    "oracle_text"
                )
                or ""
            )
            match = re.search(
                r"\bWard\s+\{(?P<generic>\d+)\}",
                oracle,
                re.IGNORECASE,
            )
            if match is None:
                continue
            ref = self._next_ref("S")
            ward = StackItem(
                stack_id=self._stable_runtime_id("stack", ref),
                ref=ref,
                kind="triggered_ability",
                controller=permanent.controller,
                label=f"{self.display_name(permanent.object_id)} — Ward",
                source_object_id=permanent.object_id,
                semantic_key="builtin:ward",
                visibility=list(self.seats),
                context={
                    "target_stack": targeted_item.ref,
                    "payer": targeted_item.controller,
                    "cost": {
                        "GENERIC": int(match.group("generic"))
                    },
                    "targeted_permanent": permanent.ref,
                },
            )
            self.state.stack.append(ward)
            queued.append(ward.ref)
            self._log(
                permanent.controller,
                "stack.trigger",
                f"Queued {ward.ref}: {ward.label}.",
                {
                    "stack": ward.ref,
                    "source": permanent.ref,
                    "target_stack": targeted_item.ref,
                    "payer": targeted_item.controller,
                },
                importance=2,
            )
        return queued

    @staticmethod
    def _semantic_key_for_ability(
        source: CardInstance,
        ability: ActivatedAbility,
    ) -> str:
        if (
            ability.effect_text.casefold().strip(" .")
            == "this creature deals 1 damage to any target"
        ):
            return (
                "dae4815e-9025-4993-ab46-52a3f1a7219e:"
                "granted:damage"
            )
        return f"{source.oracle_id}:ability:{ability.ability_id}"

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
                destination = {
                    "return": "hand",
                    "exile": "exile",
                }.get(choice.kind, "graveyard")
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
        effect_lower = ability.effect_text.casefold()
        if (
            "for each color among permanents you control, "
            "add one mana of that color"
            in effect_lower
        ):
            colors = {
                str(color).upper()
                for object_id in self.state.players[seat].zones[
                    "battlefield"
                ]
                if self.state.cards[object_id].controller == seat
                and not self.state.cards[object_id].phased_out
                for color in self._effective_card_data(object_id).get(
                    "colors", []
                )
                if str(color).upper() in "WUBRG"
            }
            return normalize_mana_bundle(
                {color: 1 for color in sorted(colors)}
            )
        if (
            "one mana of any color that a land an opponent controls "
            "could produce"
            in effect_lower
        ):
            legal_colors: set[str] = set()
            for opponent in self.active_seats:
                if opponent == seat:
                    continue
                for object_id in self.state.players[opponent].zones[
                    "battlefield"
                ]:
                    land = self.state.cards[object_id]
                    record = self.card_record(land)
                    if (
                        land.controller != opponent
                        or land.phased_out
                        or record is None
                        or not record.is_land
                    ):
                        continue
                    for mode in extract_mana_modes(
                        record,
                        self._commander_identity(opponent),
                    ):
                        legal_colors.update(
                            color
                            for color, amount in mode.bundle.items()
                            if color in "WUBRG" and amount
                        )
            raw_choice = str(response.get("mana_choice") or "").upper()
            declared = normalize_mana_bundle(response.get("mana_output"))
            if raw_choice in "WUBRG" and len(raw_choice) == 1:
                declared[raw_choice] += 1
            selected = [
                color
                for color in "WUBRG"
                if declared[color] == 1
            ]
            if (
                len(selected) != 1
                or sum(declared.values()) != 1
                or selected[0] not in legal_colors
            ):
                raise GameRuleError(
                    "Declared Fellwar/Orchard mana is not a color an "
                    "opponent's land could produce"
                )
            return declared
        legal_modes = self._mana_modes_for_ability(seat, source, ability)
        declared = normalize_mana_bundle(response.get("mana_output"))
        raw_choice = str(response.get("mana_choice") or "").upper()
        if raw_choice in "WUBRGC" and len(raw_choice) == 1:
            declared[raw_choice] += 1
        if legal_modes:
            if sum(declared.values()):
                if not any(
                    normalize_mana_bundle(mode.bundle) == declared
                    for mode in legal_modes
                ):
                    raise GameRuleError(
                        "Declared mana output is not a recognized Oracle mana mode"
                    )
                return declared
            if len(legal_modes) == 1:
                return normalize_mana_bundle(legal_modes[0].bundle)
            raise GameRuleError("Choose which mana this ability produces")

        output_text = ability.effect_text.split(".", 1)[0]
        output, complex_symbols = mana_cost_to_vector(output_text)
        bundle = {color: int(output.get(color, 0)) for color in "WUBRGC"}
        if output.get("GENERIC"):
            # Numeric symbols in an Add instruction represent colorless mana.
            bundle["C"] += int(output["GENERIC"])
        if sum(bundle.values()) and not complex_symbols:
            return normalize_mana_bundle(bundle)
        raw_choice = str(response.get("mana_choice") or "").upper()
        declared = normalize_mana_bundle(response.get("mana_output"))
        if raw_choice in "WUBRGC" and len(raw_choice) == 1:
            declared[raw_choice] += 1
        record = self.card_record(source)
        if not record:
            if (
                "one mana of any color"
                in ability.effect_text.casefold()
                and sum(declared.values()) == 1
                and declared["C"] == 0
            ):
                return declared
            raise GameRuleError("Custom mana ability needs compiled semantics")
        legal_modes = extract_mana_modes(record, self._commander_identity(seat))
        if not any(normalize_mana_bundle(mode.bundle) == declared for mode in legal_modes):
            raise GameRuleError("Declared mana output is not a recognized Oracle mana mode")
        return declared

    def _mana_modes_for_ability(
        self,
        seat: str,
        source: CardInstance,
        ability: ActivatedAbility,
    ) -> tuple[ManaMode, ...]:
        """Extract only the mana modes produced by one selected ability."""

        record = self.card_record(source)
        if record is None:
            effect = ability.effect_text.casefold()
            if "one mana of any type" in effect:
                colors = "WUBRGC"
            elif "one mana of any color" in effect:
                colors = "WUBRG"
            else:
                return ()
            return tuple(
                ManaMode(
                    {
                        **normalize_mana_bundle(None),
                        color: 1,
                    }
                )
                for color in colors
            )
        effect = ability.effect_text.casefold()
        if (
            "one mana of any color that a land an opponent controls "
            "could produce"
            in effect
        ):
            colors: set[str] = set()
            for opponent in self.active_seats:
                if opponent == seat:
                    continue
                for object_id in self.state.players[opponent].zones[
                    "battlefield"
                ]:
                    land = self.state.cards[object_id]
                    land_record = self.card_record(land)
                    if (
                        land.controller != opponent
                        or land.phased_out
                        or land_record is None
                    ):
                        continue
                    for mode in extract_mana_modes(
                        land_record,
                        self._commander_identity(opponent),
                    ):
                        colors.update(
                            color
                            for color, amount in mode.bundle.items()
                            if color in "WUBRG" and amount
                        )
            return tuple(
                ManaMode(
                    {
                        **normalize_mana_bundle(None),
                        color: 1,
                    }
                )
                for color in sorted(colors)
            )
        ability_record = replace(
            record,
            oracle_text=f"{{T}}: {ability.effect_text}",
            type_line="",
            produced_mana=(),
        )
        return extract_mana_modes(
            ability_record,
            self._commander_identity(seat),
        )

    def _recordless_mana_modes(
        self,
        seat: str,
        source: CardInstance,
    ) -> list[ManaMode]:
        """Return safely executable modes for a rules-created token.

        A token can have complete characteristics without a Scryfall-backed
        CardRecord.  Only a represented tap-mana ability whose remaining costs
        are fully compiled is eligible for automatic payment.
        """

        compiled_modes: list[ManaMode] = []
        for ability in self._activated_abilities(source):
            if (
                not ability.mana_ability
                or source.zone not in ability.zones
                or not ability.tap_source
                or not ability.compiled_cost
                or sum(ability.mana.values())
                or ability.choices
                or ability.untap_source
                or ability.discard_source
                or ability.exile_source
                or ability.life_payment
                or ability.energy_payment
                or ability.loyalty_delta is not None
                or self._activation_condition_status(
                    seat, ability, source
                )[0]
                != "payable"
            ):
                continue
            for mode in self._mana_modes_for_ability(
                seat, source, ability
            ):
                side_effects = list(mode.side_effects)
                if ability.sacrifice_source:
                    side_effects.append({"op": "sacrifice_source"})
                compiled_modes.append(
                    ManaMode(
                        mode.bundle,
                        conditional=mode.conditional,
                        restriction=mode.restriction,
                        side_effects=tuple(side_effects),
                        requires_choice=mode.requires_choice,
                    )
                )
        return compiled_modes

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
            if part.strip()
            in {
                "basic land",
                "plains",
                "island",
                "swamp",
                "mountain",
                "forest",
            }
        )

    def _fetch_land_options(self, seat: str, land_types: Sequence[str]) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        for object_id in self.state.players[seat].zones["library"]:
            card = self.state.cards[object_id]
            record = self.card_record(card)
            type_line = record.type_line.casefold() if record else ""
            matches_basic_land = (
                "basic land" in land_types
                and "basic" in self._type_parts(type_line)[2]
            )
            matches_land_type = any(
                land_type != "basic land" and land_type in type_line
                for land_type in land_types
            )
            if (
                record
                and record.is_land
                and (matches_basic_land or matches_land_type)
            ):
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

        candidate_semantic_key = self._semantic_key_for_ability(
            source,
            ability,
        )
        target_program = self.semantics.get(candidate_semantic_key)
        source_data = self._effective_card_data(source)
        source_card_types, source_subtypes, _ = self._type_parts(
            str(source_data.get("type_line") or "")
        )
        builtin_map = bool(
            source.is_token
            and "artifact" in source_card_types
            and "map" in source_subtypes
            and "target creature you control explores"
            in ability.effect_text.casefold()
        )
        target_schema_override = (
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "controller": "you",
                "creature": True,
                "count": 1,
            }
            if builtin_map
            else None
        )
        selected_modes = [str(value) for value in response.get("modes") or []]
        validated_targets, target_groups = self._validate_semantic_targets(
            seat,
            target_program,
            self._normalize_target_submission(response.get("targets")),
            modes=selected_modes,
            source_ref=source.ref,
            target_schema=target_schema_override,
        )
        target_snapshots = {
            ref: self._target_snapshot(ref) for ref in validated_targets
        }
        builtin_context = self._fetch_context(seat, ability, response)
        if (
            (ability.tap_source or ability.untap_source)
            and source.zone == "battlefield"
            and self._is_summoning_sick(source)
            and "Haste"
            not in self._effective_card_data(source).get(
                "keywords", []
            )
            and not self._may_activate_creature_as_haste(seat, source)
        ):
            raise GameRuleError(f"{source.ref} is summoning sick")
        if ability.tap_source:
            if source.zone != "battlefield":
                raise GameRuleError("Tap costs require a battlefield permanent")
            if source.tapped:
                raise GameRuleError(f"{source.ref} is tapped")
            source.tapped = True
        if ability.untap_source:
            if source.zone != "battlefield" or not source.tapped:
                raise GameRuleError("Untap-symbol cost requires a tapped battlefield permanent")
            source.tapped = False

        paid_objects = (
            self._pay_crew_cost(seat, source, ability, response)
            if self._crew_threshold(ability) is not None
            else self._pay_ability_choice_costs(
                seat, source, ability, response
            )
        )
        paid_object_snapshots = [
            self._target_snapshot(self.state.cards[object_id].ref)
            for object_id in paid_objects
        ]
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
        if ability.loyalty_delta is not None:
            current_loyalty = int(source.counters.get("loyalty", 0))
            if (
                ability.loyalty_delta < 0
                and current_loyalty < -ability.loyalty_delta
            ):
                raise GameRuleError(
                    "The planeswalker no longer has enough loyalty"
                )
            source.counters["loyalty"] = (
                current_loyalty + ability.loyalty_delta
            )
            source.annotations["loyalty_initialized"] = True
            source.annotations["loyalty_activated_turn_sequence"] = (
                self.state.turn_sequence
            )
            self._log(
                seat,
                "cost.loyalty",
                (
                    f"{seat} changed {source.ref}'s loyalty by "
                    f"{ability.loyalty_delta}."
                ),
                {
                    "source": source.ref,
                    "delta": ability.loyalty_delta,
                    "loyalty": source.counters["loyalty"],
                },
                importance=1,
                changed_objects=[source.object_id],
                changed_players=[seat],
            )

        requirements = reduced_requirements(
            ability,
            legendary_creatures=self._legendary_creatures_controlled(seat),
        )
        spent: dict[str, int] = {}
        activations: list[dict[str, Any]] = []
        if sum(requirements.values()):
            source_types = self._type_parts(
                str(
                    self._effective_card_data(source).get("type_line")
                    or ""
                )
            )[0]
            spent, activations = self._pay_for_cost(
                seat,
                requirements,
                response,
                spend_context=(
                    "artifact_ability"
                    if "artifact" in source_types
                    else "ability"
                ),
            )

        if "only once each turn" in ability.effect_text.casefold():
            activations_once = dict(
                source.annotations.get(
                    "once_per_turn_activations",
                    {},
                )
            )
            activations_once[ability.ability_id] = (
                self.state.turn_sequence
            )
            source.annotations[
                "once_per_turn_activations"
            ] = activations_once

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
            selected_mode = next(
                (
                    mode
                    for mode in self._mana_modes_for_ability(
                        seat,
                        source,
                        ability,
                    )
                    if normalize_mana_bundle(mode.bundle) == bundle
                ),
                None,
            )
            if selected_mode is not None:
                self._apply_mana_mode_side_effects(
                    seat, selected_mode.side_effects,
                    source=source,
                )
            compiled_restriction = self._compiled_mana_restriction(
                ability.effect_text
            )
            if compiled_restriction:
                self._add_restricted_mana(
                    seat,
                    compiled_restriction,
                    bundle,
                )
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
            if self._stabilize():
                return
            self.state.priority_player = seat
            self.state.priority_passes = []
            return

        source_types, source_subtypes, _ = self._type_parts(
            str(
                self._effective_card_data(source).get("type_line")
                or ""
            )
        )
        builtin_food = (
            source.is_token
            and "artifact" in source_types
            and "food" in source_subtypes
            and "you gain 3 life"
            in ability.effect_text.casefold()
        )
        semantic_key = str(
            "builtin:fetch_land"
            if builtin_context
            else (
                "builtin:food"
                if builtin_food
                else (
                    "builtin:map-explore"
                    if builtin_map
                    else candidate_semantic_key
                )
            )
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
                **(
                    {
                        "target_schema_override": copy.deepcopy(
                            target_schema_override
                        )
                    }
                    if target_schema_override is not None
                    else {}
                ),
                "cost_objects": [
                    self.state.cards[object_id].ref
                    for object_id in paid_objects
                ],
                "cost_object_snapshots": paid_object_snapshots,
                "cost_mana_value_plus_one": (
                    float(paid_object_snapshots[0].get("mana_value", 0))
                    + 1
                    if len(paid_object_snapshots) == 1
                    else None
                ),
            },
        )
        self.state.stack.append(item)
        self._queue_ward_triggers_for_targets(item)
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
        if self._stabilize():
            return
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

    @staticmethod
    def _crew_threshold(ability: ActivatedAbility) -> int | None:
        if ability.ability_id != "crew":
            return None
        match = re.search(
            r"\bCrew\s+(?P<power>\d+)\b",
            ability.effect_text,
            re.IGNORECASE,
        )
        return int(match.group("power")) if match is not None else None

    def _crew_candidates(
        self,
        seat: str,
        source: CardInstance,
    ) -> list[CardInstance]:
        return [
            self.state.cards[object_id]
            for object_id in self.state.players[seat].zones["battlefield"]
            if object_id != source.object_id
            and self.state.cards[object_id].controller == seat
            and not self.state.cards[object_id].phased_out
            and not self.state.cards[object_id].tapped
            and "creature"
            in self._type_parts(
                str(
                    self._effective_card_data(object_id).get("type_line")
                    or ""
                )
            )[0]
        ]

    def _pay_crew_cost(
        self,
        seat: str,
        source: CardInstance,
        ability: ActivatedAbility,
        response: Mapping[str, Any],
    ) -> list[str]:
        threshold = self._crew_threshold(ability)
        if threshold is None:
            raise GameRuleError("Crew threshold is not compiled")
        values = [
            str(value)
            for value in (
                response.get("cost_cards")
                or response.get("cost_objects")
                or []
            )
        ]
        if not values or len(values) != len(set(values)):
            raise GameRuleError(
                "Crew requires one or more distinct untapped creatures"
            )
        candidates = {
            candidate.ref: candidate
            for candidate in self._crew_candidates(seat, source)
        }
        if any(value not in candidates for value in values):
            raise GameRuleError(
                "Crew cost objects must be other untapped creatures you control"
            )
        selected = [candidates[value] for value in values]
        total_power = sum(
            max(0, self._numeric_stat(card.object_id, "power"))
            for card in selected
        )
        if total_power < threshold:
            raise GameRuleError(
                f"Crew {threshold} requires at least {threshold} total power"
            )
        for card in selected:
            card.tapped = True
        self._log(
            seat,
            "cost.crew",
            (
                f"{seat} tapped {len(selected)} creature(s) with "
                f"{total_power} total power to crew {source.ref}."
            ),
            {
                "source": source.ref,
                "threshold": threshold,
                "total_power": total_power,
                "objects": [card.ref for card in selected],
            },
            importance=1,
            changed_objects=[card.object_id for card in selected],
            changed_players=[seat],
        )
        return [card.object_id for card in selected]

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
            seat, ability, card
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
        if ability.loyalty_delta is not None:
            if self._loyalty_cost_modifier_present():
                return "unresolved", "unresolved_loyalty_cost_modification"
            if not (
                seat == self.state.active_player
                and not self.state.stack
                and (self.state.phase, self.state.step)
                in {
                    ("precombat_main", "main"),
                    ("postcombat_main", "main"),
                }
            ):
                return "unavailable", "loyalty_timing"
            if (
                card.annotations.get("loyalty_activated_turn_sequence")
                == self.state.turn_sequence
            ):
                return "unavailable", "loyalty_already_activated"
            if (
                ability.loyalty_delta < 0
                and int(card.counters.get("loyalty", 0))
                < -ability.loyalty_delta
            ):
                return "unpayable", "insufficient_loyalty"
        if ability.tap_source:
            if zone != "battlefield":
                return "unavailable", "tap_cost_wrong_zone"
            if card.tapped:
                return "unavailable", "source_tapped"
        if ability.untap_source and (
            zone != "battlefield"
            or not card.tapped
            or int(card.counters.get("stun", 0)) > 0
        ):
            return "unavailable", "untap_cost_unavailable"
        if (
            (ability.tap_source or ability.untap_source)
            and zone == "battlefield"
            and self._is_summoning_sick(card)
            and "Haste"
            not in self._effective_card_data(card).get("keywords", [])
            and not self._may_activate_creature_as_haste(seat, card)
        ):
            return "unavailable", "summoning_sickness"
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
        crew_threshold = self._crew_threshold(ability)
        if crew_threshold is not None and sum(
            max(0, self._numeric_stat(candidate.object_id, "power"))
            for candidate in self._crew_candidates(seat, card)
        ) < crew_threshold:
            return "unpayable", "insufficient_crew_power"
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

    def _loyalty_cost_modifier_present(self) -> bool:
        """Fail closed when a public effect modifies loyalty costs.

        Loyalty abilities can belong to any permanent, not only a
        planeswalker (CR 606.2-3).  The base loyalty-symbol cost is compiled,
        but the generic cost-modification ordering needed by CR 606.4-5 is not
        yet represented.  A visible modifier therefore makes the activation
        unresolved instead of executable at an incorrect cost.
        """

        for owner in self.active_seats:
            for object_id in self.state.players[owner].zones["battlefield"]:
                permanent = self.state.cards[object_id]
                if permanent.phased_out:
                    continue
                oracle_text = str(
                    self._effective_card_data(permanent).get("oracle_text")
                    or ""
                ).casefold()
                if (
                    "loyalty abilities" in oracle_text
                    and "cost" in oracle_text
                    and "activate" in oracle_text
                ):
                    return True
        return False

    def _may_activate_creature_as_haste(
        self,
        seat: str,
        card: CardInstance,
    ) -> bool:
        types, _, _ = self._type_parts(
            str(self._effective_card_data(card).get("type_line") or "")
        )
        return bool(
            "creature" in types
            and self._controller_has_oracle_text(
                seat,
                "you may activate abilities of creatures you control as "
                "though those creatures had haste",
            )
        )

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
        source: CardInstance | None = None,
    ) -> tuple[str, str | None]:
        """Evaluate the small compiled activation-condition grammar.

        Conditions outside this grammar are unresolved rather than guessed.
        This deliberately covers Metalcraft-style minimum-permanent checks
        without claiming general Oracle condition support.
        """

        effect = ability.effect_text.casefold()
        if (
            "activate only during your turn" in effect
            and self.state.active_player != seat
        ):
            return "unavailable", "only_during_your_turn"
        if "only once each turn" in effect:
            if source is None:
                return "unresolved", "activation_source_required"
            activations_once = dict(
                source.annotations.get(
                    "once_per_turn_activations",
                    {},
                )
            )
            if (
                activations_once.get(ability.ability_id)
                == self.state.turn_sequence
            ):
                return "unavailable", "already_activated_this_turn"
        if "activate only if" not in effect:
            return "payable", None
        if "created a token this turn" in effect:
            created = int(
                self.state.players[seat].stats.get(
                    "tokens_created_by_turn", {}
                ).get(str(self.state.turn_sequence), 0)
            )
            if created <= 0:
                return "unavailable", "requires_token_created_this_turn"
            return "payable", None
        if "activate only if it's not your turn" in effect:
            if self.state.active_player == seat:
                return "unavailable", "only_during_another_players_turn"
            return "payable", None
        if "activate only if you control an artifact" in effect:
            controls_artifact = any(
                self.state.cards[object_id].controller == seat
                and not self.state.cards[object_id].phased_out
                and "artifact"
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
                for object_id in self.state.players[seat].zones[
                    "battlefield"
                ]
            )
            if not controls_artifact:
                return "unavailable", "requires_controlled_artifact"
            return "payable", None
        if (
            "activate only if there are four or more card types among "
            "cards in your graveyard"
        ) in effect:
            card_types: set[str] = set()
            for object_id in self.state.players[seat].zones["graveyard"]:
                card_types.update(
                    self._type_parts(
                        str(
                            self._effective_card_data(object_id).get(
                                "type_line"
                            )
                            or ""
                        )
                    )[0]
                )
            if len(card_types) < 4:
                return "unavailable", "requires_delirium"
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
                    crew_threshold = self._crew_threshold(ability)
                    if crew_threshold is not None:
                        candidates = self._crew_candidates(
                            seat, card
                        )
                        hint["choose_cost"] = [
                            {
                                "k": "crew",
                                "z": "battlefield",
                                "minimum": 1,
                                "minimum_total_power": crew_threshold,
                                "legal_refs": [
                                    candidate.ref
                                    for candidate in candidates
                                ],
                            }
                        ]
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
        spend_context: str | None = None,
    ) -> bool:
        remaining = {key: int(requirements.get(key, 0)) for key in ("GENERIC", "W", "U", "B", "R", "G", "C")}
        pool = self._spendable_mana_pool(seat, spend_context)
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
                for source in self.available_mana_sources(
                    seat,
                    spend_context=spend_context,
                )
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
        face = self._front_face(record)
        mana_cost = (
            str(face.get("mana_cost") or "")
            if face is not None
            else record.mana_cost
        )
        commander_tax = (
            2 * self.state.players[seat].commander_casts.get(card.oracle_id, 0)
            if card.zone == "command" and card.is_commander
            else 0
        )
        try:
            return parsed_cost(mana_cost, commander_tax)
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
        *,
        spend_context: str | None = None,
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
                spend_context=spend_context,
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
        face = self._front_face(record)
        mana_cost = (
            str(face.get("mana_cost") or "")
            if face is not None
            else record.mana_cost
        )
        variants = [self._mana_vector(None)]
        has_x = False
        for symbol in parse_mana_symbols(mana_cost):
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
        spend_context = self._spell_mana_spend_context(
            str(
                self._effective_card_data(card).get("type_line")
                or ""
            )
        )
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
                    spend_context=spend_context,
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
        spend_context = self._spell_mana_spend_context(
            str(
                self._effective_card_data(card).get("type_line")
                or ""
            )
        )
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
                            spend_context=spend_context,
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
        force_without_mana_cost: bool = False,
    ) -> list[dict[str, Any]]:
        """Compile server-authoritative payable casting-cost alternatives.

        Semantic packs describe reusable cost families.  The returned options
        contain only costs that are currently payable and whose nonmana cost
        objects are currently available to this seat.
        """

        response = dict(response or {})
        x_value = response.get("x")
        temporary_permission = self._temporary_play_permission(seat, card)
        cast_without_mana = force_without_mana_cost or bool(
            temporary_permission
            and temporary_permission.get("without_mana_cost")
        )
        if cast_without_mana:
            if x_value is not None and int(x_value) != 0:
                return []
            printed_options = [
                {
                    "id": "without_mana_cost",
                    "kind": "alternate",
                    "label": "Cast without paying its mana cost",
                    "requirements": self._mana_vector({}),
                }
            ]
            has_x = False
        else:
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
        spend_context = self._spell_mana_spend_context(
            str(
                self._effective_card_data(card).get("type_line")
                or ""
            )
        )
        payment_mechanics = self._cost_payment_mechanics(record, schema)
        if (
            self.state.players[seat].stats.get("next_spell_improvise")
            and not any(
                str(value.get("kind") or "").casefold() == "improvise"
                for value in payment_mechanics
            )
        ):
            payment_mechanics.append({"kind": "improvise"})
        base_options: list[dict[str, Any]] = printed_options
        commander_tax = (
            2
            * self.state.players[seat].commander_casts.get(card.oracle_id, 0)
            if card.zone == "command" and card.is_commander
            else 0
        )
        for raw in (
            []
            if cast_without_mana
            else schema.get("alternate_costs", [])
        ):
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
            cast_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if "artifact" in cast_types:
                shuri_reductions = sum(
                    1
                    for object_id in self.state.players[seat].zones[
                        "battlefield"
                    ]
                    if self.state.cards[object_id].controller == seat
                    and not self.state.cards[object_id].phased_out
                    and self.state.cards[object_id].printed_name
                    == "Shuri, Wakandan Inventor"
                )
                if shuri_reductions:
                    applied = min(
                        int(option["requirements"]["GENERIC"]),
                        shuri_reductions,
                    )
                    option["requirements"]["GENERIC"] -= applied
                    option.setdefault("cost_reductions", []).append(
                        {
                            "kind": "artifact_spell_static",
                            "source": "Shuri, Wakandan Inventor",
                            "count": applied,
                        }
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
                        spend_context=spend_context,
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
                spend_context=spend_context,
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
        candidate_zones = unique_preserving_order([
            *player.zones["hand"],
            *player.zones["command"],
            *[
                object_id
                for zone in ("graveyard", "exile")
                for zone_owner in self.active_seats
                for object_id in self.state.players[zone_owner].zones[zone]
                if self._compiled_zone_cast_permission(
                    seat,
                    self.state.cards[object_id],
                )
            ],
        ])
        castable: list[str] = []
        cast_target_schemas: dict[str, dict[str, Any]] = {}
        cast_cost_options: dict[str, list[dict[str, Any]]] = {}
        unpayable_casts: list[dict[str, Any]] = []
        unresolved_casts: list[dict[str, Any]] = []
        for oid in candidate_zones:
            record = self.card_record(oid)
            front_face = self._front_face(record) if record else None
            front_type_line = (
                str(front_face.get("type_line") or "")
                if front_face is not None
                else record.type_line if record else ""
            )
            if not record or "land" in front_type_line.casefold():
                continue
            main_timing = (
                seat == self.state.active_player
                and not self.state.stack
                and self._is_main_phase()
            )
            program = self.semantics.get(
                f"{record.oracle_id}:spell:front"
            )
            timing_available = (
                "instant" in front_type_line.casefold()
                or record.has_flash
                or main_timing
            )
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
        land_options: list[tuple[str, dict[str, Any] | None]] = []
        if (
            seat == self.state.active_player
            and not self.state.stack
            and self._is_main_phase()
            and player.land_plays_remaining
        ):
            for oid in [
                    *player.zones["hand"],
                    *[
                        object_id
                        for zone in ("graveyard", "exile")
                        for zone_owner in self.active_seats
                        for object_id in self.state.players[
                            zone_owner
                        ].zones[zone]
                    ],
                ]:
                card = self.state.cards[oid]
                record = self.card_record(oid)
                faces = self._land_play_faces(record) if record else []
                if not faces or not self._compiled_land_play_permission(
                    seat,
                    card,
                ):
                    continue
                lands.append(card.ref)
                land_options.extend((card.ref, face) for face in faces)
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
                    self._semantic_key_for_ability(
                        source,
                        next(
                            ability
                            for ability in self._activated_abilities(
                                source
                            )
                            if ability.ability_id
                            == ability_hint["a"]
                        ),
                    )
                )
                if source
                else None
            )
            source_types: set[str] = set()
            source_subtypes: set[str] = set()
            selected_ability = None
            if source is not None:
                source_types, source_subtypes, _ = self._type_parts(
                    str(
                        self._effective_card_data(source).get(
                            "type_line"
                        )
                        or ""
                    )
                )
                selected_ability = next(
                    (
                        value
                        for value in self._activated_abilities(source)
                        if value.ability_id == ability_hint["a"]
                    ),
                    None,
                )
            builtin_target_schema = (
                {
                    "zones": ["battlefield"],
                    "categories": ["permanent"],
                    "controller": "you",
                    "creature": True,
                    "count": 1,
                }
                if (
                    source is not None
                    and source.is_token
                    and "artifact" in source_types
                    and "map" in source_subtypes
                    and selected_ability is not None
                    and "target creature you control explores"
                    in selected_ability.effect_text.casefold()
                )
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
            target_schema = (
                builtin_target_schema
                if builtin_target_schema is not None
                else (
                    program.target_schema
                    if program is not None
                    else None
                )
            )
            if target_schema is None:
                ability_target_status[action_id] = True
                return True
            public_schema = self._public_target_schema(
                seat,
                target_schema,
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
        actions: list[dict[str, Any]] = [
            {"id": "pass", "action": "pass", "label": "Pass priority"}
        ]
        faces_per_land = {
            ref: sum(1 for candidate_ref, _ in land_options if candidate_ref == ref)
            for ref in lands
        }
        for ref, face in land_options:
            card = next(
                value for value in self.state.cards.values() if value.ref == ref
            )
            record = self.card_record(card)
            face_name = str(face.get("name") or "") if face else ""
            display_name = face_name or (record.name if record else card.printed_name)
            action_id = f"play-land:{ref}"
            if faces_per_land.get(ref, 0) > 1:
                face_index = next(
                    index
                    for index, candidate in enumerate(record.faces)
                    if str(candidate.get("name") or "") == face_name
                )
                action_id += f":face-{face_index}"
            action = {
                "id": action_id,
                "action": "play_land",
                "kind": "play_land",
                "label": f"Play {display_name}",
                "card": ref,
                "from": card.zone,
            }
            if face_name:
                action["face"] = face_name
            life_amount = (
                self._land_entry_life_amount(record, face)
                if record
                else 0
            )
            if life_amount:
                action["choice_schema"] = {
                    "pay_life": {
                        "type": "boolean",
                        "label": (
                            f"Pay {life_amount} life to enter untapped"
                        ),
                        "default": False,
                        "life": life_amount,
                        "effect": "enters untapped",
                    }
                }
            actions.append(action)
        for ref in castable:
            card = next(
                value for value in self.state.cards.values() if value.ref == ref
            )
            record = self.card_record(card)
            face = self._front_face(record) if record else None
            cast_name = (
                str(face.get("name") or "")
                if face is not None
                else record.name if record else card.printed_name
            )
            cast_cost = (
                str(face.get("mana_cost") or "")
                if face is not None
                else record.mana_cost if record else ""
            )
            program = (
                self.semantics.get(f"{record.oracle_id}:spell:front")
                if record
                else None
            )
            action: dict[str, Any] = {
                "id": f"cast:{ref}",
                "action": "cast",
                "kind": "cast",
                "label": (
                    f"Cast {cast_name} — {cast_cost}"
                    if cast_cost
                    else f"Cast {cast_name}"
                ),
                "card": ref,
                "from": card.zone,
                "cost": cast_cost,
                "auto_pay": True,
            }
            if face is not None:
                action["face"] = cast_name
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
            source = next(
                value
                for value in self.state.cards.values()
                if value.ref == ability["s"]
            )
            selected_ability = next(
                (
                    candidate
                    for candidate in self._activated_abilities(source)
                    if candidate.ability_id == ability["a"]
                ),
                None,
            )
            if selected_ability is not None:
                action["label"] = (
                    f"{self.display_name(source.object_id)} — "
                    f"{selected_ability.effect_text}"
                )
                if selected_ability.mana_ability:
                    action["mana_ability"] = True
                    mana_modes = self._mana_modes_for_ability(
                        seat,
                        source,
                        selected_ability,
                    )
                    if len(mana_modes) > 1:
                        action["choice_schema"] = {
                            "mana_output": {
                                "type": "mana_bundle",
                                "label": "Mana to add",
                                "options": [
                                    {
                                        "value": {
                                            key: amount
                                            for key, amount in mode.bundle.items()
                                            if amount
                                        },
                                        "label": "Add "
                                        + "".join(
                                            f"{{{key}}}" * amount
                                            for key, amount in mode.bundle.items()
                                            if amount
                                        ),
                                    }
                                    for mode in mana_modes
                                ],
                            }
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
        actions.append(
            {
                "id": "concede",
                "action": "concede",
                "kind": "concede",
                "label": "Concede game",
                "choice_schema": {
                    "confirm_concede": {
                        "type": "boolean",
                        "label": (
                            "Concede and leave the remaining players in "
                            "the game"
                        ),
                        "legal_values": [True],
                        "default": True,
                        "required": True,
                    }
                },
            }
        )
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
        if field == "source_controller_subtype_count":
            subtype = str(condition.get("subtype") or "").casefold()
            if not subtype:
                raise GameRuleError(
                    "Subtype-count condition requires a subtype"
                )
            actual = sum(
                1
                for object_id in self.state.players[
                    source.controller
                ].zones["battlefield"]
                if self.state.cards[object_id].controller
                == source.controller
                and subtype
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[1]
            )
        elif field == "source_controller_type_count":
            card_type = str(condition.get("type") or "").casefold()
            if not card_type:
                raise GameRuleError(
                    "Type-count condition requires a card type"
                )
            actual = sum(
                1
                for object_id in self.state.players[
                    source.controller
                ].zones["battlefield"]
                if self.state.cards[object_id].controller
                == source.controller
                and card_type
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
            )
        elif (
            field
            == "source_controller_controls_highest_artifact_mana_value"
        ):
            controlled_values: list[float] = []
            all_values: list[float] = []
            for active_seat in self.active_seats:
                for object_id in self.state.players[
                    active_seat
                ].zones["battlefield"]:
                    permanent = self.state.cards[object_id]
                    if permanent.phased_out:
                        continue
                    data = self._effective_card_data(permanent)
                    types, _, _ = self._type_parts(
                        str(data.get("type_line") or "")
                    )
                    if "artifact" not in types:
                        continue
                    value = float(data.get("mana_value") or 0)
                    all_values.append(value)
                    if permanent.controller == source.controller:
                        controlled_values.append(value)
            actual = bool(
                controlled_values
                and max(controlled_values) == max(all_values)
            )
        elif field.startswith("source_annotation."):
            actual = source.annotations.get(
                field.removeprefix("source_annotation.")
            )
        elif field == "source_active_face":
            actual = source.active_face or (
                (
                    self.card_record(source).faces[0].get("name")
                    if self.card_record(source) is not None
                    and self.card_record(source).faces
                    else None
                )
            )
        else:
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
        if op == "contains_any":
            return bool(set(actual or []).intersection(expected or []))
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
        trigger_controller = (
            str(context.get("previous_controller"))
            if (
                self_event
                and context.get("previous_controller") is not None
                and event
                in {
                    "artifact.graveyard",
                    "creature.dies",
                    "permanent.graveyard",
                    "permanent.leave",
                }
            )
            else source.controller
        )
        if trigger_controller not in self.active_seats:
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
        if event == "creature.dies" and not self_event:
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
                trigger_controller = (
                    str(context.get("previous_controller"))
                    if (
                        program.event.endswith(".self")
                        and str(context.get("card") or "")
                        == source.ref
                        and context.get("previous_controller") is not None
                        and event
                        in {
                            "artifact.graveyard",
                            "creature.dies",
                            "permanent.graveyard",
                            "permanent.leave",
                        }
                    )
                    else source.controller
                )
                ref = self._next_ref("S")
                item = StackItem(
                    stack_id=self._stable_runtime_id("stack", ref),
                    ref=ref,
                    kind="triggered_ability",
                    controller=trigger_controller,
                    label=program.label,
                    source_object_id=source.object_id,
                    semantic_key=program.key,
                    visibility=list(self.seats),
                    context={
                        "event": event,
                        **copy.deepcopy(dict(context)),
                        "source_logical_object_id": (
                            source.logical_object_id
                        ),
                        **(
                            {"trigger_target_selection_pending": True}
                            if program.target_schema
                            else {}
                        ),
                    },
                )
                if (
                    trigger_batch is not None
                    and "one_or_more_event_batch" in program.coverage
                    and any(
                        existing.semantic_key == item.semantic_key
                        and existing.source_object_id
                        == item.source_object_id
                        and existing.context.get("event") == event
                        for existing in trigger_batch
                    )
                ):
                    continue
                trigger_count = 1
                entering_types = {
                    str(value).casefold()
                    for value in context.get("types", [])
                }
                if (
                    event
                    in {
                        "permanent.enter",
                        "artifact.enter",
                        "creature.enter",
                        "land.enter",
                        "enchantment.enter",
                    }
                    and entering_types.intersection(
                        {"artifact", "creature"}
                    )
                    and source.zone == "battlefield"
                ):
                    trigger_count += sum(
                        1
                        for permanent_id in self.state.players[
                            item.controller
                        ].zones["battlefield"]
                        if self.state.cards[
                            permanent_id
                        ].controller
                        == item.controller
                        and not self.state.cards[
                            permanent_id
                        ].phased_out
                        and (
                            (
                                "if an artifact or creature entering causes "
                                "a triggered ability of a permanent you "
                                "control to trigger, that ability triggers "
                                "an additional time"
                            )
                            in str(
                                (
                                    self.card_record(
                                        self.state.cards[permanent_id]
                                    ).oracle_text
                                    if self.card_record(
                                        self.state.cards[permanent_id]
                                    )
                                    is not None
                                    else ""
                                )
                            ).casefold()
                        )
                    )
                source_types, source_subtypes, _ = self._type_parts(
                    str(
                        self._effective_card_data(source).get(
                            "type_line"
                        )
                        or ""
                    )
                )
                if (
                    "creature" in source_types
                    and source.printed_name != "Roaming Throne"
                ):
                    trigger_count += sum(
                        1
                        for permanent_id in self.state.players[
                            item.controller
                        ].zones["battlefield"]
                        if self.state.cards[
                            permanent_id
                        ].controller
                        == item.controller
                        and not self.state.cards[
                            permanent_id
                        ].phased_out
                        and self.state.cards[
                            permanent_id
                        ].printed_name
                        == "Roaming Throne"
                        and str(
                            self.state.cards[
                                permanent_id
                            ].annotations.get(
                                "chosen_creature_type", ""
                            )
                        ).casefold()
                        in source_subtypes
                    )
                triggered.append(item)
                for copy_index in range(1, trigger_count):
                    copy_ref = self._next_ref("S")
                    copied = StackItem.from_dict(item.to_dict())
                    copied.stack_id = self._stable_runtime_id(
                        "stack", copy_ref
                    )
                    copied.ref = copy_ref
                    copied.context = {
                        **copy.deepcopy(item.context),
                        "additional_trigger_copy": copy_index,
                    }
                    triggered.append(copied)
                if "consume_evoked_marker" in program.coverage:
                    source.annotations.pop("evoked", None)
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

        serialized = [
            item.to_dict()
            for item in items
            if item.controller in self.active_seats
        ]
        if not serialized:
            return

        # CR 603.3b groups every represented ability that triggered since the
        # previous priority window.  Event producers may discover those
        # abilities at different times (damage first, then deaths caused by
        # state-based actions), so merge them until stack placement starts.
        # A started batch is sealed: abilities triggered during its placement
        # belong to the rule's later repeat pass.
        if self.state.pending_trigger_batches:
            pending = self.state.pending_trigger_batches[-1]
            same_priority_window = int(
                pending.get("priority_epoch", self.state.priority_epoch)
            ) == int(self.state.priority_epoch)
            if (
                not pending.get("placement_started", False)
                and same_priority_window
            ):
                existing = [
                    dict(value)
                    for group in pending.get("groups", [])
                    for value in group.get("items", [])
                ]
                pending["apnap_order"] = self.apnap_order()
                pending["groups"] = self._semantic_trigger_groups(
                    [*existing, *serialized]
                )
                return

        groups = self._semantic_trigger_groups(serialized)
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
                "priority_epoch": self.state.priority_epoch,
                "placement_started": False,
            }
        )

    def _semantic_trigger_groups(
        self,
        values: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for controller in self.apnap_order():
            controlled = [
                copy.deepcopy(dict(value))
                for value in values
                if str(value.get("controller") or "") == controller
            ]
            if controlled:
                groups.append(
                    {
                        "controller": controller,
                        "items": controlled,
                    }
                )
        return groups

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
            if not batch.get("placement_started", False):
                waiting = [
                    dict(value)
                    for group in batch.get("groups", [])
                    for value in group.get("items", [])
                ]
                batch["apnap_order"] = self.apnap_order()
                batch["groups"] = self._semantic_trigger_groups(waiting)
                batch["placement_started"] = True
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
                ability_source = self.state.cards.get(
                    item.source_object_id or ""
                )
                source_data = (
                    self._effective_card_data(ability_source)
                    if ability_source is not None
                    else data
                )
                stack_source_types, _, _ = self._type_parts(
                    str(source_data.get("type_line") or "")
                )
                rows.append(
                    {
                        "ref": item.ref,
                        "zone": "stack",
                        "category": (
                            "spell"
                            if item.kind in {"spell", "spell_copy"}
                            else "ability"
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
                        "stack_source_types": stack_source_types,
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
        source_colors = self._source_colors_for_ref(source_ref)
        protected_seat = (
            str(row["ref"])
            if row.get("category") == "player"
            else str(row.get("controller") or "")
        )
        if (
            as_target
            and row.get("category") == "player"
            and protected_seat in self.state.players
            and self.state.players[protected_seat].stats.get(
                "protection_from_everything_until_next_turn"
            )
        ):
            return False
        if (
            as_target
            and protected_seat in self.state.players
            and protected_seat != controller
            and source_colors.intersection(
                {
                    str(value).upper()
                    for value in self.state.players[
                        protected_seat
                    ].stats.get("hexproof_from_colors_until_end", [])
                }
            )
        ):
            return False
        card = row.get("card")
        if (
            row.get("category") == "card"
            and isinstance(card, CardInstance)
            and not card.is_card_object
        ):
            # CR 111.6/707.10: tokens and noncard copies may briefly exist in
            # another zone before the next state check, but are never cards.
            return False
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
            if self._protection_colors(card).intersection(
                source_colors
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
        if (
            group.controller_seat is not None
            and str(row.get("controller")) != group.controller_seat
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
            elif group.predicate == "permanent_card":
                if not types.intersection(
                    {
                        "artifact",
                        "battle",
                        "creature",
                        "enchantment",
                        "land",
                        "planeswalker",
                    }
                ):
                    return False
            elif group.predicate == "damageable":
                if (
                    row["category"] != "player"
                    and not types.intersection(
                        {"battle", "creature", "planeswalker"}
                    )
                ):
                    return False
            elif group.predicate == "player_or_planeswalker":
                if (
                    row["category"] != "player"
                    and "planeswalker" not in types
                ):
                    return False
            elif group.predicate == "void_counter":
                if (
                    not isinstance(card, CardInstance)
                    or row.get("zone") != "exile"
                    or int(card.counters.get("void", 0)) <= 0
                ):
                    return False
            elif group.predicate == "artifact_source":
                if (
                    row.get("zone") != "stack"
                    or "artifact"
                    not in set(
                        row.get("stack_source_types") or ()
                    )
                ):
                    return False
            elif group.predicate == "triggered_ability":
                stack_item = row.get("stack_item")
                if (
                    not isinstance(stack_item, StackItem)
                    or stack_item.kind != "triggered_ability"
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
                "stack_id": item.stack_id,
                "category": (
                    "spell"
                    if item.kind in {"spell", "spell_copy"}
                    else "ability"
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
            "object_id": card.object_id,
            "zone_change_counter": card.zone_change_counter,
            "zone": card.zone,
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

    def _target_identity_matches_snapshot(
        self,
        ref: str,
        snapshot: Mapping[str, Any],
    ) -> bool:
        """Return whether ``ref`` is still the originally selected object."""

        stack_id = snapshot.get("stack_id")
        if stack_id is not None:
            return any(
                item.ref == ref and item.stack_id == stack_id
                for item in self.state.stack
            )
        object_id = snapshot.get("object_id")
        incarnation = snapshot.get("zone_change_counter")
        if object_id is None or incarnation is None:
            # Backward-compatible records predate explicit incarnations.
            return True
        card = self.state.cards.get(str(object_id))
        return bool(
            card is not None
            and card.ref == ref
            and card.zone_change_counter == int(incarnation)
        )

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

    def _target_plan_feasible(
        self,
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
                for left_group, right_group in plan.same_player_groups:
                    left = selected.get(left_group, [])
                    right = selected.get(right_group, [])
                    if not left or not right:
                        return False
                    if any(
                        self._target_snapshot(left_ref).get("controller")
                        != self._target_snapshot(right_ref).get(
                            "controller"
                        )
                        for left_ref in left
                        for right_ref in right
                    ):
                        return False
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
    def _normalize_target_submission(targets: Any) -> list[Any]:
        """Normalize flat refs or a typed group map for target validation."""

        if targets is None:
            return []
        if isinstance(targets, Mapping):
            normalized: list[dict[str, str]] = []
            for group_id, raw_refs in targets.items():
                if isinstance(raw_refs, str):
                    refs: Sequence[Any] = [raw_refs]
                elif isinstance(raw_refs, Sequence) and not isinstance(
                    raw_refs,
                    (str, bytes, bytearray),
                ):
                    refs = raw_refs
                else:
                    raise GameRuleError(
                        "Target group values must be a ref or an array of refs"
                    )
                for ref in refs:
                    if isinstance(ref, Mapping) or ref is None:
                        raise GameRuleError(
                            "Target group values must contain only refs"
                        )
                    normalized.append(
                        {
                            "group": str(group_id),
                            "ref": str(ref),
                        }
                    )
            return normalized
        if isinstance(targets, Sequence) and not isinstance(
            targets,
            (str, bytes, bytearray),
        ):
            return list(targets)
        raise GameRuleError(
            "Targets must be an array of refs or a group-to-refs object"
        )

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
            for left_group, right_group in plan.same_player_groups:
                left = grouped.get(left_group, [])
                right = grouped.get(right_group, [])
                if not left or not right:
                    raise GameRuleError(
                        "Related target groups must both contain a target"
                    )
                if any(
                    self._target_snapshot(left_ref).get("controller")
                    != self._target_snapshot(right_ref).get("controller")
                    for left_ref in left
                    for right_ref in right
                ):
                    raise GameRuleError(
                        "Related targets must belong to the same player"
                    )
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
        if item.semantic_key in {
            "builtin:food",
            "builtin:optional-mill-one",
            "builtin:sacrifice-source",
            "builtin:storm",
            "builtin:thornbite-untap",
        }:
            return True
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
        if (
            item.kind == "spell_copy"
            and item.context.get("copy_permanent_spell")
        ):
            return True
        if item.kind == "spell" and item.card_object_id:
            record = self.card_record(item.card_object_id)
            if record and item.default_destination == "battlefield":
                oracle = record.oracle_text.casefold()
                semantic_markers = ("when ", "whenever ", "as ~ enters", "as this", "enters with", "you may have")
                return not any(marker in oracle for marker in semantic_markers)
        return False

    def _begin_battle_entry_protector_choice(
        self,
        item: StackItem,
    ) -> bool:
        """Request the CR 310.8a protector choice as a Battle enters."""

        if (
            item.default_destination != "battlefield"
            or item.card_object_id not in self.state.cards
        ):
            return False
        card = self.state.cards[item.card_object_id]
        if card.zone != "stack":
            return False
        card_types, subtypes, _ = self._type_parts(
            str(
                self._effective_card_data(card).get("type_line")
                or ""
            )
        )
        if "battle" not in card_types:
            return False
        if not subtypes:
            card.battle_protector = card.controller
            return False
        if "siege" not in subtypes:
            raise GameRuleError(
                "The protector predicate for Battle type(s) "
                f"{sorted(subtypes)} is not compiled"
            )
        if (
            card.battle_protector in self.active_seats
            and card.battle_protector != card.controller
        ):
            return False
        candidates = [
            opponent
            for opponent in self.active_seats
            if opponent != card.controller
        ]
        if not candidates:
            raise GameRuleError(
                "No opponent is available to protect this Siege"
            )
        self.permissions.issue(
            kind="battle.enter_protector",
            role="pilot",
            actors=[card.controller],
            allowed_actions=["choose"],
            payload_by_actor={
                card.controller: {
                    "stack": item.ref,
                    "battle": card.ref,
                    "name": self.display_name(card.object_id),
                    "protectors": candidates,
                    "instruction": (
                        "Choose an opponent to protect this Siege as "
                        "it enters."
                    ),
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "protector": {
                                    "type": "seat",
                                    "legal_seats": candidates,
                                    "required": True,
                                }
                            },
                        }
                    ],
                }
            },
            continuation={
                "stack_ref": item.ref,
                "object_id": card.object_id,
                "source_logical_object_id": card.logical_object_id,
                "candidates": candidates,
            },
        )
        return True

    def _complete_battle_entry_protector_choice(
        self,
        decision: Any,
    ) -> None:
        seat = decision.actors[0]
        stack_ref = str(decision.continuation["stack_ref"])
        item = next(
            (
                candidate
                for candidate in self.state.stack
                if candidate.ref == stack_ref
            ),
            None,
        )
        card = self.state.cards.get(
            str(decision.continuation["object_id"])
        )
        if (
            item is None
            or card is None
            or item.card_object_id != card.object_id
            or card.zone != "stack"
            or card.controller != seat
            or card.logical_object_id
            != str(
                decision.continuation[
                    "source_logical_object_id"
                ]
            )
        ):
            raise GameRuleError(
                "The Battle entry choice no longer matches that spell"
            )
        protector = str(
            decision.responses[seat].get("protector")
            or decision.responses[seat].get("player")
            or ""
        )
        candidates = {
            str(value)
            for value in decision.continuation.get(
                "candidates", []
            )
        }
        if protector not in candidates or protector not in self.active_seats:
            raise GameRuleError(
                "Choose one of the legal Siege protectors"
            )
        card.battle_protector = protector
        self._log(
            seat,
            "battle.protector.chosen",
            f"{seat} chose {protector} to protect {card.ref}.",
            {
                "stack": item.ref,
                "battle": card.ref,
                "protector": protector,
            },
            importance=2,
            changed_objects=[card.object_id],
            changed_players=[seat, protector],
        )
        self._prepare_stack_resolution()

    def _finish_siege_defeated_resolution(
        self,
        item: StackItem,
        *,
        outcome: str,
        card: CardInstance | None = None,
        cast_stack_ref: str | None = None,
    ) -> None:
        if item in self.state.stack:
            self.state.stack.remove(item)
        self._log(
            item.controller,
            "battle.siege_defeated.resolve",
            f"Resolved {item.ref}: {item.label} ({outcome}).",
            {
                "stack": item.ref,
                "battle": card.ref if card is not None else None,
                "outcome": outcome,
                "cast_stack": cast_stack_ref,
            },
            importance=2,
            changed_objects=(
                [card.object_id] if card is not None else []
            ),
            changed_players=[item.controller],
        )
        if self._stabilize():
            return
        self._grant_priority(self.state.active_player)

    def _begin_siege_defeated_resolution(
        self,
        item: StackItem,
    ) -> None:
        """Resolve the intrinsic CR 310.11b Siege ability natively."""

        card = self.state.cards.get(item.source_object_id or "")
        expected_logical_object_id = str(
            item.context.get("source_logical_object_id") or ""
        )
        if (
            card is None
            or card.zone != "battlefield"
            or card.logical_object_id != expected_logical_object_id
        ):
            self._finish_siege_defeated_resolution(
                item,
                outcome="source_unavailable",
                card=card,
            )
            return

        self.move_card(
            card.object_id,
            "exile",
            reason="Siege defeated trigger",
            semantic_events=True,
        )
        if card.zone != "exile":
            self._finish_siege_defeated_resolution(
                item,
                outcome="exile_failed",
                card=card,
            )
            return

        record = self.card_record(card)
        can_cast_transformed = bool(
            card.is_card_object
            and record is not None
            and record.layout == "transform"
            and len(record.faces) >= 2
            and str(record.faces[1].get("name") or "")
        )
        if not can_cast_transformed:
            self._finish_siege_defeated_resolution(
                item,
                outcome="exiled_not_castable_transformed",
                card=card,
            )
            return

        transformed_face_data = dict(record.faces[1])
        transformed_face = str(transformed_face_data["name"])
        semantic_key = (
            f"{record.oracle_id}:spell:{transformed_face}"
        )
        program = self.semantics.get(semantic_key)
        transformed_types, _, _ = self._type_parts(
            str(transformed_face_data.get("type_line") or "")
        )
        if (
            transformed_types.intersection({"instant", "sorcery"})
            and re.search(
                r"\btarget\b",
                str(transformed_face_data.get("oracle_text") or ""),
                re.IGNORECASE,
            )
            and (
                program is None
                or program.target_schema is None
            )
        ):
            self.permissions.issue(
                kind="arbiter.resolve",
                role="arbiter",
                actors=["arbiter"],
                allowed_actions=[
                    "resolve",
                    "register_and_resolve",
                    "counter_as_rule",
                    "fizzle",
                ],
                payload_by_actor={
                    "arbiter": {
                        "stack": item.ref,
                        "label": item.label,
                        "controller": item.controller,
                        "semantic_key": item.semantic_key,
                        "default_destination": None,
                        "reason": (
                            "transformed Siege spell has unresolved "
                            "mandatory target semantics"
                        ),
                        "battle": card.ref,
                        "transformed_face": transformed_face,
                    }
                },
            )
            return

        options = self._cast_cost_options(
            item.controller,
            card,
            program,
            hint=True,
            force_without_mana_cost=True,
        )
        public_options: list[dict[str, Any]] = []
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
                    item.controller,
                    target_specification,
                    source_ref=card.ref,
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
            public_options.append(public_option)
        if not public_options:
            self._finish_siege_defeated_resolution(
                item,
                outcome="exiled_cast_unavailable",
                card=card,
            )
            return

        self.permissions.issue(
            kind="battle.siege_defeated",
            role="pilot",
            actors=[item.controller],
            allowed_actions=["choose"],
            payload_by_actor={
                item.controller: {
                    "stack": item.ref,
                    "battle": card.ref,
                    "name": record.name,
                    "transformed_face": transformed_face,
                    "cast_options": public_options,
                    "prompt": (
                        "Cast this card transformed without paying its "
                        "mana cost?"
                    ),
                    "legal_actions": [
                        {
                            "id": "cast",
                            "action": "choose",
                            "choice": "cast",
                            "choice_schema": {
                                "choice": "cast",
                                "cast_options": public_options,
                            },
                        },
                        {
                            "id": "decline",
                            "action": "choose",
                            "choice": "decline",
                            "choice_schema": {
                                "choice": "decline",
                            },
                        },
                    ],
                }
            },
            continuation={
                "stack_ref": item.ref,
                "object_id": card.object_id,
                "exile_logical_object_id": card.logical_object_id,
                "transformed_face": transformed_face,
            },
        )

    def _complete_siege_defeated_choice(
        self,
        decision: Any,
    ) -> None:
        seat = decision.actors[0]
        stack_ref = str(decision.continuation.get("stack_ref") or "")
        item = next(
            (
                candidate
                for candidate in self.state.stack
                if candidate.ref == stack_ref
                and candidate.semantic_key
                == "builtin:siege-defeated"
            ),
            None,
        )
        card = self.state.cards.get(
            str(decision.continuation.get("object_id") or "")
        )
        if item is None:
            raise GameRuleError(
                "The Siege defeated trigger is no longer on the stack"
            )
        if (
            card is None
            or card.zone != "exile"
            or card.logical_object_id
            != str(
                decision.continuation.get(
                    "exile_logical_object_id"
                )
                or ""
            )
        ):
            raise GameRuleError(
                "The exiled Siege is no longer the object offered for "
                "the transformed cast"
            )
        choice = str(
            decision.responses[seat].get("choice")
            or decision.responses[seat].get("option")
            or ""
        )
        if choice not in {"cast", "decline"}:
            raise GameRuleError(
                "Choose whether to cast the defeated Siege transformed"
            )
        if choice == "decline":
            self._finish_siege_defeated_resolution(
                item,
                outcome="declined",
                card=card,
            )
            return

        transformed_face = str(
            decision.continuation.get("transformed_face") or ""
        )
        before_stack_refs = {
            candidate.ref for candidate in self.state.stack
        }
        cast_response = dict(
            decision.responses[seat].get("cast") or {}
        )
        cast_response.update(
            {
                key: copy.deepcopy(value)
                for key, value in decision.responses[seat].items()
                if key not in {"action", "cast", "choice", "option"}
            }
        )
        cast_response.update(
            {
                "card": card.ref,
                "from": "exile",
                "face": transformed_face,
                "auto_pay": True,
            }
        )
        self._cast(
            seat,
            cast_response,
            authorized_from_zone="exile",
            required_face=transformed_face,
            force_without_mana_cost=True,
            ignore_priority=True,
            ignore_timing=True,
            during_resolution=True,
        )
        cast_item = next(
            (
                candidate
                for candidate in reversed(self.state.stack)
                if candidate.ref not in before_stack_refs
                and candidate.kind == "spell"
                and candidate.card_object_id == card.object_id
            ),
            None,
        )
        if cast_item is None:
            raise StateInvariantError(
                "The transformed Siege cast did not create a spell"
            )
        self._finish_siege_defeated_resolution(
            item,
            outcome="cast_transformed",
            card=card,
            cast_stack_ref=cast_item.ref,
        )

    def _prepare_stack_resolution(self) -> None:
        if self.state.pending_trigger_batches and self._stabilize():
            return
        if not self.state.stack:
            self._advance_step()
            return
        item = self.state.stack[-1]
        if self._begin_battle_entry_protector_choice(item):
            return
        if item.semantic_key == "builtin:siege-defeated":
            self._begin_siege_defeated_resolution(item)
            return
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
        if item.semantic_key == "builtin:food":
            self._begin_resolve_item(
                item,
                [
                    {
                        "op": "life",
                        "player": item.controller,
                        "delta": 3,
                        "reason": "Food token",
                    }
                ],
                None,
                note="Built-in Food token ability resolved",
            )
            return
        if item.semantic_key == "builtin:map-explore":
            self._begin_resolve_item(
                item,
                [
                    {
                        "op": "explore",
                        "player": item.controller,
                        "card": "$target.0",
                    }
                ],
                None,
                note="Map token explore ability resolved",
            )
            return
        if item.semantic_key == "builtin:ward":
            self._begin_resolve_item(
                item,
                [
                    {
                        "op": "counter_unless_pay",
                        "player": str(item.context["payer"]),
                        "stack": str(item.context["target_stack"]),
                        "cost": dict(item.context.get("cost") or {}),
                    }
                ],
                None,
                note="Ward trigger resolved",
            )
            return
        if item.semantic_key == "builtin:optional-mill-one":
            self._begin_resolve_item(
                item,
                [
                    {
                        "op": "choose_option",
                        "player": item.controller,
                        "prompt": "You may mill a card.",
                        "options": [
                            {"id": "mill", "label": "Mill a card"},
                            {"id": "decline", "label": "Do not mill"},
                        ],
                        "then_by_choice": {
                            "mill": [
                                {
                                    "op": "mill",
                                    "player": item.controller,
                                    "count": 1,
                                }
                            ],
                            "decline": [],
                        },
                    }
                ],
                None,
                note="Moloid attack trigger",
            )
            return
        if item.semantic_key == "builtin:thornbite-untap":
            source = self.state.cards.get(item.source_object_id or "")
            self._begin_resolve_item(
                item,
                (
                    [{"op": "untap", "card": "$source"}]
                    if source is not None
                    and source.zone == "battlefield"
                    else []
                ),
                None,
                note="Thornbite Staff granted trigger",
            )
            return
        if item.semantic_key == "builtin:daretti-emblem":
            card_ref = str(item.context.get("card") or "")
            card_zone_change_counter = item.context.get(
                "card_zone_change_counter"
            )
            self._begin_resolve_item(
                item,
                [
                    {
                        "op": "delayed_trigger",
                        "controller": item.controller,
                        "label": (
                            f"Return {card_ref} with Daretti's emblem"
                        ),
                        "event": "step.begin",
                        "condition": {
                            "phase": "ending",
                            "step": "end_step",
                        },
                        "stack": {
                            "label": (
                                f"Return {card_ref} with Daretti's emblem"
                            ),
                            "context": {
                                "dynamic_effects": [
                                    {
                                        "op": "move_if_in_zone",
                                        "card": card_ref,
                                        "from": "graveyard",
                                        "destination": "battlefield",
                                        "controller": item.controller,
                                        "expected_zone_change_counter": (
                                            card_zone_change_counter
                                        ),
                                    }
                                ]
                            },
                        },
                        "once": True,
                    }
                ],
                None,
                note="Daretti emblem delayed return scheduled",
            )
            return
        program = self.semantics.get(item.semantic_key)
        if (
            program is not None
            and "intervening_condition" in program.coverage
            and program.event_condition is not None
        ):
            source = self.state.cards.get(item.source_object_id or "")
            condition_holds = bool(
                source is not None
                and source.zone == program.active_zone
                and self._semantic_event_condition_matches(
                    program.event_condition,
                    source=source,
                    context=item.context,
                )
            )
            if not condition_holds:
                self.state.stack.remove(item)
                self._log(
                    item.controller,
                    "stack.trigger.removed",
                    (
                        f"Removed {item.ref}: {item.label}; its intervening "
                        "condition was false on resolution."
                    ),
                    {
                        "stack": item.ref,
                        "reason": "intervening_condition_false",
                    },
                    importance=2,
                )
                if not self._stabilize():
                    self._grant_priority(self.state.active_player)
                return
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
        elif (
            program is None
            and item.kind == "spell_copy"
            and item.context.get("copy_permanent_spell")
        ):
            trusted_generic_resolution = True
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
                "modes": copy.deepcopy(template.get("modes") or []),
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
            normalized = self._normalize_target_submission(raw_targets)
            selected = (
                [str(value) for value in normalized]
                if all(
                    not isinstance(value, Mapping)
                    for value in normalized
                )
                else []
            )
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
                    normalized,
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
                    default_destination=template.get(
                        "default_destination"
                    ),
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
        source_card = self.state.cards.get(
            str(template.get("card_object_id") or "")
        )
        source_data = (
            self._copyable_characteristics(source_card)
            if source_card is not None
            else {
                "name": str(template.get("label") or "Spell"),
                "type_line": "Instant",
            }
        )
        for copy_item in copies:
            copy_object = self._create_copy_object(
                controller=seat,
                source=source_card,
                characteristics=source_data,
                object_kind="spell_copy",
                zone="stack",
            )
            copy_item.card_object_id = copy_object.object_id
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

    def _create_copy_object(
        self,
        *,
        controller: str,
        source: CardInstance | None,
        characteristics: Mapping[str, Any],
        object_kind: str,
        zone: str,
    ) -> CardInstance:
        """Create one serialized noncard copy object.

        Stack copies are associated with a ``StackItem`` by their caller.
        Copies in ordinary zones use normal owner-zone membership until the
        next state-based-action check makes them cease.
        """

        self._require_seat(controller, in_game=True)
        if object_kind not in {"spell_copy", "card_copy"}:
            raise GameRuleError("A copy object needs a typed copy kind")
        if zone not in {
            "library",
            "hand",
            "battlefield",
            "graveyard",
            "exile",
            "command",
            "stack",
        }:
            raise GameRuleError(f"Unsupported copy-object zone {zone}")
        ref = self._next_ref("O")
        object_id = self._stable_runtime_id("copy-object", ref)
        copied_values = copy.deepcopy(dict(characteristics))
        name = str(
            copied_values.get("name")
            or (source.printed_name if source is not None else "Copy")
        )
        oracle_id = (
            source.oracle_id
            if source is not None
            else (
                "custom-copy:"
                f"{self._stable_runtime_id('copy-oracle', ref)}"
            )
        )
        public = zone in PUBLIC_ZONES or zone in {
            "battlefield",
            "stack",
        }
        card = CardInstance(
            object_id=object_id,
            ref=ref,
            oracle_id=oracle_id,
            printed_name=name,
            owner=controller,
            controller=controller,
            zone=zone,
            object_kind=object_kind,
            zone_timestamp=self._next_zone_timestamp(),
            active_face=(
                source.active_face if source is not None else None
            ),
            annotations={
                "copy_overrides": copied_values,
                **(
                    {"copied_from": source.object_id}
                    if source is not None
                    else {
                        "token_characteristics": copied_values,
                    }
                ),
            },
            known_to=(
                list(self.seats) if public else [controller]
            ),
            revealed_to=(
                list(self.seats) if public else []
            ),
        )
        self.state.cards[object_id] = card
        if zone != "stack":
            self.state.players[controller].zones[zone].append(
                object_id
            )
        if zone == "battlefield":
            card.acquired_control_turn_count = self.state.players[
                controller
            ].turns_begun
            card.entered_battlefield_turn_sequence = (
                self.state.turn_sequence
            )
            self._refresh_world_supertype_timestamp(
                card,
                gained_at=card.zone_timestamp,
            )
        return card

    def create_card_copy(
        self,
        controller: str,
        source: str,
        *,
        zone: str | None = None,
    ) -> CardInstance:
        """Create a noncard copy for a compiled CR 707 effect.

        Casting that copy during the resolving effect remains a separate
        casting operation. Callers cannot create an unattached stack object.
        """

        original = self._resolve_object(controller, source)
        destination = str(zone or original.zone)
        if destination == "stack":
            raise GameRuleError(
                "A card copy becomes a stack object only through casting"
            )
        return self._create_copy_object(
            controller=controller,
            source=original,
            characteristics=self._copyable_characteristics(original),
            object_kind="card_copy",
            zone=destination,
        )

    def _copy_stack_item(
        self,
        *,
        controller: str,
        target: StackItem,
        targets: Sequence[str],
        target_groups: Mapping[str, Sequence[str]],
        reason: str,
    ) -> StackItem:
        """Create an independent stack copy without copying paid costs."""

        ref = self._next_ref("S")
        original_card = self.state.cards.get(
            target.card_object_id or ""
        )
        original_data = (
            self._copyable_characteristics(original_card)
            if original_card is not None
            else {}
        )
        original_types, _, _ = self._type_parts(
            str(original_data.get("type_line") or "")
        )
        permanent_spell = bool(
            target.kind in {"spell", "spell_copy"}
            and original_types
            and not original_types.intersection({"instant", "sorcery"})
        )
        copy_object = (
            self._create_copy_object(
                controller=controller,
                source=original_card,
                characteristics=(
                    original_data
                    or {
                        "name": target.label,
                        "type_line": "Instant",
                    }
                ),
                object_kind="spell_copy",
                zone="stack",
            )
            if target.kind in {"spell", "spell_copy"}
            else None
        )
        copied = StackItem(
            stack_id=self._stable_runtime_id("stack", ref),
            ref=ref,
            kind=(
                "spell_copy"
                if target.kind in {"spell", "spell_copy"}
                else target.kind
            ),
            controller=controller,
            label=f"{target.label} copy",
            card_object_id=(
                copy_object.object_id
                if copy_object is not None
                else None
            ),
            source_object_id=target.source_object_id,
            semantic_key=target.semantic_key,
            targets=[str(value) for value in targets],
            modes=list(target.modes),
            x_value=target.x_value,
            chosen_face=target.chosen_face,
            notes=target.notes,
            default_destination=target.default_destination,
            visibility=list(self.seats),
            context={
                **copy.deepcopy(dict(target.context)),
                "target_groups": {
                    str(key): [str(value) for value in values]
                    for key, values in target_groups.items()
                },
                "target_snapshots": {
                    str(value): self._target_snapshot(str(value))
                    for value in targets
                },
                "targets_revalidated": False,
                "targets_chosen_at_creation": True,
                "copied_from_stack": target.ref,
                "copy_permanent_spell": permanent_spell,
                "copy_permanent_name": str(
                    original_data.get("name") or target.label
                ),
                "copy_permanent_characteristics": copy.deepcopy(
                    original_data
                ),
            },
        )
        self.state.stack.append(copied)
        self._log(
            controller,
            "stack.copy",
            f"{controller} copied {target.ref} as {copied.ref}.",
            {
                "source_stack": target.ref,
                "copy_stack": copied.ref,
                "targets": list(copied.targets),
                "reason": reason,
            },
            importance=2,
        )
        return copied

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
        targets = self._normalize_target_submission(
            response.get("targets")
        )
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
        if not self.state.stack or self.state.stack[-1] is not item:
            raise GameRuleError(
                "Only the top object of the stack can begin resolving"
            )
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
                original_snapshot = dict(
                    item.context.get("target_snapshots", {}).get(
                        ref, {}
                    )
                )
                identity_matches = (
                    self._target_identity_matches_snapshot(
                        ref,
                        original_snapshot,
                    )
                )
                if ref in legal and identity_matches:
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
                        "reason": (
                            "object_identity_changed"
                            if ref in legal and not identity_matches
                            else "candidate_no_longer_matches"
                        ),
                    },
                    importance=2,
                )
            current_groups[group.group_id] = current
        item.targets = updated
        item.context["target_groups_current"] = current_groups
        item.context["targets_revalidated"] = True
        if selected_count and valid_count == 0:
            if item.context.get("cost_option") == "bestow":
                self._log(
                    item.controller,
                    "bestow.target.illegal",
                    (
                        f"{item.ref} lost its bestow target and will "
                        "resolve as a creature."
                    ),
                    {"stack": item.ref},
                    importance=2,
                )
                return True
            self._counter_stack_item(
                item.ref,
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
            return self._stack_source_ref(item)
        if value == "$card":
            card = self.state.cards.get(item.card_object_id or "")
            return card.ref if card else None
        if value == "$stack":
            return item.ref
        if value == "$x":
            return item.x_value or 0
        if value == "$turn_sequence":
            return self.state.turn_sequence
        if value.startswith("$context."):
            return item.context.get(value.removeprefix("$context."))
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
                return None
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
                return None
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
        item.context["currently_resolving"] = True
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
            try:
                typed_plan = default_semantic_interpreter().lower_for_seats(
                    effect,
                    actor=item.controller,
                    default_reason=item.label,
                    seats=self.seats,
                    active_seats=self.active_seats,
                    apnap_order=self.apnap_order(),
                )
            except SemanticNodeError as exc:
                raise GameRuleError(str(exc)) from exc
            if typed_plan is not None:
                draw_request = prepare_draw_resolution(
                    typed_plan,
                    tuple(effects[index + 1 :]),
                )
                if draw_request is not None:
                    if draw_request.current is None:
                        index += 1
                        continue
                    self._begin_draw_sequence(
                        draw_request.current.player,
                        draw_request.current.count,
                        reason=draw_request.current.reason,
                        private=draw_request.current.private,
                        continuation={
                            "kind": "semantic_resolution",
                            "stack_ref": stack_ref,
                            "effects": list(
                                draw_request.remaining_effects
                            ),
                            "destination": destination,
                            "note": note,
                            "instruction_pointer": (
                                instruction_pointer + index + 1
                            ),
                        },
                    )
                    return
                execute_intent_plan(self, typed_plan)
                if item not in self.state.stack:
                    return
                index += 1
                continue
            if effect.get("op") in {
                "choose_card_name",
                "choose_creature_type",
                "choose_objects",
                "choose_option",
                "choose_mana",
                "copy_all_tokens",
                "copy_stack_item",
                "counter_unless_pay",
                "cumulative_upkeep",
                "daretti_exchange",
                "discard_draw_up_to",
                "draw_optional_land",
                "explore",
                "fabricate",
                "fomori_vault",
                "choose_warform",
                "amass",
                "look_reorder_top",
                "pay_or_lose",
                "populate_with_haste",
                "proliferate",
                "put_land_from_hand",
                "put_artifact_from_hand",
                "remora_tax",
                "retarget_stack_item",
                "scry",
                "springheart_landfall",
                "sylvan_library_settle",
                "transmute_artifact",
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
            replacement_frame = (effects[index + 1 :], destination, note, instruction_pointer + index)
            if not apply_effect_with_replacement_choice(self, item, effect, replacement_frame):
                return
            index += 1
        # Remove the resolving object from stack only when all player choices
        # and effects have completed.
        item.context.pop("currently_resolving", None)
        self.state.stack.remove(item)
        self._maybe_sacrifice_completed_saga(item)
        entered: CardInstance | None = None
        if item.context.get("copy_permanent_spell"):
            if not item.card_object_id:
                raise StateInvariantError(
                    "A permanent spell copy requires a copy object"
                )
            card = self.state.cards[item.card_object_id]
            if not card.is_spell_copy or card.zone != "stack":
                raise StateInvariantError(
                    "Permanent spell-copy object left the stack early"
                )
            characteristics = copy.deepcopy(
                dict(
                    item.context.get(
                        "copy_permanent_characteristics", {}
                    )
                )
            )
            name = str(
                item.context.get("copy_permanent_name")
                or item.label.removesuffix(" copy")
            )
            card.printed_name = name
            card.annotations["copy_overrides"] = characteristics
            # CR 608.3f/707.10f: this same spell-copy object becomes a token
            # permanent. It is not a newly created token.
            card.object_kind = "token"
            card.is_token = True
            entered = self.move_card(
                card.object_id,
                "battlefield",
                controller=item.controller,
                reason="permanent spell copy resolved",
                log=False,
                semantic_events=True,
            )
        elif item.card_object_id:
            card = self.state.cards[item.card_object_id]
            if card.zone == "stack":
                if item.context.get("cost_option") == "evoke":
                    card.annotations["evoked"] = True
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
            legal_colors = [
                str(value).upper()
                for value in effect.get("colors", list("WUBRGC"))
                if str(value).upper() in "WUBRGC"
                and len(str(value)) == 1
            ]
            if not legal_colors:
                raise GameRuleError(
                    "Semantic mana choice requires at least one legal color"
                )
            context.update(
                {
                    "prompt": "Choose a mana color.",
                    "options": legal_colors,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "choice",
                                "legal_values": legal_colors,
                            },
                        }
                    ],
                }
            )
        elif op == "copy_stack_item":
            target_ref = str(effect.get("stack") or "")
            target_item = next(
                (
                    candidate
                    for candidate in self.state.stack
                    if candidate.ref == target_ref
                    and candidate.ref != item.ref
                ),
                None,
            )
            if target_item is None:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            target_program = self.semantics.get(
                target_item.semantic_key
            )
            target_schema = self._stack_target_schema(
                target_item,
                target_program,
            )
            if not target_schema or not target_item.targets:
                self._copy_stack_item(
                    controller=seat,
                    target=target_item,
                    targets=list(target_item.targets),
                    target_groups=copy.deepcopy(
                        dict(
                            target_item.context.get(
                                "target_groups", {}
                            )
                        )
                    ),
                    reason=item.label,
                )
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            public_schema = self._public_target_schema(
                seat,
                target_schema,
                source_ref=self._stack_source_ref(target_item),
            )
            if public_schema is None:
                raise GameRuleError(
                    "The copied stack object has no legal target assignment"
                )
            effect = {
                **dict(effect),
                "_target_stack_ref": target_item.ref,
                "_target_schema": copy.deepcopy(dict(target_schema)),
                "_default_targets": list(target_item.targets),
            }
            context.update(
                {
                    "prompt": (
                        "Choose targets for the copy, or keep the "
                        "original targets."
                    ),
                    "target_stack": target_item.ref,
                    "default_targets": list(target_item.targets),
                    "target_schema": public_schema,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "targets",
                                "optional": True,
                                "default": list(target_item.targets),
                                "target_schema": public_schema,
                            },
                        }
                    ],
                }
            )
        elif op == "retarget_stack_item":
            target_ref = str(effect.get("stack") or "")
            target_item = next(
                (
                    candidate
                    for candidate in self.state.stack
                    if candidate.ref == target_ref
                    and candidate.ref != item.ref
                ),
                None,
            )
            if target_item is None:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            target_program = self.semantics.get(
                target_item.semantic_key
            )
            target_schema = self._stack_target_schema(
                target_item,
                target_program,
            )
            if not target_schema or not target_item.targets:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            if available_modes(target_schema):
                plan = target_plan(
                    target_schema,
                    target_item.modes,
                    require_modes=True,
                )
                candidates = self._target_candidate_map(
                    target_item.controller,
                    plan,
                    source_ref=self._stack_source_ref(target_item),
                )
                if not self._target_plan_feasible(plan, candidates):
                    raise GameRuleError(
                        "The target stack object has no legal new "
                        "target assignment"
                    )
                public_schema = {
                    "groups": [
                        group.public_dict(candidates[group.group_id])
                        for group in plan.groups
                    ],
                    "legal_refs": unique_preserving_order(
                        ref
                        for group in plan.groups
                        for ref in candidates[group.group_id]
                    ),
                }
            else:
                public_schema = self._public_target_schema(
                    target_item.controller,
                    target_schema,
                    source_ref=self._stack_source_ref(target_item),
                )
            if public_schema is None:
                raise GameRuleError(
                    "The target stack object has no legal new targets"
                )
            effect = {
                **dict(effect),
                "_target_stack_ref": target_item.ref,
                "_target_schema": copy.deepcopy(dict(target_schema)),
                "_default_targets": list(target_item.targets),
            }
            context.update(
                {
                    "prompt": (
                        "Choose new targets, or keep the current "
                        "targets."
                    ),
                    "target_stack": target_item.ref,
                    "default_targets": list(target_item.targets),
                    "target_schema": public_schema,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "targets",
                                "optional": True,
                                "default": list(target_item.targets),
                                "target_schema": public_schema,
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
        elif op == "choose_creature_type":
            context.update(
                {
                    "prompt": "Choose a creature type.",
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "creature_type",
                                "type": "creature_type",
                                "nonempty": True,
                                "max_length": 48,
                            },
                        }
                    ],
                }
            )
        elif op == "fabricate":
            source = self.state.cards.get(
                item.source_object_id or item.card_object_id or ""
            )
            legal_values = ["token"]
            if source is not None and source.zone == "battlefield":
                legal_values.insert(0, "counter")
            effect = {
                **dict(effect),
                "_legal_values": legal_values,
            }
            context.update(
                {
                    "prompt": (
                        "Choose whether to put +1/+1 counter(s) on the "
                        "source or create Servo token(s)."
                    ),
                    "options": [
                        {
                            "id": value,
                            "label": (
                                "Put +1/+1 counters on this creature"
                                if value == "counter"
                                else "Create Servo tokens"
                            ),
                        }
                        for value in legal_values
                    ],
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "choice",
                                "legal_values": legal_values,
                            },
                        }
                    ],
                }
            )
        elif op in {"populate_with_haste", "copy_all_tokens"}:
            options = [
                self.state.cards[object_id].ref
                for object_id in self.state.players[
                    seat
                ].zones["battlefield"]
                if self.state.cards[object_id].controller == seat
                and self.state.cards[object_id].is_token
                and (
                    op == "copy_all_tokens"
                    or "creature"
                    in self._type_parts(
                        str(
                            self._effective_card_data(object_id).get(
                                "type_line"
                            )
                            or ""
                        )
                    )[0]
                )
            ]
            if not options:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {**dict(effect), "_legal_refs": options}
            context.update(
                {
                    "prompt": (
                        "Choose a creature token to populate."
                        if op == "populate_with_haste"
                        else "Choose a token for every other token to copy."
                    ),
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
        elif op == "put_land_from_hand":
            options = [
                self.state.cards[object_id].ref
                for object_id in self.state.players[seat].zones["hand"]
                if "land"
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
            ]
            if not options:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {**dict(effect), "_legal_refs": options}
            context.update(
                {
                    "prompt": str(
                        effect.get("prompt")
                        or (
                            "You may put a land card from your hand "
                            "onto the battlefield."
                        )
                    ),
                    "objects": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat,
                                ref,
                                zones={"hand"},
                                owned_only=True,
                            ).printed_name,
                        }
                        for ref in options
                    ],
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
        elif op == "put_artifact_from_hand":
            options = [
                self.state.cards[object_id].ref
                for object_id in self.state.players[seat].zones["hand"]
                if "artifact"
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
            ]
            if not options:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {**dict(effect), "_legal_refs": options}
            context.update(
                {
                    "prompt": (
                        "You may put an artifact card from your hand "
                        "onto the battlefield."
                    ),
                    "objects": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat,
                                ref,
                                zones={"hand"},
                                owned_only=True,
                            ).printed_name,
                        }
                        for ref in options
                    ],
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
        elif op == "explore":
            explorer = self._resolve_object(
                seat,
                str(effect["card"]),
                zones={"battlefield"},
            )
            library = self.state.players[seat].zones["library"]
            if not library:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            top = self.state.cards[library[-1]]
            top.known_to = list(self.seats)
            top.revealed_to = list(self.seats)
            top_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(top).get("type_line")
                    or ""
                )
            )
            self._log(
                seat,
                "explore.reveal",
                f"{seat} revealed {top.printed_name} while exploring.",
                {
                    "player": seat,
                    "card": top.ref,
                    "explorer": explorer.ref,
                },
                importance=2,
                changed_objects=[top.object_id, explorer.object_id],
            )
            if "land" in top_types:
                self.move_card(
                    top.object_id,
                    "hand",
                    reason="explore",
                    semantic_events=True,
                )
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            explorer.counters["+1/+1"] = (
                int(explorer.counters.get("+1/+1", 0)) + 1
            )
            effect = {
                **dict(effect),
                "_top_ref": top.ref,
                "_explorer_ref": explorer.ref,
            }
            context.update(
                {
                    "prompt": (
                        "Put the revealed nonland card into your "
                        "graveyard or leave it on top."
                    ),
                    "card": {
                        "id": top.ref,
                        "name": top.printed_name,
                    },
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "choice",
                                "legal_values": ["graveyard", "top"],
                            },
                        }
                    ],
                }
            )
        elif op == "fomori_vault":
            artifact_count = sum(
                1
                for object_id in self.state.players[seat].zones[
                    "battlefield"
                ]
                if self.state.cards[object_id].controller == seat
                and not self.state.cards[object_id].phased_out
                and "artifact"
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
            )
            looked = self.apply_effect(
                {
                    "op": "look_top",
                    "player": seat,
                    "viewer": seat,
                    "count": artifact_count,
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
            effect = {
                **dict(effect),
                "_looked_refs": options,
                "_artifact_count": artifact_count,
            }
            context.update(
                {
                    "prompt": (
                        "Choose one looked-at card to put into your "
                        "hand. The rest go to the bottom at random."
                    ),
                    "cards": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat,
                                ref,
                                zones={"library"},
                                owned_only=True,
                            ).printed_name,
                        }
                        for ref in options
                    ],
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
        elif op == "discard_draw_up_to":
            maximum = max(0, int(effect.get("maximum", 2)))
            options = [
                self.state.cards[object_id].ref
                for object_id in self.state.players[seat].zones["hand"]
            ]
            if not options or maximum == 0:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            maximum = min(maximum, len(options))
            effect = {
                **dict(effect),
                "_legal_refs": options,
                "_maximum": maximum,
            }
            context.update(
                {
                    "prompt": (
                        f"Discard up to {maximum} card(s), then draw "
                        "that many cards."
                    ),
                    "cards": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat,
                                ref,
                                zones={"hand"},
                                owned_only=True,
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
                                "minimum": 0,
                                "maximum": maximum,
                                "distinct": True,
                            },
                        }
                    ],
                }
            )
        elif op == "daretti_exchange":
            options = [
                self.state.cards[object_id].ref
                for object_id in self.state.players[seat].zones[
                    "battlefield"
                ]
                if self.state.cards[object_id].controller == seat
                and not self.state.cards[object_id].phased_out
                and "artifact"
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
            ]
            if not options:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {
                **dict(effect),
                "_legal_refs": options,
            }
            context.update(
                {
                    "prompt": (
                        "Choose an artifact you control to sacrifice."
                    ),
                    "objects": options,
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
        elif op == "transmute_artifact":
            stage = str(effect.get("stage") or "sacrifice")
            if stage == "sacrifice":
                options = [
                    self.state.cards[object_id].ref
                    for object_id in self.state.players[seat].zones[
                        "battlefield"
                    ]
                    if self.state.cards[object_id].controller == seat
                    and not self.state.cards[object_id].phased_out
                    and "artifact"
                    in self._type_parts(
                        str(
                            self._effective_card_data(object_id).get(
                                "type_line"
                            )
                            or ""
                        )
                    )[0]
                ]
                if not options:
                    self._continue_resolution(
                        stack_ref=item.ref,
                        effects=list(remaining),
                        destination=destination,
                        note=note,
                        instruction_pointer=instruction_pointer + 1,
                    )
                    return
                effect = {
                    **dict(effect),
                    "stage": stage,
                    "_legal_refs": options,
                }
                context.update(
                    {
                        "prompt": (
                            "Choose exactly one artifact to sacrifice "
                            "while Transmute Artifact resolves."
                        ),
                        "objects": options,
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
            elif stage == "search":
                options = [
                    self.state.cards[object_id].ref
                    for object_id in self.state.players[seat].zones[
                        "library"
                    ]
                    if "artifact"
                    in self._type_parts(
                        str(
                            self._effective_card_data(object_id).get(
                                "type_line"
                            )
                            or ""
                        )
                    )[0]
                ]
                effect = {
                    **dict(effect),
                    "stage": stage,
                    "_legal_refs": options,
                }
                context.update(
                    {
                        "prompt": (
                            "Choose an artifact card from your library, "
                            "or fail to find."
                        ),
                        "search_cards": [
                            {
                                "id": ref,
                                "name": self._resolve_object(
                                    seat,
                                    ref,
                                    zones={"library"},
                                    owned_only=True,
                                ).printed_name,
                            }
                            for ref in options
                        ],
                        "legal_actions": [
                            {
                                "id": "choose",
                                "action": "choose",
                                "choice_schema": {
                                    "field": "card",
                                    "legal_refs": options,
                                    "optional": True,
                                    "rules_may_fail_to_find": True,
                                },
                            }
                        ],
                    }
                )
            elif stage == "pay":
                card = self._resolve_object(
                    seat,
                    str(effect.get("card") or ""),
                    zones={"library"},
                    owned_only=True,
                )
                difference = max(0, int(effect.get("difference", 0)))
                requirements = {
                    **normalize_mana_bundle(None),
                    "GENERIC": difference,
                }
                if not self._cost_is_affordable(seat, requirements):
                    self.move_card(
                        card.object_id,
                        "graveyard",
                        reason="Transmute Artifact payment declined",
                        semantic_events=True,
                    )
                    self.shuffle_library(
                        seat, reason="Transmute Artifact resolved"
                    )
                    self._continue_resolution(
                        stack_ref=item.ref,
                        effects=list(remaining),
                        destination=destination,
                        note=note,
                        instruction_pointer=instruction_pointer + 1,
                    )
                    return
                effect = {
                    **dict(effect),
                    "stage": stage,
                    "_requirements": requirements,
                }
                context.update(
                    {
                        "prompt": (
                            f"Pay {difference} generic mana to put "
                            f"{card.ref} onto the battlefield?"
                        ),
                        "card": {
                            "id": card.ref,
                            "name": card.printed_name,
                        },
                        "cost": requirements,
                        "legal_actions": [
                            {
                                "id": "choose",
                                "action": "choose",
                                "choice_schema": {
                                    "field": "pay",
                                    "legal_values": [True, False],
                                },
                            }
                        ],
                    }
                )
            else:
                raise GameRuleError(
                    f"Unknown Transmute Artifact stage {stage!r}"
                )
        elif op == "choose_objects":
            selector = dict(effect.get("selector") or {})
            selector.setdefault(
                "min", int(effect.get("minimum", 1))
            )
            selector.setdefault(
                "max", int(effect.get("maximum", selector["min"]))
            )
            group = TargetGroup.from_mapping(
                selector,
                default_id="choice",
            )
            source = self.state.cards.get(
                item.source_object_id or item.card_object_id or ""
            )
            source_ref = source.ref if source else None
            options = [
                str(row["ref"])
                for row in self._target_candidate_rows(seat, group)
                if self._target_row_matches(
                    seat,
                    group,
                    row,
                    source_ref=source_ref,
                    as_target=False,
                )
            ]
            if not options:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            minimum = min(group.min_targets, len(options))
            maximum = min(group.max_targets, len(options))
            effect = {
                **dict(effect),
                "_legal_refs": options,
                "_minimum": minimum,
                "_maximum": maximum,
            }
            context.update(
                {
                    "prompt": str(
                        effect.get("prompt")
                        or "Choose the required public object(s)."
                    ),
                    "objects": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat, ref
                            ).printed_name,
                        }
                        for ref in options
                    ],
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "objects",
                                "legal_refs": options,
                                "minimum": minimum,
                                "maximum": maximum,
                                "distinct": True,
                            },
                        }
                    ],
                }
            )
        elif op == "amass":
            subtype = str(effect.get("subtype") or "Orc").strip().title()
            amount = int(effect.get("amount", 1))
            if not subtype or amount < 0:
                raise GameRuleError(
                    "Amass requires a subtype and nonnegative amount"
                )
            armies = self._controlled_subtype_refs(
                seat,
                "army",
                required_type="creature",
            )
            if not armies:
                armies = self.create_token(
                    seat,
                    name=f"{subtype} Army",
                    characteristics={
                        "type_line": f"Token Creature — {subtype} Army",
                        "colors": ["B"],
                        "power": "0",
                        "toughness": "0",
                    },
                    reason=item.label,
                )
            if len(armies) == 1:
                self._apply_amass(
                    seat,
                    armies[0],
                    subtype=subtype,
                    amount=amount,
                    reason=item.label,
                )
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {
                **dict(effect),
                "_legal_refs": armies,
                "_subtype": subtype,
                "_amount": amount,
            }
            context.update(
                {
                    "prompt": (
                        f"Choose an Army to amass {subtype}s {amount}."
                    ),
                    "objects": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat, ref, zones={"battlefield"}
                            ).printed_name,
                        }
                        for ref in armies
                    ],
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "objects",
                                "legal_refs": armies,
                                "minimum": 1,
                                "maximum": 1,
                                "distinct": True,
                            },
                        }
                    ],
                }
            )
        elif op == "sylvan_library_settle":
            hand_refs = {
                self.state.cards[object_id].ref
                for object_id in self.state.players[seat].zones["hand"]
            }
            eligible = unique_preserving_order(
                [
                    str(entry.get("object"))
                    for entry in self.state.players[seat].draw_history
                    if entry.get("turn_sequence")
                    == self.state.turn_sequence
                    and str(entry.get("object")) in hand_refs
                ]
            )
            required = min(2, len(eligible))
            if required == 0:
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {
                **dict(effect),
                "_eligible_refs": eligible,
                "_required": required,
            }
            context.update(
                {
                    "prompt": (
                        f"Choose {required} card(s) drawn this turn; for "
                        "each, pay 4 life or put it on top of your library."
                    ),
                    "objects": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat,
                                ref,
                                zones={"hand"},
                                owned_only=True,
                            ).printed_name,
                        }
                        for ref in eligible
                    ],
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "decisions",
                                "shape": "object_map",
                                "legal_refs": eligible,
                                "required": required,
                                "legal_values": [
                                    "pay_life",
                                    "top",
                                ],
                                "top_order": {
                                    "field": "top_order",
                                    "required_when_value": "top",
                                    "contains": (
                                        "exactly every ref mapped to top"
                                    ),
                                    "order": "top-first",
                                },
                                "example": {
                                    "decisions": {
                                        ref: (
                                            "pay_life"
                                            if index == 0
                                            else "top"
                                        )
                                        for index, ref in enumerate(
                                            eligible[:required]
                                        )
                                    },
                                    "top_order": list(
                                        eligible[1:required]
                                    ),
                                },
                            },
                        }
                    ],
                }
            )
        elif op == "springheart_landfall":
            source = self._resolve_object(
                seat,
                str(effect["source"]),
                zones={"battlefield"},
                controlled_only=True,
            )
            attached = self.state.cards.get(source.attached_to or "")
            requirements = self._mana_vector(
                effect.get("cost") or {"GENERIC": 1, "G": 1}
            )
            can_copy = bool(
                attached is not None
                and attached.zone == "battlefield"
                and attached.controller == seat
                and self._cost_is_affordable(seat, requirements)
            )
            if not can_copy:
                self.create_token(
                    seat,
                    name="Insect",
                    characteristics={
                        "type_line": "Token Creature — Insect",
                        "colors": ["G"],
                        "power": "1",
                        "toughness": "1",
                    },
                    reason=item.label,
                )
                self._continue_resolution(
                    stack_ref=item.ref,
                    effects=list(remaining),
                    destination=destination,
                    note=note,
                    instruction_pointer=instruction_pointer + 1,
                )
                return
            effect = {
                **dict(effect),
                "_source_ref": source.ref,
                "_attached_ref": attached.ref,
                "_requirements": requirements,
            }
            context.update(
                {
                    "prompt": (
                        "Pay {1}{G} to create a token copy of the "
                        "enchanted creature, or create a 1/1 Insect."
                    ),
                    "cost": requirements,
                    "attached_creature": attached.ref,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "pay",
                                "legal_values": [True, False],
                            },
                        }
                    ],
                }
            )
        elif op == "choose_option":
            raw_options = list(effect.get("options") or [])
            options = [
                {
                    "id": str(
                        option.get("id")
                        if isinstance(option, Mapping)
                        else option
                    ),
                    "label": str(
                        option.get("label")
                        if isinstance(option, Mapping)
                        else option
                    ),
                }
                for option in raw_options
            ]
            if not options or any(not option["id"] for option in options):
                raise GameRuleError(
                    "Semantic option choice requires nonempty options"
                )
            legal_values = [option["id"] for option in options]
            effect = {
                **dict(effect),
                "_legal_values": legal_values,
            }
            context.update(
                {
                    "prompt": str(
                        effect.get("prompt") or "Choose one option."
                    ),
                    "options": options,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "choice",
                                "legal_values": legal_values,
                            },
                        }
                    ],
                }
            )
        elif op == "scry":
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
                        "Choose which looked-at cards to put on the "
                        "bottom of your library."
                    ),
                    "objects": [
                        {
                            "id": ref,
                            "name": self._resolve_object(
                                seat,
                                ref,
                                zones={"library"},
                                owned_only=True,
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
                                "minimum": 0,
                                "maximum": len(options),
                                "destination": "library_bottom",
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
        elif op == "cumulative_upkeep":
            source = self._resolve_object(
                seat,
                str(effect["source"]),
                zones={"battlefield"},
                controlled_only=True,
            )
            source.counters["age"] = (
                int(source.counters.get("age", 0)) + 1
            )
            per_counter = self._mana_vector(
                effect.get("cost_per_counter") or {"GENERIC": 1}
            )
            age = int(source.counters["age"])
            requirements = {
                key: int(value) * age
                for key, value in per_counter.items()
            }
            payable = self._cost_is_affordable(seat, requirements)
            effect = {
                **dict(effect),
                "_requirements": requirements,
                "_source_ref": source.ref,
            }
            context.update(
                {
                    "prompt": (
                        f"Pay cumulative upkeep {requirements} or "
                        f"sacrifice {source.printed_name}."
                    ),
                    "age_counters": age,
                    "cost": requirements,
                    "payable": payable,
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "pay",
                                "legal_values": (
                                    [True, False]
                                    if payable
                                    else [False]
                                ),
                            },
                        }
                    ],
                }
            )
        elif op == "remora_tax":
            requirements = self._mana_vector(
                effect.get("cost") or {"GENERIC": 4}
            )
            payable = self._cost_is_affordable(seat, requirements)
            context.update(
                {
                    "prompt": (
                        "Pay {4} to prevent Mystic Remora's controller "
                        "from drawing a card."
                    ),
                    "cost": requirements,
                    "payable": payable,
                    "beneficiary": effect.get("beneficiary"),
                    "legal_actions": [
                        {
                            "id": "choose",
                            "action": "choose",
                            "choice_schema": {
                                "field": "pay",
                                "legal_values": (
                                    [True, False]
                                    if payable
                                    else [False]
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
        choice_effects: list[dict[str, Any]] = []
        if op == "choose_mana":
            choice = str(
                response.get("choice")
                or response.get("color")
                or response.get("mana")
                or ""
            ).upper()
            legal_colors = [
                str(value).upper()
                for value in effect.get("colors", list("WUBRGC"))
                if str(value).upper() in "WUBRGC"
                and len(str(value)) == 1
            ]
            if choice not in legal_colors:
                raise GameRuleError(
                    "Choose one of " + ", ".join(legal_colors)
                )
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
        elif op == "copy_stack_item":
            target_ref = str(effect.get("_target_stack_ref") or "")
            target_item = next(
                (
                    candidate
                    for candidate in self.state.stack
                    if candidate.ref == target_ref
                ),
                None,
            )
            if target_item is None:
                raise GameRuleError(
                    "The stack object selected for copying no longer exists"
                )
            submitted = response.get("targets")
            if submitted is None:
                selected = [
                    str(value)
                    for value in effect.get("_default_targets", [])
                ]
                grouped = copy.deepcopy(
                    dict(
                        target_item.context.get("target_groups", {})
                    )
                )
            else:
                target_program = self.semantics.get(
                    target_item.semantic_key
                )
                selected, grouped = self._validate_semantic_targets(
                    seat,
                    target_program,
                    self._normalize_target_submission(submitted),
                    modes=list(target_item.modes),
                    source_ref=self._stack_source_ref(target_item),
                    target_schema=dict(
                        effect.get("_target_schema") or {}
                    ),
                )
            self._copy_stack_item(
                controller=seat,
                target=target_item,
                targets=selected,
                target_groups=grouped,
                reason=item.label,
            )
        elif op == "retarget_stack_item":
            target_ref = str(effect.get("_target_stack_ref") or "")
            target_item = next(
                (
                    candidate
                    for candidate in self.state.stack
                    if candidate.ref == target_ref
                ),
                None,
            )
            if target_item is None:
                raise GameRuleError(
                    "The stack object selected for retargeting no "
                    "longer exists"
                )
            submitted = response.get("targets")
            if submitted is None:
                selected = [
                    str(value)
                    for value in effect.get("_default_targets", [])
                ]
                grouped = copy.deepcopy(
                    dict(
                        target_item.context.get("target_groups", {})
                    )
                )
            else:
                target_program = self.semantics.get(
                    target_item.semantic_key
                )
                selected, grouped = self._validate_semantic_targets(
                    target_item.controller,
                    target_program,
                    self._normalize_target_submission(submitted),
                    modes=list(target_item.modes),
                    source_ref=self._stack_source_ref(target_item),
                    target_schema=dict(
                        effect.get("_target_schema") or {}
                    ),
                )
            target_item.targets = list(selected)
            target_item.context["target_groups"] = copy.deepcopy(grouped)
            target_item.context["target_snapshots"] = {
                ref: self._target_snapshot(ref) for ref in selected
            }
            target_item.context["targets_revalidated"] = False
            self._log(
                seat,
                "stack.retarget",
                f"{seat} chose targets for {target_item.ref}.",
                {
                    "stack": target_item.ref,
                    "targets": list(selected),
                    "source": item.ref,
                },
                importance=2,
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
        elif op == "choose_creature_type":
            creature_type = str(
                response.get("creature_type")
                or response.get("choice")
                or ""
            ).strip()
            if (
                not creature_type
                or len(creature_type) > 48
                or not re.fullmatch(
                    r"[A-Za-z][A-Za-z '\\-]*",
                    creature_type,
                )
            ):
                raise GameRuleError(
                    "Choose a valid nonempty creature type"
                )
            source_id = item.card_object_id or item.source_object_id
            if source_id not in self.state.cards:
                raise GameRuleError(
                    "The creature-type choice has no source object"
                )
            source = self.state.cards[source_id]
            source.annotations["chosen_creature_type"] = (
                creature_type.title()
            )
            self._log(
                seat,
                "creature_type.chosen",
                (
                    f"{seat} chose {creature_type.title()} for "
                    f"{source.ref}."
                ),
                {
                    "source": source.ref,
                    "creature_type": creature_type.title(),
                },
                importance=2,
                changed_objects=[source.object_id],
            )
        elif op == "fabricate":
            choice = str(response.get("choice") or "")
            legal_values = {
                str(value)
                for value in effect.get("_legal_values") or []
            }
            if choice not in legal_values:
                raise GameRuleError(
                    "Choose an authoritative fabricate option"
                )
            amount = max(0, int(effect.get("amount", 1)))
            source = self.state.cards.get(
                item.source_object_id or item.card_object_id or ""
            )
            if choice == "counter":
                if source is None or source.zone != "battlefield":
                    raise GameRuleError(
                        "The fabricate source is no longer on the battlefield"
                    )
                source.counters["+1/+1"] = (
                    int(source.counters.get("+1/+1", 0)) + amount
                )
                self._log(
                    seat,
                    "fabricate.counter",
                    f"{source.ref} received {amount} +1/+1 counter(s).",
                    {"source": source.ref, "amount": amount},
                    importance=2,
                    changed_objects=[source.object_id],
                )
            else:
                self.create_token(
                    seat,
                    name="Servo",
                    quantity=amount,
                    characteristics={
                        "type_line": "Artifact Creature — Servo",
                        "power": "1",
                        "toughness": "1",
                        "colors": [],
                    },
                    reason=item.label,
                )
        elif op in {"populate_with_haste", "copy_all_tokens"}:
            selected = str(response.get("card") or "")
            legal = {
                str(value)
                for value in effect.get("_legal_refs") or []
            }
            if selected not in legal:
                raise GameRuleError(
                    "Selected token is not an authoritative copy option"
                )
            original = self._resolve_object(
                seat,
                selected,
                zones={"battlefield"},
                controlled_only=True,
            )
            if not original.is_token:
                raise GameRuleError("Token-copy choice requires a token")
            if op == "populate_with_haste":
                created_ref = self.create_token(
                    seat,
                    name="",
                    copy_of=original.ref,
                    temporary_keywords=["Haste"],
                    reason=item.label,
                )[0]
                created = self._resolve_object(
                    seat,
                    created_ref,
                    zones={"battlefield"},
                    controlled_only=True,
                )
                self.schedule_delayed_trigger(
                    controller=seat,
                    label=f"Sacrifice {created.ref}",
                    event_kind="step.begin",
                    condition={
                        "phase": "ending",
                        "step": "end_step",
                    },
                    stack_template={
                        "label": f"Sacrifice {created.ref}",
                        "semantic_key": "builtin:sacrifice-source",
                    },
                    source_object_id=created.object_id,
                    once=True,
                )
            else:
                characteristics = self._copyable_characteristics(
                    original
                )
                changed: list[str] = []
                for object_id in self.state.players[
                    seat
                ].zones["battlefield"]:
                    token = self.state.cards[object_id]
                    if (
                        token.controller != seat
                        or not token.is_token
                        or token.object_id == original.object_id
                    ):
                        continue
                    token.annotations["copy_overrides"] = copy.deepcopy(
                        characteristics
                    )
                    changed.append(token.object_id)
                self._log(
                    seat,
                    "token.copy_all",
                    (
                        f"{len(changed)} other token(s) became copies of "
                        f"{original.ref}."
                    ),
                    {
                        "source": item.ref,
                        "chosen_token": original.ref,
                        "objects": [
                            self.state.cards[object_id].ref
                            for object_id in changed
                        ],
                    },
                    importance=2,
                    changed_objects=changed,
                )
        elif op == "put_land_from_hand":
            selected = str(response.get("card") or "")
            legal = {
                str(value)
                for value in effect.get("_legal_refs") or []
            }
            if selected and selected not in legal:
                raise GameRuleError(
                    "Selected card is not an authoritative land option"
                )
            if selected:
                card = self._resolve_object(
                    seat,
                    selected,
                    zones={"hand"},
                    owned_only=True,
                )
                record = self.card_record(card)
                if record is None or not record.is_land:
                    raise GameRuleError(
                        "Selected object is no longer a land card in hand"
                    )
                tapped = self._land_enters_tapped(seat, record)
                self.move_card(
                    card.object_id,
                    "battlefield",
                    controller=seat,
                    tapped=tapped,
                    reason=item.label,
                    semantic_events=True,
                )
                _, subtypes, _ = self._type_parts(record.type_line)
                if (
                    "cave" in subtypes
                    and int(effect.get("cave_life", 0))
                ):
                    self.apply_effect(
                        {
                            "op": "life",
                            "player": seat,
                            "delta": int(effect["cave_life"]),
                            "reason": item.label,
                        },
                        actor=seat,
                    )
                self._log(
                    seat,
                    "land.put",
                    f"{seat} put {card.ref} onto the battlefield.",
                    {
                        "card": card.ref,
                        "tapped": tapped,
                        "source": item.ref,
                    },
                    importance=2,
                    changed_objects=[card.object_id],
                    changed_players=[seat],
                )
        elif op == "put_artifact_from_hand":
            selected = str(response.get("card") or "")
            legal = {
                str(value)
                for value in effect.get("_legal_refs") or []
            }
            if selected and selected not in legal:
                raise GameRuleError(
                    "Selected card is not an authoritative artifact option"
                )
            if selected:
                card = self._resolve_object(
                    seat,
                    selected,
                    zones={"hand"},
                    owned_only=True,
                )
                types, _, _ = self._type_parts(
                    str(
                        self._effective_card_data(card).get(
                            "type_line"
                        )
                        or ""
                    )
                )
                if "artifact" not in types:
                    raise GameRuleError(
                        "Selected object is no longer an artifact card "
                        "in hand"
                    )
                self.move_card(
                    card.object_id,
                    "battlefield",
                    controller=seat,
                    reason=item.label,
                    semantic_events=True,
                )
                self._log(
                    seat,
                    "artifact.put",
                    (
                        f"{seat} put {card.ref} onto the battlefield "
                        "from hand."
                    ),
                    {
                        "card": card.ref,
                        "source": item.ref,
                    },
                    importance=2,
                    changed_objects=[card.object_id],
                    changed_players=[seat],
                )
        elif op == "explore":
            choice = str(response.get("choice") or "")
            if choice not in {"graveyard", "top"}:
                raise GameRuleError(
                    "Explore requires choosing graveyard or top"
                )
            top_ref = str(effect.get("_top_ref") or "")
            top = self._resolve_object(
                seat,
                top_ref,
                zones={"library"},
                owned_only=True,
            )
            if (
                not self.state.players[seat].zones["library"]
                or self.state.players[seat].zones["library"][-1]
                != top.object_id
            ):
                raise GameRuleError(
                    "The revealed explore card is no longer on top"
                )
            if choice == "graveyard":
                self.move_card(
                    top.object_id,
                    "graveyard",
                    reason="explore",
                    semantic_events=True,
                )
            self._log(
                seat,
                "explore.complete",
                (
                    f"{seat} put {top.ref} into their graveyard."
                    if choice == "graveyard"
                    else f"{seat} left {top.ref} on top of their library."
                ),
                {
                    "player": seat,
                    "card": top.ref,
                    "destination": choice,
                    "explorer": effect.get("_explorer_ref"),
                },
                importance=2,
                changed_objects=[top.object_id],
                changed_players=[seat],
            )
        elif op == "fomori_vault":
            selected = str(response.get("card") or "")
            looked = [
                str(value)
                for value in effect.get("_looked_refs") or []
            ]
            if selected not in looked:
                raise GameRuleError(
                    "Choose one of the cards looked at by Fomori Vault"
                )
            library = self.state.players[seat].zones["library"]
            cards = [
                self._resolve_object(
                    seat,
                    ref,
                    zones={"library"},
                    owned_only=True,
                )
                for ref in looked
            ]
            if any(card.object_id not in library for card in cards):
                raise GameRuleError(
                    "A looked-at Fomori Vault card left the library"
                )
            chosen = next(card for card in cards if card.ref == selected)
            for card in cards:
                if card is not chosen:
                    library.remove(card.object_id)
            self.move_card(
                chosen.object_id,
                "hand",
                reason="Fomori Vault selection",
                log=False,
            )
            bottom = [
                card.object_id for card in cards if card is not chosen
            ]
            randomizer = random.Random(
                f"{self.state.config.seed}|{seat}|fomori-vault|"
                f"{self.state.event_sequence}|{item.ref}"
            )
            randomizer.shuffle(bottom)
            library[0:0] = bottom
            for object_id in bottom:
                card = self.state.cards[object_id]
                card.known_to = [seat]
                card.revealed_to = []
            self._log(
                seat,
                "fomori_vault.select",
                (
                    f"{seat} put one looked-at card into hand and "
                    f"{len(bottom)} on the bottom at random."
                ),
                {
                    "chosen": chosen.ref,
                    "bottom_count": len(bottom),
                    "looked_count": len(looked),
                },
                visibility=[seat, "analyst"],
                importance=2,
                changed_objects=[card.object_id for card in cards],
                changed_players=[seat],
            )
        elif op == "discard_draw_up_to":
            selected = [
                str(value) for value in response.get("cards", [])
            ]
            legal = {
                str(value)
                for value in effect.get("_legal_refs") or []
            }
            maximum = int(effect.get("_maximum", 0))
            if (
                len(selected) != len(set(selected))
                or len(selected) > maximum
                or any(value not in legal for value in selected)
            ):
                raise GameRuleError(
                    "Discard selection must contain up to the offered "
                    "number of distinct hand cards"
                )
            cards = [
                self._resolve_object(
                    seat,
                    ref,
                    zones={"hand"},
                    owned_only=True,
                )
                for ref in selected
            ]
            if cards:
                self._move_cards_simultaneously(
                    [
                        (card.object_id, "graveyard")
                        for card in cards
                    ],
                    reason=item.label,
                    log=False,
                )
                choice_effects = [
                    {
                        "op": "draw",
                        "player": seat,
                        "count": len(cards),
                        "private": True,
                        "reason": item.label,
                    }
                ]
            self._log(
                seat,
                "daretti.discard_draw",
                (
                    f"{seat} discarded {len(cards)} card(s) and will "
                    "draw that many."
                ),
                {
                    "count": len(cards),
                    "objects": [card.ref for card in cards],
                },
                visibility=[seat, "analyst"],
                importance=2,
                changed_objects=[card.object_id for card in cards],
                changed_players=[seat],
            )
        elif op == "daretti_exchange":
            selected = str(response.get("card") or "")
            legal = {
                str(value)
                for value in effect.get("_legal_refs") or []
            }
            if selected not in legal:
                raise GameRuleError(
                    "Choose one of the authoritative artifact options"
                )
            sacrificed = self._resolve_object(
                seat,
                selected,
                zones={"battlefield"},
                controlled_only=True,
            )
            if "artifact" not in self._type_parts(
                str(
                    self._effective_card_data(sacrificed).get(
                        "type_line"
                    )
                    or ""
                )
            )[0]:
                raise GameRuleError(
                    "Daretti's selected permanent is no longer an artifact"
                )
            self.move_card(
                sacrificed.object_id,
                "graveyard",
                reason=item.label,
                semantic_events=True,
            )
            target_ref = str(effect.get("card") or "")
            try:
                target = self._resolve_object(
                    seat,
                    target_ref,
                    zones={"graveyard"},
                    owned_only=True,
                )
            except GameRuleError:
                target = None
            if (
                target is not None
                and "artifact"
                in self._type_parts(
                    str(
                        self._effective_card_data(target).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
            ):
                self.move_card(
                    target.object_id,
                    "battlefield",
                    controller=seat,
                    reason=item.label,
                    semantic_events=True,
                )
            self._log(
                seat,
                "daretti.exchange",
                f"{seat} sacrificed {sacrificed.ref} for Daretti.",
                {
                    "sacrificed": sacrificed.ref,
                    "returned": target.ref if target is not None else None,
                },
                importance=2,
                changed_objects=[
                    sacrificed.object_id,
                    *(
                        [target.object_id]
                        if target is not None
                        else []
                    ),
                ],
                changed_players=[seat],
            )
        elif op == "transmute_artifact":
            stage = str(effect.get("stage") or "sacrifice")
            legal = {
                str(value)
                for value in effect.get("_legal_refs") or []
            }
            if stage == "sacrifice":
                selected = str(response.get("card") or "")
                if selected not in legal:
                    raise GameRuleError(
                        "Choose one of the authoritative artifact options"
                    )
                sacrificed = self._resolve_object(
                    seat,
                    selected,
                    zones={"battlefield"},
                    controlled_only=True,
                )
                types, _, _ = self._type_parts(
                    str(
                        self._effective_card_data(sacrificed).get(
                            "type_line"
                        )
                        or ""
                    )
                )
                if "artifact" not in types:
                    raise GameRuleError(
                        "Transmute Artifact requires an artifact"
                    )
                mana_value = int(
                    float(
                        self._effective_card_data(sacrificed).get(
                            "mana_value", 0
                        )
                        or 0
                    )
                )
                self.move_card(
                    sacrificed.object_id,
                    "graveyard",
                    reason=item.label,
                    semantic_events=True,
                )
                choice_effects = [
                    {
                        "op": "transmute_artifact",
                        "stage": "search",
                        "sacrificed_mana_value": mana_value,
                    }
                ]
            elif stage == "search":
                selected = response.get("card")
                if selected in {"", None}:
                    selected = None
                if selected is not None and str(selected) not in legal:
                    raise GameRuleError(
                        "Selected Transmute Artifact result is not legal"
                    )
                if selected is None:
                    self.shuffle_library(
                        seat, reason="Transmute Artifact resolved"
                    )
                else:
                    found = self._resolve_object(
                        seat,
                        str(selected),
                        zones={"library"},
                        owned_only=True,
                    )
                    found_value = int(
                        float(
                            self._effective_card_data(found).get(
                                "mana_value", 0
                            )
                            or 0
                        )
                    )
                    sacrificed_value = int(
                        effect.get("sacrificed_mana_value", 0)
                    )
                    difference = max(
                        0, found_value - sacrificed_value
                    )
                    if difference == 0:
                        self.move_card(
                            found.object_id,
                            "battlefield",
                            controller=seat,
                            reason=item.label,
                            semantic_events=True,
                        )
                        self.shuffle_library(
                            seat,
                            reason="Transmute Artifact resolved",
                        )
                    else:
                        choice_effects = [
                            {
                                "op": "transmute_artifact",
                                "stage": "pay",
                                "card": found.ref,
                                "difference": difference,
                            }
                        ]
            elif stage == "pay":
                found = self._resolve_object(
                    seat,
                    str(effect.get("card") or ""),
                    zones={"library"},
                    owned_only=True,
                )
                pay = bool(response.get("pay", False))
                requirements = self._mana_vector(
                    effect.get("_requirements") or {}
                )
                if pay:
                    if not self._cost_is_affordable(
                        seat, requirements
                    ):
                        raise GameRuleError(
                            "Transmute Artifact payment is no longer payable"
                        )
                    self._pay_for_cost(
                        seat, requirements, {"pay": "auto"}
                    )
                self.move_card(
                    found.object_id,
                    "battlefield" if pay else "graveyard",
                    controller=seat if pay else None,
                    reason=item.label,
                    semantic_events=True,
                )
                self.shuffle_library(
                    seat, reason="Transmute Artifact resolved"
                )
            else:
                raise GameRuleError(
                    f"Unknown Transmute Artifact stage {stage!r}"
                )
        elif op == "choose_objects":
            selected = [
                str(value)
                for value in response.get(
                    "objects", response.get("cards", [])
                )
            ]
            legal = set(effect.get("_legal_refs") or [])
            minimum = int(effect.get("_minimum", 0))
            maximum = int(effect.get("_maximum", len(legal)))
            if (
                len(selected) != len(set(selected))
                or len(selected) < minimum
                or len(selected) > maximum
                or any(value not in legal for value in selected)
            ):
                raise GameRuleError(
                    "Object choices do not satisfy the authoritative "
                    "selection constraints"
                )
            for continuation_effect in effect.get("then") or []:
                next_effect = dict(continuation_effect)
                next_op = str(next_effect.get("op") or "")
                if next_op in {
                    "move_selected",
                    "sacrifice_selected",
                }:
                    destination_name = (
                        "graveyard"
                        if next_op == "sacrifice_selected"
                        else str(
                            next_effect.get("destination")
                            or "graveyard"
                        )
                    )
                    cards = [
                        self._resolve_object(seat, value)
                        for value in selected
                    ]
                    self._move_cards_simultaneously(
                        [
                            (card.object_id, destination_name)
                            for card in cards
                        ],
                        reason=str(
                            next_effect.get("reason") or item.label
                        ),
                        log=True,
                    )
                elif next_op == "add_counter_selected":
                    self.apply_effect(
                        {
                            **next_effect,
                            "cards": selected,
                        },
                        actor=seat,
                    )
                elif next_op == "life_if_selected_subtype":
                    subtype = str(
                        next_effect.get("subtype") or ""
                    ).casefold()
                    amount = int(next_effect.get("amount", 0))
                    matching = any(
                        subtype
                        in self._type_parts(
                            str(
                                self._effective_card_data(
                                    self._resolve_object(seat, value)
                                ).get("type_line")
                                or ""
                            )
                        )[1]
                        for value in selected
                    )
                    if matching and amount:
                        self.apply_effect(
                            {
                                "op": "life",
                                "player": seat,
                                "delta": amount,
                                "reason": str(
                                    next_effect.get("reason")
                                    or item.label
                                ),
                            },
                            actor=seat,
                        )
                else:
                    raise GameRuleError(
                        f"Unsupported object-choice continuation {next_op!r}"
                    )
            self._log(
                seat,
                "semantic.objects.chosen",
                f"{seat} chose {len(selected)} object(s) for {item.label}.",
                {"stack": item.ref, "objects": selected},
                importance=1,
            )
        elif op == "amass":
            selected = [
                str(value)
                for value in response.get(
                    "objects", response.get("cards", [])
                )
            ]
            legal = set(effect.get("_legal_refs") or [])
            if len(selected) != 1 or selected[0] not in legal:
                raise GameRuleError("Choose exactly one legal Army to amass")
            self._apply_amass(
                seat,
                selected[0],
                subtype=str(effect.get("_subtype") or "Orc"),
                amount=int(effect.get("_amount", 1)),
                reason=item.label,
            )
        elif op == "sylvan_library_settle":
            decisions = {
                str(key): str(value)
                for key, value in dict(
                    response.get("decisions") or {}
                ).items()
            }
            eligible = {
                str(value)
                for value in effect.get("_eligible_refs") or []
            }
            required = int(effect.get("_required", 0))
            if (
                len(decisions) != required
                or any(ref not in eligible for ref in decisions)
                or any(
                    value not in {"pay_life", "top"}
                    for value in decisions.values()
                )
            ):
                raise GameRuleError(
                    "Sylvan Library requires an exact decision for each "
                    "selected card"
                )
            life_cards = [
                ref
                for ref, value in decisions.items()
                if value == "pay_life"
            ]
            life_cost = 4 * len(life_cards)
            if self.state.players[seat].life < life_cost:
                raise GameRuleError(
                    "The selected Sylvan Library life payment is not payable"
                )
            top_cards = [
                ref
                for ref, value in decisions.items()
                if value == "top"
            ]
            top_order = [
                str(value)
                for value in response.get("top_order", [])
            ]
            if set(top_order) != set(top_cards) or len(top_order) != len(
                top_cards
            ):
                raise GameRuleError(
                    "Sylvan Library top_order must list each card being "
                    "returned exactly once"
                )
            top_ids: list[str] = []
            for ref in top_order:
                card = self._resolve_object(
                    seat,
                    ref,
                    zones={"hand"},
                    owned_only=True,
                )
                self.move_card(
                    card.object_id,
                    "library",
                    position="top",
                    reason="Sylvan Library",
                    log=False,
                )
                # Assemble the simultaneous ordered return after each move
                # has crossed the canonical CR 400.7 identity boundary.
                self.state.players[seat].zones["library"].remove(
                    card.object_id
                )
                top_ids.append(card.object_id)
            self.state.players[seat].zones["library"].extend(
                reversed(top_ids)
            )
            self.state.players[seat].life -= life_cost
            self._log(
                seat,
                "sylvan_library.settle",
                (
                    f"{seat} paid {life_cost} life and returned "
                    f"{len(top_ids)} card(s) to the top of their library."
                ),
                {
                    "paid_life_for": life_cards,
                    "life_paid": life_cost,
                    "top_order": top_order,
                },
                visibility=[seat, "analyst"],
                importance=2,
                changed_objects=top_ids,
                changed_players=[seat],
            )
        elif op == "springheart_landfall":
            pay = bool(response.get("pay", False))
            if pay:
                requirements = self._mana_vector(
                    effect.get("_requirements") or {}
                )
                if not self._cost_is_affordable(seat, requirements):
                    raise GameRuleError(
                        "Springheart Nantuko's payment is no longer payable"
                    )
                source = self._resolve_object(
                    seat,
                    str(effect.get("_source_ref") or ""),
                    zones={"battlefield"},
                    controlled_only=True,
                )
                attached = self._resolve_object(
                    seat,
                    str(effect.get("_attached_ref") or ""),
                    zones={"battlefield"},
                    controlled_only=True,
                )
                if source.attached_to != attached.object_id:
                    raise GameRuleError(
                        "Springheart Nantuko is no longer attached to "
                        "that creature"
                    )
                self._pay_for_cost(
                    seat,
                    requirements,
                    {"pay": "auto"},
                )
                self.create_token(
                    seat,
                    name="",
                    copy_of=attached.ref,
                    reason=item.label,
                )
            else:
                self.create_token(
                    seat,
                    name="Insect",
                    characteristics={
                        "type_line": "Token Creature — Insect",
                        "colors": ["G"],
                        "power": "1",
                        "toughness": "1",
                    },
                    reason=item.label,
                )
        elif op == "choose_option":
            choice = str(
                response.get("choice")
                or response.get("option")
                or ""
            )
            legal_values = {
                str(value)
                for value in effect.get("_legal_values") or []
            }
            if choice not in legal_values:
                raise GameRuleError(
                    "Choose one of the authoritative option values"
                )
            by_choice = effect.get("then_by_choice") or {}
            choice_effects = [
                dict(value)
                for value in by_choice.get(choice, [])
            ]
            self._log(
                seat,
                "semantic.option.chosen",
                f"{seat} chose {choice} for {item.label}.",
                {
                    "stack": item.ref,
                    "choice": choice,
                },
                importance=1,
            )
        elif op == "scry":
            looked = [
                str(value)
                for value in effect.get("_looked_refs", [])
            ]
            bottom = [
                str(value)
                for value in response.get("cards", [])
            ]
            if (
                len(bottom) != len(set(bottom))
                or any(value not in looked for value in bottom)
            ):
                raise GameRuleError(
                    "Scry bottom choices must be distinct looked-at cards"
                )
            library = self.state.players[seat].zones["library"]
            bottom_ids: list[str] = []
            for ref in bottom:
                card = self._resolve_object(
                    seat,
                    ref,
                    zones={"library"},
                    owned_only=True,
                )
                if card.object_id not in library:
                    raise GameRuleError(
                        "A scry card left the library before the choice"
                    )
                library.remove(card.object_id)
                bottom_ids.append(card.object_id)
            for object_id in reversed(bottom_ids):
                library.insert(0, object_id)
            self._log(
                seat,
                "library.scry",
                f"{seat} put {len(bottom_ids)} card(s) on the bottom.",
                {
                    "count": len(looked),
                    "bottom_count": len(bottom_ids),
                },
                visibility=[seat, "analyst"],
                importance=1,
                changed_objects=bottom_ids,
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
        elif op == "cumulative_upkeep":
            source_ref = str(effect.get("_source_ref") or "")
            source = self._resolve_object(
                seat,
                source_ref,
                zones={"battlefield"},
                controlled_only=True,
            )
            requirements = self._mana_vector(
                effect.get("_requirements") or {}
            )
            if bool(response.get("pay", False)):
                if not self._cost_is_affordable(seat, requirements):
                    raise GameRuleError(
                        "The cumulative upkeep cost is no longer payable"
                    )
                self._pay_for_cost(
                    seat,
                    requirements,
                    {"pay": "auto"},
                )
                self._log(
                    seat,
                    "cumulative_upkeep.paid",
                    f"{seat} paid cumulative upkeep for {source.ref}.",
                    {
                        "source": source.ref,
                        "cost": requirements,
                        "age_counters": source.counters.get("age", 0),
                    },
                    importance=2,
                    changed_objects=[source.object_id],
                    changed_players=[seat],
                )
            else:
                self.move_card(
                    source.object_id,
                    "graveyard",
                    reason="cumulative upkeep not paid",
                    semantic_events=True,
                )
        elif op == "remora_tax":
            requirements = self._mana_vector(
                effect.get("cost") or {"GENERIC": 4}
            )
            if bool(response.get("pay", False)):
                if not self._cost_is_affordable(seat, requirements):
                    raise GameRuleError(
                        "The Mystic Remora payment is no longer payable"
                    )
                self._pay_for_cost(
                    seat,
                    requirements,
                    {"pay": "auto"},
                )
                self._log(
                    seat,
                    "mystic_remora.paid",
                    f"{seat} paid for Mystic Remora.",
                    {"cost": requirements, "stack": item.ref},
                    importance=2,
                    changed_players=[seat],
                )
            else:
                beneficiary = str(effect.get("beneficiary") or "")
                if beneficiary in self.active_seats:
                    choice_effects = [
                        {
                            "op": "choose_option",
                            "player": beneficiary,
                            "prompt": "Draw a card with Mystic Remora?",
                            "options": [
                                {"id": "draw", "label": "Draw a card"},
                                {
                                    "id": "decline",
                                    "label": "Do not draw",
                                },
                            ],
                            "then_by_choice": {
                                "draw": [
                                    {
                                        "op": "draw",
                                        "player": beneficiary,
                                        "count": 1,
                                        "private": True,
                                    }
                                ],
                                "decline": [],
                            },
                        }
                    ]
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
        if choice_effects:
            remaining = [*choice_effects, *remaining]
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

    def _controlled_subtype_refs(
        self,
        seat: str,
        subtype: str,
        *,
        required_type: str | None = None,
    ) -> list[str]:
        wanted = subtype.casefold()
        wanted_type = (
            required_type.casefold() if required_type is not None else None
        )
        matching: list[str] = []
        for object_id in self.state.players[seat].zones["battlefield"]:
            card = self.state.cards[object_id]
            if card.controller != seat or card.phased_out:
                continue
            types, subtypes, _ = self._type_parts(
                str(self._effective_card_data(card).get("type_line") or "")
            )
            if wanted in subtypes and (
                wanted_type is None or wanted_type in types
            ):
                matching.append(card.ref)
        return matching

    def _apply_amass(
        self,
        seat: str,
        army_ref: str,
        *,
        subtype: str,
        amount: int,
        reason: str,
    ) -> None:
        army = self._resolve_object(
            seat,
            army_ref,
            zones={"battlefield"},
            controlled_only=True,
        )
        _, subtypes, _ = self._type_parts(
            str(self._effective_card_data(army).get("type_line") or "")
        )
        if "army" not in subtypes:
            raise GameRuleError("Amass requires an Army creature")
        normalized_subtype = subtype.strip().title()
        if normalized_subtype.casefold() not in subtypes:
            self.apply_effect(
                {
                    "op": "add_subtype",
                    "card": army.ref,
                    "subtype": normalized_subtype,
                    "reason": reason,
                },
                actor=seat,
            )
        if amount:
            self.apply_effect(
                {
                    "op": "add_counter_selected",
                    "cards": [army.ref],
                    "counter": "+1/+1",
                    "amount": amount,
                    "reason": reason,
                },
                actor=seat,
            )
        self._log(
            seat,
            "keyword.amass",
            f"{seat} amassed {normalized_subtype}s {amount} onto {army.ref}.",
            {
                "army": army.ref,
                "subtype": normalized_subtype,
                "amount": amount,
                "reason": reason,
            },
            importance=2,
            changed_objects=[army.object_id],
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
            "shape": "ref_array",
            "element_type": "string",
            "minimum": minimum_choice,
            "maximum": maximum,
            "legal_refs": [option["id"] for option in options],
            "rules_may_fail_to_find": rules_may_fail,
            "example": {
                "search_cards": (
                    [options[0]["id"]]
                    if options and maximum > 0
                    else []
                ),
            },
        }
        if entry_choice and str(effect.get("destination")) == "battlefield":
            choice_schema["entry_pay_life"] = "boolean"
            choice_schema["example"]["entry_pay_life"] = False
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
        explicit_search_cards = response.get("search_cards")
        if explicit_search_cards is not None and (
            not isinstance(explicit_search_cards, Sequence)
            or isinstance(explicit_search_cards, (str, bytes))
            or any(
                not isinstance(value, str)
                for value in explicit_search_cards
            )
        ):
            raise GameRuleError(
                "search_cards must be an array of card-ref strings from "
                "choice_schema.legal_refs"
            )
        raw_values = (
            explicit_search_cards
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
        position: str | int = effect.get(
            "destination_position",
            "top",
        )
        if position is None or position == "":
            position = "top"
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
                and tapped
                and self._lands_enter_untapped_for(seat)
            ):
                tapped = False
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
        if self.state.players[item.controller].stats.get(
            "spells_cant_be_countered_until_end"
        ):
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
        self._maybe_sacrifice_completed_saga(item)
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

    def _maybe_sacrifice_completed_saga(
        self, chapter_item: StackItem
    ) -> None:
        program = self.semantics.get(chapter_item.semantic_key)
        if (
            program is None
            or "saga_final_chapter" not in program.coverage
            or chapter_item.source_object_id not in self.state.cards
        ):
            return
        saga = self.state.cards[chapter_item.source_object_id]
        if saga.zone != "battlefield":
            return
        if any(
            item.source_object_id == saga.object_id
            and (
                (candidate := self.semantics.get(item.semantic_key))
                is not None
                and "saga_chapter" in candidate.coverage
            )
            for item in self.state.stack
        ):
            return
        self.move_card(
            saga.object_id,
            "graveyard",
            reason="Saga final chapter left the stack",
            semantic_events=True,
        )

    # ------------------------------------------------------------------
    # Replacement/prevention ordering during resolution
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

    def _attack_declaration_error(
        self,
        card: CardInstance,
        active: str,
    ) -> str | None:
        data = self._effective_card_data(card)
        card_types, _, _ = self._type_parts(
            str(data.get("type_line") or "")
        )
        if card.controller != active:
            return f"{card.ref} is not controlled by {active}"
        if card.phased_out:
            return f"{card.ref} is phased out"
        if "creature" not in card_types:
            return f"{card.ref} is not a creature"
        if "battle" in card_types:
            return f"{card.ref} cannot attack because it is a Battle"
        if card.tapped:
            return f"{card.ref} is tapped"
        if (
            self._is_summoning_sick(card)
            and "Haste" not in data.get("keywords", [])
        ):
            return f"{card.ref} is summoning sick"
        if DEFENDER in normalized_keywords(data.get("keywords", [])):
            return f"{card.ref} has defender and cannot attack"
        return None

    def _combat_keywords(self, card: CardInstance) -> frozenset[str]:
        return normalized_keywords(
            self._effective_card_data(card).get("keywords", [])
        )

    def _combat_damage_participants(self) -> list[CardInstance]:
        object_ids = set(self.state.combat.attackers)
        object_ids.update(
            blocker_id
            for blocker_ids in self.state.combat.blockers.values()
            for blocker_id in blocker_ids
        )
        participants: list[CardInstance] = []
        for object_id in sorted(object_ids):
            card = self.state.cards.get(object_id)
            if (
                card is None
                or card.zone != "battlefield"
                or card.phased_out
            ):
                continue
            card_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if "creature" in card_types and "battle" not in card_types:
                participants.append(card)
        return participants

    def _initialize_combat_damage_steps(self) -> None:
        combat = self.state.combat
        if combat.damage_step_initialized:
            return
        keywords_by_object = {
            card.object_id: self._combat_keywords(card)
            for card in self._combat_damage_participants()
        }
        combat.first_strike_step = first_strike_step_required(
            keywords_by_object
        )
        combat.ordinary_second_damage_combatants = sorted(
            ordinary_second_step_combatants(keywords_by_object)
            if combat.first_strike_step
            else ()
        )
        combat.damage_step_initialized = True

    def _assigns_combat_damage_this_step(
        self,
        card: CardInstance,
    ) -> bool:
        combat = self.state.combat
        return assigns_in_damage_step(
            object_id=card.object_id,
            current_keywords=self._combat_keywords(card),
            step_index=combat.damage_step_index,
            first_strike_step=combat.first_strike_step,
            ordinary_second_step=frozenset(
                combat.ordinary_second_damage_combatants
            ),
        )

    def _protection_colors(self, card: CardInstance) -> set[str]:
        oracle = str(
            self._effective_card_data(card).get("oracle_text") or ""
        ).casefold()
        color_symbols = {
            "white": "W",
            "blue": "U",
            "black": "B",
            "red": "R",
            "green": "G",
        }
        return {
            symbol
            for name, symbol in color_symbols.items()
            if re.search(rf"protection from (?:[a-z ]+ and )?{name}", oracle)
        }

    def _source_colors_for_ref(self, source_ref: str | None) -> set[str]:
        if not source_ref:
            return set()
        card = next(
            (
                candidate
                for candidate in self.state.cards.values()
                if candidate.ref == source_ref
            ),
            None,
        )
        if card is None:
            stack_item = next(
                (
                    candidate
                    for candidate in self.state.stack
                    if candidate.ref == source_ref
                ),
                None,
            )
            if stack_item is not None:
                source_id = (
                    stack_item.card_object_id
                    or stack_item.source_object_id
                )
                card = (
                    self.state.cards.get(source_id)
                    if source_id
                    else None
                )
        if card is None:
            return set()
        return {
            str(color).upper()
            for color in self._effective_card_data(card).get("colors", [])
        }

    def _can_block(
        self,
        attacker: CardInstance,
        blocker: CardInstance,
    ) -> tuple[bool, str | None]:
        attacker_data = self._effective_card_data(attacker)
        blocker_data = self._effective_card_data(blocker)
        attacker_keywords = {
            str(value).casefold()
            for value in attacker_data.get("keywords", [])
        }
        blocker_keywords = {
            str(value).casefold()
            for value in blocker_data.get("keywords", [])
        }
        blocker_types, _, _ = self._type_parts(
            str(blocker_data.get("type_line") or "")
        )
        if "battle" in blocker_types:
            return False, "blocker_is_battle"
        by_ref = {card.ref: card for card in self.state.cards.values()}
        for source in sorted(
            self.state.cards.values(), key=lambda value: value.ref
        ):
            if source.zone != "battlefield" or source.phased_out:
                continue
            for line in self._combat_oracle_lines(source):
                parsed = parse_declaration_restriction_line(line)
                template = parsed.template
                if (
                    not parsed.exact
                    or template is None
                    or "block" not in template.declarations
                    or template.mode != "prohibit"
                ):
                    continue
                applies = {
                    "self": source.object_id == blocker.object_id,
                    "attached": source.attached_to == blocker.object_id,
                    "attached_option": (
                        source.attached_to == attacker.object_id
                    ),
                    "source_opponents": (
                        blocker.controller != source.controller
                    ),
                    "source_option": source.object_id == attacker.object_id,
                    "global": True,
                }[template.scope]
                if not applies:
                    continue
                if not self._declaration_option_matches_relation(
                    template,
                    kind="block",
                    source=source,
                    option=attacker.ref,
                    by_ref=by_ref,
                ):
                    continue
                if template.condition is not None and (
                    self._declaration_condition_holds(
                        template.condition,
                        kind="block",
                        source=source,
                        variable=blocker.ref,
                        option=attacker.ref,
                        by_ref=by_ref,
                    )
                    != template.applies_when_condition
                ):
                    continue
                if (
                    self._matches_declaration_predicate(
                        blocker, template.subject, source=source
                    )
                    and self._matches_declaration_predicate(
                        attacker, template.opposing, source=source
                    )
                ):
                    return (
                        False,
                        f"declaration_restriction:{template.template_id}",
                    )
        if "shadow" in attacker_keywords and "shadow" not in blocker_keywords:
            return False, "attacker_has_shadow"
        if "shadow" in blocker_keywords and "shadow" not in attacker_keywords:
            return False, "blocker_has_shadow"
        if (
            "flying" in attacker_keywords
            and not blocker_keywords.intersection({"flying", "reach"})
        ):
            return False, "attacker_has_flying"
        blocker_colors = {
            str(color).upper()
            for color in blocker_data.get("colors", [])
        }
        if self._protection_colors(attacker).intersection(blocker_colors):
            return False, "attacker_has_protection"
        return True, None

    def _combat_oracle_text(self, card: CardInstance) -> str:
        return " ".join(self._combat_oracle_lines(card))

    def _active_goad_designations(
        self,
        card: CardInstance,
    ) -> tuple[GoadDesignation, ...]:
        return tuple(
            designation
            for designation in card.goaded_by
            if designation.player in self.state.players
            and self.state.players[
                designation.player
            ].turns_begun < designation.expires_at_turns_begun
        )

    def _goad_prohibition_source(
        self,
        card: CardInstance,
    ) -> CardInstance | None:
        """Return an active exact static source that forbids goading."""

        for source in self.state.cards.values():
            if (
                source.zone != "battlefield"
                or source.phased_out
                or source.controller != card.controller
            ):
                continue
            oracle = " ".join(
                str(
                    self._effective_card_data(source).get("oracle_text")
                    or ""
                )
                .casefold()
                .split()
            )
            if "creatures you control can't be goaded." in oracle:
                return source
        return None

    def _combat_oracle_lines(
        self,
        card: CardInstance,
    ) -> tuple[str, ...]:
        """Return source-local normalized Oracle lines for combat grammar."""

        lines: list[str] = []
        for raw_line in str(
            self._effective_card_data(card).get("oracle_text") or ""
        ).splitlines():
            line = normalized_oracle_line(
                raw_line,
                card_name=card.printed_name,
            )
            if not line:
                continue
            lines.append(line)
        return tuple(lines)

    @staticmethod
    def _declaration_cost(
        *,
        cost_id: str,
        variable: str,
        option: str,
        payer: str,
        mana: tuple[tuple[str, int], ...],
        source: CardInstance,
        label: str,
    ) -> DeclarationCost:
        return DeclarationCost(
            cost_id=cost_id,
            variable=variable,
            option=option,
            payer=payer,
            mana=mana,
            source=source.ref,
            label=label,
        )

    def _declaration_costs(
        self,
        kind: str,
        payer: str,
        domains: Mapping[str, Sequence[str]],
    ) -> tuple[
        tuple[DeclarationCost, ...],
        tuple[tuple[CardInstance, str], ...],
    ]:
        """Derive a represented CR 508.1h or 509.1d locked-cost set."""

        costs: list[DeclarationCost] = []
        unresolved: list[tuple[CardInstance, str]] = []
        by_ref = {card.ref: card for card in self.state.cards.values()}
        for source in sorted(
            self.state.cards.values(), key=lambda value: value.ref
        ):
            if source.zone != "battlefield" or source.phased_out:
                continue
            for line_index, line in enumerate(
                self._combat_oracle_lines(source)
            ):
                parsed = parse_declaration_cost_line(line)
                if kind not in parsed.declarations:
                    continue

                def source_planeswalker(option: str) -> bool:
                    target = by_ref.get(option)
                    if (
                        target is None
                        or target.controller != source.controller
                    ):
                        return False
                    target_types, _, _ = self._type_parts(
                        str(
                            self._effective_card_data(target).get(
                                "type_line"
                            )
                            or ""
                        )
                    )
                    return "planeswalker" in target_types

                selections: list[tuple[str, str]] = []
                if parsed.scope == "self" and source.ref in domains:
                    selections.extend(
                        (source.ref, str(option))
                        for option in domains[source.ref]
                    )
                elif parsed.scope == "attached":
                    attached = self.state.cards.get(
                        source.attached_to or ""
                    )
                    if attached is not None and attached.ref in domains:
                        selections.extend(
                            (attached.ref, str(option))
                            for option in domains[attached.ref]
                        )
                elif (
                    parsed.scope == "source_controller"
                    and kind == "attack"
                ):
                    for variable, options in sorted(domains.items()):
                        selections.extend(
                            (variable, str(option))
                            for option in options
                            if option == source.controller
                            or (
                                parsed.template is not None
                                and parsed.template.includes_planeswalkers
                                and source_planeswalker(str(option))
                            )
                        )
                elif (
                    parsed.scope == "source_planeswalkers"
                    and kind == "attack"
                ):
                    selections.extend(
                        (variable, str(option))
                        for variable, options in sorted(domains.items())
                        for option in options
                        if source_planeswalker(str(option))
                    )
                elif parsed.scope == "global" and kind == "block":
                    selections.extend(
                        (variable, str(option))
                        for variable, options in sorted(domains.items())
                        for option in options
                    )
                if not selections:
                    continue
                if not parsed.exact:
                    unresolved.append((source, line))
                    continue
                template = parsed.template
                assert template is not None
                if (
                    template.source_condition == "source_untapped"
                    and source.tapped
                ):
                    continue
                if (
                    template.source_condition == "source_attacking"
                    and not source.attacking
                ):
                    continue
                for variable, option in selections:
                    costs.append(
                        self._declaration_cost(
                            cost_id=(
                                f"{kind}-cost:{parsed.scope}:{source.ref}:"
                                f"{line_index}:{variable}:{option}"
                            ),
                            variable=variable,
                            option=option,
                            payer=payer,
                            mana=template.mana,
                            source=source,
                            label=(
                                f"{self.display_name(source.object_id)} "
                                f"requires {template.printed_cost} for "
                                f"{variable} to {kind}."
                            ),
                        )
                    )
        return tuple(costs), tuple(unresolved)

    def _attack_declaration_costs(
        self,
        active: str,
        domains: Mapping[str, Sequence[str]],
    ) -> tuple[
        tuple[DeclarationCost, ...],
        tuple[tuple[CardInstance, str], ...],
    ]:
        return self._declaration_costs("attack", active, domains)

    def _matches_declaration_predicate(
        self,
        card: CardInstance,
        predicate: DeclarationObjectPredicate,
        *,
        source: CardInstance,
    ) -> bool:
        data = self._effective_card_data(card)
        card_types, subtypes, supertypes = self._type_parts(
            str(data.get("type_line") or "")
        )
        normalized_types = {value.casefold() for value in card_types}
        if predicate.types_any and not normalized_types.intersection(
            value.casefold() for value in predicate.types_any
        ):
            return False
        if predicate.types_none and normalized_types.intersection(
            value.casefold() for value in predicate.types_none
        ):
            return False
        normalized_supertypes = {
            value.casefold() for value in supertypes
        }
        if predicate.supertypes_any and not normalized_supertypes.intersection(
            value.casefold() for value in predicate.supertypes_any
        ):
            return False
        if predicate.supertypes_none and normalized_supertypes.intersection(
            value.casefold() for value in predicate.supertypes_none
        ):
            return False
        normalized_subtypes = {value.casefold() for value in subtypes}
        if predicate.subtypes_any and not normalized_subtypes.intersection(
            value.casefold() for value in predicate.subtypes_any
        ):
            return False
        if predicate.subtypes_none and normalized_subtypes.intersection(
            value.casefold() for value in predicate.subtypes_none
        ):
            return False
        colors = {
            str(value).upper() for value in data.get("colors", [])
        }
        if predicate.colors_any and not colors.intersection(
            str(value).upper() for value in predicate.colors_any
        ):
            return False
        if predicate.colors_none and colors.intersection(
            str(value).upper() for value in predicate.colors_none
        ):
            return False
        keywords = normalized_keywords(data.get("keywords", []))
        if predicate.keywords_any and not keywords.intersection(
            str(value).casefold() for value in predicate.keywords_any
        ):
            return False
        if predicate.keywords_none and keywords.intersection(
            str(value).casefold() for value in predicate.keywords_none
        ):
            return False
        if predicate.token is not None and card.is_token != predicate.token:
            return False
        if predicate.goaded is not None:
            goaded = bool(self._active_goad_designations(card))
            if goaded != predicate.goaded:
                return False
        if predicate.tapped is not None and card.tapped != predicate.tapped:
            return False
        if predicate.enchanted is not None:
            enchanted = False
            for attachment_id in card.attachments:
                attachment = self.state.cards.get(attachment_id)
                if (
                    attachment is None
                    or attachment.zone != "battlefield"
                    or attachment.phased_out
                    or attachment.attached_to != card.object_id
                ):
                    continue
                _, attachment_subtypes, _ = self._type_parts(
                    str(
                        self._effective_card_data(attachment).get("type_line")
                        or ""
                    )
                )
                if "aura" in attachment_subtypes:
                    enchanted = True
                    break
            if enchanted != predicate.enchanted:
                return False
        for comparison_rule in (
            *((predicate.stat,) if predicate.stat is not None else ()),
            *predicate.additional_stats,
        ):
            left = self._numeric_stat(
                card.object_id, comparison_rule.stat
            )
            right = (
                int(comparison_rule.value or 0)
                if comparison_rule.operand == "fixed"
                else self._numeric_stat(
                    source.object_id, comparison_rule.stat
                )
            )
            comparison = {
                "eq": left == right,
                "lt": left < right,
                "le": left <= right,
                "gt": left > right,
                "ge": left >= right,
            }[comparison_rule.operator]
            if not comparison:
                return False
        return True

    def _restriction_variables(
        self,
        template: DeclarationRestrictionTemplate,
        source: CardInstance,
        domains: Mapping[str, Sequence[str]],
    ) -> tuple[str, ...]:
        if template.scope == "self":
            return (source.ref,) if source.ref in domains else ()
        if template.scope == "attached":
            attached = self.state.cards.get(source.attached_to or "")
            return (
                (attached.ref,)
                if attached is not None and attached.ref in domains
                else ()
            )
        if template.scope == "attached_option":
            return tuple(sorted(domains))
        if template.scope == "source_opponents":
            by_ref = {
                card.ref: card for card in self.state.cards.values()
            }
            return tuple(
                variable
                for variable in sorted(domains)
                if variable in by_ref
                and by_ref[variable].controller != source.controller
            )
        return tuple(sorted(domains))

    def _restriction_is_relevant(
        self,
        scope: str | None,
        source: CardInstance,
        domains: Mapping[str, Sequence[str]],
    ) -> bool:
        if not domains:
            return False
        if scope == "self":
            return source.ref in domains
        if scope == "attached":
            attached = self.state.cards.get(source.attached_to or "")
            return attached is not None and attached.ref in domains
        if scope == "attached_option":
            attached = self.state.cards.get(source.attached_to or "")
            return attached is not None and any(
                attached.ref in options for options in domains.values()
            )
        if scope == "source_opponents":
            return any(
                card.ref in domains and card.controller != source.controller
                for card in self.state.cards.values()
            )
        if scope == "source_option":
            return any(source.ref in options for options in domains.values())
        return True

    def _declaration_condition_player(
        self,
        role: DeclarationConditionPlayer,
        *,
        kind: str,
        source: CardInstance,
        variable: str,
        option: str,
        by_ref: Mapping[str, CardInstance],
    ) -> str | None:
        if role == "source_controller":
            return source.controller
        if kind == "attack":
            if role == "attacking_player":
                attacker = by_ref.get(variable)
                return attacker.controller if attacker is not None else None
            return self._defending_player_for_attack_target(option)
        if role == "attacking_player":
            attacker = by_ref.get(option)
            return attacker.controller if attacker is not None else None
        blocker = by_ref.get(variable)
        return blocker.controller if blocker is not None else None

    def _declaration_battlefield_count(
        self,
        condition: DeclarationBattlefieldCondition,
        *,
        player: str,
        source: CardInstance,
        exclude_source: bool,
    ) -> int:
        return sum(
            1
            for card in self.state.cards.values()
            if card.zone == "battlefield"
            and not card.phased_out
            and card.controller == player
            and (not exclude_source or card.object_id != source.object_id)
            and any(
                self._matches_declaration_predicate(
                    card,
                    predicate,
                    source=source,
                )
                for predicate in condition.predicates_any
            )
        )

    def _declaration_condition_holds(
        self,
        condition: DeclarationCondition,
        *,
        kind: str,
        source: CardInstance,
        variable: str,
        option: str,
        by_ref: Mapping[str, CardInstance],
    ) -> bool:
        if isinstance(condition, DeclarationCombatCondition):
            return (
                condition.kind == "attacking_alone"
                and len(self._current_attacker_cards()) == 1
            )
        if isinstance(condition, DeclarationPlayerStateCondition):
            player = self._declaration_condition_player(
                condition.player,
                kind=kind,
                source=source,
                variable=variable,
                option=option,
                by_ref=by_ref,
            )
            if player is None:
                return False
            if condition.state == "monarch":
                return self.state.monarch == player
            return self.state.players[player].poison > 0
        if isinstance(condition, DeclarationTurnHistoryCondition):
            if condition.fact == "attacked_player":
                if kind != "attack" or option not in self.active_seats:
                    return False
                return self._object_attacked_player_this_turn(
                    source.logical_object_id,
                    option,
                )
            if condition.player is None:
                return False
            player = self._declaration_condition_player(
                condition.player,
                kind=kind,
                source=source,
                variable=variable,
                option=option,
                by_ref=by_ref,
            )
            if player is None:
                return False
            if condition.fact == "cast_spell":
                return self._player_cast_spell_this_turn(player)
            if condition.fact == "cast_creature_spell":
                return self._player_cast_spell_this_turn(
                    player,
                    creature=True,
                )
            if condition.fact == "cast_noncreature_spell":
                return self._player_cast_spell_this_turn(
                    player,
                    creature=False,
                )
            if condition.fact == "creature_died_under_control":
                return self._creature_died_under_control_this_turn(player)
            if condition.fact == "opponent_dealt_damage":
                return self._opponent_was_dealt_damage_this_turn(player)
            return False
        if isinstance(condition, DeclarationSharedSubtypeCondition):
            player = self._declaration_condition_player(
                condition.player,
                kind=kind,
                source=source,
                variable=variable,
                option=option,
                by_ref=by_ref,
            )
            if player is None:
                return False
            subtype_counts: dict[str, int] = {}
            changelings = 0
            for card in self.state.cards.values():
                if (
                    card.zone != "battlefield"
                    or card.phased_out
                    or card.controller != player
                ):
                    continue
                data = self._effective_card_data(card)
                card_types, subtypes, _ = self._type_parts(
                    str(data.get("type_line") or "")
                )
                if "creature" not in card_types:
                    continue
                has_changeling = "changeling" in normalized_keywords(
                    data.get("keywords", [])
                )
                if has_changeling:
                    changelings += 1
                else:
                    for subtype in subtypes:
                        subtype_counts[subtype] = (
                            subtype_counts.get(subtype, 0) + 1
                        )
            return changelings >= condition.minimum or any(
                count + changelings >= condition.minimum
                for count in subtype_counts.values()
            )
        player = self._declaration_condition_player(
            condition.player,
            kind=kind,
            source=source,
            variable=variable,
            option=option,
            by_ref=by_ref,
        )
        if player is None:
            return False
        count = self._declaration_battlefield_count(
            condition,
            player=player,
            source=source,
            exclude_source=condition.exclude_source,
        )
        if condition.compare_player is None:
            return count >= condition.minimum and (
                condition.maximum is None or count <= condition.maximum
            )
        other = self._declaration_condition_player(
            condition.compare_player,
            kind=kind,
            source=source,
            variable=variable,
            option=option,
            by_ref=by_ref,
        )
        if other is None:
            return False
        other_count = self._declaration_battlefield_count(
            condition,
            player=other,
            source=source,
            exclude_source=False,
        )
        return count > other_count

    def _declaration_option_matches_relation(
        self,
        template: DeclarationRestrictionTemplate,
        *,
        kind: str,
        source: CardInstance,
        option: str,
        by_ref: Mapping[str, CardInstance],
    ) -> bool:
        """Return whether an option is in a represented source-relative scope."""

        if template.option_relation is None:
            return True
        if template.option_relation != "source_controller":
            return False
        if kind == "block":
            opposing = by_ref.get(option)
            return (
                opposing is not None
                and opposing.controller == source.controller
            )
        if option == source.controller:
            return True
        if not template.includes_planeswalkers:
            return False
        target = by_ref.get(option)
        if target is None or target.controller != source.controller:
            return False
        target_types, _, _ = self._type_parts(
            str(self._effective_card_data(target).get("type_line") or "")
        )
        return "planeswalker" in target_types

    def _declaration_restrictions(
        self,
        kind: str,
        domains: Mapping[str, Sequence[str]],
    ) -> tuple[
        dict[str, tuple[str, ...]],
        tuple[DeclarationRestriction, ...],
        tuple[tuple[CardInstance, str], ...],
    ]:
        """Apply represented static CR 508.1c/509.1b restrictions."""

        original = {
            str(variable): tuple(str(option) for option in options)
            for variable, options in domains.items()
        }
        remaining = {
            variable: list(options)
            for variable, options in original.items()
        }
        constraints: list[DeclarationRestriction] = []
        unresolved: list[tuple[CardInstance, str]] = []
        by_ref = {card.ref: card for card in self.state.cards.values()}
        for source in sorted(
            self.state.cards.values(), key=lambda value: value.ref
        ):
            if source.zone != "battlefield" or source.phased_out:
                continue
            for line_index, line in enumerate(
                self._combat_oracle_lines(source)
            ):
                parsed = parse_declaration_restriction_line(line)
                if not parsed.recognized or kind not in parsed.declarations:
                    continue
                if not self._restriction_is_relevant(
                    parsed.scope, source, original
                ):
                    continue
                if not parsed.exact:
                    unresolved.append((source, line))
                    continue
                template = parsed.template
                assert template is not None
                variables = self._restriction_variables(
                    template, source, original
                )
                if template.mode == "maximum_total_selections":
                    constraints.append(
                        DeclarationRestriction(
                            restriction_id=(
                                f"{kind}:restriction:{source.ref}:"
                                f"{line_index}:maximum"
                            ),
                            kind="maximum_total_selections",
                            count=template.count,
                            label=(
                                f"{self.display_name(source.object_id)} "
                                f"allows at most {template.count} creature(s) "
                                f"to {kind}."
                            ),
                        )
                    )
                    continue
                if template.mode in {
                    "minimum_option_uses",
                    "maximum_option_uses",
                }:
                    constrained_option = (
                        source.controller
                        if kind == "attack"
                        and template.option_relation == "source_controller"
                        else source.ref
                    )
                    if kind == "attack":
                        constraint_label = (
                            f"{self.display_name(source.object_id)} allows at "
                            f"most {template.count} creature(s) to attack "
                            + (
                                "it."
                                if template.scope == "source_option"
                                else "its controller."
                            )
                        )
                    elif template.mode == "minimum_option_uses":
                        constraint_label = (
                            f"{self.display_name(source.object_id)} requires "
                            f"{template.count} blocker(s) when blocked."
                        )
                    else:
                        constraint_label = (
                            f"{self.display_name(source.object_id)} allows at "
                            f"most {template.count} blocker(s)."
                        )
                    constraints.append(
                        DeclarationRestriction(
                            restriction_id=(
                                f"{kind}:restriction:{source.ref}:"
                                f"{line_index}:option-uses"
                            ),
                            kind=template.mode,
                            option=constrained_option,
                            count=template.count,
                            when_used=(
                                template.mode == "minimum_option_uses"
                            ),
                            label=constraint_label,
                        )
                    )
                    continue
                for variable in variables:
                    subject = by_ref.get(variable)
                    if subject is None or not self._matches_declaration_predicate(
                        subject, template.subject, source=source
                    ):
                        continue
                    if template.mode == "minimum_total_selections":
                        constraints.append(
                            DeclarationRestriction(
                                restriction_id=(
                                    f"{kind}:restriction:{source.ref}:"
                                    f"{line_index}:{variable}:minimum"
                                ),
                                kind="minimum_total_selections",
                                count=template.count,
                                trigger_variable=variable,
                                label=(
                                    f"{self.display_name(subject.object_id)} "
                                    f"can't {kind} alone."
                                ),
                            )
                        )
                        continue
                    if template.mode == "minimum_matching_selections":
                        matching_variables = tuple(
                            candidate
                            for candidate in sorted(original)
                            if candidate != variable
                            and (matching := by_ref.get(candidate)) is not None
                            and self._matches_declaration_predicate(
                                matching,
                                template.matching,
                                source=source,
                            )
                        )
                        constraints.append(
                            DeclarationRestriction(
                                restriction_id=(
                                    f"{kind}:restriction:{source.ref}:"
                                    f"{line_index}:{variable}:matching"
                                ),
                                kind="minimum_variable_selections",
                                count=template.count,
                                trigger_variable=variable,
                                variables=matching_variables,
                                label=(
                                    f"{self.display_name(subject.object_id)} "
                                    f"requires {template.count} matching "
                                    f"creature(s) to also {kind}."
                                ),
                            )
                        )
                        continue
                    legal_options: list[str] = []
                    for option in remaining.get(variable, []):
                        attached_option = (
                            self.state.cards.get(source.attached_to or "")
                            if template.scope == "attached_option"
                            else None
                        )
                        if (
                            template.scope == "source_option"
                            and option != source.ref
                        ):
                            legal_options.append(option)
                            continue
                        if (
                            template.scope == "attached_option"
                            and (
                                attached_option is None
                                or option != attached_option.ref
                            )
                        ):
                            legal_options.append(option)
                            continue
                        if not self._declaration_option_matches_relation(
                            template,
                            kind=kind,
                            source=source,
                            option=option,
                            by_ref=by_ref,
                        ):
                            legal_options.append(option)
                            continue
                        if template.condition is not None:
                            condition_holds = self._declaration_condition_holds(
                                template.condition,
                                kind=kind,
                                source=source,
                                variable=variable,
                                option=option,
                                by_ref=by_ref,
                            )
                            if (
                                condition_holds
                                != template.applies_when_condition
                            ):
                                legal_options.append(option)
                                continue
                        opposing = by_ref.get(option)
                        if (
                            opposing is not None
                            and not self._matches_declaration_predicate(
                                opposing,
                                template.opposing,
                                source=source,
                            )
                        ):
                            legal_options.append(option)
                            continue
                        if (
                            opposing is None
                            and template.opposing != DeclarationObjectPredicate()
                        ):
                            legal_options.append(option)
                    remaining[variable] = legal_options
        return (
            {
                variable: tuple(options)
                for variable, options in remaining.items()
                if options
            },
            tuple(constraints),
            tuple(unresolved),
        )

    def _selected_declaration_mana(
        self,
        costs: Sequence[DeclarationCost],
        declaration: Mapping[str, str],
        *,
        payer: str,
    ) -> tuple[dict[str, int], tuple[DeclarationCost, ...]]:
        requirements = {
            key: 0
            for key in ("GENERIC", "W", "U", "B", "R", "G", "C")
        }
        selected: list[DeclarationCost] = []
        for cost in costs:
            if declaration.get(cost.variable) != cost.option:
                continue
            if cost.payer != payer:
                raise GameRuleError(
                    "A declaration cost named a different payer"
                )
            selected.append(cost)
            for key, amount in cost.mana_requirements().items():
                requirements[key] += amount
        return requirements, tuple(selected)

    def _attack_declaration_components(
        self,
        active: str,
    ) -> tuple[
        DeclarationProblem,
        tuple[DeclarationCost, ...],
        tuple[tuple[CardInstance, str, str], ...],
    ]:
        planeswalkers = self._attackable_planeswalkers(active)
        battles = self._attackable_battles(active)
        planeswalker_ids = {walker["id"] for walker in planeswalkers}
        defenders = [
            *[seat for seat in self.active_seats if seat != active],
            *[walker["id"] for walker in planeswalkers],
            *[
                battle["id"]
                for battle in battles
                if battle["id"] not in planeswalker_ids
            ],
        ]
        domains: dict[str, tuple[str, ...]] = {}
        requirements: list[DeclarationRequirement] = []
        for object_id in self.state.players[active].zones["battlefield"]:
            card = self.state.cards[object_id]
            if self._attack_declaration_error(card, active) is not None:
                continue
            domains[card.ref] = tuple(defenders)
            if "this creature attacks each combat if able" in (
                self._combat_oracle_text(card)
            ):
                requirements.append(
                    DeclarationRequirement(
                        requirement_id=f"attack:{card.ref}:each-combat",
                        kind="choose",
                        variable=card.ref,
                        label=(
                            f"{self.display_name(card.object_id)} attacks "
                            "this combat if able."
                        ),
                    )
                )
            for designation in self._active_goad_designations(card):
                requirements.extend(
                    (
                        DeclarationRequirement(
                            requirement_id=(
                                f"attack:{card.ref}:goad:{designation.player}:attack"
                            ),
                            kind="choose",
                            variable=card.ref,
                            label=(
                                f"{self.display_name(card.object_id)} attacks "
                                f"this combat if able because {designation.player} "
                                "goaded it."
                            ),
                        ),
                        DeclarationRequirement(
                            requirement_id=(
                                f"attack:{card.ref}:goad:{designation.player}:other"
                            ),
                            kind="choose_option_in",
                            variable=card.ref,
                            options=tuple(
                                seat
                                for seat in self.active_seats
                                if seat not in {active, designation.player}
                            ),
                            label=(
                                f"{self.display_name(card.object_id)} attacks "
                                f"a player other than {designation.player} if able."
                            ),
                        ),
                    )
                )
        domains, restrictions, restriction_gaps = (
            self._declaration_restrictions("attack", domains)
        )
        costs, cost_gaps = self._attack_declaration_costs(
            active,
            domains,
        )
        problem = DeclarationProblem(
            domains=domains,
            requirements=tuple(requirements),
            restrictions=restrictions,
            costed_options=frozenset(cost.selection for cost in costs),
        )
        gaps = tuple(
            (source, line, "restriction")
            for source, line in restriction_gaps
        ) + tuple(
            (source, line, "cost") for source, line in cost_gaps
        )
        return problem, costs, gaps

    def _attack_declaration_problem(self, active: str) -> DeclarationProblem:
        return self._attack_declaration_components(active)[0]

    def _block_declaration_costs(
        self,
        defender: str,
        domains: Mapping[str, Sequence[str]],
    ) -> tuple[
        tuple[DeclarationCost, ...],
        tuple[tuple[CardInstance, str], ...],
    ]:
        return self._declaration_costs("block", defender, domains)

    def _block_declaration_components(
        self,
        defender: str,
    ) -> tuple[
        DeclarationProblem,
        tuple[DeclarationCost, ...],
        tuple[tuple[CardInstance, str, str], ...],
    ]:
        attacker_cards = [
            card
            for card in self._current_attacker_cards()
            if self._defending_player_for_attacker(
                card.object_id,
                self.state.combat.attackers[card.object_id],
            )
            == defender
        ]
        domains: dict[str, tuple[str, ...]] = {}
        blockers_by_ref: dict[str, CardInstance] = {}
        for object_id in self.state.players[defender].zones["battlefield"]:
            blocker = self.state.cards[object_id]
            blocker_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(blocker).get("type_line")
                    or ""
                )
            )
            if (
                blocker.controller != defender
                or blocker.tapped
                or blocker.phased_out
                or "creature" not in blocker_types
                or "battle" in blocker_types
            ):
                continue
            legal = tuple(
                attacker.ref
                for attacker in attacker_cards
                if self._can_block(attacker, blocker)[0]
            )
            if legal:
                domains[blocker.ref] = legal
                blockers_by_ref[blocker.ref] = blocker

        requirements: list[DeclarationRequirement] = []
        for blocker_ref, blocker in blockers_by_ref.items():
            if "this creature blocks each combat if able" in (
                self._combat_oracle_text(blocker)
            ):
                requirements.append(
                    DeclarationRequirement(
                        requirement_id=f"block:{blocker_ref}:each-combat",
                        kind="choose",
                        variable=blocker_ref,
                        label=(
                            f"{self.display_name(blocker.object_id)} blocks "
                            "this combat if able."
                        ),
                    )
                )

        restrictions: list[DeclarationRestriction] = []
        for attacker in attacker_cards:
            oracle = self._combat_oracle_text(attacker)
            if "this creature must be blocked if able" in oracle:
                requirements.append(
                    DeclarationRequirement(
                        requirement_id=f"block:{attacker.ref}:if-able",
                        kind="option_used",
                        option=attacker.ref,
                        label=(
                            f"{self.display_name(attacker.object_id)} must "
                            "be blocked if able."
                        ),
                    )
                )
            if "all creatures able to block this creature do so" in oracle:
                for blocker_ref, legal in domains.items():
                    if attacker.ref not in legal:
                        continue
                    requirements.append(
                        DeclarationRequirement(
                            requirement_id=(
                                f"block:{blocker_ref}:{attacker.ref}:all"
                            ),
                            kind="choose_option",
                            variable=blocker_ref,
                            option=attacker.ref,
                            label=(
                                f"{self.display_name(blockers_by_ref[blocker_ref].object_id)} "
                                f"blocks {self.display_name(attacker.object_id)} "
                                "if able."
                            ),
                        )
                    )
            if MENACE in self._combat_keywords(attacker):
                restrictions.append(
                    DeclarationRestriction(
                        restriction_id=f"block:{attacker.ref}:menace",
                        kind="minimum_option_uses",
                        option=attacker.ref,
                        count=2,
                        when_used=True,
                        label=(
                            f"{attacker.ref} has menace and must be blocked "
                            "by zero or at least two creatures"
                        ),
                    )
                )
        domains, static_restrictions, restriction_gaps = (
            self._declaration_restrictions("block", domains)
        )
        restrictions.extend(static_restrictions)
        costs, cost_gaps = self._block_declaration_costs(
            defender,
            domains,
        )
        problem = DeclarationProblem(
            domains=domains,
            requirements=tuple(requirements),
            restrictions=tuple(restrictions),
            costed_options=frozenset(cost.selection for cost in costs),
        )
        gaps = tuple(
            (source, line, "restriction")
            for source, line in restriction_gaps
        ) + tuple(
            (source, line, "cost") for source, line in cost_gaps
        )
        return problem, costs, gaps

    def _block_declaration_problem(
        self,
        defender: str,
    ) -> DeclarationProblem:
        return self._block_declaration_components(defender)[0]

    @staticmethod
    def _validate_declaration_requirements(
        problem: DeclarationProblem,
        declaration: Mapping[str, str],
    ) -> None:
        try:
            evaluation = problem.evaluate(declaration)
        except (DeclarationConstraintError, DeclarationSearchLimitError) as exc:
            raise GameRuleError(str(exc)) from exc
        if evaluation.restriction_errors:
            raise GameRuleError(evaluation.restriction_errors[0])
        if len(evaluation.satisfied) != evaluation.maximum:
            raise GameRuleError(
                "Combat declaration satisfies "
                f"{len(evaluation.satisfied)} of a possible "
                f"{evaluation.maximum} requirements"
            )

    def _issue_attackers(self) -> None:
        active = self.state.active_player
        if active not in self.active_seats:
            self._advance_step()
            return
        candidate_by_ref: dict[str, dict[str, Any]] = {}
        for oid in self.state.players[active].zones["battlefield"]:
            card = self.state.cards[oid]
            data = self._effective_card_data(card)
            if self._attack_declaration_error(card, active) is None:
                candidate_by_ref[card.ref] = {
                    "id": card.ref,
                    "name": self.display_name(oid),
                    "sick": self._is_summoning_sick(card),
                    "haste": "Haste" in data.get("keywords", []),
                }
        problem, costs, unresolved = self._attack_declaration_components(
            active
        )
        if unresolved:
            source, line, category = unresolved[0]
            self._pause_for_unsupported_semantic(
                event=f"combat.attack_{category}:{line}",
                source=source,
            )
            return
        candidates = [
            candidate_by_ref[ref]
            for ref in problem.domains
            if ref in candidate_by_ref
        ]
        if not candidates:
            self.state.combat.attackers_declared = True
            self.state.combat.defending_players = [
                seat
                for seat in self.active_seats
                if seat != active
            ]
            self._grant_priority(active)
            return
        planeswalker_defenders = self._attackable_planeswalkers(active)
        battle_defenders = self._attackable_battles(active)
        permanent_defender_ids = {
            walker["id"] for walker in planeswalker_defenders
        }
        self.permissions.issue(
            kind="combat.attackers",
            role="pilot",
            actors=[active],
            allowed_actions=["attack"],
            payload_by_actor={
                active: {
                    "candidates": candidates,
                    "defenders": [
                        *[
                            seat
                            for seat in self.active_seats
                            if seat != active
                        ],
                        *[
                            walker["id"]
                            for walker in planeswalker_defenders
                        ],
                        *[
                            battle["id"]
                            for battle in battle_defenders
                            if battle["id"] not in permanent_defender_ids
                        ],
                    ],
                    "planeswalker_defenders": planeswalker_defenders,
                    "battle_defenders": battle_defenders,
                    "declaration_constraints": problem.projection(),
                    "declaration_costs": [
                        cost.to_dict() for cost in costs
                    ],
                    "payment": {
                        "default": "auto",
                        "manual_fields": ["mana", "payment"],
                        "spend_context": "combat_declaration",
                    },
                }
            },
        )

    def _attackable_planeswalkers(
        self,
        attacker: str,
    ) -> list[dict[str, Any]]:
        planeswalkers: list[dict[str, Any]] = []
        for card in self.state.cards.values():
            if (
                card.zone != "battlefield"
                or card.phased_out
                or card.controller not in self.active_seats
                or card.controller == attacker
            ):
                continue
            card_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if "planeswalker" not in card_types:
                continue
            planeswalkers.append(
                {
                    "id": card.ref,
                    "name": self.display_name(card.object_id),
                    "controller": card.controller,
                    "loyalty": int(card.counters.get("loyalty", 0)),
                }
            )
        return sorted(planeswalkers, key=lambda value: value["id"])

    def _attackable_battles(self, attacker: str) -> list[dict[str, Any]]:
        battles: list[dict[str, Any]] = []
        for card in self.state.cards.values():
            if (
                card.zone != "battlefield"
                or card.phased_out
                or card.battle_protector not in self.active_seats
                or card.battle_protector == attacker
            ):
                continue
            card_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if "battle" not in card_types:
                continue
            battles.append(
                {
                    "id": card.ref,
                    "name": self.display_name(card.object_id),
                    "controller": card.controller,
                    "protector": card.battle_protector,
                    "defense": int(
                        card.counters.get("defense", 0)
                    ),
                }
            )
        return sorted(battles, key=lambda value: value["id"])

    def _battle_for_attack_target(
        self,
        value: str,
    ) -> CardInstance | None:
        battle = next(
            (
                card
                for card in self.state.cards.values()
                if card.ref == value
                and card.zone == "battlefield"
                and not card.phased_out
            ),
            None,
        )
        if battle is None:
            return None
        card_types, _, _ = self._type_parts(
            str(
                self._effective_card_data(battle).get("type_line")
                or ""
            )
        )
        return battle if "battle" in card_types else None

    def _planeswalker_for_attack_target(
        self,
        value: str,
    ) -> CardInstance | None:
        planeswalker = next(
            (
                card
                for card in self.state.cards.values()
                if card.ref == value
                and card.zone == "battlefield"
                and not card.phased_out
            ),
            None,
        )
        if planeswalker is None:
            return None
        card_types, _, _ = self._type_parts(
            str(
                self._effective_card_data(planeswalker).get("type_line")
                or ""
            )
        )
        return planeswalker if "planeswalker" in card_types else None

    def _attack_target_details(
        self,
        attacker: str,
        value: str,
    ) -> dict[str, str] | None:
        if value in self.active_seats and value != attacker:
            return {
                "target": value,
                "kind": "player",
                "defending_player": value,
            }
        planeswalker = self._planeswalker_for_attack_target(value)
        if (
            planeswalker is not None
            and planeswalker.controller in self.active_seats
            and planeswalker.controller != attacker
        ):
            return {
                "target": planeswalker.ref,
                "kind": "planeswalker",
                "defending_player": planeswalker.controller,
            }
        battle = self._battle_for_attack_target(value)
        if (
            battle is not None
            and battle.battle_protector in self.active_seats
            and battle.battle_protector != attacker
        ):
            return {
                "target": battle.ref,
                "kind": "battle",
                "defending_player": str(battle.battle_protector),
            }
        return None

    def _defending_player_for_attack_target(
        self,
        value: str,
    ) -> str | None:
        if value in self.active_seats:
            return value
        planeswalker = self._planeswalker_for_attack_target(value)
        if planeswalker is not None:
            return planeswalker.controller
        battle = self._battle_for_attack_target(value)
        return battle.battle_protector if battle is not None else None

    def _defending_player_for_attacker(
        self,
        attacker_id: str,
        target: str,
    ) -> str | None:
        context = self.state.combat.attack_target_context.get(attacker_id)
        if context is not None:
            defender = context.get("defending_player")
            return defender if defender in self.state.players else None
        return self._defending_player_for_attack_target(target)

    def _complete_attackers(self, decision: Any) -> None:
        active = decision.actors[0]
        response = decision.responses[active]
        declarations = response.get("attackers")
        if declarations is None:
            declarations = response.get("attacks")
        declarations = declarations or {}
        if isinstance(declarations, list):
            if all(isinstance(value, Mapping) for value in declarations):
                normalized: dict[str, Any] = {}
                for value in declarations:
                    attacker = value.get("attacker") or value.get("id")
                    defender = value.get("defender")
                    if attacker is None or defender is None:
                        raise GameRuleError(
                            "Each attack declaration needs attacker and defender"
                        )
                    attacker_ref = str(attacker)
                    if attacker_ref in normalized:
                        raise GameRuleError(
                            "A creature cannot be declared twice"
                        )
                    normalized[attacker_ref] = defender
                declarations = normalized
            else:
                default_defender = response.get("defender")
                declarations = {
                    str(value): default_defender for value in declarations
                }
        if not isinstance(declarations, Mapping):
            raise GameRuleError("Attack declarations must be a mapping or list")
        chosen: list[tuple[CardInstance, dict[str, str]]] = []
        canonical: dict[str, str] = {}
        used: set[str] = set()
        for value, defender in dict(declarations).items():
            card = self._resolve_object(active, str(value), zones={"battlefield"}, controlled_only=True)
            if card.object_id in used:
                raise GameRuleError("A creature cannot be declared twice")
            defender = str(defender)
            target_details = self._attack_target_details(active, defender)
            if target_details is None:
                raise GameRuleError(f"Invalid attack defender {defender}")
            defender = target_details["target"]
            declaration_error = self._attack_declaration_error(
                card,
                active,
            )
            if declaration_error is not None:
                raise GameRuleError(declaration_error)
            chosen.append((card, target_details))
            canonical[card.ref] = defender
            used.add(card.object_id)

        problem, locked_costs, unresolved = self._attack_declaration_components(
            active
        )
        if unresolved:
            raise GameRuleError(
                "The attack declaration has unresolved restriction or cost semantics"
            )
        self._validate_declaration_requirements(problem, canonical)
        for card, _target_details in chosen:
            data = self._effective_card_data(card)
            if "Vigilance" not in data.get("keywords", []):
                card.tapped = True
        requirements, selected_costs = self._selected_declaration_mana(
            locked_costs,
            canonical,
            payer=active,
        )
        spent = normalize_mana_bundle(None)
        activations: list[dict[str, Any]] = []
        if sum(requirements.values()):
            spent, activations = self._pay_for_cost(
                active,
                requirements,
                response,
                spend_context="combat_declaration",
            )
        surviving_attackers: list[
            tuple[CardInstance, dict[str, str]]
        ] = []
        for card, target_details in chosen:
            if (
                card.zone != "battlefield"
                or card.controller != active
                or card.phased_out
            ):
                continue
            defender = target_details["target"]
            card.attacking = defender
            self.state.combat.attackers[card.object_id] = defender
            self.state.combat.attack_target_context[card.object_id] = dict(
                target_details
            )
            self._record_turn_history(
                "creature_attacked",
                actor=active,
                object_incarnation=card.logical_object_id,
                target=defender,
                target_kind=target_details["kind"],
            )
            surviving_attackers.append((card, target_details))
        used = {card.object_id for card, _ in surviving_attackers}
        self.state.combat.attackers_declared = True
        if used:
            self.state.combat.had_attacking_creature = True
        self.state.combat.defending_players = [
            seat
            for seat in self.active_seats
            if seat != active
        ]
        self._log(
            active,
            "combat.attack",
            f"{active} attacked with {len(used)} creature(s).",
            {
                "attackers": {
                    self.state.cards[oid].ref: defender
                    for oid, defender in self.state.combat.attackers.items()
                },
                "costs": [cost.cost_id for cost in selected_costs],
                "requirements": {
                    key: value
                    for key, value in requirements.items()
                    if value
                },
                "payment": {
                    key: value for key, value in spent.items() if value
                },
                "mana_sources": [
                    {
                        "source": activation.get("source_ref")
                        or activation.get("source"),
                        "bundle": activation.get("bundle"),
                    }
                    for activation in activations
                ],
            },
            importance=2,
            changed_objects=list(used),
            changed_players=[active],
        )
        attack_triggers: list[StackItem] = []
        for object_id in used:
            attacker = self.state.cards[object_id]
            if (
                "whenever this token attacks, you may mill a card"
                not in str(
                    self._effective_card_data(attacker).get("oracle_text")
                    or ""
                ).casefold()
            ):
                continue
            ref = self._next_ref("S")
            attack_triggers.append(
                StackItem(
                    stack_id=self._stable_runtime_id("stack", ref),
                    ref=ref,
                    kind="triggered_ability",
                    controller=attacker.controller,
                    label=f"{self.display_name(object_id)} attack trigger",
                    source_object_id=attacker.object_id,
                    semantic_key="builtin:optional-mill-one",
                    visibility=list(self.seats),
                    context={
                        "event": "creature.attacks",
                        "card": attacker.ref,
                        "defender": attacker.attacking,
                    },
                )
            )
        self._enqueue_semantic_trigger_batch(attack_triggers)
        self._grant_priority(active)

    def _attacked_defending_players(self) -> list[str]:
        """Return only defenders whose player or permanent is attacked."""

        attacked = {
            self._defending_player_for_attacker(attacker_id, target)
            for attacker_id, target in self.state.combat.attackers.items()
        }
        return [
            seat
            for seat in self.apnap_order()
            if seat in attacked
        ]

    def _current_attacker_cards(self) -> list[CardInstance]:
        attackers: list[CardInstance] = []
        for object_id in self.state.combat.attackers:
            card = self.state.cards.get(object_id)
            if (
                card is None
                or card.zone != "battlefield"
                or card.controller != self.state.active_player
                or card.phased_out
            ):
                continue
            card_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if "creature" in card_types and "battle" not in card_types:
                attackers.append(card)
        return attackers

    def _begin_blocker_decisions(self) -> None:
        if not self._current_attacker_cards():
            self.state.combat.blockers_declared = True
            self._grant_priority(self.state.active_player)
            return
        self.state.combat.blocker_cursor = 0
        self._issue_next_blocker()

    def _issue_next_blocker(self) -> None:
        defenders = self._attacked_defending_players()
        if self.state.combat.blocker_cursor >= len(defenders):
            self.state.combat.blockers_declared = True
            self._grant_priority(self.state.active_player)
            return
        defender = defenders[self.state.combat.blocker_cursor]
        attacker_cards = [
            card
            for card in self._current_attacker_cards()
            if self._defending_player_for_attacker(
                card.object_id,
                self.state.combat.attackers[card.object_id],
            )
            == defender
        ]
        attackers = [card.ref for card in attacker_cards]
        minimum_blockers = {
            card.ref: 2
            for card in attacker_cards
            if MENACE in self._combat_keywords(card)
        }
        problem, costs, unresolved = self._block_declaration_components(
            defender
        )
        if unresolved:
            source, line, category = unresolved[0]
            self._pause_for_unsupported_semantic(
                event=f"combat.block_{category}:{line}",
                source=source,
            )
            return
        if not problem.domains:
            self._log(
                defender,
                "combat.block",
                f"{defender} had no legal blockers.",
                {
                    "blocks": {},
                    "costs": [],
                    "requirements": {},
                    "payment": {},
                    "mana_sources": [],
                    "automatic": True,
                },
                importance=1,
                changed_players=[defender],
            )
            self.state.combat.blocker_cursor += 1
            self._issue_next_blocker()
            return
        blockers = list(problem.domains)
        legal_blocks = {
            blocker: list(options)
            for blocker, options in problem.domains.items()
        }
        self.permissions.issue(
            kind="combat.blockers",
            role="pilot",
            actors=[defender],
            allowed_actions=["block"],
            payload_by_actor={
                defender: {
                    "attackers": attackers,
                    "blockers": blockers,
                    "legal_blocks": legal_blocks,
                    "minimum_blockers": minimum_blockers,
                    "declaration_constraints": problem.projection(),
                    "declaration_costs": [
                        cost.to_dict() for cost in costs
                    ],
                    "payment": {
                        "default": "auto",
                        "manual_fields": ["mana", "payment"],
                        "spend_context": "combat_declaration",
                    },
                }
            },
        )

    def _complete_blockers(self, decision: Any) -> None:
        defender = decision.actors[0]
        response = decision.responses[defender]
        assignments = dict(response.get("blocks") or {})  # blocker ref -> attacker ref
        chosen: list[tuple[CardInstance, CardInstance]] = []
        canonical: dict[str, str] = {}
        used_blockers: set[str] = set()
        for blocker_value, attacker_value in assignments.items():
            blocker = self._resolve_object(defender, str(blocker_value), zones={"battlefield"}, controlled_only=True)
            attacker = self._resolve_object(defender, str(attacker_value), zones={"battlefield"})
            if blocker.object_id in used_blockers:
                raise GameRuleError("A blocker cannot block more than one attacker without an explicit rule")
            attack_target = self.state.combat.attackers.get(
                attacker.object_id
            )
            if (
                attack_target is None
                or self._defending_player_for_attacker(
                    attacker.object_id,
                    attack_target,
                )
                != defender
            ):
                raise GameRuleError(f"{attacker.ref} is not attacking {defender}")
            blocker_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(blocker).get("type_line")
                    or ""
                )
            )
            if (
                blocker.tapped
                or blocker.phased_out
                or "creature" not in blocker_types
            ):
                raise GameRuleError(f"{blocker.ref} cannot block")
            if "battle" in blocker_types:
                raise GameRuleError(
                    f"{blocker.ref} cannot block because it is a Battle"
                )
            can_block, reason = self._can_block(attacker, blocker)
            if not can_block:
                raise GameRuleError(
                    f"{blocker.ref} cannot block {attacker.ref}: {reason}"
                )
            chosen.append((blocker, attacker))
            canonical[blocker.ref] = attacker.ref
            used_blockers.add(blocker.object_id)

        problem, costs, unresolved = self._block_declaration_components(
            defender
        )
        if unresolved:
            raise GameRuleError(
                "The block declaration has unresolved restriction or cost semantics"
            )
        self._validate_declaration_requirements(problem, canonical)
        requirements, selected_costs = self._selected_declaration_mana(
            costs,
            canonical,
            payer=defender,
        )
        spent = normalize_mana_bundle(None)
        activations: list[dict[str, Any]] = []
        if sum(requirements.values()):
            spent, activations = self._pay_for_cost(
                defender,
                requirements,
                response,
                spend_context="combat_declaration",
            )
        surviving_blockers: list[tuple[CardInstance, CardInstance]] = []
        for blocker, attacker in chosen:
            if (
                blocker.zone != "battlefield"
                or blocker.controller != defender
                or blocker.phased_out
            ):
                continue
            self.state.combat.blockers.setdefault(attacker.object_id, []).append(blocker.object_id)
            blocker.blocking = attacker.object_id
            surviving_blockers.append((blocker, attacker))
        used_blockers = {
            blocker.object_id for blocker, _ in surviving_blockers
        }
        self._log(
            defender,
            "combat.block",
            f"{defender} declared {len(used_blockers)} blocker(s).",
            {
                "blocks": {
                    self.state.cards[b].ref: self.state.cards[a].ref
                    for a, blockers in self.state.combat.blockers.items()
                    for b in blockers
                    if b in used_blockers
                },
                "costs": [cost.cost_id for cost in selected_costs],
                "requirements": {
                    key: value
                    for key, value in requirements.items()
                    if value
                },
                "payment": {
                    key: value for key, value in spent.items() if value
                },
                "mana_sources": [
                    {
                        "source": activation.get("source_ref")
                        or activation.get("source"),
                        "bundle": activation.get("bundle"),
                    }
                    for activation in activations
                ],
            },
            importance=2,
            changed_objects=list(used_blockers),
            changed_players=[defender],
        )
        self.state.combat.blocker_cursor += 1
        self._issue_next_blocker()

    def _automatic_combat_assignments(
        self,
        actors: Sequence[str],
    ) -> list[dict[str, Any]] | None:
        """Return forced assignments, or None when a player must divide.

        A source with zero legal recipients assigns nothing. A source with one
        recipient has no strategic division choice. Two or more recipients
        require the ordinary simultaneous combat.damage decision.
        """

        options: dict[str, dict[str, Any]] = {}
        for seat in actors:
            options.update(self._combat_damage_source_options(seat))
        if any(len(option["targets"]) > 1 for option in options.values()):
            return None
        assignments: list[dict[str, Any]] = []
        for source, option in sorted(options.items()):
            targets = list(option["targets"])
            power = int(option["power"])
            if power <= 0 or not targets:
                continue
            assignments.append(
                {
                    "source": source,
                    "target": targets[0],
                    "amount": power,
                }
            )
        return assignments

    def _begin_combat_damage(self) -> None:
        self._initialize_combat_damage_steps()
        actors = [
            seat
            for seat in self.apnap_order()
            if self._combat_damage_source_options(seat)
        ]
        self._continue_combat_damage_assignments(
            actors=actors,
            cursor=0,
            announced=[],
        )

    def _continue_combat_damage_assignments(
        self,
        *,
        actors: Sequence[str],
        cursor: int,
        announced: Sequence[Mapping[str, Any]],
    ) -> None:
        """Collect CR 510.1/802.5 assignments in public APNAP order."""

        collected = [dict(value) for value in announced]
        ordered_actors = [
            seat for seat in actors if seat in self.active_seats
        ]
        while cursor < len(ordered_actors):
            seat = ordered_actors[cursor]
            automatic = self._automatic_combat_assignments([seat])
            if automatic is not None:
                self._record_combat_damage_announcement(
                    seat,
                    automatic,
                    announcement_index=cursor,
                    automatic=True,
                )
                collected.extend(automatic)
                cursor += 1
                continue

            self.permissions.issue(
                kind="combat.damage",
                role="pilot",
                actors=[seat],
                allowed_actions=["assign_damage"],
                payload_by_actor={
                    seat: {
                        "combat": self._combat_payload(
                            seat,
                            announced_assignments=collected,
                        ),
                        "instruction": (
                            "Assign damage for sources you control. Earlier "
                            "APNAP assignments are final and public."
                        ),
                    }
                },
                continuation={
                    "combat_damage_assignment_order": ordered_actors,
                    "combat_damage_assignment_cursor": cursor,
                    "announced_assignments": collected,
                },
            )
            return

        waiting = self._apply_combat_assignments(collected)
        if not waiting:
            self._grant_priority(self.state.active_player)

    def _record_combat_damage_announcement(
        self,
        seat: str,
        assignments: Sequence[Mapping[str, Any]],
        *,
        announcement_index: int,
        automatic: bool,
    ) -> None:
        canonical = [dict(value) for value in assignments]
        self._log(
            seat,
            "combat.damage.assigned",
            f"{seat} announced combat-damage assignments.",
            {
                "player": seat,
                "assignments": canonical,
                "announcement_index": announcement_index,
                "automatic": automatic,
                "damage_step": self.state.combat.damage_step_index + 1,
            },
            importance=1,
            changed_players=[seat],
        )

    def _complete_combat_damage(self, decision: Any) -> None:
        order = decision.continuation.get(
            "combat_damage_assignment_order"
        )
        if order is None:
            # Backward-compatible completion for a pending pre-v2 checkpoint.
            assignments: list[dict[str, Any]] = []
            for seat in decision.actors:
                assignments.extend(
                    self._validated_combat_damage_assignments(
                        seat,
                        decision.responses[seat].get("assignments") or [],
                    )
                )
            waiting = self._apply_combat_assignments(assignments)
            if not waiting:
                self._grant_priority(self.state.active_player)
            return

        actors = [str(value) for value in order]
        cursor = int(
            decision.continuation.get(
                "combat_damage_assignment_cursor", 0
            )
        )
        if cursor < 0 or cursor >= len(actors):
            raise GameRuleError(
                "Combat-damage assignment cursor is invalid"
            )
        seat = actors[cursor]
        if decision.actors != [seat]:
            raise GameRuleError(
                "Only the current APNAP player may assign combat damage"
            )
        assignments = self._validated_combat_damage_assignments(
            seat,
            decision.responses[seat].get("assignments") or [],
        )
        self._record_combat_damage_announcement(
            seat,
            assignments,
            announcement_index=cursor,
            automatic=False,
        )
        self._continue_combat_damage_assignments(
            actors=actors,
            cursor=cursor + 1,
            announced=[
                *(
                    dict(value)
                    for value in decision.continuation.get(
                        "announced_assignments", []
                    )
                ),
                *assignments,
            ],
        )

    def _validated_combat_damage_assignments(
        self,
        seat: str,
        submitted: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(submitted, Sequence)
            or isinstance(submitted, (str, bytes, Mapping))
        ):
            raise GameRuleError(
                "Combat-damage assignments must be an array"
            )
        source_options = self._combat_damage_source_options(seat)
        source_targets = {
            source: set(option["targets"])
            for source, option in source_options.items()
        }
        source_power = {
            source: int(option["power"])
            for source, option in source_options.items()
        }

        # These options are also projected to the assigning seat. Keep all
        # target and total validation authoritative here; the browser uses
        # them only to render controls and useful defaults.

        totals: dict[str, int] = {}
        canonical: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for raw in submitted:
            if not isinstance(raw, Mapping):
                raise GameRuleError(
                    "Each combat-damage assignment must be an object"
                )
            if set(raw) != {"source", "target", "amount"}:
                raise GameRuleError(
                    "Combat-damage assignment requires exactly source, "
                    "target, and amount"
                )
            if not isinstance(raw["source"], str):
                raise GameRuleError(
                    "Combat-damage assignment source must be a string"
                )
            if not isinstance(raw["target"], str):
                raise GameRuleError(
                    "Combat-damage assignment target must be a string"
                )
            source_ref = raw["source"]
            if source_ref not in source_targets:
                raise GameRuleError(
                    f"{source_ref or 'Object'} is not assigning combat damage"
                )
            if source_power[source_ref] <= 0:
                raise GameRuleError(
                    f"{source_ref} does not assign combat damage because "
                    "its power is 0 or less"
                )
            target_ref = raw["target"]
            if target_ref not in source_targets[source_ref]:
                raise GameRuleError(
                    f"{target_ref or 'Object'} is an illegal combat-damage "
                    f"target for {source_ref}"
                )
            value = raw["amount"]
            if not isinstance(value, int) or isinstance(value, bool):
                raise GameRuleError("Combat damage must be an integer")
            amount = value
            if amount < 0:
                raise GameRuleError("Damage cannot be negative")
            pair = (source_ref, target_ref)
            if pair in seen_pairs:
                raise GameRuleError(
                    "A combat-damage source/target pair may appear only once"
                )
            seen_pairs.add(pair)
            totals[source_ref] = totals.get(source_ref, 0) + amount
            canonical.append(
                {
                    "source": source_ref,
                    "target": target_ref,
                    "amount": amount,
                }
            )

        for source_ref, power in source_power.items():
            required = power if source_targets.get(source_ref) else 0
            assigned = totals.get(source_ref, 0)
            if assigned != required:
                raise GameRuleError(
                    f"{source_ref} must assign exactly {required} combat "
                    f"damage, not {assigned}"
                )

        typed_assignments = [
            DamageAssignment(
                source=str(item["source"]),
                target=str(item["target"]),
                amount=int(item["amount"]),
            )
            for item in canonical
        ]
        attacking_cards = [
            self.state.cards[object_id]
            for object_id in self.state.combat.attackers
            if object_id in self.state.cards
            and self.state.cards[object_id].zone == "battlefield"
            and self.state.cards[object_id].controller == seat
            and self.state.cards[object_id].ref in source_targets
        ]
        attacking_source_refs = frozenset(
            card.ref for card in attacking_cards
        )
        deathtouch_source_refs = frozenset(
            card.ref
            for card in attacking_cards
            if DEATHTOUCH in self._combat_keywords(card)
        )
        for attacker in attacking_cards:
            if (
                TRAMPLE not in self._combat_keywords(attacker)
                or attacker.object_id not in self.state.combat.blockers
            ):
                continue
            spill_target = str(
                self.state.combat.attackers[attacker.object_id]
            )
            blocker_refs: list[str] = []
            blocker_state: dict[str, CreatureDamageState] = {}
            for blocker_id in self.state.combat.blockers.get(
                attacker.object_id, []
            ):
                blocker = self.state.cards.get(blocker_id)
                if (
                    blocker is None
                    or blocker.zone != "battlefield"
                    or blocker.phased_out
                ):
                    continue
                blocker_refs.append(blocker.ref)
                blocker_state[blocker.ref] = CreatureDamageState(
                    toughness=self._numeric_stat(
                        blocker.object_id,
                        "toughness",
                    ),
                    marked_damage=blocker.marked_damage,
                )
            error = trample_assignment_error(
                attacker_ref=attacker.ref,
                spill_target=spill_target,
                blocker_refs=blocker_refs,
                assignments=typed_assignments,
                attacking_source_refs=attacking_source_refs,
                deathtouch_source_refs=deathtouch_source_refs,
                blocker_state=blocker_state,
            )
            if error is not None:
                raise GameRuleError(error)
        return canonical

    def _combat_damage_source_options(
        self, seat: str
    ) -> dict[str, dict[str, Any]]:
        source_targets: dict[str, set[str]] = {}
        source_power: dict[str, int] = {}
        for attacker_id, defender in self.state.combat.attackers.items():
            attacker = self.state.cards.get(attacker_id)
            if (
                attacker is None
                or attacker.zone != "battlefield"
                or attacker.controller != seat
                or attacker.phased_out
                or not self._assigns_combat_damage_this_step(attacker)
            ):
                continue
            types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(attacker).get("type_line")
                    or ""
                )
            )
            if "creature" not in types:
                continue
            was_blocked = attacker_id in self.state.combat.blockers
            if was_blocked:
                targets = set()
                for blocker_id in self.state.combat.blockers.get(
                    attacker_id, []
                ):
                    blocker = self.state.cards.get(blocker_id)
                    if (
                        blocker is None
                        or blocker.zone != "battlefield"
                        or blocker.phased_out
                    ):
                        continue
                    blocker_types, _, _ = self._type_parts(
                        str(
                            self._effective_card_data(blocker).get(
                                "type_line"
                            )
                            or ""
                        )
                    )
                    if "creature" in blocker_types:
                        targets.add(blocker.ref)
                if (
                    TRAMPLE in self._combat_keywords(attacker)
                    and self._combat_damage_target_exists(
                        str(defender), attacker_id=attacker.object_id
                    )
                ):
                    targets.add(str(defender))
            else:
                target = str(defender)
                targets = (
                    {target}
                    if self._combat_damage_target_exists(
                        target, attacker_id=attacker.object_id
                    )
                    else set()
                )
            source_targets[attacker.ref] = targets
            source_power[attacker.ref] = max(
                0,
                self._numeric_stat(attacker.object_id, "power"),
            )

        blocker_attackers: dict[str, set[str]] = {}
        for attacker_id, blocker_ids in self.state.combat.blockers.items():
            attacker = self.state.cards.get(attacker_id)
            if attacker is None or attacker.zone != "battlefield":
                continue
            for blocker_id in blocker_ids:
                blocker = self.state.cards.get(blocker_id)
                if (
                    blocker is None
                    or blocker.zone != "battlefield"
                    or blocker.controller != seat
                    or blocker.phased_out
                    or not self._assigns_combat_damage_this_step(blocker)
                ):
                    continue
                types, _, _ = self._type_parts(
                    str(
                        self._effective_card_data(blocker).get(
                            "type_line"
                        )
                        or ""
                    )
                )
                if "creature" not in types:
                    continue
                blocker_attackers.setdefault(blocker.ref, set()).add(
                    attacker.ref
                )
                source_power[blocker.ref] = max(
                    0,
                    self._numeric_stat(blocker.object_id, "power"),
                )
        source_targets.update(blocker_attackers)
        return {
            source: {
                "power": source_power[source],
                "targets": sorted(targets),
            }
            for source, targets in source_targets.items()
        }

    def _combat_damage_target_exists(
        self,
        target: str,
        *,
        attacker_id: str | None = None,
    ) -> bool:
        """Return whether an attack target is still a legal damage recipient.

        An attacked permanent leaving combat does not remove its attackers
        from combat (CR 506.4c), but an ordinary unblocked attacker then has
        no combat-damage recipient (CR 510.1b).  The declaration-time target
        kind and defending player keep that distinction authoritative.
        """

        if attacker_id is None:
            if target in self.state.players:
                return target in self.active_seats
            return any(
                card.ref == target
                and card.zone == "battlefield"
                and not card.phased_out
                for card in self.state.cards.values()
            )
        context = self.state.combat.attack_target_context.get(attacker_id)
        if context is None:
            context = self._attack_target_details(
                self.state.active_player, target
            )
        if context is None or context.get("target") != target:
            return False
        kind = context.get("kind")
        defender = context.get("defending_player")
        if kind == "player":
            return target == defender and target in self.active_seats
        card = next(
            (
                candidate
                for candidate in self.state.cards.values()
                if candidate.ref == target
                and candidate.zone == "battlefield"
                and not candidate.phased_out
            ),
            None,
        )
        if card is None or defender not in self.active_seats:
            return False
        card_types, _, _ = self._type_parts(
            str(self._effective_card_data(card).get("type_line") or "")
        )
        if kind == "planeswalker":
            return (
                "planeswalker" in card_types
                and card.controller == defender
            )
        if kind == "battle":
            return (
                "battle" in card_types
                and card.battle_protector == defender
            )
        return False

    def _combat_payload(
        self,
        seat: str | None = None,
        *,
        announced_assignments: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        payload = {
            "attackers": {self.state.cards[oid].ref: target for oid, target in self.state.combat.attackers.items()},
            "blockers": {self.state.cards[aid].ref: [self.state.cards[bid].ref for bid in bids] for aid, bids in self.state.combat.blockers.items()},
            "damage_step": self.state.combat.damage_step_index + 1,
            "first_strike_step": self.state.combat.first_strike_step,
            "announced_assignments": [
                dict(value) for value in announced_assignments
            ],
        }
        if seat is not None:
            payload["damage_sources"] = self._combat_damage_source_options(
                seat
            )
        return payload

    def _apply_combat_assignments(
        self,
        assignments: Sequence[Mapping[str, Any]],
        *,
        replacement_selections: Sequence[str | None] = (),
    ) -> bool:
        """Deal one simultaneous combat-damage batch and stabilize it.

        Returns ``True`` when replacement ordering, trigger ordering, another
        rules choice, a semantic stop, or game end prevents the ordinary
        priority grant.
        """

        proposals: list[DamageProposal] = []
        declared = [dict(value) for value in assignments]
        for index, assignment in enumerate(declared):
            source_ref = str(assignment.get("source") or "")
            source = next(
                (
                    card
                    for card in self.state.cards.values()
                    if card.ref == source_ref
                ),
                None,
            )
            if source is None:
                raise GameRuleError(f"Unknown damage source {source_ref}")
            amount = int(assignment.get("amount", 0))
            if amount < 0:
                raise GameRuleError("Damage cannot be negative")
            if amount == 0:
                # CR 120.8: zero produces no event or replacement window.
                continue
            target = str(assignment.get("target") or "")
            if source.zone != "battlefield":
                self._log(
                    source.controller,
                    "combat.damage.no_source",
                    (
                        f"{source.ref} assigned no combat damage because "
                        "it was no longer on the battlefield."
                    ),
                    {
                        "source": source.ref,
                        "target": target,
                        "amount": amount,
                    },
                    importance=1,
                )
                continue
            if not self._combat_damage_target_exists(target):
                self._log(
                    source.controller,
                    "combat.damage.no_target",
                    (
                        f"{source.ref} assigned no combat damage; {target} "
                        "was no longer a legal damage recipient."
                    ),
                    {
                        "source": source.ref,
                        "target": target,
                        "amount": amount,
                    },
                    importance=1,
                )
                continue
            try:
                proposals.append(
                    damage_proposal(
                        self,
                        proposal_id=(
                            f"damage.combat:{self.state.revision}:"
                            f"{self.state.event_sequence + 1}:{index}"
                        ),
                        actor=source.controller,
                        source_ref=source.ref,
                        target=target,
                        amount=amount,
                        combat=True,
                        reason="combat damage",
                        deathtouch=(
                            DEATHTOUCH in self._combat_keywords(source)
                        ),
                        damage_step=self.state.combat.damage_step_index + 1,
                        first_strike_step=(
                            self.state.combat.first_strike_step
                        ),
                    )
                )
            except DamageError as exc:
                raise GameRuleError(str(exc)) from exc

        try:
            result = resolve_damage_batch(
                self,
                proposals,
                replacement_selections=replacement_selections,
            )
        except ReplacementChoiceRequired as required:
            issue_combat_damage_replacement_choice(
                self,
                assignments=declared,
                selections=replacement_selections,
                required=required,
            )
            return True
        except DamageError as exc:
            raise GameRuleError(str(exc)) from exc

        self.state.combat.damage_assignments.extend(declared)
        dealt_assignments = [
            {
                "source": event.source,
                "target": event.target,
                "amount": event.dealt_amount,
            }
            for event in result.events
            if event.was_dealt
        ]
        for event in result.events:
            if not event.prevented_amount:
                continue
            self._log(
                event.target_controller,
                "combat.damage.prevented",
                (
                    f"{event.prevented_amount} damage from {event.source} "
                    f"to {event.target} was prevented."
                ),
                {
                    "source": event.source,
                    "target": event.target,
                    "assigned_amount": event.assigned_amount,
                    "dealt_amount": event.dealt_amount,
                    "prevented_amount": event.prevented_amount,
                    "applied_effects": list(event.applied_effects),
                },
                importance=1,
                changed_objects=(
                    [event.target_object_id]
                    if event.target_object_id is not None
                    else []
                ),
                changed_players=(
                    [event.target]
                    if event.target_kind == "player"
                    else []
                ),
            )
        self._log(
            None,
            "combat.damage",
            (
                "Combat damage was dealt."
                if dealt_assignments
                else "No combat damage was dealt."
            ),
            {
                "assignments": dealt_assignments,
                "declared_assignments": declared,
                "damage_step": self.state.combat.damage_step_index + 1,
                "first_strike_step": self.state.combat.first_strike_step,
                "damage_events": [
                    event.semantic_context() for event in result.events
                ],
            },
            importance=2,
            changed_objects=result.changed_objects,
            changed_players=result.changed_players,
        )
        if self._semantic_pause_annotation() is not None:
            return True
        return self._stabilize()

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

    def _enchant_target_schema(
        self,
        aura: CardInstance,
    ) -> dict[str, Any] | None:
        override = aura.annotations.get("enchant_target_schema")
        if isinstance(override, Mapping):
            return copy.deepcopy(dict(override))

        oracle = str(
            self._effective_card_data(aura).get("oracle_text") or ""
        )
        match = next(
            (
                re.fullmatch(
                    r"enchant (?P<restriction>.+?)\.?",
                    line.strip(),
                    re.IGNORECASE,
                )
                for line in oracle.splitlines()
                if line.strip().casefold().startswith("enchant ")
            ),
            None,
        )
        if match is None:
            return None
        restriction = match.group("restriction").strip().casefold()
        controller_relation = "any"
        for suffix, relation in (
            (" an opponent controls", "opponent"),
            (" opponent controls", "opponent"),
            (" you control", "you"),
        ):
            if restriction.endswith(suffix):
                restriction = restriction[: -len(suffix)].strip()
                controller_relation = relation
                break

        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "controller": controller_relation,
            "count": 1,
        }
        if restriction in {
            "creature card in a graveyard",
            "creature card in your graveyard",
        }:
            schema.update(
                {
                    "zones": ["graveyard"],
                    "categories": ["card"],
                    "creature": True,
                    "owner": (
                        "you"
                        if restriction.endswith("your graveyard")
                        else "any"
                    ),
                }
            )
            return schema
        if restriction == "card in a graveyard":
            schema.update(
                {
                    "zones": ["graveyard"],
                    "categories": ["card"],
                }
            )
            return schema
        if restriction == "nonland permanent":
            schema.update({"permanent": True, "land": False})
            return schema

        type_words = {
            "artifact",
            "battle",
            "creature",
            "enchantment",
            "land",
            "planeswalker",
        }
        alternatives = [
            value.strip()
            for value in re.split(r"\s+or\s+", restriction)
        ]
        if alternatives and all(
            value in type_words for value in alternatives
        ):
            schema["types_any"] = alternatives
            return schema
        all_types = restriction.split()
        if all_types and all(value in type_words for value in all_types):
            schema["types_all"] = all_types
            return schema
        if restriction == "permanent":
            schema["permanent"] = True
            return schema
        if restriction in {"player", "opponent"}:
            # Player attachment needs a non-card attachment identity and is
            # intentionally outside the currently reviewed subset.
            return None
        # A single subtype restriction (for example, "Shrine") can use the
        # same declarative target query.  More elaborate quality grammar stays
        # unresolved rather than being guessed.
        if re.fullmatch(r"[a-z][a-z'-]*", restriction):
            schema["subtypes_any"] = [restriction]
            return schema
        return None

    def _attachment_is_legal(
        self,
        attachment: CardInstance,
        *,
        subtypes: set[str],
    ) -> bool | None:
        if attachment.attached_to is None:
            return False
        target = self.state.cards.get(attachment.attached_to)
        if target is None or target.zone == "outside":
            return False

        schema: dict[str, Any] | None
        if "aura" in subtypes:
            schema = self._enchant_target_schema(attachment)
        elif "equipment" in subtypes:
            schema = {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "creature": True,
                "count": 1,
            }
        elif "fortification" in subtypes:
            schema = {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "land": True,
                "count": 1,
            }
        else:
            return target.zone == "battlefield"
        if schema is None:
            return None
        try:
            group = TargetGroup.from_mapping(schema)
        except ValueError:
            return None
        row = next(
            (
                candidate
                for candidate in self._target_candidate_rows(
                    attachment.controller,
                    group,
                )
                if str(candidate["ref"]) == target.ref
            ),
            None,
        )
        if row is None or not self._target_row_matches(
            attachment.controller,
            group,
            row,
            source_ref=attachment.ref,
            as_target=False,
        ):
            return False

        target_oracle = str(
            self._effective_card_data(target).get("oracle_text") or ""
        ).casefold()
        if "protection from everything" in target_oracle:
            return False
        if self._protection_colors(target).intersection(
            self._source_colors_for_ref(attachment.ref)
        ):
            return False
        return True

    def _has_world_supertype(self, card: CardInstance) -> bool:
        _, _, supertypes = self._type_parts(
            str(
                self._effective_card_data(card).get("type_line")
                or ""
            )
        )
        return "world" in supertypes

    def _refresh_world_supertype_timestamp(
        self,
        card: CardInstance,
        *,
        gained_at: int | None = None,
    ) -> bool:
        """Synchronize how long one battlefield object has been World."""

        if card.zone != "battlefield":
            card.world_supertype_timestamp = None
            return False
        if not self._has_world_supertype(card):
            card.world_supertype_timestamp = None
            return False
        if card.world_supertype_timestamp is None:
            card.world_supertype_timestamp = (
                int(gained_at)
                if gained_at is not None
                else self._next_zone_timestamp()
            )
            return True
        return False

    def _synchronize_world_supertype_timestamps(self) -> None:
        """Observe simultaneous gains/losses of the World supertype."""

        newly_world: list[CardInstance] = []
        for card in self.state.cards.values():
            if card.zone != "battlefield":
                if card.world_supertype_timestamp is not None:
                    card.world_supertype_timestamp = None
                continue
            if self._has_world_supertype(card):
                if card.world_supertype_timestamp is None:
                    newly_world.append(card)
            else:
                card.world_supertype_timestamp = None
        if newly_world:
            timestamp = self._next_zone_timestamp()
            for card in newly_world:
                card.world_supertype_timestamp = timestamp

    def _permanent_sba_snapshots(
        self,
    ) -> list[PermanentSnapshot]:
        snapshots: list[PermanentSnapshot] = []
        seen: set[str] = set()
        for seat in self.active_seats:
            for object_id in self.state.players[seat].zones["battlefield"]:
                if object_id in seen:
                    continue
                seen.add(object_id)
                card = self.state.cards[object_id]
                if card.zone != "battlefield" or card.phased_out:
                    continue
                data = self._effective_card_data(card)
                card_types, subtypes, supertypes = self._type_parts(
                    str(data.get("type_line") or "")
                )
                keywords = {
                    str(value).casefold()
                    for value in data.get("keywords", [])
                }
                snapshots.append(
                    PermanentSnapshot(
                        object_id=card.object_id,
                        card_types=frozenset(card_types),
                        subtypes=frozenset(subtypes),
                        world="world" in supertypes,
                        world_timestamp=(
                            card.world_supertype_timestamp
                        ),
                        toughness=(
                            self._numeric_stat(object_id, "toughness")
                            if "creature" in card_types
                            else None
                        ),
                        marked_damage=card.marked_damage,
                        deathtouch_damage=card.deathtouch_damage,
                        indestructible="indestructible" in keywords,
                        loyalty=(
                            int(card.counters.get("loyalty", 0))
                            if (
                                "planeswalker" in card_types
                                and (
                                    "loyalty" in card.counters
                                    or card.annotations.get(
                                        "loyalty_initialized"
                                    )
                                    or card.counters.get(
                                        "loyalty_initialized"
                                    )
                                )
                            )
                            else None
                        ),
                        defense=(
                            int(card.counters.get("defense", 0))
                            if "battle" in card_types
                            else None
                        ),
                        battle_trigger_pending=(
                            self._battle_trigger_pending(card)
                            if "battle" in card_types
                            else False
                        ),
                        attached_to=card.attached_to,
                        attachment_legal=(
                            self._attachment_is_legal(
                                card,
                                subtypes=subtypes,
                            )
                            if card.attached_to is not None
                            else False
                        ),
                        counters=dict(card.counters),
                        counter_maximums=(
                            counter_maximums_from_oracle(
                                str(data.get("oracle_text") or "")
                            )
                        ),
                    )
                )
        return snapshots

    def _object_sba_snapshots(self) -> list[ObjectSnapshot]:
        return [
            ObjectSnapshot(
                object_id=card.object_id,
                zone=card.zone,
                is_token=card.is_token,
                is_spell_copy=card.is_spell_copy,
                is_card_copy=card.is_card_copy,
            )
            for card in self.state.cards.values()
            if card.zone != "outside"
        ]

    def _detach_permanent(self, card: CardInstance) -> None:
        target = self.state.cards.get(card.attached_to or "")
        if target is not None and card.object_id in target.attachments:
            target.attachments.remove(card.object_id)
        card.attached_to = None

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

    def _repair_battle_protectors(self) -> str | None:
        """Apply or request the represented CR 704.5w-x protector repair."""

        attacked_targets = set(self.state.combat.attackers.values())
        for seat in self.active_seats:
            for object_id in list(
                self.state.players[seat].zones["battlefield"]
            ):
                battle = self.state.cards[object_id]
                if battle.zone != "battlefield" or battle.phased_out:
                    continue
                card_types, subtypes, _ = self._type_parts(
                    str(
                        self._effective_card_data(battle).get(
                            "type_line"
                        )
                        or ""
                    )
                )
                if "battle" not in card_types:
                    continue
                if not subtypes:
                    if battle.battle_protector != battle.controller:
                        battle.battle_protector = battle.controller
                        self._log(
                            battle.controller,
                            "state.battle_protector",
                            (
                                f"{battle.controller} became protector "
                                f"of {battle.ref}."
                            ),
                            {
                                "battle": battle.ref,
                                "protector": battle.controller,
                                "reason": "Battle has no Battle type",
                            },
                            importance=2,
                            changed_objects=[battle.object_id],
                            changed_players=[battle.controller],
                        )
                        return "changed"
                    continue
                if "siege" not in subtypes:
                    raise GameRuleError(
                        "The protector predicate for Battle type(s) "
                        f"{sorted(subtypes)} is not compiled"
                    )
                protector_valid = (
                    battle.battle_protector in self.active_seats
                    and battle.battle_protector != battle.controller
                )
                if protector_valid:
                    continue
                if (
                    battle.battle_protector != battle.controller
                    and battle.ref in attacked_targets
                ):
                    # CR 704.5w waits until no creature is attacking this
                    # Battle. CR 704.5x has no such exception when a Siege's
                    # controller is also its protector.
                    continue
                candidates = [
                    opponent
                    for opponent in self.active_seats
                    if opponent != battle.controller
                ]
                if not candidates:
                    self._move_cards_simultaneously(
                        [(battle.object_id, "graveyard")],
                        reason="no legal Battle protector",
                        log=False,
                    )
                    self._log(
                        battle.controller,
                        "state.battle_protector",
                        (
                            f"{battle.ref} had no legal protector and "
                            "went to its owner's graveyard."
                        ),
                        {
                            "battle": battle.ref,
                            "protector": None,
                            "reason": "no_legal_protector",
                        },
                        importance=2,
                        changed_objects=[battle.object_id],
                    )
                    return "changed"
                self.permissions.issue(
                    kind="state.battle_protector",
                    role="pilot",
                    actors=[battle.controller],
                    allowed_actions=["choose"],
                    payload_by_actor={
                        battle.controller: {
                            "battle": battle.ref,
                            "name": self.display_name(
                                battle.object_id
                            ),
                            "protectors": candidates,
                            "legal_actions": [
                                {
                                    "id": "choose",
                                    "action": "choose",
                                    "choice_schema": {
                                        "protector": {
                                            "type": "seat",
                                            "legal_seats": candidates,
                                            "required": True,
                                        }
                                    },
                                }
                            ],
                        }
                    },
                    continuation={
                        "object_id": battle.object_id,
                        "source_logical_object_id": (
                            battle.logical_object_id
                        ),
                        "candidates": candidates,
                    },
                )
                return "waiting"
        return None

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

            if self._remove_invalid_combat_objects():
                continue

            self._synchronize_world_supertype_timestamps()
            sba_batch = evaluate_state_based_actions(
                permanents=self._permanent_sba_snapshots(),
                objects=self._object_sba_snapshots(),
            )
            ordinary_move_to_grave = unique_preserving_order(
                [
                    *sba_batch.put_in_graveyard,
                    *sba_batch.destroy,
                ]
            )
            move_to_grave = unique_preserving_order(
                [
                    *ordinary_move_to_grave,
                    *sba_batch.world_rule,
                ]
            )
            if sba_batch.changed:
                world_rule_rows = [
                    {
                        "object": self.state.cards[object_id].ref,
                    }
                    for object_id in sba_batch.world_rule
                    if self.state.cards[object_id].zone
                    == "battlefield"
                ]
                world_rule_ids = set(sba_batch.world_rule)
                world_survivors = [
                    card.ref
                    for card in self.state.cards.values()
                    if card.zone == "battlefield"
                    and not card.phased_out
                    and card.world_supertype_timestamp is not None
                    and card.object_id not in world_rule_ids
                ]
                simultaneous = [
                    (object_id, "graveyard")
                    for object_id in move_to_grave
                    if self.state.cards[object_id].zone == "battlefield"
                ]
                if simultaneous:
                    self._move_cards_simultaneously(
                        simultaneous,
                        reason="state-based action",
                        log=False,
                    )
                detached: list[str] = []
                for object_id in sba_batch.detach:
                    card = self.state.cards[object_id]
                    if (
                        card.zone == "battlefield"
                        and card.attached_to is not None
                    ):
                        self._detach_permanent(card)
                        detached.append(object_id)
                counter_changes: list[dict[str, Any]] = []
                maximum_counter_changes: list[dict[str, Any]] = []
                counter_removals: dict[
                    tuple[str, str], int
                ] = {}
                for object_id, count in (
                    sba_batch.counter_pairs_to_remove
                ):
                    for kind in ("+1/+1", "-1/-1"):
                        key = (object_id, kind)
                        counter_removals[key] = max(
                            counter_removals.get(key, 0),
                            count,
                        )
                for object_id, kind, count in (
                    sba_batch.counter_maximums_to_remove
                ):
                    key = (object_id, kind)
                    # Counter-removal actions discovered from the same
                    # snapshot can name the same indistinguishable counters.
                    # Satisfy the greatest required removal for that kind
                    # rather than adding overlapping requirements.
                    counter_removals[key] = max(
                        counter_removals.get(key, 0),
                        count,
                    )
                counter_values_before: dict[
                    str, dict[str, int]
                ] = {}
                for object_id, _ in (
                    sba_batch.counter_pairs_to_remove
                ):
                    card = self.state.cards[object_id]
                    if card.zone != "battlefield":
                        continue
                    counter_values_before.setdefault(
                        object_id,
                        dict(card.counters),
                    )
                for object_id, _, _ in (
                    sba_batch.counter_maximums_to_remove
                ):
                    card = self.state.cards[object_id]
                    if card.zone != "battlefield":
                        continue
                    counter_values_before.setdefault(
                        object_id,
                        dict(card.counters),
                    )
                for (object_id, kind), count in sorted(
                    counter_removals.items()
                ):
                    card = self.state.cards[object_id]
                    if card.zone != "battlefield":
                        continue
                    remaining = max(
                        0,
                        int(card.counters.get(kind, 0)) - count,
                    )
                    if remaining:
                        card.counters[kind] = remaining
                    else:
                        card.counters.pop(kind, None)
                for object_id, count in (
                    sba_batch.counter_pairs_to_remove
                ):
                    card = self.state.cards[object_id]
                    if card.zone != "battlefield":
                        continue
                    counter_changes.append(
                        {
                            "object": card.ref,
                            "pairs_removed": count,
                        }
                    )
                for object_id, kind, count in (
                    sba_batch.counter_maximums_to_remove
                ):
                    card = self.state.cards[object_id]
                    if card.zone != "battlefield":
                        continue
                    before = int(
                        counter_values_before[object_id].get(
                            kind, 0
                        )
                    )
                    maximum_counter_changes.append(
                        {
                            "object": card.ref,
                            "counter": kind,
                            "before": before,
                            "maximum": before - count,
                            "required_removal": count,
                            "after": int(
                                card.counters.get(kind, 0)
                            ),
                        }
                    )
                ceased: list[dict[str, Any]] = []
                ceased_object_ids: list[str] = []
                for object_id in sba_batch.cease:
                    card = self.state.cards[object_id]
                    if card.zone == "outside":
                        continue
                    previous_zone = card.zone
                    if previous_zone == "stack":
                        self.state.stack = [
                            item
                            for item in self.state.stack
                            if item.card_object_id != card.object_id
                        ]
                    else:
                        self._remove_from_zone(card)
                    card.zone = "outside"
                    card.known_to = list(self.seats)
                    card.revealed_to = list(self.seats)
                    ceased.append(
                        {
                            "object": card.ref,
                            "kind": (
                                "token"
                                if card.is_token
                                else card.object_kind
                            ),
                            "zone": previous_zone,
                        }
                    )
                    ceased_object_ids.append(card.object_id)
                if ordinary_move_to_grave:
                    self._log(
                        None,
                        "state.creatures_died",
                        (
                            "State-based actions moved "
                            f"{len(move_to_grave)} permanent(s) to "
                            "graveyards."
                        ),
                        {
                            "objects": [
                                self.state.cards[object_id].ref
                                for object_id in ordinary_move_to_grave
                            ],
                            "put_in_graveyard": [
                                self.state.cards[object_id].ref
                                for object_id in (
                                    sba_batch.put_in_graveyard
                                )
                            ],
                            "destroyed": [
                                self.state.cards[object_id].ref
                                for object_id in sba_batch.destroy
                            ],
                        },
                        importance=2,
                        changed_objects=ordinary_move_to_grave,
                    )
                if world_rule_rows:
                    self._log(
                        None,
                        "state.world_rule",
                        (
                            "The world rule moved "
                            f"{len(world_rule_rows)} permanent(s) to "
                            "their owners' graveyards."
                        ),
                        {
                            "moved": world_rule_rows,
                            "survivors": world_survivors,
                        },
                        importance=2,
                        changed_objects=list(sba_batch.world_rule),
                        changed_players=sorted(
                            {
                                self.state.cards[object_id].owner
                                for object_id in (
                                    sba_batch.world_rule
                                )
                            }
                        ),
                    )
                if detached:
                    self._log(
                        None,
                        "state.attachments_unattached",
                        (
                            "State-based actions unattached "
                            f"{len(detached)} permanent(s)."
                        ),
                        {
                            "objects": [
                                self.state.cards[object_id].ref
                                for object_id in detached
                            ]
                        },
                        importance=2,
                        changed_objects=detached,
                    )
                if counter_changes:
                    self._log(
                        None,
                        "state.counters_annihilated",
                        (
                            "State-based actions removed opposing "
                            "+1/+1 and -1/-1 counters."
                        ),
                        {"changes": counter_changes},
                        importance=2,
                        changed_objects=[
                            object_id
                            for object_id, _ in (
                                sba_batch.counter_pairs_to_remove
                            )
                            if self.state.cards[object_id].zone
                            == "battlefield"
                        ],
                    )
                if maximum_counter_changes:
                    self._log(
                        None,
                        "state.counter_maximums",
                        (
                            "State-based actions enforced "
                            "maximum-counter abilities."
                        ),
                        {"changes": maximum_counter_changes},
                        importance=2,
                        changed_objects=[
                            object_id
                            for object_id, _, _ in (
                                sba_batch.counter_maximums_to_remove
                            )
                            if self.state.cards[object_id].zone
                            == "battlefield"
                        ],
                    )
                if ceased:
                    self._log(
                        None,
                        "state.objects_ceased",
                        (
                            "State-based actions caused "
                            f"{len(ceased)} token or copy object(s) to "
                            "cease to exist."
                        ),
                        {"objects": ceased},
                        importance=2,
                        changed_objects=ceased_object_ids,
                        changed_players=sorted(
                            {
                                self.state.cards[object_id].owner
                                for object_id in ceased_object_ids
                            }
                        ),
                    )
                continue

            protector_repair = self._repair_battle_protectors()
            if protector_repair == "waiting":
                return True
            if protector_repair == "changed":
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

    def _complete_battle_protector_choice(
        self,
        decision: Any,
    ) -> None:
        seat = decision.actors[0]
        object_id = str(decision.continuation["object_id"])
        battle = self.state.cards.get(object_id)
        if (
            battle is None
            or battle.zone != "battlefield"
            or battle.controller != seat
            or battle.logical_object_id
            != str(
                decision.continuation[
                    "source_logical_object_id"
                ]
            )
        ):
            raise GameRuleError(
                "The Battle protector choice no longer matches that "
                "battlefield object"
            )
        protector = str(
            decision.responses[seat].get("protector")
            or decision.responses[seat].get("player")
            or ""
        )
        candidates = {
            str(value)
            for value in decision.continuation.get(
                "candidates", []
            )
        }
        if protector not in candidates or protector not in self.active_seats:
            raise GameRuleError(
                "Choose one of the legal Battle protectors"
            )
        battle.battle_protector = protector
        self._log(
            seat,
            "state.battle_protector",
            f"{protector} became protector of {battle.ref}.",
            {
                "battle": battle.ref,
                "protector": protector,
                "reason": "state-based protector repair",
            },
            importance=2,
            changed_objects=[battle.object_id],
            changed_players=[seat, protector],
        )
        self._stabilize()

    def _eliminate_players(self, seats: Sequence[str], *, reason: str) -> None:
        unique = [seat for seat in unique_preserving_order(seats) if seat in self.active_seats]
        if not unique:
            return
        departing_monarch = self.state.monarch in unique
        monarch_before_departure = self.state.monarch
        active_before_departure = self.state.active_player
        for seat in unique:
            player = self.state.players[seat]
            player.in_game = False
            self.state.eliminated_players.append(seat)
            # Objects owned by the player leave the game.
            # Checkpoints are serialized with sorted mapping keys, while a
            # continuously running game retains construction order. Zone
            # timestamps are authoritative, so elimination must not allocate
            # them according to incidental dictionary insertion order.
            for card in sorted(
                self.state.cards.values(),
                key=lambda value: (value.ref, value.object_id),
            ):
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
            for card in sorted(
                self.state.cards.values(),
                key=lambda value: (value.ref, value.object_id),
            ):
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
        if departing_monarch:
            if not remaining:
                previous = self.state.monarch
                self.state.monarch = None
                self._log(
                    None,
                    "monarch.change",
                    "No player is the monarch.",
                    {
                        "player": None,
                        "previous": previous,
                        "reason": "the monarch left the game",
                    },
                    importance=2,
                    changed_players=(
                        [str(previous)] if previous is not None else []
                    ),
                )
            else:
                successor = (
                    active_before_departure
                    if active_before_departure in remaining
                    else self._next_active_after(
                        str(
                            active_before_departure
                            or monarch_before_departure
                            or self.state.turn_order[-1]
                        )
                    )
                )
                self.become_monarch(
                    str(successor),
                    reason="the monarch left the game",
                )
        self.state.combat.defending_players = [
            seat
            for seat in self.state.combat.defending_players
            if seat in remaining
        ]
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
        try:
            typed_plan = default_semantic_interpreter().lower_for_seats(
                effect,
                actor=actor,
                default_reason=reason,
                seats=self.seats,
                active_seats=self.active_seats,
                apnap_order=self.apnap_order(),
            )
        except SemanticNodeError as exc:
            raise GameRuleError(str(exc)) from exc
        if typed_plan is not None:
            return execute_intent_plan(self, typed_plan)
        if op == "goad":
            self._require_seat(actor, in_game=True)
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            card_types, _, _ = self._type_parts(
                str(self._effective_card_data(card).get("type_line") or "")
            )
            if "creature" not in card_types:
                raise GameRuleError("Only a creature can be goaded")
            prohibition = self._goad_prohibition_source(card)
            if prohibition is not None:
                self._log(
                    actor,
                    "permanent.goad.prevented",
                    f"{card.ref} can't be goaded.",
                    {
                        "object": card.ref,
                        "player": actor,
                        "source": prohibition.ref,
                        "reason": reason,
                    },
                    importance=1,
                )
                return card.ref
            existing = next(
                (
                    designation
                    for designation in self._active_goad_designations(card)
                    if designation.player == actor
                ),
                None,
            )
            if existing is not None:
                self._log(
                    actor,
                    "permanent.goad.redundant",
                    f"{card.ref} was already goaded by {actor}.",
                    {
                        "object": card.ref,
                        "player": actor,
                        "reason": reason,
                    },
                    importance=1,
                )
                return card.ref
            designation = GoadDesignation(
                player=actor,
                expires_at_turns_begun=(
                    self.state.players[actor].turns_begun + 1
                ),
                created_turn_sequence=self.state.turn_sequence,
            )
            card.goaded_by.append(designation)
            self._log(
                actor,
                "permanent.goad",
                f"{card.ref} was goaded by {actor}.",
                {
                    "object": card.ref,
                    "player": actor,
                    "expires_at_turns_begun": (
                        designation.expires_at_turns_begun
                    ),
                    "reason": reason,
                },
                importance=2,
                changed_objects=[card.object_id],
            )
            return card.ref
        if op in {
            "next_spell_improvise",
            "next_spell_uncounterable",
        }:
            seat = str(effect.get("player") or actor)
            self.state.players[seat].stats[op] = True
            self._log(
                actor,
                "effect.next_spell",
                (
                    f"{seat}'s next spell has "
                    + (
                        "improvise."
                        if op == "next_spell_improvise"
                        else "can't be countered."
                    )
                ),
                {"player": seat, "effect": op, "reason": reason},
                importance=1,
                changed_players=[seat],
            )
            return True
        if op == "veil_of_summer":
            seat = str(effect.get("player") or actor)
            opponent_cast_blue_or_black = any(
                event.turn_sequence == self.state.turn_sequence
                and event.code == "stack.cast"
                and event.actor in self.active_seats
                and event.actor != seat
                and {"U", "B"}.intersection(
                    {
                        str(value).upper()
                        for value in event.details.get("colors", [])
                    }
                )
                for event in self.state.events
            )
            if opponent_cast_blue_or_black:
                self.draw(seat, 1, reason=reason)
            player = self.state.players[seat]
            player.stats["spells_cant_be_countered_until_end"] = True
            player.stats["hexproof_from_colors_until_end"] = ["U", "B"]
            self._log(
                actor,
                "effect.veil",
                f"{seat} gained Veil of Summer's turn-long effects.",
                {
                    "player": seat,
                    "drew": opponent_cast_blue_or_black,
                    "colors": ["U", "B"],
                },
                importance=2,
                changed_players=[seat],
            )
            return opponent_cast_blue_or_black
        if op == "add_counter_selected":
            counter = str(effect.get("counter") or "").strip()
            amount = int(effect.get("amount", 1))
            if not counter or amount < 0:
                raise GameRuleError("Counter effect requires a name and nonnegative amount")
            try:
                results = place_counters_on_refs(
                    self,
                    actor=actor,
                    object_refs=tuple(
                        str(value) for value in effect.get("cards") or ()
                    ),
                    counter_name=counter,
                    amount=amount,
                    selections=tuple(
                        effect.get("_replacement_selections") or ()
                    ),
                    reason=reason,
                    source_ref=str(effect.get("source") or "") or None,
                )
            except CounterPlacementError as exc:
                raise GameRuleError(str(exc)) from exc
            return [
                self.state.cards[result.object_id].ref
                for result in results
            ]
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
            # CR 403.2 supplies battlefield scope when a spell or ability
            # doesn't name another zone.  The operation names below carry
            # that ordinary scope; ``move`` and ``exile`` remain explicitly
            # zone-polymorphic because reviewed target schemas and resolving
            # object instructions use them for named nonbattlefield zones.
            implicit_zones = {
                "sacrifice": {"battlefield"},
                "destroy": {"battlefield"},
                "bounce": {"battlefield"},
                "discard": {"hand"},
            }
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones=implicit_zones.get(op),
            )
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
                tapped=(
                    bool(effect["tapped"])
                    if "tapped" in effect
                    else None
                ),
                position=(
                    effect["position"]
                    if effect.get("position") is not None
                    else "top"
                ),
                reason=reason,
                semantic_events=True,
                replacement_selections=tuple(
                    effect.get("_replacement_selections") or ()
                ),
            )
        if op == "move_if_in_zone":
            expected_zone = str(effect.get("from") or "")
            try:
                card = self._resolve_object(
                    actor,
                    str(effect["card"]),
                )
            except GameRuleError:
                self._log(
                    actor,
                    "effect.linked_object_missing",
                    "A linked object no longer exists in the game.",
                    {
                        "object": str(effect["card"]),
                        "expected_zone": expected_zone,
                        "reason": "object_absent",
                    },
                    importance=2,
                )
                return None
            if not expected_zone or card.zone != expected_zone:
                return None
            expected_counter = effect.get(
                "expected_zone_change_counter"
            )
            expected_identity = effect.get(
                "expected_object_identity"
            )
            identity_mismatch = (
                expected_counter is not None
                and card.zone_change_counter
                != int(expected_counter)
            ) or (
                expected_identity is not None
                and card.logical_object_id
                != str(expected_identity)
            )
            if identity_mismatch:
                self._log(
                    actor,
                    "effect.linked_object_missing",
                    (
                        f"{card.ref} is no longer the object linked by "
                        "the effect."
                    ),
                    {
                        "object": card.ref,
                        "expected_zone": expected_zone,
                        "reason": "object_identity_changed",
                    },
                    importance=2,
                    changed_objects=[card.object_id],
                )
                return None
            return self.move_card(
                card.object_id,
                str(effect.get("destination") or "graveyard"),
                controller=effect.get("controller"),
                tapped=(
                    bool(effect["tapped"])
                    if "tapped" in effect
                    else None
                ),
                position=(
                    effect["position"]
                    if effect.get("position") is not None
                    else "top"
                ),
                reason=reason,
                semantic_events=True,
                replacement_selections=tuple(
                    effect.get("_replacement_selections") or ()
                ),
            )
        if op == "animate_dead_prepare":
            aura = self._resolve_object(
                actor,
                str(effect["aura"]),
                zones={"stack"},
            )
            target = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"graveyard"},
            )
            types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(target).get(
                        "type_line"
                    )
                    or ""
                )
            )
            if "creature" not in types:
                raise GameRuleError(
                    "Animate Dead requires a creature card in a graveyard"
                )
            aura.annotations["pending_aura_target"] = target.ref
            return target.ref
        if op == "bestow_prepare":
            aura = self._resolve_object(
                actor,
                str(effect["aura"]),
                zones={"stack"},
            )
            target = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(target).get(
                        "type_line"
                    )
                    or ""
                )
            )
            if "creature" not in types:
                raise GameRuleError(
                    "Bestow requires a creature target"
                )
            aura.annotations["bestowed"] = True
            aura.annotations["pending_aura_target"] = target.ref
            aura.annotations["pending_aura_zone"] = "battlefield"
            return target.ref
        if op == "animate_dead_reanimate":
            aura = self._resolve_object(
                actor,
                str(effect["aura"]),
                zones={"battlefield"},
                controlled_only=True,
            )
            target_id = aura.attached_to
            if target_id not in self.state.cards:
                return None
            creature = self.state.cards[target_id]
            if creature.zone != "graveyard":
                return None
            types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(creature).get(
                        "type_line"
                    )
                    or ""
                )
            )
            if "creature" not in types:
                return None
            self.move_card(
                creature.object_id,
                "battlefield",
                controller=actor,
                reason="Animate Dead",
                semantic_events=True,
            )
            aura.attached_to = creature.object_id
            if aura.object_id not in creature.attachments:
                creature.attachments.append(aura.object_id)
            aura.annotations["enchant_target_schema"] = {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "creature": True,
                "count": 1,
            }
            aura.annotations["animate_dead_creature"] = (
                creature.object_id
            )
            self._log(
                actor,
                "animate_dead.reanimate",
                (
                    f"{actor} returned {creature.ref} and attached "
                    f"{aura.ref} to it."
                ),
                {
                    "aura": aura.ref,
                    "creature": creature.ref,
                },
                importance=2,
                changed_objects=[aura.object_id, creature.object_id],
                changed_players=[actor],
            )
            return creature.ref
        if op == "attach":
            equipment_value = str(
                effect.get("equipment") or effect.get("source")
            )
            creature_value = str(effect["creature"])

            def attachment_object(value: str) -> CardInstance:
                identity_matches = [
                    card
                    for card in self.state.cards.values()
                    if card.object_id == value
                    or card.ref.casefold() == value.casefold()
                ]
                if len(identity_matches) == 1:
                    return identity_matches[0]
                return self._resolve_object(
                    actor,
                    value,
                    zones={"battlefield"},
                )

            equipment = attachment_object(equipment_value)
            if equipment.zone != "battlefield":
                self._log(
                    actor,
                    "attachment.no_effect",
                    (
                        f"{equipment.ref} could not become attached because "
                        "it was no longer on the battlefield."
                    ),
                    {
                        "equipment": equipment.ref,
                        "creature": creature_value,
                        "reason": reason,
                        "result": "equipment_not_on_battlefield",
                    },
                    importance=2,
                )
                return None
            creature = attachment_object(creature_value)
            if creature.zone != "battlefield":
                self._log(
                    actor,
                    "attachment.no_effect",
                    (
                        f"{equipment.ref} could not become attached because "
                        f"{creature.ref} was no longer on the battlefield."
                    ),
                    {
                        "equipment": equipment.ref,
                        "creature": creature.ref,
                        "reason": reason,
                        "result": "creature_not_on_battlefield",
                    },
                    importance=2,
                )
                return None
            equipment_types, equipment_subtypes, _ = self._type_parts(
                str(
                    self._effective_card_data(equipment).get("type_line")
                    or ""
                )
            )
            creature_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(creature).get("type_line")
                    or ""
                )
            )
            if (
                "artifact" not in equipment_types
                or "equipment" not in equipment_subtypes
                or "creature" not in creature_types
            ):
                raise GameRuleError(
                    "Attach requires an Equipment and a creature"
                )
            if equipment.attached_to in self.state.cards:
                previous = self.state.cards[equipment.attached_to]
                if equipment.object_id in previous.attachments:
                    previous.attachments.remove(equipment.object_id)
            equipment.attached_to = creature.object_id
            if equipment.object_id not in creature.attachments:
                creature.attachments.append(equipment.object_id)
            self._log(
                actor,
                "attachment.attach",
                f"{equipment.ref} became attached to {creature.ref}.",
                {
                    "equipment": equipment.ref,
                    "creature": creature.ref,
                    "reason": reason,
                },
                importance=2,
                changed_objects=[
                    equipment.object_id,
                    creature.object_id,
                ],
            )
            return creature.ref
        if op == "welder_exchange":
            battlefield_ref = effect.get("battlefield_card")
            graveyard_ref = effect.get("graveyard_card")
            if not battlefield_ref or not graveyard_ref:
                return None
            try:
                battlefield_card = self._resolve_object(
                    actor,
                    str(battlefield_ref),
                    zones={"battlefield"},
                )
                graveyard_card = self._resolve_object(
                    actor,
                    str(graveyard_ref),
                    zones={"graveyard"},
                )
            except GameRuleError:
                return None
            battlefield_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(battlefield_card).get(
                        "type_line"
                    )
                    or ""
                )
            )
            graveyard_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(graveyard_card).get(
                        "type_line"
                    )
                    or ""
                )
            )
            if (
                "artifact" not in battlefield_types
                or "artifact" not in graveyard_types
                or battlefield_card.controller != graveyard_card.owner
            ):
                return None
            self._move_cards_simultaneously(
                [
                    (battlefield_card.object_id, "graveyard"),
                    (graveyard_card.object_id, "battlefield"),
                ],
                reason=reason,
                log=True,
            )
            return [battlefield_card.ref, graveyard_card.ref]
        if op == "mill":
            seat = str(effect.get("player") or actor)
            self._require_seat(seat, in_game=True)
            count = max(0, int(effect.get("count", 1)))
            library = self.state.players[seat].zones["library"]
            object_ids = list(reversed(library[-count:])) if count else []
            moved = self._move_cards_simultaneously(
                [(object_id, "graveyard") for object_id in object_ids],
                reason=reason,
                log=False,
            )
            self._log(
                actor,
                "card.mill",
                f"{seat} milled {len(moved)} card(s).",
                {
                    "player": seat,
                    "count": len(moved),
                    "objects": [card.ref for card in moved],
                    "reason": reason,
                },
                importance=1,
                changed_objects=[card.object_id for card in moved],
                changed_players=[seat],
            )
            return [card.ref for card in moved]
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
        if op == "shuffle_graveyard_bottom_random":
            raw_players = effect.get("players")
            players = (
                [str(value) for value in raw_players]
                if isinstance(raw_players, Sequence)
                and not isinstance(raw_players, (str, bytes))
                else (
                    [str(raw_players)]
                    if raw_players
                    else []
                )
            )
            moved_by_player: dict[str, list[str]] = {}
            for seat in players:
                if seat not in self.active_seats:
                    continue
                graveyard_ids = list(
                    self.state.players[seat].zones["graveyard"]
                )
                if not graveyard_ids:
                    moved_by_player[seat] = []
                    continue
                randomizer = random.Random(
                    f"{self.state.config.seed}|{self.state.turn_sequence}|"
                    f"{seat}|graveyard-bottom|{self.state.event_sequence}"
                )
                randomizer.shuffle(graveyard_ids)
                self._move_cards_simultaneously(
                    [
                        (object_id, "library")
                        for object_id in graveyard_ids
                    ],
                    reason=reason,
                    log=False,
                )
                library = self.state.players[seat].zones["library"]
                moved_set = set(graveyard_ids)
                remaining_ids = [
                    object_id
                    for object_id in library
                    if object_id not in moved_set
                ]
                library[:] = [*graveyard_ids, *remaining_ids]
                moved_by_player[seat] = [
                    self.state.cards[object_id].ref
                    for object_id in graveyard_ids
                ]
                self._log(
                    actor,
                    "graveyard.bottom",
                    (
                        f"{seat} put {len(graveyard_ids)} graveyard "
                        "card(s) on the bottom in a random order."
                    ),
                    {
                        "player": seat,
                        "count": len(graveyard_ids),
                        "reason": reason,
                    },
                    importance=2,
                    changed_objects=graveyard_ids,
                    changed_players=[seat],
                )
            return moved_by_player
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
            if amount < 0:
                raise GameRuleError("Damage cannot be negative")
            if amount == 0:
                return 0
            try:
                proposal = damage_proposal(
                    self,
                    proposal_id=(
                        f"damage.effect:{self.state.revision}:"
                        f"{self.state.event_sequence + 1}:0"
                    ),
                    actor=actor,
                    source_ref=(
                        str(effect["source"])
                        if effect.get("source") is not None
                        else None
                    ),
                    target=target,
                    amount=amount,
                    combat=False,
                    reason=reason,
                    unpreventable=bool(effect.get("unpreventable", False)),
                    deathtouch=bool(effect.get("deathtouch", False)),
                )
                result = resolve_damage_batch(
                    self,
                    (proposal,),
                    replacement_selections=tuple(
                        effect.get("_replacement_selections") or ()
                    ),
                )
            except DamageError as exc:
                raise GameRuleError(str(exc)) from exc
            event = result.events[0]
            self._log(
                actor,
                (
                    "effect.damage"
                    if event.was_dealt
                    else "effect.damage.prevented"
                ),
                (
                    f"{event.target} took {event.dealt_amount} damage."
                    if event.was_dealt
                    else f"Damage to {event.target} was prevented."
                ),
                {
                    "source": event.source,
                    "target": event.target,
                    "assigned_amount": event.assigned_amount,
                    "amount": event.dealt_amount,
                    "prevented_amount": event.prevented_amount,
                    "reason": reason,
                    "applied_effects": list(event.applied_effects),
                    "damage_event": event.semantic_context(),
                },
                importance=2,
                changed_objects=result.changed_objects,
                changed_players=result.changed_players,
            )
            return event.dealt_amount
        if op == "damage_each_opponent":
            amount = int(effect.get("amount", 0))
            if amount < 0:
                raise GameRuleError("Damage cannot be negative")
            if amount == 0:
                return 0
            opponents = [
                seat
                for seat in self.active_seats
                if seat != actor
            ]
            try:
                proposals = tuple(
                    damage_proposal(
                        self,
                        proposal_id=(
                            f"damage.effect:{self.state.revision}:"
                            f"{self.state.event_sequence + 1}:{index}"
                        ),
                        actor=actor,
                        source_ref=(
                            str(effect["source"])
                            if effect.get("source") is not None
                            else None
                        ),
                        target=opponent,
                        amount=amount,
                        combat=False,
                        reason=reason,
                        unpreventable=bool(
                            effect.get("unpreventable", False)
                        ),
                    )
                    for index, opponent in enumerate(opponents)
                )
                result = resolve_damage_batch(
                    self,
                    proposals,
                    replacement_selections=tuple(
                        effect.get("_replacement_selections") or ()
                    ),
                )
            except DamageError as exc:
                raise GameRuleError(str(exc)) from exc
            self._log(
                actor,
                "effect.damage",
                f"Each opponent of {actor} was dealt damage.",
                {
                    "opponents": opponents,
                    "assigned_amount": amount,
                    "dealt_amount": result.dealt_amount,
                    "reason": reason,
                    "damage_events": [
                        event.semantic_context() for event in result.events
                    ],
                },
                importance=2,
                changed_players=result.changed_players,
            )
            return result.dealt_amount

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
        if op == "lose_life_each_opponent":
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
                "effect.life",
                f"Each opponent of {actor} lost {amount} life.",
                {
                    "opponents": opponents,
                    "delta": -amount,
                    "reason": reason,
                },
                importance=2,
                changed_players=opponents,
            )
            return amount
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
        if op == "scute_swarm_token":
            controller = str(effect.get("controller") or actor)
            land_count = sum(
                1
                for object_id in self.state.players[
                    controller
                ].zones["battlefield"]
                if self.state.cards[object_id].controller == controller
                and "land"
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[0]
            )
            if land_count >= int(effect.get("threshold", 6)):
                return self.create_token(
                    controller,
                    name="Scute Swarm",
                    copy_of=str(effect["source"]),
                    reason=reason,
                )
            return self.create_token(
                controller,
                name="Insect",
                characteristics={
                    "type_line": "Token Creature — Insect",
                    "colors": ["G"],
                    "power": "1",
                    "toughness": "1",
                },
                reason=reason,
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
        if op == "control_next_turn":
            target = str(effect.get("player") or "")
            if target not in self.active_seats:
                raise GameRuleError(
                    "Turn-control effect requires an active player"
                )
            self.state.players[target].stats[
                "next_turn_controlled_by"
            ] = actor
            self._log(
                actor,
                "turn.control.scheduled",
                (
                    f"{actor} will control {target} during that "
                    "player's next turn."
                ),
                {
                    "controller": actor,
                    "player": target,
                    "reason": reason,
                },
                importance=3,
                changed_players=[actor, target],
            )
            return target
        if op == "protection_from_everything_until_next_turn":
            seat = str(effect.get("player") or actor)
            self._require_seat(seat, in_game=True)
            self.state.players[seat].stats[
                "protection_from_everything_until_next_turn"
            ] = True
            self._log(
                actor,
                "player.protection",
                (
                    f"{seat} gained protection from everything until "
                    "their next turn."
                ),
                {
                    "player": seat,
                    "duration": "until_next_turn",
                    "reason": reason,
                },
                importance=2,
                changed_players=[seat],
            )
            return seat
        if op == "end_turn":
            self._end_turn_now(actor=actor, reason=reason)
            return None
        if op == "create_daretti_emblem":
            player = self.state.players[actor]
            self.create_emblem(
                actor,
                abilities=[
                    (
                        "Whenever an artifact is put into your "
                        "graveyard from the battlefield, return that "
                        "card to the battlefield at the beginning of "
                        "the next end step."
                    )
                ],
                display_label="Daretti, Scrap Savant emblem",
                semantic_key="builtin:daretti-emblem",
                reason=reason,
            )
            player.stats["daretti_emblems"] = (
                int(player.stats.get("daretti_emblems", 0)) + 1
            )
            return player.stats["daretti_emblems"]
        if op == "grant_urzas_saga_chapter":
            source = self._resolve_object(
                actor,
                str(effect.get("source") or ""),
                zones={"battlefield"},
                controlled_only=True,
            )
            chapter = int(effect.get("chapter", 0))
            if source.printed_name != "Urza's Saga" or chapter not in {
                1,
                2,
            }:
                raise GameRuleError(
                    "Urza's Saga chapter grant is not valid"
                )
            source.annotations[
                f"urzas_saga_chapter_{chapter}"
            ] = True
            self._log(
                actor,
                "saga.ability.gained",
                f"{source.ref} gained its chapter {chapter} ability.",
                {
                    "source": source.ref,
                    "chapter": chapter,
                    "reason": reason,
                },
                importance=2,
                changed_objects=[source.object_id],
                changed_players=[actor],
            )
            return chapter
        if op == "return_transformed":
            source = self._resolve_object(
                actor,
                str(effect.get("card") or effect.get("source") or ""),
                zones={"exile"},
            )
            record = self.card_record(source)
            if record is None or len(record.faces) < 2:
                raise GameRuleError(
                    "Return transformed requires a transforming card"
                )
            self.move_card(
                source.object_id,
                "battlefield",
                controller=source.owner,
                enter_face=str(record.faces[1].get("name") or ""),
                reason=reason,
                semantic_events=True,
            )
            return source.ref
        if op == "demonic_junker_resolve":
            source = self._resolve_object(
                actor,
                str(effect.get("source") or ""),
            )
            changes: list[tuple[str, str]] = []
            destroyed_controlled = False
            for raw_ref in effect.get("cards") or []:
                if raw_ref is None:
                    continue
                try:
                    creature = self._resolve_object(
                        actor,
                        str(raw_ref),
                        zones={"battlefield"},
                    )
                except GameRuleError:
                    continue
                types, _, _ = self._type_parts(
                    str(
                        self._effective_card_data(creature).get(
                            "type_line"
                        )
                        or ""
                    )
                )
                keywords = {
                    str(value).casefold()
                    for value in self._effective_card_data(creature).get(
                        "keywords", []
                    )
                }
                if (
                    "creature" not in types
                    or "indestructible" in keywords
                ):
                    continue
                destroyed_controlled = (
                    destroyed_controlled
                    or creature.controller == actor
                )
                changes.append((creature.object_id, "graveyard"))
            if changes:
                self._move_cards_simultaneously(
                    changes,
                    reason=reason,
                    log=True,
                )
            if (
                destroyed_controlled
                and source.zone == "battlefield"
                and source.controller == actor
            ):
                source.counters["+1/+1"] = (
                    int(source.counters.get("+1/+1", 0)) + 2
                )
            return [
                self.state.cards[object_id].ref
                for object_id, _ in changes
            ]
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
            copy_source = effect.get("copy_of")
            token_name = (
                str(effect["name"])
                if "name" in effect
                else ("" if copy_source else "Token")
            )
            return self.create_token(
                str(effect.get("controller") or actor),
                name=token_name,
                quantity=int(effect.get("quantity", 1)),
                tapped=bool(effect.get("tapped", False)),
                attacking=effect.get("attacking"),
                copy_of=copy_source,
                characteristics=dict(effect.get("characteristics") or {}),
                temporary_keywords=list(effect.get("temporary_keywords") or []),
                reason=reason,
                replacement_selections=tuple(
                    effect.get("_replacement_selections") or ()
                ),
            )
        if op == "create_token_if_no_controlled_subtype":
            controller = str(effect.get("controller") or actor)
            subtype = str(effect.get("subtype") or "").casefold()
            if not subtype:
                raise GameRuleError(
                    "Conditional token effect requires a subtype"
                )
            if any(
                self.state.cards[object_id].controller == controller
                and subtype
                in self._type_parts(
                    str(
                        self._effective_card_data(object_id).get(
                            "type_line"
                        )
                        or ""
                    )
                )[1]
                for object_id in self.state.players[
                    controller
                ].zones["battlefield"]
            ):
                return []
            return self.create_token(
                controller,
                name=str(effect.get("name") or subtype.title()),
                quantity=int(effect.get("quantity", 1)),
                tapped=bool(effect.get("tapped", False)),
                characteristics=dict(
                    effect.get("characteristics") or {}
                ),
                reason=reason,
            )
        if op == "add_type_until_end_of_turn":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            card_type = str(effect.get("type") or "").strip().title()
            if not card_type:
                raise GameRuleError("Temporary type effect requires a type")
            until_end = card.annotations.setdefault("until_end_of_turn", {})
            until_end["add_types"] = unique_preserving_order(
                [
                    *list(until_end.get("add_types") or []),
                    card_type,
                ]
            )
            self._log(
                actor,
                "permanent.type",
                f"{card.ref} became a {card_type} in addition to its other types until end of turn.",
                {
                    "object": card.ref,
                    "type": card_type,
                    "reason": reason,
                },
                importance=1,
                changed_objects=[card.object_id],
            )
            return card.ref
        if op == "add_subtype_until_end_of_turn":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            subtype = str(effect.get("subtype") or "").strip().title()
            if not subtype:
                raise GameRuleError(
                    "Temporary subtype effect requires a subtype"
                )
            until_end = card.annotations.setdefault(
                "until_end_of_turn",
                {},
            )
            until_end["add_subtypes"] = unique_preserving_order(
                [
                    *list(until_end.get("add_subtypes") or []),
                    subtype,
                ]
            )
            self._log(
                actor,
                "permanent.subtype",
                (
                    f"{card.ref} became a {subtype} in addition to "
                    "its other types until end of turn."
                ),
                {
                    "object": card.ref,
                    "subtype": subtype,
                    "reason": reason,
                },
                importance=1,
                changed_objects=[card.object_id],
            )
            return card.ref
        if op == "copy_until_end_of_turn":
            source = self._resolve_object(
                actor,
                str(effect.get("source") or effect.get("card")),
                zones={"battlefield"},
            )
            target = self._resolve_object(
                actor,
                str(effect.get("target")),
            )
            until_end = source.annotations.setdefault(
                "until_end_of_turn",
                {},
            )
            if "copy_overrides_previous" not in until_end:
                until_end["copy_overrides_previous"] = copy.deepcopy(
                    source.annotations.get("copy_overrides")
                )
            characteristics = self._copyable_characteristics(target)
            if effect.get("except_nonlegendary"):
                type_line = str(
                    characteristics.get("type_line") or ""
                )
                characteristics["type_line"] = re.sub(
                    r"\bLegendary\s+",
                    "",
                    type_line,
                    count=1,
                    flags=re.IGNORECASE,
                )
            source.annotations["copy_overrides"] = characteristics
            self._log(
                actor,
                "permanent.copy",
                (
                    f"{source.ref} became a copy of {target.ref} until "
                    "end of turn."
                ),
                {
                    "source": source.ref,
                    "target": target.ref,
                    "duration": "until_end_of_turn",
                    "reason": reason,
                },
                importance=2,
                changed_objects=[source.object_id],
            )
            return source.ref
        if op == "change_control_until_end_of_turn":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            new_controller = str(
                effect.get("controller") or actor
            )
            until_end = card.annotations.setdefault(
                "until_end_of_turn",
                {},
            )
            until_end.setdefault("control_previous", card.controller)
            self.change_control(
                card.object_id,
                new_controller,
                reason=reason,
            )
            return card.ref
        if op == "add_type":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            card_type = str(effect.get("type") or "").strip().title()
            if not card_type:
                raise GameRuleError("Continuous type effect requires a type")
            card.annotations["continuous_add_types"] = (
                unique_preserving_order(
                    [
                        *list(
                            card.annotations.get(
                                "continuous_add_types", []
                            )
                        ),
                        card_type,
                    ]
                )
            )
            self._log(
                actor,
                "permanent.type",
                (
                    f"{card.ref} became a {card_type} in addition to its "
                    "other types."
                ),
                {
                    "object": card.ref,
                    "type": card_type,
                    "reason": reason,
                },
                importance=1,
                changed_objects=[card.object_id],
            )
            return card.ref
        if op == "add_subtype":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            subtype = str(effect.get("subtype") or "").strip().title()
            if not subtype:
                raise GameRuleError("Continuous subtype effect requires a subtype")
            card.annotations["continuous_add_subtypes"] = (
                unique_preserving_order(
                    [
                        *list(
                            card.annotations.get(
                                "continuous_add_subtypes", []
                            )
                        ),
                        subtype,
                    ]
                )
            )
            self._log(
                actor,
                "permanent.subtype",
                (
                    f"{card.ref} became a {subtype} in addition to its "
                    "other types."
                ),
                {
                    "object": card.ref,
                    "subtype": subtype,
                    "reason": reason,
                },
                importance=1,
                changed_objects=[card.object_id],
            )
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
        if op == "modify_stats_until_end_of_turn":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"battlefield"},
            )
            until_end = card.annotations.setdefault(
                "until_end_of_turn",
                {},
            )
            power = int(effect.get("power", 0))
            toughness = int(effect.get("toughness", 0))
            until_end["power"] = int(until_end.get("power", 0)) + power
            until_end["toughness"] = (
                int(until_end.get("toughness", 0)) + toughness
            )
            self._log(
                actor,
                "permanent.stats",
                (
                    f"{card.ref} got {power:+d}/{toughness:+d} until "
                    "end of turn."
                ),
                {
                    "object": card.ref,
                    "power": power,
                    "toughness": toughness,
                    "reason": reason,
                },
                importance=2,
                changed_objects=[card.object_id],
            )
            return card.ref
        if op == "grant_play_without_mana_cost":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={"exile"},
            )
            if card.owner == actor:
                raise GameRuleError(
                    "Dauthi Voidwalker can choose only a card an opponent owns"
                )
            if int(card.counters.get("void", 0)) <= 0:
                raise GameRuleError(
                    "The chosen exiled card does not have a void counter"
                )
            card.annotations["temporary_play_permission"] = {
                "player": actor,
                "zone": "exile",
                "turn_sequence": self.state.turn_sequence,
                "without_mana_cost": True,
                "allow_land": True,
                "allow_spell": True,
                "source": str(effect.get("source") or ""),
            }
            self._log(
                actor,
                "permission.play",
                (
                    f"{actor} may play {card.ref} from exile this turn "
                    "without paying its mana cost."
                ),
                {
                    "player": actor,
                    "object": card.ref,
                    "zone": "exile",
                    "turn_sequence": self.state.turn_sequence,
                    "without_mana_cost": True,
                    "reason": reason,
                },
                importance=2,
                changed_objects=[card.object_id],
                changed_players=[actor],
            )
            return card.ref
        if op == "grant_cast_permission":
            card = self._resolve_object(
                actor,
                str(effect["card"]),
                zones={str(effect.get("zone") or "graveyard")},
                owned_only=bool(effect.get("owned_only", True)),
            )
            allowed_types = {
                str(value).casefold()
                for value in effect.get("types_any", [])
            }
            card_types, _, _ = self._type_parts(
                str(
                    self._effective_card_data(card).get("type_line")
                    or ""
                )
            )
            if allowed_types and not allowed_types.intersection(
                card_types
            ):
                raise GameRuleError(
                    "The selected card does not satisfy the cast permission"
                )
            card.annotations["temporary_play_permission"] = {
                "player": actor,
                "zone": card.zone,
                "turn_sequence": self.state.turn_sequence,
                "without_mana_cost": bool(
                    effect.get("without_mana_cost", False)
                ),
                "allow_land": False,
                "allow_spell": True,
                "source": str(effect.get("source") or ""),
            }
            self._log(
                actor,
                "permission.cast",
                (
                    f"{actor} may cast {card.ref} from {card.zone} "
                    "this turn."
                ),
                {
                    "player": actor,
                    "object": card.ref,
                    "zone": card.zone,
                    "turn_sequence": self.state.turn_sequence,
                    "without_mana_cost": bool(
                        effect.get("without_mana_cost", False)
                    ),
                    "reason": reason,
                },
                visibility=[actor, "analyst"],
                importance=2,
                changed_objects=[card.object_id],
                changed_players=[actor],
            )
            return card.ref
        if op == "counter":
            card = self._resolve_object(actor, str(effect["card"]), zones={"battlefield"})
            name = str(effect.get("counter") or "+1/+1")
            delta = int(effect.get("delta", 1))
            if delta > 0:
                try:
                    results = place_counters_on_refs(
                        self,
                        actor=actor,
                        object_refs=(card.ref,),
                        counter_name=name,
                        amount=delta,
                        selections=tuple(
                            effect.get("_replacement_selections") or ()
                        ),
                        reason=reason,
                        source_ref=str(effect.get("source") or "") or None,
                    )
                except CounterPlacementError as exc:
                    raise GameRuleError(str(exc)) from exc
                return results[0].after
            before, after = self._change_permanent_counter(
                card,
                name,
                delta,
            )
            self._log(
                actor,
                "permanent.counter",
                f"{card.ref} {name} changed by {after - before}.",
                {
                    "object": card.ref,
                    "counter": " ".join(name.casefold().split()),
                    "requested_delta": delta,
                    "delta": after - before,
                    "before": before,
                    "after": after,
                },
                importance=1,
                changed_objects=[card.object_id],
            )
            return after
        if op == "counter_all_subtype":
            seat = str(effect.get("player") or actor)
            subtype = str(effect.get("subtype") or "").casefold()
            counter_name = str(effect.get("counter") or "+1/+1")
            amount = int(effect.get("amount", 1))
            try:
                results = place_counters_on_controlled_subtype(
                    self,
                    actor=actor,
                    controller=seat,
                    subtype=subtype,
                    counter_name=counter_name,
                    amount=amount,
                    selections=tuple(
                        effect.get("_replacement_selections") or ()
                    ),
                    reason=reason,
                    source_ref=str(effect.get("source") or "") or None,
                )
            except CounterPlacementError as exc:
                raise GameRuleError(str(exc)) from exc
            return [
                self.state.cards[result.object_id].ref
                for result in results
            ]
        if op == "look_top":
            seat = str(effect.get("player") or actor)
            viewer = str(effect.get("viewer") or actor)
            self._require_seat(seat, in_game=True)
            self._require_seat(viewer, in_game=True)
            try:
                count = int(effect.get("count", 1))
            except (TypeError, ValueError) as exc:
                raise GameRuleError(
                    "Library look count must be an integer"
                ) from exc
            if count < 0:
                raise GameRuleError(
                    "Library look count cannot be negative"
                )
            library = self.state.players[seat].zones["library"]
            ids = (
                list(reversed(library[-count:]))
                if count
                else []
            )
            for oid in ids:
                card = self.state.cards[oid]
                card.known_to = sorted(set(card.known_to).union({viewer}))
            self._log(actor, "library.look", f"{viewer} looked at the top {len(ids)} card(s) of {seat}'s library.", {"player": seat, "count": len(ids)}, visibility=[viewer, "analyst"], importance=1, changed_objects=ids)
            return [self.state.cards[oid].ref for oid in ids]
        if op == "reorder_top":
            seat = str(effect.get("player") or actor)
            viewer = str(effect.get("viewer") or actor)
            self._require_seat(seat, in_game=True)
            self._require_seat(viewer, in_game=True)
            values = list(effect.get("cards") or [])  # top-first
            ids = [self._resolve_object(viewer, str(value), zones={"library"}).object_id for value in values]
            library = self.state.players[seat].zones["library"]
            if len(ids) != len(set(ids)):
                raise GameRuleError(
                    "The same library card cannot be reordered twice"
                )
            current_top = (
                list(reversed(library[-len(ids):]))
                if ids
                else []
            )
            if (
                set(ids) != set(current_top)
                or any(
                    viewer not in self.state.cards[oid].known_to
                    for oid in ids
                )
            ):
                raise GameRuleError(
                    "Can only reorder the exact known cards currently on top"
                )
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

    def create_emblem(
        self,
        owner: str,
        *,
        abilities: Sequence[str],
        display_label: str = "Emblem",
        semantic_key: str | None = None,
        reason: str = "emblem effect",
    ) -> str:
        """Create a public noncard, nonpermanent command-zone object."""

        self._require_seat(owner, in_game=True)
        normalized_abilities = [
            str(ability).strip() for ability in abilities
        ]
        if (
            not normalized_abilities
            or any(not ability for ability in normalized_abilities)
        ):
            raise GameRuleError(
                "An emblem must have at least one nonempty ability"
            )
        ref = self._next_ref("E")
        object_id = self._stable_runtime_id("emblem-object", ref)
        emblem = CardInstance(
            object_id=object_id,
            ref=ref,
            oracle_id=(
                "custom-emblem:"
                + self._stable_runtime_id("emblem-oracle", ref)
            ),
            printed_name=str(display_label or "Emblem"),
            owner=owner,
            controller=owner,
            zone="command",
            object_kind="emblem",
            zone_timestamp=self._next_zone_timestamp(),
            annotations={
                "display_label": str(display_label or "Emblem"),
                "emblem_abilities": normalized_abilities,
                "emblem_semantic_key": semantic_key,
                "object_characteristics": {
                    "type_line": "",
                    "oracle_text": "\n".join(normalized_abilities),
                    "colors": [],
                    "keywords": [],
                },
            },
            known_to=list(self.seats),
            revealed_to=list(self.seats),
        )
        self.state.cards[object_id] = emblem
        self.state.players[owner].zones["command"].append(object_id)
        self.state.players[owner].stats["emblem_objects_v1"] = True
        self._log(
            owner,
            "emblem.create",
            f"{owner} created {emblem.printed_name}.",
            {
                "object": ref,
                "label": emblem.printed_name,
                "abilities": list(normalized_abilities),
                "semantic_key": semantic_key,
                "reason": reason,
            },
            importance=3,
            changed_objects=[object_id],
            changed_players=[owner],
        )
        return ref

    def create_token(
        self,
        controller: str,
        *,
        name: str,
        quantity: int = 1,
        tapped: bool = False,
        attacking: str | None = None,
        battle_protector: str | None = None,
        copy_of: str | None = None,
        characteristics: Mapping[str, Any] | None = None,
        temporary_keywords: Sequence[str] = (),
        reason: str = "token effect",
        replacement_selections: Sequence[str | None] = (),
    ) -> list[str]:
        try:
            return create_tokens(
                self,
                controller,
                name=name,
                quantity=quantity,
                tapped=tapped,
                attacking=attacking,
                battle_protector=battle_protector,
                copy_of=copy_of,
                characteristics=characteristics,
                temporary_keywords=temporary_keywords,
                reason=reason,
                replacement_selections=replacement_selections,
            )
        except TokenCreationError as exc:
            raise GameRuleError(str(exc)) from exc

    def change_control(self, object_id: str, new_controller: str, *, reason: str = "") -> None:
        self._require_seat(new_controller, in_game=True)
        card = self.state.cards[object_id]
        if card.zone != "battlefield":
            raise GameRuleError("Only battlefield permanents have controllers")
        old = card.controller
        self._remove_object_from_combat(
            card,
            reason="control changed",
        )
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
