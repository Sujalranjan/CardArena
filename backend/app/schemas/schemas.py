"""Pydantic schemas for REST API and WebSocket payloads."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------- User Schemas ----------------
class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    avatar: Optional[str] = "default"


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---------------- Room Player Schemas ----------------
class RoomPlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    seat: int
    is_ready: bool
    is_connected: bool
    joined_at: datetime
    display_name: str
    username: str
    avatar: Optional[str] = "default"


# ---------------- Room Schemas ----------------
class RoomCreate(BaseModel):
    selected_game: str = "hearts"
    max_players: int = Field(default=4, ge=2, le=8)


class RoomUpdateSettings(BaseModel):
    selected_game: Optional[str] = None
    max_players: Optional[int] = Field(default=None, ge=2, le=8)


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    host_id: str
    selected_game: str
    max_players: int
    status: str
    created_at: datetime
    players: List[RoomPlayerResponse] = []


class JoinRoomRequest(BaseModel):
    room_code: str


# ---------------- WebSocket Message Protocol ----------------
class WSClientMessage(BaseModel):
    """Client -> Server message contract."""
    type: str = Field(description="Message type identifier, e.g. READY, START_GAME, PING")
    payload: Dict[str, Any] = Field(default_factory=dict)


class WSServerMessage(BaseModel):
    """Server -> Client authoritative response or broadcast."""
    type: str = Field(description="Message type identifier, e.g. ROOM_STATE, ERROR, PONG")
    payload: Dict[str, Any] = Field(default_factory=dict)
