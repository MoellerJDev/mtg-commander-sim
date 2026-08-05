---
title: "ADR 0022: reusable rules-piece inventory"
status: "ADR"
authoritative_source: "this decision record"
verified: "2026-08-05"
audience: "compiler, rules, assurance, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0022"
decision_status: "accepted"
date: "2026-08-05"
---

# ADR 0022: reusable rules-piece inventory

## Context

The repository already has authoritative rules, mechanic, capability,
CardProgram, runtime-component, compiler-coverage, and card-unlock-frontier
artifacts. They answer different questions with different units, obscuring
shared semantic dependencies and interaction evidence. Cards, Oracle sentences,
numbered rules, and broad mechanics are each too coarse or too specific to be
the only reusable implementation unit. A new trust registry would also compete
with existing authorities.

## Decision

Add a versioned, generated reusable-piece inventory that joins existing
authorities without superseding them. The ontology has closed classes and
relation types. Each piece has independent inventory, compiler, runtime,
assurance, corpus, and interaction axes. Card relations retain ability IDs and
source authority. Card-text-shaped residual clusters collapse to a shared
missing grammar boundary while retaining raw frontier identities.

The generator covers every material ability in the pinned Commander frontier,
all registered capabilities and mechanics, all registered runtime handlers and
components, and their current rule/evidence links. It emits per-card and
interaction indexes, a complex-card composition benchmark, and a durable
point-in-time baseline with deterministic fingerprints.

The matrix is reporting infrastructure only. Runtime legality, mutation,
trust, replay, and privacy remain owned by existing typed subsystems.
Snapshot-complete is fail-closed and cannot be inferred from inventory or one
witness.

The reviewed architecture baselines advance with this ADR after the new
inventory modules are scanned against the pinned card-name index. The refresh
records ordinary schema vocabulary that is also printed on cards, while the
guard continues to reject any later unreviewed literal or growth in an existing
oversized function. Inventory orchestration and CLI registration are extracted
at coherent boundaries so this refresh does not waive new size debt.

## Alternatives

- Use the card-unlock frontier alone. Rejected because it omits represented
  pieces and their interactions.
- Make one piece per Oracle sentence. Rejected because prose clusters are not
  reusable semantic ownership boundaries.
- Make one piece per numbered rule. Rejected because primitives and rules have
  a many-to-many relationship.
- Replace capability and mechanic registries. Rejected because they already
  own trust and rule-contract semantics.
- Hand-maintain a planning spreadsheet. Rejected because joins, fingerprints,
  and pinned corpus counts would drift.

## Consequences

- Rules-family selection can use reusable sole/paired blockers and interaction
  risk without claiming that ranking proves correctness.
- Compiler and runtime progress can be compared with a durable adoption
  baseline while pinned snapshots remain unchanged.
- Ontology changes require explicit schema/policy review; ordinary registry and
  compiler additions flow into generated output.
- The per-card index is larger than the summary matrix, but inspection is
  index-backed and game runtime is unaffected.
- Official ruling presence is counted; behavioral ruling classification remains
  an explicit future boundary.
