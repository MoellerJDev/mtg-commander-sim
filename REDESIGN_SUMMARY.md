---
title: "Redesign summary"
status: "historical"
authoritative_source: "early architecture redesign checkpoint"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "maintainers researching project history"
maintenance: "hand-maintained"
---

# Redesign summary

This is a historical design note for the transition away from the duel
prototype. In the current product direction, human/browser and deterministic
scripted clients are primary; pilot and arbiter adapters are optional and no
AI system may supply authoritative live rules. Unsupported material behavior
fails closed.

## The root problem

The duel prototype made ChatGPT perform three expensive jobs at once:

1. choose a strategy
2. interpret arbitrary card text and rules
3. mutate and narrate game state

That made every priority window verbose, allowed hidden information to leak across seats, and forced manual repair of extra turns, delayed triggers, state-based actions, and opponent choices.

## New operating model

The redesign uses five independent responsibilities:

- **CommanderEngine**: authoritative mechanics and state
- **Pilot A/B/C/D**: strategy for one seat only
- **Arbiter**: rules resolution for uncompiled card semantics
- **StateProjector**: least-privilege observations
- **GameService/protocol client**: transport, capability validation, and synchronization

This is the same structure a native client would use. Replacing an LLM callback with a GUI does not grant new permissions or require direct state access.

## Player input

A pilot receives one decision capability and returns one compact action. It does not submit effects or a rewritten state.

Examples:

```json
{"a":"keep"}
{"a":"p","y":"until_my_turn"}
{"a":"l","card":"A37"}
{"a":"c","card":"A12","targets":["S4"],"auto_pay":true}
{"a":"atk","attackers":{"A21":"B","A34":"D"}}
```

The server validates timing, authenticated principal, object, advertised ability, cast zone, objective cost, target scope where implemented, and capability. Rejected actions roll back. A pilot never supplies arbitrary effects and, in strict mode, cannot understate a printed cost or invent a cast-from-graveyard permission.

## Four-player changes

- four seats are first-class, not two duel objects duplicated
- priority rotates through all players still in the game
- each attacker chooses a defending player/object
- defending players block in the required order
- players leaving are removed without ending the game prematurely
- extra turns are scheduled and resume normal turn order correctly
- multiplayer-only land conditions use the live opponent count

## Mulligan correction

The exact workflow is now:

1. A declares in starting-player order.
2. B, C, and D declare in turn order.
3. All players who chose to mulligan shuffle and redraw seven after the final declaration.
4. The first multiplayer mulligan has no bottom penalty.
5. A later mulligan redraws seven and privately bottoms the counted number.
6. A player who keeps cannot mulligan again.

The optional LLM guard treats a functional second seven as a keep unless the pilot provides a concrete deck-specific reason to accept a six-card hand. It prevents the earlier Zimone behavior of repeatedly mulliganing into a practical game loss while preserving an explicit override for truly nonfunctional hands.

## Token reduction

- full state only at bootstrap/resync
- hash-checked JSON patches afterward
- card definitions once per seat
- stable short refs
- filtered events
- exact decision-only capabilities
- automatic empty-priority passes
- longer yields
- automatic deterministic transitions
- bounded same-capability correction packets after rejected model actions
- cached card semantics
- local rules lookup on demand

Bundled benchmark:

| Packet | Estimated tokens |
|---|---:|
| A-seat four-player bootstrap | 1,549 |
| unchanged repeated live decision | 269 |
| A mulligan-declaration delta | 108 |

The larger improvement is call count: known-empty priority windows no longer invoke a model at all.

## Previously identified engine failures now covered

- extra-turn queue
- upkeep/end-step delayed triggers
- core state-based actions
- legend-rule choices
- player elimination
- first-class stack countering
- opponent-owned AP/NAP choices
- multiple-defender combat
- top-library knowledge and reorder
- conservative conditional mana handling that fails closed when a spending condition is not compiled
- hand-zone Channel discovery and server-paid discard/mana costs
- server-derived activation costs and validated sacrifice/discard selections
- denial of pilot-supplied underpayments and unauthorized cast zones
- fail-closed phase advancement
- live opponent-count lands
- seat-private projections
- arbiter-only effect operations
- client patch integrity and resync

## Honest boundary

Full Magic is not complete. Continuous-effect layers, replacement/prevention ordering, every alternate cost, and all unusual special actions remain incremental work. Unknown card semantics become scoped arbiter tasks instead of guessed state changes. This makes the current project usable for careful simulations while giving future work a stable place to land.
