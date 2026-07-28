# Game Record v3

Game Record v3 replaces the growing `game.json` monolith with a replayable
authoritative checkpoint, append-oriented journals, and a derived review.

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Public identity, format profile, deck/card-data/semantic fingerprints, outcome, replay status, and fidelity result |
| `checkpoint.json` | Current authoritative state without event history or raw capabilities |
| `initial-checkpoint.json.gz` | Private replay origin containing the exact shuffled physical objects and pending decision |
| `commands.jsonl` | Accepted external commands only, with principal, hashed capability ID, exact normalized payload, RNG counters, and before/after hashes |
| `events.jsonl` | Normalized trace at `minimal`, `standard`, or `debug` level |
| `decisions.jsonl` | Every external attempt, including rejected attempts, scoped legal alternatives, reason/plan/confidence, model metrics, and fallback status |
| `review.json` | Machine-readable derived history, diagnostics, and fidelity gate |
| `review.md` | Human-readable review grouped by meaningful turns |
| `semantics.json` | Optional local semantic programs used by that game |
| `cursors.json` | Delivery cursor state; not part of authoritative replay |

Raw capability tokens are never durable state. Checkpoints store only SHA-256
identifiers for active capabilities, clear the capability map, and issue new
opaque tokens when loaded. Consumed capabilities are not retained.

The JSON schemas live under `schemas/game-record-v3-*.schema.json` and
`schemas/game-review-v1.schema.json`.

## Replay

New v3 records replay from `initial-checkpoint.json.gz` by resubmitting each
accepted command through the normal permission and rules boundary. Verification
checks:

- engine version
- semantic registry fingerprint
- before-state hash for every command
- after-state hash for every command
- final authoritative state hash

Run:

```bash
python simctl.py replay run/duel --db data/scryfall-current.sqlite3 --verify
```

A mismatch fails closed at the first divergent command. Event text and
capability tokens do not participate in the authoritative hash.

## Legacy migration

Version 2 `game.json` files contain decision names but not the submitted
payloads or historical legal-action catalogs, so command replay cannot be
reconstructed honestly. Migration therefore uses an explicit
`legacy_snapshot` replay mode:

```bash
python simctl.py inspect-game run/live-duel/game.json --pretty
python simctl.py migrate-record run/live-duel/game.json \
  --output run/live-duel-v3 \
  --db data/scryfall-current.sqlite3
python simctl.py replay run/live-duel-v3 \
  --db data/scryfall-current.sqlite3 --verify
```

The migrated decision journal labels missing alternatives, reasons, and
payloads as unavailable. Its replay verification checks snapshot integrity; it
does not pretend the old game can be command-replayed.

## Trace levels

- `minimal`: gameplay-changing milestones suitable for compact batch records.
- `standard`: normal audit trace without priority/step/mana-clear/untap
  bookkeeping.
- `debug`: every authoritative event, including routine bookkeeping.

Commands and decisions remain complete at every trace level. Review data is
derived and can be regenerated; it is not authoritative state.

## Fidelity gate

Review classification is explicit. A game cannot become
`deck_review_eligible` when it has material land-entry conflicts, incomplete
relevant semantics, incomplete decision alternatives/reasons, a profile
mismatch, or unverified replay. A single eligible game is still not
`matchup_evidence`; that requires a separately designed batch methodology.

The migrated turn-21 live duel is deliberately classified `smoke_only`. It is
useful protocol and kernel evidence, but its ignored Oracle semantics, ten
incorrect land-entry states, missing historical action catalogs, and smoke
pilot make it unsuitable for claims about either deck or their matchup.
