from __future__ import annotations

import json
import tempfile
import unittest

from mtg_commander_sim import CommandEnvelope, CommanderSession, GameService, ProjectedClientView, ProtocolError
from common import keep_all, load_assets, make_session


class PermissionProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_wrong_principal_cannot_use_capability(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=21)
        cap = session.engine.permissions.capability_for("pilot:A")
        result = session.engine.try_submit(token=cap.token, principal="pilot:B", action="keep", payload={})
        self.assertFalse(result.ok)
        self.assertIn("not issued", result.summary)
        self.assertFalse(cap.consumed)

    def test_pilot_cannot_submit_arbiter_or_state_mutation_action(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=22)
        result = session.act("pilot:A", {"a": "resolve", "effects": [{"op": "draw"}]})
        self.assertFalse(result.ok)
        self.assertIn("outside capability scope", result.summary)

    def test_private_hands_are_seat_projected(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=23)
        packet = session.packet("pilot:A", full=True)
        self.assertIn("hand", packet["state"]["players"]["A"])
        self.assertNotIn("hand", packet["state"]["players"]["B"])
        self.assertEqual(7, packet["state"]["players"]["B"]["hand_n"])
        self.assertNotIn("known_top", packet["state"]["players"]["A"])
        b_names = {session.state.cards[oid].printed_name for oid in session.state.players["B"].zones["hand"]}
        a_names = {session.state.cards[oid].printed_name for oid in session.state.players["A"].zones["hand"]}
        unique = b_names - a_names
        if unique:
            serialized = json.dumps(packet)
            self.assertTrue(all(name not in serialized for name in unique))

    def test_live_capability_is_repeated_in_delta_packets(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=24)
        first = session.packet("pilot:A", full=True)
        second = session.packet("pilot:A")
        self.assertEqual(first["decision"]["cap"], second["decision"]["cap"])
        self.assertEqual("delta", second["mode"])

    def test_delta_packet_is_smaller_than_bootstrap(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=25)
        full = session.packet("pilot:A", full=True)
        delta = session.packet("pilot:A")
        full_size = session.projector.measure(full)["compact_chars"]
        delta_size = session.projector.measure(delta)["compact_chars"]
        self.assertLess(delta_size, full_size * 0.55)

    def test_rules_lookup_accepts_object_refs(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=26)
        ref = session.state.cards[session.state.players["A"].zones["hand"][0]].ref
        digest = session.rules([ref], max_rulings_per_card=1)
        self.assertIn("### ", digest)
        self.assertIn(session.state.cards[session.state.players["A"].zones["hand"][0]].printed_name, digest)

    def test_service_checks_game_and_capability(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=27)
        service = GameService(session)
        cap = session.engine.permissions.capability_for("pilot:A")
        bad = service.command(CommandEnvelope("wrong", cap.token, "keep", {}), principal="pilot:A")
        self.assertFalse(bad.ok)
        good = service.command(CommandEnvelope(session.state.game_id, cap.token, "keep", {}), principal="pilot:A")
        self.assertTrue(good.ok)

    def test_save_and_load_preserves_cursor_and_state(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=28)
        session.packet("pilot:A", full=True)
        with tempfile.TemporaryDirectory() as tmp:
            session.save(tmp)
            loaded = CommanderSession.load(self.db, tmp)
            self.assertEqual(session.state.game_id, loaded.state.game_id)
            self.assertEqual(1, loaded.cursors["pilot:A"].packet_no)
            self.assertEqual(session.cursors["pilot:A"].view_hash, loaded.cursors["pilot:A"].view_hash)
            self.assertEqual(session.state.event_sequence, loaded.state.event_sequence)

    def test_client_reducer_reconstructs_delta_and_rejects_wrong_base(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=281)
        client = ProjectedClientView("pilot:A")
        full = session.packet("pilot:A", full=True)
        first_state = client.ingest(full)
        self.assertEqual(7, first_state["players"]["A"]["hand_n"])

        # A simultaneous keep changes decision metadata and event history but
        # leaves the projected rules state hash-valid.
        self.assertTrue(session.act("pilot:A", {"a": "keep"}).ok)
        delta = session.packet("pilot:A")
        reconstructed = client.ingest(delta)
        self.assertEqual(delta["view"], client.current_hash)
        self.assertEqual(session.projector._snapshot("pilot:A"), reconstructed)

        bad = dict(delta)
        bad["pkt"] = delta["pkt"] + 1
        bad["base"] = "not-the-current-hash"
        with self.assertRaises(ProtocolError):
            client.ingest(bad)


if __name__ == "__main__":
    unittest.main()

# Additional least-privilege and semantic-cache tests are defined separately so
# unittest discovery still sees them when this module is imported.
class ArbiterBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_arbiter_projection_does_not_receive_private_hands(self):
        from mtg_commander_sim.model import StackItem
        import uuid
        session = make_session(self.db, self.mishra, self.zimone, seed=290)
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.priority_player = None
        engine.state.stack.append(StackItem(uuid.uuid4().hex, "S-unknown", "triggered_ability", "A", "Unknown test ability", semantic_key="unknown:test", visibility=list("ABCD")))
        engine._prepare_stack_resolution()
        packet = session.packet("arbiter", full=True)
        self.assertEqual("arbiter.resolve", packet["decision"]["kind"])
        for seat in "ABCD":
            self.assertNotIn("hand", packet["state"]["players"][seat])
            self.assertEqual(7, packet["state"]["players"][seat]["hand_n"])

    def test_arbiter_does_not_learn_face_down_public_object_identity(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=292)
        engine = session.engine
        object_id = session.state.players["A"].zones["hand"][0]
        engine.move_card(object_id, "battlefield", log=False)
        session.state.cards[object_id].face_down = True
        packet = session.packet("arbiter", full=True)
        projected = packet["state"]["players"]["A"]["bf"]
        face_down = next(obj for obj in projected if obj["id"] == session.state.cards[object_id].ref)
        self.assertEqual("?", face_down["n"])
        self.assertNotIn("cid", face_down)

    def test_cached_semantics_resolve_runtime_target_placeholders(self):
        from mtg_commander_sim.model import StackItem
        from mtg_commander_sim.semantics import SemanticProgram
        import uuid
        session = make_session(self.db, self.mishra, self.zimone, seed=291)
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.priority_player = None
        engine.semantics.put(SemanticProgram(key="test:bolt", label="Test bolt", effects=[{"op": "damage", "target": "$target.0", "amount": 3}]))
        engine.state.stack.append(StackItem(uuid.uuid4().hex, "S-bolt", "triggered_ability", "A", "Test bolt", semantic_key="test:bolt", targets=["B"], visibility=list("ABCD")))
        engine._prepare_stack_resolution()
        self.assertEqual(37, engine.state.players["B"].life)
        self.assertFalse(engine.state.stack)
        self.assertEqual("A", engine.state.priority_player)
