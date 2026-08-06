---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "08a38c9fcb354580f9b06cb44b22540c0e8f7863d41be173cf0f21f052c8bbe0"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1656,"partial":13550,"unresolved":16417}`
- CardProgram states: `{"residual":29967,"trusted":1656}`
- Hard construction failures: 0
- Frontier fingerprint: `08a38c9fcb354580f9b06cb44b22540c0e8f7863d41be173cf0f21f052c8bbe0`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,679 | 7,794 | 3,227 | 9,679 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 174 | 346 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 145 | 531 | partial | high |
| `effect_clause:deal-damage` | 1,048 | 1,016 | 130 | 290 | missing_lowering | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 128 | 385 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 106 | 311 | partial | high |
| `activated_effect:deal-damage` | 525 | 495 | 90 | 180 | missing_lowering | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `activated_effect:return` | 451 | 450 | 79 | 168 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 759 | 734 | 76 | 156 | missing_contract | high |
| `effect_clause:exile` | 1,062 | 1,012 | 75 | 465 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 74 | 166 | missing_lowering | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 64 | 129 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 64 | 86 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 61 | 184 | missing_lowering | high |
| `activated_effect:create-token` | 487 | 476 | 59 | 204 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `activated_effect:unparsed-target-creature-gains` | 98 | 94 | 47 | 81 | missing_lowering | high |
| `keyword_dependency:cycling` | 297 | 297 | 45 | 297 | missing_contract | medium |
| `effect_clause:create-token` | 729 | 712 | 43 | 159 | missing_lowering | high |
| `effect_clause:destroy-mass` | 201 | 190 | 42 | 88 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,617 | 10,410 | 10,410 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,597 | 10,556 | 10,556 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,575 | 10,595 | 10,595 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,574 | 10,336 | 10,336 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,561 | 10,315 | 10,315 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,555 | 10,267 | 10,267 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,551 | 10,375 | 10,375 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:return` | 3,540 | 10,279 | 10,279 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-509-declare-blockers-step` | 3,539 | 10,354 | 10,354 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-111-tokens` | 3,537 | 10,521 | 10,521 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:deal-damage` | 3,523 | 10,500 | 10,500 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:deal-damage` | 3,523 | 10,205 | 10,257 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:tap-state` | 3,523 | 10,191 | 10,230 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:destroy-target` | 3,520 | 10,279 | 10,279 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:return` | 3,520 | 10,193 | 10,235 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:return` | 3,518 | 10,318 | 10,318 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:unparsed-regenerate-this-creature` | 3,516 | 10,154 | 10,170 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:exile` | 3,508 | 10,490 | 10,490 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:menace` | 3,508 | 10,396 | 10,396 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:create-token` | 3,508 | 10,229 | 10,306 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
