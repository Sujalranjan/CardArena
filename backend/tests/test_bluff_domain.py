"""Bluff engine rules, validation, hidden information and fairness integration."""
import json
import pytest
from app.game_engine import game as base_game_module
from app.game_engine.action import ActionType, EventType, GameAction
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.deck import Deck
from app.game_engine.fairness import DECK_DEFINITIONS, STANDARD_52, deterministic_shuffle
from app.game_engine.registry import GameRegistry
from app.game_engine.state import GamePhase
from app.games import bluff as bluff_module
from app.games.bluff import MAX_CARDS_PER_PLAY, MAX_PLAYERS, MIN_PLAYERS, BluffGame
from app.services.game_session_manager import GameSessionManager

ALL_CARD_IDS = set(DECK_DEFINITIONS[STANDARD_52])


def _players(n):
    return [f"bluff_p{i}" for i in range(n)]


def _new_game(n=4, game_id="bluff_room"):
    game = BluffGame(game_id=game_id)
    events = game.initialize_game(_players(n))
    return game, events


def _cards(*specs):
    return [Card.create(suit, rank) for suit, rank in specs]


def _rig(game, hands, turn):
    """Replace dealt hands with known cards for deterministic rule tests."""
    for pid, hand in hands.items():
        game.state.players[pid].hand = list(hand)
    game.state.pile = []
    game.state.last_play = None
    game.state.last_challenge = None
    game.state.current_turn_player_id = turn


def _play(game, pid, cards, rank, **extra):
    return GameAction(
        type=ActionType.PLAY_CARDS,
        player_id=pid,
        payload={"card_ids": [c.id for c in cards], "declared_rank": rank.value, **extra},
    )


def _call(game, pid, **extra):
    return GameAction(type=ActionType.CALL_BLUFF, player_id=pid, payload=dict(extra))


# ---------------- Registration / initialization (1-9) ----------------
def test_bluff_is_registered():
    assert GameRegistry.get("bluff") is BluffGame


@pytest.mark.parametrize("n", list(range(MIN_PLAYERS, MAX_PLAYERS + 1)))
def test_initialization_deals_every_card_exactly_once(n):
    game, events = _new_game(n)
    hands = {pid: [c.id for c in game.state.players[pid].hand] for pid in game.state.player_order}

    all_dealt = [cid for hand in hands.values() for cid in hand]
    assert len(all_dealt) == len(ALL_CARD_IDS)
    assert set(all_dealt) == ALL_CARD_IDS
    sizes = [len(h) for h in hands.values()]
    assert max(sizes) - min(sizes) <= 1
    assert game.state.phase == GamePhase.IN_PROGRESS
    assert game.state.current_turn_player_id in game.state.player_order
    assert game.state.starting_player_id == game.state.current_turn_player_id

    # Each hand is exactly the seat's share of the committed deck order (round-robin from the end)
    order = game.fairness.get(1).deck_order()
    for seat, pid in enumerate(game.state.player_order):
        expected = {order[len(order) - 1 - (k * n + seat)] for k in range(len(hands[pid]))}
        assert set(hands[pid]) == expected


@pytest.mark.parametrize("bad", [[], _players(1), _players(MAX_PLAYERS + 1)])
def test_invalid_player_counts_rejected(bad):
    with pytest.raises(ValueError):
        BluffGame(game_id="bad").initialize_game(bad)


def test_duplicate_player_ids_rejected():
    with pytest.raises(ValueError):
        BluffGame(game_id="dup").initialize_game(["same", "same"])


def test_starting_player_is_chosen_by_server_csprng(monkeypatch):
    n = 5
    calls = []

    def fake_randbelow(k):
        calls.append(k)
        return k - 1

    monkeypatch.setattr(bluff_module.secrets, "randbelow", fake_randbelow)
    game, events = _new_game(n)
    assert calls == [n]
    assert game.state.current_turn_player_id == game.state.player_order[n - 1]
    started = next(e for e in events if e.type == EventType.GAME_STARTED)
    assert started.data["starting_player_id"] == game.state.player_order[n - 1]


def test_starting_player_varies_across_games():
    starters = set()
    for _ in range(60):
        game, _ = _new_game(4)
        starters.add(game.state.player_order.index(game.state.current_turn_player_id))
    assert len(starters) > 1


