---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "37e88bc14d4049ff80bf997d966fc76a7f1db30fc4272020589b3fa1702c1f7b"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":2324,"partial":13263,"unresolved":16036}`
- CardProgram states: `{"residual":29299,"trusted":2324}`
- Hard construction failures: 0
- Frontier fingerprint: `37e88bc14d4049ff80bf997d966fc76a7f1db30fc4272020589b3fa1702c1f7b`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,578 | 7,720 | 3,344 | 9,578 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 567 | 520 | 187 | 346 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 166 | 531 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 140 | 385 | partial | high |
| `effect_clause:deal-damage` | 1,007 | 976 | 115 | 253 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 325 | 320 | 112 | 325 | partial | high |
| `effect_clause:return` | 740 | 713 | 111 | 250 | missing_lowering | high |
| `effect_clause:destroy-target` | 588 | 555 | 96 | 253 | missing_lowering | high |
| `effect_clause:exile` | 1,038 | 989 | 91 | 451 | missing_lowering | high |
| `activated_effect:deal-damage` | 514 | 485 | 86 | 169 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 297 | 281 | 86 | 162 | missing_contract | high |
| `activated_effect:return` | 450 | 449 | 80 | 167 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 75 | 164 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 71 | 129 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 69 | 144 | missing_lowering | high |
| `effect_clause:unparsed-target-creature-gets` | 216 | 213 | 67 | 140 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 131 | 126 | 64 | 86 | missing_lowering | high |
| `effect_clause:look-reveal` | 574 | 569 | 60 | 113 | missing_lowering | high |
| `activated_effect:create-token` | 475 | 464 | 54 | 194 | missing_lowering | high |
| `activated_effect:unparsed-target-creature-gains` | 98 | 94 | 50 | 81 | missing_lowering | high |
| `activated_effect:put-counter` | 376 | 364 | 44 | 128 | missing_lowering | high |
| `effect_clause:create-token` | 723 | 706 | 43 | 158 | missing_lowering | high |
| `effect_clause:draw` | 599 | 591 | 43 | 128 | missing_lowering | high |
| `effect_clause:sacrifice` | 387 | 383 | 41 | 131 | missing_lowering | high |
| `activated_effect:destroy-target` | 151 | 150 | 41 | 60 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,759 | 10,309 | 10,309 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,750 | 10,455 | 10,455 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,725 | 10,494 | 10,494 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,712 | 10,249 | 10,249 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,699 | 10,173 | 10,173 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,685 | 10,288 | 10,288 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-111-tokens` | 3,682 | 10,434 | 10,434 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,677 | 10,177 | 10,177 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:return` | 3,674 | 10,174 | 10,174 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:destroy-target` | 3,658 | 10,177 | 10,177 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:tap-state` | 3,655 | 10,088 | 10,126 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:exile` | 3,654 | 10,375 | 10,375 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:return` | 3,654 | 10,091 | 10,133 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:unparsed-regenerate-this-creature` | 3,653 | 10,053 | 10,069 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:deal-damage` | 3,652 | 10,216 | 10,216 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:deal-damage` | 3,650 | 10,093 | 10,142 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:return` | 3,649 | 10,213 | 10,213 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:deal-damage` | 3,647 | 10,362 | 10,362 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:return` | 3,645 | 10,359 | 10,359 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:create-token` | 3,634 | 10,118 | 10,191 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
