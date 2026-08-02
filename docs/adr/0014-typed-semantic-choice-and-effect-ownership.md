---
title: "ADR 0014: typed semantic choice and effect ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-02"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0014"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0014: typed semantic choice and effect ownership

## Context

`CommanderEngine` previously paired two large semantic-choice switches and a
large immediate-effect switch. The same operation identity, continuation
fields, validation, and mutation path were repeated across those switches.
Several universal operations also encoded one card's name even when their
behavior was a reusable zone, token, copy, continuous-effect, or emblem rule.

## Decision

Semantic choices are registered once through versioned handlers that own both
preparation and completion. Handlers receive immutable, visibility-scoped
queries and return typed intents; they never receive `CommanderEngine` or
mutate `GameState`. A narrow coordinator validates and resumes the existing
Game Record v3 continuation shape through one compatibility decoder.

Immediate effects use one frozen registry of typed family handlers. The
engine's `apply_effect` method is a compatibility coordinator that validates a
registered operation, lowers it, and executes its typed plan. Zone and
attachment, resource, continuous, delayed, stack, token, and copy behavior are
owned by focused runtime families.

The architecture operation baseline replaces eleven removed card-shaped names
with eleven reviewed generic operations. The operation count does not grow.
These replacements express modified token copies, conditional token creation,
artifact-zone exchange, typed emblem creation, ability markers, matched
temporary modifiers, selected destruction rewards, and linked Aura
reanimation without printed-name dispatch.

Activated mana ability completion is owned by a narrow mana transaction
module. Pure tap-for-mana activations may expose a same-window rollback for the
manual-mana UI; spending, passing, phase changes, side effects, restrictions,
or other costs invalidate it. The rollback delegates pool spending and tap
state to canonical owners and remains replayed through the ordinary command
journal.

## Alternatives

- Move the existing switches intact to another module. Rejected because it
  preserves duplicated dispatch and creates another monolith.
- Give choice handlers a broad engine protocol. Rejected because it would
  obscure mutation ownership and hidden-information boundaries.
- Retain card-named operations behind a registry. Rejected because registry
  indirection alone does not make card-specific kernel behavior generic.
- Allow arbitrary callbacks or dictionary field paths. Rejected because they
  are not closed, versioned, or auditable rules vocabulary.

## Consequences

- Each choice and immediate effect operation has one registered owner.
- New records use typed/versioned continuations while historical Game Record
  v3 continuations retain their pinned compatibility behavior.
- Engine line count and oversized switch count decrease materially without
  hiding the same implementation in a replacement god module.
- Generic operation names are replay-visible schema and require explicit
  architecture review before the baseline can change again.
- The remaining compatibility operations stay inventoried and must shrink as
  their rules families receive typed owners.

## Removal condition

The Game Record v3 decoder and bounded compatibility path may be removed only
in a future record version with an explicit migration policy. Remaining
card-shaped operations leave the compatibility inventory when their reusable
rules families and CardProgram lowering are certified.
