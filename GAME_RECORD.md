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
| `opportunities.jsonl` | Engine-side priority audit with meaningful-action signature, delivery/suppression disposition, and decision link |
| `review.json` | Machine-readable derived history, diagnostics, and fidelity gate |
| `review.md` | Human-readable review grouped by meaningful turns |
| `semantics.json` | Optional local semantic programs used by that game |
| `cursors.json` | Delivery cursor state; not part of authoritative replay |
| `pilot-profiles.json` | Advisory fingerprinted profile assigned to each pilot principal |
| `plans.json` | Remaining validated ordered-plan actions required to resume safely across fixed-seat tool processes |
| `pilot-seat-memory/<seat>.json` | Bounded strategic memory isolated to one fixed seat |
| `call-benchmark.json` | Priority/yield/opportunity and observed provider-call metrics |
| `hidden-information-audit.json` | Seat projection, decision-field, and memory reference-leak audit |

Raw capability tokens are never durable state. Checkpoints store only SHA-256
identifiers for active capabilities, clear the capability map, and issue new
opaque tokens when loaded. Consumed capabilities are not retained.

Native command rows also record the action-template ID, selected object refs,
targets, modes, X, selected costs, RNG consumption/results, and semantic
program versions used by the transition. Rejected attempts stay in
`decisions.jsonl` and never enter `commands.jsonl`.

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

Fresh native records use `manifest.replay.mode = "command_replay"`. The
separate `legacy_snapshot` mode is reserved for migrated records whose accepted
commands cannot be reconstructed honestly.

An unfinished record replays its accepted-command prefix. A passing prefix
proves that every accepted transition reproduced the saved checkpoint; it does
not imply that the game ended. Version 0.6.0 uses explicit lifecycle states:
`created`, `in_progress`, `paused`, `complete`, `aborted`, and `corrupt`.
Paused records carry a structured `pause_reason`, and Codex arenas copy that
reason into `codex_arena.stop_reason`.

An operator may preserve a discovered boundary explicitly:

```bash
python simctl.py arena pause run/game --db data/scryfall-current.sqlite3 \
  --kind legal_action_exposure_failure \
  --reason "targeted action advertised without a legal target"
```

Derived artifacts can be reconstructed and verified from the durable
checkpoint and journals:

```bash
python simctl.py refresh-record run/game --db data/scryfall-current.sqlite3
python simctl.py finalize-record run/game --db data/scryfall-current.sqlite3
python simctl.py verify-record run/game --db data/scryfall-current.sqlite3
```

`finalize-record` marks a terminal game complete or an unfinished game paused,
then verifies exact replay. Record components are atomically replaced and the
manifest is written last as the commit marker. Integrity verification rejects
manifest/journal counter contradictions rather than trusting stale summaries.

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

An unfinished native run with real command and decision journals is a
`pilot_test`, while its outcome remains `in_progress`. `pilot_test` is protocol
and characterization evidence only. `deck_review_eligible` additionally
requires a terminal game, replay verification, complete historical
alternatives/reasons, trusted materially relevant semantics, the requested
format, no material rules conflict, and a genuinely strategic pilot.

Version 0.7.0 fails legal-action exposure when any meaningful window is
incorrectly suppressed or a mandatory-target action is advertised without
legal targets. The report records `profile_fingerprint_match`,
`action_opportunity_coverage`, `suppressed_meaningful_windows`,
`yields_invalidated_by_reason`, `pilot_thread_count`,
`persistent_thread_reuse`, `primary_made_strategic_decision`,
`provider_identity_verified`, `model_identity_verified`,
`seat_projection_verified`, and `codex_subagent_run`.

Version 0.8.0 records use the same Game Record v3 layout. Semantic closure does
not redesign the record: replay continues to pin semantic-program identity,
source hashes, accepted commands, transition hashes, opportunity rows, and
honest provider metadata. A 100/100 exact-list preflight is necessary but not
sufficient for matchup evidence; the terminal, replay, pilot, fidelity, format,
and sample-size gates still apply.

