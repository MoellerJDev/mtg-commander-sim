---
title: "ADR 0007: CardProgram runtime components"
status: "ADR"
authoritative_source: "this decision record"
verified: "2026-08-01"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0007"
decision_status: "accepted"
date: "2026-08-01"
---

# ADR 0007: CardProgram runtime components

## Context

Some reviewed static and replacement abilities were represented by empty
CardProgram effects while `CommanderEngine` selected their behavior from a
printed card name. Moving those branches into card-named helpers would preserve
the same hidden coupling. Encoding them as ordinary resolving effects would be
incorrect because they apply continuously to later events.

## Decision

CardProgram abilities may declare versioned runtime component descriptors in
their existing `handlers` field. A descriptor identifies a registered generic
handler, event, applicability data, and typed parameters. Registry validation
is deterministic and fail-closed; unknown IDs, schema versions, fields, or
parameter shapes make the semantic program invalid before a game begins.

The first component is `replacement.token.additional.v1`. It handles only a
mandatory, fixed, commutative addition to a nonempty token-creation event when
the event and source have the same controller and the original tokens contain
the declared card types. It emits typed additional-token intents. The engine
creates every token in the modified event through its canonical token path and
gives them one creation timestamp.

This component does not implement general replacement-effect ordering. It
excludes optional effects, noncommutative choices, replacement rediscovery,
quantity doubling, and outputs computed from mutable state. Those cases remain
blocked behind CR 616 work.

The second component is `continuous.anthem.power_toughness.v1`. It emits a
source-stamped CR 613 layer-7c effect for a fixed modifier applied to
same-controller permanents with declared subtypes. Runtime source collection
uses a narrow read-only state protocol. Applicability is evaluated after
earlier layers, so represented layer-4 subtype changes affect the anthem. A
stable semantic-program/descriptor identity keeps multiple components on one
source distinct.

This component does not implement general continuous-effect compilation. It
excludes power/toughness-setting effects, characteristic-defining abilities,
state-derived amounts, same-layer dependency discovery, and ability-removal
dependency interactions.

Printed names and Oracle IDs may appear in reviewed CardProgram/override
registration data, tests, and provenance, but not in generic handler logic or
engine dispatch. Game Record remains version 3; the complete CardProgram map,
including runtime descriptors, stays fingerprinted in the existing semantic
registry and CardProgram provenance.

When a complete historical semantic snapshot predates runtime descriptors, the
registry may expose the package's validated built-in descriptor as a narrowly
versioned compatibility component without mutating the loaded program map or
its recorded fingerprint. The engine still requires the descriptor's Oracle
source hash to match the record-pinned card database. New records carry the
descriptor directly and do not use this bridge.

## Consequences

- Static runtime participation is inspectable in `simctl card explain` rather
  than inferred from an engine branch.
- Every component declares a stable ID, schema version, rules references,
  capability dependencies, applicability, typed output, and replay tests.
- Runtime family registries share one frozen validation contract and one
  generated architecture inventory/fingerprint.
- Repeated card implementations can share one component while retaining
  card-specific token definitions in reviewed data.
- Historical complete registries retain the old represented behavior through
  the explicit compatibility component while their semantic fingerprints stay
  unchanged.
- The first migrations remove two printed-name branches from token creation
  and the Stridehangar Thopter anthem branch from characteristic evaluation;
  unrelated card-specific and continuous-effect debt remains separate work.

## Alternatives

- Move each branch to a card-named Python helper. Rejected because it preserves
  card identity as generic runtime control flow.
- Parse Oracle prose during a game. Rejected because live games use validated,
  fingerprinted CardPrograms and never perform speculative compilation.
- Claim the existing general replacement framework covers these effects.
  Rejected because affected-player ordering and replacement rediscovery are
  not complete.
