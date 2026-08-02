from __future__ import annotations

from typing import Any, Mapping

from .commander import COMMANDER_DAMAGE_IDENTITY_VERSION


def commander_damage_identity_version(value: int | None) -> int:
    """Return the explicit replay provenance version for a checkpoint."""

    return 1 if value is None else value


def validate_commander_damage_identity_provenance(
    manifest: Mapping[str, Any],
    state_version: int | None,
) -> None:
    """Bind an additive Game Record v3 marker to checkpoint semantics."""

    format_value = manifest.get("format")
    if not isinstance(format_value, Mapping):
        raise ValueError("Record format provenance is malformed")
    declared = format_value.get("commander_damage_identity_version", 1)
    if type(declared) is not int or declared not in {
        1,
        COMMANDER_DAMAGE_IDENTITY_VERSION,
    }:
        raise ValueError("Unsupported commander damage identity provenance")
    if declared != commander_damage_identity_version(state_version):
        raise ValueError(
            "Commander damage identity provenance does not match the "
            "initial checkpoint"
        )
