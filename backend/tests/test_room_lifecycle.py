"""Tests for Room lifecycle, joins, duplicate protection, ready toggling, and host permissions."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.database.session import Base
from app.models.models import Room, RoomPlayer, RoomStatus, User
from app.services.room_service import RoomService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_room_and_host_assignment(async_db: AsyncSession):
    host = User(username="alice", display_name="Alice")
    async_db.add(host)
    await async_db.commit()
    await async_db.refresh(host)

    room = await RoomService.create_room(async_db, host, selected_game="hearts", max_players=4)

    assert room.code is not None
    assert len(room.code) == 6
    assert room.host_id == host.id
    assert room.status == RoomStatus.WAITING
    assert len(room.players) == 1
    assert room.players[0].user_id == host.id
    assert room.players[0].seat == 0


@pytest.mark.asyncio
async def test_join_room_and_duplicate_join(async_db: AsyncSession):
    alice = User(username="alice", display_name="Alice")
    bob = User(username="bob", display_name="Bob")
    async_db.add_all([alice, bob])
    await async_db.commit()

    room = await RoomService.create_room(async_db, alice, selected_game="teen_patti", max_players=4)

    # Bob joins
    updated_room, bob_player = await RoomService.join_room(async_db, bob, room.code)
    assert len(updated_room.players) == 2
    assert bob_player.seat == 1

    # Bob attempts duplicate join -> should be idempotent, not duplicate seat
    updated_room_2, bob_player_2 = await RoomService.join_room(async_db, bob, room.code)
    assert len(updated_room_2.players) == 2
    assert bob_player_2.seat == 1


@pytest.mark.asyncio
async def test_room_capacity_limit(async_db: AsyncSession):
    users = [User(username=f"user_{i}", display_name=f"User {i}") for i in range(3)]
    async_db.add_all(users)
    await async_db.commit()

    # Room max 2 players
    room = await RoomService.create_room(async_db, users[0], max_players=2)
    await RoomService.join_room(async_db, users[1], room.code)

    # 3rd player attempts to join
    with pytest.raises(ValueError, match="Room is full"):
        await RoomService.join_room(async_db, users[2], room.code)


@pytest.mark.asyncio
async def test_ready_state_and_leave_room(async_db: AsyncSession):
    alice = User(username="alice", display_name="Alice")
    bob = User(username="bob", display_name="Bob")
    async_db.add_all([alice, bob])
    await async_db.commit()

    room = await RoomService.create_room(async_db, alice, max_players=4)
    await RoomService.join_room(async_db, bob, room.code)

    # Bob toggles ready
    updated = await RoomService.set_player_ready(async_db, room.id, bob.id, is_ready=True)
    bob_p = next(p for p in updated.players if p.user_id == bob.id)
    assert bob_p.is_ready is True

    # Bob leaves
    refreshed = await RoomService.leave_room(async_db, bob.id, room.id)
    assert len(refreshed.players) == 1
    assert refreshed.players[0].user_id == alice.id


@pytest.mark.asyncio
async def test_host_transfer_on_leave(async_db: AsyncSession):
    alice = User(username="alice", display_name="Alice")
    bob = User(username="bob", display_name="Bob")
    async_db.add_all([alice, bob])
    await async_db.commit()

    room = await RoomService.create_room(async_db, alice, max_players=4)
    await RoomService.join_room(async_db, bob, room.code)

    # Alice (host) leaves
    refreshed = await RoomService.leave_room(async_db, alice.id, room.id)
    assert len(refreshed.players) == 1
    # Bob should now be the new host
    assert refreshed.host_id == bob.id


@pytest.mark.asyncio
async def test_host_only_settings_update(async_db: AsyncSession):
    alice = User(username="alice", display_name="Alice")
    bob = User(username="bob", display_name="Bob")
    async_db.add_all([alice, bob])
    await async_db.commit()

    room = await RoomService.create_room(async_db, alice, selected_game="hearts", max_players=4)
    await RoomService.join_room(async_db, bob, room.code)

    # Bob (non-host) tries to change settings -> forbidden
    with pytest.raises(PermissionError):
        await RoomService.update_settings(async_db, room.id, bob.id, selected_game="napoleon")

    # Alice (host) updates settings -> success
    updated = await RoomService.update_settings(async_db, room.id, alice.id, selected_game="napoleon", max_players=6)
    assert updated.selected_game == "napoleon"
    assert updated.max_players == 6
