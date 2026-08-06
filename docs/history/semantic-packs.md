---
title: "Semantic-pack compatibility history"
status: "historical"
authoritative_source: "semantic-pack schema, CardProgram compatibility adapter, and historical Game Record loader"
verified: "2026-08-06"
audience: "replay, migration, and semantic compatibility contributors"
maintenance: "hand-maintained"
---

# Semantic-pack compatibility history

Semantic packs were the reviewed card-behavior input before canonical
CardProgram artifacts became the current runtime authority. Tracked packs remain
supported compatibility data for historical records and narrowly reviewed
overrides. They are not the scaling architecture for new cards and do not grant
clients, providers, or an LLM mutation authority.

## Compatibility contract

A pack groups abilities by Oracle ID and records face/ability identity, active
zone, typed choices/effects, source Oracle and rulings hashes, provenance, trust
level, and characterization evidence. Loading converts the supported pack
schema to canonical CardProgram abilities and derives the historical
semantic-key index. A saved `semantics.json` containing both views fails closed
when they disagree.

Historical Game Records pin the semantic registry and source fingerprints used
at creation. Compatibility loading preserves those artifacts and their replay
meaning; it does not upgrade them to current compiler output or capability
closure. Narrow built-in compatibility descriptors may participate only through
the versioned adapter and matching source identity documented by the current
runtime.

## Current authority

New work targets source-spanned [CardPrograms](../architecture/card-programs.md),
the [Oracle compiler](../architecture/compiler.md), fine-grained capabilities,
and reusable typed rules owners. A reviewed pack ability may shadow only the
same stable generated ability key. It cannot hide unrelated residual text or
make an incomplete card trusted.

When substantially similar pack descriptors recur, migrate the wording to a
generic compiler production and subsystem owner, preserve historical loading,
and remove the current duplicate execution path. A genuinely irreducible
exception uses the [card override boundary](../extension/card-override.md) with
source hashes, exact residual classification, rules dependencies, and focused
assurance.

Pack-level reviewed trust is not CardProgram capability closure. Strict play
still fails for material residuals, missing capabilities, source drift,
unsupported targets/costs/layers/replacements, or incomplete interaction,
privacy, replay, and mutation evidence.

See the [Game Record compatibility contract](../reference/game-record.md) and
generated [compiler status](../COMPILER_COVERAGE_STATUS.md). Git history retains
the implementation chronology that this compatibility reference omits.
