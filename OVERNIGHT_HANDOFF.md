# Overnight handoff

Last updated: 2026-07-30

## Repository

- Authenticated GitHub owner: `MoellerJDev`
- Repository: `mtg-commander-sim`
- Visibility: private
- Remote: `https://github.com/MoellerJDev/mtg-commander-sim.git`
- Default branch: `main`
- Review-MVP branch: `agent/review-mvp`
- Rules branch: `agent/rules-completeness`
- Rules-program base: `d099fe4`
- This continuation started at:
  `6517dc0870ee9344ea6a2be89bf3b2ea36b61d37`
- Ending checkpoint: the branch `HEAD` containing this handoff
- Package version: `0.8.0`

The ending hash is intentionally referenced as the containing `HEAD`; embedding
that commit's own hash would change the commit. The final task report and
remote branch identify the exact immutable hash.

## Current rules checkpoint

The checkpoint adds a versioned partial CR 400 contract, upgrades the partial
CR 111 and CR 704 contracts, and implements logical card incarnations plus
token lifecycle. It now:

- serializes a monotonically increasing logical incarnation beside stable
  physical card identity;
- routes ordinary zone changes, draws, and casts through that boundary;
- treats same-zone exile and command moves as new objects;
- revalidates targets against the selected incarnation;
- identity-guards implemented linked delayed moves, including the Daretti
  ruling witness;
- clears stale counters/annotations while preserving explicit entry
  continuations;
- lets a token reach its first destination, prevents another move, and causes
  it to cease in the next shared CR 704 snapshot;
- omits physical/incarnation identifiers from seat projections;
- preserves exact command replay with the new authoritative fields.

The prior permanent snapshot behavior remains: toughness, lethal/deathtouch,
loyalty, supported attachment legality, and opposing counter pairs are
detected from one immutable snapshot. `CommanderEngine` applies the combined
batch and repeats before priority.

This is not complete CR 400/111/704 support. Spell/card-copy cessation still
needs a transient noncard representation. The complete CR 400.7 exception
matrix, merged/melded and face-down identity, stickers, all legacy linked
references, world timestamps, counter caps, Sagas, dungeons, space sculptor,
battles, Roles, speed, player-attached Auras, full enchant qualities,
regeneration, and simultaneous replaceable loss/action events remain blockers.

## Pinned coverage

- CR effective date: 2026-06-19
- CR SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Indexed rules: 3,300
- Indexed sections: 156
- Glossary entries: 733
- Discovered mechanics: 425
- Partial/untrusted mechanic contracts: 12
- Unclassified mechanics: 413
- Trusted mechanics in the new corpus registry: 0
- `current_snapshot_complete`: false
- Full Oracle snapshot: 2,957 exact; 15,691 partial; 19,725 unresolved;
  69,664 material residuals
- Commander-legal snapshot: 338 exact; 14,354 partial; 16,930 unresolved;
  61,212 material residuals

## Validation

- Compilation: pass
- Rebuilt compact CI database: 181 cards, 185 aliases, 443 rulings
- Unit/integration tests: 351 passed
- Focused object identity/token lifecycle tests: 14 passed
- Focused CR 704 tests: 12 passed
- Seed-20260730 corrected decision/opportunity test: pass
- Seed-20260730 exact replay: pass
- Seed-20260730 hidden-information audit: pass
- `suppressed_meaningful_windows`: 0 in the regression
- Exact Zimone and Dina preflight: 100 fully playable, 0 partial, 0
  unresolved, trusted-only ready, 0 expected arbiter calls
- Exact Mishra, Eminent One preflight: 100 fully playable, 0 partial, 0
  unresolved, trusted-only ready, 0 expected arbiter calls
- Four-player protocol demo: pass
- Protocol packet benchmark: 1,549 bootstrap / 269 repeated / 108
  declaration estimated tokens
- Repository/history/secret/artifact validation: pass
- JSON schemas checked: 12
- Pinned rules verification: 3,300 rules and 425 mechanics pass
- Wheel clean installation/import/CLI smoke: pass
- Wheel:
  `mtg_commander_sim-0.8.0-py3-none-any.whl`
- Wheel SHA-256:
  `6b1f9391c1316fff0e95c6e2c36eca7318dfc334f9500e61f84c1ed1b8d3b5f6`

## Deck-review evidence state

- Qualifying full games: 0
- `deck_operation_evidence`: 0
- `matchup_evidence`: 0
- Duplicated-pod fixtures remain ineligible for matchup evidence.
- No deck list was modified.

The existing exact-list preflight is semantic closure for the two pinned lists,
not broad Oracle completeness and not game/deck-quality evidence.

## GitHub state

- Authentication: active as `MoellerJDev`; no credential value was recorded.
- Open pull requests at handoff preparation: none.
- Draft rules-completeness PR: not yet opened.
- CI for this local checkpoint: pending commit/push; all required local gates
  above pass.

## Known limitations and next step

There is no external blocker. Continue on `agent/rules-completeness` with the
next dependency-ordered object/SBA slice:

1. add transient spell/card-copy objects and CR 704.5e cessation;
2. migrate remaining physical-reference links to typed incarnation/LKI
   handles and finish CR 400.7 continuation policies;
3. model battlefield/world timestamps and the world rule;
4. integrate destruction/loss with typed replacement and regeneration;
5. add the remaining ordinary CR 704.5 actions and interaction tests;
6. rerun full coverage and every validation gate.

The review-MVP branch still separately lacks three consecutive qualifying
persistent-Codex games, review-batch aggregation, per-deck operation reports,
and its draft PR. Those requirements remain active and must not be inferred
from this rules checkpoint.
