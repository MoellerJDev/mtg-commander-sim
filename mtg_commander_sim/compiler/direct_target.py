from __future__ import annotations

"""Small structural helpers for independently owned direct-target grammars."""

from typing import Any, Mapping, Sequence


CompiledDirectTarget = tuple[
    str,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any],
    tuple[str, ...],
]


def _closed_values(
    values: Sequence[str],
    *,
    field: str,
    required: bool = False,
) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"Direct-target {field} must be an array")
    normalized = list(values)
    if required and not normalized:
        raise ValueError(f"Direct-target {field} must not be empty")
    if any(type(value) is not str or not value for value in normalized):
        raise ValueError(
            f"Direct-target {field} values must be nonempty strings"
        )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"Direct-target {field} values must be unique")
    return normalized


def direct_target_slug(value: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError("Direct-target slugs require a nonempty value")
    return (
        value.casefold().replace(",", "").replace(" or ", "-or-").replace(" ", "-")
    )


def direct_target_effect(
    operation: str,
    *,
    reference_field: str,
) -> tuple[Mapping[str, Any], ...]:
    if type(operation) is not str or not operation:
        raise ValueError("Direct-target operations must be nonempty")
    if type(reference_field) is not str or not reference_field:
        raise ValueError("Direct-target reference fields must be nonempty")
    return ({"op": operation, reference_field: "$target.0"},)


def permanent_target_schema(
    *,
    types_any: Sequence[str] = (),
    types_none: Sequence[str] = (),
) -> Mapping[str, Any]:
    any_values = _closed_values(types_any, field="types_any")
    none_values = _closed_values(types_none, field="types_none")
    if types_any and types_none:
        raise ValueError("Direct permanent targets require one type predicate")
    schema: dict[str, Any] = {
        "zones": ["battlefield"],
        "categories": ["permanent"],
        "count": 1,
    }
    if any_values:
        schema["types_any"] = any_values
    if none_values:
        schema["types_none"] = none_values
    return schema


def stack_target_schema(
    *,
    categories: Sequence[str],
    types_any: Sequence[str] = (),
    types_none: Sequence[str] = (),
    colors_any: Sequence[str] = (),
    predicate: str | None = None,
    colorless: bool | None = None,
) -> Mapping[str, Any]:
    category_values = _closed_values(
        categories,
        field="categories",
        required=True,
    )
    any_values = _closed_values(types_any, field="types_any")
    none_values = _closed_values(types_none, field="types_none")
    color_values = _closed_values(colors_any, field="colors_any")
    predicates = sum(
        bool(value)
        for value in (
            any_values,
            none_values,
            color_values,
            predicate,
            colorless,
        )
    )
    if predicates > 1:
        raise ValueError("Direct stack targets require one optional predicate")
    schema: dict[str, Any] = {
        "zones": ["stack"],
        "categories": category_values,
        "source_exclusion": True,
        "count": 1,
    }
    if any_values:
        schema["types_any"] = any_values
    elif none_values:
        schema["types_none"] = none_values
    elif color_values:
        schema["colors_any"] = color_values
    elif predicate is not None:
        if type(predicate) is not str or not predicate:
            raise ValueError("Direct stack predicates must be nonempty")
        schema["predicate"] = predicate
    elif colorless is not None:
        if type(colorless) is not bool:
            raise ValueError("Direct stack colorless predicates must be boolean")
        schema["colorless"] = colorless
    return schema


def compiled_direct_target(
    *,
    template_id: str,
    effects: tuple[Mapping[str, Any], ...],
    target_schema: Mapping[str, Any],
    mechanics: tuple[str, ...],
) -> CompiledDirectTarget:
    if type(template_id) is not str or not template_id:
        raise ValueError("Direct-target templates require an identity")
    if len(effects) != 1 or not isinstance(effects[0], Mapping):
        raise ValueError("Direct-target templates require one effect")
    if not isinstance(target_schema, Mapping):
        raise ValueError("Direct-target templates require a target schema")
    mechanic_values = _closed_values(
        mechanics,
        field="mechanics",
        required=True,
    )
    return template_id, effects, target_schema, tuple(mechanic_values)


__all__ = [
    "CompiledDirectTarget",
    "compiled_direct_target",
    "direct_target_effect",
    "direct_target_slug",
    "permanent_target_schema",
    "stack_target_schema",
]
