---
title: "Codex project instructions"
status: "current"
authoritative_source: "repository contribution and architecture policy"
verified: "2026-08-02"
audience: "Codex agents and contributors"
maintenance: "hand-maintained"
---

# Codex project instructions

## Browser ownership and headless testing

- Treat every system-browser window and Codex in-app browser as user-owned
  state. Never open, reuse, focus, or navigate a visible browser during agent
  work unless the user explicitly requests visible browser interaction in that
  same task. A prior request, an already-open browser, or a running localhost
  listener is not authorization.
- Starting a listener such as `127.0.0.1:18080` is test infrastructure only.
  It must not launch or navigate a browser. Probe HTTP endpoints with a CLI
  client and run UI checks in an isolated headless Playwright browser.
- Agent-driven server checks must use `python -m server --no-open`; never run a
  bare `python -m server`, pass `--open`, invoke `webbrowser`, use an OS
  browser-launch command, or use a browser-control tool unless the user has
  explicitly requested an interactive/manual browser session.
- Keep Vite `open: false` and HTML reporters configured with `open: "never"`.
  Stop server processes started for an automated check when the check ends.

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

## Current architecture program

The repository is migrating incrementally from the current centralized engine
to domain-owned rules modules. Follow the ordered phases recorded in the active
project objective; do not use a feature request as permission for a big-bang
rewrite.

- Phase 1 runtime trust/default-deny governance is integrated on certified
  `main`. Its explicit evidence, trust/closure, component
  binding, performance, and architecture ratchets are current policy.
- Certified `main` integrates the typed `tap`, `untap`, and
  `untap_all_creatures`
  migration through a dedicated semantic family and the classified
  `tap_state.py` mutation port, with a negative engine delta and exact
  rollback/replay/mutation evidence.
- Keep those capabilities tested and blocked until complete tap/untap
  prohibitions, universal replacement participation, and effective-characteristic
  closure are represented. Do not widen this slice into broad Oracle grammar,
  a new card family, or numerical Comprehensive Rules traversal.
- Certified `main` integrates the dependency-ordered behavioral-rules
  scheduler. Its generated queue must conservatively cover
  every reviewed blocked behavioral rule and every unclassified nonpassing
  rule exactly once. Select subsystem batches from that queue; do not resume
  numerical rule traversal.
- Certified `main` includes immutable nested replacement-event trees,
  seat-scoped replayable replacement ordering, and focused token/zone mutation
  boundaries. CR 616.1g is promoted only for represented containing-before-
  contained behavior; broader CR 614/616 remains blocked.
- Certified `main` includes the focused counter-placement prepare/commit owner
  for represented effect-generated permanent counters and fixed integral
  quantity-replacement descriptors. Entry counters, player counters, costs,
  rule actions, and continuation-sensitive legacy producers remain blocked.
- The active bounded slice is `rules/damage-result-events`. It delegates final
  dealt components to immutable affected-subject CR 120.3 result trees, resolves
  represented containing and contained replacements, and commits one validated
  mutation plan. Generic represented Infect, Wither, Lifelink, and fixed Toxic
  outcomes plus fixed life-gain multiplication and a whole-result life floor
  are in scope. Keep persistent shields, redirection, non-damage
  transformations, dynamic Toxic, unrepresented source LKI/ability grants,
  remaining result-replacement families, and resumable replacement choices
  during mana payment explicitly blocked.
- The generated post-merge queue selects the dependency-ready CR 210.1 Battle
  defense-characteristic/entry batch. Do not implement it on the damage-result
  branch; begin it only after this branch is certified and merged.
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
