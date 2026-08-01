from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import tokenize
import tomllib
import unittest
from typing import Any, Iterable, Mapping

try:
    from scripts.architecture_support import (
        build_card_name_hash_index,
        decode_card_name_hash_index,
        printed_name_digest,
    )
except ModuleNotFoundError:  # Direct `python scripts/...` execution.
    from architecture_support import (
        build_card_name_hash_index,
        decode_card_name_hash_index,
        printed_name_digest,
    )


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "platform" / "architecture-audit-source.json"
CARD_BASELINE = ROOT / "platform" / "card-specificity-baseline.json"
CARD_NAME_INDEX = ROOT / "platform" / "card-name-hash-index.json"
JSON_OUTPUT = ROOT / "coverage" / "architecture-audit.json"
ARCHITECTURE_STATUS = ROOT / "docs" / "ARCHITECTURE_DEBT_STATUS.md"
COMPILER_STATUS = ROOT / "docs" / "COMPILER_COVERAGE_STATUS.md"
GUARD_BASELINE = ROOT / "platform" / "architecture-guard-baseline.json"
CAPABILITY_REGISTRY = (
    ROOT / "mtg_commander_sim" / "rules" / "capability-registry.json"
)
CARD_PROGRAM_SCHEMA = ROOT / "schemas" / "card-program-v2.schema.json"

PYTHON_SUFFIXES = {".py"}
WEB_SUFFIXES = {".ts", ".tsx", ".css"}
MUTATING_METHODS = {
    "add",
    "append",
    "clear",
    "discard",
    "extend",
    "insert",
    "pop",
    "remove",
    "reverse",
    "setdefault",
    "sort",
    "update",
}
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
DOC_METADATA_KEYS = {
    "title",
    "status",
    "authoritative_source",
    "verified",
    "audience",
    "maintenance",
}
VIRTUAL_GENERATED_DOCS = {
    "docs/ARCHITECTURE_DEBT_STATUS.md": {
        "title": "Architecture debt status",
        "status": "generated",
        "authoritative_source": "coverage/architecture-audit.json",
        "verified": "generated from the Phase 0 baseline",
        "audience": "maintainers and rules contributors",
        "maintenance": "generated",
    },
    "docs/COMPILER_COVERAGE_STATUS.md": {
        "title": "Compiler coverage status",
        "status": "generated",
        "authoritative_source": "coverage/architecture-audit.json",
        "verified": "generated from pinned coverage artifacts",
        "audience": "compiler and rules contributors",
        "maintenance": "generated",
    },
}


@dataclass(frozen=True)
class SourceAnalysis:
    relative: str
    module: str
    text: str
    tree: ast.Module
    logical_lines: frozenset[int]
    functions: tuple[dict[str, Any], ...]
    imports: tuple[str, ...]
    string_literals: tuple[dict[str, Any], ...]
    state_writes: tuple[dict[str, Any], ...]
    semantic_branches: tuple[dict[str, Any], ...]
    oracle_id_literals: tuple[dict[str, Any], ...]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _serialize_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _source() -> dict[str, Any]:
    source = _load_json(SOURCE)
    if source.get("schema_version") != 1:
        raise ValueError("Unsupported architecture audit source schema")
    return source


def _production_paths(source: Mapping[str, Any]) -> list[Path]:
    paths: set[Path] = set()
    for relative in source["scope"]["production_roots"]:
        root = ROOT / relative
        if not root.is_dir():
            raise ValueError(f"Production root does not exist: {relative}")
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in PYTHON_SUFFIXES | WEB_SUFFIXES:
                if "generated" not in path.relative_to(ROOT).parts:
                    paths.add(path)
    for relative in source["scope"].get("production_files", []):
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"Production file does not exist: {relative}")
        paths.add(path)
    return sorted(paths, key=lambda value: value.relative_to(ROOT).as_posix())


def _logical_python_lines(text: str) -> frozenset[int]:
    ignored = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
        tokenize.COMMENT,
    }
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type not in ignored and token.string.strip():
            lines.add(token.start[0])
    return frozenset(lines)


def _logical_web_lines(text: str) -> int:
    in_block = False
    count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if in_block:
            if "*/" in line:
                in_block = False
                line = line.split("*/", 1)[1].strip()
            else:
                continue
        if line.startswith("/*"):
            if "*/" not in line[2:]:
                in_block = True
                continue
            line = line.split("*/", 1)[1].strip()
        if line and not line.startswith("//"):
            count += 1
    return count


