"""Comprehensive Hearts Hardening, Full 13-trick Match, Passing Cycle, Multi-round and Moon Tests."""
import pytest
from app.game_engine.action import ActionType, EventType, GameAction
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.deck import Deck
from app.game_engine.state import GamePhase
from app.games.hearts import HeartsGame
from app.games.hearts_state import PassDirection


def test_passing_direction_four_round_cycle():
    game = HeartsGame(game_id="room_pass_cycle")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    # Round 1: Left
    assert game.state.hearts_round.round_number == 1
    assert game.state.hearts_round.pass_direction == PassDirection.LEFT
    assert game._get_pass_target("p1", PassDirection.LEFT) == "p2"
    assert game._get_pass_target("p4", PassDirection.LEFT) == "p1"

    # Start Round 2: Right
    game.start_round(2)
    assert game.state.hearts_round.round_number == 2
    assert game.state.hearts_round.pass_direction == PassDirection.RIGHT
    assert game._get_pass_target("p1", PassDirection.RIGHT) == "p4"
    assert game._get_pass_target("p2", PassDirection.RIGHT) == "p1"

    # Start Round 3: Across
    game.start_round(3)
    assert game.state.hearts_round.round_number == 3
    assert game.state.hearts_round.pass_direction == PassDirection.ACROSS
    assert game._get_pass_target("p1", PassDirection.ACROSS) == "p3"
    assert game._get_pass_target("p2", PassDirection.ACROSS) == "p4"

    # Start Round 4: Hold (None)
    game.start_round(4)
    assert game.state.hearts_round.round_number == 4
    assert game.state.hearts_round.pass_direction == PassDirection.NONE
    assert game.state.phase == GamePhase.IN_PROGRESS  # No passing phase

    # Pass attempt on hold round must be rejected
    invalid_pass = GameAction(
        type=ActionType.PASS_CARD,
        player_id="p1",
        payload={"card_ids": [c.id for c in game.state.players["p1"].hand[:3]]},
    )
    is_valid, reason = game.validate_action(invalid_pass)
    assert not is_valid
    assert "hold rounds" in reason or "Passing phase is not active" in reason

    # Start Round 5: Left again
    game.start_round(5)
    assert game.state.hearts_round.pass_direction == PassDirection.LEFT


def test_malicious_pass_payload_cannot_redirect_destination():
    game = HeartsGame(game_id="room_pass_sec")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    # In Round 1, p1 must pass to p2 (LEFT)
    # p1 attempts to pass to p4 by providing target_player_id
    p1_cards = [c.id for c in game.state.players["p1"].hand[:3]]
    spoofed_pass = GameAction(
        type=ActionType.PASS_CARD,
        player_id="p1",
        payload={"card_ids": p1_cards, "target_player_id": "p4"},
    )
    is_valid, _ = game.validate_action(spoofed_pass)
    assert is_valid
    game.apply_action(spoofed_pass)

    # Other 3 players pass
    for pid in ["p2", "p3", "p4"]:
        c_ids = [c.id for c in game.state.players[pid].hand[:3]]
        game.apply_action(GameAction(type=ActionType.PASS_CARD, player_id=pid, payload={"card_ids": c_ids}))

    # Verify that p1's cards went to p2 (authoritative LEFT), NOT p4
    p2_hand_ids = {c.id for c in game.state.players["p2"].hand}
    p4_hand_ids = {c.id for c in game.state.players["p4"].hand}
    for cid in p1_cards:
        assert cid in p2_hand_ids
        assert cid not in p4_hand_ids


def test_rejection_of_invalid_card_counts_for_passing():
    game = HeartsGame(game_id="room_pass_counts")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    p1_hand = [c.id for c in game.state.players["p1"].hand]

    # 0 cards
    action_0 = GameAction(type=ActionType.PASS_CARD, player_id="p1", payload={"card_ids": []})
    is_val, _ = game.validate_action(action_0)
    assert not is_val

    # 1 card
    action_1 = GameAction(type=ActionType.PASS_CARD, player_id="p1", payload={"card_ids": [p1_hand[0]]})
    is_val, _ = game.validate_action(action_1)
    assert not is_val

    # 2 cards
    action_2 = GameAction(type=ActionType.PASS_CARD, player_id="p1", payload={"card_ids": p1_hand[:2]})
    is_val, _ = game.validate_action(action_2)
    assert not is_val

    # 4 cards
    action_4 = GameAction(type=ActionType.PASS_CARD, player_id="p1", payload={"card_ids": p1_hand[:4]})
    is_val, reason = game.validate_action(action_4)
    assert not is_val
    assert "requires exactly 3 cards" in reason

    # Duplicate card in 3 selection
    action_dup = GameAction(
        type=ActionType.PASS_CARD,
        player_id="p1",
        payload={"card_ids": [p1_hand[0], p1_hand[0], p1_hand[1]]},
    )
    is_val_dup, reason_dup = game.validate_action(action_dup)
    assert not is_val_dup
    assert "Duplicate cards" in reason_dup


