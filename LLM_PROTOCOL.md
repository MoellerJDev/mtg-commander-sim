---
title: "LLM pilot and arbiter protocol"
status: "current"
authoritative_source: "pilot protocol schemas and session implementation"
verified: "2026-08-05"
audience: "pilot-provider and protocol contributors"
maintenance: "hand-maintained"
---

# LLM pilot and arbiter protocol

This document describes an optional untrusted client adapter retained for
experimentation. It is not the product architecture, a rules authority, or a
CI/merge/release gate. Browser, scripted, manual, subprocess, and future AI
clients must use the same projected-state and capability-command boundary.
Strict production games never require a model-authored ruling.

## Recommended process layout

For strict hidden information, use five independent contexts:

- `pilot:A`
- `pilot:B`
- `pilot:C`
- `pilot:D`
- `arbiter`

A sixth analyst context can review full game logs after the game. A single ChatGPT context may pilot every seat for exploratory testing, but that relies on the model honoring seat projections rather than literally forgetting prior hands.

`PilotProvider` is the transport-neutral strategic boundary. The built-in
implementations are deterministic scripted responses, manual JSON
file/stdin exchange, and JSON stdin/stdout subprocesses. Each seat owns a
provider instance and `PilotMemory`; the arbiter is never multiplexed into a
strategic seat. See `PILOT_PROVIDERS.md`.

## Pilot system instruction

```text
You are pilot:{SEAT} in a four-player Commander game.
Maximize this seat's probability of winning. Use only the current projected
state and legally retained seat memory. Do not invent mana, targets, triggers,
or rules. Output exactly one JSON action and no prose.

Mulligans: declarations occur in turn order. The first multiplayer mulligan is
free. After the free redraw, keep every functional hand unless there is a
specific deck-dependent reason that a six-card hand is more likely to function.
A merely imperfect second seven is a keep.

Use short object references. Request rulings only when an interaction is
material. Use a yield when there is no plausible action before a defined stop.
```

## Packet protocol 3.0

### Full bootstrap

```json
{
  "v":"3.0",
  "mode":"full",
  "principal":"pilot:A",
  "pkt":1,
  "base":null,
  "view":"35b27d09191ffba709cd",
  "view_revision":0,
  "state":{
    "rev":0,
    "event":6,
    "game":{"id":"a1b2c3d4","over":false,"winner":null},
    "turn":{"seq":0,"active":null,"phase":"setup","step":"mulligan"},
    "players":{
      "A":{"life":40,"hand":[{"id":"A12","cid":"...","n":"..."}],"bf":[],"gy":[],"cmd":[...]},
      "B":{"life":40,"hand_n":7,"bf":[],"gy":[],"cmd":[...]}
    },
    "stack":[],
    "combat":{"atk":{},"blk":{}}
  },
  "defs":[...],
  "events":[...],
  "decision":{
    "cap":"c_opaque",
    "kind":"mulligan.declare",
    "allow":["keep","mulligan"],
    "legal_actions":[
      {"id":"keep","action":"keep"},
      {"id":"mulligan","action":"mulligan"}
    ],
    "ctx":{...}
  }
}
```

### Delta

```json
{
  "v":"3.0",
  "mode":"delta",
  "principal":"pilot:A",
  "pkt":2,
  "base":"35b27d09191ffba709cd",
  "view":"e84b4a13aca4595e7e1a",
  "view_revision":1,
  "rev":1,
  "event":11,
  "patch":[
    {"op":"replace","path":"/rev","value":1},
    {"op":"replace","path":"/event","value":11}
  ],
  "events":[...],
  "decision":null
}
```

`decision` is always present. A live capability repeats until consumed; `null` explicitly clears a stale decision. A client applies the patch only when `base` matches its current hash.

### Compact object fields

| Field | Meaning |
|---|---|
| `id` | stable game-object reference |
| `n` | visible name |
| `cid` | short Oracle/card-definition ID |
| `tap` | tapped |
| `ctr` | counters |
| `dmg` | marked damage |
| `tok` | token |
| `cmd` | commander |
| `ctl` | non-owner controller |
| `at` | attached-to object |
| `atk` | defender being attacked |

## Player response envelope

The in-process session derives the current capability. A network client also sends the capability token from the packet in its authenticated command envelope.

Prefer `action_id` over reconstructing an action from prose. Priority IDs are
stable within the decision, for example `play-land:A37`, `cast:A12`, or
`activate:A44:ab2`. The response may add only choices still required by that
catalog entry:

```json
{
  "action_id":"activate:A44:ab2",
  "choices":{"search_card":"A73"},
  "plan":"FIX_COLORS",
  "reason":"Fetch the untapped source needed for the next spell.",
  "confidence":0.91,
  "memory_update":"The fetched source establishes the missing color."
}
```

`reason`, `plan`, `confidence`, model identity, token counts, and latency are
decision-audit metadata. `CommanderSession` removes them before submitting the
normalized action to `CommanderEngine`. Rejections are logged as decision
attempts but never as accepted replay commands.

Provider responses validate against `schemas/pilot-response.schema.json`.
`reason` is limited to 180 characters, `memory_update` to 500, confidence to
0–1, and `plan` to the fixed strategic categories documented in
`PILOT_PROVIDERS.md`. A fingerprinted advisory deck profile is loaded once into
that seat's private memory rather than repeated in every observation.

Provider, model/implementation ID, invocation ID, usage, latency, retry, and
fallback fields are audit metadata. A decision row is counted as a provider
invocation only when the runner actually called a provider. Missing usage stays
unknown; it is not replaced by a token estimate.

