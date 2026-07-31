# Integration handoff

Last updated: 2026-07-31

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data.

## Repository and integration state

- Repository: private `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `agent/cr-405-stack`
- Stage A merge commit on `main`:
  `bd89201be44de85aa9b85fcc9f0baacb0ee76dbe`
- Stage A PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/2`
- Rules PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/1`
- Package version: `0.8.0`
- Existing tags: `v0.6.0`, `v0.7.0`

PR #2, PR #1, and focused CR 512/511/510/509/508/507/506 PRs #3-9
passed their exact-SHA matrices and merged into `main` through ordinary merge
commits. Main commit
`c8a52711dc9294957fc0f437a4aaeab72da213aa` then passed run 30615647165.
CR 505 PR #10 and CR 504 PR #11 are independent drafts. CR 503 PR #12 is the
dependency parent for CR 502 PR #13, which is the parent for CR 501 PR #14.
CR 500 PR #15 is a dependency-staged draft based on
`agent/cr-501-beginning-phase`; CR 405 PR #16 is based on CR 500. Their jobs
did not receive runners because
GitHub reported an account billing or spending-limit failure; those pre-run
failures are neither code passes nor code failures.

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

Current reviewed inventory after the CR 405 synchronization:

- 471 reviewed cases
- 71 executable semantic passes
- 334 reviewed blocked cases
- 66 definition-only cases
- 2,829 unreviewed inventory cases
- 425 discovered mechanics
- 40 partial/untrusted mechanic contracts
- 385 unclassified mechanics
- 0 corpus-wide trusted mechanics

Implemented reviewed families include narrow contracts for damage, defense,
Battles, state-based actions, replacement/prevention ordering, effects,
resolution, linked abilities, loyalty abilities, mana abilities, static and
triggered abilities, casting, activating abilities, stack, general turn structure,
beginning phase, untap,
upkeep, end step, cleanup,
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

The focused CR 405 local test gate passed atop the validated CR 500 dependency:

- generated platform, rules, mechanics, and Oracle status checks
- all noninventory and all generated per-rule tests
- seed-20260730 opportunity/replay/privacy regression
- deterministic four-player natural-winner soak
- protocol demo and packet benchmark
- repository/history/secret/artifact scans
- wheel build, clean installation, imported version, and CLI smoke
- the six focused CR 405 source/LIFO/priority/mana/state/leaving/replay tests

The local test gate ran 3,854 tests in 190.764 seconds, verified all 3,300 pinned
rules cases and 425 mechanics, checked 14 schemas and repository history,
completed the protocol demo, and built and clean-installed the wheel. The
seed-20260730 and four-player natural-winner regressions were independently
rerun with exact replay and zero suppressed meaningful windows. The repository
scan covered 277 tracked files and 11,590,147 bytes. Main commit
`c8a52711dc9294957fc0f437a4aaeab72da213aa` already passed run 30615647165;
CR 405 implementation commit
`c1621288eba73791f3ebcd7821173d283270705a` produced push run
30624094540 and pull-request run 30624097333. All eight jobs had
`runner_id=0`, zero steps, and GitHub's billing/spending-limit annotation. No
exact-SHA CI pass is claimed for the focused branches until their jobs receive
runners and pass.

## Evidence boundaries

- Source linkage for every rule is not behavioral correctness for every rule.
- Exact-list semantic closure is not Oracle-corpus completeness.
- The micro-pool soak is rules-runtime/protocol evidence, not Commander
  format-legality, deck quality, or matchup evidence.
- Duplicate-list fixtures are never matchup evidence.
- No deck list was changed.

## Exact next step

Keep dependency-staged CR 405 PR #16 in draft while GitHub Actions cannot
allocate runners, and begin CR 400 General zone identity. CR 405 passes only
top insertion, complete-pass LIFO resolution, direct effects, represented
static abilities, and represented state-action stack bypass. Stack-first
casting, complete simultaneous APNAP placement, stack characteristics,
triggered mana, special/turn-based actions, concession at any time, and
complete player-leaves-game ordering remain blocked. Do not merge or promote
those gaps.
