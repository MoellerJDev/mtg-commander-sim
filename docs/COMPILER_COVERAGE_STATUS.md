---
title: "Compiler coverage status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "b5e5caa77f0420759e4aad2088c14fe73e7bb1f9"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Compiler coverage status

This generated report describes only the pinned Oracle corpus and current compiler. Exact compilation is not the same as complete game-behavior proof.

## Current representation

- Compiler: `oracle-ir-v27`
- Runtime IR: OracleCardIR lowered to canonical CardProgram V2 with a derived SemanticProgram compatibility index
- CardProgram V2 present: true
- Compiler module: 1,589 physical / 1,541 logical lines

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

- Registry schema/version: `1/25`
- Pinned rules effective date: `2026-06-19`
- Registry fingerprint: `9d879283a17ef95c1fc27e64f5048d71d7298ea8cc28af9e56eac2719fcdcfee`
- Evidence fingerprint: `3f5cc8d336a05fccb465f2bcd708515f7f5fc0789ee62cabd29062f9a9aa06e6`
- Explicit evidence declarations: 328
- Capability records: 42
- Trusted records: 32
- Blocked records: 4
- Dependency fail-closed statuses: `{"not_applicable": 18, "not_run": 3, "passed": 21}`
- Implementation mutation statuses: `{"killed": 35, "not_run": 7}`

| Broad aggregate | Capability records | Trusted | Blocked members |
|---|---:|---:|---|
| `cr-121-drawing-a-card` | 1 | true | none |
| `cr-120-damage` | 18 | false | `damage.combat.excess`, `damage.prevention.order`, `damage.replacement.order`, `damage.trigger.noncombat` |
| `cr-725-the-monarch` | 1 | false | `variant.monarch.designate` |
| `cr-903-commander` | 1 | true | none |
| `cr-111-tokens` | 1 | false | `token.creation.additional_replacement` |
| `cr-614-replacement-effects` | 1 | false | `zone.change.destination_replacement` |
| `cr-613-continuous-effects` | 3 | true | none |
| `tap-and-untap` | 3 | false | `permanent.tap.effect`, `permanent.untap.all_creatures`, `permanent.untap.effect` |

## Pinned corpus accounting

| Scope | Oracle IDs | Exact | Partial | Unresolved | Material residuals | Complete |
|---|---:|---:|---:|---:|---:|---:|
| Full Oracle | 38,485 | 3,385 | 16,082 | 19,018 | 65,898 | false |
| Commander legal | 31,623 | 725 | 14,648 | 16,250 | 57,488 | false |

## Full-corpus residual kinds

| Kind | Count |
|---|---:|
| `dependency_contract` | 17,088 |
| `trigger` | 15,230 |
| `spell_effect` | 11,318 |
| `static_ability` | 11,104 |
| `effect` | 7,211 |
| `cost` | 2,009 |
| `replacement_effect` | 1,757 |
| `declaration_restriction` | 170 |
| `declaration_cost` | 11 |

## Semantic packs and implicit overrides

- Pack files: 15
- Program entries: 265
- Unique program keys: 253
- Duplicate keys resolved by pack order: 12
- Unique Oracle IDs represented: 142
- Card-specific operation names: 5
- Typed card-override boundary present: true
- Explicit typed overrides: 0

## Snapshot fingerprints

- Oracle SHA-256: `47be914ae0e54bbf63b285c065b4eb823a5f42927dcff6a404c0023ca870fba0`
- Rulings SHA-256: `6e0f7b8e73981df2da7d91329c1904e68a33c0269ec655d29484379beb3b725e`
- Oracle updated: `2026-08-02T09:02:31.886+00:00`
- Rulings updated: `2026-08-02T09:00:36.367+00:00`

## Boundary

The current compiler is partial and interleaved. Full-corpus exactness is not claimed. Fine-grained closure currently covers only the reviewed base-damage spell slice; other nodes retain the broad-contract fallback. CardProgram V2 now provides canonical aggregation, validation, and replay pinning. Typed handlers and fully distinct compiler stages remain incremental work.
