---
title: "CI pipeline and two-slot development"
status: "current"
authoritative_source: "GitHub workflows, platform/test-shards.json, and local gate scripts"
verified: "2026-08-02"
audience: "contributors and maintainers"
maintenance: "hand-maintained"
---

# CI pipeline and two-slot development

The repository uses a short local feedback loop and exact-head public
certification. Local checks find likely defects quickly; GitHub Actions is the
ordinary merge authority. The workflow never requires a visible browser.

## Two development slots

Keep at most two substantive branches active:

- Slot A is pushed and undergoing pull-request certification.
- Slot B is a separate worktree containing the next independent rules batch.

Create Slot B from current remote `main` while Slot A is running:

```powershell
git fetch origin --prune
git worktree add ..\mtg-commander-sim-next -b <next-branch> origin/main
Set-Location ..\mtg-commander-sim-next
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . -r requirements-dev.txt
```

Never rebase or rewrite Slot A while its exact head is being certified. If its
CI fails, preserve coherent Slot B work, fix Slot A in its own worktree, push a
new immutable head, and let stale runs cancel. After Slot A merges, fetch and
rebase Slot B only when its changes actually overlap the merged work.

Clean up a merged slot only after confirming its pull request and `main` SHA:

```powershell
git fetch origin --prune
git worktree remove <merged-worktree-path>
git branch -d <merged-branch>
git push origin --delete <merged-branch>
```

Do not delete a branch with unique work, an active run, or an unmerged pull
request.

## Local quick gate

Run focused tests while implementing. Before commit, use:

```powershell
.\.venv\Scripts\python.exe scripts/quick_gate.py --dry-run
.\.venv\Scripts\python.exe scripts/quick_gate.py
```

`platform/change-impact-policy.json` is the versioned many-to-many path/check
policy consumed by `scripts/change_impact.py`, `scripts/quick_gate.py`, and
`scripts/ci_plan.py`. It maps normalized paths to the manifest in
`platform/test-shards.json`, generated checks, and platform gates. Internal
rules modules are never classified by generic words such as `action` or
`choice`; browser-facing protocol, projection, action-catalog, choice-form,
server, and priority-owner paths are explicit. Cross-cutting protection and
attachment sources deliberately select compiler, replacement, targeting, and
state-action owners so a source-correctness regression cannot escape through a
single narrow shard. `scripts/quick_gate.py` includes
committed and working-tree changes, validates Python 3.12, compiles Python,
builds the compact card database when necessary, runs directly changed tests
and affected functional shards, and selects relevant generated, architecture,
rules, repository, package, or browser-build checks.

The local quick gate does not run Playwright journeys. Browser-sensitive work
gets generated-type, typecheck, and production-build checks locally; isolated
headless Chromium belongs to CI. Never add a command that opens, focuses, or
navigates the user's browser.

The full `scripts/local_merge_gate.py` remains appropriate for a release or an
exceptional persistence, replay, privacy, or packaging risk. It is deliberately
not the default per-commit gate.

## Pull-request certification

`.github/workflows/ci.yml` runs these independent jobs:

- ten balanced Ubuntu functional shards;
- generated inventory, rules, documentation, repository, and architecture
  validation;
- wheel build and clean-install verification;
- a focused Windows compatibility overlay, widened to the complete suite for
  platform-sensitive changes or the `windows-full` label;
- browser build plus one four-context smoke journey, widened to two isolated
  Playwright shards for browser-sensitive changes or the `browser-full` label.
  Full shards use distinct ports, runtime directories, and SQLite databases.

The final `PR / Certification` job receives every required job through
`needs` and fails unless all succeeded. Protect `main` with the exact required
status context `PR / Certification`.

Do not use `gh pr merge --auto` until branch protection is confirmed. Without a
required check, GitHub may merge immediately while jobs are still running.
Once protection is active, auto-merge is safe only for the immutable SHA whose
certification is in progress.

The nonblocking metrics job records observed queue, job, and critical-path
durations as an artifact and job summary. Cache-hit rate, agent idle time, and
stale-run cancellation remain `null` when GitHub does not expose measured data;
the reporting code never estimates them as observations.

Deterministic failures that escape the quick gate are recorded in
`platform/ci-escape-source.json`. The generated
`coverage/ci-escape-report.json` and `.md` classify each failure, its direct
regression, and the impact-edge disposition. Push counts and Slot B idle time
remain null when they cannot be observed; workflow-run counts are not relabeled
as pushes.

## Main and nightly assurance

`.github/workflows/main-smoke.yml` runs after each push to `main`. It checks a
compact replay/server suite, generated integration state, pinned rules, wheel
metadata, and the production browser build. It is an integration alarm, not a
second complete pre-merge suite.

`.github/workflows/nightly.yml` owns expensive breadth:

- complete deterministic Python suites on Ubuntu and Windows;
- all isolated headless Chromium journeys;
- at least 100,000 deterministic property transitions across parallel jobs;
- focused implementation mutations, natural-winner/persistence soak, and
  performance/repository checks;
- current Scryfall ingestion and full/Commander Oracle and CardProgram
  censuses as artifacts;
- Python and npm dependency audits.

Nightly failures are real regressions or assurance debt. Fix them on a focused
branch; do not weaken the nightly budget to make a failure disappear.

## Shard maintenance

Every `tests/test_*.py` module belongs to exactly one primary shard in
`platform/test-shards.json`. Overlay suites such as `main-smoke`,
`windows-compat`, and `nightly-property` may intentionally reuse modules.

Validate ownership after adding, renaming, or deleting a test module:

```powershell
.\.venv\Scripts\python.exe scripts/test_shards.py validate
```

Keep functional shard weights close enough to use parallel capacity. Split by
coherent subsystem ownership, not by individual test methods. The generated
inventory shard is separate because thousands of small generated cases have a
different runtime profile from behavioral tests.

## Recovery and inspection

Inspect current repository activity without opening a browser:

```powershell
gh pr list --state open --limit 50
gh run list --limit 20
gh run view <run-id> --json status,conclusion,headSha,url
gh run view <run-id> --json jobs --jq '.jobs[] | {name,status,conclusion}'
```

If the stable certification context is missing, first inspect the workflow job
graph and `scripts/verify_ci_needs.py`. If the quick gate selects an unexpected
surface, add a deterministic classifier regression before changing the mapping.
Never bypass a failing required check or represent unavailable CI metrics as
observed values.
