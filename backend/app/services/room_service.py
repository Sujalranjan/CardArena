"""Services for room creation, joining, state queries, and persistence."""
import secrets
import string
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.logging import logger
from app.models.models import Room, RoomPlayer, RoomStatus, User
from app.schemas.schemas import RoomPlayerResponse, RoomResponse

# 32-character unambiguous alphabet (omits O, 0, I, 1)
# Entropy: 32^6 = 1,073,741,824 possible codes
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_room_code(length: int = 6) -> str:
    """Generates an unpredictable cryptographically secure room code."""
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(length))


class RoomService:
    @staticmethod
    async def create_room(
        db: AsyncSession, host_user: User, selected_game: str = "hearts", max_players: int = 4
    ) -> Room:
        code = generate_room_code()
        # Ensure code uniqueness with collision retry
        for attempt in range(10):
            existing = await db.execute(select(Room).where(Room.code == code))
            if not existing.scalar_one_or_none():
                break
            code = generate_room_code()

        room = Room(
            code=code,
            host_id=host_user.id,
            selected_game=selected_game,
            max_players=max_players,
            status=RoomStatus.WAITING,
        )
        db.add(room)
        await db.flush()

        host_player = RoomPlayer(
            room_id=room.id,
            user_id=host_user.id,
            seat=0,
            is_ready=False,
            is_connected=True,
        )
        db.add(host_player)
        await db.commit()

        logger.info(f"Room created: code={room.code}, id={room.id}, host={host_user.username}")
        return await RoomService.get_room_by_id(db, room.id)

    @staticmethod
    async def get_room_by_id(db: AsyncSession, room_id: str) -> Optional[Room]:
        stmt = (
            select(Room)
            .where(Room.id == room_id)
            .options(
                selectinload(Room.players).selectinload(RoomPlayer.user),
                selectinload(Room.host_user),
            )
            .execution_options(populate_existing=True)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_room_by_code(db: AsyncSession, room_code: str) -> Optional[Room]:
        stmt = (
            select(Room)
            .where(Room.code == room_code.strip().upper())
            .options(
                selectinload(Room.players).selectinload(RoomPlayer.user),
                selectinload(Room.host_user),
            )
            .execution_options(populate_existing=True)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def join_room(db: AsyncSession, user: User, room_code: str) -> Tuple[Room, RoomPlayer]:
        room = await RoomService.get_room_by_code(db, room_code)
        if not room:
            raise ValueError(f"Room with code '{room_code}' does not exist.")

        if room.status != RoomStatus.WAITING:
            raise ValueError("Cannot join room: game is already in progress or finished.")

        # Atomic query for existing membership
        stmt = select(RoomPlayer).where(
            RoomPlayer.room_id == room.id, RoomPlayer.user_id == user.id
        )
        existing_res = await db.execute(stmt)
        existing_player = existing_res.scalar_one_or_none()
        if existing_player:
            existing_player.is_connected = True
            await db.commit()
            refreshed = await RoomService.get_room_by_id(db, room.id)
            return refreshed, existing_player

        # Query all current players in room to check capacity and seats
        p_stmt = select(RoomPlayer).where(RoomPlayer.room_id == room.id).with_for_update(nowait=False)
        current_players = (await db.execute(p_stmt)).scalars().all()

        if len(current_players) >= room.max_players:
            raise ValueError(f"Room is full (max {room.max_players} players).")

        taken_seats = {p.seat for p in current_players}
        available_seat = 0
        while available_seat in taken_seats:
            available_seat += 1

        new_player = RoomPlayer(
            room_id=room.id,
            user_id=user.id,
            seat=available_seat,
            is_ready=False,
            is_connected=True,
        )
        db.add(new_player)
        await db.commit()

        logger.info(f"Player {user.username} joined room {room.code} in seat {available_seat}")
        refreshed_room = await RoomService.get_room_by_id(db, room.id)
        return refreshed_room, new_player

    @staticmethod
    async def leave_room(db: AsyncSession, user_id: str, room_id: str) -> Optional[Room]:
        stmt = select(RoomPlayer).where(
            RoomPlayer.room_id == room_id, RoomPlayer.user_id == user_id
        )
        res = await db.execute(stmt)
        player_to_remove = res.scalar_one_or_none()
        if not player_to_remove:
            return await RoomService.get_room_by_id(db, room_id)

        await db.delete(player_to_remove)
        await db.commit()
        logger.info(f"Player {user_id} left room {room_id}")

        room_stmt = select(Room).where(Room.id == room_id)
        room_res = await db.execute(room_stmt)
        room = room_res.scalar_one_or_none()
        if not room:
            return None

        rem_stmt = select(RoomPlayer).where(RoomPlayer.room_id == room_id).order_by(RoomPlayer.seat)
        remaining_players = (await db.execute(rem_stmt)).scalars().all()

        if not remaining_players:
            await db.delete(room)
            await db.commit()
            logger.info(f"Room {room_id} deleted because all players left.")
            return None

        if room.host_id == user_id:
            room.host_id = remaining_players[0].user_id
            await db.commit()
            logger.info(f"Host transferred to player {room.host_id} in room {room_id}")

        return await RoomService.get_room_by_id(db, room_id)

    @staticmethod
    async def set_player_ready(
        db: AsyncSession, room_id: str, user_id: str, is_ready: bool
    ) -> Room:
        stmt = select(RoomPlayer).where(
            RoomPlayer.room_id == room_id, RoomPlayer.user_id == user_id
        )
        res = await db.execute(stmt)
        player = res.scalar_one_or_none()
        if not player:
            raise ValueError("Player not in room.")

        player.is_ready = is_ready
        await db.commit()
        logger.info(f"Player {user_id} ready state set to {is_ready} in room {room_id}")
        return await RoomService.get_room_by_id(db, room_id)

    @staticmethod
    async def set_player_connection(
        db: AsyncSession, room_id: str, user_id: str, is_connected: bool
    ) -> Optional[Room]:
        stmt = select(RoomPlayer).where(
            RoomPlayer.room_id == room_id, RoomPlayer.user_id == user_id
        )
        res = await db.execute(stmt)
        player = res.scalar_one_or_none()
        if player:
            player.is_connected = is_connected
            await db.commit()
        return await RoomService.get_room_by_id(db, room_id)

    @staticmethod
    async def set_room_status(db: AsyncSession, room_id: str, status: RoomStatus) -> Optional[Room]:
        room_res = await db.execute(select(Room).where(Room.id == room_id))
        room = room_res.scalar_one_or_none()
        if not room:
            return None
        room.status = status
        await db.commit()
        logger.info(f"Room {room_id} status set to {status.value}")
        return await RoomService.get_room_by_id(db, room_id)

    @staticmethod
    async def update_settings(
        db: AsyncSession,
        room_id: str,
        user_id: str,
        selected_game: Optional[str] = None,
        max_players: Optional[int] = None,
    ) -> Room:
        room_stmt = select(Room).where(Room.id == room_id)
        room_res = await db.execute(room_stmt)
        room = room_res.scalar_one_or_none()
        if not room:
            raise ValueError("Room not found.")
        if room.host_id != user_id:
            raise PermissionError("Only the room host can modify settings.")

        if selected_game:
            room.selected_game = selected_game
        if max_players is not None:
            p_stmt = select(RoomPlayer).where(RoomPlayer.room_id == room.id)
            current_count = len((await db.execute(p_stmt)).scalars().all())
            if max_players < current_count:
                raise ValueError("max_players cannot be less than current player count.")
            room.max_players = max_players

        await db.commit()
        return await RoomService.get_room_by_id(db, room_id)

    @staticmethod
    def serialize_room(room: Room) -> RoomResponse:
        players_dto = []
        for p in room.players:
            display_name = p.user.display_name if p.user else "Unknown"
            username = p.user.username if p.user else "unknown"
            avatar = p.user.avatar if p.user else "default"
            players_dto.append(
                RoomPlayerResponse(
                    id=p.id,
                    user_id=p.user_id,
                    seat=p.seat,
                    is_ready=p.is_ready,
                    is_connected=p.is_connected,
                    joined_at=p.joined_at,
                    display_name=display_name,
                    username=username,
                    avatar=avatar,
                )
            )

        return RoomResponse(
            id=room.id,
            code=room.code,
            host_id=room.host_id,
            selected_game=room.selected_game,
            max_players=room.max_players,
            status=room.status.value if hasattr(room.status, "value") else str(room.status),
            created_at=room.created_at,
            players=players_dto,
        )
