# Integration handoff

Last updated: 2026-07-31

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data.

## Repository state

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- `origin/main`: `c8a52711dc9294957fc0f437a4aaeab72da213aa`
- Current branch: `agent/cr-408-command`
- Verified CR 408 implementation commit:
  `a5143ef5629f3e7138104397a9ca15d72558eb59`
- Package: `0.8.0`
- Tags: `v0.6.0`, `v0.7.0`
- No release tag is planned for this integration checkpoint.

PRs #1–9 merged through ordinary merge commits. The completed, frozen backlog
is:

1. #11 — CR 504 Draw Step, based on `main`
2. #10 — CR 505 Main Phase, based on `main`
3. #12 — CR 503 Upkeep Step, based on `main`
4. #13 — CR 502 Untap Step, based on #12's branch
5. #14 — CR 501 Beginning Phase, based on #13's branch
6. #15 — CR 500 Turn Structure, based on #14's branch
7. #16 — CR 405 Stack, based on #15's branch
8. #17 — CR 400 General Zone Identity, based on #16's branch
9. #18 — CR 401 Library, based on #17's branch
10. #19 — CR 402 Hand, based on #18's branch
11. #20 — CR 403 Battlefield, based on #19's branch
12. #21 — CR 404 Graveyard, based on #20's branch
13. #22 — CR 406 Exile, based on #21's branch
14. #23 — CR 407 Ante Exclusion, based on #22's branch
15. #24 — CR 408 Command, based on #23's branch

CR 408 was already committed, pushed, locally verified, and opened as PR #24
when the freeze instruction arrived, so it is preserved as the frozen tip.
Do not create CR 409 or another rules-family branch.

## Current deterministic evidence

- 3,908 tests passed locally in 275.465 seconds on Windows Python 3.11.9.
- All 3,300 pinned rule records and 425 mechanic records verify against the
  2026-06-19 rules source.
- Current CR 408-tip conformance: 100 passing, 365 blocked, 78
  definition-only, 2,757 unreviewed.
- Mechanics: 47 partial, 378 unclassified, 0 trusted.
- Full Oracle: 2,957 exact, 15,691 partial, 19,725 unresolved; 69,664 material
  residuals.
- Commander-legal Oracle: 338 exact, 14,354 partial, 16,930 unresolved;
  61,212 material residuals.
- Seed-20260730 opportunity/replay, deterministic four-player natural-winner,
  hidden-information projection, repository/history/security, protocol demo,
  wheel build, and clean-install checks pass.
- PR #24 push run `30633146886` and pull-request run `30633164682` each passed
  Ubuntu/Windows on Python 3.11/3.12.

GitHub Actions is executing normally now that the repository is public. Earlier
zero-step billing/spending-limit failures on PRs #10–23 are historical external
failures, not current merge evidence. Updated PR heads must receive ordinary
green CI; do not use an administrator bypass while runners execute normally.

Local tool availability:

- Python 3.11.9: available
- Python 3.12: not installed locally
- Node 24.18.0 and npm 11.16.0: available
- WSL2: not installed
- Docker: not installed

The GitHub matrix supplies the supported Python 3.11/3.12 and
Ubuntu/Windows coverage that is not locally available.

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

## Immediate execution order

1. Finish the documentation reconciliation and reusable local merge gate.
2. Integrate PRs #11, #10, then #12–#24 into `main` with ordinary merge
   commits, regenerated derived artifacts, exact-head local evidence, and green
   GitHub CI.
3. Verify every intended feature head is reachable from `main`.
4. Run the complete final gate on `main` and refresh this handoff.
5. Create `agent/server-browser-vertical-slice` from updated `main`.
6. Implement one coherent authoritative server/browser vertical slice. Do not
   resume broad sequential CR review until it is tested and merged.

Exact next command after the documentation commit:

```powershell
py -3.11 scripts/local_merge_gate.py --expected-branch agent/cr-408-command
```
