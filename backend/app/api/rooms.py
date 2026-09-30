"""REST endpoints for Room creation, joining, query, and management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.auth import get_current_user
from app.database.session import get_db
from app.models.models import User
from app.schemas.schemas import (
    JoinRoomRequest,
    RoomCreate,
    RoomResponse,
    RoomUpdateSettings,
    WSServerMessage,
)
from app.services.room_service import RoomService
from app.websocket.connection_manager import manager

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    data: RoomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await RoomService.create_room(
        db=db,
        host_user=current_user,
        selected_game=data.selected_game,
        max_players=data.max_players,
    )
    return RoomService.serialize_room(room)


@router.get("/{room_id_or_code}", response_model=RoomResponse)
async def get_room(
    room_id_or_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Try by code first (uppercase) then by ID
    room = await RoomService.get_room_by_code(db, room_id_or_code)
    if not room:
        room = await RoomService.get_room_by_id(db, room_id_or_code)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return RoomService.serialize_room(room)


@router.post("/join", response_model=RoomResponse)
async def join_room(
    data: JoinRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        room, _ = await RoomService.join_room(db, current_user, data.room_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    serialized = RoomService.serialize_room(room)

    # Broadcast updated room state to connected players
    await manager.broadcast_to_room(
        room_id=room.id,
        message=WSServerMessage(
            type="PLAYER_JOINED",
            payload={"room": serialized.model_dump(), "joined_user_id": current_user.id},
        ),
    )

    return serialized


@router.post("/{room_id}/leave", status_code=status.HTTP_200_OK)
async def leave_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    refreshed_room = await RoomService.leave_room(db, current_user.id, room_id)
    if refreshed_room:
        serialized = RoomService.serialize_room(refreshed_room)
        await manager.broadcast_to_room(
            room_id=room_id,
            message=WSServerMessage(
                type="PLAYER_LEFT",
                payload={"room": serialized.model_dump(), "left_user_id": current_user.id},
            ),
        )
    return {"message": "Left room successfully"}


@router.patch("/{room_id}/settings", response_model=RoomResponse)
async def update_room_settings(
    room_id: str,
    data: RoomUpdateSettings,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        room = await RoomService.update_settings(
            db=db,
            room_id=room_id,
            user_id=current_user.id,
            selected_game=data.selected_game,
            max_players=data.max_players,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    serialized = RoomService.serialize_room(room)
    await manager.broadcast_to_room(
        room_id=room.id,
        message=WSServerMessage(type="ROOM_SETTINGS_UPDATED", payload={"room": serialized.model_dump()}),
    )
    return serialized
