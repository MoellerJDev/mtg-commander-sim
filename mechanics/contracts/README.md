# Mechanic contracts

Every mechanic must receive a versioned contract before the generated registry
may mark it trusted.

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

Run `simctl rules sync` after changing a contract so its hash and status are
overlaid into `mechanics/registry.json`, then run `simctl rules verify`.
