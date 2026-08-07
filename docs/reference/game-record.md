---
title: "Game Record v3"
status: "current"
authoritative_source: "quorune/record.py, persistence implementation, and Game Record schemas"
verified: "2026-08-06"
audience: "engine, persistence, replay, and analyst contributors"
maintenance: "hand-maintained"
concern: "game-record"
---

# Game Record v3

Game Record v3 is the authoritative persistence, replay, and audit directory for
one game. It separates canonical state and accepted inputs from delivery state
and derived review. The schemas under `schemas/game-record-v3-*.schema.json`
and the serializer implementation define the exact format.

## Directory contract

| File | Contract |
| --- | --- |
| `manifest.json` | Public identity, lifecycle, profiles, source fingerprints, outcome, replay, and fidelity summary |
| `initial-checkpoint.json.gz` | Private exact replay origin, including physical objects and the pending decision |
| `checkpoint.json` | Current authoritative state without event history or raw capabilities |
| `commands.jsonl` | Accepted external commands with normalized payloads, principals, capability digests, RNG facts, and before/after hashes |
| `events.jsonl` | Normalized trace at the selected trace level; excluded from the authoritative state hash |
| `decisions.jsonl` | Accepted and rejected external attempts, legal alternatives, audit metadata, retries, and fallback status |
| `opportunities.jsonl` | Engine priority/opportunity delivery and suppression audit |
| `semantics.json` | Pinned canonical CardPrograms and compatibility semantic-key index |
| `cursors.json` | Delivery cursor state; not authoritative replay input |
| `pilot-profiles.json` | Optional advisory profile fingerprints by principal |
| `pilot-seat-memory/` | Optional bounded memory isolated by seat |
| `plans.json` | Remaining validated ordered actions for safe fixed-seat resume |
| `review.json`, `review.md` | Derived diagnostics and fidelity review; rebuildable and nonauthoritative |
| `hidden-information-audit.json` | Derived projection and reference-leak audit |
| `call-benchmark.json` | Derived observed provider/opportunity metrics with provenance |

Raw capability tokens, guest tokens, invite codes, provider credentials, and
network connection cursors are never authoritative durable state. A loaded
checkpoint reissues opaque capabilities from persisted digests and the current
pending decision.

## Canonicalization and hashes

Authoritative JSON uses deterministic serialization and strict schema
validation. State hashes cover canonical authoritative state, including
versioned rules-relevant fields and continuations. They exclude presentation
text, raw capability tokens, connection cursors, and derived review.

Every accepted command records:

- sequential record command identity and optional network idempotency identity;
- authenticated principal, decision, action, and normalized delegated choices;
- source/card program and runtime binding provenance when applicable;
- deterministic RNG consumption and results;
- before-state and after-state hashes; and
- the replay-relevant semantic/capability fingerprints used by the transition.

The manifest pins engine, card-data, rules, compiler, CardProgram, capability,
semantic-handler, runtime-component, profile, and record-format identity as
applicable. Loading rejects internal disagreement before replay begins.

## Replay contract

Native records use `command_replay`. Verification loads the exact initial
checkpoint and pinned semantic identity, then resubmits each accepted command
through the ordinary permission and rules boundary. It verifies the before hash,
normalized transition, RNG facts, after hash, and final authoritative state.
The first mismatch fails closed.

Rejected attempts remain in `decisions.jsonl`; they never become replay
commands. An unfinished or paused record verifies its accepted-command prefix.
A passing prefix proves deterministic reproduction of that prefix, not a
terminal game or strategic evidence.

Historical records retain their recorded compatibility semantics. New optional
fields use explicit versioned shapes, and absence preserves the older hash and
meaning where the schema allows it. A current runtime never silently recompiles
or reinterprets an old record as if it used current Oracle, rules, or
CardPrograms.

## Lifecycle and atomicity

Lifecycle values are `created`, `in_progress`, `paused`, `complete`, `aborted`,
and `corrupt`. A pause has a structured reason. An administrative browser stop
does not add a synthetic game command or advance state; resume may clear only
that administrative reason.

Record components are written atomically and the manifest is the final commit
marker. Accepted network commands are persisted before acknowledgement.
Integrity verification rejects manifest/journal counter disagreement, invalid
hashes, malformed continuations, and incompatible source identity rather than
trusting a stale summary.

## Privacy and derived artifacts

The directory is private operator state, not a pilot, browser, or spectator
API. Checkpoints and journals may contain hidden zones, authoritative object
identity, private choices, or provider audit data. Clients receive only
principal projections. Complete public history is read through the serialized
actor and filtered to a compact spectator-safe event shape.

`review.json`, `review.md`, benchmarks, and hidden-information audits are
derived. They may be reconstructed from the canonical record and must never be
used as replay inputs or edited to change game truth. Provider identity and
usage remain configured, reported, observed, or verified facts; unavailable
values remain unknown rather than estimated as observations.

## Legacy migration

Legacy snapshot records that lack accepted command payloads cannot be promoted
to honest command replay. Migration uses an explicit `legacy_snapshot` mode,
preserves unavailable decision facts as unavailable, and verifies snapshot
integrity only. It does not convert a historical smoke artifact into rules,
deck, or matchup evidence.

## Commands

```powershell
.\.venv\Scripts\python.exe simctl.py replay run/game `
  --db data/scryfall-current.sqlite3 --verify
.\.venv\Scripts\python.exe simctl.py verify-record run/game `
  --db data/scryfall-current.sqlite3
.\.venv\Scripts\python.exe simctl.py refresh-record run/game `
  --db data/scryfall-current.sqlite3
.\.venv\Scripts\python.exe simctl.py finalize-record run/game `
  --db data/scryfall-current.sqlite3
```

Migration and inspection commands are discoverable through `simctl.py --help`.
Never hand-edit a record to make verification pass. See
[replay architecture](../architecture/replay.md),
[protocol](protocol.md), and [privacy testing](../testing/privacy.md).
