---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "4fea4a3ac7d1c3dc55763681c086441d056a5d87df837dcd31e858bcc75016c9"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1351,"partial":13850,"unresolved":16422}`
- CardProgram states: `{"residual":30272,"trusted":1351}`
- Hard construction failures: 0
- Frontier fingerprint: `4fea4a3ac7d1c3dc55763681c086441d056a5d87df837dcd31e858bcc75016c9`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 2,889 | 9,684 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 152 | 346 | partial | high |
| `effect_clause:deal-damage` | 1,048 | 1,016 | 130 | 290 | missing_lowering | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 124 | 385 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 121 | 531 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 104 | 311 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `activated_effect:deal-damage` | 525 | 495 | 85 | 180 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 777 | 751 | 79 | 167 | missing_contract | high |
| `activated_effect:return` | 451 | 450 | 78 | 168 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 74 | 166 | missing_lowering | high |
| `effect_clause:exile` | 1,062 | 1,012 | 72 | 465 | missing_lowering | high |
| `mechanic_dependency:cr-121-drawing-a-card` | 205 | 203 | 71 | 194 | partial | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `keyword_dependency:trample` | 974 | 968 | 62 | 907 | partial | medium |
| `activated_effect:create-token` | 487 | 476 | 57 | 204 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 56 | 86 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `keyword_dependency:first-strike` | 363 | 360 | 53 | 327 | partial | medium |
| `activated_effect:put-counter` | 408 | 397 | 53 | 184 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 53 | 129 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `keyword_dependency:deathtouch` | 336 | 333 | 45 | 301 | partial | medium |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:trample` | 3,302 | 10,946 | 10,946 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, keyword_dependency:trample` | 3,291 | 10,976 | 10,976 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, keyword_dependency:trample` | 3,254 | 11,122 | 11,122 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-111-tokens, keyword_dependency:trample` | 3,251 | 10,902 | 10,902 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,250 | 10,415 | 10,415 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, keyword_dependency:trample` | 3,241 | 10,881 | 10,881 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:trample, keyword_dependency:first-strike` | 3,228 | 10,930 | 10,930 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:return, keyword_dependency:trample` | 3,220 | 10,845 | 10,845 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,208 | 10,561 | 10,561 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-614-replacement-effects` | 3,207 | 10,600 | 10,600 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,207 | 10,341 | 10,341 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,205 | 10,380 | 10,380 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:tap-state, keyword_dependency:trample` | 3,202 | 10,757 | 10,796 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:destroy-target, keyword_dependency:trample` | 3,200 | 10,845 | 10,845 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:return, keyword_dependency:trample` | 3,199 | 10,759 | 10,801 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,198 | 10,320 | 10,320 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:deal-damage, keyword_dependency:trample` | 3,197 | 10,771 | 10,823 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-509-declare-blockers-step` | 3,197 | 10,359 | 10,359 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:trample, keyword_dependency:deathtouch` | 3,196 | 10,892 | 10,892 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,194 | 10,283 | 10,283 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
