---
title: "Rules completeness status"
status: "current"
authoritative_source: "pinned rules, generated coverage, capability evidence, and CardProgram census"
verified: "2026-08-05"
audience: "rules, compiler, engine, and product contributors"
maintenance: "hand-maintained"
---

# Rules completeness status

MTG Commander Sim is a deterministic, replayable **partial** implementation of
Magic and Commander. It does not implement every Comprehensive Rule or Oracle
interaction. Unsupported material behavior fails trusted preflight or stops the
game before mutation.

This page defines the claim boundary. Exact current counts and fingerprints are
generated in [compiler coverage](COMPILER_COVERAGE_STATUS.md),
[rules coverage](../coverage/rules-coverage.md),
[mechanics coverage](../coverage/mechanics-coverage.md), and the
[reusable-piece matrix](../coverage/reusable-piece-matrix.md).

## Implemented foundation

The current runtime provides:

- pinned rules, Oracle, rulings, compiler, capability, mechanic and semantic
  identities;
- CardProgram V2 with source spans, residual preservation and trust closure;
- deterministic multiplayer turn, priority, zone, stack, combat, Commander and
  state-action foundations;
- typed proposal and transaction owners for a growing set of casting,
  activation, mana, continuous, replacement, trigger, draw, life, counter,
  damage and attachment families;
- principal-scoped projections, transactional rejection and exact Game Record
  v3 command replay;
- conformance, dependency, interaction, property, privacy and mutation gates.

These foundations are reusable but bounded. A registered type or passing witness
does not imply complete coverage of its numbered rule.

## Principal incomplete areas

Material gaps remain in:

- complete continuous-effect layers, dependencies, timestamps and
  characteristic-defining abilities;
- universal replacement/prevention participation and simultaneous affected
  player/object ordering;
- alternate/additional costs, restricted mana and complete cost modification;
- unusual casting zones, special actions, face-down/merged objects, copies and
  linked abilities;
- broad target, search, trigger, loop and shortcut grammar;
- complete combat assignment, evasion, prevention and damage-result variants;
- comprehensive Oracle lowering and ambient cross-card interaction closure.

The generated dependency queue and card-unlock frontier state the exact current
blockers. Do not copy their counts or “next” selection into living prose.

## Promotion rule

A card or rule becomes trusted only when every material span lowers, every
required capability resolves, reachable interactions close for the selected
profile, and required assurance passes. Unknown, partial and reviewed
compatibility bases remain visibly distinct.

Do not add printed-name behavior to the core engine, infer support from a deck
fixture, or preserve a coverage promotion disproved by a correctness fix. Rules
work follows the family acceptance process in
the [rules assurance model](rules/assurance-model.md).
