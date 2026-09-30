"""Hearts domain state model extending BaseGameState."""
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from app.game_engine.card import Card
from app.game_engine.state import BaseGameState, GamePhase


class PassDirection(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    ACROSS = "ACROSS"
    NONE = "NONE"


class TrickCard(BaseModel):
    player_id: str
    card: Card


class HeartsRoundState(BaseModel):
    round_number: int = 1
    pass_direction: PassDirection = PassDirection.LEFT
    hearts_broken: bool = False
    is_first_trick: bool = True
    
    # passing state: player_id -> list of cards selected to pass
    passed_cards: Dict[str, List[Card]] = Field(default_factory=dict)
    has_passed: Dict[str, bool] = Field(default_factory=dict)
    
    # trick state
    current_trick: List[TrickCard] = Field(default_factory=list)
    completed_tricks_count: int = 0
    trick_lead_suit: Optional[str] = None
    trick_winner_id: Optional[str] = None

    # round scoring: player_id -> list of taken point cards
    taken_cards: Dict[str, List[Card]] = Field(default_factory=dict)
    round_points: Dict[str, int] = Field(default_factory=dict)


class HeartsGameState(BaseGameState):
    """Authoritative state for a complete Hearts match."""
    max_score_threshold: int = 100
    hearts_round: HeartsRoundState = Field(default_factory=HeartsRoundState)
