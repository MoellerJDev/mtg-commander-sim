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
`9a94b82f8744df29757e056b24c3b29e29ad5553` through PR 93. Exact-head run
30959180040 and post-merge main-smoke run 30961096927 are green. The active
Slot A implementation branch is `rules/generic-haste-summoning-sickness`,
based directly on that merge and intended for PR 94.

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

PR 94 is a coherent foundation-plus-harvest slice for the
`keyword_dependency:haste` frontier family. The generic keyword compiler and
effective-characteristic evaluator existed already; the branch adds one typed,
read-only CR 302.6/702.10 summoning-sickness and Haste owner, routes attack,
activated-ability, mana-source discovery, mana payment, and as-though-Haste
legality through it, and closes two fine-grained capabilities.

The selection was made from the PR 93 frontier fingerprint
`2401a67a1673d8d4e8571d4d8ac1461239aa5fc093689912ca4f04e1e58b7083`:

- 630 lowerable Haste abilities affecting 626 Commander-legal cards;
- 32 sole-blocker cards;
- 139 one-additional-blocker opportunities and 175 two-additional-blocker
  opportunities;
- expected 32 full-card promotions and 367 fewer material residuals;
- no prerequisite capabilities; medium effort and medium interaction risk;
- leading paired blockers were continuous layers/dependencies (66 cards),
  Flying (11), CR 611 continuous effects (7), and first strike (5).

The one final regeneration matched the prediction exactly: Commander exact and
trusted CardPrograms rose from 782 to 814, capability-closed programs from 779
to 811, and material residuals fell from 57,177 to 56,810. Full-corpus exact and
trusted programs rose by 45 and full-corpus material residuals fell by 429.
The residual Haste row has no sole-blocker or projected exact gain, so
conditional and otherwise nonclosed variants remain explicit residuals.

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
[CI pipeline guide](docs/development/ci-pipeline.md). While PR 94 runs in public
CI, create Slot B from fresh `origin/main` and begin PR 95 as one independent,
dependency-ready reusable rules family. Ordinary mana-ability capability
closure is the leading bounded candidate; re-check the refreshed frontier and
its prerequisites before committing to it. Do not select the entire continuous
layers/dependencies row, and keep Playwright shard balancing separate unless a
rules branch genuinely changes a browser-facing schema.
