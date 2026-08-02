---
title: "Codex project instructions"
status: "current"
authoritative_source: "repository contribution and architecture policy"
verified: "2026-08-01"
audience: "Codex agents and contributors"
maintenance: "hand-maintained"
---

# Codex project instructions

## Nonnegotiable boundaries

- `CommanderEngine` is authoritative. Never let a pilot mutate zones, life, mana, stack, counters, or effects directly.
- Every player command must be authorized by an unconsumed capability issued to that authenticated principal.
- Only the arbiter may submit generic effects, and only while holding an `arbiter.resolve` capability.
- Hidden information must be projected by principal. Never solve a UI issue by exposing full state.
- No Scryfall network calls during a game. Use local SQLite data.
- Unknown Oracle semantics must fail into an arbiter decision; never guess silently.
- Rules/Oracle completeness is snapshot-scoped. Pin CR, Oracle, rulings,
  compiler, mechanic-contract, and semantic hashes before promoting coverage.
- A material typed-Oracle compiler residual or untrusted mechanic dependency
  must fail trusted preflight; never discard unsupported Oracle text.
- A yield is an optimization, never authority to suppress a changed meaningful-action signature. `suppressed_meaningful_windows` must remain zero.
- Pilots select server-advertised ability/cost options. Never restore arbitrary `declared_cost`, `cost_effects`, or uncompiled cast-from-zone input in strict mode.
- Treat `principal` as authenticated transport metadata, never as a seat chosen inside a client command body.
- Keep public protocol objects JSON-serializable, versioned, and hash-resynchronizable.
- The realistic mulligan guard is policy, not a Magic rule; preserve the distinction.
- Codex arena pilots use only their fixed-seat tool surface. Never give a pilot a run path to inspect, another seat's packet/memory, a raw capability, or authoritative checkpoint.
- The primary Codex task may arbitrate public rules context but must never choose a strategic seat action or silently repair a legal poor choice.
- Never label provider/model/thread identity as observed unless it came from an actual invocation. Preserve `null` when the platform does not expose a value.
- Never promote a duplicated-deck fixture or a run with incomplete material semantics to matchup evidence.
- Semantic choices that suspend resolution must persist a versioned,
  replayable frame. Private search candidates go only to the searching seat;
  public records must not reveal a nonrevealed result moved to hand.
- Record summaries and provider counters are derived from journals. Never
  upgrade recorded provider/model identity to verified by inference, and never
  describe accepted-prefix replay as a completed game.
- Product gameplay, rules enforcement, CI, merge gates, and releases must not
  require an LLM, Codex runtime, provider credential, or live AI ruling. An AI
  client is optional and has no authority beyond the ordinary projected client
  protocol.
- Do not spend product slices improving AI strategy, model routing, prompts, or
  provider sessions. Keep existing provider-specific adapters isolated from the
  authoritative rules and application layers.
- Automated checks must never open or drive a contributor's system browser or
  the Codex in-app browser. Run Playwright in its isolated headless browser,
  start `python -m server` with `--no-open`, keep Vite `open: false`, and keep
  HTML reporters configured with `open: "never"`. Only launch a visible browser
  when the user explicitly asks for an interactive/manual browser session.
- Agent-driven server or UI checks must not run bare `python -m server`, invoke
  `webbrowser`, use an OS browser-launch command, or navigate/focus the Codex
  in-app browser. A listener such as `127.0.0.1:18080` is test infrastructure,
  not permission to open a visible tab. Use `python -m server --no-open` and
  headless Playwright, then stop any server process started for the check. This
  restriction applies even when a visible browser is already open for unrelated
  user work; explicit user authorization is required for every visible-browser
  session.
- The server is intentionally non-opening by default. `python -m server --open`
  is a user-facing convenience and agents must never pass `--open` unless the
  user explicitly requests a visible browser launch in that same task. Printing
  or probing a localhost URL does not authorize navigation to it.

## Current architecture program

The repository is migrating incrementally from the current centralized engine
to domain-owned rules modules. Follow the ordered phases recorded in the active
project objective; do not use a feature request as permission for a big-bang
rewrite.

- Phase 1 runtime trust/default-deny governance is integrated on certified
  `main` through PR #60. Its explicit evidence, trust/closure, component
  binding, performance, and architecture ratchets are current policy.
- Certified `main` integrates the typed `tap`, `untap`, and
  `untap_all_creatures`
  migration through a dedicated semantic family and the classified
  `tap_state.py` mutation port, with a negative engine delta and exact
  rollback/replay/mutation evidence.
