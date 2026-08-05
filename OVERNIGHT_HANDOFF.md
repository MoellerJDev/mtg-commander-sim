---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "2026-08-05"
audience: "maintainers continuing the migration"
maintenance: "hand-maintained"
---

# Integration handoff

This is a sanitized operational handoff. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider-session data.

## Integration coordinate

The public repository is `MoellerJDev/mtg-commander-sim`; `main` is the only
default branch. PR 98's fixed-output mana family is merged at
`9a03e4688b61d29ae10fd338ad7db2aeebe74336`. PR 99's full-history nightly
provenance repair is merged at
`2aa1b6d6ff8f75ab219665618a247b315b7fc411`, with exact-head certification and
post-merge main smoke green. The active implementation branch is
`rules/generic-flash-cast-timing`, merged locally with that protected main
rather than rebased or force-pushed.

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

The Flash branch is a coherent foundation-plus-harvest slice for face-pinned
printed Flash, not a claim to complete cast timing or CR 702.8. One immutable
typed permission and one registered runtime component supply action
advertisement and command validation from the same legality function.
CardProgram V2 lowering emits exact source spans and selected-face identities;
no runtime Oracle parsing, printed name, collector number, set code, or Oracle
ID selects behavior, and the engine gains no state-write owner.

The selection came from frontier family `keyword_dependency:flash`: 591
affected Commander cards, 52 sole-blocker cards, 125 one-additional-blocker
opportunities, 592 expected exact abilities, 52 expected exact cards, and 592
expected residual removals. It had no capability prerequisites and medium
interaction risk. This is a universal typed timing foundation plus its direct
generic keyword harvest.

The one final regeneration matched the prediction exactly. Commander exact and
trusted CardPrograms rise from 1,216 to 1,268, capability-closed programs rise
from 1,212 to 1,264, partial cards fall from 13,883 to 13,831, unresolved cards
remain 16,524, failures remain zero, and material residuals fall from 52,325 to
51,733. `CommanderEngine` shrinks by seven logical lines and direct GameState
writes remain 135. Exact current architecture and corpus figures live in the
generated [architecture debt report](docs/ARCHITECTURE_DEBT_STATUS.md) and
[compiler coverage report](docs/COMPILER_COVERAGE_STATUS.md).

Conditional, granted, removed, and player-wide as-though Flash remain explicit
residuals. Priority, zone permission, land-play timing, other cast
prohibitions, costs, and targets keep their existing independent owners. Raw
keyword metadata without the trusted compiled permission fails closed.

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
[CI pipeline guide](docs/development/ci-pipeline.md). PR 99 is merged and this
Flash successor now contains its protected merge commit. Publish this branch
without rebasing or force-pushing. It does not change a browser-facing schema;
Playwright shard balancing remains separate. While exact-head CI runs, select
the next dependency-ready typed family from refreshed frontier fingerprint
`411fba39984c31b6d4e611a5467cc594d5eb685e90952e90b5cd88a16c3f8e86`, and do
not select the complete continuous-layers/dependencies row.
