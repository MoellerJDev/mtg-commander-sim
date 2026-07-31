from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

PROTOCOL_VERSION = "3.0"


class ProtocolError(ValueError):
    """Raised when a projected-state packet cannot be applied safely."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def view_hash(value: Any) -> str:
    """Return a short content hash suitable for projection resynchronization."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:20]


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _unescape_pointer(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _join(path: str, token: str | int) -> str:
    escaped = _escape_pointer(str(token))
    return f"{path}/{escaped}" if path else f"/{escaped}"


def json_patch(old: Any, new: Any, path: str = "") -> list[dict[str, Any]]:
    """Create a compact RFC-6902-compatible add/remove/replace patch.

    Lists use a common-prefix/common-suffix edit. Projected zones are normally
    stable enough that drawing, moving, or creating one object becomes one or
    two list operations instead of retransmitting every player's full state.
    """

    if old == new:
        return []

    if isinstance(old, Mapping) and isinstance(new, Mapping):
        operations: list[dict[str, Any]] = []
        old_keys = set(old)
        new_keys = set(new)
        for key in sorted(old_keys - new_keys):
            operations.append({"op": "remove", "path": _join(path, key)})
        for key in sorted(new_keys - old_keys):
            operations.append(
                {"op": "add", "path": _join(path, key), "value": copy.deepcopy(new[key])}
            )
        for key in sorted(old_keys & new_keys):
            operations.extend(json_patch(old[key], new[key], _join(path, key)))
        return operations

    if isinstance(old, list) and isinstance(new, list):
        prefix = 0
        limit = min(len(old), len(new))
        while prefix < limit and old[prefix] == new[prefix]:
            prefix += 1

        suffix = 0
        while (
            suffix < len(old) - prefix
            and suffix < len(new) - prefix
            and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]
        ):
            suffix += 1

        old_stop = len(old) - suffix
        new_stop = len(new) - suffix
        operations = []
        # Remove from the highest index so subsequent indexes stay valid.
        for index in range(old_stop - 1, prefix - 1, -1):
            operations.append({"op": "remove", "path": _join(path, index)})
        # Insert the replacement middle in forward order.
        for offset, value in enumerate(new[prefix:new_stop]):
            operations.append(
                {
                    "op": "add",
                    "path": _join(path, prefix + offset),
                    "value": copy.deepcopy(value),
                }
            )
        return operations

    return [{"op": "replace", "path": path, "value": copy.deepcopy(new)}]


def _tokens(path: str) -> list[str]:
    if path == "":
        return []
    if not path.startswith("/"):
        raise ProtocolError(f"Invalid JSON Pointer {path!r}")
    return [_unescape_pointer(token) for token in path[1:].split("/")]


def _parent(document: Any, path: str) -> tuple[Any, str]:
    tokens = _tokens(path)
    if not tokens:
        return None, ""
    target = document
    for token in tokens[:-1]:
        if isinstance(target, list):
            try:
                target = target[int(token)]
            except (ValueError, IndexError) as exc:
                raise ProtocolError(f"Invalid list path component {token!r} in {path!r}") from exc
        elif isinstance(target, dict):
            if token not in target:
                raise ProtocolError(f"Missing object path component {token!r} in {path!r}")
            target = target[token]
        else:
            raise ProtocolError(f"Cannot traverse through scalar at {path!r}")
    return target, tokens[-1]


def apply_json_patch(document: Any, operations: Sequence[Mapping[str, Any]]) -> Any:
    """Apply the supported RFC-6902 subset and return a deep-copied document."""

    result = copy.deepcopy(document)
    for raw in operations:
        operation = str(raw.get("op") or "")
        path = str(raw.get("path") or "")
        if path == "":
            if operation in {"add", "replace"}:
                result = copy.deepcopy(raw.get("value"))
                continue
            if operation == "remove":
                result = None
                continue
            raise ProtocolError(f"Unsupported patch operation {operation!r}")

        parent, token = _parent(result, path)
        if isinstance(parent, list):
            if token == "-":
                index = len(parent)
            else:
                try:
                    index = int(token)
                except ValueError as exc:
                    raise ProtocolError(f"List index must be an integer in {path!r}") from exc
            if operation == "remove":
                try:
                    parent.pop(index)
                except IndexError as exc:
                    raise ProtocolError(f"List removal out of range in {path!r}") from exc
            elif operation == "add":
                if index < 0 or index > len(parent):
                    raise ProtocolError(f"List insertion out of range in {path!r}")
                parent.insert(index, copy.deepcopy(raw.get("value")))
            elif operation == "replace":
                try:
                    parent[index] = copy.deepcopy(raw.get("value"))
                except IndexError as exc:
                    raise ProtocolError(f"List replacement out of range in {path!r}") from exc
            else:
                raise ProtocolError(f"Unsupported patch operation {operation!r}")
        elif isinstance(parent, dict):
            if operation == "remove":
                if token not in parent:
                    raise ProtocolError(f"Missing key for removal in {path!r}")
                del parent[token]
            elif operation in {"add", "replace"}:
                if operation == "replace" and token not in parent:
                    raise ProtocolError(f"Missing key for replacement in {path!r}")
                parent[token] = copy.deepcopy(raw.get("value"))
            else:
                raise ProtocolError(f"Unsupported patch operation {operation!r}")
        else:
            raise ProtocolError(f"Patch parent is not a container in {path!r}")
    return result
