from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Iterable

from .model import Capability, DecisionGroup, GameState


class PermissionDenied(RuntimeError):
    """Raised when a principal attempts an action outside its issued capability."""


@dataclass(frozen=True, slots=True)
class AuthorizedCommand:
    capability: Capability
    decision: DecisionGroup
    action: str
    payload: dict[str, Any]


class CapabilityManager:
    """
    Opaque, single-use decision capabilities.

    The game server derives ``principal`` from the authenticated connection.  A
    local ChatGPT session passes it explicitly, but the same command envelope can
    be exposed through HTTP/WebSocket without changing the engine permission
    model.  Pilots never receive mutation or rules-resolution capabilities.
    """

    def __init__(self, state: GameState):
        self.state = state

    @staticmethod
    def pilot_principal(seat: str) -> str:
        return f"pilot:{seat}"

    def issue(
        self,
        *,
        kind: str,
        role: str,
        actors: Iterable[str],
        allowed_actions: Iterable[str],
        payload_by_actor: dict[str, dict[str, Any]] | None = None,
        simultaneous: bool = False,
        continuation: dict[str, Any] | None = None,
    ) -> DecisionGroup:
        if self.state.pending_decision is not None:
            raise RuntimeError("Cannot issue a new decision while another is pending")
        actor_list = list(actors)
        decision_id = f"D{self.state.ref_counters.get('decision', 0) + 1}"
        self.state.ref_counters["decision"] = self.state.ref_counters.get("decision", 0) + 1
        decision = DecisionGroup(
            decision_id=decision_id,
            kind=kind,
            role=role,
            actors=actor_list,
            allowed_actions=list(allowed_actions),
            payload_by_actor=dict(payload_by_actor or {}),
            simultaneous=simultaneous,
            continuation=dict(continuation or {}),
            created_revision=self.state.revision,
        )
        self.state.pending_decision = decision

        for actor in actor_list:
            if role == "pilot":
                strategic_controller = self.state.players[
                    actor
                ].stats.get("turn_controlled_by")
                principal = self.pilot_principal(
                    str(strategic_controller or actor)
                )
                capability_actor: str | None = actor
            else:
                principal = role
                capability_actor = None if actor == role else actor
            token = self._new_token()
            self.state.capabilities[token] = Capability(
                token=token,
                decision_id=decision_id,
                principal=principal,
                role=role,
                actor=capability_actor,
                allowed_actions=list(decision.allowed_actions),
                created_revision=self.state.revision,
            )
        return decision

    def _new_token(self) -> str:
        while True:
            token = "c_" + secrets.token_urlsafe(8)
            if token not in self.state.capabilities:
                return token

    def capability_for(self, principal: str) -> Capability | None:
        decision = self.state.pending_decision
        if not decision:
            return None
        for capability in self.state.capabilities.values():
            if (
                capability.decision_id == decision.decision_id
                and capability.principal == principal
                and not capability.consumed
            ):
                return capability
        return None

    def authorize(
        self,
        *,
        token: str,
        principal: str,
        action: str,
        payload: dict[str, Any],
    ) -> AuthorizedCommand:
        decision = self.state.pending_decision
        if decision is None:
            raise PermissionDenied("No decision is currently pending")
        capability = self.state.capabilities.get(token)
        if capability is None:
            raise PermissionDenied("Unknown capability token")
        if capability.consumed:
            raise PermissionDenied("Capability has already been consumed")
        if capability.decision_id != decision.decision_id:
            raise PermissionDenied("Capability belongs to an expired decision")
        if capability.principal != principal:
            raise PermissionDenied("Capability was not issued to this principal")
        if action not in capability.allowed_actions:
            raise PermissionDenied(
                f"Action {action!r} is outside capability scope {capability.allowed_actions}"
            )
        capability.consumed = True
        return AuthorizedCommand(capability, decision, action, payload)

    def record_response(self, command: AuthorizedCommand) -> None:
        actor_key = command.capability.actor or command.capability.principal
        command.decision.responses[actor_key] = {
            "action": command.action,
            **command.payload,
        }

    def decision_complete(self) -> bool:
        decision = self.state.pending_decision
        if decision is None:
            return False
        expected = set(decision.actors)
        if decision.role != "pilot":
            # Non-pilot actors are usually the principal name itself.
            expected = {
                cap.actor or cap.principal
                for cap in self.state.capabilities.values()
                if cap.decision_id == decision.decision_id
            }
        return expected.issubset(decision.responses)

    def close_decision(self) -> DecisionGroup:
        decision = self.state.pending_decision
        if decision is None:
            raise RuntimeError("No pending decision")
        for capability in self.state.capabilities.values():
            if capability.decision_id == decision.decision_id:
                capability.consumed = True
        self.state.pending_decision = None
        return decision

    def reissue_pending(self) -> None:
        """Replace persisted capability metadata with fresh opaque tokens.

        Capability tokens are transport credentials, not authoritative game
        state. Checkpoints deliberately omit them and reissue only the still
        unanswered actors when a record is loaded or replayed.
        """
        decision = self.state.pending_decision
        self.state.capabilities = {}
        if decision is None:
            return
        for actor in decision.actors:
            actor_key = actor if decision.role == "pilot" else actor
            if actor_key in decision.responses:
                continue
            if decision.role == "pilot":
                strategic_controller = self.state.players[
                    actor
                ].stats.get("turn_controlled_by")
                principal = self.pilot_principal(
                    str(strategic_controller or actor)
                )
            else:
                principal = decision.role
            token = self._new_token()
            self.state.capabilities[token] = Capability(
                token=token,
                decision_id=decision.decision_id,
                principal=principal,
                role=decision.role,
                actor=actor if decision.role == "pilot" else (None if actor == decision.role else actor),
                allowed_actions=list(decision.allowed_actions),
                created_revision=self.state.revision,
            )

    def invalidate_current(self) -> None:
        decision = self.state.pending_decision
        if not decision:
            return
        for capability in self.state.capabilities.values():
            if capability.decision_id == decision.decision_id:
                capability.consumed = True
        self.state.pending_decision = None
