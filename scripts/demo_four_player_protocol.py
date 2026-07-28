from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mtg_commander_sim import (
    CardDatabase,
    CommanderSession,
    DeckLoader,
    ProjectedClientView,
    StateProjector,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/scryfall-20260728-compact.sqlite3")
    parser.add_argument("--out", default="demo")
    parser.add_argument("--seed", type=int, default=20260728)
    args = parser.parse_args()

    root = ROOT
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = root / db_path
    db = CardDatabase(db_path)
    try:
        loader = DeckLoader(db)
        mishra = loader.load(root / "examples/mishra-eminent-one.txt", commander="Mishra, Eminent One")
        zimone = loader.load(root / "examples/zimone-and-dina.txt", commander="Zimone and Dina")
        session = CommanderSession.create(
            db,
            {"A": mishra, "B": zimone, "C": mishra, "D": zimone},
            first_player="A",
            seed=args.seed,
        )
        client = ProjectedClientView("pilot:A")

        full = session.packet("pilot:A", full=True)
        client.ingest(full)
        unchanged = session.packet("pilot:A")
        client.ingest(unchanged)
        session.act("pilot:A", {"a": "mulligan"})
        after_declaration = session.packet("pilot:A")
        client.ingest(after_declaration)

        (out / "pilot-a-bootstrap.json").write_text(
            json.dumps(full, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out / "pilot-a-unchanged-delta.json").write_text(
            json.dumps(unchanged, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out / "pilot-a-after-declaration-delta.json").write_text(
            json.dumps(after_declaration, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        measures = {
            "bootstrap": StateProjector.measure(full),
            "unchanged_live_decision": StateProjector.measure(unchanged),
            "after_declaration": StateProjector.measure(after_declaration),
            "ratios": {
                "unchanged_vs_bootstrap": round(
                    StateProjector.measure(unchanged)["compact_chars"]
                    / StateProjector.measure(full)["compact_chars"],
                    4,
                ),
                "declaration_vs_bootstrap": round(
                    StateProjector.measure(after_declaration)["compact_chars"]
                    / StateProjector.measure(full)["compact_chars"],
                    4,
                ),
            },
            "protocol": full["v"],
            "players": 4,
            "seed": args.seed,
        }
        (out / "token-benchmark.json").write_text(
            json.dumps(measures, indent=2), encoding="utf-8"
        )

        summary = f"""# Four-player protocol smoke test

- Protocol: `{full['v']}`
- Seats: A Mishra, B Zimone/Dina, C Mishra, D Zimone/Dina
- Initial pending principal: `pilot:A`
- After A declares a mulligan, the next principal is `{session.pending_principals()[0]}`.
  This demonstrates turn-order declarations rather than concurrent declarations.
- Pilot A still has seven cards until every player in the round has declared;
  redraws are applied together after the last declaration.
- Bootstrap estimate: {measures['bootstrap']['estimated_tokens']} tokens
- Repeated live-decision delta: {measures['unchanged_live_decision']['estimated_tokens']} tokens
- A's declaration delta: {measures['after_declaration']['estimated_tokens']} tokens
- Client reducer hash after the final packet: `{client.current_hash}`

The demo intentionally stops before B declares. It tests protocol routing,
least-privilege seat projection, turn-order mulligan input, hash-checked patches,
and token measurement without requiring card semantics.
"""
        (out / "SMOKE_TEST.md").write_text(summary, encoding="utf-8")
        print(json.dumps(measures, indent=2))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
