# Client Integration and Permission Boundary

## Goal

The browser client reuses the simulation service without changing how game
actions are authorized. UI code may render richer state, animations, card
presentation, clocks, and prompts, but it never receives direct mutation
access.

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

The in-process boundary and the listening FastAPI adapter both use protocol
3.0. `schemas/command-envelope.schema.json` rejects unknown properties and
requires client command/decision/action IDs plus the expected projected-state
revision. The authenticated guest's room seat—not the request body—selects the
principal.

## HTTP/WebSocket surface

```text
POST /api/v1/guests
POST /api/v1/rooms
POST /api/v1/rooms/join
PUT  /api/v1/rooms/{room_id}/deck
POST /api/v1/rooms/{room_id}/start
GET  /api/v1/games/{game_id}
GET  /api/v1/games/{game_id}/state?full=true
POST /api/v1/games/{game_id}/stop
POST /api/v1/games/{game_id}/resume
POST /api/v1/games/{game_id}/commands
WS   /api/v1/games/{game_id}/stream
```

The game-inspection response is an application projection containing only safe
lifecycle metadata and journal counts. Stop/resume are room-owner operations,
not pilot actions: they never accept a seat or principal in the body and never
mint an engine capability. The WebSocket carries the same lifecycle projection
beside each ordinary seat packet. Clients must disable action submission while
status is not `active`; the service independently enforces that rule.

Example command body:

```json
{
  "protocol_version":"3.0",
  "game_id":"game-uuid",
  "command_id":"web-7b63b",
  "decision_id":"D14",
  "action_id":"cast:A12",
  "capability":"opaque-single-use-token",
  "expected_view_revision":37,
  "choices":{"targets":["S4"]}
}
```

The connection identity supplies `principal`; the client-controlled command body does not contain it. `GameService.command(..., principal=...)` accepts the principal only as trusted transport metadata.

## Capability checks

Every command is validated against:

- protocol version and strict field set
- game ID
- client command idempotency key
- expected projected-state revision
- authenticated principal
- unconsumed capability token
- live decision ID
- role
- actor/seat
- allowed action name

Invalid actions roll back transactionally. A capability is consumed only by an accepted response within its decision group.

Capabilities are not reusable API keys. They are narrow authorization grants for one rules decision.

## Projection synchronization

Protocol 3.0 provides:

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

When a delta's `base` differs from the local hash, reconnect or request
`full=true`. Never apply a patch to an unknown base. Every WebSocket connection
has an independent ephemeral cursor, so a second tab or reconnect cannot move
the first tab's delta base.

## Hidden information

Each connection receives a principal-specific projection. An invited spectator
is authenticated as a room member but receives principal `spectator`, no hand,
no decision capability, and no command authority. A pilot receives its own hand
and legally known opposing cards. The arbiter receives public state and
resolution context, not all private hands. Analyst access should be disabled
during live adversarial play unless the environment explicitly permits it.

The WebSocket event tail is bounded delivery context. To render the complete
public history, an authenticated player or spectator paginates
`GET /api/v1/games/{game_id}/events`. The response uses one fixed public event
shape and never includes raw details. A client must not read the Game Record
directory, checkpoint, or analyst artifacts directly.

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

Server persistence separates:

- authoritative `GameState`
- semantic registry
- ephemeral projection cursor by `(game_id, principal, connection_id)`
- append-only events/metrics
- authentication and seat assignment

A client reconnect receives a full projection, so cursors are an optimization
rather than a correctness dependency. SQLite contains the control plane and
hashed idempotency receipts; Game Record v3 contains authoritative game state
and accepted-command replay truth.

## Security notes

- Do not accept principal/seat in a client-controlled body, and do not trust role, controller, mana payment, cast zone, cost overrides, or effect operations from a client.
- Do not expose authoritative save files to pilots.
- Do not use capability tokens as long-lived session authentication.
- Rate-limit rejected commands.
- Log capability issuance and consumption without logging private hand contents to public telemetry.
- Keep analyst access separate from the safe game-member lifecycle
  projection; never turn inspection into a record-path or checkpoint endpoint.

## Why the GUI does not require a permission refactor

Every browser, native, scripted, subprocess, or optional AI client speaks the
same projected-state and capability-command protocol. A new client renders and
submits packets; it does not replace the engine, permissions, state projection,
or command envelope.
