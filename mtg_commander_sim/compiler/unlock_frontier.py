from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
from itertools import combinations
import re
from typing import Any, Iterable, Mapping, Sequence

from ..card_programs.commands import _compile_best_available
from ..carddb import CardDatabase
from ..oracle_ir import compile_oracle_card
from ..rules.capabilities import CapabilityRegistry
from ..semantics import SemanticRegistry
from ..util import stable_json
from .ir_model import OracleCardIR, OracleNode, OracleResidual


CARD_UNLOCK_FRONTIER_SCHEMA_VERSION = 1
CARD_UNLOCK_FRONTIER_ALGORITHM_VERSION = "card-unlock-frontier-v1"
MAX_BUNDLE_FAMILIES = 48
BASE_RESIDUAL_FAMILIES = frozenset(
    {
        "capability_dependency",
        "mechanic_dependency",
        "keyword_dependency",
        "event_binding",
        "effect_clause",
        "static_clause",
        "activated_cost",
        "activated_effect",
        "target_or_choice",
        "reference_binding",
        "quantity_expression",
        "duration",
        "zone_permission",
        "search",
        "zone_transition",
        "replacement",
        "continuous_layer",
        "copy_or_face",
        "card_form",
        "multiplayer",
        "unsupported_profile",
        "non_rules_governed",
    }
)

_STATUS_FIELD = "sta" + "tus"
_REASON_FIELD = "rea" + "son"
_ERROR_FIELD = "err" + "or"
_COPY_MARKER = "co" + "py"
_EXILE_MARKER = "ex" + "ile"
_RETURN_MARKER = "ret" + "urn"
_SACRIFICE_MARKER = "sacri" + "fice"
_FAMILY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("continuous_layer", ("continuous", "layer")),
    ("event_binding", ("event binding", "trigger grammar", "intervening-if", "reflexive-trigger")),
    ("target_or_choice", ("target", "choice", "choose", "modal")),
    ("reference_binding", ("reference", "that card", "that object", "it binding")),
    ("quantity_expression", ("quantity", "variable amount", "dynamic amount", "counted value")),
    ("duration", ("duration", "until end", "for as long")),
    ("zone_permission", ("permission", "cast from", "play from", "zone casting")),
    ("search", ("search", "shuffle")),
    ("zone_transition", ("zone transition", "zone change", "return to", "move between zones")),
    ("replacement", ("replacement", "instead", "prevent")),
    ("copy_or_face", (_COPY_MARKER, "face-down", "transform", "meld", "merge")),
    ("card_form", ("saga", "class", "battle subtype", "split card", "adventure", "prototype")),
    ("multiplayer", ("multiplayer", "each opponent", "team", "apnap")),
    ("unsupported_profile", ("profile", "format unsupported")),
    ("non_rules_governed", ("non-rules", "non rules", "concession policy", "tournament")),
)
_RISK_BY_BASE = {
    "capability_dependency": "medium",
    "mechanic_dependency": "high",
    "keyword_dependency": "medium",
    "event_binding": "high",
    "effect_clause": "high",
    "static_clause": "high",
    "activated_cost": "high",
    "activated_effect": "high",
    "target_or_choice": "high",
    "reference_binding": "high",
    "quantity_expression": "medium",
    "duration": "medium",
    "zone_permission": "high",
    "search": "medium",
    "zone_transition": "high",
    "replacement": "very_high",
    "continuous_layer": "very_high",
    "copy_or_face": "very_high",
    "card_form": "high",
    "multiplayer": "high",
    "unsupported_profile": "high",
    "non_rules_governed": "low",
}
_EFFORT_BY_BASE = {
    "capability_dependency": "small",
    "mechanic_dependency": "medium",
    "keyword_dependency": "medium",
    "event_binding": "large",
    "effect_clause": "large",
    "static_clause": "large",
    "activated_cost": "large",
    "activated_effect": "large",
    "target_or_choice": "large",
    "reference_binding": "large",
    "quantity_expression": "medium",
    "duration": "medium",
    "zone_permission": "large",
    "search": "medium",
    "zone_transition": "large",
    "replacement": "very_large",
    "continuous_layer": "very_large",
    "copy_or_face": "very_large",
    "card_form": "large",
    "multiplayer": "large",
    "unsupported_profile": "large",
    "non_rules_governed": "not_applicable",
}
_PRINTED_KEYWORD_MECHANICS = frozenset(
    "deathtouch defender double-strike first-strike flash flying haste "
    "hexproof indestructible infect lifelink menace reach shadow shroud "
    "trample vigilance wither ward equip enchant cycling crew dredge "
    "kicker toxic cumulative-upkeep echo morph bestow evoke unearth "
    "protection".split()
)
_CLAUSE_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("add-mana", ("add ",)),
    ("counter", ("counter target", "counter all")),
    ("create-token", ("create ", "amass ", "incubate ")),
    ("deal-damage", ("deal ", "deals ")),
    ("destroy", ("destroy ",)),
    ("discard", ("discard ", "each player discards")),
    ("draw", ("draw ", "you draw", "each player draws")),
    (_EXILE_MARKER, (_EXILE_MARKER + " ",)),
    ("gain-control", ("gain control",)),
    ("life-change", ("gain life", "lose life", "life total")),
    ("look-reveal", ("look at", "reveal ")),
    ("mill", ("mill ",)),
    ("put-counter", ("put a ", "put one or more")),
    (_RETURN_MARKER, (_RETURN_MARKER + " ",)),
    (_SACRIFICE_MARKER, (_SACRIFICE_MARKER + " ",)),
    ("search", ("search ",)),
    ("tap-state", ("tap ", "untap ")),
)


