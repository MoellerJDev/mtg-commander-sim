---
name: commander-arena
description: Coordinate, resume, inspect, or review a four-seat Commander match using one neutral Codex primary and four persistent seat-isolated Codex pilots. Use for Codex-subagent Commander arena runs, hidden-information-safe pilot routing, replay verification, or arena fidelity review.
---

# Commander Arena

Run the primary Codex session as the neutral coordinator and rules arbiter. The
primary is not a fifth pilot and must never select a strategic seat action.
Recommend GPT-5.6 Sol with Ultra reasoning for the primary session. Pilot agents
use the project `.codex/agents/mtg-pilot-*.toml` definitions. The user-selected
fast profile is `gpt-5.6-sol` with `low` reasoning and the `priority` service
tier; do not call it GPT-5.5 or Instant because this runtime does not expose
that identity.

## Start

1. Validate every requested deck as Commander and refresh live Moxfield sources.
   Trust validated live commander metadata and deck contents. Require an exact
   compatible deck-list profile fingerprint; otherwise regenerate the profile
   or mark an explicit commander/archetype fallback with a fidelity warning.
2. Create `commander_review` by default: four players, 40 life, first player
   draws on turn one, and one free multiplayer mulligan. Use `commander_duel`
   only when the user explicitly requests a duel or narrow regression. A
   Commander review arena defaults to `semantic_policy=trusted_only`; verify
   that policy before sending the first pilot task. Use `arbitrate_or_pause`
   only for an explicitly non-evidence development run.
3. Set `MTG_GAME_DIR` to the created record directory. Never place all four
   private hands in the primary prompt.
4. Start exactly four persistent pilot sessions once: `mtg_pilot_a`,
   `mtg_pilot_b`, `mtg_pilot_c`, and `mtg_pilot_d`. Prefer
   `simctl arena-codex-run` when the desktop host counts the primary against
   its four active child slots; that command starts four local Codex sessions
   in parallel outside the child-slot pool.
   Save each actual thread label/ID, provider, model, and reasoning effort.
   If a stable ID or token usage is unavailable, record `null`; do not estimate
   it as observed.
5. Give each pilot only its own fixed-seat façade output, validated profile,
   and initial projected task. The fast broker disables pilot tools and relays
   these values internally without exposing them to the primary. Keep all four
   sessions for the whole match.

Do not spawn a new agent per action. Do not allow a pilot to advise another
seat, inspect the run directory, or spawn nested subagents.

## Coordinate

Loop sequentially even though all four pilot threads remain active:

1. Ask the coordinator surface for the next principal and public fidelity state.
2. Stop immediately if `suppressed_meaningful_windows` is nonzero or another
   material fidelity gate requires code work.
3. For `pilot:A` through `pilot:D`, route the task only to that seat's existing
   thread. Ask for strict JSON matching the typed action/ordered-plan union,
   exact plan enum, and bounded reason/memory fields. The pilot must submit
   private-dependent data only through its fixed-seat tool. Its message back to
   the parent may contain only status, accepted decision IDs, and the principal
   boundary—never hand/library cards, private search choices, memory, or raw
   task data. A blocked response may add a sanitized error code/message only
   when it contains no private game data.
   When the host uses the one-shot `pilot-tool` fallback instead of a persistent
   MCP attachment, every `submit-action` command must repeat the full actual
   invocation identity: provider, model, reasoning effort, stable thread
   ID/label when exposed, `--provider-invoked`, and both available identity
   verification flags. Never abbreviate the command on later turns. A missing
   or changed identity is a fidelity error, not an acceptable unverified action.
4. Submit the response through that seat's fixed façade. On rejection,
   return only the compact error/current task to the same thread and retry.
5. Apply a legal pilot action even when the primary considers it strategically
   poor. Never silently replace it.
6. For an arbiter task under `trusted_only`, stop the game without live
   improvisation. Only an explicitly non-evidence `arbitrate_or_pause`
   development run may resolve it in the primary using public/rules context.
7. Ask only the principal that actually has a meaningful task. Do not ask every
   pilot to answer every priority window.
8. Allow ordered plans for normal development. Stop a plan on an opposing
   response, material stack/state change, hidden draw, invalid target, changed
   cost, an unsupplied new player choice, combat, semantic uncertainty, or
   fidelity failure. A plan may supply a future private-search card name, but
   only the fixed-seat server may resolve it after that private choice exists.
9. Save/checkpoint periodically and after every accepted external action.
10. If a pilot echoes any private task data into the parent-message channel,
    stop immediately and classify the run as a fidelity failure. A clean
    durable hidden-information audit cannot retroactively make that app-level
    disclosure safe.

Never continue after a suppressed meaningful window. Never grant pilots raw
capabilities, checkpoint access, arbitrary state mutation, or arbiter DSL.

## Resume or inspect

Load the existing record, verify its game ID and four-seat thread registry, and
resume each original session. `arena-codex-run` performs this recovery
automatically. A failed resume is an interruption/restart event; do not silently
create a replacement. Use the coordinator surface for public progress and each
fixed-seat surface only for its assigned pilot.

Distinguish provider types precisely:

- `scripted`: deterministic regression fixture
- `manual-json`: human/Codex file bridge
- `subprocess-json`: external process adapter
- `codex_subagent`: actual recorded persistent Codex subagent invocation only

Never label a mock, unavailable provider, or manual response as
`codex_subagent`.

## Finish and report

1. Stop at the requested turn, a win, an unresolved material semantic, or a
   fidelity failure.
2. Mark an unfinished run `paused` with its exact structured stop reason; never
   imply that stopping coordination ended the game.
3. Save the final checkpoint and opportunity journal, atomically rebuild
   derived artifacts, and run exact accepted-command-prefix replay
   verification (`complete_game` scope only for a terminal game).
4. Generate the review and hidden-information audit.
5. Report infrastructure failures separately from deck and pilot findings.
6. Confirm `suppressed_meaningful_windows == 0` before claiming call reduction.
7. Treat duplicated-deck protocol fixtures as `pilot_test`, never matchup
   evidence. Do not claim deck or matchup superiority without semantic and
   sample-size gates.

The primary may coordinate and arbitrate, but it must never make a strategic
decision for a seat.
