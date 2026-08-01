# Changelog

## Unreleased

### Managed local runtime and responsive browser

- Added a card-first table inspector: pointer hover and keyboard focus drive a
  persistent large-art/Oracle-text viewer, visible double-faced cards can switch
  faces, and narrow layouts offer the same view in an enlarged dialog.
- Made every projected graveyard and exile directly browsable from its player
  board, enriched represented card spells on the stack for safe inspection, and
  retained opposing hand/library privacy.
- Changed playable card clicks into selection with object-scoped actions while
  keeping drag-to-battlefield and manual mana-source activation as fast paths;
  the action tray remains a complete fallback over the same server-issued IDs.
- Made drag-to-battlefield work through both native drag data and a pointer
  fallback, with a Chromium two-browser test that proves the exact card leaves
  hand and enters the battlefield rather than merely looking draggable.
- Added Arena-style card interaction: legal hand/command cards now show their
  specific play or cast action, can be clicked or dragged to the battlefield,
  and offer an explicit Auto-mana confirmation instead of an unlabeled generic
  verb.
- Added optional Manual mana mode. Legal mana sources become clickable in the
  projected battlefield, activation order is recorded normally, exact
  multi-color modes are selected through a server-issued form, and casting
  consumes floated mana before routine automatic completion.
- Kept generically enforced mana-mode life payments and self-damage inside the
  trusted preflight boundary, so manual activation does not incorrectly
  downgrade sources such as Elves of Deep Shadow.
- Fixed modal double-faced land plays. Agadeem's Awakening now advertises
  **Play Agadeem, the Undercrypt**, prompts for the land face's exact 3-life
  entry choice, enters on that face, and renders the matching characteristics
  and image instead of being silently returned to hand.
- Browser games now require the active player to explicitly leave precombat
  and postcombat main. The same pass action is labeled **Continue to combat**
  or **End turn**; empty nonactive response windows remain safely automatic.
- Added reviewed Sunscorched Desert and Orcish Bowmasters semantics, including
  targeted ETB damage, permanent-spell resolution, opponent extra-draw
  triggers, and generic Amass Orcs execution. Unsupported trusted-only
  resolution now pauses the visible game lifecycle instead of leaving clients
  on an inaccessible arbiter task.
- Hardened the same boundary for records created by older browser builds. A
  persisted arbiter-only decision now becomes a durable, non-resumable browser
  rules pause, player actions disappear, and every seat is told that no player
  action or priority pass is pending. New browser records are regression-checked
  for `trusted_only`, debug trace retention, and the reviewed Sunscorched Desert
  and Orcish Bowmasters programs.
- Reduced normal local startup to `python -m server`: the launcher installs
  missing browser dependencies, rebuilds changed React sources, serves the
  production client and API from one origin, and opens the local UI.
- Added visible first-run setup, 24-hour Scryfall bulk-manifest checks, atomic
  Oracle/rulings SQLite builds, current-pair archive retention, and
  fingerprinted database snapshots retained only for saved Game Records that
  still require them.
- Made startup verify and activate the newest available Scryfall snapshot
  before deck import becomes ready, and added exact-fingerprint confirmation
  for future-dated preview legality without weakening semantic fail-closed
  behavior or ordinary Commander construction errors.
- Kept an existing card database available when Windows prevents pending-update
  activation because another local server still has the SQLite file open; the
  system status now identifies the lock and requests a clean restart.
- Indexed Scryfall image references in SQLite and added a host-restricted,
  size-bounded, atomic local image cache with bounded deck prefetch and
  per-visible-card browser requests; bulk card data never enters the browser.
- Reworked the room and game surfaces into responsive desktop/mobile layouts
  with deck-ready summaries, card art, stack/activity context, accessible
  modal focus/Escape behavior, reconnect controls, reduced-motion support, and
  exact-envelope retry after ambiguous command delivery.
- Kept the host invite available after readiness and reload, added owner-only
  invite replacement with immediate old-code invalidation, and added a
  seat-scoped pregame **Change deck / Unready** flow.
- Isolated guest authentication per browser tab (including WebSockets) so
  shared incognito cookie jars cannot collapse all players into the last seat.
- Added explicit two-player `commander_duel` and four-player room creation,
  owner seat removal, nonowner leave, and atomic **New room** replacement.
- Added invite-authenticated watch-only memberships. Spectators receive a
  capability-free public projection over HTTP/WebSocket, cannot submit seat
  commands, and can leave an active table without changing any player state.
- Added a serialized, paginated complete public-log endpoint and browser
  dialog. Browser records retain every event; responses remove raw details and
  private visibility, and the public history survives reconnect and process
  restart.
- Added bounded startup retry backoff for already-open room pages and accurate
  `starting` system status while card data is being verified.
- Fixed production WebSocket origin validation so the one-command UI's exact
  same origin is accepted without a Vite-only allowlist override; unrelated
  origins remain rejected.
- Replaced opaque stale-game WebSocket 403 reconnect loops with one terminal
  seat-safe message and a **Return to lobby** path, and made disconnect wakeups
  cancellation-safe on Python 3.11.
- Extended application and Chromium coverage for managed data, archive/snapshot
  cleanup, record-pinned recovery, local static serving, 390-pixel layout,
  focus restoration, and byte-equivalent idempotent command retry.

### Authoritative server/browser vertical slice

