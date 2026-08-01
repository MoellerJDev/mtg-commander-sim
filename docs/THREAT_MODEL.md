---
title: "Threat model"
status: "current"
authoritative_source: "implemented local server, protocol, projection, and repository controls"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "maintainers, security reviewers, and deployers"
maintenance: "hand-maintained"
---

# Threat model

## Scope and assets

This model covers the single-process local browser/server application and
optional pilot tools. Protected assets include hidden zones and choices,
library order, raw action capabilities, guest/invite tokens, pilot memory,
authoritative checkpoints, game integrity, exact replay evidence, local file
paths, provider credentials, and third-party card content.

## Trust boundaries

- Browser input, WebSocket messages, deck URLs, pilot responses, and subprocess
  output are untrusted.
- `GameService`, the serialized game actor, and `CommanderEngine` form the
  state-changing trust boundary.
- `StateProjector` is the disclosure boundary.
- SQLite/Game Records and managed card snapshots are local trusted storage, but
  their contents must still be validated and fingerprinted.
- Scryfall and Moxfield are external data sources, not runtime rules authorities.
- Custom-agent instructions are policy, not an operating-system sandbox.

## Principal threats and controls

| Threat | Current control | Residual risk |
|---|---|---|
| Forged seat/action | HttpOnly guest binding, CSRF, server-derived principal, single-use scoped capability | Local guest identity is not a production account system |
| Hidden-data disclosure | principal projection, spectator projection, filtered logs, negative privacy tests | New fields require explicit projection review |
| Concurrent/double mutation | one actor mailbox, expected revision, idempotency, durable acknowledgement | Multi-process actor ownership is unsupported |
| Replay or data drift | engine/card/semantic/deck fingerprints and exact replay | Unsupported legacy records fail closed rather than migrate invisibly |
| Filesystem/path escape | fixed server roots and whitelisted pilot tools | Local process compromise is outside application isolation |
| SSRF/content abuse | fixed Moxfield adapter and Scryfall image host/size/type checks | Public-host egress and abuse controls are not implemented |
| Secret leakage in Git | ignore rules, repository/history/secret scan, sanitized fixtures | Contributors must still review new artifact classes |
| Semantic false confidence | trusted-only browser policy, residual/fidelity gates, generated coverage | Rules and Oracle coverage remain incomplete |

## Assumptions and non-goals

The local machine and Python process are assumed to be controlled by the user.
The current server is not hardened against a hostile host administrator, local
malware, denial of service, or Internet-scale abuse. Public hosting requires the
separate [hosted deployment target](operations/hosted.md) and an independent
security review.

Report vulnerabilities through the process in [SECURITY.md](../SECURITY.md).
