from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .util import normalize_mana_bundle, stable_json

ZoneName = Literal[
    "library",
    "hand",
    "battlefield",
    "graveyard",
    "exile",
    "command",
    "stack",
    "outside",
]

PrincipalRole = Literal["pilot", "arbiter", "analyst", "spectator", "admin"]


@dataclass(slots=True)
class CardInstance:
    object_id: str
    ref: str
    oracle_id: str
    printed_name: str
    owner: str
    controller: str
    zone: str
    is_token: bool = False
    is_commander: bool = False
    tapped: bool = False
    face_down: bool = False
    active_face: str | None = None
    phased_out: bool = False
    counters: dict[str, int] = field(default_factory=dict)
    marked_damage: int = 0
    deathtouch_damage: bool = False
    temporary_keywords: list[str] = field(default_factory=list)
    annotations: dict[str, Any] = field(default_factory=dict)
    attached_to: str | None = None
    attachments: list[str] = field(default_factory=list)
    acquired_control_turn_count: int = 0
    entered_battlefield_turn_sequence: int = 0
    revealed_to: list[str] = field(default_factory=list)
    known_to: list[str] = field(default_factory=list)
    attacking: str | None = None
    blocking: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CardInstance":
        return cls(**data)


@dataclass(slots=True)
class YieldPolicy:
    mode: str = "none"
    created_revision: int = 0
    created_event_sequence: int = 0
    created_turn_sequence: int = 0
    created_priority_epoch: int = 0
    created_active_player: str | None = None
    created_phase: str | None = None
    created_step: str | None = None
    created_land_plays_remaining: int | None = None
    action_signature: str | None = None
    stack_signature: str | None = None
    expires_turn_sequence: int | None = None
    expires_on_stack_change: bool = True
    expires_on_hand_change: bool = True
    expires_on_battlefield_change: bool = True
    stop_phase: str | None = None
    stop_step: str | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "YieldPolicy":
        return cls(**(data or {}))


@dataclass(slots=True)
class PlayerState:
    seat: str
    name: str
    life: int = 40
    poison: int = 0
    energy: int = 0
    in_game: bool = True
    mana_pool: dict[str, int] = field(default_factory=lambda: normalize_mana_bundle(None))
    zones: dict[str, list[str]] = field(
        default_factory=lambda: {
            "library": [],
            "hand": [],
            "battlefield": [],
            "graveyard": [],
            "exile": [],
            "command": [],
            "outside": [],
        }
    )
    commander_casts: dict[str, int] = field(default_factory=dict)
    commander_damage_received: dict[str, int] = field(default_factory=dict)
    turns_begun: int = 0
    land_plays_remaining: int = 1
    max_hand_size: int = 7
    mulligans_taken: int = 0
    mulligan_penalty: int = 0
    mulligan_status: str = "pending"  # pending, bottoming, kept
    kept_hand: bool = False
    attempted_empty_draw: bool = False
    draw_history: list[dict[str, Any]] = field(default_factory=list)
    decision_notes: list[dict[str, Any]] = field(default_factory=list)
    rules_seen: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    yield_policy: YieldPolicy = field(default_factory=YieldPolicy)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["yield_policy"] = self.yield_policy.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerState":
        payload = dict(data)
        payload["mana_pool"] = normalize_mana_bundle(payload.get("mana_pool"))
        payload["yield_policy"] = YieldPolicy.from_dict(payload.get("yield_policy"))
        return cls(**payload)


@dataclass(slots=True)
class StackItem:
    stack_id: str
    ref: str
    kind: str
    controller: str
    label: str
    card_object_id: str | None = None
    source_object_id: str | None = None
    semantic_key: str | None = None
    targets: list[Any] = field(default_factory=list)
    modes: list[str] = field(default_factory=list)
    x_value: int | None = None
    chosen_face: str | None = None
    notes: str = ""
    default_destination: str | None = None
    visibility: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StackItem":
        return cls(**data)


@dataclass(slots=True)
class TurnEntry:
    turn_id: str
    player: str
    extra: bool = False
    source: str | None = None
    created_sequence: int = 0
    skip_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TurnEntry":
        return cls(**data)


@dataclass(slots=True)
class DelayedTrigger:
    trigger_id: str
    ref: str
    controller: str
    label: str
    source_object_id: str | None
    event_kind: str
    condition: dict[str, Any]
    stack_template: dict[str, Any]
    once: bool = True
    created_turn_sequence: int = 0
    expires_turn_sequence: int | None = None
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DelayedTrigger":
        return cls(**data)


