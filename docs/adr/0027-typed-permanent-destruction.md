---
title: "ADR 0027: typed permanent-destruction transaction"
status: "ADR"
authoritative_source: "this decision record and typed permanent-destruction implementation"
verified: "2026-08-06"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0027"
decision_status: "accepted"
date: "2026-08-06"
---

# ADR 0027: typed permanent-destruction transaction

## Context

Destruction was represented by several effect paths and state-based-action
branches. Those paths could disagree about Indestructible, shield counters,
simultaneous zone changes, rollback, or public event output. Direct targeted
destruction also lacked a closed compiler family shared by spells, triggers,
and activated abilities.

The broader family includes regeneration, “can't be regenerated,” optional or
modal instructions, qualified or aggregate selection, continuous ability
changes, and replacement interactions that are not closed by this decision.

## Decision

All represented destruction lowers to an immutable, identity-pinned request
and a preflighted destruction plan. One typed owner determines whether each
object is destroyed, prohibited by Indestructible, or has one shield counter
removed instead. It commits counter changes through the counter owner and zone
changes through the canonical zone-change owner. State-based destruction uses
the same owner while correctly ignoring shield counters.

The compiler lowers exactly one mandatory whole-clause instruction to destroy
exactly one target artifact, creature, enchantment, land, permanent, artifact
or enchantment, or creature or planeswalker. Spell, trigger, and activated
contexts use the same source-spanned CardProgram node and capability. Runtime
code never reparses Oracle text or branches on a card identity.

State-based-action evaluation may propose destruction before prohibitions are
applied. A narrow execution coordinator combines that plan with other
simultaneous state-based zone changes so an Indestructible permanent can still
move for an independently applicable state-based action.

## Alternatives

- Keep destruction inside generic effect dispatch and state-based-action code.
  Rejected because duplicated legality and mutation ownership cannot provide
  atomic rollback or one replay contract.
- Treat Indestructible or shield counters as target restrictions. Rejected
  because they do not make the target illegal and must be evaluated when the
  destruction event resolves.
- Promote the aggregate destruction mechanic. Rejected because the unsupported
  variants and ambient interactions remain materially reachable.

## Consequences

- Advertised targeted-destruction actions and accepted commands share the same
  typed target schema and resolution-time revalidation.
- Caller-owned dictionaries cannot mutate the replay-pinned request or plan.
- Canonical physical-object ordering makes equivalent batches serialize and
  replay identically, including four-player simultaneous results.
- Indestructible prevents destruction without consuming a shield counter;
  state-based lethal or deathtouch destruction does not consume shields.
- Regeneration, prohibition wording, optional, modal, aggregate, qualified,
  compound, unsupported continuous/copy interactions, and broader replacement
  behavior remain explicit residuals and fail trust closed.

## Removal condition

The direct-target grammar may widen only through another typed clause family
that preserves exact source spans, strict target closure, canonical mutation
owners, atomic preflight, and replay identity. The aggregate mechanic remains
untrusted until its documented variants are independently capability-closed.
