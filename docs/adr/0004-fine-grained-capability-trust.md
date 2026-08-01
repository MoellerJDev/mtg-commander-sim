---
title: "ADR 0004: fine-grained capability trust"
status: "ADR"
authoritative_source: "this decision record"
verified: "2026-08-01"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0004"
decision_status: "accepted"
date: "2026-08-01"
---

# ADR 0004: fine-grained capability trust

## Context

The Oracle IR compiler previously gated an entire recognized node on broad
mechanic IDs such as CR 120 damage. Every mechanic contract is currently
untrusted because each describes a large rule family with known gaps. That
made it impossible to distinguish a bounded, tested base damage result from
unimplemented infect, wither, replacement ordering, or excess damage.

A compiler template match is not sufficient evidence of runtime correctness,
but waiting for an entire broad rule family also hides useful verified scope.
The trust decision must identify exactly which behavioral promises a program
uses and must fail closed when any reachable promise is untrusted.

## Decision

Add a packaged, versioned fine-grained capability registry. Each capability
has a stable ID and version, pinned rules, supported profiles, applicability,
dependencies, implementation owners, evidence classes, mutation status,
blockers, and trust status.

Compute a deterministic transitive closure for the selected profile. A closure
is trusted only when every reachable capability is present, supported by the
profile, and trusted. The registry and closure fingerprints travel with a
capability-aware generated semantic program.

Broad mechanic IDs remain as aggregate reporting views. Their blocked members
do not prevent an independent narrower closure from being trusted, and a
narrower closure does not promote the aggregate. Compiler node shapes without
a reviewed fine-grained mapping continue through the legacy mechanic-contract
gate. Existing reviewed semantic packs remain compatible while CardProgram V2
is developed.

The first migration maps the generated any-target base damage spell shape to
target revalidation and base CR 120.3 result capabilities. Damage replacement,
prevention ordering, infect, wither, lifelink composition, excess damage, and
noncombat trigger dispatch remain explicit blocked aggregate members. Those
ambient capabilities must enter a match-level closure when another reachable
program or state makes them applicable; this first slice does not claim the
full damage family is trusted.

## Alternatives

- Keep broad mechanic contracts as the only trust unit. Rejected because an
  unrelated unimplemented variant blocks every bounded implemented path.
- Trust semantic operation names directly. Rejected because an operation name
  has no versioned rules scope, dependency closure, or evidence contract.
- Treat an exact compiler template match as trusted. Rejected because parsing
  exactness does not prove runtime rules, interaction, privacy, or replay
  behavior.
- Replace all broad contracts and semantic packs at once. Rejected because a
  staged compatibility bridge is safer and independently reviewable.

## Consequences

- Capability registry changes alter trust semantics and require review plus a
  version change when compatibility demands it.
- Generated programs may carry additive direct-dependency, closure, profile,
  and fingerprint fields; legacy programs serialize unchanged.
- Missing, cyclic, unsupported-profile, blocked, and mutation-incomplete trust
  metadata fail closed.
- The compiler must add mappings incrementally. An unmapped node does not gain
  trust merely because another node family migrated.
- Match-level ambient capability reachability and CardProgram V2 pinning remain
  later phases, so normal runtime-generated programs stay provisional unless a
  caller deliberately supplies and validates a capability closure.
