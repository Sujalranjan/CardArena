"""Comprehensive Security & Architecture Hardening Test Suite for Phase 1.5."""
import json
import pytest
import pytest_asyncio
from app.auth.auth import create_access_token
from app.database.session import Base
from app.game_engine.action import ActionType, EventType, GameAction, GameEvent
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.game import BaseGame
from app.game_engine.player import Player, PlayerPublicView
from app.game_engine.registry import GameRegistry
from app.game_engine.state import GamePhase, PlayerGameView
from app.main import app
from app.models.models import Room, RoomPlayer, RoomStatus, User
from app.services.game_session_manager import GameSessionManager
from app.services.room_service import RoomService, generate_room_code
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


class SecurityAuditingGame(BaseGame):
    """Registered test game verifying engine isolation, hidden state, and action handling."""

    def initialize_game(self, player_ids: list[str]) -> list[GameEvent]:
        for i, pid in enumerate(player_ids):
            if pid == "alice":
                hand = [Card.create(Suit.SPADES, Rank.ACE), Card.create(Suit.HEARTS, Rank.KING)]
            else:
                hand = [Card.create(Suit.DIAMONDS, Rank.QUEEN), Card.create(Suit.CLUBS, Rank.TEN)]

            self.state.add_player(
                Player(
                    id=pid,
                    seat=i,
                    display_name=f"Player_{pid}",
                    hand=hand,
                )
            )
        self.state.phase = GamePhase.IN_PROGRESS
        return [
            GameEvent(
                game_id=self.game_id,
                type=EventType.GAME_STARTED,
                actor_player_id=player_ids[0],
                data={"status": "initialized"},
            )
        ]

    def start_game(self) -> list[GameEvent]:
        return []

    def validate_action(self, action: GameAction) -> tuple[bool, str]:
        # Validate that acting player can only play cards in their own hand
        player = self.state.get_player(action.player_id)
        if not player:
            return False, "Player not found in game state"

        if action.type == ActionType.PLAY_CARD:
            card_id = action.payload.get("card_id")
            if not any(c.id == card_id for c in player.hand):
                return False, f"Card {card_id} is not in {action.player_id}'s hand"
            return True, ""
        return True, ""

    def apply_action(self, action: GameAction) -> list[GameEvent]:
        if action.type == ActionType.PLAY_CARD:
            player = self.state.get_player(action.player_id)
            card = player.remove_card(action.payload["card_id"])
            return [
                GameEvent(
                    game_id=self.game_id,
                    type=EventType.CARD_PLAYED,
                    actor_player_id=action.player_id,
                    data={"played_card": card.id if card else None},
                )
            ]
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


GameRegistry.register_class("security_audit_game", SecurityAuditingGame)


@pytest_asyncio.fixture
async def sec_db():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ---------------- 1. Player Impersonation & Forged ID Protection ----------------
@pytest.mark.asyncio
async def test_action_cannot_impersonate_another_player():
    gsm = GameSessionManager()
    session = gsm.create_session("room_aud_1", "security_audit_game", ["alice", "bob"])

    bob = session.game.state.get_player("bob")
    bob_card = bob.hand[0].id

    # Alice tries to play Bob's card -> rejected by authoritative validation
    success, reason = await gsm.dispatch_action(
        room_id="room_aud_1",
        actor_player_id="alice",  # Authenticated identity from socket
        action_type_str="PLAY_CARD",
        payload={"card_id": bob_card},  # Alice doesn't own this card!
    )
    assert not success
    assert "not in alice's hand" in reason


# ---------------- 2. Typed Action Schema Validation ----------------
@pytest.mark.asyncio
async def test_invalid_action_payload_rejected_before_game_engine():
    gsm = GameSessionManager()
    gsm.create_session("room_aud_2", "security_audit_game", ["alice", "bob"])

    # Missing required 'card_id' for PLAY_CARD action
    success, reason = await gsm.dispatch_action(
        room_id="room_aud_2",
        actor_player_id="alice",
        action_type_str="PLAY_CARD",
        payload={"wrong_field": 123},
    )
    assert not success
    assert "Invalid payload for PLAY_CARD" in reason


# ---------------- 3. Client Cannot Submit Authoritative State ----------------
@pytest.mark.asyncio
async def test_client_cannot_inject_scores_or_winner(sec_db: AsyncSession):
    gsm = GameSessionManager()
    session = gsm.create_session("room_aud_3", "security_audit_game", ["alice", "bob"])

    malicious_payload = {
        "score": {"alice": 9999},
        "winner": "alice",
        "phase": "GAME_OVER",
        "card_id": "SPADES_A",
    }
    success, _ = await gsm.dispatch_action(
        room_id="room_aud_3",
        actor_player_id="alice",
        action_type_str="PLAY_CARD",
        payload=malicious_payload,
    )
    assert success
    # Verify authoritative score in server state was UNTOUCHED
    assert session.game.state.scores.get("alice", 0) == 0


# ---------------- 4. Hidden Information Protection in Serialized Payloads ----------------
@pytest.mark.asyncio
async def test_hidden_card_ids_absent_from_serialized_network_payloads():
    gsm = GameSessionManager()
    session = gsm.create_session("room_aud_4", "security_audit_game", ["alice", "bob"])

    bob = session.game.state.get_player("bob")
    bob.hand = [Card.create(Suit.DIAMONDS, Rank.ACE), Card.create(Suit.CLUBS, Rank.NINE)]

    alice_view: PlayerGameView = session.game.get_player_view("alice")
    alice_network_payload = json.dumps(alice_view.model_dump())

    assert "DIAMONDS_A" not in alice_network_payload
    assert "CLUBS_9" not in alice_network_payload

    bob_public = next(p for p in alice_view.players if p.id == "bob")
    assert bob_public.card_count == 2


# ---------------- 5. Room Code Generation Entropy & Non-Predictability ----------------
def test_room_code_entropy_and_unambiguity():
    codes = set()
    for _ in range(500):
        code = generate_room_code(6)
        assert len(code) == 6
        assert not any(c in code for c in "0O1I")
        codes.add(code)
    assert len(codes) == 500


# ---------------- 6. Reconnection and Replay Events Sequence ----------------
@pytest.mark.asyncio
async def test_sequenceable_game_events_and_reconnection():
    gsm = GameSessionManager()
    session = gsm.create_session("room_aud_6", "security_audit_game", ["alice", "bob"])

    alice = session.game.state.get_player("alice")
    card_to_play = alice.hand[0].id

    success, _ = await gsm.dispatch_action(
        room_id="room_aud_6",
        actor_player_id="alice",
        action_type_str="PLAY_CARD",
        payload={"card_id": card_to_play},
    )
    assert success

    assert len(session.event_history) >= 2
    for i in range(len(session.event_history) - 1):
        assert session.event_history[i].sequence_number < session.event_history[i + 1].sequence_number

    reconnected_view = session.game.get_player_view("alice")
    assert len(reconnected_view.my_hand) == 1
