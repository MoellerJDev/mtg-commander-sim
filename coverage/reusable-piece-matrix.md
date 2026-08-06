---
title: "Reusable rules piece matrix"
status: "generated"
authoritative_source: "coverage/reusable-piece-matrix.json.gz"
verified: "c1688e0d9e8ec04f0400ff7c2cdeab7699fda8b8fe421066989735b4f16bf9a5"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Reusable rules piece matrix

Current Oracle IR material ability and residual spans plus all registered capabilities, mechanics, handlers, components, and pinned rule references. This inventories current source relations without claiming universal runtime completion.

Counts official ruling presence by Oracle ID. Ruling prose is not yet behaviorally classified, so these counts are composition evidence rather than coverage claims.

## Snapshot

- Profile: `commander_review`
- Ontology: `reusable-pieces-v1`
- Pieces: 995
- Cards indexed: 31,623
- Material abilities classified: 59,968
- Unclassified material spans: 0
- Mapped pinned rules: 628 / 3,300
- Applicable piece pairs: 19,609
- Covered piece pairs: 68

## Ontology classes

| Class | Pieces |
|---|---:|
| `actions_permissions` — Actions, permissions, and prohibitions | 4 |
| `card_forms` — Card types and specialized forms | 3 |
| `choices_continuations` — Modes, targets, choices, and continuations | 6 |
| `combat` — Combat | 11 |
| `compiler_cardprogram` — Compiler and CardProgram pieces | 192 |
| `continuous_effects` — Static abilities and continuous effects | 16 |
| `costs_mana` — Costs and mana | 6 |
| `events_mutations` — Typed events and mutations | 58 |
| `keyword_mechanics` — Keyword actions and keyword abilities | 568 |
| `multiplayer_commander` — Multiplayer, Commander, and profile pieces | 1 |
| `object_identity` — Object identity and lifetime | 29 |
| `one_shot_effects` — One-shot semantic effects | 81 |
| `players_format` — Players, relationships, and format state | 1 |
| `proposals` — Casting and activation proposals | 2 |
| `quantities` — Quantity and value expressions | 1 |
| `references` — References | 1 |
| `replacement_prevention` — Replacement and prevention | 13 |
| `triggers` — Triggers | 2 |

## Universal systems

| System | Status | Pieces | Blocking pieces |
|---|---|---:|---:|
| `action_legality_casting_activation_costs_mana` | `inventoried` | 12 | 5 |
| `combat` | `compositional` | 11 | 0 |
| `derived_characteristics_static_layers` | `inventoried` | 16 | 5 |
| `generic_triggers_stack_placement` | `inventoried` | 2 | 2 |
| `multiplayer_player_leaving_commander` | `represented` | 2 | 0 |
| `objects_identity_zones_faces_copies` | `represented` | 32 | 0 |
| `replacement_prevention` | `inventoried` | 13 | 5 |
| `state_turn_loops_stabilization` | `inventoried` | 0 | 0 |
| `targets_modes_searches_references_choices` | `inventoried` | 8 | 6 |
| `typed_transactions_events_mutations` | `inventoried` | 139 | 53 |

## Highest current blocker leverage

| Piece | Class | Residuals | Sole blockers | Expected cards | Runtime | Assurance |
|---|---|---:|---:|---:|---|---|
| `residual.continuous_layer.continuous-effect-layers-and-dependencies` | `continuous_effects` | 9,679 | 3,283 | 3,283 | `absent` | `untested` |
| `residual.activated_effect.unparsed-clause-grammar` | `one_shot_effects` | 2,880 | 771 | 771 | `absent` | `untested` |
| `residual.effect_clause.unparsed-clause-grammar` | `one_shot_effects` | 2,943 | 483 | 483 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-611-continuous-effects` | `keyword_mechanics` | 565 | 181 | 181 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-614-replacement-effects` | `keyword_mechanics` | 531 | 145 | 145 | `absent` | `untested` |
| `residual.effect_clause.deal-damage` | `one_shot_effects` | 1,048 | 130 | 130 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-509-declare-blockers-step` | `keyword_mechanics` | 421 | 128 | 128 | `absent` | `untested` |
| `residual.effect_clause.return` | `one_shot_effects` | 754 | 108 | 108 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-111-tokens` | `keyword_mechanics` | 311 | 106 | 106 | `absent` | `untested` |
| `residual.activated_effect.deal-damage` | `one_shot_effects` | 525 | 91 | 91 | `absent` | `untested` |
| `residual.effect_clause.destroy-target` | `one_shot_effects` | 590 | 89 | 89 | `absent` | `untested` |
| `residual.activated_effect.return` | `one_shot_effects` | 451 | 79 | 79 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-115-targets` | `keyword_mechanics` | 759 | 77 | 77 | `absent` | `untested` |
| `residual.effect_clause.exile` | `one_shot_effects` | 1,062 | 76 | 76 | `absent` | `untested` |
| `residual.activated_effect.tap-state` | `one_shot_effects` | 322 | 75 | 75 | `absent` | `untested` |
| `residual.effect_clause.tap-state` | `one_shot_effects` | 387 | 67 | 67 | `absent` | `untested` |
| `residual.activated_effect.put-counter` | `one_shot_effects` | 408 | 62 | 62 | `absent` | `untested` |
| `residual.activated_effect.create-token` | `one_shot_effects` | 487 | 59 | 59 | `absent` | `untested` |
| `residual.effect_clause.look-reveal` | `one_shot_effects` | 579 | 55 | 55 | `absent` | `untested` |
| `residual.effect_clause.counter` | `one_shot_effects` | 276 | 50 | 50 | `absent` | `untested` |
| `residual.keyword_dependency.cycling` | `keyword_mechanics` | 297 | 46 | 46 | `absent` | `untested` |
| `residual.effect_clause.create-token` | `one_shot_effects` | 729 | 43 | 43 | `absent` | `untested` |
| `residual.activated_effect.search` | `one_shot_effects` | 236 | 42 | 42 | `absent` | `untested` |
| `residual.effect_clause.destroy-mass` | `one_shot_effects` | 201 | 42 | 42 | `absent` | `untested` |
| `residual.effect_clause.draw` | `one_shot_effects` | 600 | 41 | 41 | `absent` | `untested` |
| `residual.activated_effect.destroy-target` | `one_shot_effects` | 152 | 38 | 38 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-508-declare-attackers-step` | `keyword_mechanics` | 134 | 37 | 37 | `absent` | `untested` |
| `residual.effect_clause.put-counter` | `one_shot_effects` | 276 | 33 | 33 | `absent` | `untested` |
| `residual.keyword_dependency.morph` | `keyword_mechanics` | 141 | 30 | 30 | `absent` | `untested` |
| `residual.activated_effect.draw` | `one_shot_effects` | 416 | 29 | 29 | `absent` | `untested` |

## Boundary

Inventory and classification are not implementation or trust. Universal systems remain conservatively below snapshot-complete until all required rules, pieces, rulings, and interactions close.
