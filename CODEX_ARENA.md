---
title: "Codex Commander Arena"
status: "current"
authoritative_source: "Codex pilot configuration and arena commands"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "Codex arena operators and pilot-provider contributors"
maintenance: "hand-maintained"
---

# Codex Commander Arena

This is an optional protocol-adapter experiment, not the product execution
plan. Codex sessions are untrusted clients and are not required for gameplay,
legality, CI, merges, releases, or rules decisions. Current platform work must
not optimize prompts, models, provider routing, or live AI games.

Version 0.8.0 supports one neutral primary Codex task coordinating exactly four
persistent, seat-isolated strategic pilot tasks.

## Roles

Run the primary task with model **GPT-5.6 Sol** and reasoning effort **Ultra**
from the Codex model/reasoning selector before invoking `$commander-arena`.
Ultra applies to the coordinator. The four project agents now use the
user-selected fast profile: GPT-5.6 Sol with `low` reasoning on the `priority`
tier. This runtime does not expose a GPT-5.5/“Instant” pilot model, so records
must use the actual `gpt-5.6-sol` identity rather than inventing that label.

The roles are:

- primary: public game coordinator and scoped rules arbiter
- `mtg-pilot-a`: strategic seat A only
- `mtg-pilot-b`: strategic seat B only
- `mtg-pilot-c`: strategic seat C only
- `mtg-pilot-d`: strategic seat D only

The primary is the fifth logical role, not a fifth subagent. It never receives
all four hands, chooses a seat action, advises one pilot from another pilot's
context, or replaces a legal poor action. It stops when a material fidelity or
semantic problem needs code work.

Four pilot contexts stay alive so their private strategy and bounded memory are
stable. Invocations are nevertheless sequential: Magic gives authority to one
principal, or one ordered decision group, at a time.

The current desktop collaboration host counts the primary task against its
four active sampling slots. It therefore cannot retain the primary plus four
in-app child pilots at once. The preferred fast runner starts four independent
persistent Codex CLI sessions outside that child-slot pool, bootstraps them in
parallel, and resumes the appropriate original session sequentially as Magic
changes principal. A run must stop rather than silently replace a missing
session.

## Project configuration

The project configuration is:

```text
.codex/config.toml
.codex/agents/mtg-pilot-a.toml
.codex/agents/mtg-pilot-b.toml
.codex/agents/mtg-pilot-c.toml
.codex/agents/mtg-pilot-d.toml
.agents/skills/commander-arena/SKILL.md
```

`.codex/config.toml` enables four child threads and defaults them to
`gpt-5.6-sol`/`low`. Each seat file has a unique name, read-only default,
fixed-seat server command, strict JSON instructions, and nested agents
disabled.

Custom-agent instructions are not an OS security boundary when a parent task
overrides permissions with `danger-full-access`. The fixed-seat server enforces
the game-state boundary. For filesystem-level proof as well, launch each pilot
from an empty workspace under a dedicated read-only permission profile.

## Create a match

The arena defaults to `commander_review`: four players, 40 life, first player
draws on turn one, one free multiplayer mulligan, later seven-card redraws with
private bottoming, separate commander-damage sources, live bond-land opponent
counts, and continuation after elimination.

```powershell
python simctl.py arena-create `
  --db data/scryfall-20260728-compact.sqlite3 `
  --deck A=https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ `
  --deck B=https://moxfield.com/decks/armNI_ntVUagNNygnUVyxQ `
  --deck C=https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ `
  --deck D=https://moxfield.com/decks/armNI_ntVUagNNygnUVyxQ `
  --refresh-decks `
  --first A `
  --seed 20260734 `
  --output run/codex-arena
```

`arena-create` defaults to `semantic_policy=trusted_only`. This is required for
`deck_operation_evidence`; pass `--semantic-policy arbitrate_or_pause` only for
an explicitly non-evidence development run.

Live Moxfield metadata is authoritative. The current mapping is:

- `g5vtVfRuS0W5KxZuYqZHGQ`: Zimone and Dina
- `armNI_ntVUagNNygnUVyxQ`: Mishra, Eminent One

