# Integration handoff

This file records the current integration checkpoint. Generated coverage totals
remain authoritative in `coverage/`; this document does not replace them.

## Current state

- Repository: `MoellerJDev/mtg-commander-sim` (public)
- Package: `0.8.0`
- Active branch: `agent/cr-502-untap-step`
- Main before this integration:
  `cd2597d7c5f633df6bec34c8f0c6ac8024063a6a`
- Active pull request: #13, CR 502 Untap Step
- Recently merged: #25 local merge gate and rules PRs through CR 503
- GitHub-hosted Actions are executing normally. No administrative CI bypass is
  permitted while runners work.

The CR 502 child commits are being combined with the independently integrated
CR 503-505 work. Generated ledgers are rebuilt from all source and review
overlays rather than choosing stale files from either side.

## Combined candidate snapshot

- Comprehensive Rules snapshot: 2026-06-19
- Rules SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Numbered rules: 3,300
- Reviewed rules: 452
- Passing: 67
- Blocked: 322
- Definition-only: 63
- Unreviewed: 2,848
- Partial mechanics: 39
- Unclassified mechanics: 386
- Expected discovered tests before the exact candidate gate: 3,857

These figures describe review and executable coverage, not complete Magic rules
support. Material unsupported semantics continue to fail closed.

## Latest exact evidence

- CR 503 refreshed head
  `07226dcbf1934f89e1607e99a5daddbeea27d1c7` passed all 13 local
  merge-gate stages with 3,851 tests.
- Its GitHub push run 30638732883 and pull-request run 30638736337
  passed all eight matrix jobs.
- PR #12 merged into main at
  `cd2597d7c5f633df6bec34c8f0c6ac8024063a6a`.

## Next action

Finish the CR 502 merge candidate, run the exact local merge gate including
`tests.test_untap_step_rules`, push it, require fresh green push and
pull-request matrices, and merge PR #13 normally. Then retarget and integrate
PR #14. Broad sequential rule-family work remains frozen after the existing CR
408 tip.

Once every backlog head is reachable from a final green `main`, create
`agent/server-browser-vertical-slice` directly from `main` and pause before
making platform changes.

The server/browser product slice is not yet implemented.
