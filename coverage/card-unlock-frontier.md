---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "411fba39984c31b6d4e611a5467cc594d5eb685e90952e90b5cd88a16c3f8e86"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1268,"partial":13831,"unresolved":16524}`
- CardProgram states: `{"residual":30355,"trusted":1268}`
- Hard construction failures: 0
- Frontier fingerprint: `411fba39984c31b6d4e611a5467cc594d5eb685e90952e90b5cd88a16c3f8e86`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 2,883 | 9,684 | missing_lowering | very_high |
| `effect_clause:deal-damage` | 1,122 | 1,089 | 154 | 364 | missing_lowering | high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 152 | 346 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 124 | 385 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 121 | 531 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `activated_effect:deal-damage` | 592 | 558 | 108 | 235 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 104 | 311 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 849 | 821 | 79 | 167 | missing_contract | high |
| `activated_effect:return` | 451 | 450 | 78 | 168 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 73 | 166 | missing_lowering | high |
| `mechanic_dependency:cr-121-drawing-a-card` | 205 | 203 | 71 | 194 | partial | high |
| `effect_clause:exile` | 1,062 | 1,012 | 69 | 465 | missing_lowering | high |
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
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:trample` | 3,296 | 10,946 | 10,946 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, keyword_dependency:trample` | 3,285 | 10,976 | 10,976 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, keyword_dependency:trample` | 3,259 | 10,955 | 10,955 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, keyword_dependency:trample` | 3,248 | 11,122 | 11,122 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-111-tokens, keyword_dependency:trample` | 3,245 | 10,902 | 10,902 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,244 | 10,415 | 10,415 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:trample, keyword_dependency:first-strike` | 3,222 | 10,930 | 10,930 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-611-continuous-effects` | 3,216 | 10,394 | 10,394 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:deal-damage, keyword_dependency:trample` | 3,215 | 10,826 | 10,890 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-509-declare-blockers-step` | 3,215 | 10,433 | 10,433 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:return, keyword_dependency:trample` | 3,214 | 10,845 | 10,845 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,202 | 10,561 | 10,561 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-614-replacement-effects` | 3,201 | 10,600 | 10,600 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,201 | 10,341 | 10,341 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,199 | 10,380 | 10,380 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:tap-state, keyword_dependency:trample` | 3,195 | 10,757 | 10,796 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:destroy-target, keyword_dependency:trample` | 3,194 | 10,845 | 10,845 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:return, keyword_dependency:trample` | 3,193 | 10,759 | 10,801 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:trample, keyword_dependency:deathtouch` | 3,190 | 10,892 | 10,892 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,187 | 10,283 | 10,283 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
