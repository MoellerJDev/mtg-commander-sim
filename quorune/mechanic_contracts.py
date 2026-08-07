from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


MECHANIC_CONTRACT_SCHEMA_VERSION = 1
CONTRACT_COVERAGE_STATUSES = {
    "planned",
    "partial",
    "implemented",
    "tested",
    "trusted",
}
CONTRACT_TRUST_LEVELS = {"untrusted", "provisional", "trusted"}


class MechanicContractError(ValueError):
    pass


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _nonempty_strings(
    value: Any,
    *,
    field: str,
    required: bool = True,
) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise MechanicContractError(
            f"{field} must be a list of nonempty strings"
        )
    if required and not value:
        raise MechanicContractError(f"{field} must not be empty")
    result = [str(item) for item in value]
    if len(result) != len(set(result)):
        raise MechanicContractError(f"{field} must contain unique values")
    return result


def validate_mechanic_contract(
    value: Mapping[str, Any],
    *,
    source_path: str | Path | None = None,
    expected_effective_date: str | None = None,
    expected_source_sha256: str | None = None,
    known_rule_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate one fail-closed mechanic contract.

    JSON Schema documents the transport shape, while this validator enforces
    the cross-field invariants that determine whether a contract may affect
    the trusted mechanics registry.
    """

    contract = json.loads(json.dumps(dict(value)))
    location = f" ({source_path})" if source_path else ""
    if int(contract.get("schema_version", 0)) != (
        MECHANIC_CONTRACT_SCHEMA_VERSION
    ):
        raise MechanicContractError(
            "Unsupported mechanic contract schema_version" + location
        )
    if int(contract.get("contract_version", 0)) < 1:
        raise MechanicContractError(
            "contract_version must be positive" + location
        )
    for field in ("mechanic_id", "official_name", "effective_date"):
        if not str(contract.get(field) or "").strip():
            raise MechanicContractError(
                f"{field} is required{location}"
            )
    source_hash = str(contract.get("source_sha256") or "")
    if len(source_hash) != 64 or any(
        character not in "0123456789abcdef" for character in source_hash
    ):
        raise MechanicContractError(
            "source_sha256 must be a lowercase SHA-256" + location
        )
    if (
        expected_effective_date
        and contract["effective_date"] != expected_effective_date
    ):
        raise MechanicContractError(
            f"effective_date does not match the pinned CR snapshot{location}"
        )
    if (
        expected_source_sha256
        and source_hash != expected_source_sha256
    ):
        raise MechanicContractError(
            f"source_sha256 does not match the pinned CR snapshot{location}"
        )
    rule_references = _nonempty_strings(
        contract.get("rule_references"),
        field="rule_references",
    )
    glossary_references = _nonempty_strings(
        contract.get("glossary_references", []),
        field="glossary_references",
        required=False,
    )
    _nonempty_strings(
        contract.get("dependencies", []),
        field="dependencies",
        required=False,
    )
    known = set(known_rule_ids or ())
    if known:
        unknown = sorted(set(rule_references) - known)
        if unknown:
            raise MechanicContractError(
                "Unknown rule reference(s): "
                + ", ".join(unknown)
                + location
            )
    if len(set(glossary_references)) != len(glossary_references):
        raise MechanicContractError(
            "glossary_references must be unique" + location
        )

    coverage_status = str(contract.get("coverage_status") or "")
    trust_level = str(contract.get("trust_level") or "")
    if coverage_status not in CONTRACT_COVERAGE_STATUSES:
        raise MechanicContractError(
            f"Unknown coverage_status {coverage_status!r}{location}"
        )
    if trust_level not in CONTRACT_TRUST_LEVELS:
        raise MechanicContractError(
            f"Unknown trust_level {trust_level!r}{location}"
        )

    behavior = contract.get("behavior")
    if not isinstance(behavior, Mapping):
        raise MechanicContractError(
            "behavior must be an object" + location
        )
    for field in (
        "zones",
        "objects",
        "events",
        "state_reads",
        "state_writes",
        "costs",
        "timing",
        "targets",
        "choices",
        "hidden_information",
        "apnap",
        "layers",
        "replacement_effects",
        "copy",
        "control_change",
        "zone_change",
        "source_leaves",
    ):
        if field not in behavior:
            raise MechanicContractError(
                f"behavior.{field} is required{location}"
            )
        _nonempty_strings(
            behavior[field],
            field=f"behavior.{field}",
            required=False,
        )

    _nonempty_strings(
        contract.get("variants", []),
        field="variants",
        required=False,
    )
    blockers = _nonempty_strings(
        contract.get("known_blockers", []),
        field="known_blockers",
        required=False,
    )
    test_ids = _nonempty_strings(
        contract.get("test_ids", []),
        field="test_ids",
        required=False,
    )
    witnesses = contract.get("witness_cards", [])
    if not isinstance(witnesses, list):
        raise MechanicContractError(
            "witness_cards must be a list" + location
        )
    for witness in witnesses:
        if (
            not isinstance(witness, Mapping)
            or not str(witness.get("name") or "").strip()
            or re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                r"[0-9a-f]{4}-[0-9a-f]{12}",
                str(witness.get("oracle_id") or ""),
            )
            is None
        ):
            raise MechanicContractError(
                "Each witness card needs name and oracle_id" + location
            )
    _nonempty_strings(
        contract.get("rulings", []),
        field="rulings",
        required=False,
    )
    implementation = contract.get("implementation")
    if not isinstance(implementation, Mapping):
        raise MechanicContractError(
            "implementation must be an object" + location
        )
    for field in ("component", "version"):
        if not str(implementation.get(field) or "").strip():
            raise MechanicContractError(
                f"implementation.{field} is required{location}"
            )
    if coverage_status in {"tested", "trusted"} and not test_ids:
        raise MechanicContractError(
            f"{coverage_status} contracts require test_ids{location}"
        )
    if str(contract.get("review_status") or "") not in {
        "draft",
        "reviewed",
    }:
        raise MechanicContractError(
            "review_status must be draft or reviewed" + location
        )
    if trust_level == "trusted":
        if coverage_status != "trusted":
            raise MechanicContractError(
                "Trusted contracts require coverage_status=trusted"
                + location
            )
        if blockers:
            raise MechanicContractError(
                "Trusted contracts cannot have known blockers" + location
            )
        if str(contract.get("review_status") or "") != "reviewed":
            raise MechanicContractError(
                "Trusted contracts require review_status=reviewed"
                + location
            )
        if not witnesses:
            raise MechanicContractError(
                "Trusted contracts require witness_cards" + location
            )
    return contract


def load_mechanic_contracts(
    root: str | Path,
    *,
    expected_effective_date: str | None = None,
    expected_source_sha256: str | None = None,
    known_rule_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    directory = Path(root) / "mechanics" / "contracts"
    contracts: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not directory.exists():
        return contracts
    for path in sorted(directory.glob("*.json")):
        contract = validate_mechanic_contract(
            json.loads(path.read_text(encoding="utf-8")),
            source_path=path,
            expected_effective_date=expected_effective_date,
            expected_source_sha256=expected_source_sha256,
            known_rule_ids=known_rule_ids,
        )
        mechanic_id = str(contract["mechanic_id"])
        if mechanic_id in seen:
            raise MechanicContractError(
                f"Duplicate mechanic contract: {mechanic_id}"
            )
        seen.add(mechanic_id)
        contract["_contract_path"] = path.relative_to(
            Path(root)
        ).as_posix()
        contract["_contract_sha256"] = _json_hash(
            {
                key: value
                for key, value in contract.items()
                if not key.startswith("_")
            }
        )
        contracts.append(contract)
    return contracts


def apply_contracts_to_registry(
    registry: Mapping[str, Any],
    contracts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    result = json.loads(json.dumps(dict(registry)))
    mechanics = {
        str(row["mechanic_id"]): row
        for row in result.get("mechanics", [])
    }
    applied: list[dict[str, Any]] = []
    for raw_contract in contracts:
        contract = dict(raw_contract)
        mechanic_id = str(contract["mechanic_id"])
        if mechanic_id not in mechanics:
            raise MechanicContractError(
                f"Contract mechanic is absent from CR inventory: {mechanic_id}"
            )
        mechanic = mechanics[mechanic_id]
        mechanic.update(
            {
                "coverage_status": contract["coverage_status"],
                "contract_path": contract["_contract_path"],
                "contract_sha256": contract["_contract_sha256"],
                "contract_version": contract["contract_version"],
                "implementation_component": contract["implementation"][
                    "component"
                ],
                "implementation_version": contract["implementation"][
                    "version"
                ],
                "test_ids": list(contract["test_ids"]),
                "trust_level": contract["trust_level"],
                "known_blockers": list(contract["known_blockers"]),
            }
        )
        applied.append(
            {
                "mechanic_id": mechanic_id,
                "path": contract["_contract_path"],
                "sha256": contract["_contract_sha256"],
                "version": contract["contract_version"],
            }
        )
    result["contracts"] = applied
    result["contract_count"] = len(applied)
    result["trusted_mechanic_count"] = sum(
        row.get("trust_level") == "trusted"
        for row in result.get("mechanics", [])
    )
    if applied:
        result["generation_status"] = "cr_index_with_contracts"
    return result
