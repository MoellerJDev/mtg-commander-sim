# Pilot providers

Version 0.5.0 separates strategic inference from the authoritative game. A
provider implements:

```python
PilotProvider.decide(observation, decision, memory) -> PilotResponse
```

`observation` is the principal-specific full or delta packet. `decision` is its
current capability-scoped choice. `memory` belongs to that principal only.
Providers never receive another seat's hand, library order, private choices,
analyst record, or arbiter-only resolution context.

## Built-in adapters

`ScriptedPilot` consumes exact responses or a deterministic chooser. It is for
characterization tests and reproducible fixtures, not evidence of strong
strategic play.

`ManualJsonPilot` writes the compact task JSON to the configured run path and
reads one response from a response file or stdin. It supports assisted play
without an API or credential dependency.

`SubprocessJsonPilot` starts the configured command with one JSON request on
stdin and reads one JSON object on stdout. Each seat gets its own provider
instance, so a wrapper can maintain an independent local or remote model
session. Nonzero exit, timeout, empty output, and invalid JSON fail visibly.

The arbiter is a separate provider and receives only an `arbiter` capability.
A pilot response can never submit effect-DSL operations.

`codex_subagent` is the project-scoped live arena provider. It does not replace
the scripted, manual, or subprocess adapters. Exactly four persistent
GPT-5.6 Sol/max contexts are registered once, one per seat, and every later
task returns to the same thread. The primary GPT-5.6 Sol/Ultra task is the
coordinator/arbiter, never a strategic pilot.

Pilots do not read the run directory. `simctl pilot-mcp --game-dir <run>
--seat A` fixes the seat at startup and exposes only `get_task`,
`submit_action`, `get_rules`, `get_profile`, `get_memory`, and
`update_memory`. Provider/model/thread metadata is injected by the coordinator;
pilot-supplied identity, capability, principal, effect, or semantic fields are
rejected and journaled.

## Response contract

Responses validate against `schemas/pilot-response.schema.json`. The preferred
single-action shape is:

```json
{
  "action_id": "cast:A64",
  "choices": {"targets": ["B14"]},
  "plan": "DEVELOP_ENGINE",
  "reason": "Deploy Lotus Cobra before the fetchland so landfall fixes the next color.",
  "confidence": 0.91,
  "yield": null,
  "memory_update": "Preserve Bojuka Bog while opposing recursion remains live."
}
```

`reason` is at most 180 characters and `memory_update` at most 500. `plan` is
one of:

- `MULLIGAN`
- `DEVELOP_MANA`
- `FIX_COLORS`
- `DEVELOP_ENGINE`
- `HOLD_INTERACTION`
- `DISRUPT_LEADER`
- `PROTECT_ENGINE`
- `ASSEMBLE_WIN`
- `PRESSURE_PLAYER`
- `RECOVER`
- `PASS_WITH_YIELD`

Codex-subagent responses must include a plan category, nonempty concise reason,
and confidence. Missing audit fields are rejected rather than silently filled
by the parent.

An ordered response may instead provide `actions`, each containing an
`action_id` and choices. Only the first action is initially submitted. Later
entries execute without another provider invocation only if the same principal
immediately receives another decision and the exact action ID is still legal.
Responses, stack changes, new hidden draws, resolution-time searches, delegated
choices, combat, rejection, save/load, or stale IDs stop the plan.

Invalid output and rejected actions use the existing same-capability compact
retry. The full projected state is not resent. Rejections remain in
`decisions.jsonl` and never become accepted replay commands.

## Metadata and measurement

The decision audit can persist:

- provider
- model or implementation ID
- invocation ID
- input/output tokens
- latency
- retry count
- automatic-fallback status
- immutable seat thread ID/label and reasoning effort
- first/last invocation timestamps and reuse/restart telemetry

Only a call made through a provider is counted as an invocation. A decision
record is not assumed to be a model call. Token counts are `null` with
`token_measurement_status: "unavailable"` when the provider does not report
them; packet-size token estimates remain separately labeled estimates.

## Profiles and memory

`DeckProfileCache` keys advisory JSON profiles by a canonical deck-list
fingerprint.
The built-in Zimone and Mishra profiles conform to
`schemas/pilot-profile.schema.json`. The runner copies the matching profile
into that seat's `PilotMemory` once, and persists memory independently in
`pilot-seat-memory/<seat>.json`.

Profiles describe strategy, mulligan policy, colors, engines, preservation
priorities, and threat assessment. They are not rules data. The engine does not
read them and cannot use them to make a card legal.

Profile schema v2 distinguishes `deck_list_fingerprint`, optional
`deck_source_fingerprint`, `profile_source_fingerprint`,
`profile_schema_version`, and `fingerprint_algorithm_version`. Exact compatible
list identity is required by default. A commander/archetype fallback must be
explicitly enabled, emits a fidelity warning, and never counts as
`profile_fingerprint_match`. Refreshing a changed live Moxfield list therefore
invalidates stale tutor, combo, and mulligan assumptions.

## CLI

```bash
python simctl.py pilot-run \
  --db data/scryfall-20260728-compact.sqlite3 \
  --profile commander_duel \
  --deck A=<public-moxfield-url> \
  --deck B=<public-moxfield-url> \
  --pilot A=manual \
  --pilot B=subprocess:"python local_model_wrapper.py" \
  --output run/native-game
```

Running the same command again resumes an existing output directory. The
checkpoint, projection cursors, profiles, and per-seat memories are restored.
The external subprocess is responsible for restoring any provider-side session
state beyond the persisted compact memory supplied in the request.

See `CODEX_ARENA.md` for the project agent files, primary prompt, lifecycle,
fixed-seat commands, and honest provider-identity rules.
