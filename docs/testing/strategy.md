---
title: "Testing strategy"
status: "current"
authoritative_source: "tests, quick gate, sharded PR certification, and nightly assurance"
verified: "2026-08-05"
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

During iteration, run the new/focused tests and adjacent impacted modules. The
deterministic `scripts/quick_gate.py` classifier includes both committed and
working-tree changes and selects the relevant modules, functional shards, and
validation commands. Its dry-run output is reviewable before execution.

The ordinary merge authority is the public pull-request workflow for the exact
head SHA. Ten balanced Linux functional shards run in parallel with generated
and architecture checks, package/clean-install validation, focused or complete
Windows coverage, and an isolated headless browser smoke or full journey set.
The stable `PR / Certification` job fails closed unless every required job
succeeds. Compact `main` smoke catches integration mistakes after merge; the
nightly workflow owns complete cross-platform suites, full browser journeys,
large deterministic property budgets, mutation/soak checks, current Oracle
censuses, and dependency audits.

Use `scripts/local_merge_gate.py` for releases and exceptional high-risk
persistence, replay, privacy, or packaging work, not as the default inner loop.
See the [CI pipeline guide](../development/ci-pipeline.md) for shard ownership,
two-slot worktrees, and recovery commands. The generated
[platform status](../PLATFORM_IMPLEMENTATION_STATUS.md) remains the source for
current counts.
