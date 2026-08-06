---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "98cc55d34cb606d578d6cc13cfa0285fe8e33404389fbdf63b91c7b08cc92905"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1793,"partial":13438,"unresolved":16392}`
- CardProgram states: `{"residual":29830,"trusted":1793}`
- Hard construction failures: 0
- Frontier fingerprint: `98cc55d34cb606d578d6cc13cfa0285fe8e33404389fbdf63b91c7b08cc92905`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,644 | 7,765 | 3,291 | 9,644 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 185 | 346 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 145 | 531 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 134 | 385 | partial | high |
| `effect_clause:deal-damage` | 1,048 | 1,016 | 130 | 290 | missing_lowering | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 106 | 311 | partial | high |
| `activated_effect:deal-damage` | 525 | 495 | 92 | 180 | missing_lowering | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `activated_effect:return` | 451 | 450 | 79 | 168 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 759 | 734 | 77 | 156 | missing_contract | high |
| `effect_clause:exile` | 1,062 | 1,012 | 76 | 465 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 75 | 166 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 69 | 129 | missing_lowering | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 64 | 86 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 62 | 184 | missing_lowering | high |
| `activated_effect:create-token` | 487 | 476 | 59 | 204 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `activated_effect:unparsed-target-creature-gains` | 98 | 94 | 48 | 81 | missing_lowering | high |
| `keyword_dependency:cycling` | 297 | 297 | 46 | 297 | missing_contract | medium |
| `effect_clause:create-token` | 729 | 712 | 43 | 159 | missing_lowering | high |
| `effect_clause:destroy-mass` | 201 | 190 | 42 | 88 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,699 | 10,375 | 10,375 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,674 | 10,521 | 10,521 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,650 | 10,301 | 10,301 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,646 | 10,560 | 10,560 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,637 | 10,280 | 10,280 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,632 | 10,232 | 10,232 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,621 | 10,340 | 10,340 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:return` | 3,616 | 10,244 | 10,244 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:deal-damage` | 3,609 | 10,319 | 10,319 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-111-tokens` | 3,602 | 10,486 | 10,486 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:deal-damage` | 3,601 | 10,170 | 10,222 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:tap-state` | 3,600 | 10,156 | 10,195 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:return` | 3,598 | 10,158 | 10,200 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:destroy-target` | 3,596 | 10,244 | 10,244 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:unparsed-regenerate-this-creature` | 3,596 | 10,119 | 10,135 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:deal-damage` | 3,588 | 10,465 | 10,465 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:return` | 3,588 | 10,283 | 10,283 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:exile` | 3,585 | 10,455 | 10,455 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:create-token` | 3,584 | 10,194 | 10,271 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:put-counter` | 3,580 | 10,174 | 10,214 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
