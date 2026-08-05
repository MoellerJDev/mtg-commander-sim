---
title: "CI pipeline and two-slot development"
status: "current"
authoritative_source: "GitHub workflows, platform/test-shards.json, and local gate scripts"
verified: "2026-08-05"
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
server, lifecycle, and persistence paths are explicit. `engine.py` and
`session.py` no longer imply every browser journey by path alone: the typed
subsystem changed alongside them selects any focused public behavior. A
compiler-only change with no browser-facing runtime or schema change therefore
keeps the compact smoke only. For responsibilities still inside the legacy
engine, the planner maps changed Python hunks in both the base and candidate
trees to qualified function owners. Changes to the enumerated priority, yield,
and action-opportunity methods require complete browser E2E; unrelated engine
orchestration does not inherit that cost. Cross-cutting protection and
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
- a focused Windows compatibility overlay for ordinary changes;
- for platform-sensitive changes or the `windows-full` label, all eleven
  authoritative primary shards on isolated Windows runners and Python
  processes, with `fail-fast: false`, at most five concurrent workers,
  per-shard compact databases and runtime roots, and no shared writable state;
- one separate Windows wheel build and clean-install verification, followed by
  `PR / Windows Certification`, which fails closed on the wrong mode, missing,
  skipped, failed, duplicate, or zero-test shard results, a manifest partition
  gap, or package failure;
- browser build plus a compact authoritative four-context lifecycle smoke;
- focused `mana-action`, `combat`, or `turn-draw` Playwright journeys selected
  by the affected typed rules owner (or the matching `browser-*` label);
- three deterministic complete Playwright groups for browser, protocol, projection,
  reconnect, room, WebSocket, lifecycle, persistence, browser-facing choice or
  action schema changes, workflow changes, natural-winner critical rules, or
  the `browser-full` label. The nonempty `lifecycle`, `rules`, and `soak`
  groups use distinct ports, runtime directories, and SQLite databases.

The compact smoke is the bounded reconnect/lifecycle journey: it starts the
real server, creates four seat-isolated tabs, validates private hands, submits
accepted mulligan commands including an exact retry, survives pause/resume and
reconnect, and closes every context. It does not play a natural game to a
winner. Natural completion remains in the `soak` group and runs when browser,
persistence, replay, Commander-damage, combat-completion, state-based-loss, or
workflow ownership changes. Focused journey tags are closed policy values in
`platform/change-impact-policy.json`; adding an arbitrary test title cannot
silently expand or bypass the gate.

The final `PR / Certification` job receives the stable Windows certification
result and every other required job through `needs`, and fails unless all
succeeded. Protect `main` with the exact required status context
`PR / Certification`.

The pre-sharding public baseline is run `31025126367`: its single Windows
discovery process executed the complete test allocation in 2,265.245 seconds
(37 minutes, 45.245 seconds) before reporting the already-corrected
generated-audit drift.
Use the exact-head matrix metrics—not that historical total—to decide whether
the five-runner ceiling or shard allocation should change.

Do not use `gh pr merge --auto` until branch protection is confirmed. Without a
required check, GitHub may merge immediately while jobs are still running.
Once protection is active, auto-merge is safe only for the immutable SHA whose
certification is in progress.

The nonblocking metrics job records observed queue, job, step, and critical-path
durations plus Playwright journey duration, status, retries, failure class,
browser-context count, accepted command count, authoritative/projected
revisions, and measured persistence/review time. It also reports each Windows
shard's queue, setup, test and total duration, executed test count, the one-time
package duration, the Windows critical path, and actual overlapping test-runner
concurrency. Raw JSON reports and the combined `ci-metrics` artifact are
retained for 14 days so future shard changes use measured history. Cache-hit
rate, agent idle time, and stale-run cancellation remain `null` when GitHub
does not expose measured data; the reporting code never estimates them as
observations.

Long browser journeys use one shared progress driver rather than nested timeout
loops. It observes the decision ID, phase/step, active and priority players,
view/state revisions, accepted command and event counts, latest event, actor
queue, and pending persistence. Ninety seconds without a real change fails with
a compact snapshot and exact one-test rerun command. Ordinary command
acknowledgements still wait for authoritative durability, while review artifacts
remain derived and are generated only for paused or terminal records.

`scripts/update_platform_status.py` treats current Git and pull-request facts
as validation inputs rather than prose. Active PR phases must identify a real
open PR whose head contains the recorded candidate commit; a candidate already
reachable from `main`, a pending PR already merged, or a stale head lacking an
explicit historical classification fails closed. Current test counts and
CardProgram census values are derived from the authoritative test inventory and
coverage artifacts rather than copied into `platform/readiness-source.json`.

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
- all three isolated headless Chromium groups, including the natural-winner
  soak;
- at least 100,000 deterministic property transitions across parallel jobs;
- focused implementation mutations, natural-winner/persistence soak, and
  performance/repository checks;
- current Scryfall ingestion and full/Commander Oracle and CardProgram
  censuses as artifacts;
- Python and npm dependency audits.

Nightly failures are real regressions or assurance debt. Fix them on a focused
branch; do not weaken the nightly budget to make a failure disappear.

## Headless browser commands

The public workflow is authoritative, but a focused local reproduction may be
run headlessly after assigning isolated paths and ports. None of these commands
opens a visible browser or HTML report:

```powershell
$env:MTG_CARD_DB = "data/test-ci-smoke.sqlite3"
$env:MTG_E2E_SERVER_PORT = "18081"
$env:MTG_E2E_WEB_PORT = "15171"
$env:MTG_E2E_RUNTIME_DIR = "../local/playwright-smoke"
$env:MTG_PLAYWRIGHT_JSON = "../local/playwright-smoke.json"
npm run e2e:smoke --prefix web

Set-Location web
npx playwright test --grep "@browser-lifecycle"
npx playwright test --grep "@browser-rules"
npx playwright test --grep "@browser-soak"
```

Use different database, runtime, and port values when groups run concurrently.
On failure, prefer the exact `--grep` command printed by the progress diagnostic.

## Shard maintenance

Every `tests/test_*.py` module belongs to exactly one primary shard in
`platform/test-shards.json`. Overlay suites such as `main-smoke`,
`windows-compat`, and `nightly-property` may intentionally reuse modules.

Validate ownership after adding, renaming, or deleting a test module:

```powershell
.\.venv\Scripts\python.exe scripts/test_shards.py validate
```

Every primary shard is directly reproducible on Windows and can write the same
compact result record consumed by public certification and metrics:

```powershell
.\.venv\Scripts\python.exe scripts/test_shards.py run core-domain `
  --result-json local/windows-results/core-domain.json
```

`generated-validation` is a primary shard, not a second full-discovery pass.
The complete Windows matrix therefore executes every discovered test module
exactly once. `windows-compat` remains an intentionally overlapping focused
suite and never runs alongside the full matrix.

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
