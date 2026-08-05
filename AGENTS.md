---
title: "Codex project instructions"
status: "current"
authoritative_source: "repository contribution, architecture, and documentation policy"
verified: "2026-08-05"
audience: "Codex agents and contributors"
maintenance: "hand-maintained"
---

# Codex project instructions

Read this file completely before changing the repository. These instructions
are durable guardrails, not a status report. Never add branch names, pull
request numbers, CI run IDs, test totals or transient task notes here.

## Find current context

1. Inspect Git, worktree, pull-request and CI state instead of trusting a prior
   handoff.
2. Read [`docs/index.md`](docs/index.md) and use its task routing table.
3. Read the relevant generated status report before choosing rules or
   architecture work.
4. Read only the architecture, reference, operations and ADR documents required
   by the task, then inspect their authoritative code and tests.
5. Treat implementation, schemas, machine-readable policy and executable tests
   as current behavior. Generated reports own changing measurements. ADRs and
   the changelog explain history; they do not override current behavior.

Useful status entry points:

- [`docs/PLATFORM_IMPLEMENTATION_STATUS.md`](docs/PLATFORM_IMPLEMENTATION_STATUS.md)
- [`docs/RULES_COMPLETENESS_STATUS.md`](docs/RULES_COMPLETENESS_STATUS.md)
- [`docs/COMPILER_COVERAGE_STATUS.md`](docs/COMPILER_COVERAGE_STATUS.md)
- [`docs/ARCHITECTURE_DEBT_STATUS.md`](docs/ARCHITECTURE_DEBT_STATUS.md)
- [`coverage/card-unlock-frontier.md`](coverage/card-unlock-frontier.md)
- [`coverage/reusable-piece-matrix.md`](coverage/reusable-piece-matrix.md)

## Authority and safety boundaries

- `CommanderEngine` and its typed rules subsystems are authoritative. A client
  never mutates zones, life, mana, stack, counters, choices or effects.
- Every player command uses an unconsumed capability issued to the authenticated
  principal. `principal` is transport identity, never client-selected data.
- Only a scoped arbiter capability can submit generic effects. Product gameplay,
  rules enforcement, CI and releases cannot depend on an LLM or live AI ruling.
- Project hidden information by principal. Never solve a UI or test problem by
  exposing an authoritative checkpoint, library order or another seat's data.
- Use the pinned local Scryfall snapshot during games. Network access belongs to
  managed data refresh outside game transitions.
- Material unknown Oracle semantics, unsupported grammar and untrusted
  capability dependencies fail closed before mutation.
- A yield is an optimization, never authority to suppress a changed meaningful
  action. `suppressed_meaningful_windows` must remain zero.
- Advertised actions and accepted commands consume the same typed legality,
  cost and target authority.
- Preserve protocol versioning, deterministic hashes, transactional rollback,
  principal projection and exact Game Record v3 replay.
- Do not infer provider/model identity, completion, rules fidelity or matchup
  evidence from partial or duplicated fixtures.

## Rules and architecture changes

The repository is incrementally extracting coherent rules ownership from the
central engine. Do not perform a big-bang rewrite and do not move code merely to
reduce a line count.

A valid rules family:

- represents a reusable Comprehensive Rules behavior rather than a card name,
  collector number, set code or Oracle ID;
- uses immutable typed queries/proposals/transactions and a narrow mutation
  owner;
- removes the prior implementation and narrows dependency direction;
- lowers source-spanned CardProgram V2 nodes when Oracle text participates;
- declares fine-grained capabilities and ambient interaction dependencies;
- shares legality between offers and command validation;
- fails closed for unsupported variants;
- adds positive, negative, malformed-input, rollback, multiplayer, replay,
  privacy, property and focused mutation evidence where applicable;
- regenerates rules, compiler, card, architecture and status artifacts once at
  the final exact head.

Do not add a second capability, mechanic, compiler, scheduler or runtime
component registry. Do not add runtime Oracle parsing or arbitrary executable
callbacks. Repeated source-pinned descriptors must become a generic compiler
production and component family.

Follow [`docs/architecture/dependency-rules.md`](docs/architecture/dependency-rules.md)
and the accepted [ADRs](docs/adr/index.md). A production module or function over
the policy threshold is measured debt; growth requires the documented review
path. The generated architecture audit is the measurement authority.

## Browser ownership

Every visible browser—including the Codex in-app browser—is user-owned state.
Do not open, reuse, focus or navigate one unless the user explicitly requests
visible interaction in the current task.

- Automated server checks use
  `.\.venv\Scripts\python.exe -m server --no-open`.
- Probe HTTP endpoints with CLI clients.
- Run UI checks only in isolated headless Playwright contexts.
- Keep Vite `open: false` and HTML reporters at `open: "never"`.
- Stop processes started for a check when the check ends.

An open browser, prior permission or running localhost listener is not current
authorization.

## Development and certification

Use the worktree-local CPython 3.12 environment, never a global `python` alias.
Keep one substantive branch under certification and at most one independent
next-batch worktree. Do not mix their changes.

During development, run new and adjacent impacted tests. Before publishing an
ordinary change, inspect and run the deterministic quick gate:

```powershell
.\.venv\Scripts\python.exe scripts\quick_gate.py --dry-run
.\.venv\Scripts\python.exe scripts\quick_gate.py
```

Public exact-head pull-request CI is the normal merge authority. The full local
merge gate is for releases and unusually high-risk persistence, replay, privacy
or packaging changes. Browser automation remains headless. The complete
workflow and recovery commands are in
[`docs/development/ci-pipeline.md`](docs/development/ci-pipeline.md).

Never stage `run/`, `local/`, SQLite databases, Scryfall archives, image or deck
caches, raw capabilities, private packets, provider memory or live Game Records.
Use temporary directories and sanitized recipes for regression records.

## Documentation contract

This repository uses a docs-as-code adaptation of Diátaxis:

- tutorials teach a safe first success;
- how-to guides solve a concrete operator or contributor task;
- reference pages state precise interfaces and facts;
- explanations describe architecture and rationale;
- ADRs preserve durable decisions and consequences;
- generated reports are the only authority for changing counts, fingerprints,
  branch integration state and next-work selection.

For every implementation change, update the smallest existing document that
owns the affected behavior. Do not create a progress diary, branch handoff,
duplicate overview or one-page-per-feature note.

Living documentation must:

- describe the immediate current state in present tense;
- distinguish implemented behavior from explicit limitations;
- avoid PR/SHA/run/test/card totals and other volatile facts;
- link to generated status instead of copying it;
- have one primary audience and one documentation purpose;
- use sentence-case headings, literal language and repository-relative links;
- identify commands that are safe to copy;
- delete or rewrite superseded guidance in the same PR;
- update [`docs/index.md`](docs/index.md) when files move, appear or disappear.

Use an ADR only for a durable architecture decision whose alternatives and
consequences future contributors need. Supersede accepted ADRs; do not rewrite
their historical decision. Keep historical narrative only in ADRs and
[`CHANGELOG.md`](CHANGELOG.md).

Run the documentation fitness functions after any Markdown change:

```powershell
.\.venv\Scripts\python.exe scripts\validate_documentation.py --check
.\.venv\Scripts\python.exe scripts\update_platform_status.py --check
.\.venv\Scripts\python.exe scripts\update_architecture_audit.py --check
```

If a document disagrees with code or generated evidence, fix or remove the
document. Never preserve a stale statement for continuity.
