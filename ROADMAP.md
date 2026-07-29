# Roadmap

Version 0.6.0 adds resumable private-search semantics, typed Codex output,
ordered future choices, explicit record lifecycle/finalization, and
journal-derived provider telemetry on top of the fixed-seat arena. The phases below describe
remaining production depth; neither the scripted regression nor duplicated
four-seat pilot fixture claims a complete Oracle corpus or matchup evidence.

## Phase 1 — stabilize the multiplayer kernel

- maintain passing regression suite for turns, priority, combat, mulligans, state-based actions, and permissions
- add replay fixtures for real four-player games
- add property tests for zone membership and patch round trips
- add server-side timeouts/default actions for disconnected pilots

## Phase 2 — semantic coverage from actual games

- record arbiter misses by Oracle/ability key
- compile the highest-frequency spell, ETB, death, landfall, and activated-ability templates
- add deterministic tests using local Oracle text and rulings
- add choice templates rather than encoding choices inside arbiter effects

## Phase 3 — deeper rules modules

- continuous-effect layers and dependencies
- replacement/prevention chooser
- alternate/additional costs, cost reducers, and a server-issued cost-option compiler
- restricted/conditional mana lots with spending predicates (rather than a color-only pool)
- special actions and non-hand casting permissions
- first/double-strike damage and trample assignment
- copied/face-down/linked-object edge cases
- general deterministic loop/shortcut negotiation beyond the two validated shortcut fixtures

## Phase 4 — arena and batch hardening

- OS/process isolation for remote seat contexts beyond the implemented fixed-seat projection/tool boundary
- arbiter model tier separate from pilots
- model timeout/retry policy
- deterministic seeds and replay IDs
- batch metrics: win rate, turn of elimination, interaction exchanges, and mulligan outcomes; native call/yield/opportunity/retry metrics are implemented
- parallel game workers over immutable deck definitions and local card data

## Phase 5 — native/web client

- authenticated seat assignment
- HTTP command endpoint and WebSocket projection stream
- `ProjectedClientView` reducer in TypeScript
- card image/zone/combat UI
- reconnect/full-resync path
- spectator and postgame analyst views

## Version 0.7.0 — interaction correctness

- data-driven exact target domains across stack and public zones
- mode-aware target generation before an action is advertised
- authoritative target revalidation on submission and resolution
- counterspell and removal characterization for the two exact review lists
- exact replay and target-fidelity telemetry

## Version 0.8.0 — review MVP

- exact-list semantic preflight closure for the two review decks
- batch review aggregation with explicit sample-size and fidelity gates
- three complete four-seat Codex pilot games only after preflight passes
- auditable draft-PR evidence without publishing private Game Records

No roadmap phase should expand pilot permissions. New rules and UI features
remain behind the existing capability and projection boundaries. A duplicated
deck pod, an incomplete semantic pack, or an undersized sample can never be
promoted to matchup evidence.
