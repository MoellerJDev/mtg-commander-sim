---
title: "Integration checkpoint"
status: "current"
authoritative_source: "live Git state and generated status reports"
verified: "2026-08-05"
audience: "maintainers resuming repository work"
maintenance: "hand-maintained"
---

# Integration checkpoint

This file intentionally contains no branch name, commit SHA, CI run number,
coverage count or copied milestone narrative. Those hand-maintained snapshots
became stale as soon as work merged.

Before continuing, inspect the live repository and GitHub state:

```powershell
git fetch origin --prune
git status --short --branch
git log --oneline --decorate --graph --all -30
git branch -vv
gh pr list --state open --limit 50
gh run list --limit 20
```

Then read:

- [platform implementation status](docs/PLATFORM_IMPLEMENTATION_STATUS.md) for
  integrated milestones and the exact next task;
- [compiler coverage](docs/COMPILER_COVERAGE_STATUS.md) and the generated
  [card-unlock frontier](coverage/card-unlock-frontier.md) for rules-family
  selection;
- [architecture debt](docs/ARCHITECTURE_DEBT_STATUS.md) for ratcheted source
  measurements;
- [CI workflow](docs/development/ci-pipeline.md) for exact-head certification
  and the two-slot process;
- [agent instructions](AGENTS.md) for current repository policy.

Use one active rules PR and at most one independent next-batch worktree. Prefer
focused local tests and the change-impact quick gate; public exact-head CI is the
normal merge authority. Browser automation must remain isolated and headless.
After merge, verify fresh `main`, remove only branches proven fully merged, and
select the next dependency-ready reusable rules family from regenerated data.
