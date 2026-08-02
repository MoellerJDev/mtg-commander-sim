from __future__ import annotations

from dataclasses import asdict
import hashlib
from typing import Any, Iterable

from ..carddb import CardDatabase, CardRecord
from ..rules.capabilities import CapabilityRegistry
from ..semantics import SemanticProgram, SemanticRegistry
from ..util import stable_json


def runtime_handler_footprint(
    program: SemanticProgram,
) -> tuple[str, str, tuple[str, ...]] | None:
    handler_ids = tuple(
        sorted(str(handler.get("handler_id") or "") for handler in program.handlers)
    )
    if not handler_ids or any(not value for value in handler_ids):
        return None
    return program.active_zone, program.event, handler_ids


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


def _generated_ability_id(
    *,
    kind: str,
    face_id: str,
    line: int,
    static_declaration: bool,
) -> str | None:
    if kind == "spell_ability":
        return f"spell:{face_id}"
    if kind == "activated_ability":
        return f"ability:ab{line}"
    if kind == "triggered_ability":
        return f"trigger:{face_id}:n{line}"
    if static_declaration:
        return f"static:{face_id}:n{line}"
    return None


def _generated_coverage(*, kind: str, runtime_handler: bool) -> str:
    if kind == "spell_ability":
        return "spell_resolution"
    if kind == "triggered_ability":
        return "triggered_ability"
    if runtime_handler:
        return "runtime_static_handler"
    return "activated_ability"


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
            keyword_declaration = (
                node.kind == "keyword_ability"
                and bool(node.capability_dependencies)
            )
            runtime_handler_declaration = bool(node.handlers)
            if not node.lowerable or (
                not node.effects
                and not keyword_declaration
                and not runtime_handler_declaration
            ):
                continue
            ability_id = _generated_ability_id(
                kind=node.kind,
                face_id=face.face_id,
                line=node.span.line,
                static_declaration=(
                    keyword_declaration or runtime_handler_declaration
                ),
            )
            if ability_id is None:
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
                    handlers=[dict(handler) for handler in node.handlers],
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
                        _generated_coverage(
                            kind=node.kind,
                            runtime_handler=runtime_handler_declaration,
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
    promote_exact_runtime_handlers: bool = False,
) -> dict[str, Any]:
    from ..oracle_ir import ORACLE_COMPILER_VERSION

    generated = 0
    skipped_existing = 0
    promoted_runtime_handlers = 0
    cards_seen: set[str] = set()
    for record in records:
        if record.oracle_id in cards_seen:
            continue
        cards_seen.add(record.oracle_id)
        provisional_programs = generated_programs(
            db,
            record,
            trust_level=trust_level,
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
        trusted_handlers: dict[str, SemanticProgram] = {}
        if (
            promote_exact_runtime_handlers
            and trust_level == "provisional"
            and capability_registry is not None
            and any(program.handlers for program in provisional_programs)
        ):
            try:
                trusted_handlers = {
                    program.key: program
                    for program in generated_programs(
                        db,
                        record,
                        trust_level="trusted",
                        trusted_mechanics=trusted_mechanics,
                        capability_registry=capability_registry,
                        capability_profile=capability_profile,
                    )
                    if program.handlers
                }
            except ValueError as exc:
                if "cannot be promoted to trusted generated semantics" not in str(exc):
                    raise
        for provisional in provisional_programs:
            program = trusted_handlers.get(provisional.key, provisional)
            if registry.get(program.key) is not None:
                skipped_existing += 1
                continue
            footprint = runtime_handler_footprint(program)
            if footprint is not None and any(
                existing.trust_level == "trusted"
                and runtime_handler_footprint(existing) == footprint
                for existing in registry.programs_for_oracle(record.oracle_id)
            ):
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
            if program is not provisional:
                promoted_runtime_handlers += 1
            registry.put(program)
            generated += 1
    return {
        "cards_considered": len(cards_seen),
        "programs_generated": generated,
        "programs_skipped_existing": skipped_existing,
        "runtime_handlers_promoted": promoted_runtime_handlers,
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
