from __future__ import annotations

"""Shared source-pinned runtime access for compiled activated abilities."""

from typing import Any, Protocol


class CompiledActivatedAbilityHost(Protocol):
    semantics: Any

    def card_record(self, card: Any) -> Any: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...


def printed_face(record: Any, card: Any) -> tuple[str, str]:
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


def trusted_face_handler_programs(
    host: CompiledActivatedAbilityHost,
    card: Any,
    *,
    executable_oracle_text: str,
    active_zone: str,
    event: str,
) -> tuple[Any, ...]:
    required = (
        "semantics",
        "card_record",
        "semantic_program_is_current_trusted",
    )
    if not all(hasattr(host, field) for field in required):
        return ()
    record = host.card_record(card)
    if record is None:
        return ()
    expected_face, printed_oracle_text = printed_face(record, card)
    if executable_oracle_text != printed_oracle_text:
        return ()
    return tuple(
        program
        for program in host.semantics.runtime_handler_programs_for_oracle(
            record.oracle_id,
            active_zone=active_zone,
            event=event,
        )
        if host.semantic_program_is_current_trusted(program)
        and str(program.provenance.get("face_id") or "") == expected_face
    )


def trusted_face_handler_family_present(
    host: CompiledActivatedAbilityHost,
    card: Any,
    *,
    active_zone: str,
    event: str,
    handler_id: str,
) -> bool:
    required = (
        "semantics",
        "card_record",
        "semantic_program_is_current_trusted",
    )
    if not all(hasattr(host, field) for field in required):
        return False
    record = host.card_record(card)
    if record is None:
        return False
    expected_face, _ = printed_face(record, card)
    return any(
        str(program.provenance.get("face_id") or "") == expected_face
        and host.semantic_program_is_current_trusted(program)
        and any(
            str(descriptor.get("handler_id") or "") == handler_id
            for descriptor in program.handlers
        )
        for program in host.semantics.runtime_handler_programs_for_oracle(
            record.oracle_id,
            active_zone=active_zone,
            event=event,
        )
    )


__all__ = [
    "CompiledActivatedAbilityHost",
    "printed_face",
    "trusted_face_handler_family_present",
    "trusted_face_handler_programs",
]
