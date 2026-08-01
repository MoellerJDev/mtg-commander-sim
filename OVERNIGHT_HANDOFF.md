# Integration handoff

Last updated: 2026-07-31

This is a sanitized operational summary. It contains no credentials,
capabilities, private hands, library order, private choices, live Game Records,
or provider session data. Current generated metrics live in
`docs/PLATFORM_IMPLEMENTATION_STATUS.md`.

## Repository state

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Browser/runtime integration merge:
  `4c576494dfe6fe60ea31e6891fd8261f9714b4a6`
- Certified feature head:
  `52202490db25fb7be6a2c2dba36bbf4b959a41b2`
- Package: `0.8.0`
- Tags: `v0.6.0`, `v0.7.0`
- No `v0.8.0` release tag has been created.

PRs #1–#17 and #24–#31 are merged through ordinary merge commits. PR #24
incorporated the ancestry-proven CR 400–408 stack; PRs #18–#23 were closed as
superseded only after their exact heads were reachable from `main`. PRs #27–#31
then integrated the authoritative browser/server vertical slice, restart and
lifecycle hardening, the managed local data runtime, and browser gameplay
polish.

Local and remote branch cleanup is complete: only `main` remains, every merged
feature commit is reachable from it, and there are no open pull requests. No
force push or tag movement was used.

## Deterministic evidence

- The exact local merge gate passed all 18 stages at `5220249`.
- 3,986 unit/integration tests pass on Windows Python 3.11.9 against the
  compact public CI card database.
- All 3,300 pinned rule records and 425 mechanic records verify against the
  June 19, 2026 rules source. Generated per-rule inventory tests do not imply
  semantic completeness.
- Conformance remains 106 passing, 371 blocked, 80 definition-only, and 2,743
  unreviewed. No complete-rules claim is authorized.
- The deterministic four-player natural-winner, seed-20260730 replay,
  projection/privacy, protocol demo, dependency, repository/history/security,
  wheel build, and clean-install gates pass.
- Generated protocol types, the production browser build, and the isolated
  four-context Chromium test pass.
- PR #31 head `5220249` passed the public Python 3.11/3.12 Ubuntu/Windows and
  Browser/Chromium matrix in run `30674523046`.
- Merge commit `4c57649` is covered by public `main` run `30674808173`.

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
- compact-fixture regressions for modal land faces, Sunscorched Desert, Orcish
  Bowmasters, priority progression, exact retry, privacy, and reconnect behavior

Not implemented or not complete:

- spectator sessions and complete public-log presentation
- complete screen-reader audit and every future choice-schema presentation
- production accounts, PostgreSQL, multi-process actor ownership, expiry and
  rate-limit policy, containers, TLS/reverse-proxy deployment, backups, and
  production observability
- complete Comprehensive Rules, Commander-legal Oracle, or rulings enforcement

Optional Codex/LLM adapters remain isolated, untrusted clients. They are not
rules, product, CI, merge, or release authorities.

## Next dependency-ordered work

Keep broad sequential rules review frozen unless a browser path exposes a
concrete rules blocker. The next focused server/browser slice should add:

1. spectator-safe, read-only session/projection handling;
2. complete public game-log retrieval and browser presentation; and
3. browser end-to-end journeys for targeting, stack response, combat,
   concession, natural completion, and process restart.

That slice must preserve exact replay, idempotency, seat projection, hidden
information, and the existing no-AI core runtime boundary. Production
deployment hardening follows in a separate focused slice.
