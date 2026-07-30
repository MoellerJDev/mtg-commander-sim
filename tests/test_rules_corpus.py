from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mtg_commander_sim.cli import main
from mtg_commander_sim.rules_corpus import (
    RulesCorpusError,
    _trusted_https_url,
    compare_rule_indexes,
    parse_comprehensive_rules,
    rules_coverage,
    rules_inventory,
    sync_rules_corpus,
    verify_rules_corpus,
)


RULES_FIXTURE = """\
Magic: The Gathering Comprehensive Rules

These rules are effective as of June 19, 2026.

Contents
1. Game Concepts
100. General
7. Additional Rules
701. Keyword Actions
702. Keyword Abilities
Glossary

1. Game Concepts
100. General
100.1. Behavioral source text that must never enter the derived index.
100.1a A dependent subrule used by the parser test.

7. Additional Rules
701. Keyword Actions
701.1. Keyword action introduction.
701.2. Activate
701.2a Activation detail.
702. Keyword Abilities
702.1. Keyword ability introduction.
702.2. Flying
702.2a Flying detail.

Glossary

Activate
A glossary definition. See rule 701.2.

Flying
Another glossary definition. See rule 702.2.

Credits
"""


class RulesCorpusTests(unittest.TestCase):
    def test_official_url_normalization_encodes_spaces_without_widening_hosts(self):
        self.assertEqual(
            (
                "https://media.wizards.com/2026/downloads/"
                "MagicCompRules%2020260619.txt"
            ),
            _trusted_https_url(
                "https://media.wizards.com/2026/downloads/"
                "MagicCompRules 20260619.txt"
            ),
        )
        with self.assertRaises(RulesCorpusError):
            _trusted_https_url(
                "https://attacker.invalid/MagicCompRules.txt"
            )

    def test_parse_indexes_ids_hashes_sections_glossary_and_mechanics(self):
        parsed = parse_comprehensive_rules(
            RULES_FIXTURE,
            source_sha256="a" * 64,
        )
        self.assertEqual("2026-06-19", parsed["effective_date"])
        by_id = {
            row["rule_id"]: row for row in parsed["rules"]
        }
        self.assertEqual("100.1", by_id["100.1a"]["parent_rule_id"])
        self.assertEqual(
            {"100", "100.1", "100.1a", "701", "701.1", "701.2",
             "701.2a", "702", "702.1", "702.2", "702.2a"},
            set(by_id),
        )
        self.assertTrue(
            all(row["short_summary"] is None for row in parsed["rules"])
        )
        self.assertTrue(
            all(
                row["coverage_status"] == "unclassified"
                for row in parsed["rules"]
            )
        )
        self.assertEqual(
            {"activate", "flying"},
            {row["term_id"] for row in parsed["glossary"]},
        )
        mechanic_ids = {
            row["mechanic_id"] for row in parsed["mechanics"]
        }
        self.assertIn("activate", mechanic_ids)
        self.assertIn("flying", mechanic_ids)

    def test_sync_writes_compact_derived_files_and_verifies_raw_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.txt"
            source.write_text(RULES_FIXTURE, encoding="utf-8")
            result = sync_rules_corpus(
                root,
                source_file=source,
            )
            self.assertTrue(result["ok"])
            for relative in (
                "rules/manifest.json",
                "rules/rule-index.json",
                "rules/glossary-index.json",
                "rules/mechanic-index.json",
                "rules/dependency-graph.json",
                "mechanics/registry.json",
                "coverage/rules-coverage.json",
                "coverage/rules-coverage.md",
                "coverage/mechanics-coverage.json",
                "coverage/mechanics-coverage.md",
            ):
                self.assertTrue((root / relative).is_file(), relative)

            derived = (root / "rules/rule-index.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(
                "Behavioral source text that must never enter",
                derived,
            )
            inventory = rules_inventory(root)
            self.assertEqual(11, inventory["rules"])
            coverage = rules_coverage(root)
            self.assertFalse(coverage["current_snapshot_complete"])
            self.assertEqual(11, coverage["status_counts"]["unclassified"])
            verification = verify_rules_corpus(root)
            self.assertTrue(verification["ok"], verification["errors"])
            self.assertTrue(verification["raw_source_verified"])
            mechanic_coverage = json.loads(
                (root / "coverage/mechanics-coverage.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(5, mechanic_coverage["total_mechanics"])
            self.assertFalse(
                mechanic_coverage["current_snapshot_complete"]
            )

            first_manifest = (
                root / "rules/manifest.json"
            ).read_bytes()
            sync_rules_corpus(root, source_file=source)
            second_manifest = (
                root / "rules/manifest.json"
            ).read_bytes()
            second_delta = (
                root / "coverage/rules-delta.json"
            ).read_bytes()
            sync_rules_corpus(root, source_file=source)
            self.assertEqual(
                first_manifest,
                second_manifest,
            )
            self.assertEqual(
                second_delta,
                (root / "coverage/rules-delta.json").read_bytes(),
            )

    def test_diff_detects_changed_and_renumbered_rules(self):
        old = parse_comprehensive_rules(
            RULES_FIXTURE,
            source_sha256="a" * 64,
        )
        new_text = RULES_FIXTURE.replace(
            "100.1. Behavioral source text that must never enter the derived index.",
            "100.1. Changed behavioral source text.",
        ).replace(
            "100.1a A dependent subrule used by the parser test.",
            "100.1b A dependent subrule used by the parser test.",
        )
        new = parse_comprehensive_rules(
            new_text,
            source_sha256="b" * 64,
        )
        delta = compare_rule_indexes(
            {
                "effective_date": "2026-06-19",
                "source_sha256": "b" * 64,
                "rules": new["rules"],
            },
            {
                "effective_date": "2026-06-19",
                "source_sha256": "a" * 64,
                "rules": old["rules"],
            },
        )
        self.assertIn("100.1", delta["changed_rule_ids"])
        self.assertIn("100.1b", delta["added_rule_ids"])
        self.assertIn("100.1a", delta["removed_rule_ids"])
        self.assertEqual(
            [{"from": "100.1a", "to": "100.1b",
              "text_sha256": old["rules"][2]["text_sha256"]}],
            delta["renumbered_rules"],
        )
        self.assertTrue(delta["requires_review"])

    def test_sync_pins_available_oracle_and_rulings_bulk_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.txt"
            oracle = root / "oracle.jsonl.gz"
            rulings = root / "rulings.jsonl.gz"
            database = root / "cards.sqlite3"
            source.write_text(RULES_FIXTURE, encoding="utf-8")
            oracle.write_bytes(b"oracle-snapshot")
            rulings.write_bytes(b"rulings-snapshot")
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)"
            )
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                [
                    ("schema_version", "1"),
                    ("oracle_source", str(oracle)),
                    ("rulings_source", str(rulings)),
                    ("card_count", "123"),
                    ("ruling_count", "456"),
                    ("scryfall_oracle_updated_at", "oracle-time"),
                    ("scryfall_rulings_updated_at", "rulings-time"),
                ],
            )
            connection.commit()
            connection.close()

            sync_rules_corpus(
                root,
                source_file=source,
                card_db_path=database,
            )
            manifest = json.loads(
                (root / "rules/manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            snapshot = manifest["card_data_snapshot"]
            self.assertTrue(snapshot["available"])
            self.assertEqual(
                hashlib.sha256(b"oracle-snapshot").hexdigest(),
                snapshot["oracle_bulk"]["sha256"],
            )
            self.assertEqual(
                "oracle-time",
                snapshot["oracle_bulk"]["updated_at"],
            )
            self.assertEqual(
                456,
                snapshot["rulings_bulk"]["ruling_count"],
            )

    def test_cli_sync_inventory_verify_and_report_use_local_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.txt"
            report = root / "rules-report.md"
            source.write_text(RULES_FIXTURE, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    0,
                    main(
                        [
                            "rules",
                            "sync",
                            "--root",
                            str(root),
                            "--source-file",
                            str(source),
                        ]
                    ),
                )
            synced = json.loads(output.getvalue())
            self.assertTrue(synced["ok"])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    0,
                    main(["rules", "inventory", "--root", str(root)]),
                )
            self.assertEqual(11, json.loads(output.getvalue())["rules"])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    0,
                    main(["rules", "verify", "--root", str(root)]),
                )
            self.assertTrue(json.loads(output.getvalue())["ok"])

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "rules",
                            "report",
                            "--root",
                            str(root),
                            "--output",
                            str(report),
                        ]
                    ),
                )
            self.assertIn(
                "Pinned-snapshot completeness: blocked",
                report.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
