---
title: "Drawing-card transaction"
status: "current"
authoritative_source: "mtg_commander_sim/drawing, semantic_runtime/draw_replacements.py, and CR 121 contract/conformance artifacts"
verified: "2026-08-04"
audience: "rules, compiler, replay, and engine contributors"
maintenance: "hand-maintained"
---

# Drawing-card transaction

Represented game draws use one typed boundary. `drawing/model.py` distinguishes
an instruction to draw N cards from each individual draw event, validates the
replacement result, and pins the affected player, library size, reason, and
visibility. `drawing/transaction.py` is the narrow mutation owner for ordinary
top-library-to-hand draws, empty-library attempts, draw history/events, and the
represented Dredge mill-and-return result.

`drawing/coordinator.py` sequences individual events, discovers trusted runtime
replacements, issues a private affected-player choice when necessary, and
resumes either a later draw, an APNAP batch, draw-step entry, or the exact next
spell instruction. `drawing/continuation.py` owns that strict immutable Game
Record v3 value. Historical v3 Dredge continuations keep an explicit validated
compatibility path and are not silently reinterpreted.

Turn draws, fixed resolving-effect draws, conditional opponent-cast-color
draws, optional-follow-up draws, and draw-each-player effects converge on this
coordinator. Setup hands and mulligan redraws are intentionally enclosing game
procedures, not CR 121 draw events. The ordinary intent executor rejects a
`DrawCardsIntent` that has not been routed through the coordinator, preventing
a future producer from bypassing replacement, replay, or privacy handling.

The current typed replacement vocabulary includes `PreventDraw` and
`DredgeDraw`. `replacement.draw.dredge.v1` is generated from `Dredge N`, is
active only for a trusted exact graveyard CardProgram, requires enough cards in
the library, and pins physical identity plus zone-change counter through the
choice. A replacement is considered even when the library is empty, and it
finishes before a multi-card sequence or later resolution instruction resumes.

This boundary certifies only the reviewed passing parts of CR 121. Per-turn
draw limits, optional-draw and draw-as-cost legality, shared-team ordering,
additional actions tied to the drawn card, result-generated draw ordering,
casting-process face-down draws, reveal-as-drawn choices, and the complete
Oracle replacement grammar remain blocked in the contract and scheduler.

Primary focused assurance lives in `test_draw_transaction_model.py`,
`test_draw_transaction_commit.py`, `test_draw_continuation.py`,
`test_draw_replacement_components.py`, `test_draw_step_rules.py`,
`test_semantic_handlers.py`, and `test_exact_zimone_closure.py`.
