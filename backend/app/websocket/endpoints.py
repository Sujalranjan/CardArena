"""WebSocket endpoint with hardened identity verification, typed action dispatch, and reconnection."""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from app.auth.auth import get_user_from_token
from app.core.logging import logger
from app.database.session import AsyncSessionLocal
from app.game_engine.action import ActionType
from app.game_engine.registry import GameRegistry
from app.models.models import RoomStatus
from app.schemas.schemas import WSClientMessage, WSServerMessage
from app.services.game_session_manager import game_session_manager
from app.services.room_service import RoomService
from app.websocket.connection_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/rooms/{room_id}")
async def room_websocket_endpoint(websocket: WebSocket, room_id: str):
    """
    WebSocket endpoint for realtime room updates and game actions.
    Authentication token is strictly verified from query params `?token=...`.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token")
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_from_token(token, db)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid auth token")
            return

        room = await RoomService.get_room_by_id(db, room_id)
        if not room:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Room not found")
            return

        # Authorization: user must already have a membership record in this room
        player = next((p for p in room.players if p.user_id == user.id), None)
        if not player:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION, reason="Not authorized for this room"
            )
            return

        # Secure connection: bind websocket to user.id derived from token
        await manager.connect(websocket, room_id, user.id)
        await RoomService.set_player_connection(db, room_id, user.id, is_connected=True)

        refreshed_room = await RoomService.get_room_by_id(db, room_id)
        serialized_room = RoomService.serialize_room(refreshed_room)

        # Notify peers of reconnection
        await manager.broadcast_to_room(
            room_id=room_id,
            message=WSServerMessage(
                type="PLAYER_RECONNECTED",
                payload={"room": serialized_room.model_dump(), "user_id": user.id},
            ),
        )

        # Send initial room state to connecting user
        await manager.send_to_user(
            room_id=room_id,
            user_id=user.id,
            message=WSServerMessage(
                type="ROOM_STATE",
                payload={"room": serialized_room.model_dump()},
            ),
        )

        # If a game session is active, send sanitized player view
        await game_session_manager.send_reconnect_view(room_id, user.id)

    try:
        while True:
            raw_text = await websocket.receive_text()

            # 1. Parse and validate JSON message frame
            try:
                raw_json = json.loads(raw_text)
                client_msg = WSClientMessage.model_validate(raw_json)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Malformed WS message from user {user.id}: {e}")
                await manager.send_to_user(
                    room_id=room_id,
                    user_id=user.id,
                    message=WSServerMessage(
                        type="ERROR",
                        payload={"error": "Malformed message schema"},
                    ),
                )
                continue

            msg_type = client_msg.type.upper()
            payload = client_msg.payload

            # 2. SECURITY HARDENING: Rejection / Neutralization of forged client player_id
            # The client is NEVER allowed to dictate acting player identity.
            if "player_id" in payload and payload["player_id"] != user.id:
                logger.warning(
                    f"SECURITY ALERT: User {user.id} attempted to spoof player_id '{payload['player_id']}'"
                )
                await manager.send_to_user(
                    room_id=room_id,
                    user_id=user.id,
                    message=WSServerMessage(
                        type="ERROR",
                        payload={"error": "Player impersonation detected and rejected"},
                    ),
                )
                continue

            # 3. Handle Game Actions via GameSessionManager
            in_game_action_types = {
                ActionType.PLAY_CARD.value,
                ActionType.DRAW_CARD.value,
                ActionType.DISCARD_CARD.value,
                ActionType.PASS_CARD.value,
                ActionType.BET.value,
                ActionType.CALL.value,
                ActionType.FOLD.value,
                ActionType.CHALLENGE.value,
                ActionType.END_TURN.value,
            }

            if msg_type in in_game_action_types:
                success, reason = await game_session_manager.dispatch_action(
                    room_id=room_id,
                    actor_player_id=user.id,  # Server-derived authenticated identity!
                    action_type_str=msg_type,
                    payload=payload,
                )
                if not success:
                    await manager.send_to_user(
                        room_id=room_id,
                        user_id=user.id,
                        message=WSServerMessage(type="ERROR", payload={"error": reason}),
                    )
                continue

            # 4. Handle Room Lifecycle and Management Actions
            async with AsyncSessionLocal() as db:
                current_room = await RoomService.get_room_by_id(db, room_id)
                if not current_room:
                    break

                if msg_type == "PING":
                    await manager.send_to_user(
                        room_id=room_id,
                        user_id=user.id,
                        message=WSServerMessage(type="PONG", payload={}),
                    )

                elif msg_type == "GET_ROOM_STATE":
                    serialized = RoomService.serialize_room(current_room)
                    await manager.send_to_user(
                        room_id=room_id,
                        user_id=user.id,
                        message=WSServerMessage(type="ROOM_STATE", payload={"room": serialized.model_dump()}),
                    )

                elif msg_type in ("READY", "NOT_READY"):
                    is_ready = (msg_type == "READY")
                    updated_room = await RoomService.set_player_ready(db, room_id, user.id, is_ready)
                    serialized = RoomService.serialize_room(updated_room)
                    await manager.broadcast_to_room(
                        room_id=room_id,
                        message=WSServerMessage(
                            type="ROOM_STATE",
                            payload={"room": serialized.model_dump(), "event": f"PLAYER_{msg_type}"},
                        ),
                    )

                elif msg_type == "START_GAME":
                    # Host-only authorization
                    if current_room.host_id != user.id:
                        await manager.send_to_user(
                            room_id=room_id,
                            user_id=user.id,
                            message=WSServerMessage(
                                type="ERROR",
                                payload={"error": "Only the room host can start the game"},
                            ),
                        )
                        continue

                    # Validation: minimum players
                    if len(current_room.players) < 2:
                        await manager.send_to_user(
                            room_id=room_id,
                            user_id=user.id,
                            message=WSServerMessage(
                                type="ERROR",
                                payload={"error": "At least 2 players are required to start."},
                            ),
                        )
                        continue

                    # Validation: all non-host players must be ready
                    non_host_unready = [
                        p.user.display_name for p in current_room.players
                        if p.user_id != current_room.host_id and not p.is_ready
                    ]
                    if non_host_unready:
                        await manager.send_to_user(
                            room_id=room_id,
                            user_id=user.id,
                            message=WSServerMessage(
                                type="ERROR",
                                payload={"error": f"Waiting for players to be ready: {', '.join(non_host_unready)}"},
                            ),
                        )
                        continue

                    # Lifecycle transition
                    current_room.status = RoomStatus.PLAYING
                    await db.commit()
                    updated_room = await RoomService.get_room_by_id(db, room_id)
                    serialized = RoomService.serialize_room(updated_room)

                    # Create GameSession in GameSessionManager if game type is registered
                    player_ids = [p.user_id for p in updated_room.players]
                    if GameRegistry.is_supported(current_room.selected_game):
                        game_session_manager.create_session(
                            room_id=room_id,
                            game_type=current_room.selected_game,
                            player_ids=player_ids,
                        )
                        await game_session_manager.broadcast_player_views(room_id)

                    await manager.broadcast_to_room(
                        room_id=room_id,
                        message=WSServerMessage(
                            type="GAME_STARTED",
                            payload={
                                "room": serialized.model_dump(),
                                "game_type": current_room.selected_game,
                                "message": f"Game session for '{current_room.selected_game}' initialized successfully.",
                            },
                        ),
                    )

                elif msg_type == "UPDATE_SETTINGS":
                    selected_game = payload.get("selected_game")
                    max_players = payload.get("max_players")
                    try:
                        updated_room = await RoomService.update_settings(
                            db=db,
                            room_id=room_id,
                            user_id=user.id,
                            selected_game=selected_game,
                            max_players=max_players,
                        )
                        serialized = RoomService.serialize_room(updated_room)
                        await manager.broadcast_to_room(
                            room_id=room_id,
                            message=WSServerMessage(
                                type="ROOM_STATE",
                                payload={"room": serialized.model_dump(), "event": "SETTINGS_UPDATED"},
                            ),
                        )
                    except (PermissionError, ValueError) as err:
                        await manager.send_to_user(
                            room_id=room_id,
                            user_id=user.id,
                            message=WSServerMessage(type="ERROR", payload={"error": str(err)}),
                        )

                else:
                    await manager.send_to_user(
                        room_id=room_id,
                        user_id=user.id,
                        message=WSServerMessage(
                            type="ERROR",
                            payload={"error": f"Unknown action or message type '{msg_type}'"},
                        ),
                    )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        async with AsyncSessionLocal() as db:
            await RoomService.set_player_connection(db, room_id, user.id, is_connected=False)
            refreshed = await RoomService.get_room_by_id(db, room_id)
            if refreshed:
                serialized = RoomService.serialize_room(refreshed)
                await manager.broadcast_to_room(
                    room_id=room_id,
                    message=WSServerMessage(
                        type="PLAYER_DISCONNECTED",
                        payload={"room": serialized.model_dump(), "user_id": user.id},
                    ),
                )
