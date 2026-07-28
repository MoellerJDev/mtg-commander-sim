from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from .protocol import PROTOCOL_VERSION, ProtocolError, apply_json_patch, view_hash


@dataclass(slots=True)
class ProjectedClientView:
    """Reference client-side reducer for LLM runners, GUIs, and WebSockets.

    The permission model stays server-side. This class only reconstructs the
    authenticated principal's projected view from a bootstrap plus patches.
    """

    principal: str
    state: dict[str, Any] | None = None
    current_hash: str | None = None
    packet_no: int = 0
    definitions: dict[str, dict[str, Any]] = field(default_factory=dict)
    decision: dict[str, Any] | None = None
    recent_events: list[dict[str, Any]] = field(default_factory=list)

    def ingest(self, packet: Mapping[str, Any]) -> dict[str, Any]:
        version = str(packet.get("v") or "")
        if version != PROTOCOL_VERSION:
            raise ProtocolError(f"Unsupported packet protocol {version!r}")
        if str(packet.get("principal") or "") != self.principal:
            raise ProtocolError("Packet belongs to a different principal")
        number = int(packet.get("pkt") or 0)
        if number <= self.packet_no:
            raise ProtocolError("Packet number is stale or duplicated")

        mode = str(packet.get("mode") or "")
        if mode == "full":
            if "state" not in packet:
                raise ProtocolError("Full packet is missing state")
            self.state = copy.deepcopy(packet["state"])
        elif mode == "delta":
            if self.state is None:
                raise ProtocolError("A delta cannot be applied before a full packet")
            if packet.get("base") != self.current_hash:
                raise ProtocolError("Delta base hash does not match; request a full resync")
            self.state = apply_json_patch(self.state, list(packet.get("patch") or []))
        else:
            raise ProtocolError(f"Unknown packet mode {mode!r}")

        expected = str(packet.get("view") or "")
        actual = view_hash(self.state)
        if expected != actual:
            raise ProtocolError(f"Projected-state hash mismatch: expected {expected}, got {actual}")
        self.current_hash = actual
        self.packet_no = number
        self.decision = copy.deepcopy(packet.get("decision"))
        for definition in packet.get("defs") or []:
            cid = str(definition.get("cid") or "")
            if cid:
                self.definitions[cid] = copy.deepcopy(definition)
        if packet.get("events"):
            self.recent_events.extend(copy.deepcopy(list(packet["events"])))
            self.recent_events = self.recent_events[-64:]
        return self.state
