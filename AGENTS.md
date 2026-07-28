# Codex project instructions

## Nonnegotiable boundaries

- `CommanderEngine` is authoritative. Never let a pilot mutate zones, life, mana, stack, counters, or effects directly.
- Every player command must be authorized by an unconsumed capability issued to that authenticated principal.
- Only the arbiter may submit generic effects, and only while holding an `arbiter.resolve` capability.
- Hidden information must be projected by principal. Never solve a UI issue by exposing full state.
- No Scryfall network calls during a game. Use local SQLite data.
- Unknown Oracle semantics must fail into an arbiter decision; never guess silently.
- Pilots select server-advertised ability/cost options. Never restore arbitrary `declared_cost`, `cost_effects`, or uncompiled cast-from-zone input in strict mode.
- Treat `principal` as authenticated transport metadata, never as a seat chosen inside a client command body.
- Keep public protocol objects JSON-serializable, versioned, and hash-resynchronizable.
- The realistic mulligan guard is policy, not a Magic rule; preserve the distinction.

## Before committing

```bash
python -m compileall -q mtg_commander_sim tests scripts simctl.py
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/demo_four_player_protocol.py --out demo
```

Set `MTG_CARD_DB` when the database is outside `data/`.

## Architecture tests required

Changes touching turns, priority, combat, state-based actions, mulligans, permissions, projection patches, or semantic resolution require regression tests.

For a new client feature:

1. reuse or add a capability action
2. project data only to principals that need it
3. update protocol schema and reducer tests
4. keep transport logic out of `CommanderEngine`

For new card semantics:

1. prefer generic DSL operations
2. use runtime placeholders rather than physical object IDs
3. delegate strategic player choices
4. include a deterministic rules test
5. do not hard-code a deck name or commander into the kernel

## Performance targets

- After bootstrap, routine packets should usually remain below 1,000 estimated input tokens.
- Empty known priority windows should make no model call.
- A repeated live decision without a state change should stay below 400 estimated tokens.
- Prefer automatic transitions, yields, and semantic caching over more model calls.
- Preserve patch hash validation; never trade correctness for a smaller unverified delta.
