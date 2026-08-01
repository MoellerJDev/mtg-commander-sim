---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "3bb415ef898e3c013eaf78007c4169cc530111f5"
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
- Current program boundary: finish the focused Phase 3 CardProgram V2 slice,
  then begin Phase 4 typed semantic handlers. Broad rules expansion remains
  paused until the migration rails are integrated.

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

## Integrated migration rails

Verified `main` contains the Phase 1 ratcheted architecture/documentation
guards and the Phase 2 versioned fine-grained capability registry. The active
Phase 3 branch adds canonical CardProgram V2 aggregation, deterministic
serialization, generated/reviewed compatibility adapters, source and trust
validation, inspection commands, and additive Game Record v3 fingerprints.
Generated Markdown remains presentation only; its JSON/source inputs are
authoritative.

## Merge discipline

- Keep each branch focused on one migration or dependency-ordered rules slice.
- Run focused tests locally while iterating.
- Before merge, run the repository’s exact-head local merge gate and require the
  public CI matrix to pass for the same commit.
- Merge normally, remove the merged feature branch, return to updated `main`,
  and start the next phase from a fresh branch.
- Do not alter tags or release licenses without explicit authorization.

## Next checkpoint

After CardProgram V2 merges, Phase 4 replaces central string dispatch with
typed semantic handlers without widening card coverage. The generated platform
and compiler status reports are the exact source for the live next task and
remaining blockers.
