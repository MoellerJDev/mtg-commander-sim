---
title: "Card programs"
status: "current"
authoritative_source: "mtg_commander_sim/semantics.py, capability registry, and semantic pack schemas"
verified: "2026-08-01"
audience: "compiler, rules, and semantic-pack contributors"
maintenance: "hand-maintained"
---

# Card programs

A `SemanticProgram` is immutable, source-pinned executable metadata associated
with an Oracle identity. Schema v3 records zones, abilities, effects, targets,
triggers, trust metadata, source hashes, and dependency evidence. The registry
merges reviewed packs and provisional compiler output while rejecting
incompatible or conflicting definitions.

Capability-aware generated programs may also carry additive direct capability
IDs and the resolved profile-scoped closure with registry and closure
fingerprints. Programs without those fields retain their prior serialized
shape. This is the compatibility rail for CardProgram V2, not CardProgram V2
itself.

## Trust boundary

- Reviewed packs may be trusted only when their source fingerprints and tests
  match.
- Compiler output remains provisional when any material residual or dependency
  is unresolved.
- A capability-aware compiler promotion requires every member of the exact
  transitive closure to be trusted for the selected profile.
- Broad mechanic aggregate status neither grants nor revokes a smaller exact
  closure; unmigrated nodes keep using the conservative broad-contract gate.
- Game creation pins the semantic registry fingerprint. A saved game is not
  silently upgraded by a later pack.
- Runtime execution accepts registered operations only. Unknown operations and
  semantically incomplete paths fail closed.

## Current execution model

Programs subscribe to represented events or define cast/activated/resolution
behavior. `CommanderEngine` performs the actual mutations through generic
effect operations, target selection, choice continuations, trigger collection,
and stabilization. A program does not receive arbitrary Python or game-state
write authority.

## Target CardProgram v2 boundary

The migration target replaces broad mechanic trust with fine-grained capability
dependency closure and makes every node's inputs, outputs, targeting, zones,
visibility, and replay contract explicit. That target is not implemented merely
because equivalent fields exist in current semantic packs. Schema changes,
trust changes, or a new extension interface require an ADR.

See the [semantic-node guide](../extension/semantic-node.md),
[override guide](../extension/card-override.md), and generated
[compiler status](../COMPILER_COVERAGE_STATUS.md).
