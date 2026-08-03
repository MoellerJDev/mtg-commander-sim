---
title: "Compiler coverage status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "f39730fd6dab90af9667748e3d7d0e15fc713f8b"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Compiler coverage status

This generated report describes only the pinned Oracle corpus and current compiler. Exact compilation is not the same as complete game-behavior proof.

## Current representation

- Compiler: `oracle-ir-v16`
- Runtime IR: OracleCardIR lowered to canonical CardProgram V2 with a derived SemanticProgram compatibility index
- CardProgram V2 present: true
- Compiler module: 1,781 physical / 1,713 logical lines

## Canonical CardProgram

- Schema version: `2`
- Schema: `schemas/card-program-v2.schema.json`
- Required card fields: 14
- Required per-ability fields: 27
- Model: `mtg_commander_sim/card_programs/model.py`
- Generated/reviewed adapter: `mtg_commander_sim/card_programs/adapters.py`
- Runtime validator: `mtg_commander_sim/card_programs/validation.py`
- Canonical reviewed registry CardPrograms: 143
- Intrinsic strict-capability-ready CardPrograms: 0
- Trust bases: `{"legacy_reviewed": 143}`

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

- Registry schema/version: `1/12`
- Pinned rules effective date: `2026-06-19`
- Registry fingerprint: `3ed41585ededd2a66aaa72ba341ce5a9f6ba0624c7123f0e19a65115e5e08a9c`
- Evidence fingerprint: `3ac1c6a252be1159623147c906e4074e7857035127815faf743dd41882b51a21`
- Explicit evidence declarations: 211
- Capability records: 33
- Trusted records: 21
- Blocked records: 4
- Dependency fail-closed statuses: `{"not_applicable": 12, "not_run": 3, "passed": 18}`
- Implementation mutation statuses: `{"killed": 24, "not_run": 9}`

| Broad aggregate | Capability records | Trusted | Blocked members |
|---|---:|---:|---|
| `cr-121-drawing-a-card` | 1 | false | `zone.draw.library_to_hand` |
| `cr-120-damage` | 18 | false | `damage.combat.excess`, `damage.prevention.order`, `damage.replacement.order`, `damage.trigger.noncombat` |
| `cr-725-the-monarch` | 1 | false | `variant.monarch.designate` |
| `cr-903-commander` | 1 | true | none |
| `cr-111-tokens` | 1 | false | `token.creation.additional_replacement` |
| `cr-614-replacement-effects` | 1 | false | `zone.change.destination_replacement` |
| `cr-613-continuous-effects` | 2 | false | `continuous.power_toughness.fixed_anthem` |
| `tap-and-untap` | 3 | false | `permanent.tap.effect`, `permanent.untap.all_creatures`, `permanent.untap.effect` |

## Pinned corpus accounting

| Scope | Oracle IDs | Exact | Partial | Unresolved | Material residuals | Complete |
|---|---:|---:|---:|---:|---:|---:|
| Full Oracle | 38,485 | 3,052 | 16,097 | 19,336 | 69,384 | false |
| Commander legal | 31,623 | 412 | 14,676 | 16,535 | 60,761 | false |

## Full-corpus residual kinds

| Kind | Count |
|---|---:|
| `dependency_contract` | 19,419 |
| `trigger` | 15,246 |
| `static_ability` | 12,086 |
| `spell_effect` | 11,375 |
| `effect` | 7,291 |
| `cost` | 2,009 |
| `replacement_effect` | 1,777 |
| `declaration_restriction` | 170 |
| `declaration_cost` | 11 |

## Semantic packs and implicit overrides

- Pack files: 15
- Program entries: 265
- Unique program keys: 253
- Duplicate keys resolved by pack order: 12
- Unique Oracle IDs represented: 143
- Card-specific operation names: 6
- Typed card-override boundary present: true
- Explicit typed overrides: 0

## Snapshot fingerprints

- Oracle SHA-256: `47be914ae0e54bbf63b285c065b4eb823a5f42927dcff6a404c0023ca870fba0`
- Rulings SHA-256: `6e0f7b8e73981df2da7d91329c1904e68a33c0269ec655d29484379beb3b725e`
- Oracle updated: `2026-08-02T09:02:31.886+00:00`
- Rulings updated: `2026-08-02T09:00:36.367+00:00`

## Boundary

The current compiler is partial and interleaved. Full-corpus exactness is not claimed. Fine-grained closure currently covers only the reviewed base-damage spell slice; other nodes retain the broad-contract fallback. CardProgram V2 now provides canonical aggregation, validation, and replay pinning. Typed handlers and fully distinct compiler stages remain incremental work.