The target-action audit additionally records actions prevented before
exposure, incorrectly advertised actions, no-target/mode-target removals,
candidate generation, rejected target submissions, targets becoming illegal,
rules/effect counter totals, and stack interaction windows created or
auto-passed. A nonzero `illegal_target_actions_advertised` value fails fidelity,
caps classification at `rules_test`, and is attributed to infrastructure
rather than the pilot.

A pilot is never blamed for a missed action when its opportunity row says no
task was delivered, the generator failed, semantics were unresolved, or a
yield suppressed the window. Duplicate-deck four-player protocol fixtures are
always `matchup_evidence: false`.

## Decision and provider metrics

The review keeps observations separate from estimates:

- `decision_records_observed`: audit rows, including rejected provider attempts
- `pilot_invocations_observed`: actual strategic provider calls, or `null` when unknown
- `arbiter_invocations_observed`: actual rules-provider calls, or `null` when unknown
- `automatic_decisions`: accepted planned commands that required no new provider call
- `priority_windows_considered`: every engine priority opportunity audited
- `pass_only_windows_skipped`: priority windows with no meaningful action
- `yield_covered_windows`: unchanged windows safely covered by a yield
- `suppressed_meaningful_windows`: must remain zero
- `ordered_plan_responses`: accepted multi-action pilot plans
- `estimated_calls_without_optimization`: explicitly labeled counterfactual
- `estimated_calls_with_optimization`: actual provider rows for a native run
- `input_tokens_observed` / `output_tokens_observed`: provider-reported totals only
- `token_measurement_status`: `complete`, `partial`, `unavailable`, or `unknown_legacy`

A legacy `decision.response` event is not assumed to be an LLM call. Placeholder
values such as `unavailable in v2 record` do not count as complete reasons or
plans. If a native adapter does not supply usage data, observed token totals are
`null`; packet-size estimates remain separately labeled estimates.

For Codex arenas, `manifest.json.codex_arena` records the parent session ID
when exposed; immutable seat/thread labels and IDs; provider, model, and
reasoning effort; invocation count; first/last timestamps; reuse; retries; and
restart/interruption counters. Unknown token counts or opaque platform IDs are
stored as `null`, never estimated as observed.

`manifest.json.provider_telemetry` is derived from durable rows and keeps these
counts distinct: game decisions created, provider calls attempted/accepted/
rejected, retry calls, accepted commands, automatic decisions, arbiter calls,
unique pilot threads, persistent reuse, ordered plans submitted, and ordered
plan actions executed. A thread handle is routing identity; an invocation ID is
an individual call identity and is never synthesized from that handle.

Provider/model values have separate recorded, configured, and verified
dimensions. A genuine Codex submission can attest the configured and observed
values; an older record without that provenance remains recorded-but-unverified
after refresh. Refresh never upgrades identity by inference.

## Size definitions

All byte values are exact on-disk file sizes at review generation:

- `checkpoint_bytes`: `checkpoint.json`
- `command_journal_bytes`: `commands.jsonl`
- `event_journal_bytes`: `events.jsonl`
- `decision_journal_bytes`: `decisions.jsonl`
- `manifest_bytes`: `manifest.json`
- `review_artifact_bytes`: `review.json` plus `review.md`
- `resumable_core_bytes`: every run file needed to restore authoritative state,
  projection cursors, semantic registry, pilot profiles, and pilot memory,
  excluding derived reviews
- `complete_record_bytes`: every regular file in the run directory, including
  derived review artifacts

`review.json` and `review.md` use these same definitions. Because review files
contain the metrics describing themselves, generation iterates until the
serialized sizes stabilize.

## Elimination privacy

The authoritative record preserves physical identities so an analyst can audit
the game. It does not turn owner departure into public revelation. Remaining
pilot projections keep the former hand, library order, face-down cards, and
private choices hidden while retaining cards that were already public or
legally known. Legacy migration chooses the more restrictive knowledge state
when exact historical knowledge cannot be reconstructed and annotates that
uncertainty.
