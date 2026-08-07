---
title: "Rules kernel"
status: "current"
authoritative_source: "mtg_commander_sim engine and rules modules"
verified: "2026-08-07"
audience: "rules and engine contributors"
maintenance: "hand-maintained"
---

# Rules kernel

## Responsibility

The kernel validates and applies deterministic game transitions: priority,
turn structure, zones, costs, choices, stack resolution, combat, state-based
actions, represented continuous/replacement effects, and semantic programs.
It is authoritative for legality and never delegates rules decisions to a UI or
pilot.

## State and mutations

`GameState` owns players, cards, zones, stack, turn/combat state, pending
decisions, events, yields, and fidelity telemetry. During migration,
`CommanderEngine` remains the declared general mutation owner. Casting and
activation use read-only immutable proposal builders followed by declared
typed commit owners; `mana_activation.py`, `tap_state.py`, and
`token_creation.py`, `destruction.py`, `permanent_exile.py`, and
`return_to_hand.py` own focused transactions behind typed host protocols.
Destruction delegates shield removal to the counter owner and permanent
movement to the zone owner; direct exile and return snapshot owner, controller,
and object identity before delegating their requested moves to that same
replacement-aware zone owner.
Capability lifecycle and replay hydration have narrowly declared compatibility
ownership. All other rules helpers return values or operate through an
approved mutation boundary. Typed semantic handlers receive
an immutable rules query and emit intents; they cannot import the engine or
state model. The intent executor calls existing canonical engine methods or
the focused tap-state port.
Typed direct-target destruction, permanent-exile, and return-to-owner-hand
handlers likewise commit only through their focused transactions; the aggregate
mechanics remain untrusted where regeneration, mass selection, linked exile,
recursion, reanimation, costs, or other unsupported grammar and interactions
are materially reachable.

Continuous characteristics are a shared rules responsibility rather than a
client reconstruction. `continuous_effect_state.py` owns the authoritative
resolution-effect journal and expiration; `characteristic_evaluation.py`
combines that journal with live CardProgram static effects for both engine
legality and principal-scoped projection. Raw journal entries and physical
object identities never enter the projection.

## Inputs and outputs

- Inputs: a pinned `GameState`, semantic registry, server-issued action ID,
  capability-scoped choices, and deterministic randomness already represented
  in state/commands.
- Outputs: an accepted transition and events, or a typed rejection with the
  original state preserved.

## Dependencies and invariants

The rules domain may depend on model and rules helpers. It must not depend on
HTTP, WebSockets, server persistence, AI providers, or browser code. A rejected
command is transactional. Legal alternatives are currently payable, hidden
information is projected separately, and state stabilization precedes the next
priority decision.

## Casting, activation, and action offers

`rules/action_catalog.py` composes executable offers from the same pure casting
and activation queries used during command validation. Each offer contains a
canonical proposal fingerprint and an expiry revision. Execution accepts the
offer only while its source, cost, target, timing, and payability facts remain
equivalent, then commits through `rules/casting/commit.py` or
`rules/activation/commit.py`. Stale offers fail before mutation.

`abilities.py` generically lowers represented colon abilities, Crew, and the
supported Craft reminder grammar. CardPrograms may grant an activated ability
through a serialized descriptor; historical card-named markers are interpreted
only by the Game Record v3 compatibility adapter.

## Extension and event participation

Reusable mechanics belong in focused rules modules and typed semantic
operations. The current tap-state owner commits only the represented single
permanent and all-effective-creature operations; it preserves stun replacement
and phased-out behavior without claiming the complete replacement or layer
systems. The token owner runs represented token events through immutable
nested replacement trees before committing one timestamped batch and
dispatching enter events. `replacement_decisions.py` persists competing
affected-seat choices as ordinary Game Record v3 continuations, and represented
zone-destination changes use the same exact selection journal before mutation.
Triggers consume normalized events; replacements transform represented events
before final mutation; state-based actions run to a fixed point. Universal
counter, draw, damage, prevention, entry, and prohibition participation remains
blocked. New rules work must identify event/replacement participation and use
capability IDs from the versioned registry.

For represented CR 611 object modifications, resolution-created effects lock
the affected physical/logical object set after successful preparation. Static
effects keep a live source-bound `ObjectQuerySpec` and recompute membership
after earlier layers. Unsupported duration or operation families fail before
the journal mutates.

Combat declaration relationships commit through
`combat_relationship_state.py`. After a complete declaration, the engine
adapts public combat facts into immutable canonical attack or block transition
values. Typed transition derivation owns ordinary printed Exalted, Battle Cry,
Melee, Flanking, and positive-integer Bushido occurrences; the shared trigger
batch owns APNAP placement, and the continuous-effect journal owns their
identity-pinned layer 7c results. Transition models have no mutable state or
engine dependency. Their narrow adapters may read effective characteristics
and delegate commits to the declared combat, trigger, and continuous-effect
owners. Conditional or prose-equivalent variants, unsupported granted or
copied fragments, trigger multiplication, and broader attack/block transition
triggers remain explicit residuals.

`ObjectQuerySpec` is a strict immutable predicate shared by those live effects
and other represented rules families. Its current schema distinguishes
all-required from any-required card types and preserves colors, subtypes,
supertypes, keywords, token/tap/phasing state, public relations, visibility,
and source exclusion. Historical schema-v1 payloads round-trip without the
additive `types_any` field so Game Record v3 replay does not silently rewrite
old descriptors.

## Visibility and replay

The kernel holds authoritative information but never builds network responses.
Every accepted strategic command is recorded and must replay to the exact state
hash with the same rules, cards, and semantics fingerprints.

## Unsupported cases and evidence

Unsupported grammar or behavior fails closed through semantic/preflight or
runtime fidelity gates. The generated
[rules status](../RULES_COMPLETENESS_STATUS.md) is the authority for remaining
families. Primary evidence is the deterministic test suite, replay tests,
privacy tests, mutation/rollback evidence, and source-pinned conformance
artifacts.
