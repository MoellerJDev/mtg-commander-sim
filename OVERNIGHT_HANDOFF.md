---
title: "Integration handoff"
status: "current"
authoritative_source: "git main and generated status artifacts"
verified: "7cc9ea1702c67519b14d2f177d82dcc8fab5458f"
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
- PR #58 merged as `7cc9ea1702c67519b14d2f177d82dcc8fab5458f`.
- The post-PR-58 reconciliation commit containing this handoff updates current
  status and generated coordinates without adding a card family.
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
schema `2`, Oracle compiler `oracle-ir-v12`, and capability registry `1/4`.
The current semantic-handler fingerprint is
`8f805ad48c179e72abb8175dd585813430b831a08d122cc7d21850535b61f9ae`.
The current global runtime-component fingerprint is
`4731c5a8ed035ef1a8da0266566bc6e81b4e1d5668369fa0d61ecb03e06c4de8`.
Snapshot dates, source hashes, capability totals, CardProgram/compiler totals,
test classes, replay/privacy/browser status, and architecture debt are generated
in the linked status reports and must not be hand-copied here.

## Trust-hardening boundary

The following remain unimplemented and must not be inferred from existing
trusted labels or compatibility tests:

- explicit capability-evidence declarations and a generated evidence index;
- separate dependency fail-closed and implementation-mutation status;
- CardProgram trust-basis accounting;
- intrinsic, format, match ambient, and dynamic closure enforcement;
- strict handler/component binding to trusted applicable closure;
- explicit compatibility provenance through canonical CardProgram identity;
- default-deny production-module classification, stable mutation identities,
  complete generic specificity scope, and exact ADR exception binding;
- a dedicated continuous-effect collection and characteristic-query benchmark.

Legacy-reviewed behavior is not capability-closed behavior. Existing runtime
components are bounded promises, not general CR 613 or CR 616 support.

## Merge discipline

- Keep each branch focused on one migration or dependency-ordered rules slice.
- Run focused tests locally while iterating.
- Before merge, run the repository’s exact-head local merge gate and require the
  public CI matrix to pass for the same commit.
- Merge normally, remove the merged feature branch, return to updated `main`,
  and start the next phase from a fresh branch.
- Do not alter tags or release licenses without explicit authorization.

## Next checkpoint

After reconciliation merges and `main` is clean, run:

```bash
git switch -c feat/runtime-trust-hardening
```

That focused phase implements the trust and governance boundary above without
adding a new card family, widening the Oracle grammar, or resuming numerical
Comprehensive Rules traversal. Its first work is explicit capability evidence
and mutation status, because later trust-basis and closure decisions depend on
that evidence model.
