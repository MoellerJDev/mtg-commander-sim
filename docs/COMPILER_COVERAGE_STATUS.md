---
title: "Compiler coverage status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "ff5973728476d66406179a2bc6b5113bd8483aaf"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Compiler coverage status

This generated report describes only the pinned Oracle corpus and current compiler. Exact compilation is not the same as complete game-behavior proof.

## Current representation

- Compiler: `oracle-ir-v37`
- Runtime IR: OracleCardIR lowered to canonical CardProgram V2 with a derived SemanticProgram compatibility index
- CardProgram V2 present: true
- Compiler module: 1,501 physical / 1,452 logical lines

## Canonical CardProgram

- Schema version: `2`
- Schema: `schemas/card-program-v2.schema.json`
- Required card fields: 14
- Required per-ability fields: 27
- Model: `mtg_commander_sim/card_programs/model.py`
- Generated/reviewed adapter: `mtg_commander_sim/card_programs/adapters.py`
- Runtime validator: `mtg_commander_sim/card_programs/validation.py`
- Canonical reviewed registry CardPrograms: 142
- Intrinsic strict-capability-ready CardPrograms: 0
- Trust bases: `{"legacy_reviewed": 142}`

## Stages

| Stage | Current status | Evidence complete |
|---|---|---:|
| `normalization` | `interleaved` | true |
| `segmentation` | `interleaved` | true |
| `lexing` | `not_a_distinct_stage` | false |
| `parsing` | `regex_and_helper_parsers_interleaved` | true |
| `binding` | `not_a_distinct_stage` | false |
| `typing` | `partial_dataclass_ir` | true |
| `lowering` | `generated_abilities_extracted_and_aggregated_to_card_program_v2` | true |
| `capability_closure` | `fine_grained_damage_slice_with_legacy_fallback` | true |
| `residual_classification` | `implemented_interleaved` | true |
| `validation` | `card_program_v2_schema_roundtrip_source_trust_and_fingerprint_validation` | true |

## Fine-grained capability registry

- Registry schema/version: `1/39`
- Pinned rules effective date: `2026-06-19`
- Registry fingerprint: `e4c530ffa1e859fcfb2f088128ae842c3e8030491dfcb337e2506e85ab8d41d5`
- Evidence fingerprint: `e5c405e6b823876f28318e5f7ed17009a659ba924752c1ef76c005c0940ca850`
- Explicit evidence declarations: 570
- Capability records: 68
- Trusted records: 58
- Blocked records: 4
- Dependency fail-closed statuses: `{"not_applicable": 32, "not_run": 3, "passed": 33}`
- Implementation mutation statuses: `{"killed": 61, "not_run": 7}`

| Broad aggregate | Capability records | Trusted | Blocked members |
|---|---:|---:|---|
| `cr-121-drawing-a-card` | 1 | true | none |
| `cr-120-damage` | 19 | false | `damage.combat.excess`, `damage.prevention.order`, `damage.replacement.order`, `damage.trigger.noncombat` |
| `cr-725-the-monarch` | 1 | false | `variant.monarch.designate` |
| `cr-903-commander` | 1 | true | none |
| `cr-111-tokens` | 1 | false | `token.creation.additional_replacement` |
| `cr-614-replacement-effects` | 1 | false | `zone.change.destination_replacement` |
| `cr-613-continuous-effects` | 3 | true | none |
| `tap-and-untap` | 3 | false | `permanent.tap.effect`, `permanent.untap.all_creatures`, `permanent.untap.effect` |

## Pinned corpus accounting

| Scope | Oracle IDs | Exact | Partial | Unresolved | Material residuals | Complete |
|---|---:|---:|---:|---:|---:|---:|
| Full Oracle | 38,542 | 4,727 | 14,565 | 19,250 | 56,261 | false |
| Commander legal | 31,623 | 1,793 | 13,438 | 16,392 | 48,648 | false |

## Full-corpus residual kinds

| Kind | Count |
|---|---:|
| `trigger` | 15,277 |
| `spell_effect` | 11,241 |
| `static_ability` | 11,108 |
| `effect` | 7,168 |
| `dependency_contract` | 6,526 |
| `cost` | 2,015 |
| `replacement_effect` | 1,758 |
| `mana_ability` | 771 |
| `declaration_restriction` | 170 |
| `unsupported_enchant_restriction` | 148 |
| `unsupported_protection_quality` | 68 |
| `declaration_cost` | 11 |

## Semantic packs and implicit overrides

- Pack files: 15
- Program entries: 266
- Unique program keys: 254
- Duplicate keys resolved by pack order: 12
- Unique Oracle IDs represented: 142
- Card-specific operation names: 5
- Typed card-override boundary present: true
- Explicit typed overrides: 0

## Snapshot fingerprints

- Oracle SHA-256: `41d849cdc8eb8d6dffef53c26cf9bfee2d0e1c02a98c4951580439a55b0486b3`
- Rulings SHA-256: `312dd0636e821125560f332f5a5dbb7467ca4d07006097fc9cb425a4110bc098`
- Oracle updated: `2026-08-04T09:02:45.219+00:00`
- Rulings updated: `2026-08-04T09:00:38.847+00:00`

## Boundary

The current compiler is partial and interleaved. Full-corpus exactness is not claimed. Fine-grained closure spans the registered typed capabilities for represented damage, draw, continuous-effect, attachment, mana, cast-timing, and combat families; unregistered or blocked dependencies remain residual. CardProgram V2 provides canonical aggregation, validation, and replay pinning, while broader typed handlers and fully distinct compiler stages remain incremental work.
