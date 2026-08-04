from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import hashlib
from typing import Any, Iterable, Mapping

from ..carddb import CardDatabase, CardRecord
from ..compiler.program_generation import (
    generated_programs,
    rulings_source_hash,
    runtime_handler_footprint,
)
from ..oracle_ir import ORACLE_COMPILER_VERSION, compile_oracle_card
from ..rules.capabilities import CapabilityRegistry
from ..semantics import SemanticProgram, SemanticRegistry
from .model import CardProgram, CardProgramError, CardProgramFace


SEMANTIC_PACK_COMPATIBILITY_COMPILER = "semantic-pack-v3-card-program-v2"


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_faces(
    record: CardRecord,
    *,
    compiled_face_ids: Iterable[str],
) -> tuple[CardProgramFace, ...]:
    face_ids = tuple(compiled_face_ids)
    if record.faces:
        if len(face_ids) != len(record.faces):
            raise CardProgramError(
                "Compiled face count does not match the card record"
            )
        return tuple(
            CardProgramFace(
                face_id=face_id,
                name=str(face.get("name") or record.name),
                type_line=str(face.get("type_line") or record.type_line),
                oracle_text_hash=_text_hash(
                    str(face.get("oracle_text") or "")
                ),
            )
            for face_id, face in zip(face_ids, record.faces, strict=True)
        )
    return (
        CardProgramFace(
            face_id=face_ids[0] if face_ids else "front",
            name=record.name,
            type_line=record.type_line,
            oracle_text_hash=_text_hash(record.oracle_text),
        ),
    )


def _program_face_id(program: SemanticProgram) -> str:
    explicit = str(program.provenance.get("face_id") or "").strip()
    if explicit:
        return explicit
    parts = program.ability_id.split(":")
    if len(parts) > 1:
        positional = parts[1].split("-", 1)[0]
        if positional in {"front", "back"}:
            return positional
    return "front"


def _bind_program_faces(
    programs: Iterable[SemanticProgram],
    faces: Iterable[CardProgramFace],
) -> tuple[SemanticProgram, ...]:
    face_values = tuple(faces)
    face_ids = {face.face_id for face in face_values}
    only_face = next(iter(face_ids)) if len(face_ids) == 1 else None
    positional_aliases = (
        {
            "front": face_values[0].face_id,
            "back": face_values[1].face_id,
        }
        if len(face_values) == 2
        else {}
    )
    result = []
    for program in programs:
        face_id = _program_face_id(program)
        if face_id in face_ids:
            result.append(program)
            continue
        if face_id in positional_aliases:
            provenance = dict(program.provenance)
            provenance["face_id"] = positional_aliases[face_id]
            provenance["face_identity_adapter"] = (
                "two_face_positional_alias"
            )
            result.append(replace(program, provenance=provenance))
            continue
        if only_face is None:
            raise CardProgramError(
                f"Ability {program.ability_id} has no unambiguous face identity"
            )
        provenance = dict(program.provenance)
        provenance["face_id"] = only_face
        provenance["face_identity_adapter"] = "single_face_compatibility"
        result.append(replace(program, provenance=provenance))
    return tuple(result)


