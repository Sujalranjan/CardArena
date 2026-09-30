"""Provably fair commit/reveal shuffling: algorithm, engine/Hearts integration and WebSocket exposure."""
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from app.game_engine import fairness as fairness_module
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.deck import Deck
from app.game_engine.action import EventType
from app.game_engine.fairness import (
    ALGORITHM,
    DECK_DEFINITIONS,
    STANDARD_52,
    FairnessLedger,
    canonical_deck_hash,
    compute_commitment,
    deterministic_shuffle,
    generate_server_seed,
    verify_commitment,
    verify_public_record,
    verify_round,
)
from app.game_engine.state import GamePhase
from app.games.hearts import HeartsGame
from app.services.game_session_manager import GameSessionManager, game_session_manager
from tests.test_platform_lifecycle import _connect, _recv_until, ws_env  # noqa: F401 (fixture)

CANONICAL = DECK_DEFINITIONS[STANDARD_52]
BACKEND_DIR = Path(__file__).resolve().parents[1]

# Known-answer vector: seed = bytes 0x00..0x1f
KAT_SEED = bytes(range(32))
KAT_COMMITMENT = "630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd"
KAT_FIRST_8 = ["CLUBS_A", "DIAMONDS_6", "CLUBS_J", "HEARTS_7", "DIAMONDS_5", "CLUBS_4", "DIAMONDS_2", "SPADES_9"]
KAT_ORDER_SHA256 = "649756d3b54bf3a2de59ed540569a6357145d601c7c1cf95a4c1c94d67e0fa87"


def _independent_shuffle(canonical, seed: bytes):
    """Re-implementation written from the documented spec only (not the module's code)."""
    stream, counter = b"", 0

    def take(n):
        nonlocal stream, counter
        while len(stream) < n:
            stream += hmac.new(seed, b"cardarena-shuffle-v1" + counter.to_bytes(8, "big"), hashlib.sha256).digest()
            counter += 1
        out, stream = stream[:n], stream[n:]
        return out

    deck = list(canonical)
    for i in range(len(deck) - 1, 0, -1):
        n = i + 1
        while True:
            x = int.from_bytes(take(4), "big")
            if x < 2**32 - (2**32 % n):
                break
        j = x % n
        deck[i], deck[j] = deck[j], deck[i]
    return deck


def _seed_of(game, round_number):
    return game.fairness.get(round_number)._server_seed.hex()


# ---------------- A: server seed ----------------
def test_server_seed_uses_csprng_with_256_bits(monkeypatch):
    calls = []
    real = fairness_module.secrets.token_bytes

    def spy(n):
        calls.append(n)
        return real(n)

    monkeypatch.setattr(fairness_module.secrets, "token_bytes", spy)
    seed = generate_server_seed()
    assert calls == [32]
    assert isinstance(seed, bytes) and len(seed) == 32

    seeds = [generate_server_seed() for _ in range(1000)]
    assert len(set(seeds)) == 1000
    ones = sum(bin(int.from_bytes(s, "big")).count("1") for s in seeds)
    assert 0.48 < ones / (1000 * 256) < 0.52


# ---------------- B, P, Q: commitment ----------------
def test_commitment_is_deterministic_sha256_of_seed():
    assert compute_commitment(KAT_SEED) == KAT_COMMITMENT
    assert compute_commitment(KAT_SEED) == hashlib.sha256(KAT_SEED).hexdigest()
    seed = generate_server_seed()
    assert compute_commitment(seed) == compute_commitment(seed)
    assert verify_commitment(seed.hex(), compute_commitment(seed))


def test_tampered_seed_or_commitment_fails_verification():
    seed = generate_server_seed()
    commitment = compute_commitment(seed)
    tampered_seed = bytearray(seed)
    tampered_seed[0] ^= 0x01
    assert not verify_commitment(bytes(tampered_seed).hex(), commitment)
    tampered_commitment = ("0" if commitment[0] != "0" else "1") + commitment[1:]
    assert not verify_commitment(seed.hex(), tampered_commitment)
    assert not verify_commitment("not-hex", commitment)
    assert not verify_round(bytes(tampered_seed).hex(), commitment, CANONICAL).ok
    assert not verify_round(seed.hex(), tampered_commitment, CANONICAL).ok


