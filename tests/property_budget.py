from __future__ import annotations

import os


DEFAULT_PROPERTY_TRANSITIONS = 1_000
MAX_PROPERTY_TRANSITIONS = 1_000_000


def property_transitions() -> int:
    raw = os.environ.get("MTG_PROPERTY_TRANSITIONS")
    if raw is None:
        return DEFAULT_PROPERTY_TRANSITIONS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("MTG_PROPERTY_TRANSITIONS must be an integer") from exc
    if value < 1 or value > MAX_PROPERTY_TRANSITIONS:
        raise ValueError(
            "MTG_PROPERTY_TRANSITIONS must be between 1 and "
            f"{MAX_PROPERTY_TRANSITIONS}"
        )
    return value
