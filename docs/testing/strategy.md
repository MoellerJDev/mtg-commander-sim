---
title: "Testing strategy"
status: "current"
authoritative_source: "tests, local merge gate, and CI workflow"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "all contributors"
maintenance: "hand-maintained"
---

# Testing strategy

Tests prove bounded behavior; generated inventories do not prove rules
correctness. Each change starts with focused tests and expands validation in
proportion to risk.

## Evidence layers

1. Unit tests cover typed values, parsers, legality predicates, and isolated
   rules helpers.
2. Transaction tests cover legal and illegal commands, rollback, costs,
   choices, state-based actions, and event ordering.
3. Replay tests prove canonical commands reconstruct the same authoritative
   state under pinned fingerprints.
4. Projection/privacy tests prove each principal sees exactly its allowed view.
5. Interaction tests cover capability pairs and high-risk multi-effect cases.
6. Browser tests prove the untrusted UI invokes the same server-issued actions
   across isolated contexts, reconnect, and persistence.
7. Generated CR/Oracle coverage records source linkage, review state, and
   residuals; it is not executable evidence by itself.

Capability evidence is an explicit generated relationship, not an inferred
test-name match. A migrated semantic family supplies positive and negative
behavior, malformed-input rollback, exact replay, and implementation-mutation
evidence. The tap-state family additionally characterizes CR 122.1d stun
replacement, effective creature types, phased-out objects, and no-op event
suppression while retaining honest blockers for the broader systems.

During iteration, run the new/focused tests and adjacent impacted modules.
Before merge, commit an immutable head, run `scripts/local_merge_gate.py` for
that exact branch/SHA, and require the public CI matrix for the same SHA. The
generated [platform status](../PLATFORM_IMPLEMENTATION_STATUS.md) is the source
for current counts.
