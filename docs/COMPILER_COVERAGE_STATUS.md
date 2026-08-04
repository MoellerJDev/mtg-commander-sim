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

- Compiler: `oracle-ir-v30`
- Runtime IR: OracleCardIR lowered to canonical CardProgram V2 with a derived SemanticProgram compatibility index
- CardProgram V2 present: true
- Compiler module: 1,577 physical / 1,530 logical lines

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

- Registry schema/version: `1/27`
- Pinned rules effective date: `2026-06-19`
- Registry fingerprint: `cc9f8dc5e03e36b394feed0ecec7b7962ceadb52c65326fa76f1cda812c934cb`
- Evidence fingerprint: `e0c2ab9f5054230f436d95bff1164da513be4b5bd6960d430e648f42fa61b65f`
- Explicit evidence declarations: 343
- Capability records: 44
- Trusted records: 34
- Blocked records: 4
- Dependency fail-closed statuses: `{"not_applicable": 19, "not_run": 3, "passed": 22}`
- Implementation mutation statuses: `{"killed": 37, "not_run": 7}`

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
| Full Oracle | 38,542 | 3,463 | 16,015 | 19,064 | 65,692 | false |
| Commander legal | 31,623 | 782 | 14,585 | 16,256 | 57,177 | false |

## Full-corpus residual kinds

| Kind | Count |
|---|---:|
| `dependency_contract` | 16,539 |
| `trigger` | 15,274 |
| `spell_effect` | 11,321 |
| `static_ability` | 11,148 |
| `effect` | 7,240 |
| `cost` | 2,015 |
| `replacement_effect` | 1,758 |
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

The current compiler is partial and interleaved. Full-corpus exactness is not claimed. Fine-grained closure currently covers only the reviewed base-damage spell slice; other nodes retain the broad-contract fallback. CardProgram V2 now provides canonical aggregation, validation, and replay pinning. Typed handlers and fully distinct compiler stages remain incremental work.
