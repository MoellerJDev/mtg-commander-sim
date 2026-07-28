from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session, pass_current


class MulliganAndTurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_multiplayer_first_mulligan_is_free_and_redraws_seven(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=11)
        self.assertTrue(session.act("pilot:A", {"a": "mulligan"}).ok)
        for seat in "BCD":
            self.assertTrue(session.act(f"pilot:{seat}", {"a": "keep"}).ok)
        player = session.state.players["A"]
        self.assertEqual(1, player.mulligans_taken)
        self.assertEqual(7, len(player.zones["hand"]))
        packet = session.packet("pilot:A")
        self.assertEqual(1, packet["decision"]["ctx"]["if_mulligan"]["bottom"])
        self.assertEqual(6, packet["decision"]["ctx"]["if_mulligan"]["resulting_hand_size"])
        self.assertIn("KEEP any functional hand", packet["decision"]["ctx"]["decision_policy"])

    def test_second_hand_can_be_kept_at_seven(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=12)
        session.act("pilot:A", {"a": "mulligan"})
        for seat in "BCD":
            session.act(f"pilot:{seat}", {"a": "keep"})
        self.assertTrue(session.act("pilot:A", {"a": "keep"}).ok)
        self.assertEqual(7, len(session.state.players["A"].zones["hand"]))
        self.assertTrue(session.state.started)

    def test_second_counted_mulligan_bottoms_one(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=13)
        session.act("pilot:A", {"a": "mulligan"})
        for seat in "BCD":
            session.act(f"pilot:{seat}", {"a": "keep"})
        session.act("pilot:A", {"a": "mulligan", "override_reason": "Test the counted-mulligan path"})
        packet = session.packet("pilot:A")
        self.assertEqual("mulligan.bottom", packet["decision"]["kind"])
        self.assertEqual(1, packet["decision"]["ctx"]["count"])
        card = packet["decision"]["ctx"]["hand"][0]["id"]
        self.assertTrue(session.act("pilot:A", {"a": "bottom", "cs": [card]}).ok)
        self.assertEqual(6, len(session.state.players["A"].zones["hand"]))
        self.assertTrue(session.act("pilot:A", {"a": "keep"}).ok)
        self.assertEqual(6, len(session.state.players["A"].zones["hand"]))


    def test_functional_post_free_hand_requires_override_to_mulligan_again(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=100)
        # Force the first free redraw, then select a seed until the packet marks
        # the new hand functional. This seed is deterministic for the bundled lists.
        session.act("pilot:A", {"a": "mulligan"})
        for seat in "BCD":
            session.act(f"pilot:{seat}", {"a": "keep"})
        packet = session.packet("pilot:A")
        self.assertTrue(packet["decision"]["ctx"]["signals"]["functional_baseline"])
        rejected = session.act("pilot:A", {"a": "mulligan"})
        self.assertFalse(rejected.ok)
        self.assertIn("functional baseline", rejected.summary)
        accepted = session.act("pilot:A", {"a": "mulligan", "override_reason": "No access to a commander color and no turn-two plan"})
        self.assertTrue(accepted.ok, accepted.summary)

    def test_mulligan_declarations_follow_turn_order_then_redraw_together(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=14)
        self.assertEqual(["pilot:A"], session.pending_principals())
        self.assertTrue(session.act("pilot:A", {"a": "mulligan"}).ok)
        self.assertEqual(["pilot:B"], session.pending_principals())
        self.assertTrue(session.act("pilot:B", {"a": "keep"}).ok)
        self.assertEqual(["pilot:C"], session.pending_principals())
        self.assertTrue(session.act("pilot:C", {"a": "mulligan"}).ok)
        self.assertEqual(["pilot:D"], session.pending_principals())
        self.assertTrue(session.act("pilot:D", {"a": "keep"}).ok)
        # Redraws happen only after the final declaration in the round.
        self.assertEqual(1, session.state.players["A"].mulligans_taken)
        self.assertEqual(1, session.state.players["C"].mulligans_taken)
        self.assertEqual(7, len(session.state.players["A"].zones["hand"]))
        self.assertEqual(7, len(session.state.players["C"].zones["hand"]))
        self.assertEqual(["pilot:A"], session.pending_principals())
        self.assertFalse(session.state.started)

    def test_first_player_draws_on_first_multiplayer_turn(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=15)
        keep_all(session)
        self.assertEqual(("beginning", "upkeep"), (session.state.phase, session.state.step))
        for _ in range(4):
            pass_current(session)
        self.assertEqual(("beginning", "draw"), (session.state.phase, session.state.step))
        self.assertEqual(8, len(session.state.players["A"].zones["hand"]))

    def test_priority_rotates_all_four_seats(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=16)
        keep_all(session)
        observed = []
        for _ in range(4):
            observed.append(session.pending_principals()[0])
            pass_current(session)
        self.assertEqual(["pilot:A", "pilot:B", "pilot:C", "pilot:D"], observed)

    def test_yields_skip_redundant_priority_windows(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=17)
        keep_all(session)
        pass_current(session)
        pass_current(session, yield_mode="until_my_turn")
        pass_current(session, yield_mode="until_my_turn")
        pass_current(session, yield_mode="until_my_turn")
        # Draw step gives A priority; B/C/D will be auto-passed after A passes.
        self.assertEqual("pilot:A", session.pending_principals()[0])
        pass_current(session)
        self.assertEqual(("precombat_main", "main"), (session.state.phase, session.state.step))
        self.assertEqual(["pilot:A"], session.pending_principals())

    def test_empty_known_priority_windows_are_skipped_without_model_calls(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=171, auto_pass_empty=True)
        engine = session.engine
        # Give every player a lands-only opening hand.  The command-zone cards
        # are not castable during upkeep, so the entire opening upkeep priority
        # round has no action represented by the implemented grammar.
        for seat in "ABCD":
            player = session.state.players[seat]
            hand = list(player.zones["hand"])
            land_candidates = [
                oid for oid in player.zones["library"]
                if (
                    engine.card_record(oid)
                    and engine.card_record(oid).is_land
                    and not any(
                        "hand" in ability.zones and not ability.mana_ability
                        for ability in engine._activated_abilities(engine.state.cards[oid])
                    )
                )
            ][: len(hand)]
            self.assertEqual(len(hand), len(land_candidates))
            for old, new in zip(hand, land_candidates):
                hand_index = player.zones["hand"].index(old)
                lib_index = player.zones["library"].index(new)
                player.zones["hand"][hand_index] = new
                player.zones["library"][lib_index] = old
                session.state.cards[new].zone = "hand"
                session.state.cards[old].zone = "library"
        keep_all(session)
        self.assertNotEqual("upkeep", session.state.step)
        self.assertEqual(1, session.state.turn_sequence)


if __name__ == "__main__":
    unittest.main()
