---
title: "Deployment boundary"
status: "current"
authoritative_source: "implemented single-process local server and security boundary"
verified: "2026-08-05"
audience: "operators and deployment reviewers"
maintenance: "hand-maintained"
---

# Deployment boundary

The application supports a single-process local deployment on a user-controlled
machine. It does not provide a supported public Internet or multi-host mode.

The current runtime has lightweight guest identity, local SQLite control data,
filesystem Game Records, one in-process actor per loaded game, local Scryfall
data and an on-demand image cache. It does not provide production accounts,
external actor leasing, distributed locks, rate limiting, abuse controls,
multi-process ownership, TLS termination, backup orchestration or rights-cleared
hosted card assets.

Do not expose the local server directly to an untrusted network. A hosted
deployment requires a separate architecture and security review covering
identity, authorization, storage, actor ownership, recovery, observability,
network controls, data retention and Scryfall/card-image terms. Until that work
is implemented and documented, use the [local operations guide](local-app.md).
