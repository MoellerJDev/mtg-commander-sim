---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "2026-08-01"
audience: "maintainers continuing the migration"
maintenance: "hand-maintained"
---

# Integration handoff

This is a sanitized operational handoff. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider-session data.

## Integration coordinate

- Public repository: `MoellerJDev/mtg-commander-sim`
- Default branch: `main`; do not create `master`.
- Certified `main` is `b1ecdc0f3446a37ffe31bfca1237a079691e6b22` after
  PR #59; its five CI jobs passed in run `30725523797`.
- Active work is the focused `feat/runtime-trust-hardening` Phase 1 branch. Read
  its exact head, pull request, and CI run from `git` and `gh`; do not freeze
  pre-publication placeholders into this handoff.
- The live branch, pull request, exact-head CI, and clean-tree state must be
  read from `git`, `gh`, and the generated platform ledger rather than inferred
  from an older handoff.

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

Verified `main` contains the ratcheted architecture/documentation guards, the
versioned fine-grained capability registry, canonical CardProgram V2,
registered typed semantic handlers, canonical stack-resolution routing, and
two bounded runtime-component families: fixed additional-token replacement and
fixed same-controller subtype anthem. Generated Markdown remains presentation
only; its JSON and source inputs are authoritative.

The pinned development line is package `0.8.0`, Protocol `3.0`, CardProgram
schema `2`, Oracle compiler `oracle-ir-v12`, and capability registry `1/5`.
Snapshot dates, source hashes, capability totals, CardProgram/compiler totals,
test classes, replay/privacy/browser status, and architecture debt are generated
in the linked status reports and must not be hand-copied here.

## Trust-hardening boundary

The Phase 1 candidate implements explicit generated capability evidence,
separate dependency/implementation-mutation status, CardProgram trust bases,
intrinsic/format/match/dynamic closure, strict handler/component binding,
compatibility provenance, exact replay provenance, default-deny module and
stable-write governance, zero engine growth, and an uncached continuous-effect
structural performance baseline.

Capability-only strict match readiness remains blocked because traditional and
Commander format-wide capabilities are not yet inventoried. Reviewed
declared-pool compatibility remains separate. Several capabilities and both
bounded runtime-component families remain tested or blocked rather than
trusted. Existing components are bounded promises, not general CR 613 or CR
616 support.

## Merge discipline

- Keep each branch focused on one migration or dependency-ordered rules slice.
- Run focused tests locally while iterating.
- Before merge, run the repository’s exact-head local merge gate and require the
  public CI matrix to pass for the same commit.
- Merge normally, remove the merged feature branch, return to updated `main`,
  and start the next phase from a fresh branch.
- Do not alter tags or release licenses without explicit authorization.

## Next checkpoint

Finish the Phase 1 candidate with:

```bash
python scripts/update_capability_evidence.py --check
python scripts/update_module_classifications.py --check
python scripts/benchmark_continuous_effects.py --check
python scripts/update_architecture_audit.py --check
python scripts/update_platform_status.py --check
```

Then commit the coherent branch, run affected tests, publish one focused PR,
certify its exact head through the full local gate and public CI, merge, clean
up the branch, and refresh the main-branch ledger. Only then score the next
measured debt migration; do not resume numerical rules traversal.
