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
default branch. PR 97's durable headless-browser synchronization is merged at
`6033efe107a9c0451c3a2616a8fa6b6ae646a390`. PR 95's generic Flying and Reach
block-legality family passed every protected exact-head gate and is merged at
`057082cb81c77f3381895d71af503e19479b5193`. The active Slot B implementation
branch is `rules/ordinary-mana-abilities`, integrated with that fresh protected
`main` rather than rebased or force-pushed.

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

The ordinary-mana branch is a coherent foundation-plus-harvest slice, not a
claim to complete CR 605. Its typed capability covers target-free, nonloyalty
activated mana abilities only when the entire fixed output and every mandatory
activation cost are represented. One immutable source-spanned CardProgram V2
descriptor supplies action advertisement, command validation, payment-window
discovery, immediate stackless resolution, exact replay identity, and the
canonical tap, sacrifice, life, and mana-cost commit owners. No printed name,
collector number, set code, or Oracle ID selects behavior, and the engine does
not gain another state-write owner.

The selection was made from the post-PR-95 card-unlock frontier. The coarse
`mechanic_dependency:cr-605-mana-abilities` row carried high interaction risk
and activation, casting, cost-payment, loyalty, mana-pool, priority, stack,
target, trigger, reentrancy, nested-payment, output-grammar, and replacement
prerequisites. Exact selection and harvest figures live only in the generated
[card-unlock frontier](coverage/card-unlock-frontier.md).

This branch intentionally takes only the dependency-closed fixed-output subset.
The one final regeneration matched its predicted promotions and residual
reduction. The partial-to-unresolved movement is an honest correction:
parenthesized basic-land reminder nodes and unsupported dynamic or conditional
variants are no longer treated as executable lowerable mana abilities. There
are no exact-card demotions. Representative promotions include Sol Ring,
Llanowar Elves, Gilded Lotus, Lotus Petal, the Signets, and the Pathway lands.

The new typed owners account for the positive production delta while
`CommanderEngine` shrinks, direct GameState-write identities and card-specific
heuristics do not grow, and `oracle_ir.py` falls below its production-module
review threshold. Exact architecture and line deltas live only in the generated
[architecture debt report](docs/ARCHITECTURE_DEBT_STATUS.md).

Dynamic, conditional, restricted, triggered, side-effecting, arbitrary
resolving-effect payment, target, loyalty, and mana-production replacement or
trigger variants remain explicit residuals. Basic land types grant distinct
intrinsic abilities through the existing CR 305.6 owner; reminder text does not
execute.

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
[CI pipeline guide](docs/development/ci-pipeline.md). PR 95 is merged and this
ordinary-mana successor now contains its protected merge commit. Publish this
branch without rebasing or force-pushing. It does not change a browser-facing
schema; Playwright shard balancing remains separate. Select the next
dependency-ready typed family from the refreshed frontier only after this
branch is certified, and do not select the complete
continuous-layers/dependencies row.
