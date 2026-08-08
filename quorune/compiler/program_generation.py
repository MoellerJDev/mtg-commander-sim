from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
from typing import Any, Iterable, Mapping

from ..carddb import CardDatabase, CardRecord
from ..object_predicate import ObjectQuerySpec
from ..rules.capabilities import (
    CapabilityRegistry,
    capability_covered_mechanics,
)
from ..rules.node_capability_shapes import (
    fixed_damage_node_capabilities,
    mass_destruction_node_capabilities,
    fixed_draw_node_capabilities,
    single_explore_node_capabilities,
    single_proliferate_node_capabilities,
    targeted_counter_node_capabilities,
    targeted_destruction_node_capabilities,
    targeted_exile_node_capabilities,
    targeted_return_to_hand_node_capabilities,
    targeted_tap_state_node_capabilities,
)
from ..semantics import SemanticProgram, SemanticRegistry
from ..util import stable_json


_EXILE_MECHANIC = "exile"


def runtime_handler_footprint(
    program: SemanticProgram,
) -> tuple[str, str, tuple[str, ...]] | None:
    handler_descriptors = tuple(
        sorted(
            _runtime_handler_semantic_descriptor(handler)
            for handler in program.handlers
        )
    )
    if not handler_descriptors or any(
        not value for value in handler_descriptors
    ):
        return None
    return program.active_zone, program.event, handler_descriptors


def _runtime_handler_semantic_descriptor(
    handler: dict[str, Any],
) -> str:
    handler_id = str(handler.get("handler_id") or "")
    if handler_id not in {
        "continuous.anthem.power_toughness.v1",
        "continuous.anthem.fixed-query.v2",
    }:
        return (
            stable_json(_canonical_semantic_value(handler))
            if handler_id
            else ""
        )

    condition = dict(handler.get("condition") or {})
    modifier = dict(handler.get("modifier") or {})
    if handler_id == "continuous.anthem.power_toughness.v1":
        predicate = ObjectQuerySpec(
            zones=("battlefield",),
            types_all=("creature",),
            subtypes_all=tuple(
                condition.get("target_subtypes_all") or ()
            ),
        )
        exclude_source = False
    else:
        predicate = ObjectQuerySpec.from_dict(condition.get("predicate"))
        exclude_source = bool(condition.get("exclude_source", False))
    return stable_json(
        {
            "family": "continuous.anthem.fixed-query",
            "event": str(handler.get("event") or ""),
            "target_controller": str(
                condition.get("target_controller") or ""
            ),
            "predicate": predicate.canonical_dict(),
            "exclude_source": exclude_source,
            "modifier": modifier,
        }
    )


_CANONICAL_QUERY_FIELDS = frozenset(
    ObjectQuerySpec().canonical_dict()
)
_LEGACY_QUERY_FIELDS = _CANONICAL_QUERY_FIELDS - {"types_any"}


def _canonical_semantic_value(value: Any) -> Any:
    """Normalize typed query values inside a complete handler descriptor."""

    if isinstance(value, Mapping):
        fields = frozenset(value)
        if fields in {_CANONICAL_QUERY_FIELDS, _LEGACY_QUERY_FIELDS}:
            return ObjectQuerySpec.from_dict(value).canonical_dict()
        return {
            str(key): _canonical_semantic_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_semantic_value(item) for item in value]
    return value


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
    node_id: str | None = None,
) -> str | None:
    if kind == "spell_ability":
        return f"spell:{face_id}"
    if kind in {"activated_ability", "mana_ability"}:
        return f"ability:ab{line}"
    if kind == "triggered_ability":
        return f"trigger:{face_id}:n{line}"
    if static_declaration:
        if str(node_id or "").endswith(":flash"):
            return f"static:{face_id}:n{line}:flash"
        return f"static:{face_id}:n{line}"
    return None


def _generated_coverage(*, kind: str, runtime_handler: bool) -> str:
    if kind == "spell_ability":
        return "spell_resolution"
    if kind == "triggered_ability":
        return "triggered_ability"
    if kind == "mana_ability":
        return "activated_mana_ability"
    if runtime_handler:
        return "runtime_static_handler"
    return "activated_ability"


