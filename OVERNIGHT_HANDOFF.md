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

The checkpoint adds versioned partial CR 400/613/704/707 contract updates and
implements serialized copy objects on top of the logical-incarnation,
timestamp, World-rule, and token-lifecycle foundation. It now:

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
- allocates a serialized timestamp moment for each new zone incarnation;
- assigns one shared moment to objects moved simultaneously to a destination;
- separately records when a battlefield object most recently gained World;
- enforces CR 704.5k by keeping the unique newest World permanent or moving
  every World permanent when the newest duration is tied;
- preserves a permanent spell's logical incarnation under CR 400.7a;
- represents spell copies and card copies as serialized noncard objects;
- enforces CR 704.5e when those copies enter invalid zones;
- converts a resolving copied permanent spell into the same token object,
  without emitting a token-creation event;
- omits physical/incarnation identifiers from seat projections;
- omits authoritative zone/World timestamps from seat projections;
- preserves exact command replay with the new authoritative fields.

The prior permanent snapshot behavior remains: toughness, lethal/deathtouch,
loyalty, supported attachment legality, and opposing counter pairs are
detected from one immutable snapshot. `CommanderEngine` applies the combined
batch and repeats before priority.

This is not complete CR 400/111/704/707 support. Complete copiable values,
card-copy casting and playing, Prepare's exile exception, face-down and linked
copy interactions, and copied choice/cost/target exceptions remain blocked.
The complete CR 400.7 exception matrix, merged/melded identity, stickers, all
legacy linked references, complete CR 613.7m APNAP relative timestamps,
consumption of serialized timestamps by every continuous-effect source,
counter caps, Sagas, dungeons, space sculptor, battles, Roles, speed,
player-attached Auras, full enchant qualities, regeneration, and simultaneous
replaceable loss/action events also remain blockers.

## Pinned coverage

- CR effective date: 2026-06-19
- CR SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Indexed rules: 3,300
- Indexed sections: 156
- Glossary entries: 733
- Discovered mechanics: 425
- Partial/untrusted mechanic contracts: 13
- Unclassified mechanics: 412
- Trusted mechanics in the new corpus registry: 0
- `current_snapshot_complete`: false
- Full Oracle snapshot: 2,957 exact; 15,691 partial; 19,725 unresolved;
  69,664 material residuals
- Commander-legal snapshot: 338 exact; 14,354 partial; 16,930 unresolved;
  61,212 material residuals

## Validation

- Compilation: pass
- Rebuilt compact CI database: 181 cards, 185 aliases, 443 rulings
- Unit/integration tests: 366 passed
- Focused object identity/token lifecycle tests: 15 passed
- Focused copy-object lifecycle tests: 8 passed
- Focused CR 704 tests: 18 passed
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
  `07e1d64086a7851a2bfe824741491ad06df2666188434e9baaeb04998741620b`

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

1. migrate remaining physical-reference links to typed incarnation/LKI
   handles and finish CR 400.7 continuation policies;
2. integrate destruction/loss with typed replacement and regeneration;
3. add maximum-counter restrictions and the remaining ordinary CR 704.5
   actions and interaction tests;
4. integrate serialized object timestamps into every continuous-effect source
   and implement CR 613.7m APNAP relative ordering;
5. implement complete copiable-value, card-copy casting, Prepare, and
   specialized copy interactions behind the CR 707 contract;
6. rerun full coverage and every validation gate.

The review-MVP branch still separately lacks three consecutive qualifying
persistent-Codex games, review-batch aggregation, per-deck operation reports,
and its draft PR. Those requirements remain active and must not be inferred
from this rules checkpoint.
