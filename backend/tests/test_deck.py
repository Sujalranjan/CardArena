"""Tests for cryptographically secure Deck and Card generation."""
import pytest
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.deck import Deck


def test_card_creation_and_attributes():
    card = Card.create(Suit.SPADES, Rank.ACE)
    assert card.suit == Suit.SPADES
    assert card.rank == Rank.ACE
    assert card.id == "SPADES_A"
    assert "A♠" in str(card)


def test_deck_initialization():
    deck = Deck()
    assert deck.remaining == 52
    unique_ids = {card.id for card in deck.cards}
    assert len(unique_ids) == 52


def test_deck_draw():
    deck = Deck()
    top_card = deck.draw()
    assert top_card is not None
    assert deck.remaining == 51

    # Drawing n cards
    drawn = deck.draw_n(5)
    assert len(drawn) == 5
    assert deck.remaining == 46


def test_deck_cryptographic_shuffle():
    deck1 = Deck()
    initial_order = [c.id for c in deck1.cards]

    deck1.shuffle()
    shuffled_order = [c.id for c in deck1.cards]

    assert len(shuffled_order) == 52
    assert set(shuffled_order) == set(initial_order)
    # The probability of standard 52-card deck remaining in exact same order after secure shuffle is 1/52!
    assert shuffled_order != initial_order


def test_deck_deal_round_robin():
    deck = Deck()
    deck.shuffle()
    hands = deck.deal(num_players=4, cards_per_player=13)

    assert len(hands) == 4
    for hand in hands:
        assert len(hand) == 13

    assert deck.remaining == 0

    all_dealt = [c.id for hand in hands for c in hand]
    assert len(set(all_dealt)) == 52


def test_deck_deal_insufficient_cards():
    deck = Deck()
    with pytest.raises(ValueError):
        deck.deal(num_players=4, cards_per_player=14)  # 56 cards > 52