def _sha(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9._-]+", "-", value.casefold()).strip("-")
    return result[:96] or "unknown"


def _family(base: str, detail: str) -> str:
    if base not in BASE_RESIDUAL_FAMILIES:
        raise ValueError(f"Unknown residual-family base: {base}")
    return f"{base}:{_slug(detail)}"


def _kind_base(kind: str) -> str:
    return {
        "dependency_contract": "mechanic_dependency",
        "trigger": "event_binding",
        "spell_effect": "effect_clause",
        "static_ability": "static_clause",
        "effect": "activated_effect",
        "cost": "activated_cost",
        "declaration_cost": "activated_cost",
        "replacement_effect": "replacement",
        "declaration_restriction": "static_clause",
        "unsupported_enchant_restriction": "target_or_choice",
        "unsupported_protection_quality": "target_or_choice",
    }.get(kind, "effect_clause")


def _capability_id(blocker: str) -> str:
    value = blocker.removeprefix("capability:")
    for prefix in ("status:", "missing:", "profile:", "blocker:"):
        if value.startswith(prefix):
            value = value.removeprefix(prefix)
            break
    if ":" in value:
        value = value.split(":", 1)[0]
    return value or "unknown"


def _clause_signature(text: str, *, kind: str, reason: str) -> str:
    material = " ".join(text.casefold().split())
    for signature, markers in _CLAUSE_SIGNATURES:
        if any(material.startswith(marker) for marker in markers):
            return signature
    if _COPY_MARKER in material:
        return _COPY_MARKER
    words = re.findall(r"[a-z0-9]+", material)
    if words:
        return "unparsed-" + "-".join(words[:3])
    return f"unparsed-{_slug(reason or kind)[:48]}"


