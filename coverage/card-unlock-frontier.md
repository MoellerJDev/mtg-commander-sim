---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "e64fbe56c37d35c4747d4b848a9371d4016480484bc928658835bf3d92c80af7"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1865,"partial":13363,"unresolved":16395}`
- CardProgram states: `{"residual":29758,"trusted":1865}`
- Hard construction failures: 0
- Frontier fingerprint: `e64fbe56c37d35c4747d4b848a9371d4016480484bc928658835bf3d92c80af7`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,643 | 7,764 | 3,312 | 9,643 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 185 | 346 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 161 | 531 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 136 | 385 | partial | high |
| `effect_clause:deal-damage` | 1,048 | 1,016 | 133 | 290 | missing_lowering | high |
| `effect_clause:return` | 754 | 727 | 112 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 106 | 311 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 94 | 254 | missing_lowering | high |
| `activated_effect:deal-damage` | 525 | 495 | 92 | 180 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 759 | 734 | 81 | 156 | missing_contract | high |
| `effect_clause:exile` | 1,062 | 1,012 | 80 | 465 | missing_lowering | high |
| `activated_effect:return` | 451 | 450 | 80 | 168 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 75 | 166 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 70 | 147 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 70 | 129 | missing_lowering | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 64 | 86 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 62 | 184 | missing_lowering | high |
| `activated_effect:create-token` | 487 | 476 | 59 | 204 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `activated_effect:search` | 236 | 233 | 52 | 69 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `activated_effect:unparsed-target-creature-gains` | 98 | 94 | 48 | 81 | missing_lowering | high |
| `effect_clause:destroy-mass` | 201 | 190 | 45 | 88 | missing_lowering | high |
| `effect_clause:create-token` | 729 | 712 | 43 | 159 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,722 | 10,374 | 10,374 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,711 | 10,520 | 10,520 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,685 | 10,559 | 10,559 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,671 | 10,300 | 10,300 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,661 | 10,279 | 10,279 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,657 | 10,231 | 10,231 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,644 | 10,339 | 10,339 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:return` | 3,641 | 10,243 | 10,243 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-111-tokens` | 3,639 | 10,485 | 10,485 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:deal-damage` | 3,635 | 10,318 | 10,318 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:deal-damage` | 3,628 | 10,464 | 10,464 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:destroy-target` | 3,622 | 10,243 | 10,243 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:deal-damage` | 3,622 | 10,169 | 10,221 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:tap-state` | 3,621 | 10,155 | 10,194 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:return` | 3,620 | 10,157 | 10,199 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:unparsed-regenerate-this-creature` | 3,618 | 10,118 | 10,134 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:return` | 3,615 | 10,282 | 10,282 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:exile` | 3,610 | 10,454 | 10,454 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:return` | 3,609 | 10,428 | 10,428 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:create-token` | 3,605 | 10,193 | 10,270 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
