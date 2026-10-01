"""Bluff domain state extending BaseGameState."""
from typing import List, Optional
from pydantic import BaseModel, Field
from app.game_engine.card import Card, Rank
from app.game_engine.state import BaseGameState


class BluffPlay(BaseModel):
    """A face-down play. `cards` is private server state until a challenge reveals it."""
    player_id: str
    cards: List[Card]
    declared_rank: Rank

    @property
    def declared_quantity(self) -> int:
        return len(self.cards)


class BluffChallengeResult(BaseModel):
    """Outcome of a CALL_BLUFF. Public once resolved (the challenged cards are revealed)."""
    challenger_id: str
    challenged_player_id: str
    declared_rank: Rank
    declared_quantity: int
    revealed_cards: List[Card]
    declaration_truthful: bool
    pile_recipient_id: str
    pile_size: int


class BluffGameState(BaseGameState):
    """Authoritative state for a Bluff match (one deal; the game ends when a hand empties)."""
    starting_player_id: Optional[str] = None
    # Every face-down card currently in the central pile (private)
    pile: List[Card] = Field(default_factory=list)
    # The only play that may be challenged: the immediately previous one (private cards)
    last_play: Optional[BluffPlay] = None
    last_challenge: Optional[BluffChallengeResult] = None
    play_count: int = 0
    winner_id: Optional[str] = None