Creation validates each list and exact profile fingerprint, then writes
`PRIMARY_CODEX_PROMPT.md`. Use that file as the primary Ultra task prompt.
`commander_duel` remains available through the ordinary duel/pilot commands for
narrow two-player regression tests.

## Fast four-session runner

The preferred desktop command avoids the three-child ceiling and unnecessary
MCP round trips:

```powershell
python simctl.py arena-codex-run `
  --db data/scryfall-20260728-compact.sqlite3 `
  --game run/codex-arena `
  --model gpt-5.6-sol `
  --reasoning-effort low `
  --service-tier priority `
  --through-turn 8
```

Use `--through-turn 0` for a natural terminal game. The first invocation starts
A–D in parallel and writes a coordinator-only `codex-cli-pilots.json`
registry. Later invocations recover those exact session IDs; they never spawn
replacement pilots for recorded seats.

The broker calls the same fixed-seat `get_task`, `get_profile`, `get_memory`,
`submit_action`, and `update_memory` façade inside the process. It passes only
one seat projection to that seat's Codex session. Pilot shell, apps, tools, and
nested agents are disabled. The primary receives only the final public command
summary, never a private packet. Codex's structured output uses the packaged
`codex-pilot-response.schema.json`; the broker decodes choice objects, injects
provider identity and observed usage, and submits through the seat boundary.

Every accepted command checkpoints the record. At the requested stop, the
runner performs exact replay while preserving an unfinished record as
`in_progress`; terminal and fidelity-paused records retain their actual status.

## Fixed-seat pilot tools

A pilot process authenticates its seat at startup:

```powershell
python simctl.py pilot-mcp --game-dir run/codex-arena --seat A
```

It exposes exactly:

1. `get_task()`
2. `submit_action(...)` with a typed action/ordered-plan union
3. `get_rules(refs)`
4. `get_profile()`
5. `get_memory()`
6. `update_memory(text)`

Later calls cannot select another seat. Tasks omit raw capabilities.
`get_rules` accepts exact visible/legally known object references, not arbitrary
card-name lookup. Memory is capped at 500 characters and stored separately per
seat. Provider/model/reasoning/thread fields are server-injected.

The surface has no checkpoint, initial checkpoint, analyst, arbitrary file,
state mutation, or effect-DSL operation. Guessed own-library refs and opposing
hidden refs are denied.

The local one-shot equivalent, useful when the Codex host does not attach the
MCP namespace automatically, is:

```powershell
python simctl.py pilot-tool `
  --game-dir run/codex-arena `
  --seat A `
  --provider codex_subagent `
  --model gpt-5.6-sol `
  --reasoning-effort low `
  --thread-id <actual-stable-thread-id> `
  --thread-label mtg-pilot-a `
  --provider-invoked `
  get-task
