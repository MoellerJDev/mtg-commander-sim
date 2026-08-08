from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..carddb import CardRecord
from ..characteristic_evaluation import type_parts
from ..entry_counter_model import (
    IntrinsicEntryCounter,
    intrinsic_entry_counters,
)
from .ir_model import SourceSpan


INTRINSIC_ENTRY_COUNTER_CAPABILITY = "counter.producer.intrinsic_entry"


@dataclass(frozen=True, slots=True)
class CardFormRuleNode:
    """One rules-derived declaration pinned to an exact card face type line."""

    face_id: str
    source_text: str
    span: SourceSpan
    entry_counter: IntrinsicEntryCounter
    capability_dependencies: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.face_id or not self.source_text:
            raise ValueError("Card-form rule nodes require face and source text")
        if self.span.start != 0 or self.span.end != len(self.source_text):
            raise ValueError("Card-form rule source span must cover the type line")
        if self.span.line != 1:
            raise ValueError("Card-form rule source span must use line one")
        if self.capability_dependencies != (
            INTRINSIC_ENTRY_COUNTER_CAPABILITY,
        ):
            raise ValueError(
                "Intrinsic entry nodes require their fine-grained capability"
            )

    def descriptor(self) -> dict[str, Any]:
        return {
            "kind": "intrinsic_entry_counter",
            "counter_name": self.entry_counter.counter_name,
            "amount": self.entry_counter.amount,
            "required_type": self.entry_counter.required_type,
            "rule_id": self.entry_counter.rule_id,
        }


def _face_sources(
    record: CardRecord,
    *,
    compiled_face_ids: Sequence[str],
) -> tuple[tuple[str, str, Mapping[str, Any]], ...]:
    if record.faces:
        if len(compiled_face_ids) != len(record.faces):
            raise ValueError("Compiled face count does not match card faces")
        return tuple(
            (
                face_id,
                str(face.get("type_line") or record.type_line),
                face,
            )
            for face_id, face in zip(
                compiled_face_ids, record.faces, strict=True
            )
        )
    if len(compiled_face_ids) != 1:
        raise ValueError("A single-faced card requires one compiled face")
    return (
        (
            compiled_face_ids[0],
            record.type_line,
            {"loyalty": record.loyalty, "defense": record.defense},
        ),
    )


def intrinsic_entry_counter_nodes(
    record: CardRecord,
    *,
    compiled_face_ids: Sequence[str],
) -> tuple[CardFormRuleNode, ...]:
    """Compile CR 306.5b/310.4b from canonical card-form data once."""

    nodes: list[CardFormRuleNode] = []
    for face_id, type_line, characteristics in _face_sources(
        record,
        compiled_face_ids=compiled_face_ids,
    ):
        card_types, _subtypes, _supertypes = type_parts(type_line)
        for counter in intrinsic_entry_counters(
            characteristics,
            card_types=tuple(sorted(card_types)),
        ):
            nodes.append(
                CardFormRuleNode(
                    face_id=face_id,
                    source_text=type_line,
                    span=SourceSpan(start=0, end=len(type_line), line=1),
                    entry_counter=counter,
                    capability_dependencies=(
                        INTRINSIC_ENTRY_COUNTER_CAPABILITY,
                    ),
                )
            )
    return tuple(nodes)


__all__ = [
    "CardFormRuleNode",
    "INTRINSIC_ENTRY_COUNTER_CAPABILITY",
    "intrinsic_entry_counter_nodes",
]
