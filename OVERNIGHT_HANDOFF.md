# Integration handoff

Last updated: 2026-07-31

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data. Current generated metrics live in
`docs/PLATFORM_IMPLEMENTATION_STATUS.md`.

## Repository state

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Latest integrated `main` merge:
  `00bd8e1abe08fd254794ab5e1f1b2386291bcbe9`
- Latest certified feature head:
  `5f03ff3f06420238b068193f5193521fa34869df`
- Current focused branch: `agent/browser-lifecycle-journey`, based on
  `00bd8e1`; its candidate commit is the commit containing this handoff.
- Current focused slice: browser combat, public commander damage, confirmed
  concession, natural completion, terminal restart recovery, and exact replay
- Package: `0.8.0`
- Tags: `v0.6.0`, `v0.7.0`
- No `v0.8.0` release tag has been created.

PRs #1–#17 and #24–#35 are merged through ordinary merge commits. PR #24
incorporated the ancestry-proven CR 400–408 stack; PRs #18–#23 were closed as
superseded only after their exact heads were reachable from `main`. PRs #27–#35
integrated the authoritative browser/server vertical slice, restart and
lifecycle hardening, managed local data, UI interaction, spectators/public
logs, the visible fail-closed browser rules boundary, and current trigger/token
mana stabilization. No force push or tag movement was used.

## Deterministic evidence

- The latest integrated feature head `5f03ff3` passed the exact 18-stage local
  merge gate and public matrix before PR #35 merged.
- 3,997 unit/integration tests pass on Windows Python 3.11.9 against the
  compact public CI card database.
- All 3,300 pinned rule records and 425 mechanic records verify against the
  June 19, 2026 rules source. Generated per-rule inventory tests do not imply
  semantic completeness.
- Conformance remains 106 passing, 371 blocked, 80 definition-only, and 2,743
  unreviewed. No complete-rules claim is authorized.
- The deterministic four-player natural-winner, seed-20260730 replay,
  projection/privacy, protocol demo, dependency, repository/history/security,
  wheel build, and clean-install gates pass.
- Generated protocol types, the production browser build, and all seven
  Playwright/Chromium scenarios pass. The browser suite includes four-seat
  isolation, an isolated spectator/public log, 1v1 room recovery, penalized
  mulligan choices, a target/stack/Treasure/Bowmasters journey, explicit combat,
  confirmed concession, and a natural commander-damage winner.
- The natural-winner browser record accepted 49 commands, finished with Seat A,
  replayed to the exact final hash, reported zero suppressed meaningful
  windows, and passed its hidden-information audit. A completed concession also
  restores as terminal after server restart and exact replay.
- Merge commit `00bd8e1` is covered by public `main` run `30681492014` across
  Python 3.11/3.12, Ubuntu/Windows, and Browser/Chromium.

GitHub Actions is operating normally. Historical zero-step billing failures
are not current evidence and no administrator bypass is authorized or needed.

Local tool availability:

- Python 3.11.9: available
- Python 3.12: not installed locally
- Node 24.18.0 and npm 11.16.0: available
- WSL2: not installed
- Docker: not installed

The public GitHub matrix supplies supported Python 3.11/3.12 and
Ubuntu/Windows coverage unavailable on this workstation.

## Product boundary

Implemented:

- authoritative deterministic `CommanderEngine`
- strict protocol 3.0 commands with decision IDs, revisions, and idempotency
- principal-specific projections and capability-scoped application commands
- serialized single-process game actors and restart recovery
- SQLite control-plane persistence plus Game Record v3 command replay
- FastAPI HTTP/WebSocket transport with guest identity, CSRF/origin checks,
  invite-only two/four-seat rooms, readiness, removal, leave, and replacement
- owner-only stop/resume and seated-member safe inspection
- per-tab seat isolation and terminal stale-game recovery
- one-command local server/browser startup with daily Scryfall metadata checks,
  atomic snapshot activation, stale-database fallback, and on-demand image cache
- responsive TypeScript browser client with projected tables, card inspector,
  public-zone browsing, click/drag play, cast/activate controls, manual or
  automatic mana, current generic choice forms, and explicit main-phase advance
- invite-authenticated read-only spectators with capability-free projections,
  live WebSocket updates, a complete durable public event log, and restart
  recovery without checkpoint or analyst access
- compact-fixture regressions for modal land faces, Sunscorched Desert, Orcish
  Bowmasters under the browser's trusted-only policy, priority progression,
  exact retry, privacy, and reconnect behavior
- immediate post-land stabilization so represented ETB triggers and their
  choices occur before priority returns
- exact rules-created Treasure mana choices and automatic payment with its
  tap/sacrifice cost
- a deterministic two-browser target/response journey from Sunscorched Desert
  through An Offer You Can't Refuse and Orcish Bowmasters/Amass
- server-issued attack and block declarations, public commander damage by
  source, a true-only concession confirmation, terminal winner/draw rendering,
  and a deterministic natural commander-damage winner
- terminal lifecycle persistence: completed concession survives process restart
  with no reissued player action and the record passes exact replay
- dedicated Playwright API/web ports that do not intercept open manual-game tabs
- durable browser fail-closed handling for legacy records that contain an
  arbiter-only decision; those records now display a rules-boundary pause and
  cannot resemble repeated player priority passes

Not implemented or not complete:

- complete screen-reader audit and every future choice-schema presentation
- production accounts, PostgreSQL, multi-process actor ownership, expiry and
  rate-limit policy, containers, TLS/reverse-proxy deployment, backups, and
  production observability
- complete Comprehensive Rules, Commander-legal Oracle, or rulings enforcement

Optional Codex/LLM adapters remain isolated, untrusted clients. They are not
rules, product, CI, merge, or release authorities.

## Next dependency-ordered work

The inspected full-database duel was created at 17:58 local time, before the
18:44 browser-interaction fix. Its frozen checkpoint used
`semantic_policy=arbitrate_or_pause`, and its frozen registry contained no
Orcish Bowmasters program. It is historical pre-fix evidence, not evidence that
the current generic trigger path failed. Current source hashes for both reviewed
cards match the active full database, and compact trusted-only regressions pass.

Compact current-server browser evidence now covers targeted ETBs, a genuine
stack response through rules-created Treasure payment, combat, concession,
natural completion, process-restart persistence, exact replay, and privacy. The
next focused slice is still a fresh full-database manual/browser journey created
after a clean server restart. Reconfirm the same paths against that active full
snapshot. Treat any new failure as a rules or browser defect, but do not reuse
the pinned pre-fix record as current semantic evidence.

That slice must preserve exact replay, idempotency, seat projection, hidden
information, and the existing no-AI core runtime boundary. Production
deployment hardening follows in a separate focused slice.
