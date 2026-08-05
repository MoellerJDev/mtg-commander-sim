---
title: "Runtime containers"
status: "current"
authoritative_source: "mtg_commander_sim, server, web, platform, and coverage trees"
verified: "2026-08-05"
audience: "contributors and operators"
maintenance: "hand-maintained"
---

# Runtime containers

```mermaid
flowchart TB
    subgraph Client["Untrusted clients"]
        Web["web/ React client"]
        Providers["manual, scripted, subprocess, Codex providers"]
    end
    subgraph Application["Application layer"]
        Api["server/ HTTP and WebSocket adapters"]
        Actor["single-writer GameActor"]
        GameService["GameService command boundary"]
    end
    subgraph Domain["Rules and session boundary"]
        Session["CommanderSession"]
        Engine["CommanderEngine legacy kernel"]
        Projection["StateProjector"]
        Registry["SemanticRegistry and Oracle IR"]
    end
    subgraph Storage["Local storage"]
        ServerDb["room/session SQLite"]
        Records["Game Record v3 directories"]
        CardDb["Scryfall SQLite snapshots"]
        Images["on-demand image cache"]
    end
    Web --> Api --> Actor --> GameService --> Session --> Engine
    Providers --> GameService
    Session --> Projection --> Api
    Engine --> Registry
    Actor --> Records
    Api --> ServerDb
    Api --> CardDb
    Api --> Images
```

## Ownership

- `CommanderEngine` is the legacy authoritative mutation boundary during the
  migration. New mutation owners are prohibited by policy.
- `CommanderSession` manages capabilities, projected decisions, yields, and the
  ordered command protocol around the engine.
- `GameService` validates command envelopes, idempotency, authorization, and
  persistence before acknowledgement.
- `server/` owns guest/room lifecycle, one actor mailbox per game, HTTP and
  WebSocket transport, managed data, and browser assets.
- `StateProjector` is read-only and emits principal-scoped views.

The dependency policy is executable in `scripts/validate_architecture.py`.
Measured migration debt and allowed legacy exceptions live in generated and
machine-readable architecture artifacts, not in this document.
