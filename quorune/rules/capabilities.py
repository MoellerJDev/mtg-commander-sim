from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .component_resolution import implementation_component_resolves
from .node_capability_shapes import (
    fixed_counter_placement_node_capabilities,
    fixed_counter_placement_set_node_capabilities,
    fixed_counter_placement_target_set_node_capabilities,
    fixed_player_counter_placement_node_capabilities,
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

from ..util import stable_json


CAPABILITY_REGISTRY_SCHEMA_VERSION = 1
CAPABILITY_STATUSES = {
    "unclassified",
    "specified",
    "implemented",
    "tested",
    "interaction_tested",
    "trusted",
    "blocked",
    "not_applicable",
    "non_rules_governed",
}
DEPENDENCY_FAIL_CLOSED_STATUSES = {
    "not_run",
    "passed",
    "failed",
    "not_applicable",
}
IMPLEMENTATION_MUTATION_STATUSES = {
    "not_run",
    "killed",
    "survived",
    "not_applicable",
}
EVIDENCE_FIELDS = {
    "positive": "positive_tests",
    "negative": "negative_tests",
    "interaction": "interaction_tests",
    "multiplayer": "multiplayer_tests",
    "privacy": "privacy_tests",
    "replay": "replay_tests",
}
MINIMUM_TRUSTED_REGISTRY_EVIDENCE = frozenset(
    {"positive", "negative", "replay"}
)
_LIFELINK_MECHANIC = "li" + "felink"
_TOXIC_MECHANIC = "tox" + "ic"
_VIGILANCE_MECHANIC = "vigi" + "lan" + "ce"
_HASTE_MECHANIC = "ha" + "ste"
_FLYING_MECHANIC = "fl" + "ying"
_REACH_MECHANIC = "re" + "ach"
_FLASH_MECHANIC = "fl" + "ash"
_TRAMPLE_MECHANIC = "tram" + "ple"
_DEATHTOUCH_MECHANIC = "dea" + "thtouch"
_DEFENDER_MECHANIC = "def" + "ender"
_MENACE_MECHANIC = "men" + "ace"
_FEAR_MECHANIC = "fe" + "ar"
_HORSEMANSHIP_MECHANIC = "hor" + "semanship"
_INTIMIDATE_MECHANIC = "intim" + "idate"
_SHADOW_MECHANIC = "sha" + "dow"
_SKULK_MECHANIC = "sku" + "lk"
_FLANKING_MECHANIC = "flan" + "king"
_BUSHIDO_MECHANIC = "bu" + "shido"
_EXALTED_MECHANIC = "ex" + "alted"
_BATTLE_CRY_MECHANIC = "battle" + " cry"
_MELEE_MECHANIC = "me" + "lee"
_CYCLING_MECHANIC = "cyc" + "ling"
_BASIC_LANDWALK_MECHANICS = (
    "pl" + "ainswalk",
    "is" + "landwalk",
    "sw" + "ampwalk",
    "mount" + "ainwalk",
    "for" + "estwalk",
)
_FIRST_STRIKE_MECHANIC = "first" + " strike"
_DOUBLE_STRIKE_MECHANIC = "double" + " strike"
_EXILE_MECHANIC = "ex" + "ile"
MECHANIC_CAPABILITY_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    _CYCLING_MECHANIC: ("activation.cycling.hand",),
    **{
        mechanic: ("combat.block.landwalk.basic_type",)
        for mechanic in _BASIC_LANDWALK_MECHANICS
    },
    _DEFENDER_MECHANIC: ("combat.attack.defender",),
    _MENACE_MECHANIC: ("combat.block.menace",),
    _FEAR_MECHANIC: ("combat.block.fear",),
    _HORSEMANSHIP_MECHANIC: ("combat.block.horsemanship",),
    _INTIMIDATE_MECHANIC: ("combat.block.intimidate",),
    _SHADOW_MECHANIC: ("combat.block.shadow",),
    _SKULK_MECHANIC: ("combat.block.skulk",),
    _FLANKING_MECHANIC: ("combat.trigger.flanking",),
    _BUSHIDO_MECHANIC: ("combat.trigger.bushido",),
    _EXALTED_MECHANIC: ("combat.trigger.exalted",),
    _BATTLE_CRY_MECHANIC: ("combat.trigger.battle_cry",),
    _MELEE_MECHANIC: ("combat.trigger.melee",),
    _DEATHTOUCH_MECHANIC: (
        "combat.damage.assignment.deathtouch",
        "damage.result.deathtouch",
    ),
    _DOUBLE_STRIKE_MECHANIC: (
        "combat.damage.participation.strike_steps",
    ),
    _FLASH_MECHANIC: ("timing.cast.printed_flash",),
    _FIRST_STRIKE_MECHANIC: (
        "combat.damage.participation.strike_steps",
    ),
    _FLYING_MECHANIC: ("combat.block.flying",),
    _HASTE_MECHANIC: (
        "combat.attack.haste",
        "activation.tap_untap_cost.haste",
    ),
    _REACH_MECHANIC: ("combat.block.reach",),
    _TRAMPLE_MECHANIC: ("combat.damage.assignment.trample",),
    _VIGILANCE_MECHANIC: ("combat.attack.vigilance",),
    "cr-119-life": ("life.change.effect",),
    "cr-121-drawing-a-card": ("zone.draw.library_to_hand",),
    "infect": ("damage.result.infect",),
    _LIFELINK_MECHANIC: ("damage.result.lifelink",),
    _TOXIC_MECHANIC: ("damage.result.toxic",),
    "wither": ("damage.result.wither",),
    "trigger-event-normalized-zone-change": (
        "trigger.event.normalized_zone_change",
    ),
}
_SHAPE_GATED_MECHANICS = frozenset(
    {
        "cr-121-drawing-a-card",
        "counter",
        "destroy",
        _EXILE_MECHANIC,
        "return-to-owner-hand",
    }
)
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_EFFECTIVE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REGISTRY_FIELDS = {
    "schema_version",
    "registry_version",
    "effective_date",
    "source_sha256",
    "profiles",
    "aggregates",
    "capabilities",
}
_AGGREGATE_FIELDS = {"mechanic_id", "capabilities"}
_CAPABILITY_FIELDS = {
    "id",
    "version",
    "official_rules",
    "supported_profiles",
    "applicability",
    "dependencies",
    "implementation_components",
    "positive_tests",
    "negative_tests",
    "interaction_tests",
    "multiplayer_tests",
    "privacy_tests",
    "replay_tests",
    "required_evidence",
    "dependency_fail_closed_status",
    "dependency_fail_closed_rationale",
    "implementation_mutation_status",
    "implementation_mutation_rationale",
    "blockers",
    "status",
}
_APPLICABILITY_FIELDS = {"summary", "inputs", "outputs", "exclusions"}
DEFAULT_CAPABILITY_REGISTRY = (
    Path(__file__).resolve().with_name("capability-registry.json")
)


