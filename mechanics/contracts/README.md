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
state-based-action subset including the world rule.

Run `simctl rules sync` after changing a contract so its hash and status are
overlaid into `mechanics/registry.json`, then run `simctl rules verify`.