def _module_name(relative: str) -> str:
    path = Path(relative).with_suffix("")
    parts = list(path.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _source_segment(lines: tuple[str, ...], node: ast.AST) -> str:
    """Return a node's source without repeatedly rescanning the whole module."""
    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    start_column = getattr(node, "col_offset", None)
    end_column = getattr(node, "end_col_offset", None)
    if None in {start_line, end_line, start_column, end_column}:
        return ast.unparse(node)
    start_index = int(start_line) - 1
    end_index = int(end_line) - 1
    if start_index == end_index:
        return lines[start_index][int(start_column) : int(end_column)]
    pieces = [lines[start_index][int(start_column) :]]
    pieces.extend(lines[start_index + 1 : end_index])
    pieces.append(lines[end_index][: int(end_column)])
    return "".join(pieces)


def _nearest_function(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> str | None:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(current)
    return None


def _function_records(
    tree: ast.Module,
    logical_lines: frozenset[int],
    relative: str,
    parents: Mapping[ast.AST, ast.AST],
) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parent = parents.get(node)
        is_method = isinstance(parent, ast.ClassDef)
        qualified = f"{parent.name}.{node.name}" if is_method else node.name
        end = int(node.end_lineno or node.lineno)
        records.append(
            {
                "file": relative,
                "symbol": qualified,
                "name": node.name,
                "kind": "method" if is_method else "function",
                "visibility": (
                    "dunder"
                    if node.name.startswith("__") and node.name.endswith("__")
                    else "private"
                    if node.name.startswith("_")
                    else "public"
                ),
                "line": node.lineno,
                "end_line": end,
                "physical_lines": end - node.lineno + 1,
                "logical_lines": sum(node.lineno <= line <= end for line in logical_lines),
            }
        )
    return tuple(sorted(records, key=lambda item: (item["line"], item["symbol"])))


def _resolved_imports(tree: ast.Module, module: str) -> tuple[str, ...]:
    imports: set[str] = set()
    current = module.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = current[: -node.level]
                if node.module:
                    imports.add(".".join([*prefix, node.module]))
                else:
                    imports.update(".".join([*prefix, alias.name]) for alias in node.names)
            elif node.module:
                imports.add(node.module)
    return tuple(sorted(value for value in imports if value))


def _attribute_chain(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*_attribute_chain(node.value), node.attr]
    if isinstance(node, ast.Subscript):
        return _attribute_chain(node.value)
    return []


def _is_state_reference(
    node: ast.AST,
    relative: str,
    state_owner_modules: set[str],
    state_parameter_modules: set[str],
) -> bool:
    chain = _attribute_chain(node)
    if relative in state_owner_modules and chain[:2] == ["self", "state"]:
        return True
    return relative in state_parameter_modules and chain[:1] == ["state"]


def _state_write_records(
    tree: ast.Module,
    lines: tuple[str, ...],
    relative: str,
    source: Mapping[str, Any],
    parents: Mapping[ast.AST, ast.AST],
) -> tuple[dict[str, Any], ...]:
    owner_modules = set(source["scope"]["state_owner_modules"])
    parameter_modules = set(source["scope"]["state_parameter_modules"])
    records: dict[tuple[int, int, str, str], dict[str, Any]] = {}

    def add(node: ast.AST, kind: str, target: ast.AST) -> None:
        if not _is_state_reference(target, relative, owner_modules, parameter_modules):
            return
        expression = _source_segment(lines, node)
        expression = " ".join(expression.split())[:240]
        key = (node.lineno, node.col_offset, kind, expression)
        records[key] = {
            "file": relative,
            "line": node.lineno,
            "column": node.col_offset,
            "symbol": _nearest_function(node, parents),
            "kind": kind,
            "expression": expression,
        }

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                add(node, "assignment", target)
        elif isinstance(node, ast.AnnAssign):
            add(node, "annotated_assignment", node.target)
        elif isinstance(node, ast.AugAssign):
            add(node, "augmented_assignment", node.target)
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                add(node, "delete", target)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in MUTATING_METHODS:
                add(node, f"mutating_call:{node.func.attr}", node.func.value)
    return tuple(records[key] for key in sorted(records))


def _semantic_branch_records(
    tree: ast.Module,
    lines: tuple[str, ...],
    relative: str,
    parents: Mapping[ast.AST, ast.AST],
) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        condition: ast.AST | None = None
        if isinstance(node, ast.If):
            condition = node.test
        elif isinstance(node, ast.Match):
            condition = node.subject
        if condition is None:
            continue
        rendered = _source_segment(lines, condition)
        if not re.search(r"\b(?:op|operation)\b", rendered, re.IGNORECASE):
            continue
        literals = sorted(
            {
                child.value
                for child in ast.walk(condition)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            }
        )
        records.append(
            {
                "file": relative,
                "line": node.lineno,
                "symbol": _nearest_function(node, parents),
                "condition": " ".join(rendered.split())[:240],
                "string_literals": literals,
            }
        )
    return tuple(sorted(records, key=lambda item: (item["line"], item["condition"])))


def _string_records(
    tree: ast.Module,
    relative: str,
    parents: Mapping[ast.AST, ast.AST],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    condition_nodes: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            condition_nodes.update(ast.walk(node.test))
        elif isinstance(node, ast.Match):
            condition_nodes.update(ast.walk(node.subject))
            for case in node.cases:
                condition_nodes.update(ast.walk(case.pattern))
                if case.guard:
                    condition_nodes.update(ast.walk(case.guard))
    strings: list[dict[str, Any]] = []
    oracle_ids: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        record = {
            "file": relative,
            "line": node.lineno,
            "column": node.col_offset,
            "symbol": _nearest_function(node, parents),
            "value": node.value,
            "in_condition": node in condition_nodes,
        }
        strings.append(record)
        for oracle_id in UUID_PATTERN.findall(node.value):
            oracle_ids.append({**record, "oracle_id": oracle_id.lower()})
    key = lambda item: (item["line"], item["column"], item["value"])
    return tuple(sorted(strings, key=key)), tuple(sorted(oracle_ids, key=key))


def _analyze_python(path: Path, source: Mapping[str, Any]) -> SourceAnalysis:
    relative = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=relative)
    parents = _parent_map(tree)
    lines = tuple(text.splitlines(keepends=True))
    logical = _logical_python_lines(text)
    strings, oracle_ids = _string_records(tree, relative, parents)
    return SourceAnalysis(
        relative=relative,
        module=_module_name(relative),
        text=text,
        tree=tree,
        logical_lines=logical,
        functions=_function_records(tree, logical, relative, parents),
        imports=_resolved_imports(tree, _module_name(relative)),
        string_literals=strings,
        state_writes=_state_write_records(tree, lines, relative, source, parents),
        semantic_branches=_semantic_branch_records(tree, lines, relative, parents),
        oracle_id_literals=oracle_ids,
    )


def analyze_production() -> tuple[
    dict[str, Any], list[Path], dict[str, SourceAnalysis]
]:
    source = _source()
    paths = _production_paths(source)
    analyses = {
        path.relative_to(ROOT).as_posix(): _analyze_python(path, source)
        for path in paths
        if path.suffix == ".py"
    }
    return source, paths, analyses


def _production_metrics(
    paths: Iterable[Path],
    analyses: Mapping[str, SourceAnalysis],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    functions = [item for value in analyses.values() for item in value.functions]
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        physical = len(text.splitlines())
        logical = (
            len(analyses[relative].logical_lines)
            if relative in analyses
            else _logical_web_lines(text)
        )
        modules.append(
            {
                "file": relative,
                "language": "python" if path.suffix == ".py" else "web",
                "physical_lines": physical,
                "logical_lines": logical,
                "functions_and_methods": len(analyses[relative].functions)
                if relative in analyses
                else None,
            }
        )
    modules.sort(key=lambda item: (-item["logical_lines"], item["file"]))
    thresholds = source["thresholds"]
    method_visibility = Counter(
        item["visibility"] for item in functions if item["kind"] == "method"
    )
    oversized_modules = [
        item
        for item in modules
        if item["logical_lines"] > thresholds["module_logical_lines_review"]
    ]
    oversized_functions = [
        item
        for item in functions
        if item["logical_lines"] > thresholds["function_logical_lines_review"]
    ]
    return {
        "scope": {
            "roots": list(source["scope"]["production_roots"]),
            "files": list(source["scope"].get("production_files", [])),
            "generated_web_types_excluded": True,
            "logical_line_definition": (
                "Python token-bearing lines; nonblank non-comment lines for TypeScript, "
                "TSX, and CSS."
            ),
        },
        "file_count": len(modules),
        "python_file_count": sum(item["language"] == "python" for item in modules),
        "web_file_count": sum(item["language"] == "web" for item in modules),
        "physical_lines": sum(item["physical_lines"] for item in modules),
        "logical_lines": sum(item["logical_lines"] for item in modules),
        "modules": modules,
        "methods": {
            "public": method_visibility["public"],
            "private": method_visibility["private"],
            "dunder": method_visibility["dunder"],
            "total": sum(method_visibility.values()),
        },
        "top_level_functions": sum(item["kind"] == "function" for item in functions),
        "largest_functions_and_methods": sorted(
            functions,
            key=lambda item: (-item["logical_lines"], item["file"], item["line"]),
        )[:30],
        "review_thresholds": thresholds,
        "oversized_module_count": len(oversized_modules),
        "oversized_modules": oversized_modules,
        "oversized_function_and_method_count": len(oversized_functions),
        "oversized_functions_and_methods": sorted(
            oversized_functions,
            key=lambda item: (-item["logical_lines"], item["file"], item["line"]),
        ),
    }


def _import_metrics(analyses: Mapping[str, SourceAnalysis]) -> dict[str, Any]:
    known = {analysis.module for analysis in analyses.values()}
    edges: set[tuple[str, str]] = set()
    for analysis in analyses.values():
        for imported in analysis.imports:
            target = imported
            while target and target not in known and "." in target:
                target = target.rsplit(".", 1)[0]
            if target in known and target != analysis.module:
                edges.add((analysis.module, target))
    fan_in: Counter[str] = Counter(target for _, target in edges)
    fan_out: Counter[str] = Counter(source for source, _ in edges)
    rows = []
    for module in sorted(known):
        rows.append(
            {
                "module": module,
                "fan_in": fan_in[module],
                "fan_out": fan_out[module],
            }
        )
    return {
        "internal_edges": len(edges),
        "modules": rows,
        "highest_fan_in": sorted(rows, key=lambda row: (-row["fan_in"], row["module"]))[:15],
        "highest_fan_out": sorted(rows, key=lambda row: (-row["fan_out"], row["module"]))[:15],
    }


def _engine_metrics(
    analyses: Mapping[str, SourceAnalysis], source: Mapping[str, Any]
) -> dict[str, Any]:
    engine = analyses["mtg_commander_sim/engine.py"]
    methods = [item for item in engine.functions if item["kind"] == "method"]
    responsibilities: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for category in source["engine_method_responsibilities"]:
        pattern = re.compile(category["pattern"], re.IGNORECASE)
        names = sorted(
            item["name"]
            for item in methods
            if item["name"] not in assigned and pattern.search(item["name"])
        )
        assigned.update(names)
        responsibilities.append(
            {"id": category["id"], "method_count": len(names), "methods": names}
        )
    visibility = Counter(item["visibility"] for item in methods)
    return {
        "physical_lines": len(engine.text.splitlines()),
        "logical_lines": len(engine.logical_lines),
        "public_methods": visibility["public"],
        "private_methods": visibility["private"],
        "dunder_methods": visibility["dunder"],
        "responsibility_groups": responsibilities,
        "cross_subsystem_responsibility_count": sum(
            bool(item["method_count"]) for item in responsibilities
        ),
        "unclassified_methods": sorted(
            item["name"] for item in methods if item["name"] not in assigned
        ),
    }


def _state_and_dispatch_metrics(
    analyses: Mapping[str, SourceAnalysis], source: Mapping[str, Any]
) -> dict[str, Any]:
    state_writes = [item for value in analyses.values() for item in value.state_writes]
    branches = [item for value in analyses.values() for item in value.semantic_branches]
    oracle_ids = [item for value in analyses.values() for item in value.oracle_id_literals]
    card_ops = set(source["card_specific_semantic_operations"])
    branch_literals = Counter(
        literal for branch in branches for literal in branch["string_literals"]
    )
    return {
        "direct_game_state_write_heuristic": {
            "count": len(state_writes),
            "locations": sorted(
                state_writes, key=lambda item: (item["file"], item["line"], item["column"])
            ),
            "limitations": (
                "Counts direct assignments and common mutator calls rooted at configured "
                "GameState owners or GameState parameters; alias-mediated writes require review."
            ),
        },
        "semantic_operation_branches": {
            "count": len(branches),
            "locations": sorted(branches, key=lambda item: (item["file"], item["line"])),
            "operation_literal_counts": dict(sorted(branch_literals.items())),
            "card_specific_operation_branch_occurrences": {
                operation: branch_literals[operation]
                for operation in sorted(card_ops)
                if branch_literals[operation]
            },
            "limitations": (
                "AST heuristic covers if/match conditions whose source names op or operation."
            ),
        },
        "oracle_id_literals": {
            "count": len(oracle_ids),
            "locations": sorted(
                oracle_ids, key=lambda item: (item["file"], item["line"], item["column"])
            ),
        },
    }


def _semantic_handler_metrics(
    state_dispatch: Mapping[str, Any],
) -> dict[str, Any]:
    from mtg_commander_sim.semantic_runtime import (
        default_semantic_handler_registry,
    )

    registry = default_semantic_handler_registry()
    inventory = registry.inventory()
    engine_branches = [
        branch
        for branch in state_dispatch["semantic_operation_branches"][
            "locations"
        ]
        if branch["file"] == "mtg_commander_sim/engine.py"
    ]
    legacy_apply_effect_branches = [
        branch
        for branch in engine_branches
        if branch["symbol"] == "apply_effect"
    ]
    engine_dispatch_operations = {
        literal
        for branch in engine_branches
        for literal in branch["string_literals"]
    }
    registered_operations = {
        str(handler["operation"]) for handler in inventory
    }
    return {
        "schema_version": 1,
        "registry_fingerprint": registry.fingerprint,
        "registered_handler_count": len(inventory),
        "registered_operation_count": len(registered_operations),
        "registered_operations": sorted(registered_operations),
        "handlers": inventory,
        "engine_string_dispatch_branch_count": len(engine_branches),
        "legacy_apply_effect_branch_count": len(
            legacy_apply_effect_branches
        ),
        "registered_operations_still_in_legacy_dispatch": sorted(
            registered_operations & engine_dispatch_operations
        ),
        "read_only_context": (
            "mtg_commander_sim.semantic_runtime.context."
            "ReadOnlyHandlerContext"
        ),
        "typed_intent_executor": (
            "mtg_commander_sim.semantic_runtime.executor."
            "execute_intent_plan"
        ),
    }


def _card_names(database: Path) -> tuple[dict[str, str], dict[str, str]]:
    names: dict[str, str] = {}
    metadata: dict[str, str] = {}
    with sqlite3.connect(database) as connection:
        metadata = {
            str(key): str(value)
            for key, value in connection.execute("SELECT key, value FROM metadata")
        }
        for name, faces_json in connection.execute(
            "SELECT name, faces_json FROM cards ORDER BY oracle_id"
        ):
            names[str(name).strip().casefold()] = str(name)
            try:
                faces = json.loads(str(faces_json))
            except json.JSONDecodeError:
                faces = []
            for face in faces if isinstance(faces, list) else []:
                if isinstance(face, dict) and str(face.get("name") or "").strip():
                    face_name = str(face["name"]).strip()
                    names[face_name.casefold()] = face_name
    return names, metadata


def _refresh_card_baseline(
    database: Path,
    analyses: Mapping[str, SourceAnalysis],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    if not database.is_file():
        raise ValueError(f"Card database does not exist: {database}")
    names, metadata = _card_names(database)
    scoped_files = set(source["scope"]["core_card_specificity_files"])
    matches: list[dict[str, Any]] = []
    for relative in sorted(scoped_files):
        if relative not in analyses:
            raise ValueError(f"Card-specificity file is not a Python production file: {relative}")
        for literal in analyses[relative].string_literals:
            normalized = " ".join(literal["value"].split()).casefold()
            if normalized in names:
                matches.append({**literal, "matched_printed_name": names[normalized]})
    return {
        "schema_version": 1,
        "generator": "scripts/update_architecture_audit.py --write --card-db <path>",
        "database_snapshot": {
            "card_count": metadata.get("card_count"),
            "oracle_source_sha256": metadata.get("oracle_source_sha256"),
            "scryfall_oracle_updated_at": metadata.get("scryfall_oracle_updated_at"),
        },
        "card_names_and_faces_loaded": len(names),
        "scope": sorted(scoped_files),
        "exact_printed_name_literals": sorted(
            matches,
            key=lambda item: (item["file"], item["line"], item["column"], item["value"]),
        ),
        "limitations": (
            "Exact full printed-name literals only. Card-named helpers and semantic "
            "operations are separately reviewed in architecture-audit-source.json."
        ),
    }


def _card_name_index(
    database: Path,
) -> dict[str, Any]:
    if not database.is_file():
        raise ValueError(f"Card database does not exist: {database}")
    names, metadata = _card_names(database)
    snapshot = {
        "card_count": metadata.get("card_count"),
        "oracle_source_sha256": metadata.get("oracle_source_sha256"),
        "scryfall_oracle_updated_at": metadata.get("scryfall_oracle_updated_at"),
    }
    return build_card_name_hash_index(names, snapshot)


def _validate_card_baseline(
    baseline: Mapping[str, Any],
    analyses: Mapping[str, SourceAnalysis],
    source: Mapping[str, Any],
    digest_index: frozenset[bytes],
) -> dict[str, Any]:
    def identity(literal: Mapping[str, Any]) -> tuple[str, str | None, str, bool]:
        return (
            str(literal["file"]),
            literal.get("symbol"),
            str(literal["value"]),
            bool(literal.get("in_condition")),
        )

    observed = [
        literal
        for relative in source["scope"]["core_card_specificity_files"]
        for literal in analyses[relative].string_literals
        if printed_name_digest(str(literal["value"])) in digest_index
    ]
    allowances = Counter(
        identity(item) for item in baseline.get("exact_printed_name_literals", [])
    )
    new: list[dict[str, Any]] = []
    for item in observed:
        key = identity(item)
        if allowances[key] > 0:
            allowances[key] -= 1
        else:
            new.append(item)
    removed_count = sum(allowances.values())
    return {
        "entry_count": len(observed),
        "baseline_entry_count": len(
            baseline.get("exact_printed_name_literals", [])
        ),
        "conditional_entry_count": sum(
            bool(item.get("in_condition"))
            for item in observed
        ),
        "no_unreviewed_growth": len(new) == 0,
        "new_unreviewed_literals": new,
        "removed_baseline_occurrences": removed_count,
        "structural_identity": "file, nearest symbol, literal value, conditional use",
        "database_snapshot": baseline.get("database_snapshot", {}),
        "limitations": baseline.get("limitations"),
    }


def _debt_trend(
    production: Mapping[str, Any],
    engine: Mapping[str, Any],
    state_dispatch: Mapping[str, Any],
    card_validation: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not GUARD_BASELINE.is_file():
        return None
    baseline = _load_json(GUARD_BASELINE)
    dimensions = {
        "engine_logical_lines": (
            int(baseline["engine"]["logical_lines"]),
            int(engine["logical_lines"]),
        ),
        "direct_game_state_writes": (
            sum(baseline["direct_game_state_writes_by_file"].values()),
            int(state_dispatch["direct_game_state_write_heuristic"]["count"]),
        ),
        "printed_name_literals": (
            int(card_validation["baseline_entry_count"]),
            int(card_validation["entry_count"]),
        ),
        "oracle_id_literals": (
            len(baseline["oracle_id_literals"]),
            int(state_dispatch["oracle_id_literals"]["count"]),
        ),
        "legacy_card_specific_operations": (
            len(baseline["legacy_card_specific_operations"]),
            len(source["card_specific_semantic_operations"]),
        ),
        "card_named_helpers": (
            len(baseline["card_named_helpers"]),
            len(source["card_named_helpers"]),
        ),
        "oversized_modules": (
            len(baseline["oversized_modules"]),
            int(production["oversized_module_count"]),
        ),
        "oversized_functions_and_methods": (
            len(baseline["oversized_functions_and_methods"]),
            int(production["oversized_function_and_method_count"]),
        ),
    }
    return {
        "baseline_commit": baseline["baseline_commit"],
        "policy": "platform/architecture-policy.json",
        "guard": "python scripts/validate_architecture.py --check",
        "dimensions": {
            name: {
                "baseline": baseline_value,
                "current": current_value,
                "delta": current_value - baseline_value,
            }
            for name, (baseline_value, current_value) in dimensions.items()
        },
    }


def _walk_operations(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        if isinstance(value.get("op"), str):
            yield value["op"]
        for child in value.values():
            yield from _walk_operations(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_operations(child)


def _semantic_pack_metrics(source: Mapping[str, Any]) -> dict[str, Any]:
    files = sorted((ROOT / "mtg_commander_sim" / "semantic_packs").glob("*.json"))
    programs: list[tuple[str, dict[str, Any]]] = []
    pack_rows: list[dict[str, Any]] = []
    operations: Counter[str] = Counter()
    for path in files:
        value = _load_json(path)
        pack_programs = value.get("programs", [])
        if not isinstance(pack_programs, list):
            raise ValueError(f"{path} programs must be a list")
        for program in pack_programs:
            if not isinstance(program, dict):
                raise ValueError(f"{path} contains a non-object program")
            programs.append((path.name, program))
            operations.update(_walk_operations(program))
        pack_rows.append(
            {
                "file": path.relative_to(ROOT).as_posix(),
                "name": value.get("name"),
                "schema_version": value.get("schema_version"),
                "program_count": len(pack_programs),
            }
        )
    keys: defaultdict[str, list[str]] = defaultdict(list)
    oracle_ids: set[str] = set()
    trust = Counter()
    authored_by = Counter()
    for filename, program in programs:
        keys[str(program.get("key"))].append(filename)
        if program.get("oracle_id"):
            oracle_ids.add(str(program["oracle_id"]))
        trust[str(program.get("trust_level") or "missing")] += 1
        provenance = program.get("provenance")
        if isinstance(provenance, dict):
            authored_by[str(provenance.get("authored_by") or "missing")] += 1
    duplicates = {
        key: origins for key, origins in sorted(keys.items()) if len(origins) > 1
    }
    card_specific = set(source["card_specific_semantic_operations"])
    observed = set(operations)
    return {
        "pack_count": len(pack_rows),
        "program_entries": len(programs),
        "unique_program_keys": len(keys),
        "unique_oracle_ids": len(oracle_ids),
        "duplicate_key_count": len(duplicates),
        "duplicate_keys_and_pack_order": duplicates,
        "trust_level_counts": dict(sorted(trust.items())),
        "authored_by_counts": dict(sorted(authored_by.items())),
        "packs": pack_rows,
        "semantic_operation_counts": dict(sorted(operations.items())),
        "card_specific_operations": sorted(card_specific & observed),
        "configured_card_specific_operations_not_observed": sorted(card_specific - observed),
        "unclassified_operation_count": len(observed - card_specific),
        "typed_card_override_boundary_present": (
            ROOT / "mtg_commander_sim" / "card_programs" / "model.py"
        ).is_file(),
        "explicit_typed_override_count": 0,
    }


def _compiler_metrics(
    source: Mapping[str, Any], analyses: Mapping[str, SourceAnalysis]
) -> dict[str, Any]:
    oracle = _load_json(ROOT / "coverage" / "oracle-coverage.json")
    commander = _load_json(ROOT / "coverage" / "oracle-coverage-commander.json")
    mechanics = _load_json(ROOT / "coverage" / "mechanics-coverage.json")
    capabilities = _load_json(CAPABILITY_REGISTRY)
    card_program_schema = _load_json(CARD_PROGRAM_SCHEMA)
    capability_rows = {
        str(row["id"]): row for row in capabilities["capabilities"]
    }
    capability_statuses = Counter(
        str(row["status"]) for row in capability_rows.values()
    )
    aggregate_rows = []
    for aggregate in capabilities["aggregates"]:
        referenced = [
            capability_rows[str(capability_id)]
            for capability_id in aggregate["capabilities"]
        ]
        aggregate_rows.append(
            {
                "mechanic_id": aggregate["mechanic_id"],
                "trusted": all(
                    row["status"] == "trusted" for row in referenced
                ),
                "capability_count": len(referenced),
                "blocked_capabilities": sorted(
                    str(row["id"])
                    for row in referenced
                    if row["status"] != "trusted"
                ),
            }
        )
    capability_fingerprint = hashlib.sha256(
        json.dumps(
            capabilities,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    symbols: defaultdict[str, list[str]] = defaultdict(list)
    for analysis in analyses.values():
        for node in ast.walk(analysis.tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols[node.name].append(f"{analysis.relative}:{node.lineno}")
        for node in analysis.tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    symbols[alias.asname or alias.name].append(f"{analysis.relative}:{node.lineno}")
    stages = []
    for stage in source["compiler_stages"]:
        evidence = {
            symbol: sorted(symbols.get(symbol, []))
            for symbol in stage["evidence_symbols"]
        }
        stages.append(
            {
                **stage,
                "evidence": evidence,
                "all_configured_evidence_present": all(evidence.values()) if evidence else False,
            }
        )
    return {
        "current_ir": (
            "OracleCardIR lowered to canonical CardProgram V2 with a derived "
            "SemanticProgram compatibility index"
        ),
        "card_program_v2_present": "CardProgram" in symbols,
        "card_program": {
            "schema_version": card_program_schema["properties"]["schema_version"]["const"],
            "required_card_fields": len(card_program_schema["required"]),
            "required_ability_fields": len(
                card_program_schema["$defs"]["ability"]["required"]
            ),
            "schema": CARD_PROGRAM_SCHEMA.relative_to(ROOT).as_posix(),
            "model": "mtg_commander_sim/card_programs/model.py",
            "adapter": "mtg_commander_sim/card_programs/adapters.py",
            "validator": "mtg_commander_sim/card_programs/validation.py",
        },
        "compiler_version": oracle.get("compiler_version"),
        "compiler_module": "mtg_commander_sim/oracle_ir.py",
        "compiler_module_physical_lines": len(
            analyses["mtg_commander_sim/oracle_ir.py"].text.splitlines()
        ),
        "compiler_module_logical_lines": len(
            analyses["mtg_commander_sim/oracle_ir.py"].logical_lines
        ),
        "stages": stages,
        "full_oracle": {
            "snapshot": oracle.get("card_data_snapshot"),
            "total_oracle_ids": oracle.get("total_oracle_ids"),
            "total_faces": oracle.get("total_faces"),
            "status_counts": oracle.get("status_counts"),
            "exact_fraction": oracle.get("exact_fraction"),
            "material_residuals": oracle.get("material_residuals"),
            "residual_kinds": oracle.get("residual_kinds"),
            "template_count": len(oracle.get("templates", {})),
            "current_snapshot_complete": oracle.get("current_snapshot_complete"),
        },
        "commander_legal_oracle": {
            "snapshot": commander.get("card_data_snapshot"),
            "total_oracle_ids": commander.get("total_oracle_ids"),
            "total_faces": commander.get("total_faces"),
            "status_counts": commander.get("status_counts"),
            "exact_fraction": commander.get("exact_fraction"),
            "material_residuals": commander.get("material_residuals"),
            "residual_kinds": commander.get("residual_kinds"),
            "template_count": len(commander.get("templates", {})),
            "current_snapshot_complete": commander.get("current_snapshot_complete"),
        },
        "mechanic_contracts": {
            "total": mechanics.get("total_mechanics"),
            "trusted": mechanics.get("trusted_mechanics"),
            "status_counts": mechanics.get("status_counts"),
            "current_snapshot_complete": mechanics.get("current_snapshot_complete"),
        },
        "rule_capabilities": {
            "schema_version": capabilities["schema_version"],
            "registry_version": capabilities["registry_version"],
            "effective_date": capabilities["effective_date"],
            "source_sha256": capabilities["source_sha256"],
            "fingerprint": capability_fingerprint,
            "total": len(capability_rows),
            "status_counts": dict(sorted(capability_statuses.items())),
            "profiles": capabilities["profiles"],
            "aggregates": aggregate_rows,
        },
    }


def _front_matter(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return metadata
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip('"')
    return {}


def _documentation_metrics(source: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for relative in source["required_documents"]:
        virtual = VIRTUAL_GENERATED_DOCS.get(relative)
        path = ROOT / relative
        present = path.is_file() or virtual is not None
        metadata = dict(virtual or _front_matter(path))
        if virtual:
            metadata["verified"] = str(source["audit"]["baseline_main_commit"])
        missing_metadata = sorted(DOC_METADATA_KEYS - set(metadata)) if present else []
        rows.append(
            {
                "file": relative,
                "present": present,
                "metadata": metadata,
                "missing_metadata": missing_metadata,
                "metadata_complete": present and not missing_metadata,
            }
        )
    return {
        "required_count": len(rows),
        "present_count": sum(row["present"] for row in rows),
        "missing_count": sum(not row["present"] for row in rows),
        "metadata_complete_count": sum(row["metadata_complete"] for row in rows),
        "missing_documents": [row["file"] for row in rows if not row["present"]],
        "metadata_drift": [
            {"file": row["file"], "missing_metadata": row["missing_metadata"]}
            for row in rows
            if row["present"] and row["missing_metadata"]
        ],
        "policy": {
            "authoritative_index": "docs/index.md",
            "validator": "python scripts/validate_documentation.py --check",
            "metadata_enforced": True,
            "internal_links_enforced": True,
            "stale_claims_enforced": True,
            "adr_system_enforced": True,
        },
        "documents": rows,
    }


def _count_test_functions(paths: Iterable[Path]) -> tuple[int, Counter[str]]:
    count = 0
    categories: Counter[str] = Counter()
    patterns = {
        "replay_named": re.compile(r"replay", re.IGNORECASE),
        "privacy_or_projection_named": re.compile(
            r"privacy|hidden|projection", re.IGNORECASE
        ),
        "compiler_named": re.compile(r"oracle|compiler|semantic", re.IGNORECASE),
        "server_named": re.compile(r"server|browser|websocket|room", re.IGNORECASE),
        "fuzz_named": re.compile(r"fuzz", re.IGNORECASE),
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                count += 1
                for category, pattern in patterns.items():
                    if pattern.search(node.name):
                        categories[category] += 1
    return count, categories


def _regex_test_count(directory: Path, pattern: str) -> int:
    expression = re.compile(pattern, re.MULTILINE)
    return sum(
        len(expression.findall(path.read_text(encoding="utf-8")))
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx"}
    )


def _test_metrics() -> dict[str, Any]:
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    conventional, categories = _count_test_functions(tests)
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    discovered = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), pattern="test_*.py"
    ).countTestCases()
    rules = _load_json(ROOT / "coverage" / "rules-conformance.json")
    generated_rules = int(rules.get("total_cases") or 0)
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").casefold()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").casefold()
    mutation_tools = [
        tool for tool in ("mutmut", "cosmic-ray", "mutpy") if tool in requirements + pyproject
    ]
    return {
        "python": {
            "discovered_total": discovered,
            "conventional_ast_cases": conventional,
            "generated_rule_conformance_cases": generated_rules,
            "reconciles": discovered == conventional + generated_rules,
            "test_files": len(tests),
            "named_cross_cutting_counts": dict(sorted(categories.items())),
        },
        "browser": {
            "playwright_e2e_journeys": _regex_test_count(
                ROOT / "web" / "tests", r"^\s*test\s*\("
            ),
            "node_unit_cases": _regex_test_count(
                ROOT / "web" / "unit", r"^\s*test\s*\("
            ),
        },
        "property_and_fuzz": {
            "hypothesis_configured": "hypothesis" in requirements + pyproject,
            "named_deterministic_fuzz_cases": categories["fuzz_named"],
            "dedicated_property_suite": False,
        },
        "mutation_testing": {
            "configured_tools": mutation_tools,
            "mutation_score": None,
        },
        "performance_benchmarks": {
            "dedicated_suite": False,
            "baseline": None,
        },
    }


def _rules_metrics() -> dict[str, Any]:
    manifest = _load_json(ROOT / "rules" / "manifest.json")
    conformance = _load_json(ROOT / "coverage" / "rules-conformance.json")
    mechanics = _load_json(ROOT / "coverage" / "mechanics-coverage.json")
    return {
        "comprehensive_rules": {
            "effective_date": manifest.get("effective_date"),
            "source_sha256": manifest.get("source_sha256"),
            "rule_count": manifest.get("rule_count"),
            "section_count": manifest.get("section_count"),
            "glossary_count": manifest.get("glossary_count"),
        },
        "conformance": {
            "total_cases": conformance.get("total_cases"),
            "semantic_passing_cases": conformance.get("semantic_passing_cases"),
            "blocked_cases": conformance.get("blocked_cases"),
            "definition_only_cases": conformance.get("definition_only_cases"),
            "unreviewed_cases": conformance.get("unreviewed_cases"),
            "current_snapshot_complete": conformance.get("current_snapshot_complete"),
        },
        "mechanics": {
            "total": mechanics.get("total_mechanics"),
            "trusted": mechanics.get("trusted_mechanics"),
            "status_counts": mechanics.get("status_counts"),
        },
    }


def _coordinates(source: Mapping[str, Any]) -> dict[str, Any]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        "repository": "MoellerJDev/mtg-commander-sim",
        "default_branch": "main",
        "baseline_main_commit": source["audit"]["baseline_main_commit"],
        "baseline_worktree_clean": source["audit"]["baseline_worktree_clean"],
        "package_version": project["project"]["version"],
        "requires_python": project["project"]["requires-python"],
        "ci": source["ci"],
    }


def build_report() -> dict[str, Any]:
    source, paths, analyses = analyze_production()
    if not CARD_BASELINE.is_file():
        raise ValueError(
            "Missing card-specificity baseline; run with --write --card-db <full-db>"
        )
    if not CARD_NAME_INDEX.is_file():
        raise ValueError(
            "Missing card-name hash index; run with --write --card-db <full-db>"
        )
    card_baseline = _load_json(CARD_BASELINE)
    digest_index = decode_card_name_hash_index(_load_json(CARD_NAME_INDEX))
    card_validation = _validate_card_baseline(
        card_baseline, analyses, source, digest_index
    )
    if not card_validation["no_unreviewed_growth"]:
        raise ValueError(
            "Core code contains printed-name literals outside the reviewed baseline"
        )
    state_dispatch = _state_and_dispatch_metrics(analyses, source)
    semantic_handlers = _semantic_handler_metrics(state_dispatch)
    production = _production_metrics(paths, analyses, source)
    engine = _engine_metrics(analyses, source)
    return {
        "schema_version": 1,
        "generated": {
            "generator": "scripts/update_architecture_audit.py",
            "source": "platform/architecture-audit-source.json",
            "card_specificity_source": "platform/card-specificity-baseline.json",
            "stale_check": "python scripts/update_architecture_audit.py --check",
            "scope_note": source["audit"]["scope_note"],
        },
        "audit": source["audit"],
        "coordinates": _coordinates(source),
        "rules": _rules_metrics(),
        "tests": _test_metrics(),
        "architecture": {
            "production": production,
            "engine": engine,
            "imports": _import_metrics(analyses),
            **state_dispatch,
            "semantic_handlers": semantic_handlers,
            "printed_name_literals": card_validation,
            "card_named_helpers": source["card_named_helpers"],
            "subsystem_ownership": source["subsystem_ownership"],
            "missing_dedicated_owners": [
                item["id"]
                for item in source["subsystem_ownership"]
                if item["missing_dedicated_owner"]
            ],
            "debt_trend": _debt_trend(
                production, engine, state_dispatch, card_validation, source
            ),
        },
        "compiler": _compiler_metrics(source, analyses),
        "semantic_packs_and_overrides": _semantic_pack_metrics(source),
        "documentation": _documentation_metrics(source),
    }


def _metadata_lines(
    title: str, authoritative_source: str, audience: str, verified: str
) -> list[str]:
    return [
        "---",
        f'title: "{title}"',
        'status: "generated"',
        f'authoritative_source: "{authoritative_source}"',
        f'verified: "{verified}"',
        f'audience: "{audience}"',
        'maintenance: "generated"',
        "---",
        "",
    ]


def _debt_trend_lines(architecture: Mapping[str, Any]) -> list[str]:
    trend = architecture.get("debt_trend")
    if not trend:
        return []
    lines = [
        "",
        "## Enforced debt trend",
        "",
        f"Baseline: `{trend['baseline_commit']}`. Guard: `{trend['guard']}`.",
        "",
        "| Dimension | Baseline | Current | Delta |",
        "|---|---:|---:|---:|",
    ]
    for name, values in trend["dimensions"].items():
        lines.append(
            f"| `{name}` | {values['baseline']:,} | {values['current']:,} | "
            f"{values['delta']:+,} |"
        )
    return lines


def render_architecture_status(report: Mapping[str, Any]) -> str:
    architecture = report["architecture"]
    production = architecture["production"]
    engine = architecture["engine"]
    docs = report["documentation"]
    tests = report["tests"]
    lines = _metadata_lines(
        "Architecture debt status",
        "coverage/architecture-audit.json",
        "maintainers and rules contributors",
        report["audit"]["baseline_main_commit"],
    )
    lines.extend(
        [
            "# Architecture debt status",
            "",
            "This generated migration dashboard is anchored to the Phase 0 baseline. "
            "It measures the current tree and does not claim architectural completion, "
            "rules completeness, or universal card support.",
            "",
            "## Baseline coordinates",
            "",
            f"- Main commit: `{report['coordinates']['baseline_main_commit']}`",
            f"- Package: `{report['coordinates']['package_version']}`",
            f"- CI run: [{report['coordinates']['ci']['run_id']}]"
            f"({report['coordinates']['ci']['url']}) — "
            f"`{report['coordinates']['ci']['status']}`",
            f"- Production scope: {production['file_count']} files, "
            f"{production['physical_lines']:,} physical lines, "
            f"{production['logical_lines']:,} logical lines",
            "",
            "## Central engine debt",
            "",
            f"- `engine.py`: {engine['physical_lines']:,} physical / "
            f"{engine['logical_lines']:,} logical lines",
            f"- Methods: {engine['public_methods']} public, "
            f"{engine['private_methods']} private, {engine['dunder_methods']} dunder",
            f"- Cross-subsystem responsibility groups: "
            f"{engine['cross_subsystem_responsibility_count']}",
            f"- Direct GameState-write heuristic: "
            f"{architecture['direct_game_state_write_heuristic']['count']} locations",
            f"- Semantic-operation branches: "
            f"{architecture['semantic_operation_branches']['count']}",
            f"- Registered typed semantic handlers: "
            f"{architecture['semantic_handlers']['registered_handler_count']} "
            f"across {architecture['semantic_handlers']['registered_operation_count']} "
            "operations",
            f"- Remaining legacy `apply_effect` branches: "
            f"{architecture['semantic_handlers']['legacy_apply_effect_branch_count']}",
            f"- Registered operations still intercepted by engine string dispatch: "
            f"{len(architecture['semantic_handlers']['registered_operations_still_in_legacy_dispatch'])}",
            f"- Exact printed-name literals in configured core files: "
            f"{architecture['printed_name_literals']['entry_count']} "
            f"({architecture['printed_name_literals']['conditional_entry_count']} conditional)",
            f"- Oracle-ID literals in Python production code: "
            f"{architecture['oracle_id_literals']['count']}",
            f"- Card-named helpers: {len(architecture['card_named_helpers'])}",
            f"- Modules above the {production['review_thresholds']['module_logical_lines_review']:,}-logical-line review threshold: "
            f"{production['oversized_module_count']}",
            f"- Functions/methods above the {production['review_thresholds']['function_logical_lines_review']:,}-logical-line review threshold: "
            f"{production['oversized_function_and_method_count']}",
            "- Printed-name matching is deliberately over-inclusive: ordinary words that "
            "are also printed card names remain baseline candidates for Phase 1 review.",
        ]
    )
    lines.extend(_debt_trend_lines(architecture))
    lines.extend(
        [
            "",
            "## Largest production modules",
            "",
            "| File | Language | Physical | Logical |",
            "|---|---:|---:|---:|",
        ]
    )
    for module in production["modules"][:15]:
        lines.append(
            f"| `{module['file']}` | {module['language']} | "
            f"{module['physical_lines']:,} | {module['logical_lines']:,} |"
        )
    lines.extend(
        [
            "",
            "## Largest functions and methods",
            "",
            "| Symbol | File:line | Logical | Physical |",
            "|---|---|---:|---:|",
        ]
    )
    for item in production["largest_functions_and_methods"][:15]:
        lines.append(
            f"| `{item['symbol']}` | `{item['file']}:{item['line']}` | "
            f"{item['logical_lines']} | {item['physical_lines']} |"
        )
    lines.extend(
        [
            "",
            "## Engine responsibility spread",
            "",
            "| Responsibility | Matched methods |",
            "|---|---:|",
        ]
    )
    for item in engine["responsibility_groups"]:
        lines.append(f"| `{item['id']}` | {item['method_count']} |")
    lines.extend(
        [
            "",
            "## Missing dedicated ownership",
            "",
            *(
                f"- `{value}`"
                for value in architecture["missing_dedicated_owners"]
            ),
            "",
            "These are review classifications from the machine-readable source, not "
            "automatic proof that an extraction boundary is correct.",
            "",
            "## Test classes",
            "",
            f"- Python discovered: {tests['python']['discovered_total']:,}",
            f"- Conventional Python cases: "
            f"{tests['python']['conventional_ast_cases']:,}",
            f"- Generated CR conformance cases: "
            f"{tests['python']['generated_rule_conformance_cases']:,}",
            f"- Playwright journeys: {tests['browser']['playwright_e2e_journeys']}",
            f"- Browser unit cases: {tests['browser']['node_unit_cases']}",
            f"- Dedicated property suite: "
            f"{str(tests['property_and_fuzz']['dedicated_property_suite']).lower()}",
            f"- Mutation score: {tests['mutation_testing']['mutation_score']}",
            f"- Performance baseline: {tests['performance_benchmarks']['baseline']}",
            "",
            "## Documentation drift",
            "",
            f"- Required: {docs['required_count']}",
            f"- Present after generated Phase 0 outputs: {docs['present_count']}",
            f"- Missing: {docs['missing_count']}",
            f"- Metadata complete: {docs['metadata_complete_count']}",
            "",
            "The authoritative index, metadata, internal-link, stale-claim, and "
            "ADR policies are enforced by `scripts/validate_documentation.py`. "
            "Detailed document records remain in `coverage/architecture-audit.json`.",
            "",
            "## Regeneration",
            "",
            "```bash",
            "python scripts/update_architecture_audit.py --write --card-db data/scryfall-current.sqlite3",
            "python scripts/update_architecture_audit.py --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_compiler_status(report: Mapping[str, Any]) -> str:
    compiler = report["compiler"]
    full = compiler["full_oracle"]
    commander = compiler["commander_legal_oracle"]
    capabilities = compiler["rule_capabilities"]
    card_program = compiler["card_program"]
    semantics = report["semantic_packs_and_overrides"]
    lines = _metadata_lines(
        "Compiler coverage status",
        "coverage/architecture-audit.json",
        "compiler and rules contributors",
        report["audit"]["baseline_main_commit"],
    )
    lines.extend(
        [
            "# Compiler coverage status",
            "",
            "This generated report describes only the pinned Oracle corpus and current "
            "compiler. Exact compilation is not the same as complete game-behavior proof.",
            "",
            "## Current representation",
            "",
            f"- Compiler: `{compiler['compiler_version']}`",
            f"- Runtime IR: {compiler['current_ir']}",
            f"- CardProgram V2 present: "
            f"{str(compiler['card_program_v2_present']).lower()}",
            f"- Compiler module: {compiler['compiler_module_physical_lines']:,} physical / "
            f"{compiler['compiler_module_logical_lines']:,} logical lines",
            "",
            "## Canonical CardProgram",
            "",
            f"- Schema version: `{card_program['schema_version']}`",
            f"- Schema: `{card_program['schema']}`",
            f"- Required card fields: {card_program['required_card_fields']}",
            f"- Required per-ability fields: {card_program['required_ability_fields']}",
            f"- Model: `{card_program['model']}`",
            f"- Generated/reviewed adapter: `{card_program['adapter']}`",
            f"- Runtime validator: `{card_program['validator']}`",
            "",
            "## Stages",
            "",
            "| Stage | Current status | Evidence complete |",
            "|---|---|---:|",
        ]
    )
    for stage in compiler["stages"]:
        lines.append(
            f"| `{stage['id']}` | `{stage['current_status']}` | "
            f"{str(stage['all_configured_evidence_present']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Fine-grained capability registry",
            "",
            f"- Registry schema/version: "
            f"`{capabilities['schema_version']}/{capabilities['registry_version']}`",
            f"- Pinned rules effective date: `{capabilities['effective_date']}`",
            f"- Registry fingerprint: `{capabilities['fingerprint']}`",
            f"- Capability records: {capabilities['total']}",
            f"- Trusted records: "
            f"{capabilities['status_counts'].get('trusted', 0)}",
            f"- Blocked records: "
            f"{capabilities['status_counts'].get('blocked', 0)}",
            "",
            "| Broad aggregate | Capability records | Trusted | Blocked members |",
            "|---|---:|---:|---|",
        ]
    )
    for aggregate in capabilities["aggregates"]:
        blocked = ", ".join(
            f"`{value}`" for value in aggregate["blocked_capabilities"]
        ) or "none"
        lines.append(
            f"| `{aggregate['mechanic_id']}` | "
            f"{aggregate['capability_count']} | "
            f"{str(aggregate['trusted']).lower()} | {blocked} |"
        )
    lines.extend(
        [
            "",
            "## Pinned corpus accounting",
            "",
            "| Scope | Oracle IDs | Exact | Partial | Unresolved | Material residuals | Complete |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label, value in (("Full Oracle", full), ("Commander legal", commander)):
        status = value["status_counts"]
        lines.append(
            f"| {label} | {value['total_oracle_ids']:,} | {status['exact']:,} | "
            f"{status['partial']:,} | {status['unresolved']:,} | "
            f"{value['material_residuals']:,} | "
            f"{str(value['current_snapshot_complete']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Full-corpus residual kinds",
            "",
            "| Kind | Count |",
            "|---|---:|",
        ]
    )
    for kind, count in sorted(
        full["residual_kinds"].items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"| `{kind}` | {count:,} |")
    lines.extend(
        [
            "",
            "## Semantic packs and implicit overrides",
            "",
            f"- Pack files: {semantics['pack_count']}",
            f"- Program entries: {semantics['program_entries']}",
            f"- Unique program keys: {semantics['unique_program_keys']}",
            f"- Duplicate keys resolved by pack order: {semantics['duplicate_key_count']}",
            f"- Unique Oracle IDs represented: {semantics['unique_oracle_ids']}",
            f"- Card-specific operation names: "
            f"{len(semantics['card_specific_operations'])}",
            f"- Typed card-override boundary present: "
            f"{str(semantics['typed_card_override_boundary_present']).lower()}",
            f"- Explicit typed overrides: {semantics['explicit_typed_override_count']}",
            "",
            "## Snapshot fingerprints",
            "",
            f"- Oracle SHA-256: `{full['snapshot']['oracle_source_sha256']}`",
            f"- Rulings SHA-256: `{full['snapshot']['rulings_source_sha256']}`",
            f"- Oracle updated: `{full['snapshot']['scryfall_oracle_updated_at']}`",
            f"- Rulings updated: `{full['snapshot']['scryfall_rulings_updated_at']}`",
            "",
            "## Boundary",
            "",
            "The current compiler is partial and interleaved. Full-corpus exactness is "
            "not claimed. Fine-grained closure currently covers only the reviewed base-damage "
            "spell slice; other nodes retain the broad-contract fallback. CardProgram V2 now "
            "provides canonical aggregation, validation, and replay pinning. Typed handlers "
            "and fully distinct compiler stages remain incremental work.",
            "",
        ]
    )
    return "\n".join(lines)


def _outputs(report: Mapping[str, Any]) -> dict[Path, str]:
    return {
        JSON_OUTPUT: _serialize_json(report),
        ARCHITECTURE_STATUS: render_architecture_status(report),
        COMPILER_STATUS: render_compiler_status(report),
    }


def _write_outputs(report: Mapping[str, Any]) -> None:
    for path, content in _outputs(report).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def _check_outputs(report: Mapping[str, Any]) -> list[str]:
    stale = []
    for path, expected in _outputs(report).items():
        actual = path.read_text(encoding="utf-8") if path.is_file() else None
        if actual != expected:
            stale.append(path.relative_to(ROOT).as_posix())
    return stale


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--card-db", type=Path)
    parser.add_argument("--refresh-specificity-allowances", action="store_true")
    parser.add_argument("--adr", type=Path)
    args = parser.parse_args()
    refreshed_card_index = False
    refreshed_allowances = False
    if args.check and args.card_db:
        parser.error("--card-db is only valid with --write")
    if args.refresh_specificity_allowances and not args.card_db:
        parser.error("--refresh-specificity-allowances requires --card-db")
    if args.refresh_specificity_allowances and not args.adr:
        parser.error("--refresh-specificity-allowances requires --adr")
    if args.adr and not args.refresh_specificity_allowances:
        parser.error("--adr is only valid with --refresh-specificity-allowances")
    if args.write and args.card_db:
        source, _paths, analyses = analyze_production()
        CARD_NAME_INDEX.write_text(
            _serialize_json(_card_name_index(args.card_db.resolve())),
            encoding="utf-8",
            newline="\n",
        )
        refreshed_card_index = True
        if args.refresh_specificity_allowances:
            adr = args.adr.resolve()
            if not adr.is_file() or ROOT not in adr.parents:
                parser.error("--adr must name an existing repository ADR")
            adr_relative = adr.relative_to(ROOT)
            if adr_relative.parts[:2] != ("docs", "adr"):
                parser.error("--adr must be under docs/adr/")
            baseline = _refresh_card_baseline(
                args.card_db.resolve(), analyses, source
            )
            baseline["review_adr"] = adr_relative.as_posix()
            CARD_BASELINE.write_text(
                _serialize_json(baseline), encoding="utf-8", newline="\n"
            )
            refreshed_allowances = True
    report = build_report()
    if args.write:
        _write_outputs(report)
        print(
            json.dumps(
                {
                    "ok": True,
                    "outputs": [
                        *(
                            [CARD_NAME_INDEX.relative_to(ROOT).as_posix()]
                            if refreshed_card_index
                            else []
                        ),
                        *(
                            [CARD_BASELINE.relative_to(ROOT).as_posix()]
                            if refreshed_allowances
                            else []
                        ),
                        *(
                            path.relative_to(ROOT).as_posix()
                            for path in _outputs(report)
                        ),
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    stale = _check_outputs(report)
    if stale:
        print(
            "architecture audit is stale; run `python "
            "scripts/update_architecture_audit.py --write --card-db "
            "data/scryfall-current.sqlite3`: "
            + ", ".join(stale),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"ok": True, "stale_outputs": []}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"architecture audit failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