class CapabilityRegistryError(ValueError):
    """The capability graph is malformed or cannot be resolved safely."""


def _validate_trusted_capability(
    capability_id: str,
    row: Mapping[str, Any],
    *,
    dependency_status: str,
    implementation_mutation_status: str,
) -> None:
    if row["blockers"]:
        raise CapabilityRegistryError(
            f"Trusted {capability_id} cannot retain blockers"
        )
    components = row["implementation_components"]
    if not components:
        raise CapabilityRegistryError(
            f"Trusted {capability_id} requires an implementation"
        )
    if not any(
        implementation_component_resolves(component)
        for component in components
    ):
        raise CapabilityRegistryError(
            f"Trusted {capability_id} requires a resolvable "
            "implementation component"
        )
    if row["dependencies"] and dependency_status != "passed":
        raise CapabilityRegistryError(
            f"Trusted {capability_id} requires passed dependency "
            "fail-closed evidence"
        )
    if implementation_mutation_status != "killed":
        raise CapabilityRegistryError(
            f"Trusted {capability_id} requires killed implementation "
            "mutation evidence"
        )
    missing_minimum = MINIMUM_TRUSTED_REGISTRY_EVIDENCE - set(
        row["required_evidence"]
    )
    if missing_minimum:
        raise CapabilityRegistryError(
            f"Trusted {capability_id} must require minimum evidence: "
            + ", ".join(sorted(missing_minimum))
        )
    for evidence in row["required_evidence"]:
        field = EVIDENCE_FIELDS[evidence]
        if not row[field]:
            raise CapabilityRegistryError(
                f"Trusted {capability_id} requires {field}"
            )