# ---------------- C, D, E, F, G, O: deterministic shuffle ----------------
def test_standard_52_definition_matches_engine_deck():
    assert CANONICAL == [c.id for c in Deck().cards]
    assert len(CANONICAL) == 52 and len(set(CANONICAL)) == 52


def test_same_seed_same_deck_and_known_answer_vector():
    order = deterministic_shuffle(CANONICAL, KAT_SEED)
    assert order == deterministic_shuffle(CANONICAL, KAT_SEED)
    assert order[:8] == KAT_FIRST_8
    assert canonical_deck_hash(order) == KAT_ORDER_SHA256


def test_different_seeds_produce_different_orders():
    orders = {tuple(deterministic_shuffle(CANONICAL, generate_server_seed())) for _ in range(200)}
    assert len(orders) == 200


def test_every_deck_preserves_exact_card_set_without_duplicates():
    for _ in range(200):
        order = deterministic_shuffle(CANONICAL, generate_server_seed())
        assert len(order) == 52
        assert len(set(order)) == 52
        assert sorted(order) == sorted(CANONICAL)


def test_independent_reimplementation_reproduces_deck():
    for seed in [KAT_SEED] + [generate_server_seed() for _ in range(25)]:
        assert _independent_shuffle(CANONICAL, seed) == deterministic_shuffle(CANONICAL, seed)


@pytest.mark.parametrize("hash_seed", ["0", "12345", "random"])
def test_shuffle_is_identical_across_processes(hash_seed):
    code = (
        "from app.game_engine.fairness import deterministic_shuffle, DECK_DEFINITIONS;"
        f"print(','.join(deterministic_shuffle(DECK_DEFINITIONS['standard-52'], bytes(range(32)))))"
    )
    env = dict(os.environ, PYTHONHASHSEED=hash_seed)
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out.split(",") == deterministic_shuffle(CANONICAL, KAT_SEED)