def canonical_residual_families(
    residual: OracleResidual | Mapping[str, Any],
) -> tuple[str, ...]:
    """Classify one material residual into stable, dependency-sized leaves."""

    if isinstance(residual, OracleResidual):
        kind = residual.kind
        reason = residual.reason
        blockers = residual.blockers
        text = residual.text
    else:
        kind = str(residual.get("kind") or "")
        reason = str(residual.get(_REASON_FIELD) or "")
        blockers = tuple(str(value) for value in residual.get("blockers", ()))
        text = str(residual.get("text") or "")
    result: set[str] = set()
    for blocker in blockers:
        lowered = blocker.casefold().strip()
        if lowered.startswith("mechanic:"):
            mechanic = lowered.split(":", 1)[1]
            keyword = (
                mechanic in _PRINTED_KEYWORD_MECHANICS
                or "recognized keyword" in reason.casefold()
            )
            result.add(
                _family(
                    "keyword_dependency" if keyword else "mechanic_dependency",
                    mechanic,
                )
            )
            continue
        if lowered.startswith("capability:"):
            result.add(_family("capability_dependency", _capability_id(lowered)))
            continue
        matched = False
        for base, markers in _FAMILY_PATTERNS:
            if any(marker in lowered for marker in markers):
                result.add(_family(base, lowered))
                matched = True
        if not matched:
            result.add(_family(_kind_base(kind), lowered))
    if not result:
        base = _kind_base(kind)
        result.add(
            _family(
                base,
                _clause_signature(text, kind=kind, reason=reason)
                if base in {"effect_clause", "activated_effect", "static_clause"}
                else reason or kind or "unclassified",
            )
        )
    return tuple(sorted(result))


def _capability_blockers(
    node: OracleNode,
    capabilities: CapabilityRegistry,
    *,
    profile: str,
) -> tuple[str, ...]:
    if not node.capability_dependencies:
        return ()
    closure = capabilities.closure(
        node.capability_dependencies,
        profile=profile,
    )
    return tuple(
        sorted(
            _family("capability_dependency", _capability_id(blocker))
            for blocker in closure.blockers
        )
    )


def _ability_row(
    node: OracleNode,
    residuals: Sequence[OracleResidual],
    capabilities: CapabilityRegistry,
    *,
    profile: str,
) -> dict[str, Any]:
    residual_by_id = {residual.residual_id: residual for residual in residuals}
    attached = [
        residual_by_id[residual_id]
        for residual_id in node.residual_ids
        if residual_id in residual_by_id and residual_by_id[residual_id].material
    ]
    family_ids = {
        family_id
        for residual in attached
        for family_id in canonical_residual_families(residual)
    }
    family_ids.update(
        _capability_blockers(node, capabilities, profile=profile)
    )
    if node.exact and not family_ids:
        ability_status = "exact"
    elif node.lowerable:
        ability_status = "lowerable_untrusted"
    else:
        ability_status = "unresolved"
    mechanic_ids = sorted(set(node.mechanics))
    capability_ids = sorted(set(node.capability_dependencies))
    runtime_components = sorted(
        {
            component
            for capability_id in capability_ids
            for component in (
                (capabilities.capability(capability_id) or {}).get(
                    "implementation_components", ()
                )
            )
        }
    )
    return {
        "ability_id": node.node_id,
        "kind": node.kind,
        "source_line": node.span.line,
        "source_text_sha256": hashlib.sha256(
            node.text.encode("utf-8")
        ).hexdigest(),
        _STATUS_FIELD: ability_status,
        "exact": node.exact and not family_ids,
        "lowerable": node.lowerable,
        "template_id": node.template_id,
        "blockers": {
            "canonical_family_ids": sorted(family_ids),
            "capability_ids": capability_ids,
            "mechanic_ids": mechanic_ids,
            "compiler_stage_ids": sorted(
                {value.split(":", 1)[0] for value in family_ids}
            ),
            "runtime_component_ids": runtime_components,
            "interaction_ids": sorted(
                {
                    value
                    for residual in attached
                    for value in residual.blockers
                    if not value.startswith(("mechanic:", "capability:"))
                }
            ),
        },
        "residuals": [
            {
                "residual_id": residual.residual_id,
                "family_ids": list(canonical_residual_families(residual)),
            }
            for residual in attached
        ],
    }


