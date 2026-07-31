# Integration handoff

This file records the current integration checkpoint. Generated coverage totals
remain authoritative in `coverage/`.

## Current state

- Repository: `MoellerJDev/mtg-commander-sim` (public)
- Package: `0.8.0`
- Active branch: `agent/cr-501-beginning-phase`
- Main before this integration:
  `78e81dde54e72766f7a9725c805f3c094ce37a3a`
- Active pull request: #14, CR 501 Beginning Phase
- Recently merged: #25 local merge gate and rules PRs through CR 502
- GitHub-hosted Actions are executing normally; CI bypass is prohibited.

The CR 501 child commits are being combined with merged CR 502-505. Generated
ledgers are rebuilt from every source and review overlay.

## Combined candidate snapshot

- Comprehensive Rules snapshot: 2026-06-19
- Rules SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Numbered rules: 3,300
- Reviewed rules: 454
- Passing: 68
- Blocked: 322
- Definition-only: 64
- Unreviewed: 2,846
- Partial mechanics: 40
- Unclassified mechanics: 385
- Expected discovered tests before the exact candidate gate: 3,860

These figures describe review and executable coverage, not complete Magic rules
support. Material unsupported semantics continue to fail closed.

## Latest exact evidence

- CR 502 refreshed head
  `1efd1c760873b65e87cb3b22e7ad6e69d0e4c38a` passed all 13 local
  merge-gate stages with 3,857 tests.
- Its GitHub push run 30639709662 and pull-request run 30639714253
  passed all eight matrix jobs.
- PR #13 merged into main at
  `78e81dde54e72766f7a9725c805f3c094ce37a3a`.

## Next action

Run the exact CR 501 merge gate including
`tests.test_beginning_phase_rules`, require fresh green push and pull-request
matrices, and merge PR #14 normally. Then integrate PR #15. Broad sequential
rule-family work remains frozen after the existing CR 408 tip.

Once every backlog head is reachable from final green `main`, create
`agent/server-browser-vertical-slice` directly from `main` and pause before
making platform changes.

The server/browser product slice is not yet implemented.