def _copy_mapping(value: Any) -> dict[str, Any] | None:
    return dict(value) if value is not None else None


def _validate_generated_program_trust(
    ir: Any,
    *,
    trust_level: str,
) -> None:
    if trust_level != "trusted":
        return
    generated_nodes = tuple(
        node
        for face in ir.faces
        for node in face.nodes
        if node.lowerable
        and (node.effects or node.handlers or node.capability_dependencies)
        and _generated_ability_id(
            kind=node.kind,
            face_id=face.face_id,
            line=node.span.line,
            static_declaration=_generated_static_declaration(node),
            node_id=node.node_id,
        )
        is not None
    )
    if generated_nodes and any(
        _generated_node_is_independently_exact(node)
        for node in generated_nodes
    ):
        return
    raise ValueError(
        f"{ir.card_name} cannot be promoted to trusted generated "
        "semantics while material Oracle residuals remain on "
        "generated nodes"
    )


def _independently_exact_protection_handler(node: Any) -> bool:
    """Allow closed protection fragments on a partially known keyword line.

    Printed comma-separated keyword lists are independent abilities.  A typed
    protection fragment therefore remains exact even when a sibling keyword
    on the same Oracle line lacks a capability contract.  No effect program or
    arbitrary runtime-handler family receives this exception.
    """

    return bool(
        node.kind == "keyword_ability"
        and node.template_id == "printed-keyword-list-v1"
        and not node.effects
        and node.handlers
        and all(
            handler.get("handler_id") == "ability.static.protection.v1"
            for handler in node.handlers
        )
        and tuple(node.capability_dependencies)
        == ("protection.typed.debt",)
    )


def _generated_node_is_independently_exact(node: Any) -> bool:
    return bool(
        node.exact or _independently_exact_protection_handler(node)
    )


def _generated_static_declaration(node: Any) -> bool:
    return bool(
        node.handlers
        or (
            node.kind == "keyword_ability"
            and node.capability_dependencies
        )
        or (
            node.kind == "static_ability"
            and node.template_id
            == "intrinsic-spell-counter-prohibition-v1"
            and tuple(node.capability_dependencies)
            == ("stack.counter.prohibition.intrinsic",)
            and not node.effects
        )
    )


