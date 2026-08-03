---
title: "Game Record v3"
status: "current"
authoritative_source: "mtg_commander_sim/record.py and record schemas"
verified: "2026-08-02"
audience: "engine, persistence, replay, and analyst contributors"
maintenance: "hand-maintained"
---

# Game Record v3

Game Record v3 replaces the growing `game.json` monolith with a replayable
authoritative checkpoint, append-oriented journals, and a derived review.

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Public identity, format profile, deck/card-data/semantic fingerprints, outcome, replay status, and fidelity result |
| `checkpoint.json` | Current authoritative state without event history or raw capabilities |
| `initial-checkpoint.json.gz` | Private replay origin containing the exact shuffled physical objects and pending decision |
| `commands.jsonl` | Accepted external commands only, with principal, hashed capability ID, optional network command/fingerprint/receipt audit, exact normalized payload, RNG counters, and before/after hashes |
| `events.jsonl` | Normalized trace at `minimal`, `standard`, or `debug` level |
| `decisions.jsonl` | Every external attempt, including rejected attempts, scoped legal alternatives, reason/plan/confidence, model metrics, and fallback status |
| `opportunities.jsonl` | Engine-side priority audit with meaningful-action signature, delivery/suppression disposition, and decision link |
| `review.json` | Machine-readable derived history, diagnostics, and fidelity gate |
| `review.md` | Human-readable review grouped by meaningful turns |
| `semantics.json` | Pinned CardProgram V2 objects plus the derived legacy semantic-key index used by that game |
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
program versions used by the transition. New rows additionally record
CardProgram schema version 2, exact card-level/trust fingerprints, a compact
runtime-binding fingerprint, and semantic-handler/runtime-component IDs used
by the transition. Rejected attempts stay in
`decisions.jsonl` and never enter `commands.jsonl`.

Protocol 3.0 adds optional `client_command_id`,
`client_request_fingerprint`, and `client_receipt` fields to accepted network
command rows. The original sequential `C1`, `C2`, … `command_id` remains Game
Record v3 replay identity; the client ID is transport idempotency identity and
does not redesign the format. The fingerprint excludes the raw capability, and
the receipt contains no guest token, invite code, or capability secret.

The JSON schemas live under `schemas/game-record-v3-*.schema.json` and
`schemas/game-review-v1.schema.json`.

## Replay

New v3 records replay from `initial-checkpoint.json.gz` by resubmitting each
accepted command through the normal permission and rules boundary. Verification
checks:

- engine version
- semantic registry fingerprint
- complete manifest CardProgram V2 fingerprint map, when present
- manifest CardProgram trust basis and closure fingerprints, when present
- capability registry and generated evidence fingerprints, when present
- semantic-handler and runtime-component inventories/fingerprints, when present
- command-scoped CardProgram V2 fingerprints for programs used, when present
- command-scoped runtime binding and capability-closure fingerprints, when present
- before-state hash for every command
- after-state hash for every command
- final authoritative state hash

Run:

```bash
python simctl.py replay run/duel --db data/scryfall-current.sqlite3 --verify
```

A mismatch fails closed at the first divergent command. Event text and
capability tokens do not participate in the authoritative hash.

CardProgram and runtime-trust pinning are additive Game Record v3 extensions, not a record
redesign. Historical v3 records without these fields continue to verify the
semantic registry as before. A new record stores the complete card-program map
in `manifest.card_programs`, repeats it under replay provenance, and stores
only the used subset in each command's `semantics.card_programs_used`.
`semantics.json` carries canonical CardPrograms and a compatibility program
index; loading rejects disagreement between them before replay begins.

Game Record v3 checkpoints now serialize both a card's stable physical
`object_id` and its `zone_change_counter`. Together they identify the logical
object selected by a target or implemented linked effect. The counter is
authoritative state and therefore participates in command hashes and replay;
it is not a capability and is not exposed in pilot projections. This is an
additive state-field extension to v3, not a new record layout.

