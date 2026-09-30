"""Tests for WebSocket connection management, message schema parsing, and authorization security."""
import json
import pytest
from app.auth.auth import create_access_token
from app.database.session import Base
from app.main import app
from app.models.models import Room, RoomPlayer, RoomStatus, User
from app.schemas.schemas import WSClientMessage, WSServerMessage
from app.websocket.connection_manager import ConnectionManager
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB = "sqlite+aiosqlite:///:memory:"


def test_ws_client_message_validation():
    # Valid message
    msg = WSClientMessage.model_validate({"type": "READY", "payload": {}})
    assert msg.type == "READY"

    # Malformed message (missing type) raises ValidationError
    with pytest.raises(Exception):
        WSClientMessage.model_validate({"payload": "something"})


def test_connection_manager_units():
    cm = ConnectionManager()
    assert not cm.is_connected("room_1", "user_1")


def test_security_fake_token_rejected():
    client = TestClient(app)
    # Connecting with invalid or forged token
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/rooms/any_room_id?token=forged.token.here") as ws:
            pass


def test_security_missing_token_rejected():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/rooms/any_room_id") as ws:
            pass
