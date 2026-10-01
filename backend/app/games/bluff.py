"""Server-authoritative implementation of Bluff (v1 rules)."""
import secrets
from typing import List, Optional, Tuple
from pydantic import ValidationError
from app.game_engine.action import (
    ActionType,
    CallBluffPayload,
    EventType,
    GameAction,
    GameEvent,
    PlayCardsPayload,
)
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.game import BaseGame
from app.game_engine.player import Player, PlayerPublicView
from app.game_engine.registry import GameRegistry
from app.game_engine.state import GamePhase, PlayerGameView
from app.games.bluff_state import BluffChallengeResult, BluffGameState, BluffPlay

MIN_PLAYERS = 2
MAX_PLAYERS = 8
MAX_CARDS_PER_PLAY = 4
FAIRNESS_ROUND = 1  # Bluff is a single deal; its seed is revealed at game over

_RANK_ORDER = {rank: i for i, rank in enumerate(Rank)}
_SUIT_ORDER = {suit: i for i, suit in enumerate(Suit)}


def _sort_hand(hand: List[Card]) -> None:
    hand.sort(key=lambda c: (_RANK_ORDER[c.rank], _SUIT_ORDER[c.suit]))


@GameRegistry.register("bluff")
class BluffGame(BaseGame):
    """
    Bluff v1:
    - 2-8 players; the full 52-card deck is dealt round-robin (provably-fair committed shuffle)
    - Server picks the starting player with the OS CSPRNG
    - On their turn a player places 1-4 of their cards face down and declares a rank
      (any rank; quantity is always the number of cards placed)
    - The next player may instead CALL_BLUFF on the immediately previous play:
      any card not of the declared rank -> the declarer takes the pile, otherwise the challenger does.
      Play then continues with the player after the challenged player.
    - The first player to empty their hand wins immediately
    """

    def __init__(self, game_id: str, game_type: str = "bluff"):
        super().__init__(game_id=game_id, game_type=game_type)
        self.state: BluffGameState = BluffGameState(game_id=game_id, game_type=game_type)

    # ---------------- Setup ----------------
    def initialize_game(self, player_ids: List[str]) -> List[GameEvent]:
        if not MIN_PLAYERS <= len(player_ids) <= MAX_PLAYERS:
            raise ValueError(
                f"Bluff requires {MIN_PLAYERS}-{MAX_PLAYERS} players, got {len(player_ids)}."
            )
        if len(set(player_ids)) != len(player_ids):
            raise ValueError("Duplicate player IDs")

        self.state.players.clear()
        self.state.player_order = []
        self.state.scores = {}
        for seat, pid in enumerate(player_ids):
            self.state.add_player(Player(id=pid, seat=seat, display_name=f"Player {seat + 1}"))

        events: List[GameEvent] = [
            GameEvent(game_id=self.game_id, type=EventType.GAME_CREATED, data={"players": list(player_ids)})
        ]

        # Commitment is created before the deck exists and before any card is dealt
        deck, commit_event = self.create_committed_deck(FAIRNESS_ROUND)
        events.append(commit_event)
        hands = deck.deal_all(num_players=len(player_ids))
        for pid, hand in zip(self.state.player_order, hands):
            _sort_hand(hand)
            self.state.players[pid].hand = hand

        starting_player_id = self.state.player_order[secrets.randbelow(len(player_ids))]
        self.state.starting_player_id = starting_player_id
        self.state.current_turn_player_id = starting_player_id
        self.state.phase = GamePhase.IN_PROGRESS

        events.append(
            GameEvent(
                game_id=self.game_id,
                type=EventType.GAME_STARTED,
                data={
                    "player_count": len(player_ids),
                    "hand_sizes": {pid: p.card_count() for pid, p in self.state.players.items()},
                    "starting_player_id": starting_player_id,
                },
            )
        )
        events.append(self._turn_event(starting_player_id))
        return events

    def start_game(self) -> List[GameEvent]:
        return []

    # ---------------- Validation ----------------
    def validate_action(self, action: GameAction) -> Tuple[bool, str]:
        if self.state.phase == GamePhase.GAME_OVER:
            return False, "Game has concluded. No further actions permitted."
        if self.state.phase != GamePhase.IN_PROGRESS:
            return False, "Game is not in progress"

        player = self.state.players.get(action.player_id)
        if not player:
            return False, f"Player {action.player_id} not in game"

        if action.type == ActionType.PLAY_CARDS:
            return self._validate_play(action, player)
        if action.type == ActionType.CALL_BLUFF:
            return self._validate_call_bluff(action)
        return False, f"Unsupported action {action.type} for Bluff"

    def _parse_play(self, action: GameAction) -> Tuple[Optional[PlayCardsPayload], str]:
        try:
            return PlayCardsPayload.model_validate(action.payload), ""
        except ValidationError as ve:
            return None, f"Invalid PLAY_CARDS payload: {ve.errors()[0]['msg']}"

    def _validate_play(self, action: GameAction, player: Player) -> Tuple[bool, str]:
        if self.state.current_turn_player_id != action.player_id:
            return False, "Not your turn"
        payload, error = self._parse_play(action)
        if payload is None:
            return False, error

        card_ids = payload.card_ids
        if not 1 <= len(card_ids) <= MAX_CARDS_PER_PLAY:
            return False, f"A play must contain 1-{MAX_CARDS_PER_PLAY} cards, got {len(card_ids)}"
        if len(set(card_ids)) != len(card_ids):
            return False, "Duplicate cards selected"
        hand_ids = {c.id for c in player.hand}
        for cid in card_ids:
            if cid not in hand_ids:
                return False, f"Card {cid} is not in your hand"
        if payload.declared_quantity is not None and payload.declared_quantity != len(card_ids):
            return False, "Declared quantity must equal the number of cards played"
        return True, ""

    def _validate_call_bluff(self, action: GameAction) -> Tuple[bool, str]:
        if self.state.current_turn_player_id != action.player_id:
            return False, "Not your turn"
        try:
            CallBluffPayload.model_validate(action.payload)
        except ValidationError as ve:
            return False, f"Invalid CALL_BLUFF payload: {ve.errors()[0]['msg']}"
        last_play = self.state.last_play
        if last_play is None:
            return False, "There is no play to challenge"
        if last_play.player_id == action.player_id:
            return False, "You cannot challenge your own play"
        return True, ""

    # ---------------- Application ----------------
    def apply_action(self, action: GameAction) -> List[GameEvent]:
        is_valid, reason = self.validate_action(action)
        if not is_valid:
            raise ValueError(reason)
        if action.type == ActionType.PLAY_CARDS:
            return self._apply_play(action)
        return self._apply_call_bluff(action)

    def _apply_play(self, action: GameAction) -> List[GameEvent]:
        payload, _ = self._parse_play(action)
        player = self.state.players[action.player_id]
        played = [player.remove_card(cid) for cid in payload.card_ids]

        self.state.pile.extend(played)
        self.state.last_play = BluffPlay(
            player_id=player.id, cards=played, declared_rank=payload.declared_rank
        )
        self.state.play_count += 1

        # Public event: count and declaration only, never the card IDs
        events: List[GameEvent] = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.CARDS_PLAYED,
                actor_player_id=player.id,
                data={
                    "player_id": player.id,
                    "declared_rank": payload.declared_rank.value,
                    "declared_quantity": len(played),
                    "pile_count": len(self.state.pile),
                    "hand_count": player.card_count(),
                },
            )
        ]

        if player.card_count() == 0:
            events.extend(self._finish_game(winner_id=player.id))
        else:
            events.append(self._turn_event(self.next_turn()))
        return events

    def _apply_call_bluff(self, action: GameAction) -> List[GameEvent]:
        challenged = self.state.last_play
        challenger_id = action.player_id
        truthful = all(card.rank == challenged.declared_rank for card in challenged.cards)
        recipient_id = challenger_id if truthful else challenged.player_id

        pile = self.state.pile
        recipient = self.state.players[recipient_id]
        for card in pile:
            recipient.add_card(card)
        _sort_hand(recipient.hand)

        result = BluffChallengeResult(
            challenger_id=challenger_id,
            challenged_player_id=challenged.player_id,
            declared_rank=challenged.declared_rank,
            declared_quantity=challenged.declared_quantity,
            revealed_cards=list(challenged.cards),
            declaration_truthful=truthful,
            pile_recipient_id=recipient_id,
            pile_size=len(pile),
        )
        self.state.last_challenge = result
        self.state.pile = []
        self.state.last_play = None

        # Play continues with the player after the one who made the challenged play
        order = self.state.player_order
        next_player_id = order[(order.index(challenged.player_id) + 1) % len(order)]
        self.state.current_turn_player_id = next_player_id

        return [
            GameEvent(
                game_id=self.game_id,
                type=EventType.CHALLENGE_ISSUED,
                actor_player_id=challenger_id,
                data={"challenger_id": challenger_id, "challenged_player_id": challenged.player_id},
            ),
            GameEvent(
                game_id=self.game_id,
                type=EventType.CHALLENGE_RESOLVED,
                actor_player_id=challenger_id,
                data=self._public_challenge(result),
            ),
            self._turn_event(next_player_id),
        ]

    def _finish_game(self, winner_id: str) -> List[GameEvent]:
        self.state.winner_id = winner_id
        self.state.phase = GamePhase.GAME_OVER
        self.state.current_turn_player_id = None
        self.state.scores = {pid: (1 if pid == winner_id else 0) for pid in self.state.player_order}
        events = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.GAME_COMPLETED,
                actor_player_id=winner_id,
                data={"winner_id": winner_id},
            )
        ]
        # The single deal is over: its seed no longer hides anything that matters
        reveal_event = self.reveal_fairness(FAIRNESS_ROUND)
        if reveal_event:
            events.append(reveal_event)
        return events

    def _turn_event(self, player_id: str) -> GameEvent:
        return GameEvent(
            game_id=self.game_id,
            type=EventType.TURN_CHANGED,
            actor_player_id=player_id,
            data={"turn_player_id": player_id},
        )

    @staticmethod
    def _public_challenge(result: BluffChallengeResult) -> dict:
        return result.model_dump(mode="json")

    # ---------------- Queries ----------------
    def get_valid_actions(self, player_id: str) -> List[str]:
        if self.state.phase != GamePhase.IN_PROGRESS or self.state.current_turn_player_id != player_id:
            return []
        actions = [ActionType.PLAY_CARDS.value]
        if self.state.last_play is not None and self.state.last_play.player_id != player_id:
            actions.append(ActionType.CALL_BLUFF.value)
        return actions

    def next_turn(self) -> str:
        order = self.state.player_order
        current = self.state.current_turn_player_id or order[0]
        next_id = order[(order.index(current) + 1) % len(order)]
        self.state.current_turn_player_id = next_id
        return next_id

    def is_round_complete(self) -> bool:
        return self.state.winner_id is not None

    def is_game_complete(self) -> bool:
        return self.state.winner_id is not None

    def calculate_score(self) -> dict:
        return dict(self.state.scores)

    def get_player_view(self, player_id: str) -> PlayerGameView:
        """Only the viewer's own hand is included; pile and unchallenged plays stay face down."""
        public_players = [
            PlayerPublicView(
                id=p.id,
                seat=p.seat,
                display_name=p.display_name,
                is_connected=p.is_connected,
                card_count=p.card_count(),
            )
            for p in (self.state.players[pid] for pid in self.state.player_order)
        ]
        viewer = self.state.players.get(player_id)
        last_play = self.state.last_play

        public_state = {
            "player_order": list(self.state.player_order),
            "starting_player_id": self.state.starting_player_id,
            "pile_count": len(self.state.pile),
            "play_count": self.state.play_count,
            "last_play": (
                {
                    "player_id": last_play.player_id,
                    "declared_rank": last_play.declared_rank.value,
                    "declared_quantity": last_play.declared_quantity,
                }
                if last_play
                else None
            ),
            "last_challenge": (
                self._public_challenge(self.state.last_challenge) if self.state.last_challenge else None
            ),
            "winner_id": self.state.winner_id,
            "declarable_ranks": [rank.value for rank in Rank],
            "max_cards_per_play": MAX_CARDS_PER_PLAY,
        }

        return PlayerGameView(
            game_id=self.game_id,
            game_type=self.game_type,
            phase=self.state.phase,
            viewer_id=player_id,
            current_turn_player_id=self.state.current_turn_player_id,
            round_number=FAIRNESS_ROUND,
            scores=dict(self.state.scores),
            players=public_players,
            my_hand=list(viewer.hand) if viewer else [],
            public_state=public_state,
            valid_actions=self.get_valid_actions(player_id),
        )