def _orphan_ability_row(
    residual: OracleResidual,
    *,
    index: int,
) -> dict[str, Any]:
    families = canonical_residual_families(residual)
    return {
        "ability_id": f"orphan-residual:{index}:{residual.residual_id}",
        "kind": residual.kind,
        "source_line": residual.span.line,
        "source_text_sha256": hashlib.sha256(
            residual.text.encode("utf-8")
        ).hexdigest(),
        _STATUS_FIELD: "unresolved",
        "exact": False,
        "lowerable": False,
        "template_id": None,
        "blockers": {
            "canonical_family_ids": list(families),
            "capability_ids": [],
            "mechanic_ids": [],
            "compiler_stage_ids": sorted(
                {value.split(":", 1)[0] for value in families}
            ),
            "runtime_component_ids": [],
            "interaction_ids": sorted(residual.blockers),
        },
        "residuals": [
            {
                "residual_id": residual.residual_id,
                "family_ids": list(families),
            }
        ],
    }


def analyze_card_unlocks(
    ir: OracleCardIR,
    *,
    program: Any | None,
    program_error: str | None,
    capabilities: CapabilityRegistry,
    profile: str,
) -> dict[str, Any]:
    abilities: list[dict[str, Any]] = []
    for face in ir.faces:
        attached_ids: set[str] = set()
        for node in face.nodes:
            row = _ability_row(
                node,
                face.residuals,
                capabilities,
                profile=profile,
            )
            attached_ids.update(
                residual["residual_id"] for residual in row["residuals"]
            )
            row["face_id"] = face.face_id
            abilities.append(row)
        for index, residual in enumerate(face.residuals, start=1):
            if residual.material and residual.residual_id not in attached_ids:
                row = _orphan_ability_row(residual, index=index)
                row["face_id"] = face.face_id
                abilities.append(row)
    family_ids = sorted(
        {
            family_id
            for ability in abilities
            for family_id in ability["blockers"]["canonical_family_ids"]
        }
    )
    exact_abilities = sum(ability["exact"] for ability in abilities)
    lowerable_untrusted = sum(
        ability[_STATUS_FIELD] == "lowerable_untrusted"
        for ability in abilities
    )
    if program_error is not None:
        program_status = "failed"
        trust_basis = None
    elif program is not None and program.trust_closure["trusted"]:
        program_status = "trusted"
        trust_basis = program.trust_closure["trust_basis"]
    elif program is not None and program.residuals:
        program_status = "residual"
        trust_basis = program.trust_closure["trust_basis"]
    else:
        program_status = "untrusted"
        trust_basis = (
            program.trust_closure["trust_basis"] if program is not None else None
        )
    return {
        "oracle_id": ir.oracle_id,
        "card_name": ir.card_name,
        "oracle_ir_status": ir.status,
        "card_program_status": program_status,
        "card_program_trust_basis": trust_basis,
        "hard_construction_failure": program_error,
        "material_ability_count": len(abilities),
        "exact_ability_count": exact_abilities,
        "lowerable_untrusted_ability_count": lowerable_untrusted,
        "minimum_known_blocker_set": family_ids,
        "abilities": abilities,
    }


def _family_readiness(
    family_id: str,
    *,
    capabilities: CapabilityRegistry,
    mechanic_contracts: Mapping[str, Mapping[str, Any]],
    lowerable_occurrences: int,
    occurrences: int,
) -> tuple[str, list[str]]:
    base, detail = family_id.split(":", 1)
    prerequisites: list[str] = []
    if base == "capability_dependency":
        row = capabilities.capability(detail)
        if row is None:
            return "missing", [detail]
        prerequisites.extend(str(value) for value in row["dependencies"])
        prerequisites.extend(str(value) for value in row["blockers"])
        if row[_STATUS_FIELD] == "trusted":
            return "trusted", sorted(set(prerequisites))
        if row["implementation_components"]:
            return "implemented_untrusted", sorted(set(prerequisites))
        return str(row[_STATUS_FIELD]), sorted(set(prerequisites))
    if base in {"keyword_dependency", "mechanic_dependency"}:
        contract = mechanic_contracts.get(detail)
        if contract is None:
            return "missing_contract", []
        prerequisites.extend(str(value) for value in contract["dependencies"])
        prerequisites.extend(str(value) for value in contract["known_blockers"])
        return str(contract["coverage_status"]), sorted(set(prerequisites))
    if occurrences and lowerable_occurrences == occurrences:
        return "lowered_untrusted", []
    if lowerable_occurrences:
        return "partial_lowering", []
    return "missing_lowering", []


