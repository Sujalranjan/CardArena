"""Cryptographically secure Deck implementation for server-authoritative games."""
import secrets
from typing import List, Optional
from app.game_engine.card import Card, Rank, Suit


class Deck:
    """
    Standard 52-card or custom deck using cryptographically secure randomness (secrets module).
    Never uses pseudo-random Math.random() or random.random().
    """

    def __init__(self, cards: Optional[List[Card]] = None, auto_populate: bool = True):
        if cards is not None:
            self._cards: List[Card] = list(cards)
        elif auto_populate:
            self._cards = self._generate_standard_deck()
        else:
            self._cards = []

    @staticmethod
    def _generate_standard_deck() -> List[Card]:
        cards: List[Card] = []
        for suit in Suit:
            for rank in Rank:
                cards.append(Card.create(suit=suit, rank=rank))
        return cards

    @property
    def remaining(self) -> int:
        return len(self._cards)

    @property
    def cards(self) -> List[Card]:
        """Returns a copy of remaining cards for internal inspection."""
        return list(self._cards)

    def shuffle(self) -> None:
        """
        Fisher-Yates shuffle utilizing `secrets.randbelow` for cryptographic unpredictability.
        """
        n = len(self._cards)
        for i in range(n - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            self._cards[i], self._cards[j] = self._cards[j], self._cards[i]

    def draw(self) -> Optional[Card]:
        """Draws one card from the top of the deck, or returns None if empty."""
        if not self._cards:
            return None
        return self._cards.pop()

    def draw_n(self, n: int) -> List[Card]:
        """Draws up to n cards from the deck."""
        drawn: List[Card] = []
        for _ in range(n):
            card = self.draw()
            if card is None:
                break
            drawn.append(card)
        return drawn

    def deal(self, num_players: int, cards_per_player: int) -> List[List[Card]]:
        """
        Deals cards sequentially to num_players in round-robin fashion.
        Raises ValueError if deck does not have enough cards.
        """
        total_required = num_players * cards_per_player
        if self.remaining < total_required:
            raise ValueError(
                f"Cannot deal {total_required} cards with only {self.remaining} remaining."
            )

        hands: List[List[Card]] = [[] for _ in range(num_players)]
        for _ in range(cards_per_player):
            for p_idx in range(num_players):
                card = self.draw()
                if card:
                    hands[p_idx].append(card)
        return hands

    def deal_all(self, num_players: int) -> List[List[Card]]:
        """
        Deals the entire deck round-robin with the same order as deal() (draw from the end,
        seat 0 first). When the deck does not divide evenly, lower seats get one extra card.
        """
        if num_players < 1:
            raise ValueError("num_players must be at least 1")
        hands: List[List[Card]] = [[] for _ in range(num_players)]
        p_idx = 0
        while self._cards:
            hands[p_idx].append(self._cards.pop())
            p_idx = (p_idx + 1) % num_players
        return hands
