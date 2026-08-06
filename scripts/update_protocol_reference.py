from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
root_text = str(ROOT)
if root_text not in sys.path:
    sys.path.insert(0, root_text)

from server.app import ServerSettings, create_app

JSON_PATH = ROOT / "coverage" / "protocol-inventory.json"
MARKDOWN_PATH = ROOT / "docs" / "reference" / "protocol-inventory.md"
GENERATION_COMMAND = (
    r".\.venv\Scripts\python.exe scripts\update_protocol_reference.py --write"
)
HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "trace"}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _schema_ref(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("$ref"), str):
        return value["$ref"]
    for key in ("anyOf", "oneOf", "allOf"):
        children = value.get(key)
        if isinstance(children, list):
            refs = [item.get("$ref") for item in children if isinstance(item, dict)]
            refs = [item for item in refs if isinstance(item, str)]
            if refs:
                return " | ".join(refs)
    return None


def _route_inventory(openapi: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for path, path_item in sorted(openapi.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            request_schema = None
            request_body = operation.get("requestBody", {})
            if isinstance(request_body, dict):
                content = request_body.get("content", {})
                if isinstance(content, dict):
                    for media_type in sorted(content):
                        media = content[media_type]
                        if isinstance(media, dict):
                            request_schema = _schema_ref(media.get("schema"))
                            if request_schema:
                                break
            routes.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": operation.get("operationId"),
                    "summary": operation.get("summary"),
                    "request_schema": request_schema,
                    "response_statuses": sorted(operation.get("responses", {}).keys()),
                }
            )
    return routes


def _schema_inventory() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    source: dict[str, Any] = {}
    for path in sorted((ROOT / "schemas").glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        source[relative] = schema
        properties = schema.get("properties", {})
        summaries.append(
            {
                "path": relative,
                "id": schema.get("$id"),
                "title": schema.get("title"),
                "type": schema.get("type"),
                "required": list(schema.get("required", [])),
                "properties": sorted(properties) if isinstance(properties, dict) else [],
            }
        )
    return summaries, source


def build_inventory() -> dict[str, Any]:
    scratch = ROOT / ".codex" / "protocol-inventory"
    settings = ServerSettings(
        card_db=scratch / "cards.sqlite3",
        database=scratch / "server.sqlite3",
        game_root=scratch / "games",
        bulk_dir=scratch / "bulk",
        card_snapshot_dir=scratch / "snapshots",
        image_cache=scratch / "images",
        static_dir=scratch / "web",
        auto_update_cards=False,
    )
    app = create_app(settings)
    openapi = app.openapi()
    http_routes = _route_inventory(openapi)
    websocket_routes = sorted(
        {
            route.path
            for route in app.routes
            if "WebSocketRoute" in type(route).__name__ and hasattr(route, "path")
        }
    )
    schemas, schema_source = _schema_inventory()
    source = {"openapi": openapi, "schemas": schema_source}
    fingerprint = hashlib.sha256(_canonical_bytes(source)).hexdigest()
    blockers: list[str] = []
    for schema in schemas:
        if not schema["id"]:
            blockers.append(f"{schema['path']} has no $id")
        if not schema["title"]:
            blockers.append(f"{schema['path']} has no title")
    return {
        "schema_version": 1,
        "source_fingerprint": fingerprint,
        "protocol": {
            "title": openapi.get("info", {}).get("title"),
            "version": openapi.get("info", {}).get("version"),
        },
        "http_routes": http_routes,
        "websocket_routes": websocket_routes,
        "schemas": schemas,
        "top_blockers": blockers[:5],
        "generation_command": GENERATION_COMMAND,
    }


def render_markdown(inventory: dict[str, Any]) -> str:
    protocol = inventory["protocol"]
    blockers = inventory["top_blockers"]
    blocker_lines = (
        "\n".join(f"- {item}" for item in blockers)
        if blockers
        else "- None detected by the inventory generator."
    )
    route_lines = "\n".join(
        f"| `{route['method']}` | `{route['path']}` | `{route['operation_id'] or ''}` |"
        for route in inventory["http_routes"]
    )
    websocket_lines = "\n".join(
        f"- `{path}`" for path in inventory["websocket_routes"]
    ) or "- None."
    machine_fingerprint = hashlib.sha256(
        (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()
    return f'''---
title: "Generated protocol inventory"
status: "generated"
authoritative_source: "server FastAPI OpenAPI output and versioned schemas/*.json"
verified: "{machine_fingerprint}"
audience: "client, server, and protocol contributors"
maintenance: "generated"
generated_source: "coverage/protocol-inventory.json"
generation_command: "{GENERATION_COMMAND}"
---

# Generated protocol inventory

Source fingerprint: `{inventory['source_fingerprint']}`

## Current top-level state

- API title: `{protocol['title']}`
- API version: `{protocol['version']}`
- HTTP operations: `{len(inventory['http_routes'])}`
- WebSocket routes: `{len(inventory['websocket_routes'])}`
- Versioned schemas: `{len(inventory['schemas'])}`

## Top blockers

{blocker_lines}

## HTTP operations

| Method | Path | Operation ID |
| --- | --- | --- |
{route_lines}

## WebSocket routes

{websocket_lines}

Complete request, response, route, and schema summaries are in the
[machine-readable protocol inventory](../../coverage/protocol-inventory.json).
The versioned schema bodies remain authoritative in [`schemas/`](../../schemas/).

Exact generation command:

```powershell
{GENERATION_COMMAND}
```
'''


def _expected() -> tuple[str, str]:
    inventory = build_inventory()
    serialized = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    return serialized, render_markdown(inventory)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected_json, expected_markdown = _expected()
    if args.write:
        JSON_PATH.write_text(expected_json, encoding="utf-8", newline="\n")
        MARKDOWN_PATH.write_text(expected_markdown, encoding="utf-8", newline="\n")
    else:
        stale = []
        for path, expected in (
            (JSON_PATH, expected_json),
            (MARKDOWN_PATH, expected_markdown),
        ):
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(path.relative_to(ROOT).as_posix())
        if stale:
            raise ValueError(f"stale generated protocol reference: {stale}")
    print(json.dumps({"ok": True, "protocol_reference": "current"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"protocol reference generation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
