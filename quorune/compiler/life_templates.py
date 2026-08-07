from __future__ import annotations

import re
from typing import Any, Mapping


_DOUBLE_CONTROLLER_LIFE_GAIN = re.compile(
    r"^If you would gain life, you gain twice that much life instead\.?$",
    re.IGNORECASE,
)


def static_life_handler(
    text: str,
) -> tuple[str, Mapping[str, Any], str] | None:
    """Lower one closed static life-change replacement wording family."""

    if _DOUBLE_CONTROLLER_LIFE_GAIN.fullmatch(text) is None:
        return None
    return (
        "life-gain-double-controller-static-v1",
        {
            "handler_id": "replacement.life.gain.multiplier.v1",
            "schema_version": 1,
            "event": "life.change",
            "condition": {
                "affected_player_relation": "source_controller",
            },
            "modification": {"multiplier": 2},
        },
        "life.gain.replacement.static_multiplier",
    )


__all__ = ["static_life_handler"]
