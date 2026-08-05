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
default branch. PR 101's isolated Browser and full-Windows certification work
is merged at `d2ae5f4a4242c471bd9d5adee393aa98224afe7b`; exact-head run
`31037993447` passed all required jobs. It executed all 4,842 Windows tests with
five observed runners and an 11m07s Windows critical path, down from the
37m45s serial baseline. Post-merge smoke `31038955981` passed all 29
integration tests and then rejected only the now-unreachable squash-branch
feature commit; active PR 102 reconciles that provenance.

The sole active rules candidate is
`rules/generic-damage-effect-clauses` in PR 102. Its pre-transplant topology is
preserved locally as `backup/generic-damage-effect-clauses-pre-pr101`; only the
five substantive rules commits were transplanted onto merged `main`.

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

## Active checkpoints

The merged CI system uses one versioned machine-readable impact policy for an
authoritative four-context lifecycle smoke, focused mana/action, combat, and
turn/draw journeys, and deterministic nonempty lifecycle, rules, and
natural-winner soak groups. Full Windows coverage is eleven process-isolated
primary shards plus one wheel job and a fail-closed certification aggregator.
The longest measured test shard is multiplayer/Commander at 372.399 seconds;
the complete Windows critical path remains within the 8–12 minute target.

The fixed-damage checkpoint is a shared effect-clause family, not a card
override. It recognizes a closed fixed-quantity damage grammar across spell,
triggered, and activated contexts; lowers source-spanned CardProgram V2 nodes;
uses the existing canonical target, damage, replay, and privacy paths; and
keeps dynamic, divided, conditional, rider-bearing, and unsupported recipient
forms as material residuals. It is now based on merged PR 101. The refreshed
Commander census records a positive exact-card harvest with no demotions or
construction failures; the authoritative deltas remain in the generated
compiler-coverage report. Focused compiler/runtime tests and the deterministic
impacted quick gate pass, as do the regenerated frontier, architecture,
documentation, repository, and shard checks. Public exact-head certification
remains pending.

After those two checkpoints, the next substantive foundation is the generated
reusable-rules-piece matrix plus durable program baseline. Do not create a
second capability registry, mechanic registry, or card scheduler.

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
[CI pipeline guide](docs/development/ci-pipeline.md). Complete PR 102's one-time
corpus/status regeneration and exact-head certification. While it certifies,
prepare the reusable-piece matrix foundation from current `main`. Do not wait
idly for CI, force-push published history, or select the coarse
continuous-layers/dependencies frontier row as one batch.
