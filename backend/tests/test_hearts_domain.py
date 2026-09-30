"""Comprehensive Hearts Domain and Rules Test Suite."""
import pytest
from app.game_engine.action import ActionType, GameAction
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.registry import GameRegistry
from app.game_engine.state import GamePhase
from app.games.hearts import HeartsGame
from app.games.hearts_state import PassDirection


def test_hearts_game_registration():
    assert GameRegistry.is_supported("hearts")
    game_cls = GameRegistry.get("hearts")
    assert game_cls == HeartsGame


def test_hearts_initialization_and_dealing():
    game = HeartsGame(game_id="room_h_1")
    player_ids = ["p1", "p2", "p3", "p4"]
    events = game.initialize_game(player_ids)

    assert len(events) >= 2
    assert game.state.phase == GamePhase.STARTING  # Round 1 is Pass Left
    assert game.state.hearts_round.pass_direction == PassDirection.LEFT

    # Verify exactly 13 cards dealt per player
    all_dealt_ids = set()
    for pid in player_ids:
        hand = game.state.players[pid].hand
        assert len(hand) == 13
        for card in hand:
            all_dealt_ids.add(card.id)

    # 52 unique cards, no duplicates, no missing cards
    assert len(all_dealt_ids) == 52


def test_hearts_passing_phase():
    game = HeartsGame(game_id="room_h_2")
    player_ids = ["p1", "p2", "p3", "p4"]
    game.initialize_game(player_ids)

    # p1 passes 3 cards to p2 (Left)
    p1_hand_ids = [c.id for c in game.state.players["p1"].hand[:3]]
    pass_action_1 = GameAction(
        type=ActionType.PASS_CARD,
        player_id="p1",
        payload={"card_ids": p1_hand_ids},
    )
    is_valid, _ = game.validate_action(pass_action_1)
    assert is_valid
    game.apply_action(pass_action_1)

    assert game.state.hearts_round.has_passed["p1"] is True
    # Still in STARTING until all 4 players pass
    assert game.state.phase == GamePhase.STARTING

    # Reject duplicate pass by p1
    is_valid_dup, reason_dup = game.validate_action(pass_action_1)
    assert not is_valid_dup
    assert "already submitted" in reason_dup

    # Other 3 players pass
    for pid in ["p2", "p3", "p4"]:
        hand_ids = [c.id for c in game.state.players[pid].hand[:3]]
        game.apply_action(
            GameAction(
                type=ActionType.PASS_CARD,
                player_id=pid,
                payload={"card_ids": hand_ids},
            )
        )

    # After all 4 pass: phase transitions to IN_PROGRESS
    assert game.state.phase == GamePhase.IN_PROGRESS
    # Each player still has exactly 13 cards after transfer
    for pid in player_ids:
        assert len(game.state.players[pid].hand) == 13

    # Turn is assigned to player holding 2 of Clubs
    starter_id = game.state.current_turn_player_id
    starter_hand = game.state.players[starter_id].hand
    assert any(c.suit == Suit.CLUBS and c.rank == Rank.TWO for c in starter_hand)


def test_hearts_first_trick_two_of_clubs_requirement():
    game = HeartsGame(game_id="room_h_3")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    # Fast-forward pass phase
    for pid in players:
        p_ids = [c.id for c in game.state.players[pid].hand[:3]]
        game.apply_action(GameAction(type=ActionType.PASS_CARD, player_id=pid, payload={"card_ids": p_ids}))

    starter_id = game.state.current_turn_player_id
    starter_player = game.state.players[starter_id]

    # Try to play a card other than 2♣ on opening lead
    non_two_club = next(c for c in starter_player.hand if not (c.suit == Suit.CLUBS and c.rank == Rank.TWO))
    bad_action = GameAction(type=ActionType.PLAY_CARD, player_id=starter_id, payload={"card_id": non_two_club.id})

    is_valid, reason = game.validate_action(bad_action)
    assert not is_valid
    assert "2 of Clubs" in reason

    # Play actual 2♣ -> succeeds
    good_action = GameAction(type=ActionType.PLAY_CARD, player_id=starter_id, payload={"card_id": "CLUBS_2"})
    is_valid, _ = game.validate_action(good_action)
    assert is_valid
    game.apply_action(good_action)
    assert len(game.state.hearts_round.current_trick) == 1


