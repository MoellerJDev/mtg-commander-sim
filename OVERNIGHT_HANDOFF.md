---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "2026-08-02"
audience: "maintainers continuing the migration"
maintenance: "hand-maintained"
---

# Integration handoff

This is a sanitized operational handoff. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider-session data.

## Integration coordinate

The public repository is `MoellerJDev/mtg-commander-sim`; `main` is the only
default branch. The merged CPython 3.12 baseline includes the generic Oracle IR
v18 prevention/life sequencing correction. Its exact-head Ubuntu, Windows, and
headless Chromium certification passed. The active implementation branch is
`chore/pipelined-ci-throughput`, based directly on that merge.

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

## Active infrastructure phase

The current branch establishes the development throughput substrate before the
next rules family:

- deterministic committed-plus-worktree change classification;
- one primary owner for every Python test module;
- ten balanced Linux behavioral shards and a separate generated inventory
  shard;
- parallel generated/architecture, package, Windows, and headless-browser
  jobs;
- a stable fail-closed `PR / Certification` context;
- compact post-merge `main` smoke;
- nightly complete cross-platform/browser, property, mutation/soak, current
  corpus, and dependency assurance;
- observed CI timing artifacts without invented cache or agent metrics.

The repository currently has no branch protection. Do not use auto-merge until
the infrastructure pull request is certified and merged and `main` protection
requires the exact `PR / Certification` context. Without that protection,
GitHub can merge immediately while checks are still running.

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
[CI pipeline guide](docs/development/ci-pipeline.md). After this infrastructure
phase merges and protection is enforced, regenerate the dependency queue from
fresh `main` and resume one coherent rules family. Pair rule implementation
with genuine engine extraction, generic Oracle/CardProgram support, evidence,
replay/privacy assurance, and honest corpus deltas; do not open a status-only
follow-up.