- Added strict protocol 3.0 command envelopes with client command IDs,
  expected-view revisions, server-derived principals, delegated-choice
  filtering, stable receipts, and durable idempotent replay.
- Added one bounded single-writer `GameActor` per active game, fail-closed
  persistence errors, Game Record-before-ack ordering, and SQLite guest, room,
  seat, deck, game-index, and idempotency storage.
- Added expiring guest sessions, CSRF protection, hashed invite/session
  secrets, atomic four-seat room claims, Moxfield or pasted-list validation,
  multiplayer game start, seat-scoped HTTP projection, and WebSocket fan-out.
- Added independent ephemeral connection cursors so multiple tabs and reconnects
  cannot corrupt one another's projection delta base.
- Added a React/TypeScript room and table client, generated schema bindings,
  hash-verifying reducer, production build, and a real Chromium test using four
  isolated contexts through all four opening keep decisions and reconnect.
- Preserved Game Record v3 replay truth while adding optional network command
  audit fields; raw guest tokens, invite codes, and decision capabilities remain
  absent from durable records.

### Platform direction

- Made the deterministic, server-authoritative browser platform the primary
  product target.
- Removed AI/Codex runs from product, rules, merge, and release completion
  criteria while retaining existing adapters as optional untrusted clients.
- Added a generated platform readiness ledger and CI stale-artifact check.
- Made manual combat-damage assignment server-authoritative: noncombat sources,
  unrelated recipients, excessive totals, duplicate pairs, malformed fields,
  and client-supplied semantic flags are rejected transactionally.
- Added a source-linked CR 505 main-phase contract with exact phase-end replay,
  stack-resolution persistence, active priority, Saga-before-priority, ordinary
  sorcery-speed, and stackless land-play evidence.
- Tightened cast and land legal-action hints to the actual precombat or
  postcombat main phase instead of trusting a standalone synthetic `main`
  step label.
- Added exact multi-blocker replay evidence and fail-closed first-strike
  characterization for the partial CR 510 contract.
- Corrected CR 504 draw-step ordering so the turn-based draw or trusted
  replacement, state-based actions, and one combined trigger-order batch all
  finish before priority; delayed draw-step triggers can no longer preempt or
  silently skip the draw.
- Added source-linked CR 504 coverage for stackless draws, trusted Dredge,
  empty-library loss timing, multiplayer and duel first-turn modifiers, and
  exact replay without promoting the incomplete draw-replacement corpus.
- Added a source-linked CR 506 combat-phase contract, authoritative combat
  role tests, and exact empty-combat replay without promoting unsupported
  multiplayer variants, effect-created combatants, or timing grammar.
- Removed represented attackers and blockers after zone, control, phasing, or
  type invalidation while retaining the historical attacker predicate needed
  to advance correctly under CR 508.8; tapping and untapping preserve combat.
- Excluded phased-out creatures from blocker alternatives and authoritative
  blocker validation, with atomic malicious-submission rollback.
- Added exact ordinary blocker declaration/replay and blocking-lifetime
  evidence for the partial CR 509 contract.
- Made attacker alternatives authoritative for the ordinary CR 508.1a
  boundary: tapped, phased-out, summoning-sick nonhaste, and Battle creatures
  are no longer advertised, and every submitted attacker is revalidated.
- Rejected duplicate structured attackers and phased-out attackers or Battle
  targets transactionally, with exact one-command replay for legal attacks.
- Corrected CR 508.8 so a combat with no attacking creatures skips the declare
  blockers and combat damage steps after the declare-attackers priority window.
- Established the supported Commander defending-player set at the beginning
  of combat, kept unsupported single-defender multiplayer profiles fail-closed,
  and fixed permanent/delayed beginning-of-combat trigger coexistence before
  active-player priority.
- Corrected the CR 511.3 boundary so attacking and blocking markers and the
  combat snapshot clear after end-of-combat priority, before postcombat main.
- Added source-linked end-of-combat priority, trigger-coexistence, multiplayer,
  and exact-replay tests while leaving generic duration expiry blocked.
- Source-reviewed CR 512 as an exact structural ending-phase contract: end
  step, then cleanup, with no next-turn transition before cleanup completes.
- Added exact command replay and cleanup-discard handoff coverage for that
  structure while retaining the partial CR 513/514 claim boundary.
- Reviewed ordinary CR 500–505 turn, beginning, untap, upkeep, draw, and main
  phase boundaries with fail-closed coverage for unsupported extra-turn,
  phasing, trigger-order, draw-replacement, and main-phase variants.
- Reviewed CR 400–408 zone boundaries, including logical object identity,
  library and hand privacy, shared battlefield membership, graveyard/exile
  visibility, Commander legality rejection of ante cards, and typed public
  command-zone emblem objects.
- Integrated the CR 400–408 and CR 500–505 backlog into `main` through the
  cumulative PR #24 tip, with 3,925 deterministic tests, 557 reviewed rule
  records, and 49 partial mechanic contracts without promoting the incomplete
  snapshot to trusted.
- Reconciled the intermediate PRs only after their exact heads were
  ancestry-proven reachable from `main`: GitHub recorded #17 as merged and
  #18–#23 closed as superseded. Broad sequential CR review is now frozen for
  the authoritative server/browser vertical slice.
- Recorded the repository's change to public visibility. No software license
  has been selected, and live private game artifacts remain excluded.

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
