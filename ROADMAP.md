# Roadmap

Version 0.5.0 adds the fixed-seat Codex arena, persistent thread identity,
meaningful-action/yield auditing, exact profile validation, payable-action
filtering, and native command-replay fixtures. The phases below describe
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

No roadmap phase should expand pilot permissions. New rules and UI features remain behind the existing capability and projection boundaries.
