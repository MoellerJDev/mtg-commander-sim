---
title: "ADR 0034: intrinsic entry counters use the replacement tree"
status: "ADR"
authoritative_source: "this decision record and intrinsic entry-counter implementation"
verified: "2026-08-08"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0034"
decision_status: "accepted"
date: "2026-08-08"
---

# ADR 0034: intrinsic entry counters use the replacement tree

## Context

Planeswalkers and Battles enter with loyalty or defense counters because of
CR 306.5b and 310.4b. The previous engine initialized those counters after a
zone move by writing the permanent's counter map directly. That bypassed
CR 614.16 replacement ordering, could not suspend for competing replacements,
and gave compilation no fine-grained declaration for behavior derived from a
card's type line rather than its Oracle text.

## Decision

Compile an immutable card-form declaration from the canonical parsed type set
and printed nonnegative integral loyalty or defense value. The declaration is
source-spanned against the exact type line and requires
`counter.producer.intrinsic_entry`; it is not represented as Oracle text and is
not reparsed at runtime.

At entry preparation, lower the declaration to a mandatory self-replacement on
the containing `zone.change` event. Applying it creates a typed nested
`counter.place` event. Zone-destination replacements may retarget that child,
then the canonical counter-placement transaction performs affected-controller
ordering, suspension, commit, projection, and replay. Resolution stores a
strict `resolving_entry` continuation and resumes the same stack item without
reapplying already completed effects.

The engine remains the high-level transaction facade. It does not own a second
counter write or a second replacement implementation.

## Alternatives

- Initialize counters after entry. Rejected because it bypasses replacement
  ordering and cannot roll back or suspend atomically.
- Encode the rule as synthetic Oracle text. Rejected because type-line and
  Oracle-text provenance are different authorities.
- Add Planeswalker- and Battle-specific branches to counter mutation. Rejected
  because the shared typed counter event already owns replacement and commit.

## Consequences

- Ordinary card entry, simultaneous APNAP preparation, competing quantity
  replacements, seat-scoped choices, and exact replay share one event tree.
- Printed values reject missing, boolean, fractional, negative, and malformed
  data before mutation.
- Siege protector selection remains a separate entry choice. Unsupported
  Battle subtypes fail closed.
- Replacement-free Planeswalker and Battle tokens use the canonical counter
  write plan. Token creation with an applicable counter replacement remains
  fail closed until token creation can suspend and resume atomically.
- Loyalty costs, counter removal or movement, Saga lore actions, and broader
  copy, face-down, and continuous-characteristic interactions remain outside
  this decision.
- Game Record v3 and public protocol schemas remain unchanged; compiler,
  capability, and continuation fingerprints advance.

## Removal condition

Replace this boundary only with a typed entry transaction that preserves
card-form provenance, self-replacement ordering, nested counter events,
identity-pinned suspension, authoritative mutation ownership, privacy, and
exact replay.