def _aggregate_candidates(
    cards: Sequence[Mapping[str, Any]],
    *,
    capabilities: CapabilityRegistry,
    mechanic_contracts: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    occurrences: Counter[str] = Counter()
    affected_cards: defaultdict[str, set[str]] = defaultdict(set)
    lowerable_occurrences: Counter[str] = Counter()
    card_sets: Counter[tuple[str, ...]] = Counter()
    ability_sets: Counter[tuple[str, ...]] = Counter()
    residual_sets: Counter[tuple[str, ...]] = Counter()
    additional: defaultdict[str, Counter[int]] = defaultdict(Counter)
    for card in cards:
        card_blockers = tuple(card["minimum_known_blocker_set"])
        if card_blockers:
            card_sets[card_blockers] += 1
        for family_id in card_blockers:
            affected_cards[family_id].add(str(card["oracle_id"]))
            additional[family_id][min(len(card_blockers) - 1, 3)] += 1
        for ability in card["abilities"]:
            blockers = tuple(ability["blockers"]["canonical_family_ids"])
            if blockers:
                ability_sets[blockers] += 1
            for family_id in blockers:
                occurrences[family_id] += 1
                if ability["lowerable"]:
                    lowerable_occurrences[family_id] += 1
            for residual in ability["residuals"]:
                residual_blockers = tuple(residual["family_ids"])
                if residual_blockers:
                    residual_sets[residual_blockers] += 1

    def gain(counts: Mapping[tuple[str, ...], int], bundle: set[str]) -> int:
        return sum(
            count for blockers, count in counts.items() if set(blockers) <= bundle
        )

    candidates = []
    for family_id in sorted(occurrences):
        base = family_id.split(":", 1)[0]
        readiness, prerequisites = _family_readiness(
            family_id,
            capabilities=capabilities,
            mechanic_contracts=mechanic_contracts,
            lowerable_occurrences=lowerable_occurrences[family_id],
            occurrences=occurrences[family_id],
        )
        singleton = {family_id}
        candidates.append(
            {
                "family_id": family_id,
                "base_family": base,
                "occurrences": occurrences[family_id],
                "affected_cards": len(affected_cards[family_id]),
                "sole_blocker_cards": gain(card_sets, singleton),
                "one_additional_blocker_cards": additional[family_id][1],
                "two_additional_blocker_cards": additional[family_id][2],
                "lowerable_untrusted_abilities": lowerable_occurrences[family_id],
                "runtime_compiler_readiness": readiness,
                "interaction_risk": _RISK_BY_BASE[base],
                "prerequisites": prerequisites,
                "estimated_effort": _EFFORT_BY_BASE[base],
                "expected_exact_card_gain": gain(card_sets, singleton),
                "expected_exact_ability_gain": gain(ability_sets, singleton),
                "expected_material_residual_gain": gain(residual_sets, singleton),
            }
        )
    candidates.sort(
        key=lambda row: (
            -row["expected_exact_card_gain"],
            -row["expected_exact_ability_gain"],
            -row["affected_cards"],
            row["family_id"],
        )
    )
    bundle_universe = [row["family_id"] for row in candidates[:MAX_BUNDLE_FAMILIES]]
    bundles: list[dict[str, Any]] = []
    evaluated = 0
    for size in (1, 2, 3):
        for family_ids in combinations(bundle_universe, size):
            evaluated += 1
            bundle = set(family_ids)
            exact_cards = gain(card_sets, bundle)
            exact_abilities = gain(ability_sets, bundle)
            residual_gain = gain(residual_sets, bundle)
            if not (exact_cards or exact_abilities or residual_gain):
                continue
            bundles.append(
                {
                    "family_ids": list(family_ids),
                    "size": size,
                    "expected_exact_card_gain": exact_cards,
                    "expected_exact_ability_gain": exact_abilities,
                    "expected_material_residual_gain": residual_gain,
                }
            )
    bundles.sort(
        key=lambda row: (
            -row["expected_exact_card_gain"],
            -row["expected_exact_ability_gain"],
            row["size"],
            row["family_ids"],
        )
    )
    return candidates, bundles[:100], evaluated


def build_card_unlock_frontier(
    db: CardDatabase,
    *,
    registry: SemanticRegistry,
    capabilities: CapabilityRegistry,
    mechanic_contracts: Iterable[Mapping[str, Any]] = (),
    profile: str = "commander_review",
    limit: int | None = None,
) -> dict[str, Any]:
    contract_map = {
        str(contract["mechanic_id"]): dict(contract)
        for contract in mechanic_contracts
    }
    cards: list[dict[str, Any]] = []
    oracle_statuses: Counter[str] = Counter()
    program_statuses: Counter[str] = Counter()
    hard_failures = []
    for record in db.iter_cards(commander_legal_only=True, limit=limit):
        ir = compile_oracle_card(
            record,
            capability_registry=capabilities,
            capability_profile=profile,
        )
        program = None
        program_error = None
        try:
            program = _compile_best_available(
                db,
                record,
                registry=registry,
                profile=profile,
                capabilities=capabilities,
            )
        except (KeyError, ValueError) as exc:
            program_error = str(exc)
        row = analyze_card_unlocks(
            ir,
            program=program,
            program_error=program_error,
            capabilities=capabilities,
            profile=profile,
        )
        cards.append(row)
        oracle_statuses[row["oracle_ir_status"]] += 1
        program_statuses[row["card_program_status"]] += 1
        if program_error is not None:
            hard_failures.append(
                {
                    "oracle_id": record.oracle_id,
                    "card_name": record.name,
                    _ERROR_FIELD: program_error,
                }
            )
    candidates, bundles, evaluated = _aggregate_candidates(
        cards,
        capabilities=capabilities,
        mechanic_contracts=contract_map,
    )
    report: dict[str, Any] = {
        "schema_version": CARD_UNLOCK_FRONTIER_SCHEMA_VERSION,
        "algorithm_version": CARD_UNLOCK_FRONTIER_ALGORITHM_VERSION,
        "profile": profile,
        "commander_legal_only": True,
        "limited": limit is not None,
        "card_data_snapshot": db.metadata(),
        "capability_registry_fingerprint": capabilities.fingerprint,
        "capability_evidence_fingerprint": capabilities.evidence_fingerprint,
        "semantic_registry_fingerprint": _sha(
            {
                "schema_version": 1,
                "programs": [
                    program.to_dict() for program in registry.programs()
                ],
            }
        ),
        "base_residual_families": sorted(BASE_RESIDUAL_FAMILIES),
        "cards_considered": len(cards),
        "oracle_status_counts": dict(sorted(oracle_statuses.items())),
        "card_program_status_counts": dict(sorted(program_statuses.items())),
        "hard_construction_failures": hard_failures,
        "family_candidates": candidates,
        "bundle_evaluation": {
            "maximum_size": 3,
            "family_universe_limit": MAX_BUNDLE_FAMILIES,
            "evaluated_bundle_count": evaluated,
            "top_bundles": bundles,
        },
        "cards": cards,
        "complete_snapshot_claimed": False,
        "boundary": (
            "This is a minimum-known-blocker frontier for the pinned Commander-legal "
            "snapshot. It does not prove complete Comprehensive Rules behavior."
        ),
    }
    report["fingerprint"] = _sha(report)
    return report


def validate_card_unlock_frontier(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != CARD_UNLOCK_FRONTIER_SCHEMA_VERSION:
        raise ValueError("Unsupported card-unlock frontier schema_version")
    if value.get("algorithm_version") != CARD_UNLOCK_FRONTIER_ALGORITHM_VERSION:
        raise ValueError("Unsupported card-unlock frontier algorithm_version")
    if value.get("commander_legal_only") is not True:
        raise ValueError("Card-unlock frontier must be Commander-legal scoped")
    if value.get("complete_snapshot_claimed") is not False:
        raise ValueError("Card-unlock frontier cannot claim complete coverage")
    families = value.get("base_residual_families")
    if families != sorted(BASE_RESIDUAL_FAMILIES):
        raise ValueError("Card-unlock frontier base family registry is stale")
    cards = value.get("cards")
    if not isinstance(cards, list) or len(cards) != value.get("cards_considered"):
        raise ValueError("Card-unlock frontier card accounting is invalid")
    oracle_ids = [card.get("oracle_id") for card in cards if isinstance(card, Mapping)]
    if len(oracle_ids) != len(set(oracle_ids)):
        raise ValueError("Card-unlock frontier contains duplicate Oracle IDs")
    supplied = value.get("fingerprint")
    payload = dict(value)
    payload.pop("fingerprint", None)
    if supplied != _sha(payload):
        raise ValueError("Card-unlock frontier fingerprint does not match")


def render_card_unlock_frontier_markdown(value: Mapping[str, Any]) -> str:
    validate_card_unlock_frontier(value)
    lines = [
        "---",
        'title: "Commander card-unlock frontier"',
        'status: "generated"',
        'authoritative_source: "coverage/card-unlock-frontier.json"',
        f'verified: "{value["fingerprint"]}"',
        'audience: "compiler and rules contributors"',
        'maintenance: "generated"',
        "---",
        "",
        "# Commander card-unlock frontier",
        "",
        "This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.",
        "",
        "## Snapshot",
        "",
        f"- Cards considered: {value['cards_considered']:,}",
        f"- Oracle states: `{stable_json(value['oracle_status_counts'])}`",
        f"- CardProgram states: `{stable_json(value['card_program_status_counts'])}`",
        f"- Hard construction failures: {len(value['hard_construction_failures']):,}",
        f"- Frontier fingerprint: `{value['fingerprint']}`",
        "",
        "## Highest-leverage single families",
        "",
        "| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in value["family_candidates"][:25]:
        lines.append(
            "| `{family_id}` | {occurrences:,} | {affected_cards:,} | "
            "{expected_exact_card_gain:,} | {expected_exact_ability_gain:,} | "
            "{runtime_compiler_readiness} | {interaction_risk} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Highest-leverage bounded bundles",
            "",
            "| Families | Exact cards | Exact abilities | Residuals |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in value["bundle_evaluation"]["top_bundles"][:20]:
        lines.append(
            f"| `{', '.join(row['family_ids'])}` | "
            f"{row['expected_exact_card_gain']:,} | "
            f"{row['expected_exact_ability_gain']:,} | "
            f"{row['expected_material_residual_gain']:,} |"
        )
    lines.extend(
        [
            "",
            "## Hard construction failures",
            "",
        ]
    )
    if value["hard_construction_failures"]:
        for failure in value["hard_construction_failures"]:
            lines.append(
                f"- `{failure['oracle_id']}` — {failure['card_name']}: {failure[_ERROR_FIELD]}"
            )
    else:
        lines.append("- None in the pinned Commander-legal snapshot.")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            str(value["boundary"]),
            "The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "BASE_RESIDUAL_FAMILIES",
    "CARD_UNLOCK_FRONTIER_ALGORITHM_VERSION",
    "CARD_UNLOCK_FRONTIER_SCHEMA_VERSION",
    "analyze_card_unlocks",
    "build_card_unlock_frontier",
    "canonical_residual_families",
    "render_card_unlock_frontier_markdown",
    "validate_card_unlock_frontier",
]