# ---------------- Fairness (32, 33, 34) ----------------
def test_commitment_before_deal_and_existing_shuffle_used(monkeypatch):
    game = BluffGame(game_id="fair_bluff")
    real_deal_all = Deck.deal_all
    observed = []

    def checking_deal_all(self, num_players):
        observed.append(game.fairness.get(1) is not None)
        return real_deal_all(self, num_players)

    def forbidden_shuffle(self):
        raise AssertionError("Bluff must not use the unverifiable Deck.shuffle()")

    monkeypatch.setattr(Deck, "deal_all", checking_deal_all)
    monkeypatch.setattr(Deck, "shuffle", forbidden_shuffle)
    events = game.initialize_game(_players(4))
    assert observed == [True]

    types = [e.type for e in events]
    assert types.index(EventType.FAIRNESS_COMMITTED) < types.index(EventType.GAME_STARTED)
    fair_round = game.fairness.get(1)
    seed = fair_round._server_seed
    assert fair_round.deck_order() == deterministic_shuffle(DECK_DEFINITIONS[STANDARD_52], seed)
    assert events[types.index(EventType.FAIRNESS_COMMITTED)].data["fairness"]["server_seed"] is None


def test_seed_hidden_in_views_until_game_over():
    gsm = GameSessionManager()
    session = gsm.create_session("bluff_seed_room", "bluff", _players(3))
    seed_hex = session.game.fairness.get(1)._server_seed.hex()
    for pid in session.game.state.player_order:
        view = gsm.build_player_view(session, pid)
        assert seed_hex not in view.model_dump_json()
        assert view.fairness[0]["revealed"] is False


# ---------------- Play validation (10-18) ----------------
@pytest.fixture
def rigged():
    game, _ = _new_game(4)
    p = game.state.player_order
    hands = {
        p[0]: _cards((Suit.SPADES, Rank.QUEEN), (Suit.HEARTS, Rank.QUEEN), (Suit.CLUBS, Rank.SEVEN),
                     (Suit.DIAMONDS, Rank.TWO), (Suit.CLUBS, Rank.TWO), (Suit.SPADES, Rank.ACE)),
        p[1]: _cards((Suit.DIAMONDS, Rank.QUEEN), (Suit.CLUBS, Rank.KING), (Suit.HEARTS, Rank.NINE)),
        p[2]: _cards((Suit.SPADES, Rank.FIVE), (Suit.HEARTS, Rank.FIVE), (Suit.DIAMONDS, Rank.FIVE)),
        p[3]: _cards((Suit.CLUBS, Rank.QUEEN), (Suit.DIAMONDS, Rank.ACE)),
    }
    _rig(game, hands, turn=p[0])
    return game, p, hands


def test_valid_play_and_declaration(rigged):
    game, p, hands = rigged
    played = hands[p[0]][:3]
    ok, reason = game.validate_action(_play(game, p[0], played, Rank.QUEEN, declared_quantity=3))
    assert ok, reason
    events = game.apply_action(_play(game, p[0], played, Rank.QUEEN))
    assert game.state.last_play.declared_rank == Rank.QUEEN
    assert game.state.last_play.declared_quantity == len(played)
    assert len(game.state.pile) == len(played)
    assert game.state.players[p[0]].card_count() == len(hands[p[0]]) - len(played)
    assert game.state.current_turn_player_id == p[1]
    played_event = next(e for e in events if e.type == EventType.CARDS_PLAYED)
    assert played_event.data["declared_quantity"] == len(played)
    assert all(c.id not in json.dumps(played_event.data) for c in played)


@pytest.mark.parametrize("case", ["not_owned", "unknown_id", "too_many", "duplicate", "bad_rank",
                                  "quantity_mismatch", "out_of_turn"])
def test_invalid_plays_rejected(rigged, case):
    game, p, hands = rigged
    own = hands[p[0]]
    if case == "not_owned":
        action = _play(game, p[0], [hands[p[1]][0]], Rank.QUEEN)
    elif case == "unknown_id":
        action = GameAction(type=ActionType.PLAY_CARDS, player_id=p[0],
                            payload={"card_ids": [own[0].id + "_X"], "declared_rank": Rank.QUEEN.value})
    elif case == "too_many":
        action = _play(game, p[0], own[: MAX_CARDS_PER_PLAY + 1], Rank.QUEEN)
    elif case == "duplicate":
        action = GameAction(type=ActionType.PLAY_CARDS, player_id=p[0],
                            payload={"card_ids": [own[0].id, own[0].id], "declared_rank": Rank.QUEEN.value})
    elif case == "bad_rank":
        action = GameAction(type=ActionType.PLAY_CARDS, player_id=p[0],
                            payload={"card_ids": [own[0].id], "declared_rank": "Z"})
    elif case == "quantity_mismatch":
        action = _play(game, p[0], own[:2], Rank.QUEEN, declared_quantity=3)
    else:
        action = _play(game, p[1], hands[p[1]][:1], Rank.QUEEN)

    ok, reason = game.validate_action(action)
    assert not ok and reason
    with pytest.raises(ValueError):
        game.apply_action(action)
    # Nothing changed
    assert [c.id for c in game.state.players[p[0]].hand] == [c.id for c in own]
    assert game.state.pile == [] and game.state.current_turn_player_id == p[0]


