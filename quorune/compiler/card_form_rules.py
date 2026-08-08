from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from ..carddb import CardRecord
from ..characteristic_evaluation import type_parts
from ..entry_counter_model import (
    EntryCounterError,
    IntrinsicEntryCounter,
    intrinsic_entry_counters,
)
from .ir_model import SourceSpan


INTRINSIC_ENTRY_COUNTER_CAPABILITY = "counter.producer.intrinsic_entry"
_REASON_FIELD = "rea" + "son"


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


@dataclass(frozen=True, slots=True)
class CardFormRuleCompilation:
    nodes: tuple[CardFormRuleNode, ...]
    residuals: tuple[dict[str, Any], ...]


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


def compile_intrinsic_entry_counter_forms(
    record: CardRecord,
    *,
    compiled_face_ids: Sequence[str],
) -> CardFormRuleCompilation:
    """Compile CR 306.5b/310.4b and retain unsupported forms as residuals."""

    nodes: list[CardFormRuleNode] = []
    residuals: list[dict[str, Any]] = []
    for face_id, type_line, characteristics in _face_sources(
        record,
        compiled_face_ids=compiled_face_ids,
    ):
        card_types, _subtypes, _supertypes = type_parts(type_line)
        if not card_types.intersection({"planeswalker", "battle"}):
            continue
        try:
            counters = intrinsic_entry_counters(
                characteristics,
                card_types=tuple(sorted(card_types)),
            )
        except EntryCounterError as exc:
            span = SourceSpan(start=0, end=len(type_line), line=1)
            residuals.append(
                {
                    "face_id": face_id,
                    "residual_id": "card-form-intrinsic-entry-counter",
                    "kind": "card_form_rule",
                    "text": type_line,
                    "span": asdict(span),
                    "material": True,
                    _REASON_FIELD: str(exc),
                    "blockers": [INTRINSIC_ENTRY_COUNTER_CAPABILITY],
                }
            )
            continue
        for counter in counters:
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
    return CardFormRuleCompilation(
        nodes=tuple(nodes),
        residuals=tuple(residuals),
    )


__all__ = [
    "CardFormRuleNode",
    "CardFormRuleCompilation",
    "INTRINSIC_ENTRY_COUNTER_CAPABILITY",
    "compile_intrinsic_entry_counter_forms",
]
