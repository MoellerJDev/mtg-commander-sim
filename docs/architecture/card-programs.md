---
title: "CardProgram architecture"
status: "current"
authoritative_source: "quorune/card_programs and schemas/card-program-v2.schema.json"
verified: "2026-08-06"
audience: "compiler, rules, replay, and extension contributors"
maintenance: "hand-maintained"
---

# CardProgram architecture

`CardProgram` is the canonical, deterministic artifact that connects pinned
Oracle input to runtime behavior. One artifact groups the executable abilities
for an Oracle ID and records face identity, source hashes, provenance, typed
nodes, material residuals, capability dependencies, trust basis, and a single
artifact fingerprint. The versioned JSON schema is the serialization authority.

## Ownership and flow

`quorune/card_programs/` owns validation, deterministic
serialization, adapters, inspection, and source-identity checks. It does not
own `GameState` and cannot mutate a game. The compiler produces typed nodes and
residuals; the registry combines generated and reviewed inputs; strict
preflight binds the resulting program to capability, handler, and component
fingerprints. Runtime code executes only registered typed operations. It never
parses Oracle prose during a state transition.

A reviewed ability may replace generated output only for the same stable
semantic key. Ambiguous ability identity, conflicting nonempty hashes, stale
source data, unknown dependencies, material residuals, or fingerprint drift
fail closed. Historical semantic-pack records remain compatibility inputs, not
a second current runtime authority.

## Trust and replay

- Parsing success does not imply complete rules support.
- Trust cannot exceed the closure of targets, costs, zones, events,
  replacements, runtime operations, and the selected rules profile.
- Unregistered or provisional behavior remains explicit; registration never
  promotes a program by itself.
- Game records pin the program and applicable registry fingerprints. Replay
  validates those values when present and uses the recorded artifact rather
  than silently recompiling it with a newer compiler.
- Program descriptors may participate in later events through runtime
  components, but those components receive bounded immutable contexts and do
  not mutate state.

## Inspection and extension

Use `simctl.py card compile`, `explain`, `audit`, `diff`, `trust-closure`, and
`runtime-components` against a pinned local card database. Inspection output
is derived from the canonical artifact; it is not an additional source of
truth.

Add reusable grammar and typed nodes before considering a card-specific
override. Preserve source spans, add positive and negative compiler fixtures,
declare exact capability dependencies, and regenerate owned reports. New
schema versions or changed architectural ownership require an ADR.

See [ADR 0005](../adr/0005-card-program-v2.md),
[ADR 0008](../adr/0008-runtime-trust-and-governance-hardening.md), the
[Oracle IR reference](../reference/oracle-ir.md), the
[compiler architecture](compiler.md), the
[typed-handler boundary](semantic-handlers.md), the
[runtime-component boundary](runtime-components.md), and the
[trust-closure model](trust-closure.md).
