# Migration from MTG Duel Lab 0.1

## Why a rewrite was preferable

The earlier script proved that ChatGPT could reason through complex game lines while Python tracked zones. Its central abstraction, however, was an assisted two-player goldfish in which player choice, rules interpretation, state mutation, and reporting were too tightly coupled.

Adding two more players to that model would multiply priority calls and hidden-information problems while preserving manual bookkeeping. Version 0.2 keeps the local card database and deck loader but replaces the game/session architecture.

## Breaking changes

- Package name changes from `mtg_duel_lab` to `mtg_commander_sim`.
- Games use a `seat -> DeckDefinition` mapping rather than two fixed players.
- Every external action requires a live capability and authenticated principal.
- Player pilots cannot provide arbitrary resolution effects or activation costs.
- Explicit activated abilities use stable server-advertised ability IDs plus validated cost-object selections.
- Non-hand/non-command casting requires a compiled zone permission; a pilot cannot make a graveyard card castable by changing `from`.
- Rules arbitration is a separate role.
- Observations are per-principal projections.
- Protocol 2.1 uses a full bootstrap followed by hash-checked JSON patches.
- Extra turns and delayed triggers are state objects rather than notes.
- Mulligan declarations occur in turn order; redraw/bottom operations are grouped correctly.
- Four-player free mulligan and first-turn draw behavior are defaults.
- Combat declarations choose a defender for every attacker.
- Known-empty priority windows can skip model calls.
- Unknown card semantics route to an arbiter and may be cached.

## Reused components

- compact Scryfall SQLite schema
- Oracle/rulings lookup
- deck text parser
- Moxfield fetch/cache fallback
- Commander deck validation
- basic utility functions

## Save migration

Version 0.3 can inspect and migrate the 0.2 `game.json` monolith:

```bash
python simctl.py inspect-game run/live-duel/game.json --pretty
python simctl.py migrate-record run/live-duel/game.json \
  --output run/live-duel-v3 \
  --db data/scryfall-current.sqlite3
```

The old file lacks submitted command payloads, historical legal alternatives,
and decision rationale. Migration preserves its final authoritative snapshot,
normalizes events and available decision metadata, and labels replay mode
`legacy_snapshot`. Verification proves snapshot integrity only. It must not be
described as command replay or complete pilot evidence.

New games use Game Record v3. `checkpoint.json` omits event history and all raw
capability tokens; accepted commands, events, and decision attempts live in
separate JSONL journals. See `GAME_RECORD.md`.

## Recommended rollout

1. Run all architecture tests.
2. Verify protocol bootstrap/patch reduction with the bundled smoke test.
3. Compile semantics only for cards reached in actual games.
4. Run four isolated pilot contexts against one local service.
5. Track decisions, token input, action rejections, and arbiter misses.
6. Add semantics for the highest-frequency unresolved cards.
7. Only then begin large matchup batches.

Coverage driven by real games is more efficient than trying to hand-code every Oracle card before the architecture stabilizes.
