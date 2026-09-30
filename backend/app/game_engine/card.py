"""Core Card definitions for the server-authoritative game engine."""
from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel, Field


class Suit(str, Enum):
    SPADES = "SPADES"
    HEARTS = "HEARTS"
    DIAMONDS = "DIAMONDS"
    CLUBS = "CLUBS"


class Rank(str, Enum):
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"


class Card(BaseModel):
    suit: Suit
    rank: Rank
    id: str = Field(description="Unique identifier for this specific card, e.g. 'SPADES_A'")

    @classmethod
    def create(cls, suit: Suit, rank: Rank) -> "Card":
        return cls(suit=suit, rank=rank, id=f"{suit.value}_{rank.value}")

    def to_dict(self) -> Dict[str, Any]:
        return {"suit": self.suit.value, "rank": self.rank.value, "id": self.id}

    def __str__(self) -> str:
        suit_symbols = {
            Suit.SPADES: "♠",
            Suit.HEARTS: "♥",
            Suit.DIAMONDS: "♦",
            Suit.CLUBS: "♣",
        }
        return f"{self.rank.value}{suit_symbols.get(self.suit, self.suit.value)}"

    def __repr__(self) -> str:
        return f"Card({self.suit.value}, {self.rank.value}, id='{self.id}')"