`CardInstance.object_kind` is also serialized and hashed. It distinguishes a
card, token, spell copy, card copy, or emblem while retaining compatibility
with older token and count-only Daretti checkpoints. Represented copy-object
IDs remain authoritative only; a seat sees the ordinary public
stack/permanent projection, not the underlying copy container. An emblem is
projected as a public command-zone object with a display label, while its
internal source identity and semantic key remain authoritative. Copy
cessation, permanent-spell-copy resolution, and represented emblem creation
therefore command-replay exactly. This is another additive v3 state
extension.

New Commander games also serialize
`GameState.commander_damage_identity_version = 2` and one public-stable
`CardInstance.commander_designation_id` on each actually designated physical
commander. The designation, rather than Oracle ID, keys the 21-combat-damage
ledger, so two players using the same named commander remain separate. It
survives ordinary zone and control changes and is never copied onto an ordinary
copy. The manifest repeats the identity version and replay verifies it against
the initial checkpoint. Historical v3 records that omit the additive marker
and designations retain their prior Oracle-ID attribution explicitly; they are
not silently reinterpreted or rehashed.

The same checkpoint serializes `GameState.timestamp_sequence`,
`CardInstance.zone_timestamp`, and `CardInstance.world_supertype_timestamp`.
The first two establish deterministic CR 613.7d zone-entry moments, including
shared moments for simultaneous moves. The last records the separate time from
which a battlefield object has continuously had World for CR 704.5k. They
participate in state hashes and exact replay but are not included in a seat
projection. This remains an additive v3 state extension; it does not redesign
the record format.

`GameState.monarch` is likewise an additive v3 checkpoint field. It stores
the one public CR 725 player designation, or `null` before anyone becomes the
monarch. A real designation participates in authoritative hashes and replay;
the initial `null` is hash-equivalent to its absence in older additive v3
checkpoints. Seat projections expose the designation but no private zone;
inherent monarch abilities remain ordinary serialized stack objects and
trigger batches.

`GameState.turn_history` is an additive, versioned v3 checkpoint field for
rules-relevant current-turn facts. Unlike `events.jsonl`, it is authoritative
and participates in command hashes because declaration legality can depend on
spells cast, a creature dying under a player's control, positive player damage,
or the direct player previously attacked by one logical object incarnation.
The journal records cast-time types and last-known death identity/control,
resets when a turn begins, and remains intact across extra combats in that
turn. A legacy v3 checkpoint that omitted the field keeps history support
disabled and reserializes without the field, preserving its historical hash;
new records always include schema version 1. Presentation events remain
excluded from the authoritative hash.

`CardInstance.battle_protector` is another additive public game-state field.
It is serialized and hashed so Siege entry choices, combat routing, protector
repair, and command replay agree exactly. Seat projections expose only the
protector seat as `protect`; they do not expose the physical card identifier,
logical-incarnation counter, or capability data.

`CombatState.damage_step_index`, `damage_step_initialized`,
`first_strike_step`, and `ordinary_second_damage_combatants` are additive v3
state fields. They preserve the CR 510.4 first-step snapshot and real second
combat-damage step across checkpoints and exact command replay. The internal
object-ID snapshot is authoritative only; projected seats receive the public
one-based damage-step number and whether the split step exists.

Sequential combat-damage choices remain ordinary v3 decision continuations.
The continuation records the fixed APNAP assignment order, current cursor, and
already announced public assignments; it contains no hidden card identity.
Forced assignments create public `combat.damage.assigned` events without a
client command. The final `combat.damage` event journals normalized assigned,
dealt, and prevented source-recipient results. Pending semantic trigger batches
use the additive `placement_started` marker so damage triggers may merge with
triggers discovered by subsequent state-based actions until placement begins,
while `priority_epoch` prevents merging across priority windows and triggers
created during placement remain a later CR 603.3b pass. These
are additive checkpoint details, not a Game Record v3 redesign.

