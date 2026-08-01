---
title: "Rules kernel"
status: "current"
authoritative_source: "mtg_commander_sim engine and rules modules"
verified: "1eb40f99b7269870c7e419aa75ea3e997e7aff0e"
audience: "rules and engine contributors"
maintenance: "hand-maintained"
---

# Rules kernel

## Responsibility

The kernel validates and applies deterministic game transitions: priority,
turn structure, zones, costs, choices, stack resolution, combat, state-based
actions, represented continuous/replacement effects, and semantic programs.
It is authoritative for legality and never delegates rules decisions to a UI or
pilot.

## State and mutations

`GameState` owns players, cards, zones, stack, turn/combat state, pending
decisions, events, yields, and fidelity telemetry. During migration,
`CommanderEngine` remains the declared general mutation owner. Capability
lifecycle and replay hydration have narrowly declared compatibility ownership.
All other rules helpers return values or operate through the engine boundary.
Typed semantic handlers receive an immutable rules query and emit intents;
they cannot import the engine or state model. The intent executor calls the
existing canonical mutation methods.

## Inputs and outputs

- Inputs: a pinned `GameState`, semantic registry, server-issued action ID,
  capability-scoped choices, and deterministic randomness already represented
  in state/commands.
- Outputs: an accepted transition and events, or a typed rejection with the
  original state preserved.

## Dependencies and invariants

The rules domain may depend on model and rules helpers. It must not depend on
HTTP, WebSockets, server persistence, AI providers, or browser code. A rejected
command is transactional. Legal alternatives are currently payable, hidden
information is projected separately, and state stabilization precedes the next
priority decision.

## Extension and event participation

Reusable mechanics belong in focused rules modules and typed semantic
operations.
Triggers consume normalized events; replacements transform represented events
before final mutation; state-based actions run to a fixed point. New rules
work must identify event/replacement participation and use capability IDs from
the versioned registry once that registry is introduced.

## Visibility and replay

The kernel holds authoritative information but never builds network responses.
Every accepted strategic command is recorded and must replay to the exact state
hash with the same rules, cards, and semantics fingerprints.

## Unsupported cases and evidence

Unsupported grammar or behavior fails closed through semantic/preflight or
runtime fidelity gates. The generated
[rules status](../RULES_COMPLETENESS_STATUS.md) is the authority for remaining
families. Primary evidence is the deterministic test suite, replay tests,
privacy tests, and source-pinned conformance artifacts.
