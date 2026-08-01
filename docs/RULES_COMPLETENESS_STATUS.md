---
title: "Rules completeness implementation status"
status: "current"
authoritative_source: "pinned rules and generated coverage artifacts"
verified: "3bb415ef898e3c013eaf78007c4169cc530111f5"
audience: "rules, compiler, and engine contributors"
maintenance: "hand-maintained"
---

# Rules completeness implementation status

This document states the current rules boundary without duplicating generated
metrics. Exact counts and source fingerprints live in
[`COMPILER_COVERAGE_STATUS.md`](COMPILER_COVERAGE_STATUS.md); architecture and
test debt live in [`ARCHITECTURE_DEBT_STATUS.md`](ARCHITECTURE_DEBT_STATUS.md).

## Claim boundary

The simulator is a deterministic, replayable partial implementation of Magic
and Commander. It does not implement the complete Comprehensive Rules or every
Oracle card interaction. A generated card program is trusted only when its
required capabilities are implemented and validated; parsing text without that
closure is not evidence of executable correctness.

Unknown or materially unresolved semantics must fail closed. A test that only
proves source inventory or parsing does not prove game behavior. Browser,
server, provider, and pilot success never promote rules fidelity by themselves.

## Implemented foundation

- A pinned Comprehensive Rules corpus, Oracle snapshot, and rulings snapshot
  support deterministic inventories and reproducible source references.
- Oracle IR v12 provides source-spanned partial compilation and material
  residuals. Generated and reviewed abilities aggregate into deterministic
  CardProgram V2 artifacts with source, capability, trust, and replay
  fingerprints. Compilation remains partial and interleaved.
- Game Record v3 records accepted commands and supports exact deterministic
  replay for represented behavior.
- The engine represents ordinary turn and priority structure, zones and object
  incarnations, the stack, mana and costs, targets and choices, state-based
  actions, combat, Commander state, and selected continuous, replacement,
  prevention, trigger, and copy behavior.
- Typed helpers exist for several rules families, but orchestration and mutation
  remain heavily centralized in `CommanderEngine`.
- Semantic packs close selected card and interaction slices. They are explicit
  overrides, not evidence of universal Oracle support.

## Known incomplete families

The generated compiler report is authoritative for exact residual categories.
The principal architectural and behavioral gaps include:

- complete continuous-effect layers, dependencies, timestamps, and CDAs;
- universal replacement/prevention event production and affected-player
  ordering;
- full alternate/additional costs, restricted mana, and cost-modification
  ordering;
- broad zone-casting permissions, special actions, face-down objects, linked
  abilities, copy effects, and merged permanents;
- complete target, search, trigger-order, loop, shortcut, multiplayer, and
  combat edge cases;
- broad fine-grained capability closure and a typed semantic-handler boundary;
- property, differential, mutation, and performance gates at the target level.

## Current migration rule

Broad card-family expansion is paused during the architecture migration. Phase
0 recorded the implementation and debt. Phase 1 added enforceable import,
mutation, card-specificity, documentation, and ADR guards. Phase 2 added the
fine-grained capability registry, and Phase 3 adds CardProgram V2. Later phases
migrate typed handlers and domain-owned state before resuming
dependency-ordered rules expansion.

Do not add a card-name branch to the core engine. A genuinely exceptional card
must use the eventual typed override boundary with source fingerprints,
capability requirements, interaction tests, replay tests, and an explicit
removal or permanence decision.

## Contributor workflow

Use the generated reports instead of hand-copying counts:

```bash
python scripts/update_architecture_audit.py --check
python simctl.py rules verify
python simctl.py rules coverage
python simctl.py rules next
```

When a coverage artifact changes intentionally, regenerate the corresponding
status document in the same commit. The repository validator rejects stale
generated outputs.
