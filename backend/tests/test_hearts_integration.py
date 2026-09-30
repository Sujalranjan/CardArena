"""End-to-end integration test of room creation, 4-player join, Hearts start, passing, and play."""
import pytest
import pytest_asyncio
from app.database.session import Base
from app.game_engine.action import ActionType, GameAction
from app.models.models import RoomStatus, User
from app.services.game_session_manager import GameSessionManager
from app.services.room_service import RoomService
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def int_db():
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
async def test_hearts_full_4player_flow(int_db: AsyncSession):
    # 1. Create 4 users
    users = [User(username=f"hearts_p{i}", display_name=f"Player {i}") for i in range(1, 5)]
    int_db.add_all(users)
    await int_db.commit()

    # 2. Host creates room for Hearts
    room = await RoomService.create_room(int_db, users[0], selected_game="hearts", max_players=4)
    assert room.code is not None

    # 3. Remaining 3 players join
    for u in users[1:]:
        await RoomService.join_room(int_db, u, room.code)

    refreshed_room = await RoomService.get_room_by_id(int_db, room.id)
    assert len(refreshed_room.players) == 4

    # 4. All players ready up
    for u in users:
        await RoomService.set_player_ready(int_db, room.id, u.id, is_ready=True)

    # 5. Start game session via GameSessionManager
    gsm = GameSessionManager()
    player_ids = [u.id for u in users]
    session = gsm.create_session(room.id, "hearts", player_ids)
    assert session is not None
    assert session.game.game_type == "hearts"

    # 6. Verify hidden information views for each player
    for u in users:
        view = session.game.get_player_view(u.id)
        assert view.viewer_id == u.id
        assert len(view.my_hand) == 13
        # Opponent cards count is 13, but opponent hands are hidden
        for opp in view.players:
            if opp.id != u.id:
                assert opp.card_count == 13
                assert not hasattr(opp, "hand")

    # 7. Execute 3-card pass for all 4 players
    for u in users:
        view = session.game.get_player_view(u.id)
        pass_card_ids = [c.id for c in view.my_hand[:3]]
        success, reason = await gsm.dispatch_action(
            room_id=room.id,
            actor_player_id=u.id,
            action_type_str="PASS_CARD",
            payload={"card_ids": pass_card_ids},
        )
        assert success, reason

    # 8. Verify transition to playing phase and opening player holding 2♣
    p1_view = session.game.get_player_view(users[0].id)
    assert p1_view.phase.value == "IN_PROGRESS"
    turn_player_id = p1_view.current_turn_player_id
    assert turn_player_id in player_ids

    # 9. Opening turn player leads with 2♣
    success, reason = await gsm.dispatch_action(
        room_id=room.id,
        actor_player_id=turn_player_id,
        action_type_str="PLAY_CARD",
        payload={"card_id": "CLUBS_2"},
    )
    assert success, reason

    # Current trick now has 1 card
    trick = session.game.state.hearts_round.current_trick
    assert len(trick) == 1
    assert trick[0].card.id == "CLUBS_2"
