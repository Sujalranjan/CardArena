"""Regression tests for platform lifecycle hardening through the real WebSocket endpoint:
duplicate START_GAME, GAME_OVER cleanup, authoritative display names and connection status."""
import asyncio
import json
import anyio.from_thread
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
import app.websocket.endpoints as endpoints_module
from app.auth.auth import create_access_token
from app.database.session import Base
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.state import GamePhase
from app.main import app
from app.models.models import Room, RoomPlayer, RoomStatus, User
from app.services.game_session_manager import GameSessionManager, game_session_manager
from app.services.room_service import RoomService

DISPLAY_NAMES = ["Alice Host", "Bob Builder", "Carol Singer", "Dave Diver"]


def _make_sessionmaker(db_url: str):
    # NullPool: each session opens a fresh connection on whichever event loop uses it
    # (the TestClient portal loop or the test's own asyncio.run loop).
    engine = create_async_engine(db_url, poolclass=NullPool)
    return engine, async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    """Seeds 4 users in a ready Hearts room and points the WebSocket endpoint at a temp DB."""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'lifecycle.db').as_posix()}"

    async def seed():
        engine, maker = _make_sessionmaker(db_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as db:
            users = [
                User(username=f"lifecycle_user_{i}", display_name=name)
                for i, name in enumerate(DISPLAY_NAMES)
            ]
            db.add_all(users)
            await db.commit()
            room = await RoomService.create_room(db, users[0], selected_game="hearts", max_players=4)
            for u in users[1:]:
                await RoomService.join_room(db, u, room.code)
                await RoomService.set_player_ready(db, room.id, u.id, is_ready=True)
            result = (room.id, [u.id for u in users])
        await engine.dispose()
        return result

    room_id, user_ids = asyncio.run(seed())

    _, endpoint_maker = _make_sessionmaker(db_url)
    monkeypatch.setattr(endpoints_module, "AsyncSessionLocal", endpoint_maker)

    async def query(fn):
        engine, maker = _make_sessionmaker(db_url)
        async with maker() as db:
            value = await fn(db)
        await engine.dispose()
        return value

    client = TestClient(app)
    env = {
        "client": client,
        "room_id": room_id,
        "user_ids": user_ids,
        "tokens": [create_access_token({"sub": uid}) for uid in user_ids],
        "query": lambda fn: asyncio.run(query(fn)),
    }
    # All WebSocket sessions must share one event loop (as under uvicorn) so cross-socket
    # broadcasts wake waiting receivers. Set the portal directly rather than entering
    # `with client:`, which would run the app lifespan against the real database.
    with anyio.from_thread.start_blocking_portal(**client.async_backend) as portal:
        client.portal = portal
        try:
            yield env
        finally:
            client.portal = None
            game_session_manager.remove_session(room_id)


def _connect(env, idx):
    return env["client"].websocket_connect(f"/ws/rooms/{env['room_id']}?token={env['tokens'][idx]}")


def _recv_until(ws, msg_type, pred=None, limit=100):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == msg_type and (pred is None or pred(msg)):
            return msg
    raise AssertionError(f"Did not receive {msg_type} within {limit} messages")


def _room_status(env):
    async def fn(db):
        return (await db.execute(select(Room.status).where(Room.id == env["room_id"]))).scalar_one()
    return env["query"](fn)


def _room_player(env, user_id):
    async def fn(db):
        stmt = select(RoomPlayer).where(RoomPlayer.room_id == env["room_id"], RoomPlayer.user_id == user_id)
        return (await db.execute(stmt)).scalar_one()
    return env["query"](fn)


def _player_entry(game_view, player_id):
    return next(p for p in game_view["players"] if p["id"] == player_id)


# ---------------- A, B, E: duplicate START_GAME + display names ----------------
def test_duplicate_start_game_rejected_and_session_preserved(ws_env):
    room_id = ws_env["room_id"]
    user_ids = ws_env["user_ids"]

    with _connect(ws_env, 0) as host_ws:
        _recv_until(host_ws, "ROOM_STATE")
        host_ws.send_json({"type": "START_GAME", "payload": {}})
        first_view = _recv_until(host_ws, "GAME_STATE")["payload"]["game_view"]
        _recv_until(host_ws, "GAME_STARTED")

        # E. Real authoritative display names, not "Player N"
        names = {p["id"]: p["display_name"] for p in first_view["players"]}
        assert names == dict(zip(user_ids, DISPLAY_NAMES))

        session = game_session_manager.get_session(room_id)
        assert session is not None
        hands_before = {pid: [c.id for c in p.hand] for pid, p in session.game.state.players.items()}
        events_before = len(session.event_history)

        # A. Second START_GAME while PLAYING -> controlled ERROR
        host_ws.send_json({"type": "START_GAME", "payload": {}})
        error = _recv_until(host_ws, "ERROR")
        assert "cannot be started" in error["payload"]["error"]

        # B. Existing session untouched, not replaced
        assert game_session_manager.get_session(room_id) is session
        hands_after = {pid: [c.id for c in p.hand] for pid, p in session.game.state.players.items()}
        assert hands_after == hands_before
        assert len(session.event_history) == events_before
        assert _room_status(ws_env) == RoomStatus.PLAYING

        # WebSocket remains connected and responsive
        host_ws.send_json({"type": "PING", "payload": {}})
        _recv_until(host_ws, "PONG")


def test_session_manager_refuses_to_replace_existing_session():
    gsm = GameSessionManager()
    session = gsm.create_session("room_no_replace", "hearts", ["p1", "p2", "p3", "p4"])
    with pytest.raises(ValueError):
        gsm.create_session("room_no_replace", "hearts", ["p1", "p2", "p3", "p4"])
    assert gsm.get_session("room_no_replace") is session


# ---------------- C, D: GAME_OVER cleanup and post-game rejection ----------------
def _rig_final_trick(session, player_ids):
    """Last trick of a round where player 0 takes a heart and crosses 100 points."""
    state = session.game.state
    hr = state.hearts_round
    state.phase = GamePhase.IN_PROGRESS
    hr.is_first_trick = False
    hr.hearts_broken = True
    hr.completed_tricks_count = 12
    hr.current_trick = []
    hr.trick_lead_suit = None
    hr.round_points = {pid: 0 for pid in player_ids}
    hr.taken_cards = {pid: [] for pid in player_ids}
    final_cards = [
        Card.create(Suit.CLUBS, Rank.ACE),
        Card.create(Suit.CLUBS, Rank.TWO),
        Card.create(Suit.CLUBS, Rank.THREE),
        Card.create(Suit.HEARTS, Rank.FIVE),
    ]
    for pid, card in zip(player_ids, final_cards):
        state.players[pid].hand = [card]
    state.scores = {pid: 0 for pid in player_ids}
    state.scores[player_ids[0]] = 99
    state.current_turn_player_id = player_ids[0]
    return final_cards


def test_game_over_cleans_up_session_and_finishes_room(ws_env):
    room_id = ws_env["room_id"]
    user_ids = ws_env["user_ids"]

    with _connect(ws_env, 0) as ws0, _connect(ws_env, 1) as ws1, \
            _connect(ws_env, 2) as ws2, _connect(ws_env, 3) as ws3:
        sockets = [ws0, ws1, ws2, ws3]
        for ws in sockets:
            _recv_until(ws, "ROOM_STATE")

        ws0.send_json({"type": "START_GAME", "payload": {}})
        _recv_until(ws0, "GAME_STARTED")

        session = game_session_manager.get_session(room_id)
        final_cards = _rig_final_trick(session, user_ids)

        for i, (ws, card) in enumerate(zip(sockets, final_cards)):
            ws.send_json({"type": "PLAY_CARD", "payload": {"card_id": card.id}})
            if i < 3:
                _recv_until(
                    ws, "GAME_STATE",
                    lambda m, n=i + 1: len(m["payload"]["game_view"]["public_state"]["current_trick"]) == n,
                )

        # Final state broadcast to every player, followed by room lifecycle update
        for ws in sockets:
            final = _recv_until(ws, "GAME_STATE", lambda m: m["payload"]["game_view"]["phase"] == "GAME_OVER")
            assert final["payload"]["game_view"]["scores"][user_ids[0]] == 100
            room_msg = _recv_until(ws, "ROOM_STATE", lambda m: m["payload"].get("event") == "GAME_OVER")
            assert room_msg["payload"]["room"]["status"] == "FINISHED"

        # C. Session cleaned up; room not stuck in PLAYING
        assert not game_session_manager.has_session(room_id)
        assert _room_status(ws_env) == RoomStatus.FINISHED

        # D. Post-GAME_OVER actions rejected
        ws1.send_json({"type": "PLAY_CARD", "payload": {"card_id": "CLUBS_4"}})
        assert "No active game session" in _recv_until(ws1, "ERROR")["payload"]["error"]
        ws0.send_json({"type": "START_GAME", "payload": {}})
        assert "cannot be started" in _recv_until(ws0, "ERROR")["payload"]["error"]
        assert not game_session_manager.has_session(room_id)


@pytest.mark.asyncio
async def test_dispatch_game_over_invokes_callback_and_rejects_further_actions():
    gsm = GameSessionManager()
    player_ids = ["p1", "p2", "p3", "p4"]
    session = gsm.create_session("room_gsm_over", "hearts", player_ids)
    final_cards = _rig_final_trick(session, player_ids)

    finished_rooms = []

    async def on_game_over(room_id):
        finished_rooms.append(room_id)

    for pid, card in zip(player_ids, final_cards):
        ok, reason = await gsm.dispatch_action(
            "room_gsm_over", pid, "PLAY_CARD", {"card_id": card.id}, on_game_over=on_game_over
        )
        assert ok, reason

    assert session.game.state.phase == GamePhase.GAME_OVER
    assert finished_rooms == ["room_gsm_over"]
    assert not gsm.has_session("room_gsm_over")

    ok, reason = await gsm.dispatch_action("room_gsm_over", "p1", "PLAY_CARD", {"card_id": "CLUBS_4"})
    assert not ok
    assert "No active game session" in reason


# ---------------- F, G: disconnect / reconnect ----------------
def test_disconnect_reconnect_updates_connection_state_without_leaking_cards(ws_env):
    room_id = ws_env["room_id"]
    host_id, p2_id, p3_id, _ = ws_env["user_ids"]

    with _connect(ws_env, 0) as host_ws:
        _recv_until(host_ws, "ROOM_STATE")

        with _connect(ws_env, 1) as p2_ws:
            _recv_until(p2_ws, "ROOM_STATE")
            host_ws.send_json({"type": "START_GAME", "payload": {}})
            view = _recv_until(host_ws, "GAME_STATE")["payload"]["game_view"]
            _recv_until(host_ws, "GAME_STARTED")
            assert _player_entry(view, p2_id)["is_connected"] is True
            assert _player_entry(view, p3_id)["is_connected"] is False  # never connected

            # Client-initiated close. Wait for the server's handling before leaving the
            # context: TestClient cancels the handler task on context exit, which a real
            # client disconnect does not do.
            p2_ws.close()

            # F. p2 disconnected: peers' game view and DB reflect it
            _recv_until(host_ws, "PLAYER_DISCONNECTED")
            _recv_until(
                host_ws, "GAME_STATE",
                lambda m: _player_entry(m["payload"]["game_view"], p2_id)["is_connected"] is False,
            )
        p2_record = _room_player(ws_env, p2_id)
        assert p2_record.is_connected is False
        seat_before = p2_record.seat

        session = game_session_manager.get_session(room_id)
        p2_hand_ids = [c.id for c in session.game.state.players[p2_id].hand]

        # Reconnect: same seat, same hand, connected again
        with _connect(ws_env, 1) as p2_ws:
            room_msg = _recv_until(p2_ws, "ROOM_STATE")
            p2_seat = next(p["seat"] for p in room_msg["payload"]["room"]["players"] if p["user_id"] == p2_id)
            assert p2_seat == seat_before

            recon = _recv_until(p2_ws, "GAME_STATE")["payload"]["game_view"]
            assert recon["viewer_id"] == p2_id
            assert [c["id"] for c in recon["my_hand"]] == p2_hand_ids
            assert _player_entry(recon, p2_id)["is_connected"] is True

            # G. No opponent private cards anywhere in the reconnect payload
            serialized = json.dumps(recon)
            for pid, player in session.game.state.players.items():
                if pid == p2_id:
                    continue
                for card in player.hand:
                    assert card.id not in serialized

            _recv_until(
                host_ws, "GAME_STATE",
                lambda m: _player_entry(m["payload"]["game_view"], p2_id)["is_connected"] is True,
            )
            assert _room_player(ws_env, p2_id).is_connected is True
            assert game_session_manager.get_session(room_id) is session
