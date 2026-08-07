from __future__ import annotations

from typing import Any, Protocol

from .cast_timing import (
    CAST_PERMISSION_ACTIVE_ZONE,
    CAST_PERMISSION_EVENT,
    CastTimingPermission,
    canonical_cast_timing_permissions,
)
from .semantic_runtime.cast_permissions import (
    default_cast_permission_registry,
)


class CompiledCastTimingHost(Protocol):
    semantics: Any

    def card_record(self, card: Any) -> Any: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...


def _face_id(record: Any, face_name: str | None) -> str:
    if face_name:
        return str(face_name)
    if getattr(record, "faces", ()):
        return str(record.faces[0].get("name") or "front")
    return "front"


def compiled_cast_timing_permissions(
    host: CompiledCastTimingHost,
    card: Any,
    *,
    face_name: str | None = None,
) -> tuple[CastTimingPermission, ...]:
    """Return trusted precompiled permissions for exactly one selected face."""

    record = host.card_record(card)
    if record is None:
        return ()
    expected_face = _face_id(record, face_name)
    registry = default_cast_permission_registry()
    result: list[CastTimingPermission] = []
    for program in host.semantics.runtime_handler_programs_for_oracle(
        record.oracle_id,
        active_zone=CAST_PERMISSION_ACTIVE_ZONE,
        event=CAST_PERMISSION_EVENT,
    ):
        if not host.semantic_program_is_current_trusted(program):
            continue
        if str(program.provenance.get("face_id") or "") != expected_face:
            continue
        for descriptor in program.handlers:
            if registry.describe(str(descriptor.get("handler_id") or "")):
                result.extend(registry.lower(descriptor, None))
    return canonical_cast_timing_permissions(result)


__all__ = [
    "CompiledCastTimingHost",
    "compiled_cast_timing_permissions",
]