Competing represented replacement effects use an ordinary additive
`replacement.order` decision continuation. The authoritative continuation
stores the immutable event batch, candidate effects, exact event path, and
prior selection journal. A finite prevention shield shared by simultaneous
damage events also stores the affected seat's exact allocation map and the
shield amount available when that choice was created. Replay validates the
event IDs, allocation total, available amount, and current option set before
resuming; malformed or stale allocations fail closed. The chooser projection contains only its current
event label and legal effect/decline options. A response is accepted only when
the event, path, affected seat, and choice reconstruct the same pending
decision, after which the original semantic instruction resumes with the exact
selection journal. Neither another seat's choice data nor raw authoritative
replacement payloads enter the projected packet. This is an additive v3
continuation, not a record redesign.

`GameState.damage_prevention_shields` and
`GameState.damage_redirections` are additive v3 checkpoint fields. They store
typed, versioned, canonically serialized durable damage modifiers, including
their stable IDs, subjects, source snapshots, durations, remaining amounts,
and used state. Those values participate in state hashes and exact command
replay. Seat projections expose only the ordinary public effects and legal
choices derived from them; they do not expose raw replacement descriptors or
another seat's pending allocation. Historical v3 checkpoints that omit the
fields load them as empty collections and retain their historical hash shape.

Fresh native records use `manifest.replay.mode = "command_replay"`. The
separate `legacy_snapshot` mode is reserved for migrated records whose accepted
commands cannot be reconstructed honestly.

An unfinished record replays its accepted-command prefix. A passing prefix
proves that every accepted transition reproduced the saved checkpoint; it does
not imply that the game ended. Version 0.6.0 uses explicit lifecycle states:
`created`, `in_progress`, `paused`, `complete`, `aborted`, and `corrupt`.
Paused records carry a structured `pause_reason`, and Codex arenas copy that
reason into `codex_arena.stop_reason`.

The browser server uses the same record lifecycle without adding a new Game
Record schema. An owner stop saves `status = "paused"` with
`pause_reason.kind = "administrative_stop"` through the serialized game actor.
It does not append a synthetic game command or alter the authoritative state
revision. Resume clears that administrative reason and preserves the pending
decision. A browser resume cannot clear any other pause kind. Exact replay
continues to verify the accepted-command prefix across stop, process restart,
resume, and later accepted commands.

Browser-created records use the existing `debug` trace level so the complete
public narrative remains durable rather than disappearing when an in-memory
projection cursor or server process is replaced. This does not expose the
private record: the authenticated public-log application endpoint reads the
event journal through the serialized actor, applies the `spectator`
visibility policy, and returns only event ID, code, actor, summary, and
importance. It never returns event details, checkpoints, capabilities,
private events, or analyst artifacts. Trace text remains outside the
authoritative state hash, as before.

The record's `manifest.scryfall.metadata_hash` also pins the local card-data
snapshot used to interpret its cards. The server opens the current SQLite
database when that fingerprint matches; otherwise it verifies and opens the
retained `data/card-snapshots/<metadata-hash>.sqlite3` file. A replaced
database is retained only while at least one local Game Record references it,
then pruned. Raw bulk archives and downloaded image bytes are rebuildable
caches and are not part of Game Record v3.

If a player confirms future-dated preview cards, the deck provenance metadata
records `format_legality.status = preview_override_confirmed`, the structured
issues, and the confirmation fingerprint. This is an auditable format-policy
exception, not semantic trust: unresolved material Oracle behavior continues
to fail closed and prevents the record from becoming conformance or matchup
evidence.

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

Version 0.8.0 records use the same Game Record v3 layout. CardProgram V2 and
semantic closure do not redesign the record: replay pins card/ability program
identity, source hashes, accepted commands, transition hashes, opportunity
rows, and honest provider metadata. A 100/100 exact-list preflight is necessary
but not sufficient for matchup evidence; the terminal, replay, pilot,
fidelity, format, and sample-size gates still apply.

Casting and activation alternatives additionally carry a canonical proposal
fingerprint and expiry revision. These are ordinary legal-alternative facts,
not capability secrets or persisted hidden reasoning. Command replay submits
the recorded action and verifies the same authoritative source, cost, target,
timing, and payability proposal; a stale proposal fails before mutation. Game
Record v3 itself is unchanged.

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