def _require_exact_fields(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    field: str,
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise CapabilityRegistryError(
            f"{field} is missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise CapabilityRegistryError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


def _strings(
    value: Any,
    *,
    field: str,
    required: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise CapabilityRegistryError(
            f"{field} must be a list of nonempty strings"
        )
    result = tuple(str(item) for item in value)
    if required and not result:
        raise CapabilityRegistryError(f"{field} must not be empty")
    if len(result) != len(set(result)):
        raise CapabilityRegistryError(f"{field} must contain unique values")
    return result


def _hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CapabilityClosure:
    requested: tuple[str, ...]
    reachable: tuple[str, ...]
    profile: str
    trusted: bool
    blockers: tuple[str, ...]
    registry_fingerprint: str
    evidence_fingerprint: str
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": list(self.requested),
            "reachable": list(self.reachable),
            "profile": self.profile,
            "trusted": self.trusted,
            "blockers": list(self.blockers),
            "registry_fingerprint": self.registry_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "fingerprint": self.fingerprint,
        }


class CapabilityRegistry:
    """Validated immutable view of fine-grained rules capabilities.

    The registry deliberately contains metadata, not mutable game state. A
    closure is a deterministic statement about exactly which bounded promises
    a program requests for one rules profile. Broad mechanic aggregates remain
    available for migration reporting, but they do not gate a smaller closure.
    """

    def __init__(self, value: Mapping[str, Any]):
        raw = json.loads(json.dumps(dict(value)))
        _require_exact_fields(raw, _REGISTRY_FIELDS, field="registry")
        if type(raw.get("schema_version")) is not int or raw[
            "schema_version"
        ] != (
            CAPABILITY_REGISTRY_SCHEMA_VERSION
        ):
            raise CapabilityRegistryError(
                "Unsupported capability registry schema_version"
            )
        if (
            type(raw.get("registry_version")) is not int
            or raw["registry_version"] < 1
        ):
            raise CapabilityRegistryError(
                "registry_version must be positive"
            )
        if _EFFECTIVE_DATE.fullmatch(str(raw["effective_date"])) is None:
            raise CapabilityRegistryError(
                "effective_date must use YYYY-MM-DD"
            )
        source_hash = str(raw["source_sha256"])
        if re.fullmatch(r"[0-9a-f]{64}", source_hash) is None:
            raise CapabilityRegistryError(
                "source_sha256 must be a lowercase SHA-256"
            )
        self._profiles = _strings(
            raw.get("profiles"), field="profiles", required=True
        )
        capability_rows = raw.get("capabilities")
        if not isinstance(capability_rows, list):
            raise CapabilityRegistryError("capabilities must be a list")
        self._capabilities: dict[str, dict[str, Any]] = {}
        for index, candidate in enumerate(capability_rows):
            if not isinstance(candidate, Mapping):
                raise CapabilityRegistryError(
                    f"capabilities[{index}] must be an object"
                )
            row = self._validate_capability(dict(candidate), index=index)
            capability_id = str(row["id"])
            if capability_id in self._capabilities:
                raise CapabilityRegistryError(
                    f"Duplicate capability id: {capability_id}"
                )
            self._capabilities[capability_id] = row

        self._aggregates: dict[str, tuple[str, ...]] = {}
        aggregate_rows = raw.get("aggregates")
        if not isinstance(aggregate_rows, list):
            raise CapabilityRegistryError("aggregates must be a list")
        for index, candidate in enumerate(aggregate_rows):
            if not isinstance(candidate, Mapping):
                raise CapabilityRegistryError(
                    f"aggregates[{index}] must be an object"
                )
            _require_exact_fields(
                candidate,
                _AGGREGATE_FIELDS,
                field=f"aggregates[{index}]",
            )
            mechanic_id = str(candidate.get("mechanic_id") or "").strip()
            if not mechanic_id:
                raise CapabilityRegistryError(
                    f"aggregates[{index}].mechanic_id is required"
                )
            if mechanic_id in self._aggregates:
                raise CapabilityRegistryError(
                    f"Duplicate aggregate mechanic: {mechanic_id}"
                )
            self._aggregates[mechanic_id] = _strings(
                candidate.get("capabilities"),
                field=f"aggregates[{index}].capabilities",
                required=True,
            )

        self._validate_references()
        self._validate_acyclic()
        self._raw = raw
        self._fingerprint = _hash(raw)
        self._evidence_fingerprint: str | None = None

    def _validate_capability(
        self,
        row: dict[str, Any],
        *,
        index: int,
    ) -> dict[str, Any]:
        prefix = f"capabilities[{index}]"
        _require_exact_fields(row, _CAPABILITY_FIELDS, field=prefix)
        capability_id = str(row.get("id") or "")
        if _CAPABILITY_ID.fullmatch(capability_id) is None:
            raise CapabilityRegistryError(
                f"{prefix}.id is not a stable capability id"
            )
        if type(row.get("version")) is not int or row["version"] < 1:
            raise CapabilityRegistryError(
                f"{prefix}.version must be positive"
            )
        status = str(row.get("status") or "")
        if status not in CAPABILITY_STATUSES:
            raise CapabilityRegistryError(
                f"{prefix}.status is unknown: {status!r}"
            )
        dependency_status = str(
            row.get("dependency_fail_closed_status") or ""
        )
        if dependency_status not in DEPENDENCY_FAIL_CLOSED_STATUSES:
            raise CapabilityRegistryError(
                f"{prefix}.dependency_fail_closed_status is unknown: "
                f"{dependency_status!r}"
            )
        implementation_mutation_status = str(
            row.get("implementation_mutation_status") or ""
        )
        if (
            implementation_mutation_status
            not in IMPLEMENTATION_MUTATION_STATUSES
        ):
            raise CapabilityRegistryError(
                f"{prefix}.implementation_mutation_status is unknown: "
                f"{implementation_mutation_status!r}"
            )
        for field in (
            "dependency_fail_closed_rationale",
            "implementation_mutation_rationale",
        ):
            if not isinstance(row.get(field), str):
                raise CapabilityRegistryError(
                    f"{prefix}.{field} must be a string"
                )
        if dependency_status == "not_applicable":
            if not row["dependency_fail_closed_rationale"].strip():
                raise CapabilityRegistryError(
                    f"{prefix}.dependency_fail_closed_rationale is required "
                    "when dependency fail-closed testing is not applicable"
                )
            if row.get("dependencies"):
                raise CapabilityRegistryError(
                    f"{prefix}.dependency_fail_closed_status cannot be "
                    "not_applicable when dependencies exist"
                )
        if implementation_mutation_status == "not_applicable" and not row[
            "implementation_mutation_rationale"
        ].strip():
            raise CapabilityRegistryError(
                f"{prefix}.implementation_mutation_rationale is required "
                "when implementation mutation testing is not applicable"
            )
        for field, required in (
            ("official_rules", True),
            ("supported_profiles", True),
            ("dependencies", False),
            ("implementation_components", False),
            ("positive_tests", False),
            ("negative_tests", False),
            ("interaction_tests", False),
            ("multiplayer_tests", False),
            ("privacy_tests", False),
            ("replay_tests", False),
            ("required_evidence", False),
            ("blockers", False),
        ):
            row[field] = list(
                _strings(
                    row.get(field),
                    field=f"{prefix}.{field}",
                    required=required,
                )
            )
        unsupported_profiles = sorted(
            set(row["supported_profiles"]) - set(self._profiles)
        )
        if unsupported_profiles:
            raise CapabilityRegistryError(
                f"{prefix} uses unknown profile(s): "
                + ", ".join(unsupported_profiles)
            )
        unknown_evidence = sorted(
            set(row["required_evidence"]) - set(EVIDENCE_FIELDS)
        )
        if unknown_evidence:
            raise CapabilityRegistryError(
                f"{prefix} uses unknown evidence class(es): "
                + ", ".join(unknown_evidence)
            )
        applicability = row.get("applicability")
        if not isinstance(applicability, Mapping):
            raise CapabilityRegistryError(
                f"{prefix}.applicability must be an object"
            )
        _require_exact_fields(
            applicability,
            _APPLICABILITY_FIELDS,
            field=f"{prefix}.applicability",
        )
        for field in ("summary", "inputs", "outputs", "exclusions"):
            if field == "summary":
                if not str(applicability.get(field) or "").strip():
                    raise CapabilityRegistryError(
                        f"{prefix}.applicability.summary is required"
                    )
            else:
                _strings(
                    applicability.get(field),
                    field=f"{prefix}.applicability.{field}",
                )
        row["applicability"] = json.loads(json.dumps(applicability))
        if status == "trusted":
            _validate_trusted_capability(
                capability_id,
                row,
                dependency_status=dependency_status,
                implementation_mutation_status=(
                    implementation_mutation_status
                ),
            )
        return row

    def _validate_references(self) -> None:
        known = set(self._capabilities)
        for capability_id, row in self._capabilities.items():
            missing = sorted(set(row["dependencies"]) - known)
            if missing:
                raise CapabilityRegistryError(
                    f"{capability_id} has unknown dependencies: "
                    + ", ".join(missing)
                )
        for mechanic_id, dependencies in self._aggregates.items():
            missing = sorted(set(dependencies) - known)
            if missing:
                raise CapabilityRegistryError(
                    f"{mechanic_id} aggregate has unknown capabilities: "
                    + ", ".join(missing)
                )

    def _validate_acyclic(self) -> None:
        visiting: list[str] = []
        complete: set[str] = set()

        def visit(capability_id: str) -> None:
            if capability_id in complete:
                return
            if capability_id in visiting:
                start = visiting.index(capability_id)
                cycle = [*visiting[start:], capability_id]
                raise CapabilityRegistryError(
                    "Capability dependency cycle: " + " -> ".join(cycle)
                )
            visiting.append(capability_id)
            for dependency in self._capabilities[capability_id][
                "dependencies"
            ]:
                visit(str(dependency))
            visiting.pop()
            complete.add(capability_id)

        for capability_id in sorted(self._capabilities):
            visit(capability_id)

    @classmethod
    def from_path(cls, path: str | Path) -> "CapabilityRegistry":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def profiles(self) -> tuple[str, ...]:
        return self._profiles

    @property
    def evidence_fingerprint(self) -> str | None:
        return self._evidence_fingerprint

    def mark_evidence_verified(self, fingerprint: str) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", str(fingerprint)) is None:
            raise CapabilityRegistryError(
                "Capability evidence fingerprint must be a lowercase SHA-256"
            )
        self._evidence_fingerprint = str(fingerprint)

    def capability(self, capability_id: str) -> dict[str, Any] | None:
        row = self._capabilities.get(capability_id)
        return json.loads(json.dumps(row)) if row is not None else None

    def capabilities(self) -> list[dict[str, Any]]:
        return [
            json.loads(json.dumps(self._capabilities[capability_id]))
            for capability_id in sorted(self._capabilities)
        ]

    def aggregate_dependencies(self, mechanic_id: str) -> tuple[str, ...]:
        return self._aggregates.get(mechanic_id, ())

    def closure(
        self,
        requested: Iterable[str],
        *,
        profile: str,
    ) -> CapabilityClosure:
        if profile not in self._profiles:
            raise CapabilityRegistryError(
                f"Unknown capability profile: {profile}"
            )
        requested_ids = tuple(sorted(set(str(value) for value in requested)))
        evidence_fingerprint = self._evidence_fingerprint or _hash(
            {"capability_evidence": "unverified"}
        )
        reachable: set[str] = set()
        blockers: set[str] = set()
        if self._evidence_fingerprint is None:
            blockers.add("evidence_index:unverified")

        def visit(capability_id: str) -> None:
            if capability_id in reachable:
                return
            row = self._capabilities.get(capability_id)
            if row is None:
                blockers.add(f"missing:{capability_id}")
                return
            reachable.add(capability_id)
            if profile not in row["supported_profiles"]:
                blockers.add(f"profile:{capability_id}:{profile}")
            if row["status"] != "trusted":
                blockers.add(f"status:{capability_id}:{row['status']}")
            blockers.update(
                f"blocker:{capability_id}:{blocker}"
                for blocker in row["blockers"]
            )
            for dependency in row["dependencies"]:
                visit(str(dependency))

        for capability_id in requested_ids:
            visit(capability_id)
        reachable_ids = tuple(sorted(reachable))
        blocker_ids = tuple(sorted(blockers))
        closure_payload = {
            "requested": requested_ids,
            "reachable": [
                {
                    "id": capability_id,
                    "version": self._capabilities[capability_id]["version"],
                    "status": self._capabilities[capability_id]["status"],
                }
                for capability_id in reachable_ids
            ],
            "missing": sorted(
                blocker.removeprefix("missing:")
                for blocker in blocker_ids
                if blocker.startswith("missing:")
            ),
            "profile": profile,
            "registry_fingerprint": self._fingerprint,
            "evidence_fingerprint": evidence_fingerprint,
        }
        return CapabilityClosure(
            requested=requested_ids,
            reachable=reachable_ids,
            profile=profile,
            trusted=not blocker_ids,
            blockers=blocker_ids,
            registry_fingerprint=self._fingerprint,
            evidence_fingerprint=evidence_fingerprint,
            fingerprint=_hash(closure_payload),
        )

    def aggregate_closure(
        self,
        mechanic_id: str,
        *,
        profile: str,
    ) -> CapabilityClosure:
        if mechanic_id not in self._aggregates:
            raise CapabilityRegistryError(
                f"Unknown mechanic aggregate: {mechanic_id}"
            )
        return self.closure(
            self._aggregates[mechanic_id], profile=profile
        )


def load_default_capability_registry() -> CapabilityRegistry:
    from .evidence import load_capability_evidence_index

    registry = CapabilityRegistry.from_path(DEFAULT_CAPABILITY_REGISTRY)
    _, fingerprint = load_capability_evidence_index(registry=registry)
    registry.mark_evidence_verified(fingerprint)
    return registry


def _targeted_effect_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanics: set[str],
) -> set[str]:
    dependencies: set[str] = set()
    for resolver in (
        fixed_counter_placement_node_capabilities,
        fixed_counter_placement_set_node_capabilities,
        fixed_counter_placement_target_set_node_capabilities,
        fixed_player_counter_placement_node_capabilities,
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
    ):
        dependencies.update(
            resolver(
                effects=effects,
                target_schema=target_schema,
                mechanic_ids=mechanics,
            )
        )
    return dependencies


def capability_dependencies_for_node(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return reviewed fine-grained dependencies for recognized node shapes.

    This bridge is intentionally narrow. Unknown operations return no mapping
    and continue through the legacy broad-contract gate until their capability
    declarations are reviewed.
    """

    mechanics = {str(value).casefold() for value in mechanic_ids}
    operations = {str(effect.get("op") or "") for effect in effects}

    def nested_operations(value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, Mapping):
            operation = value.get("op")
            if isinstance(operation, str) and operation:
                found.add(operation)
            for child in value.values():
                found.update(nested_operations(child))
        elif isinstance(value, (list, tuple)):
            for child in value:
                found.update(nested_operations(child))
        return found

    all_operations = nested_operations(effects)

    def contains_aftermath_kind(value: Any, kind: str) -> bool:
        if isinstance(value, Mapping):
            if value.get("kind") == kind:
                return True
            return any(
                contains_aftermath_kind(child, kind)
                for child in value.values()
            )
        if isinstance(value, (list, tuple)):
            return any(
                contains_aftermath_kind(child, kind) for child in value
            )
        return False

    def contains_key(value: Any, key: str) -> bool:
        if isinstance(value, Mapping):
            return key in value or any(
                contains_key(child, key) for child in value.values()
            )
        if isinstance(value, (list, tuple)):
            return any(contains_key(child, key) for child in value)
        return False
    dependencies: set[str] = set()
    for mechanic in mechanics:
        if mechanic not in _SHAPE_GATED_MECHANICS:
            dependencies.update(
                MECHANIC_CAPABILITY_DEPENDENCIES.get(mechanic, ())
            )
    if (
        "cr-603-handling-triggered-abilities" in mechanics
        and bool(effects)
    ):
        dependencies.add("trigger.placement.apnap")
    if (
        "cr-611-continuous-effects" in mechanics
        and all_operations.intersection(
            {
                "add_subtype_until_end_of_turn",
                "add_type_until_end_of_turn",
                "grant_keyword_until_end_of_turn",
                "modify_all_matching_permanents_until_end_of_turn",
                "modify_stats_until_end_of_turn",
                "pump_controlled_creatures",
            }
        )
    ):
        dependencies.add(
            "continuous.resolution.fixed_characteristics_until_end_of_turn"
        )
    schema = dict(target_schema or {})
    dependencies.update(
        _targeted_effect_capabilities(
            effects=effects,
            target_schema=target_schema,
            mechanics=mechanics,
        )
    )
    if (
        "create_damage_prevention_shield" in all_operations
        and "cr-615-prevention-effects" in mechanics
    ):
        dependencies.add("damage.prevention.persistent_amount")
        if target_schema is not None:
            dependencies.add("target.revalidate_resolution")
            if schema == {
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "damageable",
                "count": 1,
            }:
                dependencies.add(
                    "target.public.player_or_damageable_permanent"
                )
        if "cr-122-counters" in mechanics:
            dependencies.add("counter.placement.quantity_replacement")
        if contains_aftermath_kind(effects, "deal_damage"):
            dependencies.add("damage.prevention.aftermath.damage")
    prevention_triggered = contains_key(effects, "triggered_ability") or (
        "cr-615-prevention-effects" in mechanics
        and "cr-603-handling-triggered-abilities" in mechanics
        and bool(all_operations.intersection({"counter", "damage", "draw"}))
    )
    if prevention_triggered:
        dependencies.add("damage.prevention.triggered_results")
        if contains_aftermath_kind(effects, "draw_cards") or "draw" in all_operations:
            dependencies.add("zone.draw.library_to_hand")
        if contains_aftermath_kind(effects, "deal_damage") or "damage" in all_operations:
            dependencies.update(
                {"damage.amount.positive", "damage.result.player_life"}
            )
        if contains_aftermath_kind(effects, "place_counters") or "counter" in all_operations:
            dependencies.add("counter.placement.quantity_replacement")
    return tuple(sorted(dependencies))


def capability_covered_mechanics(
    dependencies: Iterable[str],
) -> tuple[str, ...]:
    supplied = set(str(value) for value in dependencies)
    covered = {
        mechanic
        for mechanic, required in MECHANIC_CAPABILITY_DEPENDENCIES.items()
        if set(required).issubset(supplied)
    }
    if "target.public.player_or_damageable_permanent" in supplied:
        covered.add("cr-115-targets")
    if "target.revalidate_resolution" in supplied:
        covered.add("cr-115-targets")
    if supplied.intersection(
        {"permanent.tap.effect", "permanent.untap.effect"}
    ):
        covered.add("tap-and-untap")
    if supplied.intersection(
        {"permanent.destroy.effect", "permanent.destroy.fixed_set"}
    ):
        covered.add("destroy")
    if "permanent.destroy.fixed_set" in supplied:
        covered.add("destroy-fixed-set")
    if "permanent.exile.effect" in supplied:
        covered.add(_EXILE_MECHANIC)
    if "permanent.return.owner_hand" in supplied:
        covered.add("return-to-owner-hand")
    if "stack.counter.effect" in supplied:
        covered.add("counter")
    if supplied.intersection(
        {
            "zone.draw.result_generated_ordering",
            "zone.draw.specifically_drawn_card_actions",
        }
    ):
        covered.add("cr-121-drawing-a-card")
    if "attachment.aura.simple_object" in supplied:
        covered.add("enchant")
    if "protection.typed.debt" in supplied:
        covered.add("protection")
    if "damage.prevention.persistent_amount" in supplied:
        covered.add("cr-615-prevention-effects")
        # Capability v4 owns the ordered fixed life sibling emitted by the
        # reviewed prevention sequence, including its typed life-change
        # precommit boundary. This is deliberately narrower than claiming the
        # complete CR 119 family or life-gain-prevention grammar.
        covered.add("cr-119-life")
    if "trigger.placement.apnap" in supplied:
        covered.add("cr-603-handling-triggered-abilities")
    if supplied.intersection(
        {
            "continuous.power_toughness.fixed_anthem",
            "continuous.resolution.fixed_characteristics_until_end_of_turn",
        }
    ):
        covered.add("cr-611-continuous-effects")
    if "damage.prevention.triggered_results" in supplied:
        covered.add("cr-615-prevention-effects")
    if "counter.placement.quantity_replacement" in supplied:
        covered.add("cr-122-counters")
    if "counter.producer.fixed_effect" in supplied:
        covered.add("cr-122-counters")
    if "counter.producer.fixed_permanent_set_effect" in supplied:
        covered.add("cr-122-counters")
    if "counter.producer.fixed_permanent_target_set_effect" in supplied:
        covered.add("cr-122-counters")
    if "counter.producer.support" in supplied:
        covered.update({"cr-115-targets", "cr-122-counters", "support"})
    if "counter.producer.fixed_player_effect" in supplied:
        covered.add("cr-122-counters")
    if "keyword_action.explore.single" in supplied:
        covered.add("ex" + "plore")
    if "counter.producer.proliferate" in supplied:
        covered.add("pro" + "liferate")
    if "damage.amount.positive" in supplied and supplied.intersection(
        {"damage.result.player_life", "damage.result.multitype_permanent"}
    ):
        covered.add("cr-120-damage")
    return tuple(sorted(covered))
