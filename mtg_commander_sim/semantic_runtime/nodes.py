from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DrawNode:
    player: str
    count: int
    reason: str
    private: bool = False


@dataclass(frozen=True, slots=True)
class DrawEachPlayerNode:
    count: int
    reason: str


@dataclass(frozen=True, slots=True)
class BecomeMonarchNode:
    player: str
    reason: str
