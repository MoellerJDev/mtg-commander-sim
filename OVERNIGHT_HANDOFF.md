# Integration handoff

Last updated: 2026-07-31

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data.

## Repository state

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Integrated commit: the `main` commit containing this document
- Package: `0.8.0`
- Tags: `v0.6.0`, `v0.7.0`
- No release tag was created for this integration checkpoint.

PRs #1–#16, #24, and #25 are merged through ordinary merge commits. PR #24
was retargeted to `main` as the cumulative CR 400–408 candidate. Before
integration, Git ancestry proved that the exact heads of PRs #17–#23 were all
ancestors of the PR #24 head. After PR #24 reached `main`, those intermediate
PRs were closed as superseded; no intended commit was abandoned or
force-pushed.

Broad sequential rules review is frozen after CR 408. Do not create CR 409 or
another stacked rules-family branch before the server/browser vertical slice.

## Deterministic evidence

- 3,925 unit/integration tests pass on Windows Python 3.11.9.
- The combined focused CR 400–408 and CR 500–505 suite passes.
- All 3,300 pinned rule records and 425 mechanic records verify against the
  June 19, 2026 rules source.
- Conformance: 106 passing, 371 blocked, 80 definition-only, 2,743 unreviewed.
- Mechanics: 49 partial, 376 unclassified, 0 trusted.
- Full Oracle: 2,957 exact, 15,691 partial, 19,725 unresolved; 69,664 material
  residuals.
- Commander-legal Oracle: 338 exact, 14,354 partial, 16,930 unresolved;
  61,212 material residuals.
- Seed-20260730 opportunity/replay, deterministic four-player natural-winner,
  hidden-information projection, repository/history/security, protocol demo,
  wheel build, and clean-install checks pass.
- PR #24 received a fresh public GitHub Actions matrix on Python 3.11/3.12 and
  Ubuntu/Windows before merge. All repository jobs executed and passed.

GitHub Actions is operating normally. Historical zero-step billing failures
are not current evidence and no administrator bypass is authorized or needed.

Local tool availability:

- Python 3.11.9: available
- Python 3.12: not installed locally
- Node 24.18.0 and npm 11.16.0: available
- WSL2: not installed
- Docker: not installed

The public GitHub matrix supplies supported Python 3.11/3.12 and
Ubuntu/Windows coverage unavailable on this workstation.

## Product boundary

Implemented:

- authoritative deterministic `CommanderEngine`
- capability-scoped in-process `GameService`
- principal-specific projections and protocol 2.1 patches
- transactional legal actions and fail-closed semantic preflight
- exact Game Record v3 command replay
- trusted-only closure for the two pinned exact 100-card lists
- source-linked rules corpus, Oracle IR, mechanic contracts, and generated
  coverage

Not implemented:

- strict network command envelope with command/decision IDs and expected view
  revision
- idempotency repository
- single-writer `GameActor` and `GameManager`
- ASGI HTTP/WebSocket server
- guest identity, rooms, seats, readiness, and reconnect transport
- durable production persistence
- TypeScript browser client and four-context browser end-to-end test
- complete Comprehensive Rules or Oracle-corpus enforcement

Optional Codex/LLM adapters remain untrusted clients. They are not rules,
product, CI, merge, or release authorities.

## Next branch

Create `agent/server-browser-vertical-slice` directly from the final green
`main`, push it without product changes, and pause. When work resumes, implement
one coherent authoritative server/browser vertical slice on that branch. Do
not resume broad sequential CR review until that slice is tested and merged.

The first implementation work should begin with the strict network command
envelope, idempotency, expected revisions, and the single-writer `GameActor`;
the browser must use that same untrusted application boundary.
