# Changelog

## Unreleased

## 0.8.0 — 2026-07-29

### Exact-list semantic closure

- Closed conservative semantic preflight for both pinned live Commander lists:
  100 fully playable cards, no partial/unresolved entries, and no expected
  arbiter calls per list.
- Added the remaining exact Zimone and Mishra costs, permissions, replacements,
  delayed effects, linked choices, copy/token engines, restricted mana, Saga,
  Craft, Crew, loyalty, and tutor families.
- Added deterministic scenarios for the newly promoted programs while
  retaining the existing decision-opportunity, replay, and privacy gates.
- Kept the claim boundary at the validated deck fingerprints; this is not full
  Oracle-corpus or complete Magic-rules coverage.

## 0.7.0 — 2026-07-28

### Exact targets and interaction

- Added declarative target plans spanning stack objects, players, battlefield
  permanents, and visible graveyard/exile/command-zone cards.
- Withheld mandatory-target actions until every target group, mode, timing
  rule, and server-issued cost option is currently satisfiable.
- Added submission and resolution revalidation, partial target survival, and
  separate rules/effect counter telemetry.
- Added trusted counterspell, removal, Channel, graveyard, proliferate,
  Pithing Needle, storm, kicker, overload, pitch, delayed-cost, and life-X
  interaction scenarios for the exact review lists.
- Extended the fidelity report so illegal target exposure fails the record and
  is attributed to infrastructure rather than a pilot.
- Reconstructed the seed-20260730 regression through turn sequence 8 with zero
  suppressed meaningful windows, zero advertised illegal target actions,
  passing seat projection, and exact command replay.

### Repository milestone

- Added offline Linux/Windows CI for Python 3.11 and 3.12.
- Added a compact public exact-list card/rulings fixture and deterministic
  database builder for tests.
- Replaced tracked private-record regressions with sanitized state recipes.
- Added repository-history, secret, capability, schema, wheel, and CLI checks.
- Added contribution, security, and repository-hygiene policies.

## 0.6.0 — 2026-07-28

- Added resumable private-search semantic frames and exact replay.
- Added typed fixed-seat Codex pilot submissions and bounded strategic memory.
- Added explicit Game Record lifecycle, fidelity, and provider telemetry.
- Added persistent four-seat Codex arena orchestration boundaries.
- Preserved scripted, manual, and subprocess pilot providers.

Version 0.6.0 is an experimental protocol/rules baseline. It does not claim
complete Oracle coverage or matchup evidence.
