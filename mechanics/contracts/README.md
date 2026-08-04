---
title: "Mechanic contracts"
status: "current"
authoritative_source: "mechanic contract schema and contract files"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "rules and compiler contributors"
maintenance: "hand-maintained"
---

# Mechanic contracts

Every mechanic must receive a versioned contract before the generated registry
may mark it trusted.

The integrated source tree currently contains 62 partial contracts, one tested
contract, one trusted contract, and 361 unclassified mechanics. Vigilance is
the first trusted mechanic contract, bounded to CR 508.1f and CR 702.20's
attack-declaration tap exception using the attacker's current effective
keywords. Broader combat, continuous-effect, copying, and granted-keyword
behavior remains governed by its own capabilities. The snapshot-complete gate
remains false.

A contract records its CR/glossary references, dependencies, zones, objects,
events, state reads/writes, costs, timing, targets and choices, hidden
information, APNAP behavior, layer/replacement participation, copy/control/
zone-change/source-leaves behavior, variants, witness cards, rulings, tests,
implementation version, and trust level.

Card-specific overrides live in a separate reviewed registry and must explain
why the typed generic compiler is insufficient. Do not add printed-name
branches to core engine modules.

Contracts use `mechanics/contract.schema.json` plus cross-field validation in
`mechanic_contracts.py`. A trusted contract must be reviewed, have witness
cards and tests, and have no known blockers. A partial contract links evidence
without allowing a happy-path test to be mistaken for complete support.

