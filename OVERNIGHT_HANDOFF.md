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
default branch. PR 100's generic compiled Flash family and live-review
persistence correction are merged at
`76c6bf154bfc62e5eae4cb10e391033413349050`; exact-head run `31016464622` and
post-merge main-smoke run `31019542461` are green. The fresh full-history
nightly run `31008277066` is also green, so the older shallow-provenance failure
is historical rather than current repository state.

The focused certification candidate is
`ci/focused-browser-impact-and-status-truth`. The preserved independent rules
checkpoint is `rules/generic-damage-effect-clauses`. Neither branch is merged
or represented as certified until GitHub says so.

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

The CI candidate introduces one versioned machine-readable impact policy for
authoritative four-context lifecycle smoke, focused mana/action, combat, and
turn/draw journeys, and deterministic nonempty lifecycle, rules, and
natural-winner soak groups. Browser, server, protocol, projection,
persistence, lifecycle, reconnect, room, WebSocket, workflow, and
browser-facing schema paths remain complete-E2E triggers. Python hunk ownership
also makes the priority, yield, and action-opportunity methods still housed in
`CommanderEngine` request complete browser E2E without turning every internal
engine edit into a full browser run. The same branch makes platform-status
generation reject stale ancestry and mismatched open/merged pull-request facts
and derives current test/CardProgram baselines from authoritative artifacts.
Long journeys use one shared 90-second no-progress diagnostic across decisions,
turn state, revisions, events, actor queues, and durability. Game persistence
runs off the event loop without acknowledging commands before the authoritative
write, and CI retains measured journey, retry, revision, command, and
persistence timing. The exact local smoke passed in 30.4 seconds; GitHub exact-
head measurements remain pending until PR 101 completes.

The fixed-damage checkpoint is a shared effect-clause family, not a card
override. It recognizes a closed fixed-quantity damage grammar across spell,
triggered, and activated contexts; lowers source-spanned CardProgram V2 nodes;
uses the existing canonical target, damage, replay, and privacy paths; and
keeps dynamic, divided, conditional, rider-bearing, and unsupported recipient
forms as material residuals. Its final corpus and architecture artifacts must
be regenerated only after it contains the merged CI predecessor.

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
[CI pipeline guide](docs/development/ci-pipeline.md). Publish the focused CI
candidate first. While it certifies, update the fixed-damage worktree from its
merged predecessor and finish that bounded grammar family. While the damage
candidate certifies, create the reusable-piece matrix foundation from current
`main`. Do not wait idly for CI, force-push published history, or select the
coarse continuous-layers/dependencies frontier row as one batch.