@pytest.mark.asyncio
async def test_pipeline_rejects_empty_forged_and_state_injecting_payloads():
    gsm = GameSessionManager()
    session = gsm.create_session("bluff_pipeline", "bluff", _players(4))
    game = session.game
    turn = game.state.current_turn_player_id
    other = next(pid for pid in game.state.player_order if pid != turn)
    card_id = game.state.players[turn].hand[0].id
    hand_before = {pid: [c.id for c in pl.hand] for pid, pl in game.state.players.items()}

    attempts = [
        (turn, "PLAY_CARDS", {"card_ids": [], "declared_rank": Rank.ACE.value}),                    # zero cards
        (turn, "PLAY_CARDS", {"card_ids": [card_id], "declared_rank": Rank.ACE.value, "pile": []}),   # inject state
        (turn, "PLAY_CARDS", {"card_ids": [card_id], "declared_rank": Rank.ACE.value, "player_id": other}),
        (turn, "PLAY_CARDS", {"card_ids": [card_id], "declared_rank": Rank.ACE.value, "next_player_id": other}),
        (turn, "CALL_BLUFF", {}),                                                                       # nothing to challenge
        ("not_a_member", "PLAY_CARDS", {"card_ids": [card_id], "declared_rank": Rank.ACE.value}),
        (other, "PLAY_CARDS", {"card_ids": [card_id], "declared_rank": Rank.ACE.value}),              # other's card, out of turn
    ]
    for actor, action_type, payload in attempts:
        ok, reason = await gsm.dispatch_action("bluff_pipeline", actor, action_type, payload)
        assert not ok, (action_type, payload)
        assert reason

    assert {pid: [c.id for c in pl.hand] for pid, pl in game.state.players.items()} == hand_before
    assert game.state.pile == [] and game.state.play_count == 0
    assert game.state.current_turn_player_id == turn


# ---------------- Hidden information (19, 20) ----------------
def test_played_cards_hidden_from_everyone_but_counts_public(rigged):
    game, p, hands = rigged
    played = hands[p[0]][:2]
    game.apply_action(_play(game, p[0], played, Rank.KING))

    for pid in p:
        view = game.get_player_view(pid)
        text = view.model_dump_json()
        assert all(c.id not in text for c in played)
        assert view.public_state["pile_count"] == len(played)
        assert view.public_state["last_play"] == {
            "player_id": p[0], "declared_rank": Rank.KING.value, "declared_quantity": len(played)
        }
        counts = {pl.id: pl.card_count for pl in view.players}
        assert counts[p[0]] == len(hands[p[0]]) - len(played)
        for other in p:
            if other != pid:
                assert all(c.id not in text for c in game.state.players[other].hand)
        assert {c.id for c in view.my_hand} == {c.id for c in game.state.players[pid].hand}


# ---------------- Challenges (21-27) ----------------
def test_false_declaration_declarer_takes_whole_pile(rigged):
    game, p, hands = rigged
    first = hands[p[0]][:3]            # Q, Q, 7 declared as Queens -> false
    game.apply_action(_play(game, p[0], first, Rank.QUEEN))
    second = hands[p[1]][:1]
    game.apply_action(_play(game, p[1], second, Rank.KING))   # K declared King, unchallenged by p2
    third = hands[p[2]][:2]            # 5, 5 declared as Sevens -> false
    game.apply_action(_play(game, p[2], third, Rank.SEVEN))
    pile_ids = {c.id for c in first + second + third}
    p2_before = game.state.players[p[2]].card_count()

    assert ActionType.CALL_BLUFF.value in game.get_valid_actions(p[3])
    events = game.apply_action(_call(game, p[3]))

    result = game.state.last_challenge
    assert result.declaration_truthful is False
    assert result.pile_recipient_id == p[2]
    assert result.challenger_id == p[3] and result.challenged_player_id == p[2]
    assert result.pile_size == len(pile_ids)
    assert {c.id for c in result.revealed_cards} == {c.id for c in third}
    assert game.state.players[p[2]].card_count() == p2_before + len(pile_ids)
    assert pile_ids <= {c.id for c in game.state.players[p[2]].hand}
    assert game.state.pile == [] and game.state.last_play is None
    assert game.state.current_turn_player_id == p[3]  # player after the challenged player
    resolved = next(e for e in events if e.type == EventType.CHALLENGE_RESOLVED)
    assert resolved.data["pile_recipient_id"] == p[2]


