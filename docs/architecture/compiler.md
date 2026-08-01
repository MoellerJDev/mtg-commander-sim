---
title: "Oracle compiler"
status: "current"
authoritative_source: "mtg_commander_sim/oracle_ir.py and pinned coverage artifacts"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "compiler and rules contributors"
maintenance: "hand-maintained"
---

# Oracle compiler

The typed Oracle compiler transforms a pinned local Scryfall record into Oracle
IR, recognized semantic nodes, dependency declarations, and material residuals.
It is deterministic for the same card/rulings snapshot and compiler version.

```mermaid
flowchart LR
    Card["Pinned Oracle card and rulings"] --> Normalize["face and text normalization"]
    Normalize --> Parse["typed source spans and templates"]
    Parse --> Lower["semantic nodes and dependencies"]
    Parse --> Residuals["classified material residuals"]
    Lower --> Gate["trust/dependency gate"]
    Residuals --> Gate
    Gate --> Program["provisional or trusted registry entry"]
```

## Invariants

- Every lowered node retains source provenance.
- Unknown grammar becomes an explicit residual rather than guessed behavior.
- Exact parsing is not equivalent to complete runtime behavior.
- A program cannot be trusted beyond the closure of its mechanics, targets,
  costs, zones, events, replacements, and runtime operations.
- The local card database is a compiler input, not an engine dependency during
  a transition.

## Extension points

Add reusable grammar and typed nodes before considering a card override. Every
new stage or CardProgram schema version requires an ADR. Update source-pinned
positive, negative, and residual tests and regenerate the authoritative JSON
and [compiler coverage report](../COMPILER_COVERAGE_STATUS.md).

Corpus-wide completeness remains unclaimed until the generated gates say
otherwise.
