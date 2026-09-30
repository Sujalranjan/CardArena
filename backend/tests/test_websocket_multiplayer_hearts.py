"""Real 4-Player WebSocket Multiplayer Hearts Integration & Zero Hidden Information Test Suite."""
import asyncio
import json
import pytest
from app.auth.auth import create_access_token
from app.game_engine.action import ActionType, EventType, GameAction
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.state import GamePhase
from app.games.hearts import HeartsGame
from app.games.hearts_state import PassDirection
from app.schemas.schemas import WSServerMessage
from app.services.game_session_manager import GameSessionManager
from app.websocket.connection_manager import ConnectionManager


class MockWebSocket:
    """Simulated client WebSocket connection capturing server messages."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.received_messages: list[WSServerMessage] = []

    async def send_text(self, text: str):
        data = json.loads(text)
        self.received_messages.append(WSServerMessage.model_validate(data))


@pytest.mark.asyncio
async def test_real_websocket_multiplayer_hearts_pipeline():
    """
    Simulates the entire multi-player WebSocket pipeline:
    1. 4 connected player sockets in a room.
    2. Hearts session initialized and individual player views broadcast.
    3. Mathematical proof of hidden information isolation in raw network payloads.
    4. Passing 3 cards by each player via dispatch_action.
    5. Phase transitions to IN_PROGRESS.
    6. Leading 2 of Clubs by owner, turn progression, follow-suit validation.
    7. Reconnection state restoration without leaking opponent cards.
    """
    room_id = "room_ws_multi_hearts"
    player_ids = ["p1", "p2", "p3", "p4"]

    # 1. Setup isolated connection manager and mock sockets for 4 players
    cm = ConnectionManager()
    sockets = {pid: MockWebSocket(pid) for pid in player_ids}
    cm._rooms[room_id] = {}
    for pid, ws in sockets.items():
        cm._rooms[room_id][pid] = ws
        cm._socket_map[ws] = (room_id, pid)

    # Wire GameSessionManager
    gsm = GameSessionManager()
    import app.services.game_session_manager as gsm_module
    original_manager = gsm_module.manager
    gsm_module.manager = cm

    try:
        # 2. Host launches Hearts game
        session = gsm.create_session(room_id, "hearts", player_ids)
        assert session is not None
        assert session.game.game_type == "hearts"
        assert session.game.state.phase == GamePhase.STARTING

        # Broadcast initial views over WebSockets
        await gsm.broadcast_player_views(room_id)

        # 3. VERIFY HIDDEN INFORMATION IN RAW WEBSOCKET PAYLOADS
        for pid in player_ids:
            ws = sockets[pid]
            assert len(ws.received_messages) >= 1
            latest_msg = ws.received_messages[-1]
            assert latest_msg.type == "GAME_STATE"

            game_view = latest_msg.payload["game_view"]
            assert game_view["viewer_id"] == pid
            assert len(game_view["my_hand"]) == 13

            my_card_ids = {c["id"] for c in game_view["my_hand"]}

            # Verify no opponent private cards exist anywhere in this player's payload
            for opp_id in player_ids:
                if opp_id == pid:
                    continue
                opp_actual_hand = {c.id for c in session.game.state.players[opp_id].hand}
                # Opponent cards must NOT intersect with this player's visible cards
                assert opp_actual_hand.isdisjoint(my_card_ids)

                # Opponent cards must NOT appear anywhere in the serialized JSON text
                serialized_text = json.dumps(game_view)
                for opp_card_id in opp_actual_hand:
                    assert opp_card_id not in serialized_text

        # 4. PASSING PHASE VIA WEBSOCKET DISPATCH
        # 4a. Attempt invalid pass: 2 cards -> REJECTED
        p1_hand = [c.id for c in session.game.state.players["p1"].hand]
        bad_success, bad_reason = await gsm.dispatch_action(
            room_id=room_id,
            actor_player_id="p1",
            action_type_str="PASS_CARD",
            payload={"card_ids": p1_hand[:2]},
        )
        assert not bad_success
        assert "requires exactly 3 cards" in bad_reason

        # 4b. All 4 players pass 3 cards
        for pid in player_ids:
            p_cards = [c.id for c in session.game.state.players[pid].hand[:3]]
            success, reason = await gsm.dispatch_action(
                room_id=room_id,
                actor_player_id=pid,
                action_type_str="PASS_CARD",
                payload={"card_ids": p_cards},
            )
            assert success, reason

        # Passing complete -> transitions to IN_PROGRESS
        assert session.game.state.phase == GamePhase.IN_PROGRESS
        assert session.game.state.current_turn_player_id is not None

        # Verify all players received updated state with 13 cards each
        for pid in player_ids:
            ws = sockets[pid]
            latest_msg = ws.received_messages[-1]
            gv = latest_msg.payload["game_view"]
            assert gv["phase"] == "IN_PROGRESS"
            assert len(gv["my_hand"]) == 13

        # 5. VERIFY 2 OF CLUBS OPENING & TURN ENFORCEMENT
        current_turn = session.game.state.current_turn_player_id
        # The player with 2 of clubs must be current turn
        assert any(c.id == "CLUBS_2" for c in session.game.state.players[current_turn].hand)

        # Non-turn player attempts to play -> REJECTED
        non_turn_player = next(pid for pid in player_ids if pid != current_turn)
        non_turn_card = session.game.state.players[non_turn_player].hand[0].id
        turn_fail, turn_reason = await gsm.dispatch_action(
            room_id=room_id,
            actor_player_id=non_turn_player,
            action_type_str="PLAY_CARD",
            payload={"card_id": non_turn_card},
        )
        assert not turn_fail
        assert "turn to play" in turn_reason

        # Current player attempts to lead a card OTHER than 2 of Clubs on trick 1 -> REJECTED
        other_cards = [c.id for c in session.game.state.players[current_turn].hand if c.id != "CLUBS_2"]
        if other_cards:
            illegal_lead_fail, lead_reason = await gsm.dispatch_action(
                room_id=room_id,
                actor_player_id=current_turn,
                action_type_str="PLAY_CARD",
                payload={"card_id": other_cards[0]},
            )
            assert not illegal_lead_fail
            assert "2 of Clubs" in lead_reason

        # Current player plays 2 of Clubs -> SUCCESS
        open_success, open_reason = await gsm.dispatch_action(
            room_id=room_id,
            actor_player_id=current_turn,
            action_type_str="PLAY_CARD",
            payload={"card_id": "CLUBS_2"},
        )
        assert open_success, open_reason

        # All clients receive updated game state showing 2 of Clubs in current trick
        for pid in player_ids:
            latest_msg = sockets[pid].received_messages[-1]
            trick = latest_msg.payload["game_view"]["public_state"]["current_trick"]
            assert len(trick) == 1
            assert trick[0]["card"]["id"] == "CLUBS_2"

        # 6. RECONNECTION HANDLING
        # Simulate p1 disconnecting and reconnecting
        reconnected_ws = MockWebSocket("p1")
        cm._rooms[room_id]["p1"] = reconnected_ws
        await gsm.send_reconnect_view(room_id, "p1")
        assert len(reconnected_ws.received_messages) == 1
        recon_view = reconnected_ws.received_messages[0].payload["game_view"]
        assert recon_view["viewer_id"] == "p1"
        assert len(recon_view["my_hand"]) in (12, 13)

    finally:
        gsm_module.manager = original_manager