@dataclass(slots=True)
class CombatState:
    attackers_declared: bool = False
    blockers_declared: bool = False
    attackers: dict[str, str] = field(default_factory=dict)  # attacker object -> defender seat/object
    defending_players: list[str] = field(default_factory=list)
    blocker_cursor: int = 0
    blockers: dict[str, list[str]] = field(default_factory=dict)  # attacker -> blocker object ids
    damage_assignments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CombatState":
        return cls(**data)


@dataclass(slots=True)
class DecisionGroup:
    decision_id: str
    kind: str
    role: str
    actors: list[str]
    allowed_actions: list[str]
    payload_by_actor: dict[str, dict[str, Any]] = field(default_factory=dict)
    simultaneous: bool = False
    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    continuation: dict[str, Any] = field(default_factory=dict)
    created_revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionGroup":
        return cls(**data)


@dataclass(slots=True)
class Capability:
    token: str
    decision_id: str
    principal: str
    role: str
    actor: str | None
    allowed_actions: list[str]
    created_revision: int
    consumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Capability":
        return cls(**data)


@dataclass(slots=True)
class Event:
    event_id: int
    revision: int
    turn_sequence: int
    active_player: str | None
    phase: str
    step: str
    actor: str | None
    code: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    visibility: list[str] = field(default_factory=list)
    importance: int = 1
    changed_objects: list[str] = field(default_factory=list)
    changed_players: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(**data)


@dataclass(slots=True)
class GameConfig:
    format_name: str = "commander"
    review_profile: str = "commander_review"
    profile: str = "auto"
    starting_life: int = 40
    poison_to_lose: int = 10
    commander_damage_to_lose: int = 21
    opening_hand_size: int = 7
    free_mulligans: int | None = None
    first_player_draws_on_turn_one: bool | None = None
    auto_untap: bool = True
    auto_draw: bool = True
    strict_timing: bool = True
    strict_mana: bool = True
    seed: int | None = None
    hidden_information_mode: str = "seat-projected"
    priority_optimization: str = "conservative-yield"
    auto_resolve_registered_semantics: bool = True
    semantic_policy: str = "arbitrate_or_pause"
    auto_pass_empty_priority: bool = True
    realistic_mulligan_guard: bool = True
    max_players: int = 6
    trace_level: str = "standard"

    def effective_profile(self, player_count: int) -> str:
        if self.profile != "auto":
            return self.profile
        return "commander_duel" if player_count == 2 else "commander_multiplayer"

    def effective_free_mulligans(self, player_count: int) -> int:
        if self.free_mulligans is not None:
            return self.free_mulligans
        return 0 if self.effective_profile(player_count) == "commander_duel" else 1

    def effective_first_player_draws(self, player_count: int) -> bool:
        if self.first_player_draws_on_turn_one is not None:
            return self.first_player_draws_on_turn_one
        return self.effective_profile(player_count) == "commander_multiplayer"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameConfig":
        return cls(**data)


