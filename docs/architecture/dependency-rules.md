---
title: "Dependency and mutation rules"
status: "current"
authoritative_source: "platform/architecture-policy.json and architecture validator"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "all code contributors"
maintenance: "hand-maintained"
---

# Dependency and mutation rules

The executable policy in `platform/architecture-policy.json` is authoritative.
This document explains its intent.

```mermaid
flowchart LR
    Browser["browser"] --> Server["transport/adapters"]
    Server --> Application["service/session"]
    Application --> Rules["rules/domain"]
    Rules --> Model["typed model/value objects"]
    Compiler["compiler/semantic data"] --> Rules
    Persistence["persistence adapters"] --> Application
```

Dependencies point toward the domain. Protected rules/domain modules may not
import server frameworks, WebSockets, persistence adapters, AI providers, or
application/session orchestration. Compiler and metadata code may describe
rules programs but may not acquire runtime mutation authority.

`CommanderEngine` remains a measured legacy mutation boundary while it is
decomposed. New engine methods, direct `GameState` write sites, card-name/Oracle
ID branches, card-specific operations/helpers, oversized modules/functions, or
unreviewed dependency exceptions fail the architecture gate. Existing debt is
ratcheted rather than endorsed.

Any new subsystem documents ownership and dependencies. Changing mutation
ownership or adding a cross-layer dependency requires an ADR. Reviewed legacy
exceptions require an ADR and removal plan; routine Scryfall digest refreshes
cannot alter the reviewed specificity allowance.
