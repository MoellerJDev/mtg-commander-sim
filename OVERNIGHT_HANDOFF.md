# Integration handoff

Last updated: 2026-07-30

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data.

## Repository and integration state

- Repository: private `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `agent/rules-completeness`
- Stage A merge commit on `main`:
  `bd89201be44de85aa9b85fcc9f0baacb0ee76dbe`
- Stage A PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/2`
- Rules PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/1`
- Package version: `0.8.0`
- Existing tags: `v0.6.0`, `v0.7.0`

PR #2 passed both exact-SHA four-job CI matrices and merged into `main` with an
ordinary merge commit. Stage B merges that updated `main` into
`agent/rules-completeness`, regenerates the combined platform/rules ledgers,
retargets PR #1 to `main`, and verifies the combined branch before merge.

The unfinished CR 512 ending-phase draft is preserved outside the integration
worktree in the named stash
`wip/cr-512-ending-phase-before-stage-b-integration`. It must be recovered only
after the combined branch is green.

## Deterministic product boundary

The product is a deterministic server-authoritative Commander platform.
AI/Codex adapters are optional untrusted clients and are not product, CI,
merge, rules, or release gates. The server never delegates live legality or
rules authority to a model.

Implemented foundation:

- authoritative `CommanderEngine` and capability-scoped `GameService`
- principal-specific hidden-information projection
- versioned full/delta protocol with view hashes
- deterministic multiplayer turn, priority, mulligan, combat, opportunity,
  and conservative-yield machinery
- trusted-only semantic preflight and server-issued legal actions
- Game Record v3 commands, checkpoints, exact replay, and sanitized fixtures
- generated platform and rules coverage ledgers with stale-output checks

Not yet implemented:

- production ASGI/HTTP/WebSocket server
- single-writer `GameActor`
- durable production database and migrations
- rooms, accounts, reconnect, spectators, or browser client

## Rules checkpoint

The branch pins the Comprehensive Rules effective 2026-06-19 at SHA-256
`e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`.
It generates one source-linked conformance case for each of 3,300 numbered
rules and preserves reviewed status only while the source and rule-text hashes
remain unchanged.

Current reviewed inventory before the Stage B regeneration:

- 316 reviewed cases
- 44 executable semantic passes
- 222 reviewed blocked cases
- 50 definition-only cases
- 2,984 unreviewed inventory cases
- 425 discovered mechanics
- 28 partial/untrusted mechanic contracts
- 397 unclassified mechanics
- 0 corpus-wide trusted mechanics

Implemented reviewed families include narrow contracts for damage, defense,
Battles, state-based actions, replacement/prevention ordering, effects,
resolution, linked abilities, loyalty abilities, mana abilities, static and
triggered abilities, casting, activating abilities, end step, cleanup,
logical zone incarnations, timestamps, World, token/copy lifecycle, and
maximum counters. These are partial family implementations, not full rules
coverage.

Current full-Oracle coverage before regeneration:

- 38,373 total
- 2,957 exact
- 15,691 partial
- 19,725 unresolved
- 69,664 material residuals

Current Commander-legal Oracle coverage before regeneration:

- 31,622 total
- 338 exact
- 14,354 partial
- 16,930 unresolved
- 61,212 material residuals

## Validation state

Stage A exact evidence:

- 288/288 local tests passed in 99.079 seconds
- Python 3.11/3.12 on Ubuntu and Windows passed for exact SHA
  `ead8fa2eecfa79b989a741daa58e103347b45a66`
- generated platform status, schemas, repository/history/security scans,
  protocol demo, wheel build, clean install, version import, and CLI passed
- deterministic four-player micro-pool reached a natural winner with zero
  suppressed meaningful windows, passed seat projection, and exact-replayed

The combined Stage B local gate passed:

- generated platform, rules, mechanics, and Oracle status checks
- all noninventory and all generated per-rule tests
- seed-20260730 opportunity/replay/privacy regression
- deterministic four-player natural-winner soak
- protocol demo and packet benchmark
- repository/history/secret/artifact scans
- wheel build, clean installation, imported version, and CLI smoke
- exact-SHA four-job GitHub Actions remains pending until push

The local gate ran 3,788 tests in 184.335 seconds, verified all 3,300 pinned
rules cases and 425 mechanics, checked 14 schemas and repository history,
completed the protocol demo, and built and clean-installed the wheel. The
four-player natural-winner soak exact-replayed after eliminating insertion-order
dependence from authoritative zone timestamps. No exact-SHA CI pass is claimed
until the integration merge is pushed.

## Evidence boundaries

- Source linkage for every rule is not behavioral correctness for every rule.
- Exact-list semantic closure is not Oracle-corpus completeness.
- The micro-pool soak is rules-runtime/protocol evidence, not Commander
  format-legality, deck quality, or matchup evidence.
- Duplicate-list fixtures are never matchup evidence.
- No deck list was changed.

## Exact next step

Commit and push the ordinary Stage B integration merge, retarget PR #1 to
`main`, update its exact evidence, wait for exact-SHA CI, and merge. Recover the
CR 512 draft only after that integration completes.
