---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "fd46db73886bcae56ce02b0d28628d8e7267995d7213122a286d97d209b9444b"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1482,"partial":13719,"unresolved":16422}`
- CardProgram states: `{"residual":30141,"trusted":1482}`
- Hard construction failures: 0
- Frontier fingerprint: `fd46db73886bcae56ce02b0d28628d8e7267995d7213122a286d97d209b9444b`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 3,138 | 9,684 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 165 | 346 | partial | high |
| `effect_clause:deal-damage` | 1,048 | 1,016 | 130 | 290 | missing_lowering | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 126 | 385 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 122 | 531 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 105 | 311 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `activated_effect:deal-damage` | 525 | 495 | 86 | 180 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 777 | 751 | 79 | 167 | missing_contract | high |
| `activated_effect:return` | 451 | 450 | 78 | 168 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 74 | 166 | missing_lowering | high |
| `effect_clause:exile` | 1,062 | 1,012 | 72 | 465 | missing_lowering | high |
| `mechanic_dependency:cr-121-drawing-a-card` | 205 | 203 | 71 | 194 | partial | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 60 | 86 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 58 | 129 | missing_lowering | high |
| `activated_effect:create-token` | 487 | 476 | 57 | 204 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 56 | 184 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `keyword_dependency:deathtouch` | 336 | 333 | 45 | 306 | partial | medium |
| `activated_effect:unparsed-target-creature-gains` | 98 | 94 | 45 | 81 | missing_lowering | high |
| `effect_clause:create-token` | 729 | 712 | 43 | 159 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,515 | 10,415 | 10,415 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,474 | 10,561 | 10,561 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,473 | 10,341 | 10,341 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-614-replacement-effects` | 3,461 | 10,600 | 10,600 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,461 | 10,320 | 10,320 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,459 | 10,380 | 10,380 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,457 | 10,283 | 10,283 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-509-declare-blockers-step` | 3,448 | 10,359 | 10,359 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:return` | 3,440 | 10,284 | 10,284 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:deathtouch` | 3,429 | 10,356 | 10,356 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:return` | 3,427 | 10,323 | 10,323 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:defender` | 3,425 | 10,331 | 10,331 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-111-tokens` | 3,424 | 10,526 | 10,526 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:tap-state` | 3,423 | 10,196 | 10,235 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:destroy-target` | 3,420 | 10,284 | 10,284 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:deal-damage` | 3,419 | 10,210 | 10,262 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:return` | 3,419 | 10,198 | 10,240 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-614-replacement-effects` | 3,411 | 10,505 | 10,505 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, activated_effect:tap-state` | 3,411 | 10,235 | 10,274 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:unparsed-regenerate-this-creature` | 3,410 | 10,159 | 10,175 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