Current partial contracts cover Flying, deathtouch, protection, simple
compiler families, CR 613 continuous-effect ordering, CR 616 replacement/
prevention ordering, CR 400 logical object incarnation, CR 111 token
lifecycle, CR 707 represented copy-object lifecycle, serialized
zone/World-since timestamp moments, and the implemented CR 704
state-based-action subset including the world rule. Separate CR 120, 210, and
310 contracts describe the implemented permanent-damage results, defense
characteristic, and Siege entry/protector/combat/trigger subset. The CR 310
contract includes exact-incarnation exile and the optional transformed cast,
but remains partial because replacement ordering and cast grammar outside
compiled cost/target schemas are blocked. CR 608 and 609 contracts trace the
resolution and effect pipelines while keeping incomplete target, choice, LKI,
APNAP, `as though`, source-selection, Aura, mutate, and resolution-trigger
families explicitly untrusted. CR 607 traces linked abilities while keeping
generic ability-pair IDs, linked object sets and facts, copied/acquired pairs,
cross-face links, and cross-object token/emblem links explicitly untrusted.
CR 606 traces loyalty abilities and verifies their base permanent, timing,
activation-limit, and payability behavior while modified and combined loyalty
costs remain fail-closed and explicitly untrusted.
CR 605 traces mana abilities and verifies stackless activated-mana resolution
and spell-payment use while possible-output grammar, generic triggered mana
abilities, and arbitrary nested payment windows remain explicitly untrusted.
CR 604 traces static-ability handling with battlefield source-lifetime and
moved-Equipment witnesses while characteristic-defining, attachment, stack,
zone-permission, and current-information/LKI coverage remains untrusted.
CR 603 traces trigger detection, pending batches, stack placement,
controller-at-trigger-time, intervening conditions, APNAP groups, delayed
triggers, and logical-incarnation guards. Complete trigger grammar, the
two-part trigger-on-trigger ordering loop, modal and optional choices,
state/player-loss/reflexive triggers, delayed-source provenance, and the full
look-back exception matrix remain untrusted.
CR 601 traces the casting proposal, represented modes/targets/costs, mana
abilities during payment, transactional rollback, spell-stack creation,
cast-trigger batching, and priority return. The current implementation moves
the card to the stack only after choices and payment, so prospective stack
characteristics, complete cost and target grammar, proposal-dependent timing
permissions, division, and opponent-made choices remain explicitly untrusted.
CR 600 pins the Spells, Abilities, and Effects section taxonomy to the
dependent CR 601-609 contracts. Because CR 600 contains only a heading, it is
definition-only and does not create a standalone behavioral claim.
CR 505 traces ordinary precombat/postcombat main boundaries, empty-stack pass
completion, active-player priority, sorcery-speed timing, Saga advancement,
and stackless land plays. Legal-action hints now require a true main-phase
phase/marker pair rather than any synthetic `main` step label. Additional or
skipped combats and main phases, ordinal identity, Archenemy, Attractions,
and complete simultaneous Saga qualification, replacement, and trigger
ordering remain blocked.
CR 504 traces the stackless turn-based draw, trusted one-at-a-time replacement,
post-draw state-based actions, combined semantic/delayed trigger ordering, and
active-player priority. It also records the Commander multiplayer and duel
first-turn modifiers and empty-library loss ordering. Complete draw
replacement/prevention semantics and the universal interaction matrix remain
untrusted.
CR 506 traces the combat-phase structure, attacking/defending roles, removal
from combat, “attacks or blocks alone,” requirement snapshots, and
combat-relative timing vocabulary. Tapping and untapping preserve represented
combat relationships, and zone, control, phasing, or type invalidation removes
represented combatants without erasing the historical attacker predicate used
by CR 508.8. Alternate multiplayer options, generic effect-created or
effect-removed combatants, planeswalkers, requirement snapshots, provenance
queries, extra combats, and the complete timing grammar remain blocked.
CR 507 traces the beginning-of-combat defending-player, trigger, priority, and
declare-attackers handoff. Supported Commander profiles establish all active
opponents as defending players without a choice, while multiplayer variants
that require choosing one defender remain rejected and explicitly blocked.
CR 510 traces combat-damage assignment authority, legal recipients, exact
power totals, atomic rollback, and ordinary simultaneous dealing. First/double
strike, trample, lifelink, APNAP damage triggers, and the universal simultaneous
replacement/prevention batch remain blocked.
CR 508 traces ordinary attacker eligibility, opponent and Battle routing,
authoritative revalidation, atomic rollback, vigilance, attacking-state
lifetime, active-player priority, and empty-combat step skipping. Planeswalker
destinations, the complete restriction/requirement solver, banding, attack
costs, declaration triggers, entry-attacking effects, defending-player LKI,
and target reselection remain blocked.
CR 509 traces ordinary blocker eligibility, defending-player routing, atomic
declaration rollback, blocking-state lifetime, multiplayer declaration order,
and the priority handoff. Requirements, block costs, declaration triggers,
multi-attacker blocks, and entry-blocking effects remain blocked.
CR 511 traces end-of-combat priority, represented boundary triggers, and the
removal-from-combat handoff into postcombat main. The complete grammar for
effects lasting until end of combat remains blocked.
CR 512 traces the structural ending-phase boundary: exactly the end step
followed by cleanup, with no next-turn transition before cleanup completes.
The phase structure passes with exact replay, while all behavior within those
steps remains bounded by the partial CR 513 and CR 514 contracts.
CR 513 traces the end-step boundary, represented permanent and delayed trigger
collection before priority, exact replay, the no-backing-up rule, and duration
handoff to cleanup. It remains partial because the two trigger families do not
yet share one universal same-controller/APNAP ordering batch and complete
Oracle trigger grammar remains untrusted.
CR 514 traces cleanup discard, represented damage and turn-duration clearing,
ordinary no-priority advancement, stabilization, delayed cleanup triggers,
exceptional priority, and the required additional cleanup step. It remains
partial because every turn-duration effect is not yet represented by one
simultaneous duration registry and the complete state-action, replacement,
trigger, APNAP, hidden-information, and replay interaction matrix is absent.
CR 602 traces activated-ability parsing, availability, authoritative costs,
stack placement, tap/untap summoning sickness, object-scoped once-per-turn
history, and sorcery/instant timing. Complete cost and instruction grammar,
CR 601.2b-i parity, transactional rollback, opponent-made activation choices,
cost-altering effects, and acquired-ability provenance remain untrusted.
CR 500–505 trace the ordinary turn, beginning, untap, upkeep, draw, and main
phase boundaries. CR 400–408 trace the general zone/object model, library,
hand, battlefield, graveyard, stack, exile, ante exclusion, and public command
objects. Every contract records exact blockers; these reviews do not imply
complete extra-turn, phasing, trigger, replacement, casual-variant, or emblem
coverage.

Run `simctl rules sync` after changing a contract so its hash and status are
overlaid into `mechanics/registry.json`, then run `simctl rules verify`.
