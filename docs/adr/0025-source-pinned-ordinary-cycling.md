---
title: "ADR 0025: source-pinned ordinary Cycling ownership"
status: "ADR"
authoritative_source: "this decision record and typed ordinary Cycling implementation"
verified: "2026-08-06"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0025"
decision_status: "accepted"
date: "2026-08-06"
---

# ADR 0025: source-pinned ordinary Cycling ownership

## Context

Cycling is written as keyword text but behaves as an activated ability whose
source is private in hand, whose physical source is discarded as a cost, and
whose draw happens later when the stack object resolves. Reinterpreting the
Oracle sentence during action generation or resolution would create a second
rules authority and could advertise a different cost from the command that is
eventually accepted.

The complete Cycling family also includes variable, hybrid, Phyrexian, snow,
and nonmana costs, typecycling, cost changes, prohibitions, and triggered
abilities. Those variants do not share one closed cost or effect grammar and
must not inherit trust from the common fixed-mana form.

## Decision

The compiler lowers a closed printed ordinary-Cycling line once into an
immutable, versioned descriptor. The descriptor records the exact fixed
ordinary mana cost, source-discard cost, hand-only activation zone, source
span, and one canonical draw result. CardProgram capability closure pins that
descriptor to the current printed face.

The ordinary activation proposal and payment owners advertise and revalidate
the same descriptor. They pay mana, move the same physical source through the
canonical semantic zone-change path, and place an ordinary nonmana ability on
the stack. Resolution uses the existing iterative replacement-aware draw
coordinator. Runtime code does not parse the Cycling Oracle sentence.

The descriptor remains discoverable as a characteristic of its object after
zone changes, but activation is permitted only from its owner's hand. Broader
effects that inspect activated abilities in arbitrary zones remain an ambient
closure blocker until they consume a shared typed query.

## Alternatives

- Continue using the general runtime activated-ability text parser. Rejected
  because live text interpretation would compete with CardProgram provenance
  and could drift between offer, payment, and replay.
- Treat every Cycling or typecycling spelling as one compiler template.
  Rejected because their costs, effects, triggers, and interaction surfaces
  differ materially.
- Resolve the draw immediately during activation. Rejected because Cycling is
  a nonmana activated ability that uses the stack and may be responded to.

## Consequences

- Fixed ordinary-mana Cycling becomes a reusable, source-pinned hand-activation
  capability with exact replay and seat-scoped privacy.
- The discard happens as a cost before stack placement, while the draw remains
  independently replaceable at resolution.
- The activation is exposed only when its complete mandatory cost is currently
  payable.
- Unsupported costs, typecycling, Cycling triggers, modifiers, prohibitions,
  granted abilities, and copied abilities remain precise residuals.

## Removal condition

The narrow runtime compatibility adapter may disappear when all activated
ability discovery consumes CardProgram descriptors directly. Residual
boundaries may be removed only as their separate typed cost, trigger,
typecycling, copy, granted-ability, and ambient-query dependencies become
capability-closed.
