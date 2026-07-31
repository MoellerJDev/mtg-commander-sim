from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from common import DB_PATH, ROOT
from mtg_commander_sim import CardDatabase
from mtg_commander_sim.record import replay_record
from server import ServerSettings, create_app
from server.app import COOKIE_NAME, CSRF_COOKIE_NAME


class ServerApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = ServerSettings(
            card_db=DB_PATH,
            database=root / "server.sqlite3",
            game_root=root / "games",
        )
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def restart_client(self) -> None:
        self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()

    def guest(self, name: str) -> tuple[str, str]:
        response = self.client.post(
            "/api/v1/guests", json={"display_name": name}
        )
        self.assertEqual(201, response.status_code, response.text)
        return response.json()["access_token"], response.json()["csrf_token"]

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def create_ready_game(self) -> tuple[str, list[str], str]:
        tokens = [self.guest(f"Player {seat}")[0] for seat in "ABCD"]
        response = self.client.post(
            "/api/v1/rooms",
            headers=self.auth(tokens[0]),
            json={"seed": 20260730},
        )
        self.assertEqual(201, response.status_code, response.text)
        room_id = response.json()["room"]["room_id"]
        invite = response.json()["invite_code"]
        for index, seat in enumerate("BCD", 1):
            response = self.client.post(
                "/api/v1/rooms/join",
                headers=self.auth(tokens[index]),
                json={"invite_code": invite, "seat": seat},
            )
            self.assertEqual(200, response.status_code, response.text)
        for index, seat in enumerate("ABCD"):
            zimone = seat in "AC"
            path = ROOT / "examples" / (
                "zimone-and-dina.txt"
                if zimone
                else "mishra-eminent-one.txt"
            )
            response = self.client.put(
                f"/api/v1/rooms/{room_id}/deck",
                headers=self.auth(tokens[index]),
                json={
                    "name": f"Deck {seat}",
                    "commander": (
                        "Zimone and Dina" if zimone else "Mishra, Eminent One"
                    ),
                    "decklist": path.read_text(encoding="utf-8"),
                },
            )
            self.assertEqual(200, response.status_code, response.text)
            self.assertTrue(response.json()["preflight"]["trusted_only_ready"])
        response = self.client.post(
            f"/api/v1/rooms/{room_id}/start",
            headers=self.auth(tokens[0]),
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["game_id"], tokens, room_id

    def test_guest_csrf_room_and_atomic_seat_claims(self):
        blank = self.client.post(
            "/api/v1/guests", json={"display_name": "   "}
        )
        self.assertEqual(422, blank.status_code, blank.text)

        alice, csrf = self.guest("Alice")
        bob, _ = self.guest("Bob")
        carol, _ = self.guest("Carol")

        denied = self.client.post("/api/v1/rooms", json={"seed": 1})
        self.assertEqual(403, denied.status_code)
        self.client.cookies.set(COOKIE_NAME, alice)
        self.client.cookies.set(CSRF_COOKIE_NAME, csrf)
        created = self.client.post(
            "/api/v1/rooms",
            headers={"X-CSRF-Token": csrf},
            json={"seed": 1},
        )
        self.assertEqual(201, created.status_code, created.text)
        room = created.json()["room"]
        invite = created.json()["invite_code"]
        self.assertTrue(room["seats"][0]["mine"])
        self.assertEqual("A", room["seats"][0]["seat"])
        unsafe_source = self.client.put(
            f"/api/v1/rooms/{room['room_id']}/deck",
            headers=self.auth(alice),
            json={
                "name": "Unsafe",
                "source_url": "https://example.invalid/deck",
            },
        )
        self.assertEqual(422, unsafe_source.status_code)
        self.assertIn("public Moxfield", unsafe_source.text)

        joined = self.client.post(
            "/api/v1/rooms/join",
            headers=self.auth(bob),
            json={"invite_code": invite, "seat": "B"},
        )
        self.assertEqual(200, joined.status_code, joined.text)
        conflict = self.client.post(
            "/api/v1/rooms/join",
            headers=self.auth(carol),
            json={"invite_code": invite, "seat": "B"},
        )
        self.assertEqual(409, conflict.status_code)

        outsider = self.client.get(
            f"/api/v1/rooms/{room['room_id']}", headers=self.auth(carol)
        )
        self.assertEqual(403, outsider.status_code)
        me = self.client.get("/api/v1/me", headers=self.auth(alice))
        self.assertEqual("Alice", me.json()["guest"]["display_name"])

    def test_four_seat_projection_websocket_reconnect_and_exact_replay(self):
        game_id, tokens, _ = self.create_ready_game()
        packets = []
        for index, seat in enumerate("ABCD"):
            response = self.client.get(
                f"/api/v1/games/{game_id}/state?full=true",
                headers=self.auth(tokens[index]),
            )
            self.assertEqual(200, response.status_code, response.text)
            packet = response.json()["packet"]
            self.assertEqual(f"pilot:{seat}", packet["principal"])
            self.assertEqual(game_id, packet["state"]["game"]["id"])
            packets.append(packet)

        a_players = packets[0]["state"]["players"]
        self.assertIn("hand", a_players["A"])
        self.assertNotIn("hand", a_players["B"])
        self.assertNotIn("hand", a_players["C"])
        self.assertNotIn("hand", a_players["D"])

        self.client.cookies.set(COOKIE_NAME, tokens[0])
        with self.client.websocket_connect(
            f"/api/v1/games/{game_id}/stream"
        ) as websocket_a:
            initial_a = websocket_a.receive_json()
            self.assertEqual("full", initial_a["packet"]["mode"])
            self.client.cookies.set(COOKIE_NAME, tokens[1])
            with self.client.websocket_connect(
                f"/api/v1/games/{game_id}/stream"
            ) as websocket_b:
                initial_b = websocket_b.receive_json()
                self.assertEqual("pilot:B", initial_b["packet"]["principal"])
                packet = initial_a["packet"]
                envelope = {
                    "protocol_version": "3.0",
                    "game_id": game_id,
                    "command_id": "browser-A-0001",
                    "decision_id": packet["decision"]["id"],
                    "action_id": "keep",
                    "capability": packet["decision"]["cap"],
                    "expected_view_revision": packet["view_revision"],
                    "choices": {},
                }
                response = self.client.post(
                    f"/api/v1/games/{game_id}/commands",
                    headers=self.auth(tokens[0]),
                    json=envelope,
                )
                self.assertEqual(200, response.status_code, response.text)
                self.assertTrue(response.json()["receipt"]["ok"])
                self.assertEqual(
                    "pilot:A", websocket_a.receive_json()["packet"]["principal"]
                )
                update_b = websocket_b.receive_json()["packet"]
                self.assertEqual("pilot:B", update_b["principal"])

                duplicate = self.client.post(
                    f"/api/v1/games/{game_id}/commands",
                    headers=self.auth(tokens[0]),
                    json=envelope,
                )
                self.assertTrue(duplicate.json()["receipt"]["replayed"])

                b_decision = update_b["decision"]
                stolen = {
                    **envelope,
                    "command_id": "browser-A-stolen",
                    "decision_id": b_decision["id"],
                    "capability": b_decision["cap"],
                    "expected_view_revision": update_b["view_revision"],
                }
                rejected = self.client.post(
                    f"/api/v1/games/{game_id}/commands",
                    headers=self.auth(tokens[0]),
                    json=stolen,
                )
                self.assertEqual(
                    "unauthorized_capability",
                    rejected.json()["receipt"]["code"],
                )

        self.client.cookies.set(COOKIE_NAME, tokens[0])
        with self.client.websocket_connect(
            f"/api/v1/games/{game_id}/stream"
        ) as reconnected:
            packet = reconnected.receive_json()["packet"]
            self.assertEqual("full", packet["mode"])
            self.assertEqual(1, packet["view_revision"])

        bad = {**envelope, "principal": "pilot:B"}
        response = self.client.post(
            f"/api/v1/games/{game_id}/commands",
            headers=self.auth(tokens[0]),
            json=bad,
        )
        self.assertEqual(422, response.status_code)

        record_dir = self.settings.game_root / game_id
        commands = [
            json.loads(line)
            for line in (record_dir / "commands.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(1, len(commands))
        self.assertEqual("browser-A-0001", commands[0]["client_command_id"])
        capability = envelope["capability"]
        for path in (
            record_dir / "commands.jsonl",
            record_dir / "checkpoint.json",
            self.settings.database,
        ):
            self.assertNotIn(capability.encode(), path.read_bytes(), path.name)

        database = CardDatabase(DB_PATH)
        try:
            replay = replay_record(record_dir, database, verify=True)
        finally:
            database.close()
        self.assertTrue(replay["ok"])

    def test_server_restart_recovers_decision_idempotency_and_replay(self):
        game_id, tokens, _ = self.create_ready_game()
        response = self.client.get(
            f"/api/v1/games/{game_id}/state?full=true",
            headers=self.auth(tokens[0]),
        )
        self.assertEqual(200, response.status_code, response.text)
        packet_a = response.json()["packet"]
        envelope_a = {
            "protocol_version": "3.0",
            "game_id": game_id,
            "command_id": "restart-A-0001",
            "decision_id": packet_a["decision"]["id"],
            "action_id": "keep",
            "capability": packet_a["decision"]["cap"],
            "expected_view_revision": packet_a["view_revision"],
            "choices": {},
        }
        accepted_a = self.client.post(
            f"/api/v1/games/{game_id}/commands",
            headers=self.auth(tokens[0]),
            json=envelope_a,
        )
        self.assertEqual(200, accepted_a.status_code, accepted_a.text)
        self.assertTrue(accepted_a.json()["receipt"]["ok"])
        revision_after_a = accepted_a.json()["receipt"]["state_revision"]

        before_restart = self.client.get(
            f"/api/v1/games/{game_id}/state?full=true",
            headers=self.auth(tokens[1]),
        )
        self.assertEqual(200, before_restart.status_code, before_restart.text)
        packet_b_before = before_restart.json()["packet"]
        self.assertIsNotNone(packet_b_before["decision"])

        self.restart_client()

        recovered = self.client.get(
            f"/api/v1/games/{game_id}/state?full=true",
            headers=self.auth(tokens[1]),
        )
        self.assertEqual(200, recovered.status_code, recovered.text)
        packet_b = recovered.json()["packet"]
        self.assertEqual("pilot:B", packet_b["principal"])
        self.assertEqual(revision_after_a, packet_b["view_revision"])
        self.assertEqual(
            packet_b_before["decision"]["id"],
            packet_b["decision"]["id"],
        )
        self.assertNotEqual(
            packet_b_before["decision"]["cap"],
            packet_b["decision"]["cap"],
        )

        duplicate = self.client.post(
            f"/api/v1/games/{game_id}/commands",
            headers=self.auth(tokens[0]),
            json=envelope_a,
        )
        self.assertEqual(200, duplicate.status_code, duplicate.text)
        self.assertTrue(duplicate.json()["receipt"]["ok"])
        self.assertTrue(duplicate.json()["receipt"]["replayed"])

        envelope_b = {
            "protocol_version": "3.0",
            "game_id": game_id,
            "command_id": "restart-B-0001",
            "decision_id": packet_b["decision"]["id"],
            "action_id": "keep",
            "capability": packet_b["decision"]["cap"],
            "expected_view_revision": packet_b["view_revision"],
            "choices": {},
        }
        accepted_b = self.client.post(
            f"/api/v1/games/{game_id}/commands",
            headers=self.auth(tokens[1]),
            json=envelope_b,
        )
        self.assertEqual(200, accepted_b.status_code, accepted_b.text)
        self.assertTrue(accepted_b.json()["receipt"]["ok"])

        database = CardDatabase(DB_PATH)
        try:
            replay = replay_record(
                self.settings.game_root / game_id,
                database,
                verify=True,
            )
        finally:
            database.close()
        self.assertTrue(replay["ok"])


if __name__ == "__main__":
    unittest.main()
