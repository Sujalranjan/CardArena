"""Authoritative Action and Sequenceable GameEvent models."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.game_engine.card import Rank


class ActionType(str, Enum):
    JOIN_GAME = "JOIN_GAME"
    READY = "READY"
    NOT_READY = "NOT_READY"
    START_GAME = "START_GAME"
    LEAVE_ROOM = "LEAVE_ROOM"

    PLAY_CARD = "PLAY_CARD"
    DRAW_CARD = "DRAW_CARD"
    DISCARD_CARD = "DISCARD_CARD"
    PASS_CARD = "PASS_CARD"
    BET = "BET"
    CALL = "CALL"
    FOLD = "FOLD"
    CHALLENGE = "CHALLENGE"
    END_TURN = "END_TURN"

    PLAY_CARDS = "PLAY_CARDS"
    CALL_BLUFF = "CALL_BLUFF"


# ---------------- Typed Specific Client Action Payloads ----------------
class PlayCardPayload(BaseModel):
    card_id: str = Field(description="Unique ID of card being played from player's hand")


class DrawCardPayload(BaseModel):
    count: int = Field(default=1, ge=1, le=10)


class DiscardCardPayload(BaseModel):
    card_ids: List[str] = Field(min_length=1)


class PassCardPayload(BaseModel):
    card_ids: List[str] = Field(min_length=1)
    target_player_id: Optional[str] = None


class BetPayload(BaseModel):
    amount: int = Field(gt=0)


class CallPayload(BaseModel):
    pass


class FoldPayload(BaseModel):
    pass


class ChallengePayload(BaseModel):
    claim_details: Optional[Dict[str, Any]] = None


class EndTurnPayload(BaseModel):
    pass


class PlayCardsPayload(BaseModel):
    """Face-down multi-card play with a declared rank. Unknown fields are rejected."""
    model_config = ConfigDict(extra="forbid")

    card_ids: List[str] = Field(min_length=1)
    declared_rank: Rank
    declared_quantity: Optional[int] = Field(
        default=None, description="Optional; when present it must equal len(card_ids)"
    )


class CallBluffPayload(BaseModel):
    """Challenges the immediately previous play. Carries no client-supplied information."""
    model_config = ConfigDict(extra="forbid")


class GameAction(BaseModel):
    type: ActionType
    player_id: str = Field(description="Server-derived verified player ID")
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventType(str, Enum):
    GAME_CREATED = "GAME_CREATED"
    PLAYER_JOINED = "PLAYER_JOINED"
    PLAYER_LEFT = "PLAYER_LEFT"
    PLAYER_READY = "PLAYER_READY"
    PLAYER_NOT_READY = "PLAYER_NOT_READY"
    GAME_STARTING = "GAME_STARTING"
    GAME_STARTED = "GAME_STARTED"
    CARD_PLAYED = "CARD_PLAYED"
    TRICK_COMPLETED = "TRICK_COMPLETED"
    ROUND_COMPLETED = "ROUND_COMPLETED"
    GAME_COMPLETED = "GAME_COMPLETED"
    CARD_DRAWN = "CARD_DRAWN"
    CARDS_DISCARDED = "CARDS_DISCARDED"
    CARDS_PASSED = "CARDS_PASSED"
    BET_PLACED = "BET_PLACED"
    PLAYER_CALLED = "PLAYER_CALLED"
    PLAYER_FOLDED = "PLAYER_FOLDED"
    CHALLENGE_ISSUED = "CHALLENGE_ISSUED"
    TURN_CHANGED = "TURN_CHANGED"
    CARDS_PLAYED = "CARDS_PLAYED"
    CHALLENGE_RESOLVED = "CHALLENGE_RESOLVED"
    FAIRNESS_COMMITTED = "FAIRNESS_COMMITTED"
    FAIRNESS_REVEALED = "FAIRNESS_REVEALED"
    PLAYER_DISCONNECTED = "PLAYER_DISCONNECTED"
    PLAYER_RECONNECTED = "PLAYER_RECONNECTED"


class GameEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    game_id: str
    sequence_number: int = Field(default=0, description="Strict monotonically increasing sequence number")
    type: EventType
    actor_player_id: Optional[str] = Field(default=None, description="Player initiating the action")
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def serialize_sanitized(self, viewer_player_id: Optional[str] = None) -> Dict[str, Any]:
        payload = self.model_dump()
        payload["timestamp"] = self.timestamp.isoformat()
        return payload
