from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .generation import (
    DEFAULT_BASELINE_PATH,
    DEFAULT_CARD_INDEX_PATH,
    DEFAULT_COMPLEX_CARDS_PATH,
    DEFAULT_DELTA_PATH,
    DEFAULT_INTERACTIONS_PATH,
    DEFAULT_MATRIX_PATH,
    REUSABLE_PIECE_ALGORITHM_VERSION,
    REUSABLE_PIECE_SCHEMA_VERSION,
    _PIECE_ID,
    _SYSTEM_STATES,
    _validate_fingerprint,
    load_json,
    load_reusable_piece_policy,
    validate_program_baseline,
    validate_reusable_piece_policy,
)


def _require_fields(
    value: Mapping[str, Any], expected: set[str], *, label: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are invalid")


def validate_reusable_piece_matrix(
    value: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> None:
    validate_reusable_piece_policy(policy)
    _require_fields(
        value,
        {
            "schema_version",
            "algorithm_version",
            "ontology_version",
            "profile",
            "commander_legal_only",
            "classification_boundary",
            "ruling_evidence_boundary",
            "snapshot",
            "input_fingerprints",
            "classes",
            "relation_types",
            "status_axes",
            "summary",
            "universal_systems",
            "rule_index",
            "pieces",
            "complete_snapshot_claimed",
            "fingerprint",
        },
        label="Reusable-piece matrix",
    )
    if value.get("schema_version") != REUSABLE_PIECE_SCHEMA_VERSION:
        raise ValueError("Unsupported reusable-piece matrix schema_version")
    if value.get("algorithm_version") != REUSABLE_PIECE_ALGORITHM_VERSION:
        raise ValueError("Unsupported reusable-piece matrix algorithm_version")
    if value.get("ontology_version") != policy["ontology_version"]:
        raise ValueError("Reusable-piece ontology version is stale")
    if value.get("profile") != policy["profile"]:
        raise ValueError("Reusable-piece matrix profile is invalid")
    if value.get("complete_snapshot_claimed") is not False:
        raise ValueError("Reusable-piece matrix cannot claim snapshot completion")
    if value.get("classes") != policy["classes"]:
        raise ValueError("Reusable-piece matrix classes are stale")
    if value.get("relation_types") != policy["relation_types"]:
        raise ValueError("Reusable-piece matrix relation types are stale")
    if value.get("status_axes") != policy["status_axes"]:
        raise ValueError("Reusable-piece matrix status axes are stale")
    pieces = value.get("pieces")
    if not isinstance(pieces, list) or not pieces:
        raise ValueError("Reusable-piece matrix has no pieces")
    piece_ids: list[str] = []
    class_ids = {str(row["id"]) for row in policy["classes"]}
    for row in pieces:
        if not isinstance(row, Mapping):
            raise ValueError("Reusable-piece rows must be mappings")
        _require_fields(
            row,
            {
                "piece_id",
                "class_id",
                "label",
                "source_kinds",
                "source_ids",
                "rule_ids",
                "implementation_components",
                "test_ids",
                "interaction_test_ids",
                "blockers",
                "status",
                "relation_counts",
                "counts",
                "frontier",
                "fingerprint",
            },
            label="Reusable-piece row",
        )
        piece_id = row.get("piece_id")
        if not isinstance(piece_id, str) or not _PIECE_ID.fullmatch(piece_id):
            raise ValueError("Reusable-piece row has an invalid piece_id")
        piece_ids.append(piece_id)
        if row.get("class_id") not in class_ids:
            raise ValueError(f"Reusable piece {piece_id} has an unknown class")
        status = row.get("status")
        if not isinstance(status, Mapping) or set(status) != set(
            policy["status_axes"]
        ):
            raise ValueError(f"Reusable piece {piece_id} has invalid statuses")
        for axis, state in status.items():
            if state not in policy["status_axes"][axis]:
                raise ValueError(
                    f"Reusable piece {piece_id} has invalid {axis} status"
                )
        if row.get("source_kinds") != sorted(set(row.get("source_kinds", ()))):
            raise ValueError(f"Reusable piece {piece_id} sources are not canonical")
        relation_counts = row.get("relation_counts")
        if not isinstance(relation_counts, Mapping) or not set(
            relation_counts
        ) <= set(policy["relation_types"]):
            raise ValueError(
                f"Reusable piece {piece_id} has invalid relation counts"
            )
        _validate_fingerprint(row, label=f"Reusable piece {piece_id}")
    if piece_ids != sorted(piece_ids) or len(piece_ids) != len(set(piece_ids)):
        raise ValueError("Reusable-piece IDs must be sorted and unique")
    summary = value.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("Reusable-piece matrix summary is missing")
    if summary.get("piece_count") != len(pieces):
        raise ValueError("Reusable-piece summary count is stale")
    if summary.get("unclassified_material_spans") != 0:
        raise ValueError("Reusable-piece matrix has unclassified material spans")
    systems = value.get("universal_systems")
    if not isinstance(systems, Mapping) or set(systems) != set(
        policy["universal_system_classes"]
    ):
        raise ValueError("Reusable-piece universal-system inventory is invalid")
    if any(row.get("status") not in _SYSTEM_STATES for row in systems.values()):
        raise ValueError("Reusable-piece universal-system status is invalid")
    _validate_fingerprint(value, label="Reusable-piece matrix")


def validate_reusable_piece_card_index(
    value: Mapping[str, Any],
    *,
    matrix: Mapping[str, Any],
) -> None:
    _require_fields(
        value,
        {
            "schema_version",
            "algorithm_version",
            "profile",
            "matrix_fingerprint",
            "cards_considered",
            "unclassified_material_spans",
            "cards",
            "fingerprint",
        },
        label="Reusable-piece card index",
    )
    if value.get("schema_version") != REUSABLE_PIECE_SCHEMA_VERSION:
        raise ValueError("Unsupported reusable-piece card-index schema")
    if value.get("matrix_fingerprint") != matrix.get("fingerprint"):
        raise ValueError("Reusable-piece card index targets a stale matrix")
    if value.get("unclassified_material_spans") != 0:
        raise ValueError("Reusable-piece card index has unclassified spans")
    cards = value.get("cards")
    if not isinstance(cards, list) or len(cards) != value.get(
        "cards_considered"
    ):
        raise ValueError("Reusable-piece card index accounting is invalid")
    known = {str(row["piece_id"]) for row in matrix["pieces"]}
    oracle_ids = []
    for card in cards:
        if not isinstance(card, Mapping):
            raise ValueError("Reusable-piece card rows must be mappings")
        _require_fields(
            card,
            {
                "oracle_id",
                "card_name",
                "oracle_ir_status",
                "card_program_status",
                "card_program_trust_basis",
                "material_ability_count",
                "exact_ability_count",
                "minimum_blocker_piece_ids",
                "pieces",
            },
            label="Reusable-piece card row",
        )
        oracle_ids.append(card.get("oracle_id"))
        relations = card.get("pieces")
        if not isinstance(relations, list):
            raise ValueError("Reusable-piece card relations must be a list")
        if any(
            not isinstance(row, Mapping)
            or set(row) != {"piece_id", "relation_types", "ability_ids"}
            for row in relations
        ):
            raise ValueError("Reusable-piece card relation fields are invalid")
        related_ids = [row.get("piece_id") for row in relations]
        if (
            related_ids != sorted(related_ids)
            or len(related_ids) != len(set(related_ids))
            or not set(related_ids) <= known
        ):
            raise ValueError("Reusable-piece card relations are invalid")
        if int(card.get("material_ability_count") or 0) and not relations:
            raise ValueError("A material card has no reusable-piece relation")
        blockers = card.get("minimum_blocker_piece_ids")
        if blockers != sorted(set(blockers or ())) or not set(blockers) <= known:
            raise ValueError("Reusable-piece card blockers are invalid")
    if len(oracle_ids) != len(set(oracle_ids)):
        raise ValueError("Reusable-piece card index has duplicate Oracle IDs")
    _validate_fingerprint(value, label="Reusable-piece card index")


def validate_reusable_piece_interactions(
    value: Mapping[str, Any],
    *,
    matrix: Mapping[str, Any],
) -> None:
    _require_fields(
        value,
        {
            "schema_version",
            "algorithm_version",
            "profile",
            "matrix_fingerprint",
            "summary",
            "pairs",
            "complete_snapshot_claimed",
            "fingerprint",
        },
        label="Reusable-piece interactions",
    )
    if value.get("schema_version") != REUSABLE_PIECE_SCHEMA_VERSION:
        raise ValueError("Unsupported reusable-piece interaction schema")
    if value.get("matrix_fingerprint") != matrix.get("fingerprint"):
        raise ValueError("Reusable-piece interactions target a stale matrix")
    if value.get("complete_snapshot_claimed") is not False:
        raise ValueError("Reusable-piece interactions cannot claim completion")
    known = {str(row["piece_id"]) for row in matrix["pieces"]}
    pairs = value.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("Reusable-piece interaction pairs are missing")
    identities = []
    for row in pairs:
        if not isinstance(row, Mapping):
            raise ValueError("Reusable-piece interaction rows must be mappings")
        _require_fields(
            row,
            {
                "piece_ids",
                "class_ids",
                "card_count",
                "ability_count",
                "covered",
                "high_risk",
                "evidence_test_ids",
                "evidence_basis",
            },
            label="Reusable-piece interaction row",
        )
        piece_ids = row.get("piece_ids")
        if row.get("evidence_basis") != "explicit_interaction_declaration_v1":
            raise ValueError(
                "Reusable-piece interaction evidence basis is unsupported"
            )
        if (
            not isinstance(piece_ids, list)
            or len(piece_ids) != 2
            or piece_ids != sorted(piece_ids)
            or len(set(piece_ids)) != 2
            or not set(piece_ids) <= known
        ):
            raise ValueError("Reusable-piece interaction pair is invalid")
        identities.append(tuple(piece_ids))
        if bool(row.get("covered")) != bool(row.get("evidence_test_ids")):
            raise ValueError("Reusable-piece interaction evidence is invalid")
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValueError("Reusable-piece interaction pairs are not canonical")
    summary = value.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("Reusable-piece interaction summary is missing")
    if summary.get("applicable_piece_pairs") != len(pairs):
        raise ValueError("Reusable-piece interaction count is stale")
    _validate_fingerprint(value, label="Reusable-piece interactions")


def validate_complex_card_benchmark(
    value: Mapping[str, Any],
    *,
    matrix: Mapping[str, Any],
) -> None:
    _require_fields(
        value,
        {
            "schema_version",
            "algorithm_version",
            "profile",
            "matrix_fingerprint",
            "ranking_weights",
            "cards_considered",
            "benchmark_size",
            "cards",
            "content_boundary",
            "fingerprint",
        },
        label="Complex-card benchmark",
    )
    if value.get("schema_version") != REUSABLE_PIECE_SCHEMA_VERSION:
        raise ValueError("Unsupported complex-card benchmark schema")
    if value.get("matrix_fingerprint") != matrix.get("fingerprint"):
        raise ValueError("Complex-card benchmark targets a stale matrix")
    cards = value.get("cards")
    if not isinstance(cards, list) or len(cards) != value.get("benchmark_size"):
        raise ValueError("Complex-card benchmark accounting is invalid")
    for row in cards:
        if not isinstance(row, Mapping):
            raise ValueError("Complex-card rows must be mappings")
        _require_fields(
            row,
            {
                "oracle_id",
                "card_name",
                "score",
                "piece_count",
                "universal_system_count",
                "material_ability_count",
                "minimum_blocker_count",
                "official_ruling_count",
                "flags",
                "piece_ids",
                "universal_system_ids",
                "composition_status",
                "sentinel",
            },
            label="Complex-card row",
        )
    non_sentinel_scores = [
        int(row["score"]) for row in cards if not row.get("sentinel")
    ]
    if non_sentinel_scores != sorted(non_sentinel_scores, reverse=True):
        raise ValueError("Complex-card benchmark rank is not canonical")
    if len({row.get("oracle_id") for row in cards}) != len(cards):
        raise ValueError("Complex-card benchmark has duplicate cards")
    _validate_fingerprint(value, label="Complex-card benchmark")


def validate_reusable_piece_delta(value: Mapping[str, Any]) -> None:
    _require_fields(
        value,
        {
            "schema_version",
            "algorithm_version",
            "baseline_id",
            "baseline_fingerprint",
            "current_matrix_fingerprint",
            "metrics",
            "deltas",
            "architecture_deltas",
            "piece_changes",
            "interaction_coverage",
            "fingerprint",
        },
        label="Reusable-piece delta",
    )
    if value.get("schema_version") != REUSABLE_PIECE_SCHEMA_VERSION:
        raise ValueError("Unsupported reusable-piece delta schema")
    _validate_fingerprint(value, label="Reusable-piece delta")


def validate_reusable_piece_artifacts(
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    policy: Mapping[str, Any],
) -> None:
    required = {
        "matrix",
        "card_index",
        "interactions",
        "complex_cards",
        "baseline",
        "delta",
    }
    if set(artifacts) != required:
        raise ValueError("Reusable-piece artifact bundle is incomplete")
    matrix = artifacts["matrix"]
    validate_reusable_piece_matrix(matrix, policy=policy)
    validate_reusable_piece_card_index(
        artifacts["card_index"], matrix=matrix
    )
    validate_reusable_piece_interactions(
        artifacts["interactions"], matrix=matrix
    )
    validate_complex_card_benchmark(
        artifacts["complex_cards"], matrix=matrix
    )
    validate_program_baseline(artifacts["baseline"])
    validate_reusable_piece_delta(artifacts["delta"])


def render_reusable_piece_matrix_markdown(
    matrix: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> str:
    validate_reusable_piece_matrix(matrix, policy=policy)
    summary = matrix["summary"]
    lines = [
        "---",
        'title: "Reusable rules piece matrix"',
        'status: "generated"',
        'authoritative_source: "coverage/reusable-piece-matrix.json.gz"',
        f'verified: "{matrix["fingerprint"]}"',
        'audience: "compiler and rules contributors"',
        'maintenance: "generated"',
        "---",
        "",
        "# Reusable rules piece matrix",
        "",
        matrix["classification_boundary"],
        "",
        matrix["ruling_evidence_boundary"],
        "",
        "## Snapshot",
        "",
        f"- Profile: `{matrix['profile']}`",
        f"- Ontology: `{matrix['ontology_version']}`",
        f"- Pieces: {summary['piece_count']:,}",
        f"- Cards indexed: {summary['cards_indexed']:,}",
        f"- Material abilities classified: {summary['material_abilities_classified']:,}",
        f"- Unclassified material spans: {summary['unclassified_material_spans']:,}",
        f"- Mapped pinned rules: {summary['mapped_rule_count']:,} / {summary['rule_count']:,}",
        f"- Applicable piece pairs: {summary['applicable_interaction_pairs']:,}",
        f"- Covered piece pairs: {summary['covered_interaction_pairs']:,}",
        "",
        "## Ontology classes",
        "",
        "| Class | Pieces |",
        "|---|---:|",
    ]
    labels = {row["id"]: row["label"] for row in policy["classes"]}
    for class_id, count in sorted(summary["class_counts"].items()):
        lines.append(f"| `{class_id}` — {labels[class_id]} | {count:,} |")
    lines.extend(
        [
            "",
            "## Universal systems",
            "",
            "| System | Status | Pieces | Blocking pieces |",
            "|---|---|---:|---:|",
        ]
    )
    for system_id, row in matrix["universal_systems"].items():
        lines.append(
            f"| `{system_id}` | `{row['status']}` | "
            f"{row['piece_count']:,} | {row.get('blocking_piece_count', 0):,} |"
        )
    lines.extend(
        [
            "",
            "## Highest current blocker leverage",
            "",
            "| Piece | Class | Residuals | Sole blockers | Expected cards | Runtime | Assurance |",
            "|---|---|---:|---:|---:|---|---|",
        ]
    )
    ranked = sorted(
        matrix["pieces"],
        key=lambda row: (
            -int(row["frontier"]["sole_blocker_cards"]),
            -int(row["frontier"]["material_occurrences"]),
            row["piece_id"],
        ),
    )
    for row in ranked[:30]:
        lines.append(
            f"| `{row['piece_id']}` | `{row['class_id']}` | "
            f"{row['frontier']['material_occurrences']:,} | "
            f"{row['frontier']['sole_blocker_cards']:,} | "
            f"{row['frontier']['expected_exact_card_gain']:,} | "
            f"`{row['status']['runtime']}` | `{row['status']['assurance']}` |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Inventory and classification are not implementation or trust. "
            "Universal systems remain conservatively below snapshot-complete "
            "until all required rules, pieces, rulings, and interactions close.",
            "",
        ]
    )
    return "\n".join(lines)


def render_reusable_piece_delta_markdown(
    delta: Mapping[str, Any],
) -> str:
    validate_reusable_piece_delta(delta)
    lines = [
        "---",
        'title: "Reusable rules piece delta"',
        'status: "generated"',
        'authoritative_source: "coverage/reusable-piece-delta.json"',
        f'verified: "{delta["fingerprint"]}"',
        'audience: "compiler and rules contributors"',
        'maintenance: "generated"',
        "---",
        "",
        "# Reusable rules piece delta",
        "",
        f"Compared with durable baseline `{delta['baseline_id']}`.",
        "",
        "| Metric | Current | Delta |",
        "|---|---:|---:|",
    ]
    for key, current in sorted(delta["metrics"].items()):
        lines.append(f"| `{key}` | {current:,} | {delta['deltas'][key]:+,} |")
    changes = delta["piece_changes"]
    lines.extend(
        [
            "",
            "## Piece status movement",
            "",
            f"- Added: {len(changes['added']):,}",
            f"- Removed: {len(changes['removed']):,}",
            f"- Promoted axes: {len(changes['promoted']):,}",
            f"- Demoted axes: {len(changes['demoted']):,}",
            "",
        ]
    )
    return "\n".join(lines)


def render_complex_card_benchmark_markdown(
    benchmark: Mapping[str, Any],
    *,
    matrix: Mapping[str, Any],
) -> str:
    validate_complex_card_benchmark(benchmark, matrix=matrix)
    lines = [
        "---",
        'title: "Complex card composition benchmark"',
        'status: "generated"',
        'authoritative_source: "coverage/complex-card-composition.json"',
        f'verified: "{benchmark["fingerprint"]}"',
        'audience: "compiler and rules contributors"',
        'maintenance: "generated"',
        "---",
        "",
        "# Complex card composition benchmark",
        "",
        benchmark["content_boundary"],
        "",
        "| Card | Score | Pieces | Systems | Abilities | Blockers | Rulings | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in benchmark["cards"]:
        lines.append(
            f"| {row['card_name']} | {row['score']:,} | "
            f"{row['piece_count']:,} | {row['universal_system_count']:,} | "
            f"{row['material_ability_count']:,} | "
            f"{row['minimum_blocker_count']:,} | "
            f"{row['official_ruling_count']:,} | "
            f"`{row['composition_status']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def load_tracked_reusable_piece_artifacts(
    root: str | Path = ".",
) -> dict[str, dict[str, Any]]:
    base = Path(root)
    artifacts = {
        "matrix": load_json(base / DEFAULT_MATRIX_PATH),
        "card_index": load_json(base / DEFAULT_CARD_INDEX_PATH),
        "interactions": load_json(base / DEFAULT_INTERACTIONS_PATH),
        "complex_cards": load_json(base / DEFAULT_COMPLEX_CARDS_PATH),
        "baseline": load_json(base / DEFAULT_BASELINE_PATH),
        "delta": load_json(base / DEFAULT_DELTA_PATH),
    }
    policy = load_reusable_piece_policy(base)
    validate_reusable_piece_artifacts(artifacts, policy=policy)
    return artifacts


def diff_reusable_piece_matrices(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    validate_reusable_piece_matrix(before, policy=policy)
    validate_reusable_piece_matrix(after, policy=policy)
    before_rows = {str(row["piece_id"]): row for row in before["pieces"]}
    after_rows = {str(row["piece_id"]): row for row in after["pieces"]}
    changed = []
    for piece_id in sorted(set(before_rows) & set(after_rows)):
        before_row = before_rows[piece_id]
        after_row = after_rows[piece_id]
        status_changes = {
            axis: {
                "before": before_row["status"][axis],
                "after": after_row["status"][axis],
            }
            for axis in policy["status_axes"]
            if before_row["status"][axis] != after_row["status"][axis]
        }
        count_changes = {
            key: int(after_row["counts"].get(key, 0))
            - int(before_row["counts"].get(key, 0))
            for key in set(before_row["counts"]) | set(after_row["counts"])
            if int(after_row["counts"].get(key, 0))
            != int(before_row["counts"].get(key, 0))
        }
        if status_changes or count_changes:
            changed.append(
                {
                    "piece_id": piece_id,
                    "status_changes": status_changes,
                    "count_deltas": dict(sorted(count_changes.items())),
                }
            )
    return {
        "schema_version": REUSABLE_PIECE_SCHEMA_VERSION,
        "before_fingerprint": before["fingerprint"],
        "after_fingerprint": after["fingerprint"],
        "added_piece_ids": sorted(set(after_rows) - set(before_rows)),
        "removed_piece_ids": sorted(set(before_rows) - set(after_rows)),
        "changed_pieces": changed,
    }


def _resolve_matrix_snapshot(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / DEFAULT_MATRIX_PATH
    return load_json(candidate)


def _find_piece(
    matrix: Mapping[str, Any], piece_id: str
) -> Mapping[str, Any]:
    for row in matrix["pieces"]:
        if row["piece_id"] == piece_id:
            return row
    raise KeyError(f"Unknown reusable piece: {piece_id}")


def card_piece_relations(
    card_index: Mapping[str, Any], card: str
) -> Mapping[str, Any]:
    needle = " ".join(card.split()).casefold()
    exact = [
        row
        for row in card_index["cards"]
        if str(row["card_name"]).casefold() == needle
        or str(row["oracle_id"]).casefold() == needle
    ]
    if not exact:
        exact = [
            row
            for row in card_index["cards"]
            if str(row["oracle_id"]).casefold().startswith(needle)
        ]
    if len(exact) != 1:
        if not exact:
            raise KeyError(f"Card not found in reusable-piece index: {card}")
        raise KeyError(f"Ambiguous card in reusable-piece index: {card}")
    return exact[0]


def _cards_for_piece(
    matrix: Mapping[str, Any],
    card_index: Mapping[str, Any],
    piece_id: str,
    limit: int,
) -> dict[str, Any]:
    _find_piece(matrix, piece_id)
    rows = [
        {
            "oracle_id": row["oracle_id"],
            "card_name": row["card_name"],
            "card_program_status": row["card_program_status"],
            "minimum_blocker_piece_ids": row["minimum_blocker_piece_ids"],
            "relation": next(
                relation
                for relation in row["pieces"]
                if relation["piece_id"] == piece_id
            ),
        }
        for row in card_index["cards"]
        if any(
            relation["piece_id"] == piece_id for relation in row["pieces"]
        )
    ]
    return {
        "piece_id": piece_id,
        "card_count": len(rows),
        "cards": rows[: max(0, int(limit))],
    }


def _blockers_for_piece(
    matrix: Mapping[str, Any],
    card_index: Mapping[str, Any],
    piece_id: str,
    limit: int,
) -> dict[str, Any]:
    piece = _find_piece(matrix, piece_id)
    cards = [
        {
            "oracle_id": row["oracle_id"],
            "card_name": row["card_name"],
            "minimum_blocker_piece_ids": row["minimum_blocker_piece_ids"],
        }
        for row in card_index["cards"]
        if piece_id in row["minimum_blocker_piece_ids"]
    ]
    cards.sort(
        key=lambda row: (
            len(row["minimum_blocker_piece_ids"]),
            row["card_name"],
            row["oracle_id"],
        )
    )
    return {
        "piece_id": piece_id,
        "frontier": piece["frontier"],
        "blockers": piece["blockers"],
        "cards": cards[: max(0, int(limit))],
    }


def _interactions_for_piece(
    matrix: Mapping[str, Any],
    interactions: Mapping[str, Any],
    piece_id: str,
    limit: int,
) -> dict[str, Any]:
    _find_piece(matrix, piece_id)
    rows = [
        row for row in interactions["pairs"] if piece_id in row["piece_ids"]
    ]
    rows.sort(
        key=lambda row: (
            not row["high_risk"],
            not row["covered"],
            -int(row["card_count"]),
            row["piece_ids"],
        )
    )
    return {
        "piece_id": piece_id,
        "summary": interactions["summary"],
        "interactions": rows[: max(0, int(limit))],
    }


def _next_pieces(
    matrix: Mapping[str, Any], limit: int
) -> dict[str, Any]:
    ranked = sorted(
        matrix["pieces"],
        key=lambda row: (
            -int(row["frontier"]["sole_blocker_cards"]),
            -int(row["frontier"]["expected_exact_card_gain"]),
            -int(row["frontier"]["material_occurrences"]),
            row["piece_id"],
        ),
    )
    return {
        "profile": matrix["profile"],
        "pieces": [
            {
                "piece_id": row["piece_id"],
                "class_id": row["class_id"],
                "status": row["status"],
                "frontier": {
                    key: value
                    for key, value in row["frontier"].items()
                    if key != "family_ids"
                }
                | {"family_count": len(row["frontier"]["family_ids"])},
                "blockers": row["blockers"],
            }
            for row in ranked[: max(0, int(limit))]
        ],
    }


def execute_reusable_piece_operation(
    operation: str,
    *,
    root: str | Path = ".",
    piece_id: str | None = None,
    card: str | None = None,
    against: str | Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    artifacts = load_tracked_reusable_piece_artifacts(root)
    matrix = artifacts["matrix"]
    card_index = artifacts["card_index"]
    interactions = artifacts["interactions"]
    if operation == "inventory":
        return {
            "schema_version": matrix["schema_version"],
            "ontology_version": matrix["ontology_version"],
            "profile": matrix["profile"],
            "snapshot": matrix["snapshot"],
            "classes": matrix["classes"],
            "summary": matrix["summary"],
            "universal_systems": matrix["universal_systems"],
            "fingerprint": matrix["fingerprint"],
        }
    if operation == "coverage":
        return {
            "schema_version": matrix["schema_version"],
            "summary": matrix["summary"],
            "status_axes": matrix["status_axes"],
            "interaction_summary": interactions["summary"],
            "baseline": artifacts["baseline"],
            "delta": artifacts["delta"],
        }
    if operation == "show":
        if not piece_id:
            raise ValueError("pieces show requires a piece ID")
        return dict(_find_piece(matrix, piece_id))
    if operation == "cards":
        if not piece_id:
            raise ValueError("pieces cards requires a piece ID")
        return _cards_for_piece(matrix, card_index, piece_id, limit)
    if operation == "blockers":
        if not piece_id:
            raise ValueError("pieces blockers requires a piece ID")
        return _blockers_for_piece(matrix, card_index, piece_id, limit)
    if operation == "interactions":
        if not piece_id:
            raise ValueError("pieces interactions requires a piece ID")
        return _interactions_for_piece(matrix, interactions, piece_id, limit)
    if operation == "diff":
        if against is None:
            return dict(artifacts["delta"])
        policy = load_reusable_piece_policy(root)
        before = _resolve_matrix_snapshot(against)
        return diff_reusable_piece_matrices(before, matrix, policy=policy)
    if operation == "next":
        return _next_pieces(matrix, limit)
    if operation == "card":
        if not card:
            raise ValueError("card pieces requires a card name or Oracle ID")
        return dict(card_piece_relations(card_index, card))
    raise ValueError(f"Unknown reusable-piece operation: {operation}")
