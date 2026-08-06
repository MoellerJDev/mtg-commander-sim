---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "c72b8e0c212d68963515fc665db0f8ef12a6523b6696c412fc961d4bf543f428"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1567,"partial":13636,"unresolved":16420}`
- CardProgram states: `{"residual":30056,"trusted":1567}`
- Hard construction failures: 0
- Frontier fingerprint: `c72b8e0c212d68963515fc665db0f8ef12a6523b6696c412fc961d4bf543f428`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 3,146 | 9,684 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 165 | 346 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 144 | 531 | partial | high |
| `effect_clause:deal-damage` | 1,048 | 1,016 | 130 | 290 | missing_lowering | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 127 | 385 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 106 | 311 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `activated_effect:deal-damage` | 525 | 495 | 89 | 180 | missing_lowering | high |
| `activated_effect:return` | 451 | 450 | 78 | 168 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 759 | 734 | 76 | 156 | missing_contract | high |
| `effect_clause:exile` | 1,062 | 1,012 | 74 | 465 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 74 | 166 | missing_lowering | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 60 | 86 | missing_lowering | high |
| `activated_effect:create-token` | 487 | 476 | 58 | 204 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 58 | 129 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 56 | 184 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `keyword_dependency:deathtouch` | 336 | 333 | 45 | 306 | partial | medium |
| `activated_effect:unparsed-target-creature-gains` | 98 | 94 | 45 | 81 | missing_lowering | high |
| `effect_clause:create-token` | 729 | 712 | 43 | 159 | missing_lowering | high |
| `keyword_dependency:defender` | 304 | 304 | 42 | 301 | partial | medium |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,524 | 10,415 | 10,415 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,504 | 10,561 | 10,561 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,492 | 10,600 | 10,600 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,482 | 10,341 | 10,341 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,469 | 10,380 | 10,380 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,469 | 10,320 | 10,320 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,462 | 10,272 | 10,272 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-509-declare-blockers-step` | 3,457 | 10,359 | 10,359 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-111-tokens` | 3,455 | 10,526 | 10,526 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:return` | 3,448 | 10,284 | 10,284 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:deal-damage` | 3,441 | 10,505 | 10,505 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:deathtouch` | 3,437 | 10,356 | 10,356 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:return` | 3,436 | 10,323 | 10,323 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:defender` | 3,433 | 10,331 | 10,331 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:tap-state` | 3,431 | 10,196 | 10,235 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:deal-damage` | 3,430 | 10,210 | 10,262 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:destroy-target` | 3,428 | 10,284 | 10,284 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:return` | 3,427 | 10,198 | 10,240 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:return` | 3,421 | 10,469 | 10,469 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, activated_effect:tap-state` | 3,420 | 10,235 | 10,274 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
