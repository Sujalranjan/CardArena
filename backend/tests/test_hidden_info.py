"""Tests proving that hidden information cannot leak to unauthorized players."""
import pytest
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.game import BaseGame
from app.game_engine.player import Player, PlayerPublicView
from app.game_engine.state import BaseGameState, GamePhase, PlayerGameView
from app.game_engine.action import GameAction, GameEvent


class MockTestGame(BaseGame):
    """Minimal test game implementation demonstrating authoritative hidden information protection."""

    def initialize_game(self, player_ids: list[str]) -> list[GameEvent]:
        for i, pid in enumerate(player_ids):
            self.state.add_player(
                Player(
                    id=pid,
                    seat=i,
                    display_name=f"Player_{pid}",
                    hand=[
                        Card.create(Suit.SPADES, Rank.ACE),
                        Card.create(Suit.HEARTS, Rank.KING),
                    ],
                )
            )
        self.state.phase = GamePhase.IN_PROGRESS
        return []

    def start_game(self) -> list[GameEvent]:
        return []

    def validate_action(self, action: GameAction) -> tuple[bool, str]:
        return True, ""

    def apply_action(self, action: GameAction) -> list[GameEvent]:
        return []

    def get_valid_actions(self, player_id: str) -> list[str]:
        return ["PLAY_CARD"]

    def next_turn(self) -> str:
        return self.state.player_order[0]

    def is_round_complete(self) -> bool:
        return False

    def is_game_complete(self) -> bool:
        return False

    def calculate_score(self) -> dict:
        return self.state.scores

    def get_player_view(self, player_id: str) -> PlayerGameView:
        public_players = [
            PlayerPublicView(
                id=p.id,
                seat=p.seat,
                display_name=p.display_name,
                is_connected=p.is_connected,
                card_count=p.card_count(),
            )
            for p in self.state.players.values()
        ]

        viewer = self.state.get_player(player_id)
        my_hand = viewer.hand if viewer else []

        return PlayerGameView(
            game_id=self.game_id,
            game_type=self.game_type,
            phase=self.state.phase,
            viewer_id=player_id,
            current_turn_player_id=self.state.current_turn_player_id,
            round_number=self.state.round_number,
            scores=self.state.scores,
            players=public_players,
            my_hand=my_hand,
            public_state={},
            valid_actions=self.get_valid_actions(player_id),
        )


def test_hidden_information_not_leaked_in_player_views():
    game = MockTestGame("game_123", "test_poker")
    game.initialize_game(["alice", "bob"])

    # Give Alice and Bob distinct secret cards
    alice = game.state.get_player("alice")
    bob = game.state.get_player("bob")

    alice.hand = [Card.create(Suit.SPADES, Rank.ACE), Card.create(Suit.CLUBS, Rank.TEN)]
    bob.hand = [Card.create(Suit.HEARTS, Rank.QUEEN), Card.create(Suit.DIAMONDS, Rank.SEVEN)]

    # Generate Alice's view
    alice_view = game.get_player_view("alice")
    alice_json = alice_view.model_dump_json()

    # 1. Alice sees her own cards
    assert "SPADES_A" in alice_json
    assert "CLUBS_10" in alice_json

    # 2. Bob's cards MUST NOT appear anywhere in Alice's serialized view
    assert "HEARTS_Q" not in alice_json
    assert "DIAMONDS_7" not in alice_json

    # 3. Alice can only see Bob's card count
    bob_public = next(p for p in alice_view.players if p.id == "bob")
    assert bob_public.card_count == 2
    assert not hasattr(bob_public, "hand")

    # Generate Bob's view
    bob_view = game.get_player_view("bob")
    bob_json = bob_view.model_dump_json()

    # 4. Bob sees his cards, Alice's are hidden
    assert "HEARTS_Q" in bob_json
    assert "DIAMONDS_7" in bob_json
    assert "SPADES_A" not in bob_json
    assert "CLUBS_10" not in bob_json
