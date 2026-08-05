---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "bacd71ee4abf89319e549fc13969ee30372be7ddb964457f2f0e0a4720e55dc2"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1216,"partial":13883,"unresolved":16524}`
- CardProgram states: `{"residual":30407,"trusted":1216}`
- Hard construction failures: 0
- Frontier fingerprint: `bacd71ee4abf89319e549fc13969ee30372be7ddb964457f2f0e0a4720e55dc2`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 2,800 | 9,684 | missing_lowering | very_high |
| `effect_clause:deal-damage` | 1,122 | 1,089 | 154 | 364 | missing_lowering | high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 150 | 346 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 124 | 385 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 119 | 531 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `activated_effect:deal-damage` | 592 | 558 | 106 | 235 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 102 | 311 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `activated_effect:return` | 451 | 450 | 78 | 168 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 849 | 821 | 75 | 167 | missing_contract | high |
| `activated_effect:tap-state` | 322 | 311 | 71 | 166 | missing_lowering | high |
| `effect_clause:exile` | 1,062 | 1,012 | 69 | 465 | missing_lowering | high |
| `mechanic_dependency:cr-121-drawing-a-card` | 205 | 203 | 68 | 194 | partial | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `keyword_dependency:trample` | 974 | 968 | 60 | 907 | partial | medium |
| `activated_effect:create-token` | 487 | 476 | 57 | 204 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 56 | 86 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `keyword_dependency:flash` | 592 | 591 | 52 | 592 | missing_contract | medium |
| `keyword_dependency:first-strike` | 363 | 360 | 52 | 327 | partial | medium |
| `activated_effect:put-counter` | 408 | 397 | 52 | 184 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 51 | 129 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:trample` | 3,209 | 10,946 | 10,946 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, keyword_dependency:trample` | 3,200 | 10,976 | 10,976 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, keyword_dependency:trample` | 3,174 | 10,955 | 10,955 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, keyword_dependency:trample` | 3,161 | 11,122 | 11,122 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,159 | 10,415 | 10,415 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-111-tokens, keyword_dependency:trample` | 3,158 | 10,902 | 10,902 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:trample, keyword_dependency:flash` | 3,157 | 11,183 | 11,183 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:trample, keyword_dependency:first-strike` | 3,136 | 10,930 | 10,930 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-509-declare-blockers-step` | 3,132 | 10,433 | 10,433 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:deal-damage, mechanic_dependency:cr-611-continuous-effects` | 3,131 | 10,394 | 10,394 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:return, keyword_dependency:trample` | 3,129 | 10,845 | 10,845 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:deal-damage, keyword_dependency:trample` | 3,128 | 10,826 | 10,890 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-614-replacement-effects` | 3,116 | 10,600 | 10,600 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,115 | 10,561 | 10,561 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, keyword_dependency:flash` | 3,114 | 10,622 | 10,622 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,114 | 10,380 | 10,380 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,114 | 10,341 | 10,341 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, keyword_dependency:flash` | 3,113 | 10,661 | 10,661 |
| `continuous_layer:continuous-effect-layers-and-dependencies, effect_clause:destroy-target, keyword_dependency:trample` | 3,109 | 10,845 | 10,845 |
| `continuous_layer:continuous-effect-layers-and-dependencies, activated_effect:return, keyword_dependency:trample` | 3,108 | 10,759 | 10,801 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