def test_hearts_follow_suit_and_hearts_breaking():
    game = HeartsGame(game_id="room_h_4")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    # Set custom controlled hands for deterministic testing
    game.state.players["p1"].hand = [
        Card.create(Suit.CLUBS, Rank.TWO),
        Card.create(Suit.HEARTS, Rank.ACE),
    ]
    game.state.players["p2"].hand = [
        Card.create(Suit.CLUBS, Rank.FIVE),
        Card.create(Suit.DIAMONDS, Rank.KING),
    ]
    game.state.players["p3"].hand = [
        Card.create(Suit.DIAMONDS, Rank.ACE),
        Card.create(Suit.HEARTS, Rank.TEN),
    ]
    game.state.players["p4"].hand = [
        Card.create(Suit.CLUBS, Rank.ACE),
        Card.create(Suit.SPADES, Rank.ACE),
    ]
    game.state.phase = GamePhase.IN_PROGRESS
    game.state.hearts_round.is_first_trick = False  # Test standard non-first-trick rules
    game.state.hearts_round.hearts_broken = False

    # p1 leads Clubs 2
    game.state.current_turn_player_id = "p1"
    game.apply_action(GameAction(type=ActionType.PLAY_CARD, player_id="p1", payload={"card_id": "CLUBS_2"}))

    # p2 has Clubs 5, attempts to play Diamonds K -> must be rejected by follow suit
    assert game.state.current_turn_player_id == "p2"
    bad_follow = GameAction(type=ActionType.PLAY_CARD, player_id="p2", payload={"card_id": "DIAMONDS_K"})
    is_valid, reason = game.validate_action(bad_follow)
    assert not is_valid
    assert "Must follow suit" in reason

    # p2 plays Clubs 5 -> valid
    game.apply_action(GameAction(type=ActionType.PLAY_CARD, player_id="p2", payload={"card_id": "CLUBS_5"}))

    # p3 has NO Clubs, can play Hearts 10 (which breaks hearts!)
    assert game.state.current_turn_player_id == "p3"
    game.apply_action(GameAction(type=ActionType.PLAY_CARD, player_id="p3", payload={"card_id": "HEARTS_10"}))
    assert game.state.hearts_round.hearts_broken is True

    # p4 plays Clubs A (wins trick)
    game.apply_action(GameAction(type=ActionType.PLAY_CARD, player_id="p4", payload={"card_id": "CLUBS_A"}))

    # p4 should have won trick and received the 1 point from Hearts 10
    assert game.state.hearts_round.trick_winner_id == "p4"
    assert game.state.hearts_round.round_points["p4"] == 1
    # p4 leads next trick
    assert game.state.current_turn_player_id == "p4"


def test_hearts_first_trick_point_card_restriction():
    game = HeartsGame(game_id="room_h_5")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    game.state.players["p1"].hand = [Card.create(Suit.CLUBS, Rank.TWO)]
    game.state.players["p2"].hand = [Card.create(Suit.HEARTS, Rank.FOUR), Card.create(Suit.DIAMONDS, Rank.SEVEN)]
    game.state.phase = GamePhase.IN_PROGRESS
    game.state.hearts_round.is_first_trick = True

    # p1 plays 2♣
    game.state.current_turn_player_id = "p1"
    game.apply_action(GameAction(type=ActionType.PLAY_CARD, player_id="p1", payload={"card_id": "CLUBS_2"}))

    # p2 has no clubs, but has Diamonds 7 (non-point) and Hearts 4 (point card)
    # Attempting Hearts 4 on trick 1 must be rejected
    game.state.current_turn_player_id = "p2"
    illegal_heart = GameAction(type=ActionType.PLAY_CARD, player_id="p2", payload={"card_id": "HEARTS_4"})
    is_valid, reason = game.validate_action(illegal_heart)
    assert not is_valid
    assert "Point cards" in reason

    # Playing Diamonds 7 is legal
    legal_diamond = GameAction(type=ActionType.PLAY_CARD, player_id="p2", payload={"card_id": "DIAMONDS_7"})
    is_valid, _ = game.validate_action(legal_diamond)
    assert is_valid


def test_hearts_shooting_the_moon():
    game = HeartsGame(game_id="room_h_6")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    # Set up round where p1 took all 26 points
    game.state.hearts_round.round_points = {"p1": 26, "p2": 0, "p3": 0, "p4": 0}
    game.state.hearts_round.completed_tricks_count = 13

    events = game._resolve_round_end()

    # In shoot the moon: shooter gets 0, all others get 26
    assert game.state.scores["p1"] == 0
    assert game.state.scores["p2"] == 26
    assert game.state.scores["p3"] == 26
    assert game.state.scores["p4"] == 26
