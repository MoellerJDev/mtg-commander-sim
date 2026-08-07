from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .model import StackItem
from .stack_counter import oracle_has_intrinsic_counter_prohibition


class GenericStackResolutionQuery(Protocol):
    semantics: Any

    def card_record(self, object_id: str) -> Any: ...

    def _trusted_generic_spell(self, record: Any) -> bool: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...


@dataclass(frozen=True, slots=True)
class EmptyStackResolution:
    destination: str | None
    note: str


def trusted_generic_empty_resolution(
    host: GenericStackResolutionQuery,
    item: StackItem,
    program: Any,
) -> EmptyStackResolution | None:
    """Plan an empty resolution only for an exact spell without an effect program."""

    if program is not None:
        return None
    trusted = False
    if item.kind == "spell" and item.card_object_id:
        record = host.card_record(item.card_object_id)
        trusted = bool(
            record
            and (
                host._trusted_generic_spell(record)
                or oracle_has_intrinsic_counter_prohibition(
                    host.semantics,
                    str(record.oracle_id),
                    current_trusted=host.semantic_program_is_current_trusted,
                )
            )
        )
    elif item.kind == "spell_copy":
        trusted = bool(item.context.get("copy_permanent_spell"))
    if not trusted:
        return None
    return EmptyStackResolution(
        destination=item.default_destination,
        note="Trusted exact spell resolved with no executable resolution effects",
    )


__all__ = [
    "EmptyStackResolution",
    "GenericStackResolutionQuery",
    "trusted_generic_empty_resolution",
]
