"""Abstract Game interface defining contracts for all future card game implementations."""
from abc import ABC, abstractmethod
from typing import List, Tuple
from app.game_engine.action import GameAction, GameEvent
from app.game_engine.state import BaseGameState, PlayerGameView


class BaseGame(ABC):
    """
    Contract for all server-authoritative card games (Hearts, 28, Teen Patti, Bluff, etc.).
    Completely isolated from FastAPI, WebSockets, or HTTP frameworks.
    """

    def __init__(self, game_id: str, game_type: str):
        self.game_id = game_id
        self.game_type = game_type
        self.state: BaseGameState = BaseGameState(game_id=game_id, game_type=game_type)

    @abstractmethod
    def initialize_game(self, player_ids: List[str]) -> List[GameEvent]:
        """Set up players, initial state, and deck."""
        pass

    @abstractmethod
    def start_game(self) -> List[GameEvent]:
        """Start the match (shuffle, deal, advance phase)."""
        pass

    @abstractmethod
    def validate_action(self, action: GameAction) -> Tuple[bool, str]:
        """Returns (is_valid, error_reason). Does not mutate state."""
        pass

    @abstractmethod
    def apply_action(self, action: GameAction) -> List[GameEvent]:
        """
        Validates and applies the action authoritatively.
        Raises ValueError if action is invalid.
        Returns list of resulting GameEvents.
        """
        pass

    @abstractmethod
    def get_valid_actions(self, player_id: str) -> List[str]:
        """List of valid ActionType names player is currently permitted to take."""
        pass

    @abstractmethod
    def next_turn(self) -> str:
        """Determines and sets the next player ID whose turn it is."""
        pass

    @abstractmethod
    def is_round_complete(self) -> bool:
        """Checks if current round or trick has ended."""
        pass

    @abstractmethod
    def is_game_complete(self) -> bool:
        """Checks if match has concluded."""
        pass

    @abstractmethod
    def calculate_score(self) -> dict:
        """Calculates and returns latest scores."""
        pass

    @abstractmethod
    def get_player_view(self, player_id: str) -> PlayerGameView:
        """
        CRITICAL: Projections MUST mask other players' private hands.
        Only the player with player_id receives their own `my_hand`.
        """
        pass
