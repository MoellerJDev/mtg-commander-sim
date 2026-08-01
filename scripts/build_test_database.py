from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mtg_commander_sim.carddb import CardDatabase, CardRecord, build_card_database
from mtg_commander_sim.deck import DeckLoader
from mtg_commander_sim.util import stable_json


def _card_payload(card: CardRecord) -> dict:
    return {
        "oracle_id": card.oracle_id,
        "name": card.name,
        "mana_cost": card.mana_cost,
        "cmc": card.mana_value,
        "type_line": card.type_line,
        "oracle_text": card.oracle_text,
        "power": card.power,
        "toughness": card.toughness,
        "loyalty": card.loyalty,
        "defense": card.defense,
        "colors": list(card.colors),
        "color_identity": list(card.color_identity),
        "keywords": list(card.keywords),
        "produced_mana": list(card.produced_mana),
        "layout": card.layout,
        "released_at": card.released_at,
        "legalities": card.legalities,
        **({"card_faces": list(card.faces)} if card.faces else {}),
    }


def export_fixture(
    source_db: Path,
    output: Path,
    deck_paths: list[Path],
    extra_names: list[str],
) -> dict:
    with CardDatabase(source_db) as db:
        loader = DeckLoader(db)
        names = set(extra_names)
        for deck_path in deck_paths:
            deck = loader.load(deck_path)
            names.update(
                entry.name
                for entry in deck.entries
                if entry.board in {"mainboard", "commander"}
            )
        cards = {
            card.oracle_id: card
            for card in (db.lookup(name) for name in sorted(names))
        }
        rulings = [
            {
                "oracle_id": ruling.oracle_id,
                "published_at": ruling.published_at,
                "source": ruling.source,
                "comment": ruling.comment,
            }
            for card in cards.values()
            for ruling in db.rulings(card)
        ]
    payload = {
        "schema_version": 1,
        "fixture_kind": "public_exact-list_card_data",
        "source": "Scryfall Oracle/rulings subset for offline tests",
        "cards": [
            _card_payload(card)
            for card in sorted(cards.values(), key=lambda value: value.name)
        ],
        "rulings": sorted(
            rulings,
            key=lambda value: (
                value["oracle_id"],
                value["published_at"],
                value["comment"],
            ),
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(stable_json(payload) + "\n", encoding="utf-8")
    return {
        "output": str(output),
        "cards": len(payload["cards"]),
        "rulings": len(payload["rulings"]),
    }


def build_fixture_database(
    fixtures: Path | list[Path], output: Path
) -> dict:
    fixture_paths = [fixtures] if isinstance(fixtures, Path) else fixtures
    cards_by_oracle: dict[str, dict] = {}
    oracle_by_name: dict[str, str] = {}
    ruling_rows: list[dict] = []
    for fixture in fixture_paths:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError(
                f"Unsupported public card fixture schema: {fixture}"
            )
        for card in payload.get("cards", []):
            oracle_id = str(card.get("oracle_id") or "")
            name = str(card.get("name") or "")
            if not oracle_id or not name:
                raise ValueError(f"Card fixture entry is missing identity: {fixture}")
            existing = cards_by_oracle.get(oracle_id)
            if existing is not None and existing != card:
                raise ValueError(
                    f"Conflicting card fixture for Oracle ID {oracle_id}"
                )
            named_oracle = oracle_by_name.get(name.casefold())
            if named_oracle is not None and named_oracle != oracle_id:
                raise ValueError(f"Conflicting card fixture name: {name}")
            cards_by_oracle[oracle_id] = card
            oracle_by_name[name.casefold()] = oracle_id
        # Preserve multiplicity. Scryfall can publish text-identical ruling
        # rows, and reviewed semantic provenance hashes that exact multiset.
        ruling_rows.extend(payload.get("rulings", []))
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        oracle_path = work / "oracle-cards.jsonl"
        rulings_path = work / "rulings.jsonl"
        oracle_path.write_text(
            "".join(
                json.dumps(card, sort_keys=True, separators=(",", ":")) + "\n"
                for card in sorted(
                    cards_by_oracle.values(),
                    key=lambda value: (value["name"], value["oracle_id"]),
                )
            ),
            encoding="utf-8",
        )
        rulings_path.write_text(
            "".join(
                json.dumps(ruling, sort_keys=True, separators=(",", ":")) + "\n"
                for ruling in sorted(
                    ruling_rows,
                    key=lambda value: (
                        str(value.get("oracle_id") or ""),
                        str(value.get("published_at") or ""),
                        str(value.get("source") or ""),
                        str(value.get("comment") or ""),
                    ),
                )
            ),
            encoding="utf-8",
        )
        result = build_card_database(
            oracle_path,
            rulings_path,
            output,
            overwrite=True,
        )
    result["fixture"] = str(fixture_paths[0])
    result["fixtures"] = [str(fixture) for fixture in fixture_paths]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export or build the compact, public CI card-data fixture."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export")
    export.add_argument("--source-db", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--deck", action="append", type=Path, default=[])
    export.add_argument("--extra-card", action="append", default=[])

    build = subparsers.add_parser("build")
    build.add_argument(
        "--fixture", required=True, action="append", type=Path
    )
    build.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "export":
        deck_paths = args.deck or [
            ROOT / "examples" / "mishra-eminent-one.txt",
            ROOT / "examples" / "zimone-and-dina.txt",
        ]
        result = export_fixture(
            args.source_db,
            args.output,
            deck_paths,
            args.extra_card,
        )
    else:
        result = build_fixture_database(args.fixture, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
