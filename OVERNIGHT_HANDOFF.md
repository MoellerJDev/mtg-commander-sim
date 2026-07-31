# Integration handoff

Generated coverage totals remain authoritative in `coverage/`.

## Current state

- Repository: `MoellerJDev/mtg-commander-sim` (public)
- Package: `0.8.0`
- Active branch: `agent/cr-405-stack`
- Main before this integration:
  `4cde25ae506a7a8b0a252096f2f7b3aad8929f9a`
- Active pull request: #16, CR 405 Stack
- Recently merged: #25 local merge gate and rules PRs through CR 500
- GitHub-hosted Actions are executing normally; CI bypass is prohibited.

## Combined candidate snapshot

- Comprehensive Rules snapshot: 2026-06-19
- Rules SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Numbered rules: 3,300
- Reviewed rules: 485
- Passing: 77
- Blocked: 340
- Definition-only: 68
- Unreviewed: 2,815
- Partial mechanics: 42
- Unclassified mechanics: 383
- Expected discovered tests before the exact candidate gate: 3,871

These figures describe review and executable coverage, not complete Magic rules
support. Material unsupported semantics continue to fail closed.

## Latest exact evidence

- CR 500 refreshed head
  `6ccba21fc02ee41d1e96e9f11e0df8452440a3c5` passed all 13 local
  merge-gate stages with 3,865 tests.
- Its GitHub push run 30641562768 and pull-request run 30641570559
  passed all eight matrix jobs.
- PR #15 merged into main at
  `4cde25ae506a7a8b0a252096f2f7b3aad8929f9a`.

## Next action

Run the exact CR 405 merge gate including `tests.test_stack_rules`, require
fresh green push and pull-request matrices, and merge PR #16 normally. Then
integrate PR #17. Broad sequential rule-family work remains frozen after the
existing CR 408 tip.

Once every backlog head is reachable from final green `main`, create
`agent/server-browser-vertical-slice` directly from `main` and pause.

The server/browser product slice is not yet implemented.
