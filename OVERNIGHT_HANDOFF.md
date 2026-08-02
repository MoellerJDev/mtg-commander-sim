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
- Certified `main` is `e756950d52030b47a6cf81edcd7d7f60ca11d97e` after
  PR #60; its five CI jobs passed in run `30729318546`.
- Phase 1 is integrated and its feature branch is deleted. Active work is the
  focused `feat/typed-tap-untap-effects` Phase 2 migration based directly on
  certified `main`; its exact-head merge gate and public CI are still pending.
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
schema `2`, Oracle compiler `oracle-ir-v12`, and capability registry `1/6` on
the current feature branch.
Snapshot dates, source hashes, capability totals, CardProgram/compiler totals,
test classes, replay/privacy/browser status, and architecture debt are generated
in the linked status reports and must not be hand-copied here.

## Integrated trust-hardening boundary

Phase 1 implements explicit generated capability evidence,
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

## Active typed tap-state migration

The current branch registers `tap`, `untap`, and `untap_all_creatures` in a
dedicated semantic family, lowers them to typed intents, and commits them
through the classified `tap_state.py` mutation port. The legacy
`apply_effect` branches are removed. Focused evidence covers strict schemas,
no-op event suppression, stun-counter replacement, effective creature types,
phased-out objects, rollback, replay, and implementation mutations. The
architecture audit reports a negative engine delta with no new direct-write
identity or specificity debt.

These capabilities use registry `1/6` and remain `tested`, not `trusted`.
Complete tap/untap prohibitions, general replacement ordering, and complete
derived-characteristic closure remain explicit blockers. This slice does not
upgrade legacy-reviewed CardPrograms or claim complete CR 701.26/122.1d
interactions.

## Merge discipline

- Keep each branch focused on one migration or dependency-ordered rules slice.
- Run focused tests locally while iterating.
- Before merge, run the repository’s exact-head local merge gate and require the
  public CI matrix to pass for the same commit.
- Merge normally, remove the merged feature branch, return to updated `main`,
  and start the next phase from a fresh branch.
- Do not alter tags or release licenses without explicit authorization.

## Next checkpoint

Finish documentation/generator reconciliation and validate the focused branch:

```bash
python scripts/update_capability_evidence.py --check
python scripts/update_module_classifications.py --check
python scripts/benchmark_continuous_effects.py --check
python scripts/update_architecture_audit.py --check
python scripts/update_platform_status.py --check
```

Commit the coherent branch, run `scripts/local_merge_gate.py` against that
exact SHA, and keep its Playwright/server work headless with `--no-open`.
Require the public CI matrix for the same SHA before merge. After normal merge
and branch cleanup, select the next coherent migration from fresh certified
`main`; do not resume numerical rules traversal.