- Keep those capabilities tested and blocked until complete tap/untap
  prohibitions, general replacement ordering, and effective-characteristic
  closure are represented. Do not widen this slice into broad Oracle grammar,
  a new card family, or numerical Comprehensive Rules traversal.
- The active rules-first planning branch is
  `feat/rules-dependency-scheduler`. Its generated queue must conservatively
  cover every reviewed blocked behavioral rule and every unclassified
  nonpassing rule exactly once. Select subsystem batches from that queue; do
  not resume numerical rule traversal.
- Preserve Game Record v3 commands, exact replay, principal projections, and
  fail-closed semantics during every extraction.
- Do not add printed-card-name or Oracle-ID conditionals, card-named semantic
  operations, or card-specific helpers to the universal engine.
- A production module above 1,500 logical lines or a function above 150 logical
  lines is measured debt and requires the documented review path for new growth.

The machine-readable baseline is `coverage/architecture-audit.json`; its
generated presentations are `docs/ARCHITECTURE_DEBT_STATUS.md` and
`docs/COMPILER_COVERAGE_STATUS.md`. Hand-maintained documents must link to those
figures rather than copying them.

## Before committing

```bash
python -m compileall -q mtg_commander_sim tests scripts simctl.py
python scripts/build_test_database.py build \
  --fixture tests/fixtures/scryfall-exact-lists.json \
  --fixture tests/fixtures/browser-lifecycle-cards.json \
  --output data/test-ci.sqlite3
# Set MTG_CARD_DB=data/test-ci.sqlite3 for the remaining commands.
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/update_capability_evidence.py --check
python scripts/update_rules_scheduler.py --check
python scripts/update_module_classifications.py --check
python scripts/benchmark_continuous_effects.py --check
python scripts/demo_four_player_protocol.py --db data/test-ci.sqlite3 --out demo
python scripts/update_platform_status.py --check
python scripts/update_architecture_audit.py --check
python scripts/validate_architecture.py --check
python scripts/validate_documentation.py --check
python scripts/validate_repository.py
python simctl.py rules verify --root .
python -m build --wheel
python scripts/verify_wheel.py
cd web
npm ci
npm run generate:types
npm run typecheck
npm run build
npm run e2e
```

Set `MTG_CARD_DB` when the database is outside `data/`.
Never stage `run/`, a SQLite database, a raw deck cache, a capability-bearing
packet, or a live Game Record. Regression records must be generated in a
temporary directory from sanitized recipes.

## Before merging

Run the reusable gate from a clean, committed branch:

```bash
python scripts/local_merge_gate.py \
  --expected-branch <branch> \
  --expected-sha <full-sha>
```

It orchestrates the commands above plus the focused opportunity, replay,
privacy, deterministic four-player, protocol-demo, dependency, and clean-exit
checks. Its logs and summary stay under ignored
`local/merge-gates/<full-sha>/`.

## Architecture tests required

Changes touching turns, priority, combat, state-based actions, mulligans, permissions, projection patches, or semantic resolution require regression tests.

Changes touching legal-action generation or yields also require opportunity
journal assertions, a zero-suppression check, and exact replay of the
seed-20260730 fixture.

For a new client feature:

1. reuse or add a capability action
2. project data only to principals that need it
3. update protocol schema and reducer tests
4. keep transport logic out of `CommanderEngine`
5. preserve one ephemeral projection cursor per network connection
6. derive the principal from authenticated room membership, never request JSON

For new card semantics:

1. prefer generic DSL operations
2. use runtime placeholders rather than physical object IDs
3. delegate strategic player choices
4. include a deterministic rules test
5. do not hard-code a deck name or commander into the kernel
6. add anchored whole-text templates to `oracle_ir.py`, preserving unmatched
   material text as a residual
7. keep generated programs provisional until every mechanic dependency has a
   trusted contract
8. add positive, negative, runtime, mutation, and source-hash tests

Put reusable CR 613 operations in `continuous_effects.py` and CR 616 event
transformations in `replacement_effects.py`. Record evidence and blockers in a
versioned mechanic contract, regenerate the registry, and verify the pinned
rules corpus.

## Performance targets

- After bootstrap, routine packets should usually remain below 1,000 estimated input tokens.
- Empty known priority windows should make no model call.
- A repeated live decision without a state change should stay below 400 estimated tokens.
- Prefer automatic transitions, yields, and semantic caching over more model calls.
- Preserve patch hash validation; never trade correctness for a smaller unverified delta.
