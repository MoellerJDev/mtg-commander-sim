---
title: "Documentation map and standard"
status: "current"
authoritative_source: "repository documentation policy and maintained documentation set"
verified: "2026-08-05"
audience: "users, operators, contributors, and coding agents"
maintenance: "hand-maintained"
---

# Documentation map and standard

This is the authoritative index for maintained project documentation. The
repository uses a docs-as-code adaptation of
[Diátaxis](https://diataxis.fr/start-here/): tutorials, how-to guides,
reference and explanation have different jobs and should not be mixed. Software
structure follows the [C4 model](https://c4model.com/diagrams) at context and
container levels; detailed code maps are generated or read from source rather
than manually duplicated. Living prose follows the
[Google developer documentation style](https://developers.google.com/style),
with this project's rules taking precedence. Durable architecture decisions use
indexed ADRs.

## Source-of-truth order

When two sources disagree, use this order:

1. implemented code, schemas and executable tests;
2. machine-readable policy, pinned source manifests and generator inputs;
3. generated reports created from those sources;
4. living tutorials, how-to guides, reference and explanation;
5. ADRs and the changelog, which explain historical decisions but do not define
   current behavior.

Changing metrics, fingerprints, integration coordinates and next-work selection
belong only in generated sources and reports. Living documents describe current
behavior in present tense and link to those reports. The repository does not
keep branch diaries, archived status pages or speculative roadmap documents.

## Start here

- [README and local quick start](../README.md) — tutorial and product overview.
- [Local application operations](operations/local-app.md) — how-to guide.
- [Platform status](PLATFORM_IMPLEMENTATION_STATUS.md) — generated current state.
- [Rules status](RULES_COMPLETENESS_STATUS.md) — current claim boundary.
- [Architecture overview](../ARCHITECTURE.md) — explanation and routing page.
- [Contributing](../CONTRIBUTING.md) — contributor how-to and repository policy.
- [Security](../SECURITY.md) — security reference and reporting policy.
- [Agent instructions](../AGENTS.md) — durable coding-agent guardrails.
- [Integration checkpoint](../OVERNIGHT_HANDOFF.md) — live-state resume checklist.

## Architecture explanations and references

- [System context](architecture/context.md)
- [Runtime containers](architecture/containers.md)
- [Rules kernel](architecture/rules-kernel.md)
- [CardProgram V2](architecture/card-programs.md)
- [Oracle compiler](architecture/compiler.md)
- [Typed semantic handlers](architecture/semantic-handlers.md)
- [Runtime components](architecture/runtime-components.md)
- [Reusable rules pieces](architecture/reusable-rules-pieces.md)
- [Counter placement](architecture/counter-placement.md)
- [Damage transactions](architecture/damage-transactions.md)
- [Drawing](architecture/drawing.md)
- [Trust closure](architecture/trust-closure.md)
- [Server runtime](architecture/server-runtime.md)
- [Replay](architecture/replay.md)
- [Visibility](architecture/visibility.md)
- [Dependency and mutation rules](architecture/dependency-rules.md)
- [Architecture decisions and template](adr/index.md)
- [ADR template](adr/template.md)
- [Client integration boundary](../CLIENT_INTEGRATION.md)
- [Game Record v3](../GAME_RECORD.md)

Decision records:

- [ADR 0001 — one serialized writer](adr/0001-single-writer-game-actor.md)
- [ADR 0002 — seat-projected protocol](adr/0002-seat-projected-network-protocol.md)
- [ADR 0003 — ratcheted architecture enforcement](adr/0003-ratcheted-architecture-enforcement.md)
- [ADR 0004 — fine-grained capability trust](adr/0004-fine-grained-capability-trust.md)
- [ADR 0005 — CardProgram V2](adr/0005-card-program-v2.md)
- [ADR 0006 — typed semantic handlers](adr/0006-typed-semantic-handler-boundary.md)
- [ADR 0007 — runtime components](adr/0007-cardprogram-runtime-components.md)
- [ADR 0008 — runtime trust](adr/0008-runtime-trust-and-governance-hardening.md)
- [ADR 0009 — tap-state mutation](adr/0009-typed-tap-state-mutation-owner.md)
- [ADR 0010 — replacement trees and token ownership](adr/0010-replacement-event-tree-and-token-owner.md)
- [ADR 0011 — counter placement](adr/0011-counter-placement-event-and-mutation-owner.md)
- [ADR 0012 — damage transactions](adr/0012-damage-transaction-and-static-prevention.md)
- [ADR 0013 — damage results](adr/0013-damage-result-event-ownership.md)
- [ADR 0014 — semantic choices and effects](adr/0014-typed-semantic-choice-and-effect-ownership.md)
- [ADR 0015 — durable damage modifiers](adr/0015-durable-damage-modifier-ownership.md)
- [ADR 0016 — casting and activation proposals](adr/0016-typed-casting-activation-proposals.md)
- [ADR 0017 — prevention continuations](adr/0017-prevention-continuations-and-aftermath.md)
- [ADR 0018 — trigger batches](adr/0018-unified-trigger-batch-ownership.md)
- [ADR 0019 — zone-trigger discovery](adr/0019-normalized-zone-trigger-discovery.md)
- [ADR 0020 — continuous-effect duration](adr/0020-continuous-effect-duration-and-applicability.md)
- [ADR 0021 — draw transactions](adr/0021-canonical-draw-transaction.md)
- [ADR 0022 — reusable rules pieces](adr/0022-reusable-rules-piece-inventory.md)
- [ADR 0023 — documentation system](adr/0023-documentation-system.md)

## Product and protocol references

- [Server and browser](../SERVER_BROWSER.md)
- [Local card database](../data/README.md)
- [Deployment boundary](operations/hosted.md)
- [Legal and third-party content boundary](LEGAL_CONTENT_BOUNDARY.md)
- [Threat model](THREAT_MODEL.md)
- [LLM client protocol](../LLM_PROTOCOL.md)
- [Pilot providers](../PILOT_PROVIDERS.md)
- [Codex arena adapter](../CODEX_ARENA.md)
- [Commander arena operational skill](../.agents/skills/commander-arena/SKILL.md)

Optional pilot documents describe clients of the ordinary projected protocol.
They do not define rules authority or a runtime dependency.

## Rules and extension references

- [Rules completeness program](../RULES_COMPLETENESS.md)
- [Rules conformance policy](../RULE_CONFORMANCE.md)
- [Typed Oracle IR](../ORACLE_IR.md)
- [Semantic packs](../SEMANTIC_PACKS.md)
- [Mechanic contracts](../mechanics/contracts/README.md)
- [Derived rules metadata](../rules/README.md)
- [Card override extension](extension/card-override.md)
- [Mechanic capability extension](extension/mechanic-capability.md)
- [Semantic node extension](extension/semantic-node.md)
- [Runtime component extension](extension/runtime-component.md)

## Testing and contributor how-to guides

- [Testing strategy](testing/strategy.md)
- [CI pipeline and two-slot workflow](development/ci-pipeline.md)
- [Interaction coverage](testing/interaction-coverage.md)
- [Replay testing](testing/replay.md)
- [Privacy testing](testing/privacy.md)
- [Mutation testing](testing/mutation.md)
- [Protocol smoke fixture](../demo/SMOKE_TEST.md)

## Generated current status

- [Platform implementation status](PLATFORM_IMPLEMENTATION_STATUS.md)
- [Architecture debt status](ARCHITECTURE_DEBT_STATUS.md)
- [Compiler coverage status](COMPILER_COVERAGE_STATUS.md)
- [Rules dependency queue](RULES_DEPENDENCY_QUEUE.md)
- [Platform readiness](../coverage/platform-readiness.md)
- [Card-unlock frontier](../coverage/card-unlock-frontier.md)
- [Reusable rules-piece matrix](../coverage/reusable-piece-matrix.md)
- [Reusable rules-piece delta](../coverage/reusable-piece-delta.md)
- [Complex-card composition](../coverage/complex-card-composition.md)
- [Mechanics coverage](../coverage/mechanics-coverage.md)
- [Rules coverage](../coverage/rules-coverage.md)
- [Rules conformance coverage](../coverage/rules-conformance.md)
- [Rules delta](../coverage/rules-delta.md)
- [CI escape report](../coverage/ci-escape-report.md)

## Historical record

- [Changelog](../CHANGELOG.md)
- [Architecture decision records](adr/index.md)

Historical status snapshots, migration narratives and before/after reports are
removed when their durable decisions or user guidance already exist elsewhere.
Git history remains available when archaeology is necessary.

## Maintenance rules

- Prefer editing an existing owner over adding a document.
- Give every document one dominant Diátaxis purpose and one audience.
- Keep current guidance timeless: no transient branch, PR, CI-run or copied
  coverage facts.
- Put a command next to the task it performs and keep it safe to copy.
- Link to a single authority instead of paraphrasing it in several places.
- Delete superseded guidance in the same pull request as its replacement.
- Add an ADR only for a durable decision with meaningful alternatives and
  consequences.
- Run `scripts/validate_documentation.py --check`; broken links, missing index
  entries, invalid metadata and volatile claims fail CI.
