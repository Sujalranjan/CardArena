"""Dedicated GameSessionManager responsible for active games, state isolation, and player views."""
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Type
from pydantic import ValidationError
from app.core.logging import logger
from app.game_engine.action import (
    ActionType,
    BetPayload,
    CallPayload,
    ChallengePayload,
    DiscardCardPayload,
    DrawCardPayload,
    EndTurnPayload,
    EventType,
    FoldPayload,
    GameAction,
    GameEvent,
    PassCardPayload,
    PlayCardPayload,
    PlayCardsPayload,
    CallBluffPayload,
)
from app.game_engine.game import BaseGame
from app.game_engine.registry import GameRegistry
from app.game_engine.state import GamePhase, PlayerGameView
from app.websocket.connection_manager import manager
from app.schemas.schemas import WSServerMessage

# Events whose data is public by construction (never contains an unrevealed seed)
PUBLIC_FAIRNESS_EVENTS = {EventType.FAIRNESS_COMMITTED, EventType.FAIRNESS_REVEALED}


class ActiveGameSession:
    """Manages runtime state and event history for a single game session."""

    def __init__(self, room_id: str, game_instance: BaseGame):
        self.room_id = room_id
        self.game: BaseGame = game_instance
        self.event_history: List[GameEvent] = []
        self._sequence_counter: int = 0
        # Public fairness events not yet sent to the room
        self.pending_fairness_events: List[GameEvent] = []

    @property
    def next_sequence(self) -> int:
        self._sequence_counter += 1
        return self._sequence_counter

    def record_events(self, events: List[GameEvent]) -> None:
        for ev in events:
            if ev.sequence_number == 0:
                ev.sequence_number = self.next_sequence
            self.event_history.append(ev)
            if ev.type in PUBLIC_FAIRNESS_EVENTS:
                self.pending_fairness_events.append(ev)


