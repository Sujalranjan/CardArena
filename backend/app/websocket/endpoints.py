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
    Authentication token is strictly verified from query params ?token=....
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

        # If a game session is active, send every player their sanitized view so the
        # reconnecting user gets their hand back and peers see the updated connection status
        await game_session_manager.broadcast_player_views(room_id)

    async def finish_room_game(finished_room_id: str) -> None:
        """Moves the room out of PLAYING once its game session has concluded."""
        async with AsyncSessionLocal() as finish_db:
            finished_room = await RoomService.set_room_status(
                finish_db, finished_room_id, RoomStatus.FINISHED
            )
            if finished_room:
                await manager.broadcast_to_room(
                    room_id=finished_room_id,
                    message=WSServerMessage(
                        type="ROOM_STATE",
                        payload={
                            "room": RoomService.serialize_room(finished_room).model_dump(),
                            "event": "GAME_OVER",
                        },
                    ),
                )

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
                ActionType.PLAY_CARDS.value,
                ActionType.CALL_BLUFF.value,
            }

            if msg_type in in_game_action_types:
                success, reason = await game_session_manager.dispatch_action(
                    room_id=room_id,
                    actor_player_id=user.id,  # Server-derived authenticated identity!
                    action_type_str=msg_type,
                    payload=payload,
                    on_game_over=finish_room_game,
                )
                if not success:
                    await manager.send_to_user(
                        room_id=room_id,
                        user_id=user.id,
                        message=WSServerMessage(type="ERROR", payload={"error": reason}),
                    )
                continue

            # 4. Handle Room Lifecycle and Management Actions
            try:
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

                        # Lifecycle guard: a room can only be started from WAITING, and an
                        # existing game session must never be replaced or discarded
                        if (
                            current_room.status != RoomStatus.WAITING
                            or game_session_manager.has_session(room_id)
                        ):
                            await manager.send_to_user(
                                room_id=room_id,
                                user_id=user.id,
                                message=WSServerMessage(
                                    type="ERROR",
                                    payload={"error": "Game cannot be started: room is not waiting for players."},
                                ),
                            )
                            continue

                        # Validation: Hearts specifically requires exactly 4 players
                        if current_room.selected_game == "hearts":
                            if len(current_room.players) != 4:
                                await manager.send_to_user(
                                    room_id=room_id,
                                    user_id=user.id,
                                    message=WSServerMessage(
                                        type="ERROR",
                                        payload={"error": f"Hearts requires exactly 4 players to start (currently {len(current_room.players)})."},
                                    ),
                                )
                                continue
                        elif len(current_room.players) < 2:
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

                        # Create GameSession if game type is registered. Done before any await
                        # after the guard above so concurrent START_GAMEs cannot both pass it.
                        player_ids = [p.user_id for p in current_room.players]
                        display_names = {
                            p.user_id: p.user.display_name for p in current_room.players if p.user
                        }
                        session_created = False
                        if GameRegistry.is_supported(current_room.selected_game):
                            game_session_manager.create_session(
                                room_id=room_id,
                                game_type=current_room.selected_game,
                                player_ids=player_ids,
                                display_names=display_names,
                            )
                            session_created = True

                        # Lifecycle transition
                        try:
                            current_room.status = RoomStatus.PLAYING
                            await db.commit()
                        except Exception:
                            if session_created:
                                game_session_manager.remove_session(room_id)
                            raise
                        updated_room = await RoomService.get_room_by_id(db, room_id)
                        serialized = RoomService.serialize_room(updated_room)

                        if session_created:
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
            except Exception as e:
                logger.error(f"Unexpected error processing message {msg_type} from {user.id}: {e}")
                await manager.send_to_user(
                    room_id=room_id,
                    user_id=user.id,
                    message=WSServerMessage(
                        type="ERROR",
                        payload={"error": "An internal error occurred while processing action"},
                    ),
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket connection uncaught exception for user {user.id}: {e}")
    finally:
        await handle_socket_closed(websocket, room_id, user.id)


async def handle_socket_closed(websocket: WebSocket, room_id: str, user_id: str) -> None:
    """
    Marks the player disconnected once their socket closes, for every exit path.
    Skipped when this socket was already replaced by a newer connection for the same
    user (e.g. page refresh), so the stale socket cannot mark a live player offline.
    """
    was_registered = manager.disconnect(websocket) is not None
    if not was_registered or manager.is_connected(room_id, user_id):
        return

    try:
        async with AsyncSessionLocal() as db:
            await RoomService.set_player_connection(db, room_id, user_id, is_connected=False)
            refreshed = await RoomService.get_room_by_id(db, room_id)
            if refreshed:
                serialized = RoomService.serialize_room(refreshed)
                await manager.broadcast_to_room(
                    room_id=room_id,
                    message=WSServerMessage(
                        type="PLAYER_DISCONNECTED",
                        payload={"room": serialized.model_dump(), "user_id": user_id},
                    ),
                )
        # Remaining players' game views reflect the disconnect (hands stay private)
        await game_session_manager.broadcast_player_views(room_id)
    except Exception as e:
        logger.error(f"Failed to record disconnect for user {user_id} in room {room_id}: {e}")
