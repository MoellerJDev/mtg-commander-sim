---
title: "Quorune Pilot Harness adapter"
status: "current"
authoritative_source: "optional pilot configuration, fixed-seat tools, and compatibility commands"
verified: "2026-08-07"
audience: "pilot-harness operators and provider contributors"
maintenance: "hand-maintained"
concern: "codex-arena-adapter"
---

# Quorune Pilot Harness adapter

The Quorune Pilot Harness is an optional protocol-adapter experiment. It is not product
execution, a rules authority, or a CI/merge/release dependency. One neutral
coordinator routes tasks to persistent seat-isolated strategy sessions. The
coordinator is not a player and never chooses or replaces a seat action.

## Roles and trust boundary

The logical roles are one public coordinator and one persistent provider
session for each seat. A session receives only its fixed-seat projected task,
advisory profile, and bounded memory. It cannot read the run directory, switch
seats, invoke an effect DSL, spawn another game authority, or inspect another
seat's private context.

Custom instructions are not an operating-system security boundary. The server's
fixed-seat façade enforces game authority. Use an isolated read-only workspace
when filesystem isolation must also be demonstrated.

Provider, model, reasoning, service tier, thread identity, invocation, usage,
latency, retry, interruption, and restart facts must reflect the actual runtime.
Do not encode a recommended model or transient host capacity in this document;
choose the available provider configuration explicitly and journal it.

## Create and run

Create a game with current commands discovered through help:

```powershell
.\.venv\Scripts\python.exe simctl.py arena-create --help
.\.venv\Scripts\python.exe simctl.py arena-codex-run --help
```

Use the primary four-player review profile for harness evidence unless the user
requests a bounded duel regression. Strict evidence runs use trusted-only
semantics. An explicitly development-only run may stop at a scoped arbiter
boundary, but live improvisation cannot become rules or deck evidence.

Start every requested seat session once and retain its actual identity. A
runner may bootstrap independent sessions concurrently, but game decisions are
routed in authoritative principal order. If a recorded session cannot resume,
stop and record the restart/fidelity failure; do not silently substitute a new
session.

## Coordination loop

1. Validate deck, profile, card snapshot, and strict semantic policy.
2. Read the next principal and public fidelity state from the coordinator
   surface.
3. Route a player task only to that seat's original provider session.
4. Submit strict schema-valid output through the fixed-seat façade.
5. Return compact rejection context only to the same session.
6. Apply a legal seat action even when the coordinator dislikes its strategy.
7. Stop on rules/semantic uncertainty, material fidelity failure, identity
   drift, or any suppressed meaningful window.
8. Persist every accepted action and periodically verify the accepted prefix.

A provider message to the coordinator may contain status, accepted decision
identity, sanitized error, and next-principal boundary. It must not echo a
private hand, library fact, private choice, memory, raw capability, or task
packet. App-level disclosure is a fidelity failure even if durable projection
audits remain clean.

Ordered plans follow the provider contract and stop on another principal,
material state change, hidden draw, invalid target or cost, unsupplied choice,
combat, uncertainty, rejection, or save/load.

## Stop, resume, and evidence

Stop at the requested boundary, terminal result, unsupported semantic, or
fidelity failure. Preserve an unfinished game as paused or in progress with its
exact reason; never fabricate a result. Resume only the recorded session
identities and the checksummed game record.

At handoff or finalization:

- save the authoritative record;
- verify exact accepted-command-prefix replay;
- regenerate derived review and hidden-information audit;
- report provider/infrastructure failures separately from strategy findings;
- confirm no meaningful window was suppressed; and
- classify duplicated-deck or unfinished fixtures only as protocol/pilot
  evidence.

Deck or matchup claims require trusted material semantics, terminal verified
games, exact profiles, genuine strategic providers, privacy/legal-action
evidence, and a predeclared multi-game methodology.

See [provider contract](providers.md), [protocol](../reference/protocol.md),
[Game Record](../reference/game-record.md), and the agent-only
[Pilot Harness skill](../../.agents/skills/commander-arena/SKILL.md).
