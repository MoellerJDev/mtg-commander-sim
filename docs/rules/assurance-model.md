---
title: "Rules completeness program"
status: "current"
authoritative_source: "pinned rules corpus, compiler, capability registry, CardPrograms, and generated coverage"
verified: "2026-08-05"
audience: "rules, compiler, and engine contributors"
maintenance: "hand-maintained"
---

# Rules completeness program

The goal is reproducible rules and card support for a pinned Comprehensive
Rules, Oracle and rulings snapshot. The simulator does not claim complete Magic
support while material grammar, capabilities or interactions remain unresolved.

Current implementation, compiler and architecture status is generated in:

- [`docs/RULES_COMPLETENESS_STATUS.md`](docs/RULES_COMPLETENESS_STATUS.md)
- [`docs/COMPILER_COVERAGE_STATUS.md`](docs/COMPILER_COVERAGE_STATUS.md)
- [`coverage/card-unlock-frontier.md`](coverage/card-unlock-frontier.md)
- [`coverage/reusable-piece-matrix.md`](coverage/reusable-piece-matrix.md)
- [`docs/RULES_DEPENDENCY_QUEUE.md`](docs/RULES_DEPENDENCY_QUEUE.md)

## Generic support for new decks

A new deck does not require one branch per card. Deck loading resolves cards
against the pinned local Scryfall database, compiles each Oracle face into
source-spanned CardProgram V2 nodes, declares fine-grained capabilities, and
checks the complete materially reachable program.

The normal path is:

```text
pinned Oracle and rulings
          |
   typed Oracle IR
          |
  CardProgram V2 nodes
          |
capability and interaction closure
          |
typed runtime queries, proposals, coordinators and mutation owners
```

Supported wording automatically benefits every equivalent card. Unsupported
wording remains a precise residual and fails trusted preflight. Card-specific
reviewed overrides are compatibility exceptions, not the scaling model; repeated
shapes must become a generic compiler production.

## Pinned inputs

`rules/source-manifest.json` pins the Comprehensive Rules source. The managed
card-data service pins Oracle and rulings exports in the local database.
Compiler, capability, mechanic-contract, runtime-component and semantic hashes
complete the executable identity stored with Game Record v3.

Refreshing Scryfall data can introduce new wording or change a deck fingerprint.
The new snapshot is compiled and validated independently. It never changes the
meaning of an in-progress or historical game.

## Completeness dimensions

Card and rules support is evaluated across separate dimensions:

- syntax: every material Oracle span is classified;
- lowering: recognized syntax becomes typed nodes with exact source spans;
- capability: every node declares the behavior it requires;
- implementation: each required capability resolves to one canonical owner;
- interaction: materially reachable cross-card behavior is represented or
  explicitly blocked;
- format/profile: Commander and multiplayer dependencies close for the selected
  game profile;
- assurance: positive, negative, replay, rollback, multiplayer, privacy,
  property and mutation evidence passes where applicable.

“Parsed,” “lowerable,” “exact Oracle IR,” “capability-closed,” and “trusted
CardProgram” are intentionally different claims.

## Family acceptance

A rules-family change is complete only when it:

1. implements one reusable behavioral family with a typed owner;
2. routes every represented producer through that owner;
3. shares legal-action advertisement and command validation;
4. removes the competing legacy implementation;
5. lowers applicable Oracle grammar without runtime text parsing;
6. declares precise capability and ambient interaction dependencies;
7. rejects unsupported variants before mutation;
8. adds the applicable conformance and trust evidence;
9. improves or holds measured architecture debt;
10. regenerates the corpus, card frontier and reusable-piece matrix at the final
    exact head.

A dataclass, witness card, test-count increase or generated report is not a
rules-family implementation by itself.

## Trust and overrides

Trusted capabilities require a resolvable implementation, current official rule
references, supported profile coverage, no blockers and the mandatory evidence
set enforced by the registry. Dependencies fail closed. Capability authors
cannot waive the minimum by declaring an empty evidence list.

A genuinely irreducible override pins Oracle, rulings, rule, compiler and test
identity and documents why generic lowering is unavailable. It remains visible
in specificity and trust reports. Do not add printed-name or Oracle-ID behavior
to the universal engine.

## Commands

Use the project interpreter and managed current database:

```powershell
.\.venv\Scripts\python.exe simctl.py rules verify
.\.venv\Scripts\python.exe simctl.py rules coverage
.\.venv\Scripts\python.exe simctl.py rules queue
.\.venv\Scripts\python.exe simctl.py rules next
.\.venv\Scripts\python.exe simctl.py pieces next
.\.venv\Scripts\python.exe scripts\update_card_unlock_frontier.py --check `
  --db data/scryfall-current.sqlite3
.\.venv\Scripts\python.exe scripts\update_reusable_piece_matrix.py --check `
  --db data/scryfall-current.sqlite3
```

Run focused tests during implementation and the change-impact quick gate before
publishing. Regenerate expensive full-corpus artifacts once at the final exact
head, then require public CI for that same SHA.

## Selecting the next family

Use the refreshed dependency queue, card-unlock frontier and reusable-piece
matrix. Prefer a bounded family that removes a shared blocker, reduces engine
responsibility and unlocks multiple cards. Do not use a stale hand-written
roadmap or traverse rules numerically.

Reports must state implemented and blocked rule IDs, capability changes,
producers migrated, architecture deltas, card/residual deltas, assurance results
and known limitations. If measured support falls after a correctness fix, report
the demotion rather than preserving a false positive.
