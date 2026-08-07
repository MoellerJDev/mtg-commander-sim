from __future__ import annotations

from typing import Any, Protocol

from .ability_fragments import (
    AbilityFragmentError,
    StaticAbilityFragment,
    ability_fragment_to_dict,
    canonical_ability_fragments,
)
from .enchant_spec import (
    EnchantSpec,
    LinkedGraveyardCreatureEnchantSpec,
    SimpleEnchantSpec,
)
from .semantic_runtime.ability_fragments import fragments_from_descriptors


class CompiledAbilityFragmentHost(Protocol):
    semantics: Any

    def card_record(self, card: Any) -> Any: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...


def _custom_fragments(card: Any) -> tuple[StaticAbilityFragment, ...]:
    characteristics = dict(
        card.annotations.get("object_characteristics")
        or card.annotations.get("token_characteristics")
        or {}
    )
    raw = characteristics.get("ability_fragments", ())
    if not isinstance(raw, (list, tuple)):
        raise AbilityFragmentError(
            "Custom ability_fragments must be an array"
        )
    return canonical_ability_fragments(raw)


def _face_id(record: Any, card: Any, face_name: str | None) -> str:
    if face_name:
        return str(face_name)
    if getattr(card, "active_face", None):
        return str(card.active_face)
    if getattr(record, "faces", ()):
        return str(record.faces[0].get("name") or "front")
    return "front"


def compiled_static_ability_fragments(
    host: CompiledAbilityFragmentHost,
    card: Any,
    *,
    face_name: str | None = None,
) -> tuple[StaticAbilityFragment, ...]:
    """Return trusted, face-pinned executable static-ability fragments.

    Oracle grammar is compiled before game execution. Runtime consumers only
    lower exact handler descriptors already pinned into SemanticPrograms.
    """

    record = host.card_record(card)
    if record is None:
        return _custom_fragments(card)
    expected_face = _face_id(record, card, face_name)
    fragments: list[StaticAbilityFragment] = []
    programs = host.semantics.runtime_handler_programs_for_oracle(
        record.oracle_id,
        active_zone="battlefield",
        event="continuous",
    )
    for program in programs:
        if not host.semantic_program_is_current_trusted(program):
            continue
        if str(program.provenance.get("face_id") or "") != expected_face:
            continue
        fragments.extend(fragments_from_descriptors(program.handlers))
    return canonical_ability_fragments(fragments)


def compiled_enchant_spec(
    host: CompiledAbilityFragmentHost,
    card: Any,
    *,
    face_name: str | None = None,
) -> EnchantSpec | None:
    """Return the one trusted Enchant descriptor pinned before runtime."""

    fragments = compiled_static_ability_fragments(
        host,
        card,
        face_name=face_name,
    )
    specs: tuple[EnchantSpec, ...] = tuple(
        fragment
        for fragment in fragments
        if isinstance(
            fragment,
            (SimpleEnchantSpec, LinkedGraveyardCreatureEnchantSpec),
        )
    )
    if len(specs) == 1:
        return specs[0]
    if specs:
        return None
    record = host.card_record(card)
    if record is None or (face_name and face_name != record.name):
        return None
    program = host.semantics.get(f"{record.oracle_id}:spell:front")
    if (
        program is None
        or not host.semantic_program_is_current_trusted(program)
    ):
        return None
    linked_specs = tuple(
        fragment
        for fragment in fragments_from_descriptors(program.handlers)
        if isinstance(fragment, LinkedGraveyardCreatureEnchantSpec)
    )
    return linked_specs[0] if len(linked_specs) == 1 else None


def compiled_ability_fragment_dicts(
    host: CompiledAbilityFragmentHost,
    card: Any,
    *,
    face_name: str | None = None,
    error_type: type[Exception] | None = None,
) -> list[dict[str, Any]]:
    """Serialize the exact trusted fragments for characteristic evaluation."""

    try:
        return [
            ability_fragment_to_dict(fragment)
            for fragment in compiled_static_ability_fragments(
                host,
                card,
                face_name=face_name,
            )
        ]
    except AbilityFragmentError as exc:
        if error_type is None:
            raise
        raise error_type(str(exc)) from exc


__all__ = [
    "CompiledAbilityFragmentHost",
    "compiled_ability_fragment_dicts",
    "compiled_enchant_spec",
    "compiled_static_ability_fragments",
]
