"""WebSocket Connection Manager for rooms, state broadcasting, and reconnection."""
from typing import Dict, List, Optional
from fastapi import WebSocket
from app.core.logging import logger
from app.schemas.schemas import WSServerMessage


class ConnectionManager:
    def __init__(self):
        # room_id -> { user_id: WebSocket }
        self._rooms: Dict[str, Dict[str, WebSocket]] = {}
        # websocket -> (room_id, user_id)
        self._socket_map: Dict[WebSocket, tuple[str, str]] = {}

    def is_connected(self, room_id: str, user_id: str) -> bool:
        return room_id in self._rooms and user_id in self._rooms[room_id]

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str) -> None:
        await websocket.accept()

        if room_id not in self._rooms:
            self._rooms[room_id] = {}

        # If user was already connected on an old socket (e.g. page refresh), cleanly close old
        if user_id in self._rooms[room_id]:
            old_ws = self._rooms[room_id][user_id]
            if old_ws != websocket:
                try:
                    await old_ws.close(code=1000, reason="Replaced by new connection")
                except Exception:
                    pass
                if old_ws in self._socket_map:
                    del self._socket_map[old_ws]

        self._rooms[room_id][user_id] = websocket
        self._socket_map[websocket] = (room_id, user_id)
        logger.info(f"WebSocket connected: room={room_id}, user={user_id}")

    def disconnect(self, websocket: WebSocket) -> Optional[tuple[str, str]]:
        if websocket not in self._socket_map:
            return None

        room_id, user_id = self._socket_map.pop(websocket)
        if room_id in self._rooms and user_id in self._rooms[room_id]:
            # Only remove if it's the exact same websocket object
            if self._rooms[room_id][user_id] == websocket:
                del self._rooms[room_id][user_id]
            if not self._rooms[room_id]:
                del self._rooms[room_id]

        logger.info(f"WebSocket disconnected: room={room_id}, user={user_id}")
        return room_id, user_id

    async def send_to_user(self, room_id: str, user_id: str, message: WSServerMessage) -> bool:
        if room_id in self._rooms and user_id in self._rooms[room_id]:
            ws = self._rooms[room_id][user_id]
            try:
                await ws.send_text(message.model_dump_json())
                return True
            except Exception as e:
                logger.error(f"Failed to send to user {user_id}: {e}")
        return False

    async def broadcast_to_room(
        self, room_id: str, message: WSServerMessage, exclude_user_id: Optional[str] = None
    ) -> None:
        if room_id not in self._rooms:
            return

        payload_json = message.model_dump_json()
        disconnected_sockets = []

        for uid, ws in list(self._rooms[room_id].items()):
            if exclude_user_id and uid == exclude_user_id:
                continue
            try:
                await ws.send_text(payload_json)
            except Exception as e:
                logger.error(f"Failed to broadcast to {uid} in {room_id}: {e}")
                disconnected_sockets.append(ws)

        for ws in disconnected_sockets:
            self.disconnect(ws)


manager = ConnectionManager()
