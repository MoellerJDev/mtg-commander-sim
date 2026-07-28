from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest

from mtg_commander_sim.bulk import (
    ScryfallBulkDataError,
    ScryfallBulkItem,
    _download_bulk_item,
    fetch_bulk_manifest,
    parse_bulk_manifest,
)


class _Response(io.BytesIO):
    def __init__(self, value: bytes, headers=None):
        super().__init__(value)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class ScryfallBulkDataTests(unittest.TestCase):
    def test_manifest_prefers_streamable_jsonl_and_ignores_untrusted_hosts(self):
        items = parse_bulk_manifest(
            {
                "object": "list",
                "data": [
                    {
                        "type": "oracle_cards",
                        "name": "Oracle Cards",
                        "updated_at": "2026-07-28T20:11:20Z",
                        "download_uri": "https://data.scryfall.io/oracle.json",
                        "jsonl_download_uri": "https://data.scryfall.io/oracle.jsonl.gz",
                        "compressed_size": 123,
                    },
                    {
                        "type": "rulings",
                        "jsonl_download_uri": "https://attacker.invalid/rulings.jsonl.gz",
                    },
                ],
            }
        )
        self.assertEqual("https://data.scryfall.io/oracle.jsonl.gz", items["oracle_cards"].download_uri)
        self.assertEqual(123, items["oracle_cards"].compressed_size)
        self.assertNotIn("rulings", items)

    def test_fetch_manifest_uses_runtime_response(self):
        payload = {
            "object": "list",
            "data": [
                {
                    "type": "rulings",
                    "name": "Rulings",
                    "updated_at": "now",
                    "jsonl_download_uri": "https://data.scryfall.io/rulings-current.jsonl.gz",
                }
            ],
        }
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request.full_url, timeout, request.get_header("User-agent")))
            return _Response(json.dumps(payload).encode("utf-8"))

        items, returned = fetch_bulk_manifest(timeout=7, urlopen=fake_urlopen)
        self.assertEqual(payload, returned)
        self.assertIn("rulings", items)
        self.assertEqual("https://api.scryfall.com/bulk-data", calls[0][0])
        self.assertEqual(7, calls[0][1])
        self.assertIn("mtg-commander-sim", calls[0][2])

    def test_invalid_manifest_fails_closed(self):
        with self.assertRaises(ScryfallBulkDataError):
            parse_bulk_manifest({"object": "card", "data": []})

    def test_download_validates_http_length_not_inconsistent_manifest_size(self):
        item = ScryfallBulkItem(
            type="rulings",
            name="Rulings",
            updated_at="now",
            download_uri="https://data.scryfall.io/rulings.jsonl.gz",
            compressed_size=999,
        )

        def fake_urlopen(_request, timeout):
            self.assertEqual(3, timeout)
            return _Response(b"abc", {"Content-Length": "3"})

        with tempfile.TemporaryDirectory() as directory:
            path = _download_bulk_item(
                item,
                Path(directory),
                timeout=3,
                force=False,
                urlopen=fake_urlopen,
            )
            self.assertEqual(b"abc", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
