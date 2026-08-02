from __future__ import annotations


class GameRuleError(RuntimeError):
    """A requested game operation is not legal in the current state."""


class StateInvariantError(RuntimeError):
    """Authoritative state violates an invariant required by the engine."""
