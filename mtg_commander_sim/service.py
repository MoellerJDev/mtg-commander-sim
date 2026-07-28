from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .engine import ActionResult
from .session import CommanderSession


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    """Transport-neutral, *unauthenticated-body* command DTO.

    A network client may supply the game, live capability, action, and action
    payload.  It never supplies the seat/principal.  The transport authenticates
    the connection and passes that principal separately to ``GameService``.
    This keeps a future GUI/WebSocket server on the same permission boundary as
    an in-process LLM runner.
    """

    game_id: str
    capability: str
    action: str
    payload: Mapping[str, Any]


class GameService:
    """Thin application boundary suitable for CLI, Codex, HTTP, or a GUI."""

    def __init__(self, session: CommanderSession):
        self.session = session

    def observe(self, principal: str, *, full: bool = False) -> dict[str, Any]:
        # In a network service, ``principal`` is derived from the authenticated
        # connection/session rather than query parameters controlled by a user.
        return self.session.packet(principal, full=full)

    def command(self, envelope: CommandEnvelope, *, principal: str) -> ActionResult:
        if envelope.game_id != self.session.state.game_id:
            return ActionResult(False, "Wrong game id", [], state_changed=False)
        current = self.session.engine.permissions.capability_for(principal)
        if current is None or current.token != envelope.capability:
            return ActionResult(False, "Unknown, stale, or unauthorized capability", [], state_changed=False)
        return self.session.act(
            principal,
            {"action": envelope.action, **dict(envelope.payload)},
        )

    def poll(self) -> list[str]:
        self.session.engine.pump()
        return self.session.pending_principals()
