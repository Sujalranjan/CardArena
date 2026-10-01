"""Regression tests: independent players joining one room never displace each other's sockets.

Joins go through the real REST endpoint and connections through the real WebSocket endpoint; the
server-side ConnectionManager registry is inspected directly, not just message delivery.
"""
import asyncio
import json
import anyio.from_thread
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
import app.websocket.endpoints as endpoints_module
from app.auth.auth import create_access_token
from app.database.session import Base, get_db
from app.main import app
from app.models.models import RoomPlayer, User
from app.services.game_session_manager import game_session_manager
from app.services.room_service import RoomService
from app.websocket.connection_manager import manager
from tests.test_platform_lifecycle import _make_sessionmaker, _recv_until


@pytest.fixture
def room_env(tmp_path, monkeypatch, request):
    """A room created by the first of several fresh users; nobody else has joined yet."""
    selected_game, max_players, user_count = request.param
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'multi.db').as_posix()}"

    async def seed():
        engine, maker = _make_sessionmaker(db_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as db:
            users = [User(username=f"multi_{tmp_path.name}_{i}", display_name=f"Multi {i}") for i in range(user_count)]
            db.add_all(users)
            await db.commit()
            room = await RoomService.create_room(db, users[0], selected_game=selected_game, max_players=max_players)
            result = (room.id, room.code, [(u.id, u.display_name) for u in users])
        await engine.dispose()
        return result

    room_id, room_code, users = asyncio.run(seed())
    _, maker = _make_sessionmaker(db_url)
    monkeypatch.setattr(endpoints_module, "AsyncSessionLocal", maker)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async def query(fn):
        engine, qmaker = _make_sessionmaker(db_url)
        async with qmaker() as db:
            value = await fn(db)
        await engine.dispose()
        return value

    client = TestClient(app)
    env = {
        "client": client,
        "room_id": room_id,
        "room_code": room_code,
        "max_players": max_players,
        "user_ids": [uid for uid, _ in users],
        "names": dict(users),
        "tokens": {uid: create_access_token({"sub": uid}) for uid, _ in users},
        "query": lambda fn: asyncio.run(query(fn)),
    }
    # One shared event loop for all sockets, as under uvicorn (see test_platform_lifecycle)
    with anyio.from_thread.start_blocking_portal(**client.async_backend) as portal:
        client.portal = portal
        try:
            yield env
        finally:
            client.portal = None
            app.dependency_overrides.pop(get_db, None)
            game_session_manager.remove_session(room_id)


def _join(env, user_id):
    return env["client"].post(
        "/api/v1/rooms/join",
        json={"room_code": env["room_code"]},
        headers={"Authorization": f"Bearer {env['tokens'][user_id]}"},
    )


def _connect(env, user_id):
    ws = env["client"].websocket_connect(f"/ws/rooms/{env['room_id']}?token={env['tokens'][user_id]}")
    ws.__enter__()
    _recv_until(ws, "ROOM_STATE")
    return ws


def _close(ws):
    ws.__exit__(None, None, None)


def _registered_sockets(env):
    return dict(manager._rooms.get(env["room_id"], {}))


def _memberships(env):
    async def fn(db):
        rows = (await db.execute(select(RoomPlayer).where(RoomPlayer.room_id == env["room_id"]))).scalars().all()
        return {r.user_id: (r.seat, r.is_connected) for r in rows}
    return env["query"](fn)


def _join_all_sequentially(env, player_ids):
    """Players join and connect one by one; after each step every earlier socket is untouched."""
    sockets = {}
    registry_snapshot = {}
    for i, uid in enumerate(player_ids):
        if i > 0:
            response = _join(env, uid)
            assert response.status_code == 200, response.text
        sockets[uid] = _connect(env, uid)

        registry = _registered_sockets(env)
        assert set(registry) == set(player_ids[: i + 1])
        for earlier_uid, server_socket in registry_snapshot.items():
            assert registry[earlier_uid] is server_socket, f"socket of {earlier_uid} was replaced"
        registry_snapshot = registry
    return sockets


def _ping_all(sockets):
    for ws in sockets.values():
        ws.send_json({"type": "PING", "payload": {}})
        _recv_until(ws, "PONG")


@pytest.mark.parametrize("room_env", [("bluff", 4, 4), ("hearts", 4, 4)], indirect=True)
def test_four_independent_players_join_without_displacing_anyone(room_env):
    env = room_env
    player_ids = env["user_ids"][: env["max_players"]]
    sockets = _join_all_sequentially(env, player_ids)
    try:
        assert all(manager.is_connected(env["room_id"], uid) for uid in player_ids)
        _ping_all(sockets)

        memberships = _memberships(env)
        assert set(memberships) == set(player_ids)
        assert len({seat for seat, _ in memberships.values()}) == len(player_ids)
        assert all(connected for _, connected in memberships.values())

        # Every player sees the same room with every member and connection flag set
        for uid, ws in sockets.items():
            ws.send_json({"type": "GET_ROOM_STATE", "payload": {}})
            room = _recv_until(ws, "ROOM_STATE")["payload"]["room"]
            assert room["id"] == env["room_id"]
            assert {p["user_id"] for p in room["players"]} == set(player_ids)
            assert all(p["is_connected"] for p in room["players"])
    finally:
        for ws in sockets.values():
            _close(ws)


@pytest.mark.parametrize("room_env", [("hearts", 4, 4)], indirect=True)
def test_four_players_receive_individualized_game_views(room_env):
    env = room_env
    player_ids = env["user_ids"][: env["max_players"]]
    sockets = _join_all_sequentially(env, player_ids)
    try:
        host_id = player_ids[0]
        for uid in player_ids[1:]:
            sockets[uid].send_json({"type": "READY", "payload": {}})
            _recv_until(sockets[uid], "ROOM_STATE", lambda m, u=uid: any(
                p["user_id"] == u and p["is_ready"] for p in m["payload"]["room"]["players"]))
        sockets[host_id].send_json({"type": "START_GAME", "payload": {}})

        session_hands = None
        for uid, ws in sockets.items():
            raw = None
            for _ in range(100):
                text = ws.receive_text()
                if json.loads(text)["type"] == "GAME_STATE":
                    raw = text
                    break
            view = json.loads(raw)["payload"]["game_view"]
            assert view["viewer_id"] == uid
            assert {p["id"]: p["display_name"] for p in view["players"]} == {
                pid: env["names"][pid] for pid in player_ids
            }
            session = game_session_manager.get_session(env["room_id"])
            session_hands = {pid: {c.id for c in p.hand} for pid, p in session.game.state.players.items()}
            assert {c["id"] for c in view["my_hand"]} == session_hands[uid]
            for other_uid in player_ids:
                if other_uid != uid:
                    assert all(card_id not in raw for card_id in session_hands[other_uid])
        assert all(manager.is_connected(env["room_id"], uid) for uid in player_ids)
    finally:
        for ws in sockets.values():
            _close(ws)


@pytest.mark.parametrize("room_env", [("bluff", 4, 4)], indirect=True)
def test_one_player_reconnecting_does_not_affect_the_others(room_env):
    env = room_env
    player_ids = env["user_ids"][: env["max_players"]]
    sockets = _join_all_sequentially(env, player_ids)
    try:
        leaving = player_ids[len(player_ids) // 2]
        others = [uid for uid in player_ids if uid != leaving]
        others_before = {uid: _registered_sockets(env)[uid] for uid in others}
        seat_before = _memberships(env)[leaving][0]

        sockets[leaving].close()
        for uid in others:
            _recv_until(sockets[uid], "PLAYER_DISCONNECTED")
        _close(sockets[leaving])
        assert not manager.is_connected(env["room_id"], leaving)
        assert _memberships(env)[leaving] == (seat_before, False)

        sockets[leaving] = _connect(env, leaving)
        for uid in others:
            _recv_until(sockets[uid], "PLAYER_RECONNECTED")

        registry = _registered_sockets(env)
        assert set(registry) == set(player_ids)
        for uid in others:
            assert registry[uid] is others_before[uid]
        assert _memberships(env)[leaving] == (seat_before, True)
        _ping_all(sockets)
    finally:
        for ws in sockets.values():
            _close(ws)


@pytest.mark.parametrize("room_env", [("bluff", 4, 5)], indirect=True)
def test_configured_maximum_is_enforced_without_disturbing_members(room_env):
    env = room_env
    player_ids = env["user_ids"][: env["max_players"]]
    extra_user = env["user_ids"][env["max_players"]]
    sockets = _join_all_sequentially(env, player_ids)
    try:
        before = _registered_sockets(env)
        response = _join(env, extra_user)
        assert response.status_code == 400
        assert "full" in response.json()["detail"].lower()

        # A non-member cannot open a room socket either
        with pytest.raises(Exception):
            with env["client"].websocket_connect(
                f"/ws/rooms/{env['room_id']}?token={env['tokens'][extra_user]}"
            ):
                pass

        assert set(_memberships(env)) == set(player_ids)
        after = _registered_sockets(env)
        assert set(after) == set(player_ids)
        assert all(after[uid] is before[uid] for uid in player_ids)
        _ping_all(sockets)
    finally:
        for ws in sockets.values():
            _close(ws)


@pytest.mark.parametrize("room_env", [("bluff", 4, 4)], indirect=True)
def test_second_connection_with_same_identity_replaces_only_that_users_socket(room_env):
    """The intended replacement (e.g. page refresh) is keyed by authenticated user ID only.
    This is why two browser tabs sharing one stored login displaced each other."""
    env = room_env
    player_ids = env["user_ids"][: env["max_players"]]
    sockets = _join_all_sequentially(env, player_ids)
    try:
        target = player_ids[-1]
        others = [uid for uid in player_ids if uid != target]
        before = _registered_sockets(env)

        replacement = _connect(env, target)
        displaced = sockets[target]
        closed = displaced.receive()
        assert closed["type"] == "websocket.close"
        _close(displaced)

        after = _registered_sockets(env)
        assert after[target] is not before[target]
        assert all(after[uid] is before[uid] for uid in others)
        assert all(manager.is_connected(env["room_id"], uid) for uid in player_ids)
        sockets[target] = replacement
        _ping_all(sockets)
    finally:
        for ws in sockets.values():
            _close(ws)
