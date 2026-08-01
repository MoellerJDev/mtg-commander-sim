---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "5197a91dcdac428c09980a39467a7a5c62bc17fa"
audience: "maintainers continuing the migration"
maintenance: "hand-maintained at each merged phase checkpoint"
---

# Integration handoff

This is a sanitized operational handoff. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider-session data.

## Integration coordinate

- Public repository: `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Verified main commit: `5197a91dcdac428c09980a39467a7a5c62bc17fa`
- Verified CI: [run 30707443584](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30707443584)
- Current branch: `feat/phase1-architecture-guards`, based exactly on that main
  commit
- Current objective: Phase 1 architecture enforcement before structural migration

PR #50 is merged. It records the Phase 0 architecture, compiler, test,
semantic-pack, card-specificity, and documentation baseline on `main`. No force
push or tag movement was used.

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

## Active Phase 1 guard deliverable

The current branch turns the measured baseline into non-growth enforcement for:

- forbidden rules/domain imports from transport, application, persistence, and
  AI layers;
- mutable `GameState` ownership and direct-write growth;
- printed card-name and Oracle-ID literals in core code;
- new `CommanderEngine` methods, card-specific semantic operations, and named
  helpers;
- new oversized modules/functions and excessive engine growth;
- a content-free, refreshable card-name digest index whose reviewed allowances
  cannot change without an ADR.

Generated Markdown is presentation only; its JSON/source inputs are
authoritative. These guards preserve existing debt as an explicit compatibility
baseline; they do not assert that extraction has already occurred.

## Merge discipline

- Keep the PR focused on architecture policy, guard baselines, validators,
  focused negative tests, and the generated debt trend.
- Run focused tests locally while iterating.
- Before merge, run the repository’s exact-head local merge gate and require the
  public CI matrix to pass for the same commit.
- Merge normally, remove the merged feature branch, return to updated `main`,
  and start the Phase 1 documentation/ADR slice from a fresh branch.
- Do not alter tags or release licenses without explicit authorization.

## Next checkpoint

After this guard slice merges, create the focused Phase 1 documentation branch.
It adds the authoritative documentation index, ADR validation, link and stale-
claim checks, and the missing current architecture/testing/operations documents
before any broad new rules family is implemented.
