---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "maintainers continuing the migration"
maintenance: "hand-maintained"
---

# Integration handoff

This is a sanitized operational handoff. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider-session data.

## Integration coordinate

- Public repository: `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- The front-matter `verified` field records the implementation commit reviewed
  for this handoff. Use `git rev-parse HEAD` and the public Actions page for the
  live checkout rather than copying an ephemeral branch or run ledger here.
- Current program boundary: finish Phase 1 enforcement before structural
  migration and broad rules expansion.

## Current product boundary

The repository contains a deterministic partial Commander engine, strict
principal projections, Game Record v3 replay, a single-process FastAPI actor
runtime, local SQLite persistence, managed Scryfall data and image caching, and
a browser table supporting two- and four-seat local play. Rules, Oracle,
deployment, accessibility, accounts, and customizable dashboard coverage remain
partial.

The exact platform state is generated in
[`docs/PLATFORM_IMPLEMENTATION_STATUS.md`](docs/PLATFORM_IMPLEMENTATION_STATUS.md).
Compiler and rules figures are generated in
[`docs/COMPILER_COVERAGE_STATUS.md`](docs/COMPILER_COVERAGE_STATUS.md). Do not
copy those figures into this handoff.

## Phase 1 documentation deliverable

The architecture baseline and non-growth guards are on verified `main`. Phase
1 documentation enforcement consists of:

- an authoritative documentation map and typed metadata on maintained files;
- focused current architecture, extension, testing, operations, and threat
  model documents;
- validated ADR metadata, index, template, and decision contents;
- internal-link and stale numerical-claim checks;
- generated-only numerical status and removal of integration chronology from
  current status documents.

Generated Markdown is presentation only; its JSON/source inputs are
authoritative. These guards preserve existing debt as an explicit compatibility
baseline; they do not assert that extraction has already occurred.

## Merge discipline

- Keep the branch focused on documentation policy, validators, current/target
  separation, focused negative tests, and generated status deduplication.
- Run focused tests locally while iterating.
- Before merge, run the repository’s exact-head local merge gate and require the
  public CI matrix to pass for the same commit.
- Merge normally, remove the merged feature branch, return to updated `main`,
  and start the Phase 2 capability trust-model slice from a fresh branch.
- Do not alter tags or release licenses without explicit authorization.

## Next checkpoint

The next phase after documentation enforcement is Phase 2: a versioned
fine-grained capability schema and one representative compiler/runtime trust
migration. Broad rules expansion remains paused until that rail exists.
