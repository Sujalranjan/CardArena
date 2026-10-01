"""Real 4-player Bluff flow over the WebSocket endpoint with individualized, leak-free views."""
import json
import pytest
from app.games import bluff as bluff_module
from app.services.game_session_manager import game_session_manager
from tests.test_multiplayer_connections import (  # noqa: F401 (room_env is a fixture)
    _close,
    _connect,
    _join_all_sequentially,
    room_env,
)
from tests.test_platform_lifecycle import _recv_until


def _collect(ws, pred, limit=200):
    """Raw texts received up to and including the first message matching pred."""
    texts = []
    for _ in range(limit):
        text = ws.receive_text()
        texts.append(text)
        if pred(json.loads(text)):
            return texts, json.loads(text)
    raise AssertionError("expected message not received")


def _is_state(pred=lambda view: True):
    return lambda m: m["type"] == "GAME_STATE" and pred(m["payload"]["game_view"])


def _private_ids(session, pid):
    return {c.id for c in session.game.state.players[pid].hand}


def _counts(view):
    return {p["id"]: p["card_count"] for p in view["players"]}


@pytest.mark.parametrize("room_env", [("bluff", 4, 4)], indirect=True)
def test_bluff_four_player_websocket_flow(room_env, monkeypatch):
    env = room_env
    p1, p2, p3, p4 = pids = env["user_ids"][:4]
    # The server picks the starter; pin its draw to seat 0 so the scripted flow starts with Player 1
    monkeypatch.setattr(bluff_module.secrets, "randbelow", lambda n: 0)

    sockets = _join_all_sequentially(env, pids)
    try:
        for uid in pids[1:]:
            sockets[uid].send_json({"type": "READY", "payload": {}})
            _recv_until(sockets[uid], "ROOM_STATE", lambda m, u=uid: any(
                p["user_id"] == u and p["is_ready"] for p in m["payload"]["room"]["players"]))
        sockets[p1].send_json({"type": "START_GAME", "payload": {}})

        # ---- Deal: individualized views, commitment first, no foreign cards, no seed ----
        session = None
        for uid, ws in sockets.items():
            texts, msg = _collect(ws, _is_state())
            types = [json.loads(t)["type"] for t in texts]
            assert "FAIRNESS_COMMITTED" in types and types.index("FAIRNESS_COMMITTED") < types.index("GAME_STATE")
            session = game_session_manager.get_session(env["room_id"])
            seed_hex = session.game.fairness.get(1)._server_seed.hex()
            view = msg["payload"]["game_view"]
            assert view["game_type"] == "bluff"
            assert view["viewer_id"] == uid
            assert {c["id"] for c in view["my_hand"]} == _private_ids(session, uid)
            assert sum(_counts(view).values()) == 52
            assert {p["id"]: p["display_name"] for p in view["players"]} == {pid: env["names"][pid] for pid in pids}
            assert view["current_turn_player_id"] == p1
            assert view["valid_actions"] == (["PLAY_CARDS"] if uid == p1 else [])
            for other in pids:
                if other != uid:
                    assert all(cid not in t for t in texts for cid in _private_ids(session, other))
            assert all(seed_hex not in t for t in texts)

        # ---- Player 1 bluffs: two cards of different ranks declared as the first card's rank ----
        hand = session.game.state.players[p1].hand
        first = hand[0]
        second = next(c for c in hand if c.rank != first.rank)
        played_ids = {first.id, second.id}
        p1_count = len(hand)
        play = {"type": "PLAY_CARDS", "payload": {"card_ids": [first.id, second.id], "declared_rank": first.rank.value}}
        sockets[p1].send_json(play)
        sockets[p1].send_json(play)  # duplicate submission must be rejected, not applied twice

        for uid, ws in sockets.items():
            texts, msg = _collect(ws, _is_state(lambda v: v["public_state"]["play_count"] == 1))
            view = msg["payload"]["game_view"]
            assert view["public_state"]["last_play"] == {
                "player_id": p1, "declared_rank": first.rank.value, "declared_quantity": 2,
            }
            assert view["public_state"]["pile_count"] == 2
            assert _counts(view)[p1] == p1_count - 2
            assert view["current_turn_player_id"] == p2
            assert view["valid_actions"] == (["PLAY_CARDS", "CALL_BLUFF"] if uid == p2 else [])
            if uid != p1:
                assert all(cid not in t for t in texts for cid in played_ids)
        # The duplicate arrives after the accepted play's broadcast and is rejected
        _recv_until(sockets[p1], "ERROR")
        assert session.game.state.play_count == 1

        # Only the current player may challenge
        sockets[p3].send_json({"type": "CALL_BLUFF", "payload": {}})
        assert "turn" in _recv_until(sockets[p3], "ERROR")["payload"]["error"].lower()
        # A challenge cannot carry client-decided results
        sockets[p2].send_json({"type": "CALL_BLUFF", "payload": {"pile_recipient_id": p2}})
        _recv_until(sockets[p2], "ERROR")

        # ---- Player 2 challenges; server resolves: false declaration -> Player 1 takes the pile ----
        p2_count = session.game.state.players[p2].card_count()
        sockets[p2].send_json({"type": "CALL_BLUFF", "payload": {}})
        for uid, ws in sockets.items():
            _, msg = _collect(ws, _is_state(lambda v: v["public_state"]["last_challenge"] is not None))
            view = msg["payload"]["game_view"]
            challenge = view["public_state"]["last_challenge"]
            assert challenge["declaration_truthful"] is False
            assert challenge["challenger_id"] == p2 and challenge["challenged_player_id"] == p1
            assert challenge["pile_recipient_id"] == p1
            assert {c["id"] for c in challenge["revealed_cards"]} == played_ids
            assert _counts(view)[p1] == p1_count and _counts(view)[p2] == p2_count
            assert view["public_state"]["pile_count"] == 0
            assert view["public_state"]["last_play"] is None
            assert view["current_turn_player_id"] == p2  # player after the challenged player
        assert played_ids <= _private_ids(session, p1)

        # ---- Truthful declaration: Player 2 plays one card as its own rank, Player 3 challenges ----
        truthful_card = session.game.state.players[p2].hand[0]
        p3_count = session.game.state.players[p3].card_count()
        sockets[p2].send_json({"type": "PLAY_CARDS", "payload": {
            "card_ids": [truthful_card.id], "declared_rank": truthful_card.rank.value}})
        _collect(sockets[p3], _is_state(lambda v: v["public_state"]["play_count"] == 2))
        sockets[p3].send_json({"type": "CALL_BLUFF", "payload": {}})
        for ws in sockets.values():
            _, msg = _collect(ws, _is_state(lambda v: (v["public_state"]["last_challenge"] or {}).get(
                "challenger_id") == p3))
            challenge = msg["payload"]["game_view"]["public_state"]["last_challenge"]
            assert challenge["declaration_truthful"] is True
            assert challenge["pile_recipient_id"] == p3
            assert _counts(msg["payload"]["game_view"])[p3] == p3_count + 1
            assert msg["payload"]["game_view"]["current_turn_player_id"] == p3

        # ---- Reconnect: individualized view restored, others unaffected, nothing leaked ----
        sockets[p4].close()
        for uid in (p1, p2, p3):
            _recv_until(sockets[uid], "PLAYER_DISCONNECTED")
        _close(sockets[p4])
        sockets[p4] = _connect(env, p4)
        texts, msg = _collect(sockets[p4], _is_state())
        view = msg["payload"]["game_view"]
        assert view["viewer_id"] == p4
        assert {c["id"] for c in view["my_hand"]} == _private_ids(session, p4)
        # Cards revealed by the last challenge are public (they now sit in the pile recipient's hand);
        # every other opponent card must be absent
        revealed = {c["id"] for c in view["public_state"]["last_challenge"]["revealed_cards"]}
        for other in (p1, p2, p3):
            leaked = {cid for cid in _private_ids(session, other) - revealed if any(cid in t for t in texts)}
            assert leaked == set(), leaked
        assert all(session.game.fairness.get(1)._server_seed.hex() not in t for t in texts)
        assert game_session_manager.get_session(env["room_id"]) is session
    finally:
        for ws in sockets.values():
            _close(ws)
