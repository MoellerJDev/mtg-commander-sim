---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "2401a67a1673d8d4e8571d4d8ac1461239aa5fc093689912ca4f04e1e58b7083"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":782,"partial":14585,"unresolved":16256}`
- CardProgram states: `{"residual":30841,"trusted":782}`
- Hard construction failures: 0
- Frontier fingerprint: `2401a67a1673d8d4e8571d4d8ac1461239aa5fc093689912ca4f04e1e58b7083`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 2,271 | 9,684 | missing_lowering | very_high |
| `mechanic_dependency:cr-605-mana-abilities` | 1,990 | 1,762 | 368 | 1,990 | partial | high |
| `keyword_dependency:flying` | 3,155 | 3,133 | 181 | 2,735 | partial | medium |
| `effect_clause:deal-damage` | 1,122 | 1,089 | 154 | 364 | missing_lowering | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 106 | 346 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 96 | 385 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 88 | 311 | partial | high |
| `activated_effect:deal-damage` | 592 | 558 | 87 | 235 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 849 | 821 | 72 | 167 | missing_contract | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `effect_clause:exile` | 1,062 | 1,012 | 65 | 465 | missing_lowering | high |
| `activated_effect:return` | 451 | 450 | 63 | 168 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 59 | 166 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `keyword_dependency:trample` | 974 | 968 | 47 | 696 | partial | medium |
| `activated_effect:create-token` | 487 | 476 | 45 | 204 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 44 | 86 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 42 | 184 | missing_lowering | high |
| `effect_clause:create-token` | 729 | 712 | 42 | 159 | missing_lowering | high |
| `effect_clause:destroy-mass` | 201 | 190 | 42 | 88 | missing_lowering | high |
| `effect_clause:draw` | 600 | 592 | 41 | 127 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:flying` | 3,271 | 14,409 | 14,409 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:trample` | 2,966 | 13,207 | 13,207 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, mechanic_dependency:cr-611-continuous-effects` | 2,961 | 12,799 | 12,799 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, mechanic_dependency:cr-509-declare-blockers-step` | 2,945 | 12,804 | 12,804 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:trample` | 2,934 | 12,370 | 12,370 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, effect_clause:deal-damage` | 2,926 | 12,783 | 12,783 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:deal-damage` | 2,912 | 12,038 | 12,038 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-509-declare-blockers-step` | 2,903 | 12,059 | 12,059 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, mechanic_dependency:cr-111-tokens` | 2,900 | 12,730 | 12,730 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:flash` | 2,899 | 13,011 | 13,011 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:haste` | 2,897 | 12,893 | 12,893 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-611-continuous-effects` | 2,884 | 12,020 | 12,020 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-111-tokens` | 2,882 | 11,985 | 11,985 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, effect_clause:return` | 2,881 | 12,673 | 12,673 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:first-strike` | 2,878 | 12,716 | 12,716 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, activated_effect:deal-damage` | 2,868 | 12,654 | 12,718 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:return` | 2,867 | 11,928 | 11,928 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, effect_clause:destroy-target` | 2,861 | 12,673 | 12,673 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:haste` | 2,857 | 12,041 | 12,041 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:reach` | 2,853 | 12,746 | 12,746 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
