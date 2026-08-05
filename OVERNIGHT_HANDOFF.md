---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "2026-08-04"
audience: "maintainers continuing the migration"
maintenance: "hand-maintained"
---

# Integration handoff

This is a sanitized operational handoff. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider-session data.

## Integration coordinate

The public repository is `MoellerJDev/mtg-commander-sim`; `main` is the only
default branch. The certified CPython 3.12 baseline is merge commit
`b3f9846deac2c907de92878e72a20b21255f6e89` through PR 94. Exact-head run
30965130610 and post-merge main-smoke run 30965839654 are green. The active
Slot B implementation branch is `rules/flying-reach-block-legality`, based
directly on that merge and intended for PR 95.

Always re-read the live branch, pull request, exact-head CI, worktree, and
generated status before acting:

```powershell
git fetch origin --prune
git status --short --branch
git log --oneline --decorate --graph --all -30
git branch -vv
gh pr list --state open --limit 50
gh run list --limit 20
```

The exact current platform, compiler, rules, test, and architecture figures are
generated in [platform status](docs/PLATFORM_IMPLEMENTATION_STATUS.md),
[compiler coverage](docs/COMPILER_COVERAGE_STATUS.md), and
[architecture debt](docs/ARCHITECTURE_DEBT_STATUS.md). Do not copy those counts
into this handoff.

## Active rules slice

PR 95 is a coherent foundation-plus-harvest slice for the
`keyword_dependency:flying` and `keyword_dependency:reach` frontier families.
It extracts one typed, read-only CR 702.9/702.17 aerial block-legality owner,
consumes the existing canonical current effective-characteristic snapshots,
and closes separate fine-grained Flying and Reach capabilities. Existing
declaration-restriction, protection, continuous-effect, copy, and action-catalog
owners retain their boundaries. Both advertised block options and accepted
commands use `CommanderEngine._can_block`.

The selection was made from the PR 94 frontier fingerprint
`f56370fbb01fd621a63d58510a488a60a9003d6c6caf16b7cf02c815f4048e02`:

- Flying appeared 3155 times across 3133 Commander-legal cards, with 192
  sole-blocker cards, 712 paired opportunities, and 1206 two-additional-blocker
  opportunities;
- Reach appeared 405 times across 403 cards, with 37 sole blockers, 103 paired
  opportunities, and 133 two-additional-blocker opportunities;
- the bundle expected 229 full-card promotions and 3,171 fewer material
  residuals; effort and interaction risk were medium;
- Flying depends on the fine-grained Reach exception. Broader continuous/copy/
  declarer prerequisites apply to unsupported producers and do not justify
  absorbing complete layers or CR 509 into this batch.

The one final regeneration matched the Commander prediction exactly: exact and
trusted CardPrograms rose from 814 to 1,043, capability-closed programs from
811 to 1,040, and material residuals fell from 56,810 to 53,639. Commander
partial cards fell by 229; unresolved and failed counts did not change. In the
full corpus, Oracle exact rose by 351, capability-closed CardPrograms by 347,
and CardProgram material residuals fell by 3,534. The four-card difference is
in the already-known full-corpus construction-failure population, which did not
change. Unsupported ability-changing/copy producers, other evasion,
declaration requirements and costs, and nonclosed Oracle grammar remain
explicit residuals. The refreshed frontier fingerprint is
`38a7ac0f5619b34f44b88492e88ad1fdfe45fa7427f85302c313c33974c756fa`.

`main` protection is active, strict, and requires `PR / Certification` with
administrator enforcement. Enable auto-merge only after the PR exists and let
that protected exact-head context decide the merge.

## Working method

Use at most two substantive worktrees: Slot A under exact-head certification
and Slot B for the next independent rules batch. Run focused tests during
implementation and the deterministic quick gate before commit:

```powershell
.\.venv\Scripts\python.exe scripts/quick_gate.py --dry-run
.\.venv\Scripts\python.exe scripts/quick_gate.py
```

Do not run the complete local merge gate for every ordinary rules branch. CI is
the normal certification authority; the full local gate is reserved for
releases and exceptional persistence, replay, privacy, or packaging risk. Keep
all browser automation isolated and headless, with reports configured never to
open.

The full operating procedure is the
[CI pipeline guide](docs/development/ci-pipeline.md). Publish PR 95 and let the
protected exact-head context decide the merge. This branch does not change a
browser-facing schema, so Playwright shard balancing stays separate. The
refreshed frontier ranks ordinary mana abilities as a high-yield candidate
(1762 affected cards, 384 sole blockers), but records high interaction risk
and explicit activation, payment, trigger, priority, and stack prerequisites;
reassess those prerequisites before making it the next batch. Do not select the
entire continuous-layers/dependencies row.
