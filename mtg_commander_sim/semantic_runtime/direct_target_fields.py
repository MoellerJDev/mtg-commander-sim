from __future__ import annotations

"""Strict structural validation shared by independent direct-target owners."""

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError


_REASON_FIELD = "reason"


@dataclass(frozen=True, slots=True)
class DirectTargetFields:
    object_ref: str
    reason: str
    replacement_selections: tuple[Any, ...] = ()


def validate_direct_target_effect(
    effect: Mapping[str, Any],
    context: ReadOnlyHandlerContext,
    *,
    operation: str,
    reference_field: str,
    family_label: str,
    allow_replacement_selections: bool,
) -> DirectTargetFields:
    allowed = {"op", reference_field, _REASON_FIELD}
    if allow_replacement_selections:
        allowed.add("_replacement_selections")
    unknown = sorted(set(effect) - allowed)
    if unknown:
        raise SemanticNodeError(
            f"{family_label} effect has unknown fields: " + ", ".join(unknown)
        )
    if effect.get("op") != operation:
        raise SemanticNodeError(f"{family_label} operation is unsupported")
    object_ref = effect.get(reference_field)
    if type(object_ref) is not str or not object_ref:
        raise SemanticNodeError(
            f"{family_label} effects require one nonempty target reference"
        )
    raw_reason = effect.get(_REASON_FIELD)
    if raw_reason is not None and (type(raw_reason) is not str or not raw_reason):
        raise SemanticNodeError(
            f"{family_label} effect reason must be a nonempty string"
        )
    raw_selections = effect.get("_replacement_selections", ())
    if raw_selections is None:
        raw_selections = ()
    if not allow_replacement_selections and raw_selections:
        raise SemanticNodeError(
            f"{family_label} effects do not accept replacement selections"
        )
    if not isinstance(raw_selections, (list, tuple)):
        raise SemanticNodeError(
            f"{family_label} replacement selections must be an array"
        )
    return DirectTargetFields(
        object_ref=object_ref,
        reason=raw_reason or context.default_reason,
        replacement_selections=tuple(raw_selections),
    )


__all__ = ["DirectTargetFields", "validate_direct_target_effect"]
