# Integration handoff

This file records the current integration checkpoint. Generated coverage totals
remain authoritative in `coverage/`; this document does not replace them.

## Current state

- Repository: `MoellerJDev/mtg-commander-sim` (public)
- Package: `0.8.0`
- Active branch: `agent/cr-503-upkeep-step`
- Main before this integration:
  `a03a4f0cfb7819e7fbc97a387403376463d0e4fe`
- Active pull request: #12, CR 503 Upkeep Step
- Recently merged: #25 local merge gate, #11 CR 504 Draw Step, #10 CR 505
  Main Phase
- GitHub-hosted Actions are executing normally. No administrative CI bypass is
  permitted while runners work.

The CR 503 branch was created from the earlier CR 506 tip. Its runtime changes
are being combined with the independently merged CR 504 and CR 505 work.
Generated ledgers are rebuilt from all source and review overlays rather than
choosing stale files from either side.

## Combined candidate snapshot

- Comprehensive Rules snapshot: 2026-06-19
- Rules SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Numbered rules: 3,300
- Reviewed rules: 446
- Passing: 67
- Blocked: 317
- Definition-only: 62
- Unreviewed: 2,854
- Partial mechanics: 38
- Unclassified mechanics: 387
- Expected discovered tests before the exact candidate gate: 3,851

These figures describe review and executable coverage, not complete Magic rules
support. Material unsupported semantics continue to fail closed.

## Latest exact evidence

- CR 505 refreshed head
  `0ca1f82dee13f5066b2308b3a5dcbe8349a06ea6` passed all 13 local
  merge-gate stages with 3,846 tests.
- Its GitHub push run 30637700880 and pull-request run 30637704541
  passed all eight matrix jobs.
- PR #10 merged into main at
  `a03a4f0cfb7819e7fbc97a387403376463d0e4fe`.

## Next action

Finish the CR 503 merge candidate, run the exact local merge gate including
`tests.test_upkeep_step_rules`, push it, require fresh green push and
pull-request matrices, and merge PR #12 normally. Then retarget and integrate
PR #13. Broad sequential rule-family work remains frozen after the existing CR
408 tip.

Once every backlog head is reachable from a final green `main`, create
`agent/server-browser-vertical-slice` directly from `main` and pause before
making platform changes.

The server/browser product slice is not yet implemented. The existing engine,
protocol, privacy, replay, and packaging foundations must not be described as a
finished authoritative browser platform.
