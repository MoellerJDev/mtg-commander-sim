# Integration handoff

This handoff is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data.

## Repository

- Repository: private `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `agent/review-mvp`
- Current commit: the commit containing this handoff
- Review integration PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/2`
- Stacked rules PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/1`
- Package version: `0.8.0`
- Existing tags: `v0.6.0`, `v0.7.0`

`agent/review-mvp` is 30 commits ahead of `main`.
`agent/rules-completeness` is 29 commits ahead of `agent/review-mvp`.
`main` has no unique commit absent from `agent/review-mvp`.

## Active phase

Stage A integrates the deterministic review foundation into `main`. AI/Codex
pilot games, provider identity, token use, and model routing are retired as
product completion gates. Existing adapters remain optional untrusted clients.

The generated program ledger is
`docs/PLATFORM_IMPLEMENTATION_STATUS.md`. Its machine-readable source is
`platform/readiness-source.json`, and CI rejects stale generated output.

## Implemented foundation

- authoritative `CommanderEngine` and capability-scoped `GameService`
- principal-specific hidden-information projection
- versioned full/delta protocol with view hashes
- deterministic multiplayer turns, priority, mulligans, combat baseline,
  opportunity audit, and conservative yields
- server-issued legal actions, costs, target plans, and choices
- trusted-only exact-list semantic preflight for the two pinned regression
  lists
- Game Record v3 command journals, checkpoints, replay, and sanitized fixtures
- scripted, manual, and subprocess deterministic client adapters
- optional AI/Codex adapters isolated from product gates

No ASGI server, single-writer `GameActor`, durable production database,
migrations, rooms/accounts service, or browser client is implemented yet.

## Snapshot and coverage state

- Comprehensive Rules corpus: not present on this branch; implemented on the
  stacked `agent/rules-completeness` branch
- Oracle/rulings scope on this branch: sanitized July 28, 2026 exact-list
  fixture with source-pinned semantic programs
- Exact Zimone and Dina list preflight: 100 fully playable, 0 partial, 0
  unresolved
- Exact Mishra, Eminent One list preflight: 100 fully playable, 0 partial, 0
  unresolved
- Full Oracle and Comprehensive Rules completeness: not claimed

## Deterministic validation

- Discovered deterministic tests: generated in
  `coverage/platform-readiness.json`
- Complete Stage A local gate: 288 tests pass in 99.079 seconds
- Added deterministic full-game soak: a trusted-only four-player micro-pool
  reaches a natural winner, has zero incorrectly suppressed meaningful
  windows, passes seat projection, and exact command replay
- Four-player protocol demo: pass
- Seed-20260730 opportunity/action-exposure regression: pass
- Repository/history/secret/capability/large-object scans: pass
- Wheel build, clean install, imported version, and CLI smoke: pass
- Baseline exact-SHA CI:
  `https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30560259007`
  across Python 3.11/3.12 on Ubuntu and Windows

The final integration-change local gate passed. Exact-SHA CI remains pending
until the current coherent diff is committed and pushed. Do not infer it from
the baseline.

## Evidence boundaries

- The deterministic micro-pool is rules-runtime evidence, not Commander deck
  legality, deck quality, or matchup evidence.
- Duplicate-list fixtures are never matchup evidence.
- Exact-list semantic closure is not Oracle-corpus completeness.
- Optional AI/Codex histories are adapter characterization only.
- No deck list was changed.

## Current blockers

- PR #2 has not yet passed final exact-SHA CI and merged into `main`.
- PR #1 remains stacked on `agent/review-mvp`.
- The browser/server/persistence product layers are not yet implemented.
- Comprehensive Rules and Commander-legal Oracle trust gates remain incomplete.

## Exact next command

Commit and push the coherent Stage A integration update, update PR #2 with the
tested SHA and evidence, and verify exact-SHA CI.

After PR #2 merges, merge updated `main` into `agent/rules-completeness` with an
ordinary merge commit, regenerate coverage/status artifacts, retarget PR #1 to
`main`, and run the expanded rules gate.
