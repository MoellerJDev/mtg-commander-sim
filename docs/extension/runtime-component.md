---
title: "Runtime-component extension guide"
status: "current"
authoritative_source: "semantic runtime registries, CardProgram V2 schema, and architecture policy"
verified: "2026-08-01"
audience: "rules, compiler, and semantic-runtime contributors"
maintenance: "hand-maintained"
---

# Runtime-component extension guide

Add a runtime component only for a reusable behavior that participates outside
one immediate semantic instruction. Do not add a component merely to move one
card-name branch behind a generic-looking descriptor.

## Checklist

1. Define the bounded family, exact CR references, event or layer, inputs,
   outputs, exclusions, visibility contract, and replay semantics.
2. Define a closed descriptor schema with stable component instance and handler
   IDs, schema version, source ability ID, and direct capability dependencies.
3. Give the handler only the minimal immutable query/context it needs. It must
   not import the engine, mutable state, session, projection, or record code.
4. Return typed intents, replacement candidates, triggers, constraints, or
   continuous effects. Route mutation through the canonical owner.
5. Register the family in its family-specific registry and aggregate metadata
   through the global inventory. Never put all family logic into the global
   registry.
6. Add positive, negative, malformed-descriptor, rollback, interaction,
   multiplayer/privacy where applicable, replay, and implementation-mutation
   evidence.
7. Bind every handler dependency at strict preflight and include component and
   CardProgram fingerprints in replay provenance.
8. Add performance instrumentation when the component participates in a hot
   query. Do not add caching without exact invalidation.
9. Remove the legacy branch and record the corpus/architecture delta. A third
   substantially similar override must be generalized.

A new extension interface or handler-family contract requires an ADR. Widening
an existing bounded component also requires new rules/evidence and must not
inherit trust from its narrower predecessor.

See [runtime-component architecture](../architecture/runtime-components.md),
[trust closure](../architecture/trust-closure.md), and the
[semantic-node guide](semantic-node.md).
