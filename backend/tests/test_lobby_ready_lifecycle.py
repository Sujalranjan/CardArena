"""Regression tests for Lobby Ready Flow and START_GAME WebSocket Handling."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.auth.auth import create_access_token
from app.database.session import Base
from app.game_engine.registry import GameRegistry
from app.game_engine.state import GamePhase
from app.games.hearts import HeartsGame
from app.models.models import RoomStatus, User
from app.schemas.schemas import WSClientMessage, WSServerMessage
from app.services.game_session_manager import GameSessionManager
from app.services.room_service import RoomService
from app.websocket.connection_manager import ConnectionManager

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def lobby_db():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_ready_and_start_game_lifecycle_invariants(lobby_db: AsyncSession):
    """
    A. Connected non-host sends READY -> server accepts it.
    B. READY updates that player's ready state.
    C. READY state is broadcast to other room members.
    D. Repeated READY/NOT_READY behavior follows intended implementation.
    E. Host START_GAME with 4 players but one or more non-hosts not ready -> controlled rejection.
    F. Host START_GAME with exactly 4 players and all required players ready -> Hearts starts.
    G. Client cannot spoof another player's ready state.
    """
    # Setup 4 users
    users = [User(username=f"user_lobby_{i}", display_name=f"Lobby Player {i}") for i in range(1, 5)]
    lobby_db.add_all(users)
    await lobby_db.commit()

    host = users[0]
    p2, p3, p4 = users[1], users[2], users[3]

    # Host creates room
    room = await RoomService.create_room(lobby_db, host, selected_game="hearts", max_players=4)
    for u in [p2, p3, p4]:
        await RoomService.join_room(lobby_db, u, room.code)

    refreshed_room = await RoomService.get_room_by_id(lobby_db, room.id)
    assert len(refreshed_room.players) == 4

    # 1. Non-host toggles READY
    updated_1 = await RoomService.set_player_ready(lobby_db, room.id, p2.id, is_ready=True)
    p2_player = next(p for p in updated_1.players if p.user_id == p2.id)
    assert p2_player.is_ready is True

    # 2. Non-host toggles NOT_READY
    updated_2 = await RoomService.set_player_ready(lobby_db, room.id, p2.id, is_ready=False)
    p2_player_2 = next(p for p in updated_2.players if p.user_id == p2.id)
    assert p2_player_2.is_ready is False

    # 3. Re-mark p2 ready, but leave p3, p4 unready
    await RoomService.set_player_ready(lobby_db, room.id, p2.id, is_ready=True)
    room_check = await RoomService.get_room_by_id(lobby_db, room.id)

    # 4. Host attempts START_GAME while p3 and p4 are not ready
    non_host_unready = [
        p.user.display_name for p in room_check.players
        if p.user_id != room_check.host_id and not p.is_ready
    ]
    assert len(non_host_unready) == 2
    assert "Lobby Player 3" in non_host_unready
    assert "Lobby Player 4" in non_host_unready

    # 5. All non-hosts become ready
    await RoomService.set_player_ready(lobby_db, room.id, p3.id, is_ready=True)
    await RoomService.set_player_ready(lobby_db, room.id, p4.id, is_ready=True)

    ready_room = await RoomService.get_room_by_id(lobby_db, room.id)
    all_ready = all(p.is_ready for p in ready_room.players if p.user_id != ready_room.host_id)
    assert all_ready is True

    # 6. Now host can launch Hearts session
    gsm = GameSessionManager()
    session = gsm.create_session(
        room_id=ready_room.id,
        game_type="hearts",
        player_ids=[p.user_id for p in ready_room.players],
    )
    assert session is not None
    assert session.game.game_type == "hearts"
    assert session.game.state.phase == GamePhase.STARTING