An ordered `actions` array may contain future `{"action_id":"..."}` entries. The session
executes a queued entry without another model call only when the same principal
immediately receives the next decision and that ID is still in the new
server-generated catalog. A different actor, a missing/stale ID, a rejection,
or a save/load boundary invalidates the remaining plan. Each automatic planned
action is still a normal authorized command with its own hashes and audit row.

### Mulligan

Keep:

```json
{"a":"keep"}
```

After the free redraw, a functional hand needs a concrete reason to go to six:

```json
{
  "a":"mulligan",
  "override_reason":"Two lands, but neither produces green and every functional line requires green by turn two."
}
```

After a counted redraw:

```json
{"a":"bottom","cs":["A17"]}
```

The simulation policy should reject vague reasons such as “looking for a stronger hand.”

### Priority

Pass once:

```json
{"a":"p"}
```

Yield until the seat's next turn unless invalidated:

```json
{"a":"p","y":"until_my_turn"}
```

Play a land:

```json
{"action_id":"play-land:A37","pay_life":true}
```

Cast with conservative automatic payment:

```json
{"a":"c","card":"A12","targets":["S4"],"auto_pay":true}
```

Cast while reserving blue mana:

```json
{"a":"c","card":"A12","auto_pay":true,"reserve":{"U":1}}
```

Activate an advertised ability. The `legal.abilities` array supplies a stable ability id; the pilot chooses physical objects for any delegated cost but never submits effect operations:

```json
{
  "a":"x",
  "source":"A44",
  "ability":"ab2",
  "cost_cards":["T3"],
  "targets":[]
}
```

Fetchland activation advertises only the legal subtype filter. After the
ability survives priority and begins resolving, a private `search.fetch`
decision advertises the then-current `search_cards`. The pilot chooses one of
those refs (or legally fails to find); the kernel revalidates the choice,
derives the found land's entry state, and shuffles. The pilot never mutates the
library or battlefield, and the choice is not leaked before resolution.

Activate Channel from hand:

```json
{
  "a":"x",
  "source":"B17",
  "from":"hand",
  "ability":"ab2",
  "targets":["C31"],
  "pay":"auto"
}
```

A compact ability hint may look like this:

```json
{"s":"B17","z":"hand","a":"ab2","i":1,"m":{"GENERIC":1,"G":1},"discard_self":1,"legend_discount":1}
```

`cost_effects`, arbitrary `declared_cost`, and unadvertised cast zones are rejected in strict mode. If an alternate cost or unusual nonmana cost is not compiled, the action fails closed and is added to semantic/cost coverage work rather than being accepted on the pilot's assertion.

Concede:

```json
{"a":"con"}
```

### Combat

Attack different opponents:

```json
{"a":"atk","attackers":{"A21":"B","A34":"D"}}
```

No attacks:

```json
{"a":"atk","attackers":{}}
```

Block:

```json
{"a":"blk","blocks":{"B18":"A21"}}
```

No blocks:

```json
{"a":"blk","blocks":{}}
```

Complex damage assignment:

```json
{
  "a":"dmg",
  "assignments":[
    {"source":"A21","target":"B18","amount":2},
    {"source":"B18","target":"A21","amount":3}
  ]
}
```

### Delegated choices

Legend rule:

```json
{"a":"choose","card":"A44"}
```

Sacrifice/discard selection:

```json
{"a":"choose","cs":["B18"]}
```

Trigger order, bottom to top:

```json
{"a":"order","triggers":["G3","G2","G1"]}
```

## Arbiter protocol

The arbiter is not a strategic pilot. It receives public state, the resolving object, targets/modes/X, and local card definitions. It may request a rules digest by object reference.

Resolve once:

```json
{
  "a":"resolve",
  "effects":[
    {"op":"damage","target":"$target.0","amount":3}
  ],
  "destination":"graveyard",
  "note":"The target remained legal."
}
```

Register reusable semantics and resolve:

```json
{
  "a":"register_and_resolve",
  "semantic_key":"oracle-id:spell:front",
  "effects":[
    {"op":"damage","target":"$target.0","amount":3}
  ],
  "destination":"graveyard"
}
```

All targets illegal:

```json
{"a":"fizzle","destination":"graveyard"}
```

The arbiter must delegate strategic choices to the affected player rather than selecting for them.

## When to request rules

Use `session.rules(["A44", "S4"])` or the CLI `rules` command when:

- a target or mode may be illegal
- a replacement/prevention effect changes the operation
- copied or face-changing characteristics matter
- last known information matters
- multiple triggers interact
- a shortcut or deterministic loop is proposed

Do not request rulings for routine mana, ordinary timing, or straightforward combat.

## Rejected-action retry

A rejected command does not consume the underlying game decision. The runner may deliver a compact retry field while preserving the same seat projection and capability:

```json
{
  "retry":{
    "attempt":2,
    "error":"Pilot-declared casting cost does not match authoritative cost.",
    "instruction":"Correct only the illegal assumption and return one JSON action."
  }
}
```

Do not narrate the mistake or rewrite the state. Return one corrected action. The default runner allows two retries and records failures separately from accepted decisions.

## Token discipline

1. Do not restate Oracle text already present in `defs`.
2. Use object references, not card names, in actions.
3. Return one JSON action only.
4. Let the engine auto-pass known-empty windows.
5. Use yields to avoid calls across irrelevant windows.
6. Ask for rules only at pivotal ambiguity.
7. Register reusable semantics after the first correct resolution.
8. Keep postgame analysis out of live pilot contexts.
9. Use full packets only for initial bootstrap or hash resynchronization.
10. Prefer fresh per-seat contexts or periodically compacted seat memory for very long games.
