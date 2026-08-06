---
title: "Optional pilot providers"
status: "current"
authoritative_source: "pilot interfaces, response schemas, fixed-seat tools, and provider tests"
verified: "2026-08-06"
audience: "pilot-provider implementers and arena operators"
maintenance: "hand-maintained"
concern: "optional-provider-contract"
---

# Optional pilot providers

Pilot providers are untrusted strategy clients. Gameplay, legality, rules
execution, persistence, replay, CI, and releases must operate without them or
any AI dependency. Providers observe one principal projection and choose among
that principal's server-issued actions; they never author rules effects or
write state.

## Isolation and interface

A provider implements the transport-neutral boundary:

```python
PilotProvider.decide(observation, decision, memory) -> PilotResponse
```

`observation` is the seat's full or delta packet, `decision` is its current
capability-scoped catalog, and `memory` belongs only to that principal. Each
seat receives an independent provider instance. Another seat's hand, library
order, private choices, memory, checkpoint, analyst files, and development
arbiter context are unavailable.

The built-in adapters are:

- `ScriptedPilot` for deterministic characterization and fixtures;
- `ManualJsonPilot` for one validated file/stdin response;
- `SubprocessJsonPilot` for one JSON request on stdin and one JSON response on
  stdout; and
- the optional Codex adapter described in [Codex arena](codex-arena.md).

Timeout, nonzero exit, empty output, invalid JSON, schema failure, or identity
drift is visible and fail-closed. Strict authoritative play does not invoke a
live model to resolve unknown semantics. A development arbiter, when explicitly
enabled, is a separate public/rules-scoped provider and is never multiplexed
into a strategic seat.

## Response schema

[`schemas/pilot-response.schema.json`](../../schemas/pilot-response.schema.json)
is the provider-response authority. Prefer one server-issued `action_id` with
only its delegated `choices`:

```json
{
  "action_id": "cast:A64",
  "choices": {"targets": ["B14"]},
  "plan": "DEVELOP_ENGINE",
  "reason": "Develop the engine while preserving the available interaction.",
  "confidence": 0.91,
  "yield": null,
  "memory_update": "Preserve the graveyard answer while recursion remains live."
}
```

`plan`, `reason`, `confidence`, `yield`, and `memory_update` are audit or
strategy metadata. They are removed before the engine receives the normalized
action. The schema bounds text and confidence and restricts `plan` to its
versioned strategic enum. Provider/model/thread/usage/latency fields are
injected or recorded by the runner, not trusted from an action body.

An ordered response may use `actions`, each with an `action_id`, immediate
choices, and optional declared future choices. Only the first action is
submitted immediately. A later entry runs without another provider call only
when the same principal immediately receives a new decision and the exact ID is
still legal. Another principal, material state/stack/cost/target change, hidden
draw, unsupplied private choice, combat, semantic uncertainty, save/load,
rejection, or stale identity cancels the remaining plan.

A future private search may state an intended public card name, but only the
fixed-seat server resolves it to a physical reference after that seat receives
the private candidate list. Provider output never selects a hidden physical
object it was not shown.

## Rejection and retry

A rejected response does not consume the game decision and never enters the
accepted command journal. The runner may return a compact error and the current
action catalog to the same provider instance. A retry corrects the illegal
assumption without replacing state, identity, or another seat's context.
Automatic fallback and retry status remain explicit audit facts.

## Fixed-seat tools

The fixed-seat façade binds one game directory and seat at process startup. It
exposes projected task, action submission, bounded rules lookup by visible or
legally known object reference, advisory profile, and that seat's bounded
memory. It exposes no checkpoint, run-directory browser, arbitrary file access,
cross-seat selector, state mutation, or effect DSL.

Provider identity and invocation metadata are coordinator-owned. Do not label a
manual, scripted, mock, or unavailable call as a live provider invocation. A
missing observed value stays `null`/unavailable; packet-size estimates remain
separately labeled estimates.

## Profiles and memory

Advisory deck profiles validate against
[`schemas/pilot-profile.schema.json`](../../schemas/pilot-profile.schema.json)
and bind to a canonical deck-list fingerprint. Commander/archetype fallback is
explicit, warns, and never counts as an exact profile match. Profiles and
memory guide strategy only; the engine never reads them to decide legality.

Memory is bounded and persisted independently by principal. A runner may resume
the same provider-side session, but the durable game remains valid when
provider-side context is unavailable only if the run stops honestly rather
than silently substituting identity.

## Run and resume

Use `simctl.py pilot-run --help` for the current adapter arguments. A run
directory resumes the same checkpoint, projection cursor, profiles, and seat
memory. External providers own restoration of any additional remote session
state.

See the [application protocol](../reference/protocol.md),
[visibility boundary](../architecture/visibility.md), and
[Game Record](../reference/game-record.md).
