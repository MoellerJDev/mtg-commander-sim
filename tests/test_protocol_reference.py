from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "update_protocol_reference", ROOT / "scripts" / "update_protocol_reference.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProtocolReferenceTests(unittest.TestCase):
    def test_inventory_contains_http_and_websocket_routes(self) -> None:
        inventory = MODULE.build_inventory()
        self.assertEqual("Quorune Server", inventory["protocol"]["title"])
        routes = {(item["method"], item["path"]) for item in inventory["http_routes"]}
        self.assertIn(("GET", "/api/v1/health"), routes)
        self.assertIn(("POST", "/api/v1/games/{game_id}/commands"), routes)
        self.assertIn("/api/v1/games/{game_id}/stream", inventory["websocket_routes"])

    def test_inventory_contains_versioned_message_schemas(self) -> None:
        inventory = MODULE.build_inventory()
        paths = {item["path"] for item in inventory["schemas"]}
        self.assertIn("schemas/command-envelope.schema.json", paths)
        self.assertIn("schemas/decision-packet.schema.json", paths)
        self.assertIn("schemas/pilot-response.schema.json", paths)
        titles = {item["path"]: item["title"] for item in inventory["schemas"]}
        self.assertEqual(
            "Quorune client command envelope v3.0",
            titles["schemas/command-envelope.schema.json"],
        )
        self.assertEqual(
            "Quorune projected decision packet v3.0",
            titles["schemas/decision-packet.schema.json"],
        )

    def test_generation_is_deterministic(self) -> None:
        first = MODULE.build_inventory()
        second = MODULE.build_inventory()
        self.assertEqual(first, second)
        self.assertRegex(first["source_fingerprint"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
