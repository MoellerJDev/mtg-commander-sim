---
title: "Drawing-card transaction"
status: "current"
authoritative_source: "mtg_commander_sim/drawing, semantic_runtime/draw_replacements.py, and CR 121 contract/conformance artifacts"
verified: "2026-08-05"
audience: "rules, compiler, replay, and engine contributors"
maintenance: "hand-maintained"
---

# Drawing-card transaction

Represented game draws use one typed boundary. `drawing/model.py` distinguishes
an instruction to draw N cards from each individual draw event, validates the
replacement or prohibited result, and pins the affected player, library size,
reason, and visibility. `drawing/restrictions.py` owns immutable per-player
permission derived from turn draw history and live fixed restrictions.
`drawing/transaction.py` is the narrow mutation owner for ordinary top-library-
to-hand draws, prohibited and empty-library attempts, draw history/events, the
represented Dredge mill-and-return result, and closed actions tied to the exact
ordinarily drawn object.

`drawing/coordinator.py` iteratively drains individual events and queued
instructions, discovers trusted runtime instruction-count and individual
replacements, recomputes permission before each individual event, issues a
private affected-player choice when necessary, queues typed draw instructions
created by replacement results ahead of the unreplaced instruction tail, and
resumes from the exact remaining count without growing the Python call stack. The same trampoline
continues an APNAP batch, draw-step entry, or the exact next spell instruction.
`drawing/continuation.py` owns that strict immutable Game Record v3 value.
Historical v3 Dredge continuations keep an explicit validated compatibility
path and are not silently reinterpreted.

Turn draws, fixed resolving-effect draws, conditional opponent-cast-color
draws, optional-follow-up draws, and draw-each-player effects converge on this
coordinator. Oracle IR v34 also lowers the closed positive fixed-count
controller, target-player, target-opponent, optional, and each-player grammar
when it is printed as an ordinary activated ability. The source-spanned node
must have a fully compiled activation cost and a strict capability-shaped draw
payload. The closed activated family also includes the exact “draw and reveal;
discard it unless it is a land” sentence used by Fa'adiyah Seer and Sindbad.
Dynamic counts, other compound effects or drawn-card actions, and ambiguous
sibling instructions remain material residuals. Setup hands and mulligan redraws are
intentionally enclosing game procedures, not CR 121 draw events. The ordinary
intent executor rejects a
`DrawCardsIntent` that has not been routed through the coordinator, preventing
a future producer from bypassing replacement, replay, or privacy handling.

The current typed replacement vocabulary includes `PreventDraw`, `DredgeDraw`,
legacy fixed instruction-count `MultiplyAmount`, and `CreateResultDraws`.
Current unconditional controller-doubling programs replace one draw with two
new draw events. The producing effect is canonically excluded from its results
under CR 614.5, while another applicable doubler may replace each new draw;
result draws finish before the unreplaced remainder of the original
instruction. Historical Game Record v3 instruction-multiplier descriptors keep
an explicit compatibility handler and are not silently reinterpreted.
Unsupported material or noncommutative choices fail closed.
`replacement.draw.dredge.v1` is generated from `Dredge N`, is
active only for a trusted exact graveyard CardProgram, requires enough cards in
the library, and pins physical identity plus zone-change counter through the
choice. A replacement is considered even when the library is empty, and it
finishes before a multi-card sequence or later resolution instruction resumes.
Replacement-free and prevented instructions of at least 2,000 draws, an
instruction suspended after 500 events with 1,500 remaining, and a 2,000-item
zero-count batch are regression-tested without recursion. Each excess draw past
the current library is still committed as its own empty-library attempt.

`restriction.draw.maximum-per-turn.v1` discovers trusted, nonphased battlefield
sources and supports the closed any-player, opponent, and source-controller
relations at maxima zero or one. Mandatory multi-draws execute each still-legal
event, while optional draws and draw costs require their complete count to be
legal. Dredge replaces rather than performs a draw and therefore does not
consume a maximum-one allowance. An empty library is not itself a prohibition.
The seat-scoped `offer_draw` handler validates the prospective drawer both
before issuing a task and when the chooser accepts it.

Activation legality and draw outcome remain separate. A fixed draw ability is
still activatable when a live effect will prohibit the eventual draw or the
library is empty. Its mana, tap, and sacrifice costs are paid first; its stack
object then resolves through the same replacement coordinator even if the
physical source has left the battlefield. Dredge can replace that draw before
resolution completes, and only the affected seat sees the replacement choice
or drawn-card identity. Table-wide activated draws use the same APNAP batch as
other each-player producers.

The represented CR 121.6c family applies a public reveal and then a conditional
discard to the exact card moved by an ordinary draw. Those actions do not apply
when that draw is replaced, and public projection retains the revealed card as
known while it remains in hand. This boundary does not evaluate hidden-zone
continuous type changes or other specifically-drawn-card actions.

This boundary certifies only the reviewed passing parts of CR 121, now including
the closed CR 121.6c action family and CR 121.7 result-draw ordering. Shared-team
ordering, conditional/dynamic draw-limit grammar, complete draw-as-cost
producers, broader actions tied to the drawn card, casting-process face-down
draws, optional reveal-as-drawn choices, and the complete Oracle replacement
grammar remain blocked in the contract and scheduler.

Primary focused assurance lives in `test_draw_transaction_model.py`,
`test_draw_transaction_commit.py`, `test_draw_continuation.py`,
`test_draw_replacement_components.py`, `test_draw_step_rules.py`,
`test_draw_restrictions.py`, `test_draw_coordinator_iteration.py`,
`test_draw_result_ordering.py`,
`test_optional_draw_choices.py`,
`test_activated_draw_abilities.py`,
`test_semantic_handlers.py`, and `test_exact_zimone_closure.py`.