def compile_card_program(
    db: CardDatabase,
    record: CardRecord,
    *,
    semantic_registry: SemanticRegistry | None = None,
    capability_registry: CapabilityRegistry | None = None,
    capability_profile: str = "traditional",
    trust_level: str = "provisional",
    trusted_mechanics: Iterable[str] = (),
) -> CardProgram:
    """Compile one pinned record and overlay reviewed ability programs by key."""

    ir = compile_oracle_card(
        record,
        trusted_mechanics=trusted_mechanics,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )
    programs = {
        program.key: program
        for program in generated_programs(
            db,
            record,
            trust_level=trust_level,
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
    }
    reviewed_keys: list[str] = []
    if semantic_registry is not None:
        for program in semantic_registry.programs_for_oracle(record.oracle_id):
            reviewed_footprint = runtime_handler_footprint(program)
            if reviewed_footprint is not None and program.trust_level == "trusted":
                for key, generated in tuple(programs.items()):
                    if runtime_handler_footprint(generated) == reviewed_footprint:
                        programs.pop(key)
            programs[program.key] = program
            reviewed_keys.append(program.key)
    faces = _record_faces(
        record,
        compiled_face_ids=(face.face_id for face in ir.faces),
    )
    abilities = _bind_program_faces(programs.values(), faces)
    residuals = [
        {"face_id": face.face_id, **residual.to_dict()}
        for face in ir.faces
        for residual in face.residuals
    ]
    return CardProgram.create(
        compiler_version=ORACLE_COMPILER_VERSION,
        oracle_id=record.oracle_id,
        card_name=record.name,
        faces=faces,
        oracle_source_hash=ir.oracle_hash,
        rulings_source_hash=rulings_source_hash(db, record),
        abilities=abilities,
        residuals=residuals,
        provenance={
            "source": "oracle_ir_with_semantic_pack_overlay",
            "oracle_ir_schema_version": ir.schema_version,
            "oracle_ir_semantic_hash": ir.semantic_hash,
            "reviewed_semantic_keys": sorted(reviewed_keys),
            "capability_profile": (
                capability_profile if capability_registry is not None else None
            ),
            "capability_registry_fingerprint": (
                capability_registry.fingerprint
                if capability_registry is not None
                else None
            ),
        },
    )


def card_program_from_semantic_programs(
    programs: Iterable[SemanticProgram],
    *,
    card_name: str | None = None,
) -> CardProgram:
    """Adapt one legacy semantic-pack Oracle group into CardProgram V2."""

    # CardProgram is the pinned canonical artifact. Keep its abilities
    # independent from the mutable legacy compatibility index so later
    # in-memory mutation is detectable at the runtime boundary.
    values = tuple(
        SemanticProgram.from_dict(program.to_dict()) for program in programs
    )
    if not values:
        raise CardProgramError("Cannot adapt an empty semantic program group")
    oracle_ids = {program.oracle_id for program in values}
    if len(oracle_ids) != 1 or None in oracle_ids:
        raise CardProgramError(
            "A semantic compatibility group requires one oracle_id"
        )
    oracle_hashes = {
        str(program.provenance.get("source_oracle_hash") or "")
        for program in values
    } - {""}
    rulings_hashes = {
        str(program.provenance.get("source_rulings_hash") or "")
        for program in values
    } - {""}
    if len(oracle_hashes) > 1:
        raise CardProgramError(
            "Semantic compatibility group has inconsistent Oracle hashes"
        )
    if len(rulings_hashes) > 1:
        raise CardProgramError(
            "Semantic compatibility group has inconsistent rulings hashes"
        )
    face_ids = sorted({_program_face_id(program) for program in values})
    oracle_hash = (
        next(iter(oracle_hashes)) if oracle_hashes else _text_hash("")
    )
    rulings_hash = (
        next(iter(rulings_hashes)) if rulings_hashes else _text_hash("")
    )
    faces = tuple(
        CardProgramFace(
            face_id=face_id,
            name=None,
            type_line=None,
            oracle_text_hash=oracle_hash,
        )
        for face_id in face_ids
    )
    abilities = _bind_program_faces(values, faces)
    return CardProgram.create(
        compiler_version=SEMANTIC_PACK_COMPATIBILITY_COMPILER,
        oracle_id=str(next(iter(oracle_ids))),
        card_name=card_name,
        faces=faces,
        oracle_source_hash=oracle_hash,
        rulings_source_hash=rulings_hash,
        abilities=abilities,
        provenance={
            "source": "semantic_pack_v3_compatibility",
            "face_hash_scope": "card_source_fallback",
            "contains_unpinned_abilities": any(
                not program.provenance.get("source_oracle_hash")
                or not program.provenance.get("source_rulings_hash")
                for program in values
            ),
            "authored_by": sorted(
                {
                    str(program.provenance.get("authored_by"))
                    for program in values
                }
            ),
            "review_statuses": sorted(
                {
                    str(program.provenance.get("review_status"))
                    for program in values
                }
            ),
        },
    )


def card_programs_from_semantic_programs(
    programs: Iterable[SemanticProgram],
) -> dict[str, CardProgram]:
    grouped: dict[str, list[SemanticProgram]] = defaultdict(list)
    for program in programs:
        if program.oracle_id:
            grouped[program.oracle_id].append(program)
    return {
        oracle_id: card_program_from_semantic_programs(values)
        for oracle_id, values in sorted(grouped.items())
    }


def program_fingerprints_for_semantic_keys(
    programs: Mapping[str, CardProgram],
    semantic_keys: Iterable[str],
) -> dict[str, str]:
    requested = set(semantic_keys)
    result: dict[str, str] = {}
    for oracle_id, program in sorted(programs.items()):
        if any(ability.key in requested for ability in program.abilities):
            result[oracle_id] = program.fingerprint
    return result
