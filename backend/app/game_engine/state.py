"""Authoritative GameState, GamePhase lifecycle, and Player Game View models."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.game_engine.card import Card
from app.game_engine.player import Player, PlayerPublicView


class GamePhase(str, Enum):
    WAITING = "WAITING"
    STARTING = "STARTING"
    IN_PROGRESS = "IN_PROGRESS"
    ROUND_END = "ROUND_END"
    GAME_OVER = "GAME_OVER"


class BaseGameState(BaseModel):
    """
    Authoritative server-side game state.
    Contains undealt cards, deck order, and all private hands.
    MUST NEVER BE SENT DIRECTLY OR WHOLE TO ANY NETWORK CLIENT.
    """
    game_id: str
    game_type: str
    phase: GamePhase = GamePhase.WAITING
    players: Dict[str, Player] = Field(default_factory=dict)
    player_order: List[str] = Field(default_factory=list)
    current_turn_player_id: Optional[str] = None
    round_number: int = 1
    scores: Dict[str, int] = Field(default_factory=dict)
    custom_state: Dict[str, Any] = Field(default_factory=dict)

    def get_player(self, player_id: str) -> Optional[Player]:
        return self.players.get(player_id)

    def add_player(self, player: Player) -> None:
        self.players[player.id] = player
        if player.id not in self.player_order:
            self.player_order.append(player.id)
        if player.id not in self.scores:
            self.scores[player.id] = 0

    def remove_player(self, player_id: str) -> None:
        if player_id in self.players:
            del self.players[player_id]
        if player_id in self.player_order:
            self.player_order.remove(player_id)


class PlayerGameView(BaseModel):
    """
    Player-specific projection with hidden information stripped.
    This is what is serialized and sent to the client via REST/WebSocket.
    """
    game_id: str
    game_type: str
    phase: GamePhase
    viewer_id: str
    current_turn_player_id: Optional[str]
    round_number: int
    scores: Dict[str, int]
    # Public views of players at table: card count and connection status ONLY
    players: List[PlayerPublicView]
    # Viewer's own private hand ONLY
    my_hand: List[Card]
    # Public table state (trump suit, current trick, discard count, etc.)
    public_state: Dict[str, Any] = Field(default_factory=dict)
    valid_actions: List[str] = Field(default_factory=list)
