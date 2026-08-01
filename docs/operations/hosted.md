---
title: "Hosted deployment target"
status: "target"
authoritative_source: "documented gaps in server runtime and threat model"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "future deployers and security contributors"
maintenance: "hand-maintained"
---

# Hosted deployment target

The current application is not a supported public hosted service. Static-site
hosting alone cannot run the authoritative Python engine, durable actor,
WebSockets, SQLite/Game Record persistence, managed card data, authentication,
or image cache.

Before adding a hosted mode, write an ADR and implement at least:

- TLS termination, strict origins, secure cookies, CSRF, rate limits, request
  size/time limits, secret rotation, and production account recovery;
- a durable database and object-store design with backup/restore and retention;
- single-writer ownership leases or deterministic routing for every game;
- multi-process-safe idempotency, lifecycle recovery, deployments, migrations,
  health checks, and observability without hidden-data logging;
- licensed/attributed content handling, bounded image caching, egress policy,
  and Scryfall/Moxfield terms review;
- abuse controls, privacy review, accessibility validation, and independent
  security assessment.

Do not expose the development server directly to the Internet. A future design
must preserve the same projected protocol, exact replay, pinned rules/card data,
and fail-closed fidelity boundary.
