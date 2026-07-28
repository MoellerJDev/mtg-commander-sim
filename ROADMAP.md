# Roadmap

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
- deterministic loop/shortcut representation

## Phase 4 — multi-agent batch runner

- isolated seat contexts with compact strategic memory
- arbiter model tier separate from pilots
- model timeout/retry policy
- deterministic seeds and replay IDs
- metrics: calls, tokens, invalid actions, arbiter misses, win rate, turn of elimination, interaction exchanges, mulligan outcomes
- parallel game workers over immutable deck definitions and local card data

## Phase 5 — native/web client

- authenticated seat assignment
- HTTP command endpoint and WebSocket projection stream
- `ProjectedClientView` reducer in TypeScript
- card image/zone/combat UI
- reconnect/full-resync path
- spectator and postgame analyst views

No roadmap phase should expand pilot permissions. New rules and UI features remain behind the existing capability and projection boundaries.