def _is_closed_fixed_damage_program(program: SemanticProgram) -> bool:
    """Recognize only the reviewed fixed-damage effect-program family."""

    template_id = str(program.provenance.get("template_id") or "")
    if not template_id.startswith("damage-"):
        return False
    required = set(
        fixed_damage_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value.startswith("cr-")
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_fixed_draw_program(program: SemanticProgram) -> bool:
    """Recognize only fixed-count draw effect programs with strict shapes."""

    required = set(
        fixed_draw_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value.startswith("cr-")
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_single_explore_program(program: SemanticProgram) -> bool:
    """Recognize only one source or controlled target exploring once."""

    required = set(
        single_explore_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value in {"ex" + "plore", "cr-115-targets"}
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_single_proliferate_program(
    program: SemanticProgram,
) -> bool:
    """Recognize one ordinary Proliferate instruction."""

    required = set(
        single_proliferate_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value == "proliferate"
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_targeted_tap_state_program(
    program: SemanticProgram,
) -> bool:
    """Recognize only the reviewed direct-target tap/untap effect family."""

    required = set(
        targeted_tap_state_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value in {"tap-and-untap", "cr-115-targets"}
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_targeted_counter_program(
    program: SemanticProgram,
) -> bool:
    """Recognize only the reviewed direct stack-counter effect family."""

    required = set(
        targeted_counter_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value in {"counter", "cr-115-targets"}
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_targeted_destruction_program(
    program: SemanticProgram,
) -> bool:
    """Recognize only the reviewed direct-target destruction family."""

    required = set(
        targeted_destruction_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value in {"destroy", "cr-115-targets"}
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_mass_destruction_program(
    program: SemanticProgram,
) -> bool:
    """Recognize only the reviewed fixed affected-set destruction family."""

    required = set(
        mass_destruction_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value in {"destroy", "destroy-fixed-set", "cr-115-targets"}
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_targeted_exile_program(
    program: SemanticProgram,
) -> bool:
    """Recognize only the reviewed direct battlefield exile family."""

    required = set(
        targeted_exile_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value in {_EXILE_MECHANIC, "cr-115-targets"}
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_targeted_return_to_hand_program(
    program: SemanticProgram,
) -> bool:
    """Recognize only the reviewed direct battlefield return family."""

    required = set(
        targeted_return_to_hand_node_capabilities(
            effects=program.effects,
            target_schema=program.target_schema,
            mechanic_ids=(
                value
                for value in program.coverage
                if value in {"return-to-owner-hand", "cr-115-targets"}
            ),
        )
    )
    return bool(required) and required.issubset(
        program.capability_dependencies
    )


def _is_closed_effect_program(program: SemanticProgram) -> bool:
    """Return whether a reviewed capability-shaped effect owns execution."""

    recognizers = (
        _is_closed_fixed_damage_program,
        _is_closed_fixed_draw_program,
        _is_closed_single_explore_program,
        _is_closed_single_proliferate_program,
        _is_closed_targeted_counter_program,
        _is_closed_targeted_destruction_program,
        _is_closed_mass_destruction_program,
        _is_closed_targeted_exile_program,
        _is_closed_targeted_return_to_hand_program,
        _is_closed_targeted_tap_state_program,
    )
    return any(recognizer(program) for recognizer in recognizers)


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
    _validate_generated_program_trust(ir, trust_level=trust_level)
    programs: list[SemanticProgram] = []
    rulings_hash = rulings_source_hash(db, record)
    for face in ir.faces:
        for node in face.nodes:
            if trust_level == "trusted" and not _generated_node_is_independently_exact(node):
                # Trust is a property of the precise source-spanned node, not
                # of every other lowerable sentence printed on the card.  A
                # closed capability declaration may therefore be promoted
                # while an unrelated sibling remains provisional.  The
                # provisional registration pass still retains that sibling,
                # so whole-card trust cannot be inferred from this filtering.
                continue
            runtime_handler_declaration = bool(node.handlers)
            if not node.lowerable or (
                not node.effects
                and not _generated_static_declaration(node)
                and not runtime_handler_declaration
            ):
                continue
            ability_id = _generated_ability_id(
                kind=node.kind,
                face_id=face.face_id,
                line=node.span.line,
                static_declaration=_generated_static_declaration(node),
                node_id=node.node_id,
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
            represented_mechanics = (
                capability_covered_mechanics(
                    node.capability_dependencies
                )
                if trust_level == "trusted"
                and not node.exact
                and _independently_exact_protection_handler(node)
                else node.mechanics
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
                    target_schema=_copy_mapping(node.target_schema),
                    event_condition=_copy_mapping(node.event_condition),
                    coverage=[
                        "generated_oracle_ir",
                        _generated_coverage(
                            kind=node.kind,
                            runtime_handler=runtime_handler_declaration,
                        ),
                        *represented_mechanics,
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


def _trusted_program_is_requested(
    program: SemanticProgram,
    *,
    promotable_effect_keys: set[str],
    promote_exact_trigger_programs: bool,
    promote_exact_effect_programs: bool,
    promote_exact_capability_declarations: bool,
) -> bool:
    return bool(
        program.handlers
        or (
            promote_exact_effect_programs
            and program.key in promotable_effect_keys
            and _is_closed_effect_program(program)
            and program.ability_id.startswith(("spell:", "ability:"))
        )
        or (
            promote_exact_trigger_programs
            and program.ability_id.startswith("trigger:")
        )
        or (
            promote_exact_capability_declarations
            and program.ability_id.startswith("static:")
            and program.capability_dependencies
        )
    )


def _trusted_generated_programs(
    db: CardDatabase,
    record: CardRecord,
    *,
    provisional_programs: list[SemanticProgram],
    promotable_effect_keys: set[str],
    trust_level: str,
    trusted_mechanics: Iterable[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
    promote_exact_runtime_handlers: bool,
    promote_exact_trigger_programs: bool,
    promote_exact_effect_programs: bool,
    promote_exact_capability_declarations: bool,
) -> dict[str, SemanticProgram]:
    promotion_requested = any(
        (
            promote_exact_runtime_handlers,
            promote_exact_trigger_programs,
            promote_exact_effect_programs,
            promote_exact_capability_declarations,
        )
    )
    candidate_exists = bool(
        promote_exact_trigger_programs
        and any(
            program.ability_id.startswith("trigger:")
            for program in provisional_programs
        )
        or any(program.handlers for program in provisional_programs)
        or (
            promote_exact_effect_programs
            and promotable_effect_keys
        )
        or (
            promote_exact_capability_declarations
            and any(
                program.ability_id.startswith("static:")
                and program.capability_dependencies
                for program in provisional_programs
            )
        )
    )
    if (
        not promotion_requested
        or trust_level != "provisional"
        or capability_registry is None
        or not candidate_exists
    ):
        return {}
    try:
        candidates = generated_programs(
            db,
            record,
            trust_level="trusted",
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
    except ValueError as exc:
        if "cannot be promoted to trusted generated semantics" not in str(exc):
            raise
        return {}
    return {
        program.key: program
        for program in candidates
        if _trusted_program_is_requested(
            program,
            promotable_effect_keys=promotable_effect_keys,
            promote_exact_trigger_programs=promote_exact_trigger_programs,
            promote_exact_effect_programs=(
                promote_exact_effect_programs
            ),
            promote_exact_capability_declarations=(
                promote_exact_capability_declarations
            ),
        )
    }


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
    promote_exact_trigger_programs: bool = False,
    promote_exact_effect_programs: bool = False,
    promote_exact_capability_declarations: bool = False,
) -> dict[str, Any]:
    from ..oracle_ir import ORACLE_COMPILER_VERSION

    generated = 0
    skipped_existing = 0
    promoted_runtime_handlers = 0
    promoted_exact_programs = 0
    promoted_exact_effect_programs = 0
    promoted_exact_fixed_damage_programs = 0
    promoted_exact_fixed_draw_programs = 0
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
        program_key_counts = Counter(
            program.key for program in provisional_programs
        )
        promotable_effect_keys = {
            program.key
            for program in provisional_programs
            if program_key_counts[program.key] == 1
            and _is_closed_effect_program(program)
            and program.ability_id.startswith(("spell:", "ability:"))
        }
        trusted_programs = _trusted_generated_programs(
            db,
            record,
            provisional_programs=provisional_programs,
            promotable_effect_keys=promotable_effect_keys,
            trust_level=trust_level,
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
            promote_exact_runtime_handlers=promote_exact_runtime_handlers,
            promote_exact_trigger_programs=promote_exact_trigger_programs,
            promote_exact_effect_programs=(
                promote_exact_effect_programs
            ),
            promote_exact_capability_declarations=(
                promote_exact_capability_declarations
            ),
        )
        for provisional in provisional_programs:
            program = trusted_programs.get(provisional.key, provisional)
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
                promoted_exact_programs += 1
                if program.handlers:
                    promoted_runtime_handlers += 1
                if (
                    program.key in promotable_effect_keys
                    and _is_closed_effect_program(program)
                    and program.ability_id.startswith(
                        ("spell:", "ability:")
                    )
                ):
                    promoted_exact_effect_programs += 1
                    if _is_closed_fixed_damage_program(program):
                        promoted_exact_fixed_damage_programs += 1
                    if _is_closed_fixed_draw_program(program):
                        promoted_exact_fixed_draw_programs += 1
            registry.put(program)
            generated += 1
    return {
        "cards_considered": len(cards_seen),
        "programs_generated": generated,
        "programs_skipped_existing": skipped_existing,
        "runtime_handlers_promoted": promoted_runtime_handlers,
        "exact_programs_promoted": promoted_exact_programs,
        "exact_effect_programs_promoted": promoted_exact_effect_programs,
        "exact_fixed_damage_programs_promoted": (
            promoted_exact_fixed_damage_programs
        ),
        "exact_fixed_draw_programs_promoted": (
            promoted_exact_fixed_draw_programs
        ),
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
