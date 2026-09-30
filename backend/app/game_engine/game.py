"""Abstract Game interface defining contracts for all future card game implementations."""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from app.game_engine.action import EventType, GameAction, GameEvent
from app.game_engine.card import Card
from app.game_engine.deck import Deck
from app.game_engine.fairness import DECK_DEFINITIONS, STANDARD_52, FairnessLedger
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
        # Private server-side commit/reveal records; never part of the serialized state
        self.fairness = FairnessLedger(game_id)

    # ---------------- Provably fair shuffling (shared by all games) ----------------
    def create_committed_deck(
        self,
        round_number: int,
        canonical_cards: Optional[List[Card]] = None,
        deck_definition: str = STANDARD_52,
    ) -> Tuple[Deck, GameEvent]:
        """
        Commits to a fresh secret seed for this round, then builds the deck from the
        deterministic shuffle of `canonical_cards` (default: the documented standard-52 order).
        Returns the deck and the FAIRNESS_COMMITTED event, which must precede any dealing.
        """
        canonical = list(canonical_cards) if canonical_cards is not None else Deck().cards
        canonical_ids = [c.id for c in canonical]
        cards_by_id = {c.id: c for c in canonical}
        if len(cards_by_id) != len(canonical):
            raise ValueError("Canonical deck card IDs must be unique")
        documented = DECK_DEFINITIONS.get(deck_definition)
        if documented is not None and documented != canonical_ids:
            raise ValueError(f"Canonical deck does not match documented definition '{deck_definition}'")

        fair_round = self.fairness.commit(round_number, canonical_ids, deck_definition)
        commit_event = GameEvent(
            game_id=self.game_id,
            type=EventType.FAIRNESS_COMMITTED,
            data={"fairness": fair_round.public_record()},
        )
        deck = Deck(cards=[cards_by_id[cid] for cid in fair_round.deck_order()])
        return deck, commit_event

    def reveal_fairness(self, round_number: int) -> Optional[GameEvent]:
        """Reveals a round's seed. Call only once that round's hidden information is final."""
        fair_round = self.fairness.get(round_number)
        if not fair_round or fair_round.revealed:
            return None
        fair_round.reveal()
        return GameEvent(
            game_id=self.game_id,
            type=EventType.FAIRNESS_REVEALED,
            data={"fairness": fair_round.public_record()},
        )

    def reveal_all_fairness(self) -> List[GameEvent]:
        """Reveals every outstanding round. Used when the game is over."""
        events = []
        for fair_round in self.fairness.unrevealed():
            event = self.reveal_fairness(fair_round.round_number)
            if event:
                events.append(event)
        return events

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
