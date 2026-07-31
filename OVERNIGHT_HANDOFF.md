# Integration handoff

Last updated: 2026-07-31

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data.

## Repository and integration state

- Repository: private `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `agent/cr-509-declare-blockers`
- Stage A merge commit on `main`:
  `bd89201be44de85aa9b85fcc9f0baacb0ee76dbe`
- Stage A PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/2`
- Rules PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/1`
- Package version: `0.8.0`
- Existing tags: `v0.6.0`, `v0.7.0`

PR #2, PR #1, and focused CR 512/511/510 PRs #3-5 passed their exact-SHA
matrices and merged into `main` through ordinary merge commits. Main commit
`5a7d87840cf0615f14b03ac76bb3eeaa9f738ed5` then passed run 30608853469.

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

Current reviewed inventory after the CR 509 synchronization:

- 357 reviewed cases
- 53 executable semantic passes
- 249 reviewed blocked cases
- 55 definition-only cases
- 2,943 unreviewed inventory cases
- 425 discovered mechanics
- 32 partial/untrusted mechanic contracts
- 393 unclassified mechanics
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

The focused CR 509 local test gate passed atop the green CR 510 baseline:

- generated platform, rules, mechanics, and Oracle status checks
- all noninventory and all generated per-rule tests
- seed-20260730 opportunity/replay/privacy regression
- deterministic four-player natural-winner soak
- protocol demo and packet benchmark
- repository/history/secret/artifact scans
- wheel build, clean installation, imported version, and CLI smoke
- the five focused CR 509 declaration/rollback/lifetime/replay tests
- exact-SHA four-job GitHub Actions for the focused commit remains pending
  until push

The local test gate ran 3,810 tests in 214.354 seconds, verified all 3,300 pinned
rules cases and 425 mechanics, checked 14 schemas and repository history,
completed the protocol demo, and built and clean-installed the wheel. The
four-player natural-winner soak exact-replayed after eliminating insertion-order
dependence from authoritative zone timestamps. The repository scan covered 253
tracked files and 11,259,832 bytes. Main commit
`5a7d87840cf0615f14b03ac76bb3eeaa9f738ed5` already passed run 30608853469;
no exact-SHA CI pass is claimed for the focused commit until it is pushed.

## Evidence boundaries

- Source linkage for every rule is not behavioral correctness for every rule.
- Exact-list semantic closure is not Oracle-corpus completeness.
- The micro-pool soak is rules-runtime/protocol evidence, not Commander
  format-legality, deck quality, or matchup evidence.
- Duplicate-list fixtures are never matchup evidence.
- No deck list was changed.

## Exact next step

Publish the green CR 509 focused branch and wait for its exact-SHA matrix.
CR 509.1a, 509.1g, and 509.2 may be claimed for the represented ordinary
declaration boundary; the remaining CR 509 records retain their dependencies.
