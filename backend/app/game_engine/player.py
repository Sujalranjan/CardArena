"""Player representation in the generic game engine."""
from typing import List, Optional
from pydantic import BaseModel, Field
from app.game_engine.card import Card


class Player(BaseModel):
    id: str = Field(description="Unique player/user ID")
    seat: int = Field(description="Assigned seat index around the table")
    display_name: str
    is_connected: bool = True
    hand: List[Card] = Field(default_factory=list, description="Private server-side hand")

    def card_count(self) -> int:
        return len(self.hand)

    def remove_card(self, card_id: str) -> Optional[Card]:
        for i, card in enumerate(self.hand):
            if card.id == card_id:
                return self.hand.pop(i)
        return None

    def add_card(self, card: Card) -> None:
        self.hand.append(card)


class PlayerPublicView(BaseModel):
    """Sanitized view of a player visible to other players (hidden information protected)."""
    id: str
    seat: int
    display_name: str
    is_connected: bool
    card_count: int
