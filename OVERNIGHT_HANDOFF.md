# Integration handoff

This file records the current integration checkpoint. Generated coverage totals
remain authoritative in `coverage/`; this document does not replace them.

## Current state

- Repository: `MoellerJDev/mtg-commander-sim` (public)
- Package: `0.8.0`
- Active branch: `agent/cr-505-main-phase`
- Main before this integration: `814ff4fc45f6b10599d13348981053e8846d34d8`
- Active pull request: #10, CR 505 Main Phase
- Recently merged: #25 local merge gate, #11 CR 504 Draw Step
- GitHub-hosted Actions are executing normally. No administrative CI bypass is
  permitted while runners work.

CR 504 and CR 505 were sibling branches. Their runtime changes merge cleanly;
their generated ledgers were regenerated from the combined source and review
overlays rather than choosing either branch's stale generated files.

## Combined candidate snapshot

- Comprehensive Rules snapshot: 2026-06-19
- Rules SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Numbered rules: 3,300
- Reviewed rules: 442
- Passing: 66
- Blocked: 315
- Definition-only: 61
- Unreviewed: 2,858
- Partial mechanics: 37
- Unclassified mechanics: 388
- Expected discovered tests before the exact candidate gate: 3,846

These figures describe review and executable coverage, not complete Magic rules
support. Material unsupported semantics continue to fail closed.

## Verified integration evidence

- Integration checkpoint `65f99875c79e3ec4909ac8eda282b353ffdcf91c`
  passed the exact local merge gate with 3,832 tests.
- CR 504 refreshed head
  `a43ced04a87d95dbdb24862832429d70a7b1468c` passed the exact local
  merge gate with 3,838 tests and both GitHub push and pull-request matrices.
- PR #11 merged into main at
  `814ff4fc45f6b10599d13348981053e8846d34d8`.

## Next action

Finish the CR 505 merge candidate, regenerate authoritative artifacts, run the
exact local merge gate including `tests.test_main_phase_rules`, push it, require
fresh green push and pull-request matrices, and merge PR #10 normally. Then
continue with PR #12 in dependency order. Broad sequential rule-family work is
frozen after the existing CR 408 tip; once the backlog is integrated and main
passes the final gate, begin `agent/server-browser-vertical-slice`.

The server/browser product slice is not yet implemented. The existing engine,
protocol, privacy, replay, and packaging foundations must not be described as a
finished authoritative browser platform.
