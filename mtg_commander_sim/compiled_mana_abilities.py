from __future__ import annotations

"""Runtime access to trusted, source-pinned activated mana descriptors."""

from typing import Any, Protocol

from .color_set_mana_abilities import ColorSetActivatedManaAbilitySpec
from .fixed_mana_abilities import FixedActivatedManaAbilitySpec
from .semantic_runtime.color_set_mana_abilities import (
    color_set_mana_specs_from_descriptors,
)
from .semantic_runtime.mana_abilities import fixed_mana_specs_from_descriptors


class CompiledManaAbilityHost(Protocol):
    semantics: Any

    def card_record(self, card: Any) -> Any: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...


def _printed_face(record: Any, card: Any) -> tuple[str, str]:
    if not getattr(record, "faces", ()):
        return "front", str(record.oracle_text or "")
    active_face = str(getattr(card, "active_face", None) or "")
    faces = tuple(record.faces)
    face = next(
        (
            candidate
            for candidate in faces
            if active_face
            and str(candidate.get("name") or "") == active_face
        ),
        faces[0],
    )
    return (
        str(face.get("name") or "front"),
        str(face.get("oracle_text") or ""),
    )


def compiled_fixed_mana_abilities(
    host: CompiledManaAbilityHost,
    card: Any,
    *,
    executable_oracle_text: str,
) -> tuple[FixedActivatedManaAbilitySpec, ...]:
    """Return exact descriptors only for the unchanged current printed face."""

    if not all(
        hasattr(host, field)
        for field in (
            "semantics",
            "card_record",
            "semantic_program_is_current_trusted",
        )
    ):
        return ()
    record = host.card_record(card)
    if record is None:
        return ()
    expected_face, printed_oracle_text = _printed_face(record, card)
    if executable_oracle_text != printed_oracle_text:
        return ()
    result: list[FixedActivatedManaAbilitySpec] = []
    programs = host.semantics.runtime_handler_programs_for_oracle(
        record.oracle_id,
        active_zone="battlefield",
        event="activate",
    )
    for program in programs:
        if not host.semantic_program_is_current_trusted(program):
            continue
        if str(program.provenance.get("face_id") or "") != expected_face:
            continue
        result.extend(fixed_mana_specs_from_descriptors(program.handlers))
    return tuple(sorted(result, key=lambda spec: spec.line_index))


def compiled_color_set_mana_abilities(
    host: CompiledManaAbilityHost,
    card: Any,
    *,
    executable_oracle_text: str,
) -> tuple[ColorSetActivatedManaAbilitySpec, ...]:
    """Return exact dynamic descriptors for the unchanged current face."""

    if not all(
        hasattr(host, field)
        for field in (
            "semantics",
            "card_record",
            "semantic_program_is_current_trusted",
        )
    ):
        return ()
    record = host.card_record(card)
    if record is None:
        return ()
    expected_face, printed_oracle_text = _printed_face(record, card)
    if executable_oracle_text != printed_oracle_text:
        return ()
    result: list[ColorSetActivatedManaAbilitySpec] = []
    programs = host.semantics.runtime_handler_programs_for_oracle(
        record.oracle_id,
        active_zone="battlefield",
        event="activate",
    )
    for program in programs:
        if not host.semantic_program_is_current_trusted(program):
            continue
        if str(program.provenance.get("face_id") or "") != expected_face:
            continue
        result.extend(
            color_set_mana_specs_from_descriptors(program.handlers)
        )
    return tuple(sorted(result, key=lambda spec: spec.line_index))


def compiled_fixed_mana_family_present(
    host: CompiledManaAbilityHost,
    card: Any,
) -> bool:
    """Return whether the current face has a trusted fixed-mana owner."""

    if not all(
        hasattr(host, field)
        for field in (
            "semantics",
            "card_record",
            "semantic_program_is_current_trusted",
        )
    ):
        return False
    record = host.card_record(card)
    if record is None:
        return False
    expected_face, _ = _printed_face(record, card)
    return any(
        str(program.provenance.get("face_id") or "") == expected_face
        and host.semantic_program_is_current_trusted(program)
        and bool(fixed_mana_specs_from_descriptors(program.handlers))
        for program in host.semantics.runtime_handler_programs_for_oracle(
            record.oracle_id,
            active_zone="battlefield",
            event="activate",
        )
    )


def compiled_color_set_mana_family_present(
    host: CompiledManaAbilityHost,
    card: Any,
) -> bool:
    """Return whether the current face has a trusted color-set mana owner."""

    if not all(
        hasattr(host, field)
        for field in (
            "semantics",
            "card_record",
            "semantic_program_is_current_trusted",
        )
    ):
        return False
    record = host.card_record(card)
    if record is None:
        return False
    expected_face, _ = _printed_face(record, card)
    return any(
        str(program.provenance.get("face_id") or "") == expected_face
        and host.semantic_program_is_current_trusted(program)
        and bool(color_set_mana_specs_from_descriptors(program.handlers))
        for program in host.semantics.runtime_handler_programs_for_oracle(
            record.oracle_id,
            active_zone="battlefield",
            event="activate",
        )
    )


__all__ = [
    "CompiledManaAbilityHost",
    "compiled_color_set_mana_abilities",
    "compiled_color_set_mana_family_present",
    "compiled_fixed_mana_abilities",
    "compiled_fixed_mana_family_present",
]
