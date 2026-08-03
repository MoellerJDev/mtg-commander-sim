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
- Agent-driven server checks must use
  `.\.venv\Scripts\python.exe -m server --no-open`; never run a bare server
  command, pass `--open`, invoke `webbrowser`, use an OS
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

- Certified `main` is CPython 3.12-only and integrates shared immutable casting
  and activation proposal builders. Action advertisement and command execution
  must continue to rebuild the same legality/cost proposal; do not return
  casting, activation, or payment legality to `CommanderEngine`.
- Certified `main` includes default-deny runtime trust, the dependency-ordered
  behavioral-rules scheduler, immutable nested replacement trees, typed
  replacement operations, physical commander designation identity, canonical
  damage results, durable prevention/redirection state, and focused token,
  zone, counter, life, and damage mutation owners. Generated reports, rather
  than branch chronology, are the source of current counts.
- Merged main through PR 79 includes the bounded
  `rules/damage-prevention-continuations-and-aftermath` slice: typed dynamic,
  divided, and per-object shields; seat-scoped source selection with
  physical/LKI pinning; transactional prevention-dependent life/counter
  aftermath; same-chooser ordering; mana-payment continuation; and the narrow
  damage-modifier and life runtime families. The generic Oracle IR v20
  correction preserves fixed independent post-prevention instructions as
  ordered siblings and routes immediate life through the canonical
  replacement-capable owner; one strict ObjectQuerySpec now owns represented
  chosen-source validation from compiler through replay and damage-time recheck.
- The active prevention-trigger branch represents closed CR 615.13 results as
  immutable waiting trigger occurrences with exact prevented-amount aggregation,
  source/controller LKI, ordinary APNAP stack placement, represented target
  choice, and exact replay. Nested triggered damage reenters the canonical
  transaction through a narrow typed port. Keep explicit-target or mixed
  immediate aftermath, broader conditional trigger results, and unsupported
  recursive loops fail-closed.
- Keep complete CR 609.7a source categories, permanent-spell continuity,
  broader source-property predicates, general replacement-capable life gain,
  life-gain prevention, remaining prevention-aftermath wording,
  partial/attached redirection,
  non-damage transformations, unresolved dynamic Toxic values, and broader CR
  614/615/616 closure explicitly blocked until their complete dependencies and
  evidence exist.
- The merged infrastructure phase establishes a two-slot development pipeline,
  deterministic change-impact quick gates, balanced PR shards, a stable
  certification context, compact `main` smoke, and deep nightly assurance.
  After the active CR 615.13 batch certifies, the corpus-ranked next family is
  canonical fixed life results plus simple targetless enter/death trigger event
  binding and lowering. Do not resume numerical rule traversal or open a
  status-only follow-up.
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

## Development and certification workflow

Use only the ignored worktree-local CPython 3.12 environment. Do not rely on a
global `python` alias. Keep one branch in GitHub certification while developing
the next independent branch in a second worktree; never mix changes between
the two slots. The complete commands, recovery procedure, and shard ownership
live in [the CI pipeline guide](docs/development/ci-pipeline.md).

During development, run the new tests and adjacent impacted modules. Before
committing an ordinary change, run the deterministic quick gate:

```powershell
.\.venv\Scripts\python.exe scripts/quick_gate.py
```

The quick gate classifies committed and working-tree paths, builds the compact
offline database when needed, compiles Python, runs affected test modules or
functional shards, and invokes relevant generated, architecture, rules,
repository, package, or browser-build checks. Inspect its plan with
`--dry-run`. It never starts a visible browser and does not run browser E2E
locally.

The public pull-request workflow is the normal certification authority. It
runs ten balanced Linux functional shards plus generated/architecture,
package, Windows-compatibility, and isolated headless-browser jobs. Every
required dependency feeds the stable `PR / Certification` result; protect
`main` with that exact context. Do not enable auto-merge until the protection
is confirmed, because GitHub otherwise treats the merge as immediately
eligible.

`scripts/local_merge_gate.py` remains available for releases and unusually
high-risk persistence, replay, privacy, or packaging changes. It is not the
default iteration gate for every rules PR. Complete Windows, browser, property,
mutation, security, and current-corpus depth also runs on the nightly workflow.

Set `MTG_CARD_DB` when the database is outside `data/`. Never stage `run/`, a
SQLite database, a raw deck cache, a capability-bearing packet, or a live Game
Record. Regression records must be generated in a temporary directory from
sanitized recipes.

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

Put reusable CR 613 operations in `continuous_effects.py`. Put CR 614-616
immutable models, typed operations, applicability, ordering, and replay logic
under `mtg_commander_sim/replacement/`; `replacement_effects.py` is only the
narrow compatibility facade. Record evidence and blockers in a versioned
mechanic contract, regenerate the registry, and verify the pinned rules corpus.

## Performance targets

- After bootstrap, routine packets should usually remain below 1,000 estimated input tokens.
- Empty known priority windows should make no model call.
- A repeated live decision without a state change should stay below 400 estimated tokens.
- Prefer automatic transitions, yields, and semantic caching over more model calls.
- Preserve patch hash validation; never trade correctness for a smaller unverified delta.
