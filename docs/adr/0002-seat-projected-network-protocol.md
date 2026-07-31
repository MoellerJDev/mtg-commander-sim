# ADR 0002: authenticated seat projections and strict protocol 3.0

- Status: accepted
- Date: 2026-07-31

## Context

Browser bodies are untrusted, capabilities are narrow decision grants rather
than login credentials, and one seat can reconnect or open multiple tabs.

## Decision

Guest sessions authenticate a room member; the server derives the principal
from the room seat. Protocol 3.0 rejects unknown command fields and requires a
client command ID, live decision/action/capability, and expected view revision.
Every WebSocket receives only that principal's projection and owns an ephemeral
connection cursor. Reconnect begins with a full projection. Raw capabilities,
session tokens, and invite codes are excluded from durable journals.
The full projection establishes a new delivery stream even when its fresh
connection cursor restarts `pkt` at one. It replaces the client's visible event
tail; monotonic packet-number rejection applies to deltas within that stream.

## Consequences

Clients cannot select another principal or mutate authoritative fields. Delta
streams are independently hash-verifiable across tabs. Guest cookies and the
single-node SQLite control plane are an MVP identity boundary, not a substitute
for accounts, production secrets management, rate limits, or an independent
security review.
