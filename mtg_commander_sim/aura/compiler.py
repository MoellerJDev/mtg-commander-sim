from __future__ import annotations

from typing import Any, Mapping, Sequence

from .grammar import parse_simple_enchant_line


def keyword_target_schema(
    material_line: str,
    mechanics: Sequence[str],
) -> Mapping[str, Any] | None:
    """Lower only the closed Enchant keyword grammar to a target schema."""

    if tuple(mechanics) != ("enchant",):
        return None
    spec = parse_simple_enchant_line(material_line)
    return spec.target_schema() if spec is not None else None


__all__ = ["keyword_target_schema"]