def test_truthful_declaration_challenger_takes_pile(rigged):
    game, p, hands = rigged
    queens = hands[p[0]][:2]           # Q, Q declared as Queens -> truthful
    game.apply_action(_play(game, p[0], queens, Rank.QUEEN))
    p1_before = game.state.players[p[1]].card_count()

    game.apply_action(_call(game, p[1]))
    result = game.state.last_challenge
    assert result.declaration_truthful is True
    assert result.pile_recipient_id == p[1]
    assert game.state.players[p[1]].card_count() == p1_before + len(queens)
    assert game.state.players[p[0]].card_count() == len(hands[p[0]]) - len(queens)
    assert game.state.current_turn_player_id == p[1]

    # Revealed cards are now public to every player
    for pid in p:
        challenge = game.get_player_view(pid).public_state["last_challenge"]
        assert {c["id"] for c in challenge["revealed_cards"]} == {c.id for c in queens}
        assert challenge["declaration_truthful"] is True


def test_challenge_unavailable_cases(rigged):
    game, p, hands = rigged
    # Nothing played yet
    assert not game.validate_action(_call(game, p[0]))[0]
    game.apply_action(_play(game, p[0], hands[p[0]][:1], Rank.QUEEN))
    # Only the current player may challenge
    assert not game.validate_action(_call(game, p[2]))[0]
    assert ActionType.CALL_BLUFF.value not in game.get_valid_actions(p[2])
    # Client cannot supply truth/result data
    ok, reason = game.validate_action(_call(game, p[1], declaration_truthful=True))
    assert not ok and "CALL_BLUFF" in reason
    # After a resolved challenge nothing is challengeable
    game.apply_action(_call(game, p[1]))
    assert not game.validate_action(_call(game, game.state.current_turn_player_id))[0]
    # A later play replaces the challengeable play: only the latest one counts
    current = game.state.current_turn_player_id
    card = game.state.players[current].hand[0]
    game.apply_action(_play(game, current, [card], card.rank))
    assert game.state.last_play.player_id == current


def test_two_player_turns_alternate_and_challenge_returns_turn():
    game, _ = _new_game(2)
    a, b = game.state.player_order
    _rig(game, {a: _cards((Suit.SPADES, Rank.TWO), (Suit.HEARTS, Rank.THREE)),
                b: _cards((Suit.CLUBS, Rank.FOUR), (Suit.DIAMONDS, Rank.FIVE))}, turn=a)
    game.apply_action(_play(game, a, game.state.players[a].hand[:1], Rank.ACE))
    assert game.state.current_turn_player_id == b
    game.apply_action(_call(game, b))
    assert game.state.last_challenge.pile_recipient_id == a
    assert game.state.current_turn_player_id == b


# ---------------- Win / game over (28, 29) ----------------
@pytest.mark.asyncio
async def test_emptying_hand_wins_and_game_over_rejects_actions():
    gsm = GameSessionManager()
    session = gsm.create_session("bluff_win_room", "bluff", _players(3))
    game = session.game
    p = game.state.player_order
    _rig(game, {p[0]: _cards((Suit.SPADES, Rank.TWO)),
                p[1]: _cards((Suit.CLUBS, Rank.FOUR)),
                p[2]: _cards((Suit.DIAMONDS, Rank.FIVE))}, turn=p[0])
    finished = []

    async def on_game_over(room_id):
        finished.append(room_id)

    ok, reason = await gsm.dispatch_action(
        "bluff_win_room", p[0], "PLAY_CARDS",
        {"card_ids": [game.state.players[p[0]].hand[0].id], "declared_rank": Rank.KING.value},
        on_game_over=on_game_over,
    )
    assert ok, reason
    assert game.state.winner_id == p[0]
    assert game.state.phase == GamePhase.GAME_OVER
    assert game.get_valid_actions(p[1]) == []
    assert finished == ["bluff_win_room"]
    assert not gsm.has_session("bluff_win_room")
    assert game.fairness.get(1).revealed  # seed revealed only now

    assert not game.validate_action(_call(game, p[1]))[0]
    ok, reason = await gsm.dispatch_action("bluff_win_room", p[1], "CALL_BLUFF", {})
    assert not ok
