---
title: "Mechanic capability extension guide"
status: "target"
authoritative_source: "standalone goal capability trust-model specification"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "rules, compiler, and architecture contributors"
maintenance: "hand-maintained"
---

# Mechanic capability extension guide

This is target architecture for Phase 2; it is not a claim that the current
mechanic-contract registry already has fine-grained capability closure.

A capability is the smallest reviewable behavioral contract that a card
program depends on. Its versioned record will identify inputs, outputs, state
read/write scope, costs, targets, zones, events, replacement participation,
visibility, replay behavior, source rules, implementation entry points, and
executable evidence.

## Intended workflow

1. Define a stable capability ID and schema entry.
2. Implement it behind a focused domain port without adding card-name logic.
3. Add legal, illegal, rollback, replay, visibility, property/mutation, and
   relevant interaction tests.
4. Link applicable Comprehensive Rules and rulings.
5. Let the compiler declare the capability dependency.
6. Compute transitive closure; trust a program only when every reachable
   capability and runtime operation is trusted for the pinned snapshot.

Broad labels such as “combat” or “replacement effects” are not sufficient
trust units. One proven simple program should be promotable without waiting for
every behavior in the broad family. A new registry schema or trust semantic
requires an ADR.
