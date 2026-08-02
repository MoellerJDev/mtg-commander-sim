from __future__ import annotations

import ast
from pathlib import Path


def implementation_component_resolves(component: str) -> bool:
    """Resolve a package component without importing runtime game modules."""

    prefix = "mtg_commander_sim."
    if not component.startswith(prefix):
        return False
    parts = component.removeprefix(prefix).split(".")
    package_root = Path(__file__).resolve().parents[1]
    for length in range(len(parts), 0, -1):
        relative = Path(*parts[:length])
        module_path = package_root / relative.with_suffix(".py")
        if not module_path.is_file():
            module_path = package_root / relative / "__init__.py"
        if not module_path.is_file():
            continue
        remaining = parts[length:]
        if not remaining:
            return True
        try:
            tree = ast.parse(
                module_path.read_text(encoding="utf-8"),
                filename=str(module_path),
            )
        except (OSError, SyntaxError, UnicodeError):
            return False
        exported = {
            node.name
            for node in tree.body
            if isinstance(
                node,
                (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }
        exported.update(
            target.id
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
            if isinstance(target, ast.Name)
        )
        return remaining[0] in exported
    return False
