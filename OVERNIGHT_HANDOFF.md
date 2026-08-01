# Integration handoff

Last updated: 2026-08-01

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data. Current generated metrics live in
`docs/PLATFORM_IMPLEMENTATION_STATUS.md`.

## Repository state

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Latest integrated `main` merge:
  `939409d1e2b5a41ade9d9ae71577dd5d653d4934`
- Latest certified feature head:
  `860fb2aabee2bd941e2aafedccec57f001f856b7`
- Current focused branch: `feat/rules-goad-requirements`, based on
  `939409d`; its
  candidate commit is the commit containing this handoff.
- Current focused slice: typed noncopiable goad designations, anchored generic
  Oracle lowering, single/multiple-player declaration requirements, exact
  duration/zone identity, public projection, static prohibition, bounded
  maximization, and exact replay
- Package: `0.8.0`
- Tags: `v0.6.0`, `v0.7.0`
- No `v0.8.0` release tag has been created.

PRs #1–#17 and #24–#39 are merged through ordinary merge commits. PR #24
incorporated the ancestry-proven CR 400–408 stack; PRs #18–#23 were closed as
superseded only after their exact heads were reachable from `main`. PRs #27–#35
integrated the authoritative browser/server vertical slice, restart and
lifecycle hardening, managed local data, UI interaction, spectators/public
logs, the visible fail-closed browser rules boundary, current trigger/token
mana stabilization, and the core combat-keyword slice. PRs #37–#39 add real
combat damage steps, APNAP damage/trigger batching, and the shared finite
attack/block declaration solver. No force push or tag movement was used.

## Deterministic evidence

- The latest integrated feature head `fc5e8be` passed the exact 18-stage local
  merge gate and public matrix before PR #36 merged.
- The integrated 4,022-test suite passed PR #39 and its `main` merge across
  Python 3.11/3.12 on Ubuntu/Windows plus Browser/Chromium. One hundred new
  and directly impacted test cases pass locally on the current goad branch;
  its full regression remains delegated to PR CI.
- All 3,300 pinned rule records and 425 mechanic records verify against the
  June 19, 2026 rules source. Generated per-rule inventory tests do not imply
  semantic completeness.
- Conformance is 115 passing, 367 blocked, 81 definition-only, and 2,737
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
- Feature head `860fb2a` is covered by PR #39 run `30687795802`; merge commit
  `939409d` is covered by `main` run `30687987451`, both across Python
  3.11/3.12, Ubuntu/Windows, and Browser/Chromium.

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

The lifecycle/browser milestone is integrated. Rules work now proceeds in
coherent dependency families. Reusable combat keyword interactions, real split
damage steps, APNAP assignment announcements, typed final combat results, and
post-damage trigger batching are implemented without promoting their broader
contracts beyond partial/untrusted. The shared attack/block solver now handles
exact source-local requirements, lure/menace restrictions, and typed goad; the
next declaration slices are conditional and other effect-granted requirements,
optional attack/block costs, and multi-block grammar. The universal typed CR
120.4/614/615/616 damage replacement/prevention/result pipeline remains the
deeper prerequisite for noncombat damage and broader Oracle trust.

Each rules PR should run its new and directly impacted tests locally, then use
the public PR matrix as the full regression authority. Preserve exact replay,
transaction rollback, idempotency, seat projection, hidden information, and
the no-AI core runtime boundary.
