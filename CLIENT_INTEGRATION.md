# Client Integration and Permission Boundary

## Goal

A future desktop/web MTG client should reuse the simulation service without changing how game actions are authorized. UI code may render richer state, animations, card images, clocks, and prompts, but it never receives direct mutation access.

## Transport-neutral core

`GameService` exposes two concepts:

```python
service.observe(authenticated_principal, full=False)
service.command(CommandEnvelope(...), principal=authenticated_principal)
```

A transport adapter is responsible for:

1. authenticating a user/agent connection
2. mapping that connection to one game principal
3. forwarding observations
4. forwarding capability-scoped commands
5. persisting/reconnecting projection cursors

The server—not the request body—determines the authenticated principal.

## Suggested HTTP/WebSocket surface

```text
POST /games
GET  /games/{game_id}/projection?full=1
POST /games/{game_id}/commands
GET  /games/{game_id}/rules?ref=A44
WS   /games/{game_id}/stream
```

Example command body:

```json
{
  "game_id":"game-uuid",
  "capability":"c_opaque",
  "action":"cast",
  "payload":{"card":"A12","targets":["S4"],"auto_pay":true}
}
```

The connection identity supplies `principal`; the client-controlled command body does not contain it. `GameService.command(..., principal=...)` accepts the principal only as trusted transport metadata.

## Capability checks

Every command is validated against:

- game ID
- authenticated principal
- unconsumed capability token
- live decision ID
- role
- actor/seat
- allowed action name

Invalid actions roll back transactionally. A capability is consumed only by an accepted response within its decision group.

Capabilities are not reusable API keys. They are narrow authorization grants for one rules decision.

## Projection synchronization

Protocol 2.1 provides:

- initial `state`
- `base` and `view` hashes
- JSON `patch` operations
- explicit current `decision`
- definitions and visible events

A client should use `ProjectedClientView` or implement equivalent logic:

```python
view = ProjectedClientView("pilot:A")
view.ingest(packet)
```

When a delta's `base` differs from the local hash, request `full=1`. Never apply a patch to an unknown base.

## Hidden information

Each connection receives a principal-specific projection. A spectator does not receive hands. A pilot receives its own hand and legally known opposing cards. The arbiter receives public state and resolution context, not all private hands. Analyst access should be disabled during live adversarial play unless the environment explicitly permits it.

## UI action generation

The server packet contains the capability's allowed action categories and context. A client can render buttons/forms from these categories, but final legality still belongs to the engine.

Examples:

- `mulligan.declare` → Keep / Mulligan
- `priority` → pass, land, cast, activate
- `combat.attackers` → attacker-to-defender mapping
- `combat.blockers` → blocker-to-attacker mapping for that defender
- `state.legend` → choose one object to keep
- `arbiter.resolve` → rules effect form; never shown to ordinary pilots

## Persistence model

Recommended server persistence separates:

- authoritative `GameState`
- semantic registry
- projection cursor by `(game_id, principal, connection/client_id)`
- append-only events/metrics
- authentication and seat assignment

A client reconnect can request a full projection, so cursors are an optimization rather than a correctness dependency.

## Security notes

- Do not accept principal/seat in a client-controlled body, and do not trust role, controller, mana payment, cast zone, cost overrides, or effect operations from a client.
- Do not expose authoritative save files to pilots.
- Do not use capability tokens as long-lived session authentication.
- Rate-limit rejected commands.
- Log capability issuance and consumption without logging private hand contents to public telemetry.
- Keep analyst/admin endpoints separate from player transport.

## Why the GUI does not require a permission refactor

The client speaks the same projected-state and capability-command protocol as an LLM pilot. A native client replaces the model callback and renders packets; it does not replace the engine, permissions, state projection, or command envelope.
