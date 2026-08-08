from __future__ import annotations

import re
from typing import Any, Protocol

from .explore import explore_source_controller


_INDEX_GROUP = "in" + "dex"


class SemanticValueHost(Protocol):
    state: Any

    def _stack_source_ref(self, item: Any) -> str | None: ...

    def _target_snapshot(self, target_ref: str) -> dict[str, Any]: ...


def resolve_semantic_value(
    host: SemanticValueHost,
    value: Any,
    item: Any,
) -> Any:
    """Resolve transport-safe runtime placeholders against one stack item."""

    if isinstance(value, list):
        return [resolve_semantic_value(host, child, item) for child in value]
    if isinstance(value, dict):
        return {
            key: resolve_semantic_value(host, child, item)
            for key, child in value.items()
        }
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    if value == "$controller":
        return item.controller
    if value == "$active":
        return host.state.active_player
    if value == "$source":
        return host._stack_source_ref(item)
    if value == "$source.controller":
        return explore_source_controller(item, host.state.cards)
    if value == "$card":
        card = host.state.cards.get(item.card_object_id or "")
        return card.ref if card else None
    if value == "$stack":
        return item.ref
    if value == "$x":
        return item.x_value or 0
    if value == "$turn_sequence":
        return host.state.turn_sequence
    if value.startswith("$context."):
        return item.context.get(value.removeprefix("$context."))
    if value == "$targets":
        return [target for target in item.targets if target is not None]
    attribute_match = re.fullmatch(
        r"\$target\.(?P<attribute>controller|owner|mana_value|colors|type_line)"
        r"[.\[](?P<index>\d+)\]?",
        value,
    )
    if attribute_match:
        index = int(attribute_match.group(_INDEX_GROUP))
        if index >= len(item.targets):
            return None
        target_ref = item.targets[index]
        if target_ref is None:
            return None
        snapshot = dict(
            item.context.get("target_snapshots", {}).get(
                str(target_ref),
                host._target_snapshot(str(target_ref)),
            )
        )
        return snapshot.get(attribute_match.group("attribute"))
    target_match = re.fullmatch(r"\$target[.\[](?P<index>\d+)\]?", value)
    if target_match:
        index = int(target_match.group(_INDEX_GROUP))
        if index >= len(item.targets):
            return None
        return item.targets[index]
    return value


__all__ = ["SemanticValueHost", "resolve_semantic_value"]
