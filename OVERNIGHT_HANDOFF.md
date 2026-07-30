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

The checkpoint adds a versioned partial CR 704 contract and an immutable
permanent snapshot evaluator. It distinguishes:

- toughness-based graveyard movement from lethal/deathtouch destruction;
- indestructible from non-destruction state actions;
- planeswalker loyalty 0;
- supported Aura, Equipment, and Fortification attachment legality;
- attached source types that must become unattached;
- opposing +1/+1 and -1/-1 counter pairs.

`CommanderEngine` applies the detected batch and repeats before priority.
Declarative enchant predicates replaced the prior printed-name-only Animate
Dead state check; the card's semantic transition records its changed enchant
restriction as data.

This is not a complete CR 704 implementation. The contract lists token/copy
cessation, world timestamps, counter caps, Sagas, dungeons, space sculptor,
battles, Roles, speed, player-attached Auras, full enchant qualities,
regeneration, and simultaneous replaceable loss/action events as blockers.

## Pinned coverage

- CR effective date: 2026-06-19
- CR SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Indexed rules: 3,300
- Indexed sections: 156
- Glossary entries: 733
- Discovered mechanics: 425
- Partial/untrusted mechanic contracts: 11
- Unclassified mechanics: 414
- Trusted mechanics in the new corpus registry: 0
- `current_snapshot_complete`: false
- Full Oracle snapshot: 2,957 exact; 15,691 partial; 19,725 unresolved;
  69,664 material residuals
- Commander-legal snapshot: 338 exact; 14,354 partial; 16,930 unresolved;
  61,212 material residuals

## Validation

- Compilation: pass
- Rebuilt compact CI database: 181 cards, 185 aliases, 443 rulings
- Unit/integration tests: 335 passed
- Focused CR 704 tests: 10 passed
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
  `cc83fae44e018d22e3a1a86b1a9638e18bea8de35ab089851ca8f6eee1053808`

The first wheel verification attempt found seven historical ignored wheels in
the shared `dist/` directory and correctly refused ambiguity. Verification was
rerun from a fresh one-wheel temporary output directory and passed.

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
next dependency-ordered CR 704/object-identity slice:

1. move token and spell-copy cessation into the shared snapshot;
2. model battlefield/world timestamps and the world rule;
3. integrate destruction/loss with typed replacement and regeneration;
4. add the remaining ordinary CR 704.5 actions and interaction tests;
5. rerun full coverage and every validation gate.

The review-MVP branch still separately lacks three consecutive qualifying
persistent-Codex games, review-batch aggregation, per-deck operation reports,
and its draft PR. Those requirements remain active and must not be inferred
from this rules checkpoint.