@dataclass(slots=True)
class GameState:
    game_id: str
    config: GameConfig
    players: dict[str, PlayerState]
    cards: dict[str, CardInstance]
    deck_names: dict[str, str]
    commander_oracle_ids: dict[str, list[str]]
    turn_order: list[str]
    current_turn: TurnEntry | None
    last_normal_turn_player: str | None
    extra_turns: list[TurnEntry] = field(default_factory=list)
    active_player: str | None = None
    priority_player: str | None = None
    priority_passes: list[str] = field(default_factory=list)
    priority_epoch: int = 0
    turn_sequence: int = 0
    phase_index: int = 0
    phase: str = "setup"
    step: str = "mulligan"
    stack: list[StackItem] = field(default_factory=list)
    delayed_triggers: list[DelayedTrigger] = field(default_factory=list)
    pending_trigger_batches: list[dict[str, Any]] = field(
        default_factory=list
    )
    combat: CombatState = field(default_factory=CombatState)
    events: list[Event] = field(default_factory=list)
    annotations: list[dict[str, Any]] = field(default_factory=list)
    action_opportunities: list[dict[str, Any]] = field(default_factory=list)
    opportunity_sequence: int = 0
    pending_decision: DecisionGroup | None = None
    capabilities: dict[str, Capability] = field(default_factory=dict)
    started: bool = False
    game_over: bool = False
    winner: str | None = None
    draw: bool = False
    eliminated_players: list[str] = field(default_factory=list)
    revision: int = 0
    event_sequence: int = 0
    state_version: int = 3
    mulligan_round: int = 0
    ref_counters: dict[str, int] = field(default_factory=dict)

    def active_seats(self) -> list[str]:
        return [seat for seat in self.turn_order if self.players[seat].in_game]

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "config": self.config.to_dict(),
            "players": {seat: player.to_dict() for seat, player in self.players.items()},
            "cards": {object_id: card.to_dict() for object_id, card in self.cards.items()},
            "deck_names": dict(self.deck_names),
            "commander_oracle_ids": {
                seat: list(ids) for seat, ids in self.commander_oracle_ids.items()
            },
            "turn_order": list(self.turn_order),
            "current_turn": self.current_turn.to_dict() if self.current_turn else None,
            "last_normal_turn_player": self.last_normal_turn_player,
            "extra_turns": [turn.to_dict() for turn in self.extra_turns],
            "active_player": self.active_player,
            "priority_player": self.priority_player,
            "priority_passes": list(self.priority_passes),
            "priority_epoch": self.priority_epoch,
            "turn_sequence": self.turn_sequence,
            "phase_index": self.phase_index,
            "phase": self.phase,
            "step": self.step,
            "stack": [item.to_dict() for item in self.stack],
            "delayed_triggers": [trigger.to_dict() for trigger in self.delayed_triggers],
            "pending_trigger_batches": copy.deepcopy(
                self.pending_trigger_batches
            ),
            "combat": self.combat.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "annotations": copy.deepcopy(self.annotations),
            "action_opportunities": copy.deepcopy(self.action_opportunities),
            "opportunity_sequence": self.opportunity_sequence,
            "pending_decision": self.pending_decision.to_dict() if self.pending_decision else None,
            "capabilities": {token: cap.to_dict() for token, cap in self.capabilities.items()},
            "started": self.started,
            "game_over": self.game_over,
            "winner": self.winner,
            "draw": self.draw,
            "eliminated_players": list(self.eliminated_players),
            "revision": self.revision,
            "event_sequence": self.event_sequence,
            "state_version": self.state_version,
            "mulligan_round": self.mulligan_round,
            "ref_counters": dict(self.ref_counters),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameState":
        return cls(
            game_id=str(data["game_id"]),
            config=GameConfig.from_dict(data["config"]),
            players={seat: PlayerState.from_dict(player) for seat, player in data["players"].items()},
            cards={oid: CardInstance.from_dict(card) for oid, card in data["cards"].items()},
            deck_names=dict(data["deck_names"]),
            commander_oracle_ids={seat: list(ids) for seat, ids in data["commander_oracle_ids"].items()},
            turn_order=list(data["turn_order"]),
            current_turn=(TurnEntry.from_dict(data["current_turn"]) if data.get("current_turn") else None),
            last_normal_turn_player=data.get("last_normal_turn_player"),
            extra_turns=[TurnEntry.from_dict(turn) for turn in data.get("extra_turns", [])],
            active_player=data.get("active_player"),
            priority_player=data.get("priority_player"),
            priority_passes=list(data.get("priority_passes", [])),
            priority_epoch=int(data.get("priority_epoch", 0)),
            turn_sequence=int(data.get("turn_sequence", 0)),
            phase_index=int(data.get("phase_index", 0)),
            phase=str(data.get("phase", "setup")),
            step=str(data.get("step", "mulligan")),
            stack=[StackItem.from_dict(item) for item in data.get("stack", [])],
            delayed_triggers=[DelayedTrigger.from_dict(item) for item in data.get("delayed_triggers", [])],
            pending_trigger_batches=copy.deepcopy(
                data.get("pending_trigger_batches", [])
            ),
            combat=CombatState.from_dict(data.get("combat", {})),
            events=[Event.from_dict(event) for event in data.get("events", [])],
            annotations=list(data.get("annotations", [])),
            action_opportunities=list(data.get("action_opportunities", [])),
            opportunity_sequence=int(data.get("opportunity_sequence", 0)),
            pending_decision=(DecisionGroup.from_dict(data["pending_decision"]) if data.get("pending_decision") else None),
            capabilities={token: Capability.from_dict(cap) for token, cap in data.get("capabilities", {}).items()},
            started=bool(data.get("started", False)),
            game_over=bool(data.get("game_over", False)),
            winner=data.get("winner"),
            draw=bool(data.get("draw", False)),
            eliminated_players=list(data.get("eliminated_players", [])),
            revision=int(data.get("revision", 0)),
            event_sequence=int(data.get("event_sequence", 0)),
            state_version=int(data.get("state_version", 2)),
            mulligan_round=int(data.get("mulligan_round", 0)),
            ref_counters=dict(data.get("ref_counters", {})),
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(stable_json(self.to_dict()), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path: str | Path) -> "GameState":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