def test_standalone_verifier_cli(tmp_path):
    ledger = FairnessLedger("g")
    fair_round = ledger.commit(1, CANONICAL)
    fair_round.reveal()
    record_file = tmp_path / "record.json"
    record_file.write_text(json.dumps(fair_round.public_record()), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(BACKEND_DIR / "app" / "game_engine" / "fairness.py"), str(record_file)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["deck_order"] == fair_round.deck_order()


# ---------------- Public record / reveal model ----------------
def test_public_record_hides_seed_until_reveal_and_verifies_after():
    ledger = FairnessLedger("game_x")
    fair_round = ledger.commit(1, CANONICAL)
    seed_hex = fair_round._server_seed.hex()

    before = fair_round.public_record()
    assert before["server_seed"] is None and before["revealed"] is False
    assert seed_hex not in json.dumps(before)
    assert not verify_public_record(before).ok
    for card_id in CANONICAL:  # no card IDs in the public record
        assert f'"{card_id}"' not in json.dumps(before)

    fair_round.reveal()
    after = fair_round.public_record()
    assert after["server_seed"] == seed_hex
    assert after["commitment"] == before["commitment"]
    result = verify_public_record(after)
    assert result.ok and result.deck_order == fair_round.deck_order()

    tampered = dict(after, server_seed=("0" if seed_hex[0] != "0" else "1") + seed_hex[1:])
    assert not verify_public_record(tampered).ok
    assert not verify_public_record(dict(after, commitment="0" * 64)).ok
    assert not verify_public_record(dict(after, canonical_deck_sha256="0" * 64)).ok
    assert not verify_public_record(dict(after, algorithm="other")).ok
    assert not verify_round(seed_hex, after["commitment"], CANONICAL, expected_deck_order=CANONICAL).ok


def test_ledger_refuses_recommit_and_engine_rejects_mislabelled_deck():
    ledger = FairnessLedger("g")
    ledger.commit(1, CANONICAL)
    with pytest.raises(ValueError):
        ledger.commit(1, CANONICAL)

    game = HeartsGame(game_id="g_mislabel")
    reversed_cards = list(reversed(Deck().cards))
    with pytest.raises(ValueError):
        game.create_committed_deck(1, canonical_cards=reversed_cards)  # claims standard-52
    deck, event = game.create_committed_deck(1, canonical_cards=reversed_cards, deck_definition="custom-test")
    assert event.data["fairness"]["deck_definition"] == "custom-test"
    assert sorted(c.id for c in deck.cards) == sorted(CANONICAL)


def test_reveal_all_fairness_reveals_outstanding_rounds():
    game = HeartsGame(game_id="g_reveal_all")
    game.create_committed_deck(1)
    game.create_committed_deck(2)
    events = game.reveal_all_fairness()
    assert [e.type for e in events] == [EventType.FAIRNESS_REVEALED] * 2
    assert all(r["revealed"] and r["server_seed"] for r in game.fairness.public_records())
    assert game.reveal_all_fairness() == []


# ---------------- H + Hearts integration ----------------
def test_commitment_created_before_deal_and_hearts_uses_committed_deck(monkeypatch):
    game = HeartsGame(game_id="room_fair_h")
    real_deal = Deck.deal
    observed = []

    def checking_deal(self, num_players, cards_per_player):
        observed.append(game.fairness.get(1) is not None)
        return real_deal(self, num_players, cards_per_player)

    monkeypatch.setattr(Deck, "deal", checking_deal)
    events = game.initialize_game(["p1", "p2", "p3", "p4"])
    assert observed == [True]

    types = [e.type for e in events]
    assert types.index(EventType.FAIRNESS_COMMITTED) < types.index(EventType.GAME_STARTED)
    commit_record = events[types.index(EventType.FAIRNESS_COMMITTED)].data["fairness"]
    assert commit_record["server_seed"] is None

    # Dealt hands are exactly what the committed seed derives (Deck.deal pops from the end, round-robin)
    order = deterministic_shuffle(CANONICAL, bytes.fromhex(_seed_of(game, 1)))
    for seat, pid in enumerate(game.state.player_order):
        expected = {order[-(1 + k * 4 + seat)] for k in range(13)}
        assert {c.id for c in game.state.players[pid].hand} == expected


@pytest.mark.asyncio
async def test_session_events_order_commit_before_deal_and_reveal_at_game_over():
    gsm = GameSessionManager()
    session = gsm.create_session("room_fair_seq", "hearts", ["p1", "p2", "p3", "p4"])
    types = [e.type for e in session.event_history]
    seqs = [e.sequence_number for e in session.event_history]
    assert seqs == sorted(seqs)
    assert types.index(EventType.FAIRNESS_COMMITTED) < types.index(EventType.GAME_STARTED)
    assert session.pending_fairness_events[0].type == EventType.FAIRNESS_COMMITTED

    # Views expose commitment only
    view = gsm.build_player_view(session, "p1")
    assert view.fairness[0]["commitment"] == session.game.fairness.get(1).commitment
    assert _seed_of(session.game, 1) not in view.model_dump_json()


def _rig_final_trick(session, player_ids, leader_score):
    state = session.game.state
    hr = state.hearts_round
    state.phase = GamePhase.IN_PROGRESS
    hr.is_first_trick = False
    hr.hearts_broken = True
    hr.completed_tricks_count = 12
    hr.current_trick = []
    hr.trick_lead_suit = None
    hr.round_points = {pid: 0 for pid in player_ids}
    hr.taken_cards = {pid: [] for pid in player_ids}
    final_cards = [
        Card.create(Suit.CLUBS, Rank.ACE),
        Card.create(Suit.CLUBS, Rank.TWO),
        Card.create(Suit.CLUBS, Rank.THREE),
        Card.create(Suit.HEARTS, Rank.FIVE),
    ]
    for pid, card in zip(player_ids, final_cards):
        state.players[pid].hand = [card]
    state.scores = {pid: 0 for pid in player_ids}
    state.scores[player_ids[0]] = leader_score
    state.current_turn_player_id = player_ids[0]
    return final_cards


def _collect_until(ws, msg_type, pred=None, limit=100):
    """Returns (all raw texts received, matching message)."""
    texts = []
    for _ in range(limit):
        text = ws.receive_text()
        texts.append(text)
        msg = json.loads(text)
        if msg["type"] == msg_type and (pred is None or pred(msg)):
            return texts, msg
    raise AssertionError(f"Did not receive {msg_type}")


# ---------------- H, I, K, L over the real WebSocket endpoint ----------------
def test_ws_commitment_published_first_seed_hidden_and_client_cannot_override(ws_env):
    room_id = ws_env["room_id"]
    client_seed = "ab" * 32

    with _connect(ws_env, 0) as host_ws:
        _recv_until(host_ws, "ROOM_STATE")
        # K. Client-supplied randomness/deck/commitment on START_GAME is ignored
        host_ws.send_json({
            "type": "START_GAME",
            "payload": {
                "server_seed": client_seed,
                "seed": client_seed,
                "commitment": compute_commitment(bytes.fromhex(client_seed)),
                "deck": list(CANONICAL),
            },
        })
        texts, _ = _collect_until(host_ws, "GAME_STARTED")
        types = [json.loads(t)["type"] for t in texts]

        session = game_session_manager.get_session(room_id)
        fair_round = session.game.fairness.get(1)
        seed_hex = _seed_of(session.game, 1)

        # H. Commitment reaches the client before any game view containing dealt cards
        assert types.index("FAIRNESS_COMMITTED") < types.index("GAME_STATE")
        commit_msg = json.loads(texts[types.index("FAIRNESS_COMMITTED")])
        assert commit_msg["payload"]["fairness"]["commitment"] == fair_round.commitment
        assert commit_msg["payload"]["sequence_number"] > 0

        # I. Raw seed absent from everything serialized before reveal
        assert all(seed_hex not in t for t in texts)
        assert fair_round.commitment == compute_commitment(bytes.fromhex(seed_hex))
        assert fair_round.commitment != compute_commitment(bytes.fromhex(client_seed))
        assert seed_hex != client_seed
        assert fair_round.deck_order() != list(CANONICAL)

        # L. Extra seed/deck fields on game actions are ignored; no message can set them
        p1 = session.game.state.player_order[0]
        pass_ids = [c.id for c in session.game.state.players[p1].hand[:3]]
        host_ws.send_json({
            "type": "PASS_CARD",
            "payload": {"card_ids": pass_ids, "deck": list(CANONICAL), "server_seed": client_seed},
        })
        texts, _ = _collect_until(host_ws, "GAME_STATE", lambda m: m["payload"]["game_view"]["public_state"]["has_passed"][p1])
        assert session.game.fairness.get(1) is fair_round
        assert _seed_of(session.game, 1) == seed_hex
        assert all(seed_hex not in t for t in texts)

        for forged_type in ("SET_SEED", "SHUFFLE", "SET_DECK", "FAIRNESS_REVEALED"):
            host_ws.send_json({"type": forged_type, "payload": {"server_seed": client_seed}})
            assert "Unknown" in _recv_until(host_ws, "ERROR")["payload"]["error"]
        assert not fair_round.revealed
        assert _seed_of(session.game, 1) == seed_hex


# ---------------- J, M, N, O over the real WebSocket endpoint ----------------
def test_ws_seed_revealed_only_at_round_end_and_reconnect_behavior(ws_env):
    room_id = ws_env["room_id"]
    user_ids = ws_env["user_ids"]
    p1_id = user_ids[1]

    with _connect(ws_env, 0) as ws0, _connect(ws_env, 2) as ws2, _connect(ws_env, 3) as ws3:
        for ws in (ws0, ws2, ws3):
            _recv_until(ws, "ROOM_STATE")

        with _connect(ws_env, 1) as ws1:
            _recv_until(ws1, "ROOM_STATE")
            ws0.send_json({"type": "START_GAME", "payload": {}})
            _recv_until(ws0, "GAME_STARTED")

            session = game_session_manager.get_session(room_id)
            round1 = session.game.fairness.get(1)
            seed1 = _seed_of(session.game, 1)
            dealt_order = round1.deck_order()

            # M. Reconnect before reveal: commitment present, seed absent
            ws1.close()
            _recv_until(ws0, "PLAYER_DISCONNECTED")
        with _connect(ws_env, 1) as ws1:
            texts, recon = _collect_until(ws1, "GAME_STATE")
            assert all(seed1 not in t for t in texts)
            record = recon["payload"]["game_view"]["fairness"][0]
            assert record["commitment"] == round1.commitment
            assert record["revealed"] is False and record["server_seed"] is None

            # J. Still hidden mid-round; reveal happens when the round's 13th trick resolves
            final_cards = _rig_final_trick(session, user_ids, leader_score=0)
            sockets = [ws0, ws1, ws2, ws3]
            for i, (ws, card) in enumerate(zip(sockets, final_cards)):
                assert not round1.revealed
                ws.send_json({"type": "PLAY_CARD", "payload": {"card_id": card.id}})
                if i < 3:
                    texts, _ = _collect_until(
                        ws, "GAME_STATE",
                        lambda m, n=i + 1: len(m["payload"]["game_view"]["public_state"]["current_trick"]) == n,
                    )
                    assert all(seed1 not in t for t in texts)

            texts, reveal_msg = _collect_until(ws2, "FAIRNESS_REVEALED")
            assert reveal_msg["payload"]["fairness"]["round_number"] == 1
            assert reveal_msg["payload"]["fairness"]["server_seed"] == seed1
            texts, commit2 = _collect_until(ws2, "FAIRNESS_COMMITTED")
            assert commit2["payload"]["fairness"]["round_number"] == 2
            seed2 = _seed_of(session.game, 2)
            _, view_msg = _collect_until(ws2, "GAME_STATE", lambda m: m["payload"]["game_view"]["round_number"] == 2)
            assert seed2 not in json.dumps(view_msg)

            # O. Verifier reproduces exactly the deck order that was dealt
            result = verify_public_record(reveal_msg["payload"]["fairness"])
            assert result.ok
            assert result.deck_order == dealt_order

            ws1.close()
            _recv_until(ws0, "PLAYER_DISCONNECTED")

        # N. Reconnect after reveal: round 1 seed public, round 2 still hidden
        with _connect(ws_env, 1) as ws1:
            texts, recon = _collect_until(ws1, "GAME_STATE")
            records = {r["round_number"]: r for r in recon["payload"]["game_view"]["fairness"]}
            assert records[1]["revealed"] is True and records[1]["server_seed"] == seed1
            assert verify_public_record(records[1]).deck_order == dealt_order
            assert records[2]["revealed"] is False and records[2]["server_seed"] is None
            assert all(seed2 not in t for t in texts)
            assert game_session_manager.get_session(room_id) is session


# ---------------- Shared cross-language vectors + public deck-definition endpoint ----------------
VECTORS_FILE = BACKEND_DIR.parent / "docs" / "architecture" / "fairness-test-vectors.json"


def test_shared_test_vectors_match_python_implementation():
    """The same file is consumed by the frontend verifier tests, keeping both implementations in sync."""
    data = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))
    assert data["algorithm"] == ALGORITHM
    canonical = DECK_DEFINITIONS[data["deck_definition"]]
    assert data["canonical_deck"] == canonical
    assert data["canonical_deck_sha256"] == canonical_deck_hash(canonical)
    assert len(data["vectors"]) >= 1
    cards_by_id = {c.id: c for c in Deck().cards}
    for vector in data["vectors"]:
        seed = bytes.fromhex(vector["server_seed"])
        assert compute_commitment(seed) == vector["commitment"]
        assert deterministic_shuffle(canonical, seed) == vector["deck_order"]
        # Dealt hands come from the engine's real Deck.deal, which the frontend hand check mirrors
        hands = Deck(cards=[cards_by_id[i] for i in vector["deck_order"]]).deal(
            num_players=data["deal"]["num_players"], cards_per_player=data["deal"]["cards_per_player"]
        )
        assert [[c.id for c in h] for h in hands] == vector["dealt_hands"]


def test_deck_definition_endpoint_serves_documented_definition():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get(f"/api/v1/fairness/deck-definitions/{STANDARD_52}")
    assert response.status_code == 200
    body = response.json()
    assert body["cards"] == DECK_DEFINITIONS[STANDARD_52]
    assert body["sha256"] == canonical_deck_hash(DECK_DEFINITIONS[STANDARD_52])
    assert body["algorithm"] == ALGORITHM
    assert client.get("/api/v1/fairness/deck-definitions/does-not-exist").status_code == 404