```

Use `submit-action --json '<response>'` for the corresponding submission.
Never invent an ID or mark `provider-invoked` when no model invocation
occurred. The one-shot fallback does not retain process arguments: repeat the
complete identity prefix, including the actual thread ID/label and verification
flags, on **every** `submit-action`. Do not shorten later calls to only
`--game-dir` and `--seat`; the server rejects unauditable Codex submissions and
identity drift.

The MCP submission schema exposes `action_id`/`action`, `actions`, the exact
plan enum, a 180-character reason, confidence, yield, and a 500-character
memory update directly. Schema-invalid output is journaled against the same
decision with its full legal alternatives and compact retry context.

## Primary loop

The primary uses:

```powershell
python simctl.py coordinator-tool --game run/codex-arena status
python simctl.py coordinator-tool --game run/codex-arena get-arbiter-task
```

The loop is:

1. Validate four decks and exact profiles.
2. Start A–D once, preferably through `arena-codex-run`, and cache each exact
   profile/initial packet only in its own persistent session.
3. Read the next principal from public coordinator status.
4. Route a pilot task only to that seat's original thread.
5. Accept strict JSON and submit through the fixed-seat surface.
   Private task data is submitted only to that surface. A pilot's message back
   to the primary may contain only status, accepted decision IDs, and the next
   principal boundary; it must not echo hand/library cards, private search
   choices, memory, or task packets. A blocked pilot may add a sanitized error
   code/message containing no private game data so the coordinator can
   distinguish a transport failure from a rules stop.
6. Return compact rejection data to the same thread when needed.
7. In `trusted_only`, stop on an arbiter task: an evidence run may not improvise
   live semantics. Only an explicitly non-evidence `arbitrate_or_pause`
   development run may use the primary's scoped public/rules arbitration.
8. Stop immediately if `suppressed_meaningful_windows` is nonzero or a
   material semantic/fidelity issue needs implementation.
9. Save periodically, then replay-verify and generate review artifacts.

Do not spawn a fresh agent per action, prompt every pilot at every priority
window, disclose all hands to the primary, let pilots advise one another, or
continue past meaningful suppression.

An app-level pilot message that echoes private task data is itself a hidden-
information fidelity failure even when the durable game record and fixed-seat
tool audit are clean. Pause immediately; never treat the affected run as deck
operation evidence.

## Responses and ordered plans

A single action is:

```json
{
  "action_id": "play-land:A21",
  "choices": {},
  "plan": "DEVELOP_MANA",
  "reason": "Play the untapped green source before deploying the accelerator.",
  "confidence": 0.93,
  "yield": null,
  "memory_update": "Need blue and black for the commander."
}
```

A main-phase plan uses top-level `actions`. The server derives ordinary mana
payments. Remaining validated actions are persisted in `plans.json`, so a
one-shot fixed-seat tool process can resume the same plan safely. Execution
may include `future_choices` for a later seat-private search result; card names
are resolved only after the private choice exists. Execution stops on another
principal's response, material stack change, hidden draw, invalid target,
changed cost, an unsupplied new player/search/trigger-order choice, combat,
semantic uncertainty, or fidelity failure.

## Stop, resume, inspect, and verify

Every accepted action saves the record. To pause, cease routing new tasks and
finalize the accepted prefix; do not fabricate a game result. To resume, reopen
the same run and rerun `arena-codex-run`; it restores the coordinator-only
seat-to-thread registry and routes only to the recorded original thread IDs. A
failed thread resume is a restart event and a persistence-fidelity failure, not
permission to silently spawn a replacement.

Inspect public progress and artifacts:

```powershell
python simctl.py arena status run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py arena pause run/codex-arena `
  --db data/scryfall-current.sqlite3 --kind fidelity_failure `
  --reason "material rule boundary requires code work"
python simctl.py arena resume run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py arena abort run/codex-arena `
  --db data/scryfall-current.sqlite3 --reason "operator requested"
python simctl.py arena finalize run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py refresh-record run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py verify-record run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py inspect-game run/codex-arena --pretty
python simctl.py inspect-decisions run/codex-arena
python simctl.py report run/codex-arena --db data/scryfall-20260728-compact.sqlite3
python simctl.py replay run/codex-arena `
  --db data/scryfall-20260728-compact.sqlite3 --verify
```

The manifest records actual thread labels/IDs, invocation counts/timestamps,
reuse, provider, model, reasoning effort, retries, interruptions, and restarts.
If the host does not expose a parent session ID or token counts, those values
remain `null`. It also records one of `created`, `in_progress`, `paused`,
`complete`, `aborted`, or `corrupt`. A paused run has a structured
`pause_reason`/arena stop reason. Passing replay on that record verifies only
the accepted-command prefix, not a completed game.

## Provider and evidence labels

- `scripted`: deterministic regression/fixture provider
- `manual-json`: human or assisted JSON bridge
- `subprocess-json`: external process with JSON stdin/stdout
- `codex_subagent`: actual persistent Codex invocation with verified identity

Duplicating Zimone in A/C and Mishra in B/D is useful only for four-seat
protocol testing. It is always `pilot_test`, never matchup evidence. No deck
should be changed from these results. A deck or matchup claim additionally
requires trusted material semantics, terminal replay-verified games,
legal-action exposure, exact profiles, genuine strategic pilots, and a
predeclared multi-game sample methodology.

The characterized 0.5.0 record remains paused at its original Entomb arbiter
boundary after refresh; identity values that lacked provenance remain
unverified. Version 0.6.0 can execute the generic private searches covered by
its provisional tutor pack, but provisional or unresolved material semantics
still prevent matchup evidence.
