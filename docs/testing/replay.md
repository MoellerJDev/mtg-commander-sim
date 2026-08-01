---
title: "Replay testing"
status: "current"
authoritative_source: "record replay tests and local merge gate"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "engine, persistence, and protocol contributors"
maintenance: "hand-maintained"
---

# Replay testing

Every state-changing rules or protocol change needs a replay witness at the
lowest practical level. Build a deterministic initial state, submit canonical
commands through the same public boundary used by clients, persist the record,
replay it, and compare authoritative state hashes and lifecycle results.

Also test rejection and rollback: an invalid target, stale capability, changed
cost, illegal payment, or malformed choice must leave no partial mutation or
accepted command. When persistence or idempotency changes, test a lost response
and exact command retry. When schema/fingerprint behavior changes, test both a
matching load and the intended fail-closed mismatch.

Do not “fix” Game Record v3 by editing a saved command or checkpoint. Historical
private records stay local; public fixtures contain sanitized recipes and no
capabilities or hidden library order. See the [replay architecture](../architecture/replay.md)
and [Game Record reference](../../GAME_RECORD.md).