def test_complete_deterministic_13_trick_round():
    """
    Sets up a full 52-card deterministic deal across 4 players and plays all 13 tricks.
    Verifies trick events, lead suit adherence, points calculation, and round transition.
    """
    game = HeartsGame(game_id="room_13_tricks")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    # Round 4 setup (Hold / None) so we skip passing and immediately play
    game.start_round(4)
    assert game.state.phase == GamePhase.IN_PROGRESS

    # Construct deterministic 13-card hands:
    # p1 gets all Clubs (2 to Ace) -> holds 2♣
    # p2 gets all Diamonds (2 to Ace)
    # p3 gets all Spades (2 to Ace) -> holds Q♠
    # p4 gets all Hearts (2 to Ace) -> holds all 13 Hearts
    ranks_in_order = [
        Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX,
        Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.JACK,
        Rank.QUEEN, Rank.KING, Rank.ACE
    ]

    game.state.players["p1"].hand = [Card.create(Suit.CLUBS, r) for r in ranks_in_order]
    game.state.players["p2"].hand = [Card.create(Suit.DIAMONDS, r) for r in ranks_in_order]
    game.state.players["p3"].hand = [Card.create(Suit.SPADES, r) for r in ranks_in_order]
    game.state.players["p4"].hand = [Card.create(Suit.HEARTS, r) for r in ranks_in_order]

    all_cards = set()
    for pid in players:
        for c in game.state.players[pid].hand:
            all_cards.add(c.id)
    assert len(all_cards) == 52

    # p1 holds 2♣, leads trick 1
    game.state.current_turn_player_id = "p1"

    for t_idx in range(13):
        leader = game.state.current_turn_player_id
        lead_card = game.state.players[leader].hand[0].id
        events = game.apply_action(
            GameAction(type=ActionType.PLAY_CARD, player_id=leader, payload={"card_id": lead_card})
        )

        for _ in range(3):
            next_p = game.state.current_turn_player_id
            valid_card = None
            for card in game.state.players[next_p].hand:
                test_act = GameAction(type=ActionType.PLAY_CARD, player_id=next_p, payload={"card_id": card.id})
                is_val, _ = game.validate_action(test_act)
                if is_val:
                    valid_card = card.id
                    break

            assert valid_card is not None, f"No legal card for {next_p} on trick {t_idx + 1}"
            trick_evs = game.apply_action(
                GameAction(type=ActionType.PLAY_CARD, player_id=next_p, payload={"card_id": valid_card})
            )
            events.extend(trick_evs)

        trick_completed_ev = next((e for e in events if e.type == EventType.TRICK_COMPLETED), None)
        assert trick_completed_ev is not None

    # After 13 tricks, completed_tricks_count is 13 and round finishes
    assert game.state.hearts_round.round_number == 5
    # p1 captured all 13 tricks (leading every trick with Clubs, while others had no clubs)
    # Total points captured: all 13 Hearts + Queen of Spades = 26 pts -> Shooting the Moon!
    # Shooter (p1) gets 0, all other 3 players get +26 points
    assert game.state.scores["p1"] == 0
    assert game.state.scores["p2"] == 26
    assert game.state.scores["p3"] == 26
    assert game.state.scores["p4"] == 26
    assert sum(game.state.scores.values()) == 78


def test_game_over_threshold_and_rejection_of_post_game_actions():
    game = HeartsGame(game_id="room_game_over")
    players = ["p1", "p2", "p3", "p4"]
    game.initialize_game(players)

    # Set p1 score to 105 (> 100 threshold)
    game.state.scores["p1"] = 105
    game.state.scores["p2"] = 20
    game.state.scores["p3"] = 40
    game.state.scores["p4"] = 15

    game.state.hearts_round.completed_tricks_count = 13
    game._resolve_round_end()

    assert game.state.phase == GamePhase.GAME_OVER
    assert game.is_game_complete() is True

    # Post-game actions must be strictly rejected
    pass_act = GameAction(
        type=ActionType.PASS_CARD,
        player_id="p1",
        payload={"card_ids": ["c1", "c2", "c3"]},
    )
    is_val, reason = game.validate_action(pass_act)
    assert not is_val
    assert "concluded" in reason
