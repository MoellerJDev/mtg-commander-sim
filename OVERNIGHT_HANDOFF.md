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

The selection was made from PR 95 frontier fingerprint
`38a7ac0f5619b34f44b88492e88ad1fdfe45fa7427f85302c313c33974c756fa`.
The coarse `mechanic_dependency:cr-605-mana-abilities` row contained 1,990
ability occurrences across 1,762 Commander-legal cards, with 384 sole-blocker
cards, 499 one-additional-blocker opportunities, and 414 two-additional-blocker
opportunities. It projected at most 384 full-card promotions and 1,990 removed
material residuals, but carried high interaction risk and activation, casting,
cost-payment, loyalty, mana-pool, priority, stack, target, trigger,
reentrancy, nested-payment, output-grammar, and replacement prerequisites.

This branch intentionally takes only the dependency-closed fixed-output subset.
The grammar scan expected 173 full-card promotions and 1,314 removed material
residuals, and the one final regeneration matched both figures. Commander
Oracle exact/trusted rises from 1,043 to 1,216; capability-closed programs rise
from 1,040 to 1,212; partial falls from 14,324 to 13,883; unresolved rises from
16,256 to 16,524; failures remain zero; and residuals fall from 53,639 to
52,325. The partial-to-unresolved movement is an honest correction: 106
parenthesized basic-land reminder nodes and unsupported dynamic/conditional
variants are no longer treated as executable lowerable mana abilities. There
are no exact-card demotions. Representative promotions include Sol Ring,
Llanowar Elves, Gilded Lotus, Lotus Petal, the Signets, and the Pathway lands.

Against the exact PR 95 head, handwritten production changes are +1,248/-327
lines (net +921) and tests are +692/-38 (net +654), excluding generated
artifacts and documentation. The new typed owners account for the positive
production delta while `CommanderEngine` shrinks by 180 logical lines, direct
GameState-write identities remain 135, printed-name and Oracle-ID heuristics do
not grow, and `oracle_ir.py` falls below the 1,500-logical-line review threshold.

Dynamic, conditional, restricted, triggered, side-effecting, arbitrary
resolving-effect payment, target, loyalty, and mana-production replacement or
trigger variants remain explicit residuals. Basic land types grant distinct
intrinsic abilities through the existing CR 305.6 owner; reminder text does not
execute. The refreshed frontier fingerprint is
`bacd71ee4abf89319e549fc13969ee30372be7ddb964457f2f0e0a4720e55dc2`.

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
