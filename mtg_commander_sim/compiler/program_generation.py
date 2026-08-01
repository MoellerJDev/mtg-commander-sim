from __future__ import annotations

from dataclasses import asdict
import hashlib
from typing import Any, Iterable

from ..carddb import CardDatabase, CardRecord
from ..rules.capabilities import CapabilityRegistry
from ..semantics import SemanticProgram, SemanticRegistry
from ..util import stable_json


def rulings_source_hash(db: CardDatabase, record: CardRecord) -> str:
    rows = sorted(
        (asdict(ruling) for ruling in db.rulings(record)),
        key=lambda row: (
            str(row["published_at"]),
            str(row["source"]),
            str(row["comment"]),
            str(row["oracle_id"]),
        ),
    )
    return hashlib.sha256(stable_json(rows).encode("utf-8")).hexdigest()


def generated_programs(
    db: CardDatabase,
    record: CardRecord,
    *,
    trust_level: str = "provisional",
    trusted_mechanics: Iterable[str] = (),
    capability_registry: CapabilityRegistry | None = None,
    capability_profile: str = "traditional",
) -> list[SemanticProgram]:
    """Lower exact Oracle IR nodes into the generic effect DSL."""

    # Imported lazily so oracle_ir can retain its stable public compatibility
    # functions without creating a module-initialization cycle.
    from ..oracle_ir import ORACLE_COMPILER_VERSION, compile_oracle_card

    ir = compile_oracle_card(
        record,
        trusted_mechanics=trusted_mechanics,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )
    if trust_level == "trusted" and ir.status != "exact":
        raise ValueError(
            f"{record.name} cannot be promoted to trusted generated "
            "semantics while material Oracle residuals remain"
        )
    programs: list[SemanticProgram] = []
    rulings_hash = rulings_source_hash(db, record)
    for face in ir.faces:
        for node in face.nodes:
            if not node.lowerable or not node.effects:
                continue
            if node.kind == "spell_ability":
                ability_id = f"spell:{face.face_id}"
            elif node.kind == "activated_ability":
                ability_id = f"ability:ab{node.span.line}"
            elif node.kind == "triggered_ability":
                ability_id = f"trigger:{face.face_id}:n{node.span.line}"
            else:
                continue
            capability_closure = (
                capability_registry.closure(
                    node.capability_dependencies,
                    profile=capability_profile,
                )
                if capability_registry is not None
                and node.capability_dependencies
                else None
            )
            programs.append(
                SemanticProgram(
                    key=f"{record.oracle_id}:{ability_id}",
                    label=(
                        record.name
                        if node.kind == "spell_ability"
                        else f"{record.name} — {node.text}"
                    ),
                    effects=[dict(effect) for effect in node.effects],
                    destination=(
                        "graveyard" if node.kind == "spell_ability" else None
                    ),
                    requires_arbiter=trust_level != "trusted",
                    version=1,
                    oracle_id=record.oracle_id,
                    ability_id=ability_id,
                    active_zone=node.active_zone,
                    event=node.event,
                    trust_level=trust_level,
                    provenance={
                        "source_oracle_hash": ir.oracle_hash,
                        "source_rulings_hash": rulings_hash,
                        "authored_by": ORACLE_COMPILER_VERSION,
                        "review_status": (
                            "capability_closure_verified"
                            if trust_level == "trusted"
                            and capability_closure is not None
                            and capability_closure.trusted
                            else (
                                "legacy_dependency_verified"
                                if trust_level == "trusted"
                                else "generated_review_required"
                            )
                        ),
                        "template_id": node.template_id,
                        "face_id": face.face_id,
                        "source_span": asdict(node.span),
                        "semantic_hash": ir.semantic_hash,
                        "dependency_trust": (
                            "capability_closure_verified"
                            if capability_closure is not None
                            and capability_closure.trusted
                            else (
                                "pending_mechanic_contracts"
                                if trust_level != "trusted"
                                else "verified"
                            )
                        ),
                        **(
                            {
                                "capability_registry_fingerprint": (
                                    capability_closure.registry_fingerprint
                                ),
                                "capability_closure_fingerprint": (
                                    capability_closure.fingerprint
                                ),
                                "capability_profile": (
                                    capability_closure.profile
                                ),
                            }
                            if capability_closure is not None
                            else {}
                        ),
                    },
                    tests=[f"oracle_template:{node.template_id}"],
                    target_schema=(
                        dict(node.target_schema)
                        if node.target_schema is not None
                        else None
                    ),
                    coverage=[
                        "generated_oracle_ir",
                        "spell_resolution"
                        if node.kind == "spell_ability"
                        else (
                            "triggered_ability"
                            if node.kind == "triggered_ability"
                            else "activated_ability"
                        ),
                        *node.mechanics,
                    ],
                    capability_dependencies=list(
                        node.capability_dependencies
                    ),
                    capability_closure=(
                        capability_closure.to_dict()
                        if capability_closure is not None
                        else None
                    ),
                )
            )
    return programs


def register_generated_programs(
    db: CardDatabase,
    registry: SemanticRegistry,
    records: Iterable[CardRecord],
    *,
    trust_level: str = "provisional",
    trusted_mechanics: Iterable[str] = (),
    capability_registry: CapabilityRegistry | None = None,
    capability_profile: str = "traditional",
) -> dict[str, Any]:
    from ..oracle_ir import ORACLE_COMPILER_VERSION

    generated = 0
    skipped_existing = 0
    cards_seen: set[str] = set()
    for record in records:
        if record.oracle_id in cards_seen:
            continue
        cards_seen.add(record.oracle_id)
        for program in generated_programs(
            db,
            record,
            trust_level=trust_level,
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        ):
            if registry.get(program.key) is not None:
                skipped_existing += 1
                continue
            if (
                program.ability_id.startswith("trigger:")
                and any(
                    existing.trust_level == "trusted"
                    and existing.active_zone == program.active_zone
                    and existing.event == program.event
                    for existing in registry.programs_for_oracle(
                        record.oracle_id
                    )
                )
            ):
                # Reviewed event handlers take precedence. Trigger program
                # keys are author-defined, so key equality alone cannot detect
                # that a reviewed pack already owns this event family.
                skipped_existing += 1
                continue
            registry.put(program)
            generated += 1
    return {
        "cards_considered": len(cards_seen),
        "programs_generated": generated,
        "programs_skipped_existing": skipped_existing,
        "trust_level": trust_level,
        "compiler_version": ORACLE_COMPILER_VERSION,
        "capability_registry_fingerprint": (
            capability_registry.fingerprint
            if capability_registry is not None
            else None
        ),
        "capability_profile": (
            capability_profile if capability_registry is not None else None
        ),
    }
