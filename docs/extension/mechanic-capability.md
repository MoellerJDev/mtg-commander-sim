---
title: "Mechanic capability extension guide"
status: "current"
authoritative_source: "mtg_commander_sim/rules/capabilities.py, its packaged registry, and ADR 0004"
verified: "2026-08-03"
audience: "rules, compiler, and architecture contributors"
maintenance: "hand-maintained"
---

# Mechanic capability extension guide

Capability registry version 13 is the current incremental trust boundary beside the
legacy broad mechanic contracts. The initial migration covers the generated
base-damage spell shape and its public target/base-result dependencies. It is
not a claim that the broad damage family or all compiler nodes have migrated.

A capability is the smallest reviewable behavioral contract that a card
program depends on. Its versioned record will identify inputs, outputs, state
read/write scope, costs, targets, zones, events, replacement participation,
visibility, replay behavior, source rules, implementation entry points, and
executable evidence.

`CapabilityRegistry.closure()` resolves a deterministic transitive graph for
one supported rules profile. Missing IDs, cycles, unsupported profiles, blocked
dependencies, retained blockers, and incomplete trust evidence fail closed.
The registry fingerprint, generated evidence fingerprint, and closure
fingerprint make the exact evaluation auditable.

Evidence relationships live in
`platform/capability-evidence-declarations.json` and are compiled into the
packaged `capability-evidence.json`. Each declaration names a fully qualified
test, evidence class, official rules, profiles, and applicability. The
validator discovers test identities from the AST; removed or renamed tests,
unknown rules/profiles, contradictory declarations, and registry-validation
tests used as behavioral evidence fail CI.

Dependency fail-closed and implementation mutation statuses are independent.
A trusted capability with dependencies requires a passed dependency test and
must have killed implementation mutation evidence. `not_applicable` requires a
reviewed rationale.

Broad mechanic aggregates are reporting and migration views. A trusted narrow
closure does not promote its broad aggregate. Conversely, a blocked aggregate
member such as infect does not block a program whose reachable node closure
does not use infect. Ambient effects must be added when match-level reachability
makes them applicable; that integration remains part of CardProgram V2 and
preflight work.

## Intended workflow

1. Define a stable capability ID and schema entry.
2. Implement it behind a focused domain port without adding card-name logic.
3. Add explicit legal, illegal, rollback, replay, visibility, property, and
   implementation-mutation evidence declarations plus relevant interaction
   tests.
4. Link applicable Comprehensive Rules and rulings.
5. Let the compiler declare the direct capability dependency without removing
   the legacy fallback for unmigrated node shapes.
6. Compute transitive closure; trust a program only when every reachable
   capability and runtime operation is trusted for the pinned snapshot.

Broad labels such as “combat” or “replacement effects” are not sufficient
trust units. One proven simple program should be promotable without waiting for
every behavior in the broad family. A new registry schema or trust semantic
requires an ADR.

The authoritative transport shape is
[`rule-capability-registry.schema.json`](../../schemas/rule-capability-registry.schema.json).
The first decision and compatibility rules are in
[ADR 0004](../adr/0004-fine-grained-capability-trust.md).