class GameSessionManager:
    """
    Central authoritative manager for active game sessions.
    Completely isolates game instances from direct WebSocket/REST manipulation.

    Sessions live in process memory only. Active games are NOT persisted and are lost
    if the backend process restarts.
    """

    def __init__(self):
        # room_id -> ActiveGameSession
        self._sessions: Dict[str, ActiveGameSession] = {}

    def has_session(self, room_id: str) -> bool:
        return room_id in self._sessions

    def get_session(self, room_id: str) -> Optional[ActiveGameSession]:
        return self._sessions.get(room_id)

    def create_session(
        self,
        room_id: str,
        game_type: str,
        player_ids: List[str],
        display_names: Optional[Dict[str, str]] = None,
    ) -> ActiveGameSession:
        """
        Creates and initializes a new game session using GameRegistry.
        Refuses to replace an existing session for the same room.
        `display_names` must come from authoritative server/database state, never from clients.
        """
        if room_id in self._sessions:
            raise ValueError(f"A game session is already active for room {room_id}")

        game_class: Type[BaseGame] = GameRegistry.get(game_type)
        game_instance = game_class(game_id=room_id, game_type=game_type)

        init_events = game_instance.initialize_game(player_ids)

        # Platform identity (not a game rule): apply authoritative room display names
        for pid, name in (display_names or {}).items():
            player = game_instance.state.players.get(pid)
            if player and name:
                player.display_name = name

        session = ActiveGameSession(room_id=room_id, game_instance=game_instance)
        session.record_events(init_events)
        self._sessions[room_id] = session

        logger.info(f"GameSession created: room={room_id}, type={game_type}, players={player_ids}")
        return session

    def validate_typed_action_payload(self, action_type: ActionType, raw_payload: dict) -> Tuple[bool, str]:
        """Strictly validates payload structure against typed Pydantic models."""
        payload_map = {
            ActionType.PLAY_CARD: PlayCardPayload,
            ActionType.DRAW_CARD: DrawCardPayload,
            ActionType.DISCARD_CARD: DiscardCardPayload,
            ActionType.PASS_CARD: PassCardPayload,
            ActionType.BET: BetPayload,
            ActionType.CALL: CallPayload,
            ActionType.FOLD: FoldPayload,
            ActionType.CHALLENGE: ChallengePayload,
            ActionType.END_TURN: EndTurnPayload,
            ActionType.PLAY_CARDS: PlayCardsPayload,
            ActionType.CALL_BLUFF: CallBluffPayload,
        }

        model_cls = payload_map.get(action_type)
        if not model_cls:
            # Action type has no specific payload requirements (e.g. READY, JOIN_GAME)
            return True, ""

        try:
            model_cls.model_validate(raw_payload)
            return True, ""
        except ValidationError as ve:
            return False, f"Invalid payload for {action_type.value}: {ve.errors()[0]['msg']}"

    async def dispatch_action(
        self,
        room_id: str,
        actor_player_id: str,
        action_type_str: str,
        payload: dict,
        on_game_over: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Tuple[bool, str]:
        """
        Processes a player action with strict security invariants:
        1. ActionType must be known.
        2. Payload must match typed schema.
        3. Game session must exist.
        4. Player must be in the game session.
        5. Action must be validated by BaseGame rules.
        6. State mutation produces GameEvents and broadcasts player-specific views.
        """
        # 1. Action type check
        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            return False, f"Unknown action type '{action_type_str}'"

        # 2. Schema check
        valid_payload, payload_err = self.validate_typed_action_payload(action_type, payload)
        if not valid_payload:
            return False, payload_err

        # 3. Session existence check
        session = self.get_session(room_id)
        if not session:
            return False, "No active game session found for this room"

        # 4. Player membership check
        if actor_player_id not in session.game.state.players:
            return False, f"Player '{actor_player_id}' is not a participant in this game"

        # 5. Build authoritative action (actor_player_id derived server-side!)
        action = GameAction(
            type=action_type,
            player_id=actor_player_id,
            payload=payload,
        )

        # 6. Validate with game rules
        is_valid, reason = session.game.validate_action(action)
        if not is_valid:
            return False, reason or "Action rejected by game rules"

        # 7. Apply action authoritatively
        try:
            events = session.game.apply_action(action)
            session.record_events(events)
        except Exception as e:
            logger.error(f"Error applying action in room {room_id}: {e}")
            return False, f"Game engine error: {str(e)}"

        # Game over: no round is active any more, so every outstanding seed is revealable
        if session.game.is_game_complete():
            session.record_events(session.game.reveal_all_fairness())

        # 8. Broadcast player-specific state views (Zero Hidden Info leakage)
        await self.broadcast_player_views(room_id)

        # 9. Clean up session if game has completed. The final GAME_OVER views were
        # broadcast above; removing the session rejects any further game actions.
        if session.game.is_game_complete():
            session.game.state.phase = GamePhase.GAME_OVER
            logger.info(f"Game session in room {room_id} has concluded.")
            self.remove_session(room_id)
            if on_game_over:
                await on_game_over(room_id)

        return True, "Action applied successfully"

    def build_player_view(self, session: ActiveGameSession, player_id: str) -> PlayerGameView:
        """
        Builds a player's sanitized view. Connection status is derived from the live
        ConnectionManager (the authoritative source), not from the game's own Player records.
        """
        player_view = session.game.get_player_view(player_id)
        for public_player in player_view.players:
            public_player.is_connected = manager.is_connected(session.room_id, public_player.id)
        player_view.fairness = session.game.fairness.public_records()
        return player_view

    async def broadcast_player_views(self, room_id: str) -> None:
        """
        Broadcasts individualized player views. Each connected player receives
        ONLY their authorized view with private cards masked.
        Pending fairness commitments/reveals are sent first, so a round's commitment
        reaches clients before any view containing that round's dealt cards.
        """
        session = self.get_session(room_id)
        if not session:
            return

        pending, session.pending_fairness_events = session.pending_fairness_events, []
        for event in pending:
            await manager.broadcast_to_room(
                room_id=room_id,
                message=WSServerMessage(
                    type=event.type.value,
                    payload={**event.data, "sequence_number": event.sequence_number},
                ),
            )

        for player_id in session.game.state.players:
            player_view: PlayerGameView = self.build_player_view(session, player_id)
            await manager.send_to_user(
                room_id=room_id,
                user_id=player_id,
                message=WSServerMessage(
                    type="GAME_STATE",
                    payload={"game_view": player_view.model_dump()},
                ),
            )

    async def send_reconnect_view(self, room_id: str, user_id: str) -> None:
        """Sends sanitized game view upon player reconnection."""
        session = self.get_session(room_id)
        if not session:
            return
        if user_id in session.game.state.players:
            player_view = self.build_player_view(session, user_id)
            await manager.send_to_user(
                room_id=room_id,
                user_id=user_id,
                message=WSServerMessage(
                    type="GAME_STATE",
                    payload={"game_view": player_view.model_dump()},
                ),
            )

    def remove_session(self, room_id: str) -> None:
        if room_id in self._sessions:
            del self._sessions[room_id]
            logger.info(f"GameSession for room {room_id} removed.")


game_session_manager = GameSessionManager()
