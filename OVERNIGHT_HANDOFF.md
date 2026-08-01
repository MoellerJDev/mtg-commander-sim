---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "65fb55cc7c6dd2ccb1cee517860dd99e2aefe67d"
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
- Verified main commit: `65fb55cc7c6dd2ccb1cee517860dd99e2aefe67d`
- Verified CI: [run 30705718025](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30705718025)
- Current branch: `feat/phase0-architecture-audit`, based exactly on that main
  commit
- Current objective: Phase 0 current-state audit before structural migration

PR #49 is merged. Its saved Auto-pass/Full control and Auto-mana/Manual mana
policies, resilient card-scoped drag/drop, and public tapped orientation are on
`main`. No force push or tag movement was used.

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

## Active Phase 0 deliverable

The current branch must establish reproducible machine-readable baselines for:

- module and function size, import shape, engine responsibility spread, and
  direct `GameState` mutation;
- printed card-name and Oracle-ID literals in core code;
- semantic operations, packs, duplicate override keys, and card-specific
  helpers;
- compiler stages, corpus coverage, residuals, and capability gaps;
- Python/browser test classes and missing quality gates;
- required-document presence and metadata drift.

Generated Markdown is presentation only; its JSON/source inputs are
authoritative. Phase 0 does not assert that the proposed ownership boundaries
have already been implemented.

## Merge discipline

- Keep the PR focused on audit sources, generators, current status documents,
  and stale-output validation.
- Run focused tests locally while iterating.
- Before merge, run the repository’s exact-head local merge gate and require the
  public CI matrix to pass for the same commit.
- Merge normally, remove the merged feature branch, return to updated `main`,
  and start Phase 1 from a fresh branch.
- Do not alter tags or release licenses without explicit authorization.

## Next checkpoint

After Phase 0 merges, create `feat/phase1-architecture-enforcement`. Phase 1
adds forbidden-import, mutation-ownership, card-specificity, generated-document,
documentation-index, and ADR enforcement before any broad new rules family is
implemented.
