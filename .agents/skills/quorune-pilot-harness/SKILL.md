---
name: quorune-pilot-harness
description: Coordinate, resume, inspect, or review a four-seat match through Quorune's optional fixed-seat pilot harness.
---

# Quorune Pilot Harness

Use this skill only for the optional pilot-harness adapter. Read the canonical
[arena operations](../../../docs/optional-clients/codex-arena.md),
[provider contract](../../../docs/optional-clients/providers.md), and
[Game Record contract](../../../docs/reference/game-record.md) before acting.

## Operate

1. Validate the requested decks, exact profiles, pinned card snapshot, and
   semantic policy.
2. Create or load the record with the current `simctl arena-* --help`
   contract.
3. Start each requested seat provider once and retain its actual provider,
   model, reasoning, service, and stable session identity when exposed.
4. Give each provider only its fixed-seat task, profile, and bounded memory.
5. Route only the authoritative next principal. Submit strict schema-valid
   output through that seat's façade and return rejection context only to the
   same session. Use the fixed seat's parent-message channel for pilot replies;
   never copy a private task packet into coordinator-visible output.
6. Apply legal seat strategy without coordinator substitution. Stop on an
   unsupported semantic, fidelity failure, identity drift, private-data echo,
   or suppressed meaningful window.
7. Save accepted actions, verify the accepted-command prefix, and regenerate
   derived review/audit artifacts at the requested stop or terminal boundary.

Do not expose checkpoints, raw capabilities, another seat's private context,
provider memory, or run-directory files. Do not improvise rules in trusted-only
play, replace a failed persistent session silently, invent provider metadata,
or label an unfinished/duplicated fixture as deck or matchup evidence.

Report the record lifecycle and stop reason, replay result, privacy/fidelity
result, actual provider identity and interruptions, and the exact remaining
boundary. Keep commands and product policy in the canonical documents rather
than duplicating them here.
