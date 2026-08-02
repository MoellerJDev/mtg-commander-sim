---
title: "ADR 0008: runtime trust and default-deny architecture governance"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-exceptions.json"
verified: "2026-08-02"
audience: "rules, compiler, runtime, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0008"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0008: runtime trust and default-deny architecture governance

## Context

The post-PR-58 baseline had two trust ambiguities. Capability records cited
test names without a machine-verified declaration and treated dependency
registry mutation as implementation mutation evidence. CardProgram V2 also
reduced capability, reviewed compatibility, match reachability, and dynamic
state to one `trusted` boolean.

The architecture ratchet used source-line-sensitive mutation locations,
allowed 300 logical lines of engine growth, checked printed names in only
seven files, and prevented only new oversized symbols. A new production module
could enter a familiar prefix without an exact ownership classification.

## Decision

Capability evidence is an explicit generated index bound to the exact registry.
Every declaration identifies the capability, evidence class, fully qualified
test, official rules, profiles, and applicability. Trusted capabilities require
separate passed dependency fail-closed status and killed implementation
mutation status.

CardProgram V2 retains schema version 2 and adds an explicit trust basis:
`capability_closed`, `legacy_reviewed`, `mixed`, `provisional`, `unresolved`,
or `non_rules_governed`. It records intrinsic, format, match, and dynamic
closure layers. Existing reviewed semantic packs remain a measured
compatibility path with source hashes, identities, replay provenance, tests,
and a removal condition; they are never reported as capability-closed.

The architecture policy becomes default-deny:

- engine net logical growth is zero;
- direct GameState writes use stable file, containing-symbol, mutation-kind,
  and normalized-state-path identities;
- existing oversized modules and symbols may not grow;
- card-specificity scanning covers every generic production Python module;
- every production Python module has one exact layer, owner, dependency,
  state-access, visibility, specificity, and replay classification;
- grandfathered debt is bound to `ARCH-EXC-0001` by an exact allowance
fingerprint rather than by line numbers or an informal ADR reference.

## Alternatives

- Keep test-name arrays inside the capability registry. Rejected because test
  existence would still be mistaken for an explicit evidence relationship.
- Treat reviewed semantic packs as capability-closed. Rejected because their
  deterministic scenario evidence does not prove fine-grained applicable
  closure.
- Permit runtime components whenever a capability ID exists. Rejected because
  profile, evidence, dependency, handler schema, and current registry drift
  would remain unchecked.
- Continue aggregate line/write counts and prefix-based module policy. Rejected
  because a new write or dependency could hide behind an unchanged total.
- Add characteristic caching immediately. Rejected until exact invalidation is
  specified and measured uncached behavior demonstrates a need.

## Exact exception

`ARCH-EXC-0001` permits only the identities and size ceilings serialized in
`platform/architecture-guard-baseline.json`. It permits removal but no growth.
It does not authorize new engine methods, state-write identities, printed-name
branches, Oracle-ID literals, semantic operations, oversized symbols, or
modules. The exception ends when those serialized allowances have been
removed or migrated to reviewed owners.

## Consequences

- Renamed or removed evidence tests make the generated index stale.
- Registered handlers and components bind to their declared capability
  closure and fingerprints; malformed registered descriptors fail closed.
- Strict capability-only preflight may fail where reviewed compatibility
  remains. Compatibility readiness is reported separately.
- Adding a Python module requires an explicit classification update.
- Refactoring a direct write may move lines freely when its stable structural
  identity is unchanged.
- Existing oversized symbols cannot grow merely because they predate the
  policy.
- Replay and privacy behavior remain unchanged; new trust fingerprints are
  additive provenance in Game Record v3.

## Removal condition

Delete `ARCH-EXC-0001` when the baseline contains no grandfathered direct
writes, oversized symbols, card-specific engine helpers, printed-name
allowances, or legacy card-specific operations. Until then, each debt-migration
PR must reduce or preserve the exact allowance set and must preserve replay and
principal-scoped visibility.
