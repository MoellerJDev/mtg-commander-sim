---
title: "Documentation map"
status: "current"
authoritative_source: "repository documentation policy"
verified: "1eb40f99b7269870c7e419aa75ea3e997e7aff0e"
audience: "users, operators, and contributors"
maintenance: "hand-maintained"
---

# Documentation map

This is the authoritative map for maintained project documentation. A document's
front matter identifies whether it describes current behavior, target design,
generated status, an architectural decision, or historical context. Generated
figures belong only in generated reports; current guidance links to them.
Codex `SKILL.md` files use the separate skill-manifest schema, so they are
indexed here but excluded from documentation front-matter validation.

## Start here

- [Project overview and quick start](../README.md)
- [Local application operations](operations/local-app.md)
- [Current platform status](PLATFORM_IMPLEMENTATION_STATUS.md)
- [Current rules boundary](RULES_COMPLETENESS_STATUS.md)
- [Architecture context](architecture/context.md)
- [Contributor workflow](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)

## Architecture

- [System context](architecture/context.md)
- [Runtime containers](architecture/containers.md)
- [Rules kernel](architecture/rules-kernel.md)
- [Card programs](architecture/card-programs.md)
- [Typed semantic handlers](architecture/semantic-handlers.md)
- [Runtime components](architecture/runtime-components.md)
- [Counter-placement transaction](architecture/counter-placement.md)
- [Damage transaction](architecture/damage-transactions.md)
- [Trust and applicable closure](architecture/trust-closure.md)
- [Oracle compiler](architecture/compiler.md)
- [Server runtime](architecture/server-runtime.md)
- [Replay](architecture/replay.md)
- [Visibility and projection](architecture/visibility.md)
- [Dependency and mutation rules](architecture/dependency-rules.md)
- [Architecture decision index](adr/index.md)
- [ADR template](adr/template.md)
- [ADR 0001 — single writer](adr/0001-single-writer-game-actor.md)
- [ADR 0002 — seat projections](adr/0002-seat-projected-network-protocol.md)
- [ADR 0003 — ratcheted enforcement](adr/0003-ratcheted-architecture-enforcement.md)
- [ADR 0004 — fine-grained capability trust](adr/0004-fine-grained-capability-trust.md)
- [ADR 0005 — canonical CardProgram V2](adr/0005-card-program-v2.md)
- [ADR 0006 — typed semantic handler boundary](adr/0006-typed-semantic-handler-boundary.md)
- [ADR 0007 — CardProgram runtime components](adr/0007-cardprogram-runtime-components.md)
- [ADR 0008 — runtime trust and default-deny governance](adr/0008-runtime-trust-and-governance-hardening.md)
- [ADR 0009 — typed tap-state mutation owner](adr/0009-typed-tap-state-mutation-owner.md)
- [ADR 0010 — replacement-event trees and token mutation owner](adr/0010-replacement-event-tree-and-token-owner.md)
- [ADR 0011 — counter-placement event and mutation owner](adr/0011-counter-placement-event-and-mutation-owner.md)
- [ADR 0012 — damage transaction and static prevention owner](adr/0012-damage-transaction-and-static-prevention.md)
- [ADR 0013 — typed damage-result event ownership](adr/0013-damage-result-event-ownership.md)
- [ADR 0014 — typed semantic choice and effect ownership](adr/0014-typed-semantic-choice-and-effect-ownership.md)
- [ADR 0015 — durable damage-modifier ownership](adr/0015-durable-damage-modifier-ownership.md)
- [ADR 0016 — typed casting and activation proposals](adr/0016-typed-casting-activation-proposals.md)
- [ADR 0017 — prevention continuations and aftermath ownership](adr/0017-prevention-continuations-and-aftermath.md)
- [ADR 0018 — unified triggered-ability batch ownership](adr/0018-unified-trigger-batch-ownership.md)
- [Legacy consolidated architecture reference](../ARCHITECTURE.md)
- [Client integration boundary](../CLIENT_INTEGRATION.md)
- [Game Record v3](../GAME_RECORD.md)
- [Server/browser reference](../SERVER_BROWSER.md)

## Extension guides

- [Card override](extension/card-override.md)
- [Mechanic capability](extension/mechanic-capability.md)
- [Semantic node](extension/semantic-node.md)
- [Runtime component](extension/runtime-component.md)
- [Typed Oracle IR reference](../ORACLE_IR.md)
- [Semantic packs](../SEMANTIC_PACKS.md)
- [Mechanic contracts](../mechanics/contracts/README.md)

## Testing and assurance

- [Testing strategy](testing/strategy.md)
- [CI pipeline and two-slot workflow](development/ci-pipeline.md)
- [Interaction coverage](testing/interaction-coverage.md)
- [Replay testing](testing/replay.md)
- [Privacy testing](testing/privacy.md)
- [Mutation testing](testing/mutation.md)
- [Rules conformance policy](../RULE_CONFORMANCE.md)
- [Rules baseline](../RULES_BASELINE.md)
- [Rules completeness program](../RULES_COMPLETENESS.md)
- [Repository hygiene](../REPOSITORY_HYGIENE.md)
- [Protocol smoke fixture](../demo/SMOKE_TEST.md)

## Operations, clients, and pilots

- [Local application](operations/local-app.md)
- [Hosted deployment target](operations/hosted.md)
- [Threat model](THREAT_MODEL.md)
- [Legal and content boundary](LEGAL_CONTENT_BOUNDARY.md)
- [LLM protocol](../LLM_PROTOCOL.md)
- [Pilot providers](../PILOT_PROVIDERS.md)
- [Codex arena](../CODEX_ARENA.md)
- [Commander arena operational skill](../.agents/skills/commander-arena/SKILL.md)
- [Local card database](../data/README.md)

## Generated status

- [Platform implementation status](PLATFORM_IMPLEMENTATION_STATUS.md)
- [Architecture debt status](ARCHITECTURE_DEBT_STATUS.md)
- [Compiler coverage status](COMPILER_COVERAGE_STATUS.md)
- [Platform readiness](../coverage/platform-readiness.md)
- [Mechanics coverage](../coverage/mechanics-coverage.md)
- [Rules coverage](../coverage/rules-coverage.md)
- [Rules conformance coverage](../coverage/rules-conformance.md)
- [Rules dependency queue](RULES_DEPENDENCY_QUEUE.md)
- [Rules delta](../coverage/rules-delta.md)

The older [Oracle coverage](../coverage/oracle-coverage.md) and
[Commander Oracle coverage](../coverage/oracle-coverage-commander.md) Markdown
snapshots are historical narrative companions. Current counts come from the
generated compiler status and its JSON sources.

## Current operational references

- [Integration handoff](../OVERNIGHT_HANDOFF.md)
- [Rules source metadata](../rules/README.md)
- [Agent instructions](../AGENTS.md)

## Target and historical material

- [Roadmap](../ROADMAP.md)
- [Changelog](../CHANGELOG.md)
- [Migration from the duel prototype](../MIGRATION.md)
- [Redesign summary](../REDESIGN_SUMMARY.md)
- [Review before/after](../REVIEW_BEFORE_AFTER.md)
- [Archived review MVP status](REVIEW_MVP_IMPLEMENTATION_STATUS.md)
