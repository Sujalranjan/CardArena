"""Complete server-authoritative implementation of standard 4-player Hearts."""
from typing import Dict, List, Optional, Tuple
from app.game_engine.action import ActionType, EventType, GameAction, GameEvent
from app.game_engine.card import Card, Rank, Suit
from app.game_engine.deck import Deck
from app.game_engine.game import BaseGame
from app.game_engine.player import Player, PlayerPublicView
from app.game_engine.registry import GameRegistry
from app.game_engine.state import GamePhase, PlayerGameView
from app.games.hearts_constants import RANK_VALUES
from app.games.hearts_state import HeartsGameState, PassDirection, TrickCard


@GameRegistry.register("hearts")
class HeartsGame(BaseGame):
    """
    Standard American Hearts:
    - Exactly 4 Players, 52 cards (13 each)
    - Passing: Left (R1), Right (R2), Across (R3), Hold/None (R4), repeating
    - Opening: Player with 2 of Clubs must lead 2♣
    - Point cards prohibited on first trick unless player holds only point cards
    - Hearts-breaking: Hearts cannot be led until broken, or player holds only Hearts
    - Trick winner: Highest card of led suit
    - Scoring: Hearts = 1 pt each, Q♠ = 13 pts
    - Shooting the Moon: Player taking all 26 pts gets 0 pts, all others get +26 pts
    - Match ends when any player reaches or exceeds 100 points
    """

    def __init__(self, game_id: str, game_type: str = "hearts"):
        super().__init__(game_id=game_id, game_type=game_type)
        self.state: HeartsGameState = HeartsGameState(game_id=game_id, game_type=game_type)

    def initialize_game(self, player_ids: List[str]) -> List[GameEvent]:
        if len(player_ids) != 4:
            raise ValueError(f"Hearts requires exactly 4 players, got {len(player_ids)}.")

        self.state.players.clear()
        self.state.player_order = list(player_ids)
        self.state.scores = {pid: 0 for pid in player_ids}

        for i, pid in enumerate(player_ids):
            self.state.add_player(
                Player(
                    id=pid,
                    seat=i,
                    display_name=f"Player {i + 1}",
                    is_connected=True,
                    hand=[],
                )
            )

        events: List[GameEvent] = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.GAME_CREATED,
                data={"players": player_ids},
            )
        ]

        # Deal and begin first round
        start_events = self.start_round(round_number=1)
        events.extend(start_events)
        return events

    def start_game(self) -> List[GameEvent]:
        return []

    def start_round(self, round_number: int) -> List[GameEvent]:
        """Shuffles, deals 13 cards to each player, and configures round phase."""
        deck = Deck()
        deck.shuffle()
        hands = deck.deal(num_players=4, cards_per_player=13)

        # Sort each player's hand by suit and rank for clean UX
        suit_order = {Suit.CLUBS: 0, Suit.DIAMONDS: 1, Suit.SPADES: 2, Suit.HEARTS: 3}
        for i, pid in enumerate(self.state.player_order):
            hand = hands[i]
            hand.sort(key=lambda c: (suit_order[c.suit], RANK_VALUES[c.rank]))
            self.state.players[pid].hand = hand

        # Determine passing direction for round_number (1-indexed)
        # R1: Left, R2: Right, R3: Across, R4: None
        cycle_idx = (round_number - 1) % 4
        direction_map = [
            PassDirection.LEFT,
            PassDirection.RIGHT,
            PassDirection.ACROSS,
            PassDirection.NONE,
        ]
        direction = direction_map[cycle_idx]

        self.state.hearts_round.round_number = round_number
        self.state.hearts_round.pass_direction = direction
        self.state.hearts_round.hearts_broken = False
        self.state.hearts_round.is_first_trick = True
        self.state.hearts_round.passed_cards = {pid: [] for pid in self.state.player_order}
        self.state.hearts_round.has_passed = {pid: False for pid in self.state.player_order}
        self.state.hearts_round.current_trick = []
        self.state.hearts_round.completed_tricks_count = 0
        self.state.hearts_round.trick_lead_suit = None
        self.state.hearts_round.trick_winner_id = None
        self.state.hearts_round.taken_cards = {pid: [] for pid in self.state.player_order}
        self.state.hearts_round.round_points = {pid: 0 for pid in self.state.player_order}

        events: List[GameEvent] = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.GAME_STARTED,
                data={"round_number": round_number, "pass_direction": direction.value},
            )
        ]

        if direction == PassDirection.NONE:
            # Hold round -> transition straight to play
            self.state.phase = GamePhase.IN_PROGRESS
            starter_id = self._find_holder_of_two_of_clubs()
            self.state.current_turn_player_id = starter_id
            events.append(
                GameEvent(
                    game_id=self.game_id,
                    type=EventType.TURN_CHANGED,
                    actor_player_id=starter_id,
                    data={"turn_player_id": starter_id, "first_trick": True},
                )
            )
        else:
            self.state.phase = GamePhase.STARTING  # Used as passing phase
            self.state.current_turn_player_id = None

        return events

    def _find_holder_of_two_of_clubs(self) -> str:
        for pid, player in self.state.players.items():
            if any(c.suit == Suit.CLUBS and c.rank == Rank.TWO for c in player.hand):
                return pid
        return self.state.player_order[0]

    def _get_pass_target(self, player_id: str, direction: PassDirection) -> str:
        idx = self.state.player_order.index(player_id)
        if direction == PassDirection.LEFT:
            target_idx = (idx + 1) % 4
        elif direction == PassDirection.RIGHT:
            target_idx = (idx - 1) % 4
        elif direction == PassDirection.ACROSS:
            target_idx = (idx + 2) % 4
        else:
            target_idx = idx
        return self.state.player_order[target_idx]

    def validate_action(self, action: GameAction) -> Tuple[bool, str]:
        # If game is already complete, no further actions can be taken
        if self.state.phase == GamePhase.GAME_OVER:
            return False, "Game has concluded. No further actions permitted."

        player_id = action.player_id
        player = self.state.players.get(player_id)
        if not player:
            return False, f"Player {player_id} not in game"

        # ---------------- Passing Phase Validation ----------------
        if action.type == ActionType.PASS_CARD:
            if self.state.phase != GamePhase.STARTING:
                return False, "Passing phase is not active"
            if self.state.hearts_round.pass_direction == PassDirection.NONE:
                return False, "Passing is not permitted on hold rounds"
            if self.state.hearts_round.has_passed.get(player_id, False):
                return False, "Player has already submitted passed cards"

            card_ids = action.payload.get("card_ids", [])
            if len(card_ids) != 3:
                return False, f"Passing requires exactly 3 cards, got {len(card_ids)}"
            if len(set(card_ids)) != 3:
                return False, "Duplicate cards selected for passing"

            player_hand_ids = {c.id for c in player.hand}
            for cid in card_ids:
                if cid not in player_hand_ids:
                    return False, f"Card {cid} is not in player's hand"
            return True, ""

        # ---------------- Playing Phase Validation ----------------
        if action.type == ActionType.PLAY_CARD:
            if self.state.phase != GamePhase.IN_PROGRESS:
                return False, "Card playing phase is not active"
            if self.state.current_turn_player_id != player_id:
                return False, f"Not {player_id}'s turn to play (current: {self.state.current_turn_player_id})"

            card_id = action.payload.get("card_id")
            card = next((c for c in player.hand if c.id == card_id), None)
            if not card:
                return False, f"Card {card_id} not found in hand"

            trick = self.state.hearts_round.current_trick
            is_lead = len(trick) == 0

            # Rule 1: First Trick Lead must be 2 of Clubs
            if self.state.hearts_round.is_first_trick and is_lead:
                if not (card.suit == Suit.CLUBS and card.rank == Rank.TWO):
                    return False, "First trick must be led with the 2 of Clubs (2♣)"

            # Rule 2: Follow suit requirement
            if not is_lead:
                lead_suit = self.state.hearts_round.trick_lead_suit
                has_lead_suit = any(c.suit == lead_suit for c in player.hand)
                if has_lead_suit and card.suit != lead_suit:
                    return False, f"Must follow suit: lead suit is {lead_suit}"

            # Rule 3: First Trick Restrictions (no Hearts or Q♠ on trick 1 unless no alternative)
            if self.state.hearts_round.is_first_trick:
                is_point_card = (card.suit == Suit.HEARTS) or (card.suit == Suit.SPADES and card.rank == Rank.QUEEN)
                if is_point_card:
                    has_non_point = any(
                        not (c.suit == Suit.HEARTS or (c.suit == Suit.SPADES and c.rank == Rank.QUEEN))
                        for c in player.hand
                    )
                    if has_non_point:
                        return False, "Point cards (Hearts, Queen of Spades) cannot be played on the first trick"

            # Rule 4: Hearts-breaking rule on lead
            if is_lead and card.suit == Suit.HEARTS:
                if not self.state.hearts_round.hearts_broken:
                    has_non_hearts = any(c.suit != Suit.HEARTS for c in player.hand)
                    if has_non_hearts:
                        return False, "Hearts have not been broken yet"

            return True, ""

        return False, f"Unsupported action {action.type} for Hearts"

    def apply_action(self, action: GameAction) -> List[GameEvent]:
        is_valid, reason = self.validate_action(action)
        if not is_valid:
            raise ValueError(reason)

        events: List[GameEvent] = []

        if action.type == ActionType.PASS_CARD:
            events.extend(self._apply_pass_cards(action))
        elif action.type == ActionType.PLAY_CARD:
            events.extend(self._apply_play_card(action))

        return events

    def _apply_pass_cards(self, action: GameAction) -> List[GameEvent]:
        player_id = action.player_id
        card_ids = action.payload["card_ids"]
        player = self.state.players[player_id]

        selected_cards: List[Card] = []
        for cid in card_ids:
            c = player.remove_card(cid)
            if c:
                selected_cards.append(c)

        self.state.hearts_round.passed_cards[player_id] = selected_cards
        self.state.hearts_round.has_passed[player_id] = True

        events = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.CARDS_PASSED,
                actor_player_id=player_id,
                data={"player_id": player_id, "cards_count": len(selected_cards)},
            )
        ]

        # Check if all 4 players have submitted their passes
        if all(self.state.hearts_round.has_passed.values()):
            direction = self.state.hearts_round.pass_direction
            for sender_id in self.state.player_order:
                target_id = self._get_pass_target(sender_id, direction)
                cards_to_give = self.state.hearts_round.passed_cards[sender_id]
                for card in cards_to_give:
                    self.state.players[target_id].add_card(card)

            # Sort all hands again
            suit_order = {Suit.CLUBS: 0, Suit.DIAMONDS: 1, Suit.SPADES: 2, Suit.HEARTS: 3}
            for pid in self.state.player_order:
                self.state.players[pid].hand.sort(key=lambda c: (suit_order[c.suit], RANK_VALUES[c.rank]))

            # Transition to playing phase
            self.state.phase = GamePhase.IN_PROGRESS
            starter_id = self._find_holder_of_two_of_clubs()
            self.state.current_turn_player_id = starter_id

            events.append(
                GameEvent(
                    game_id=self.game_id,
                    type=EventType.TURN_CHANGED,
                    actor_player_id=starter_id,
                    data={"turn_player_id": starter_id, "first_trick": True},
                )
            )

        return events

    def _apply_play_card(self, action: GameAction) -> List[GameEvent]:
        player_id = action.player_id
        card_id = action.payload["card_id"]
        player = self.state.players[player_id]

        played_card = player.remove_card(card_id)
        if not played_card:
            raise ValueError(f"Card {card_id} could not be removed from hand")

        # Break hearts if played off-suit or discard
        if played_card.suit == Suit.HEARTS:
            self.state.hearts_round.hearts_broken = True

        trick = self.state.hearts_round.current_trick
        if len(trick) == 0:
            self.state.hearts_round.trick_lead_suit = played_card.suit.value

        trick.append(TrickCard(player_id=player_id, card=played_card))

        events: List[GameEvent] = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.CARD_PLAYED,
                actor_player_id=player_id,
                data={"card": played_card.model_dump(), "trick_count": len(trick)},
            )
        ]

        if len(trick) < 4:
            # Advance to next seat clockwise
            next_player_id = self.next_turn()
            events.append(
                GameEvent(
                    game_id=self.game_id,
                    type=EventType.TURN_CHANGED,
                    actor_player_id=next_player_id,
                    data={"turn_player_id": next_player_id},
                )
            )
        else:
            # Trick resolution
            trick_events = self._resolve_current_trick()
            events.extend(trick_events)

        return events

    def _resolve_current_trick(self) -> List[GameEvent]:
        trick = self.state.hearts_round.current_trick
        lead_suit = self.state.hearts_round.trick_lead_suit

        eligible = [tc for tc in trick if tc.card.suit.value == lead_suit]
        winning_trick_card = max(eligible, key=lambda tc: RANK_VALUES[tc.card.rank])
        winner_id = winning_trick_card.player_id

        trick_points = 0
        taken_cards = [tc.card for tc in trick]
        for c in taken_cards:
            if c.suit == Suit.HEARTS:
                trick_points += 1
            elif c.suit == Suit.SPADES and c.rank == Rank.QUEEN:
                trick_points += 13

        self.state.hearts_round.taken_cards[winner_id].extend(taken_cards)
        self.state.hearts_round.round_points[winner_id] += trick_points
        self.state.hearts_round.trick_winner_id = winner_id
        self.state.hearts_round.completed_tricks_count += 1
        self.state.hearts_round.is_first_trick = False
        self.state.hearts_round.current_trick = []
        self.state.hearts_round.trick_lead_suit = None

        events: List[GameEvent] = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.TRICK_COMPLETED,
                actor_player_id=winner_id,
                data={
                    "trick_winner_id": winner_id,
                    "points": trick_points,
                    "completed_tricks": self.state.hearts_round.completed_tricks_count,
                },
            )
        ]

        if self.is_round_complete():
            round_events = self._resolve_round_end()
            events.extend(round_events)
        else:
            # Winner leads the next trick
            self.state.current_turn_player_id = winner_id
            events.append(
                GameEvent(
                    game_id=self.game_id,
                    type=EventType.TURN_CHANGED,
                    actor_player_id=winner_id,
                    data={"turn_player_id": winner_id},
                )
            )

        return events

    def _resolve_round_end(self) -> List[GameEvent]:
        round_points = dict(self.state.hearts_round.round_points)

        # Check for shooting the moon (one player took all 26 points)
        moon_shooter = None
        for pid, pts in round_points.items():
            if pts == 26:
                moon_shooter = pid
                break

        if moon_shooter:
            # Shooter gets 0, all others get 26
            for pid in self.state.player_order:
                if pid == moon_shooter:
                    round_points[pid] = 0
                else:
                    round_points[pid] = 26

        # Accumulate total scores
        for pid in self.state.player_order:
            self.state.scores[pid] += round_points[pid]

        events: List[GameEvent] = [
            GameEvent(
                game_id=self.game_id,
                type=EventType.ROUND_COMPLETED,
                data={
                    "round_scores": round_points,
                    "total_scores": dict(self.state.scores),
                    "shot_moon": moon_shooter,
                },
            )
        ]

        if self.is_game_complete():
            self.state.phase = GamePhase.GAME_OVER
            self.state.current_turn_player_id = None
            lowest_scorer = min(self.state.player_order, key=lambda p: self.state.scores[p])
            events.append(
                GameEvent(
                    game_id=self.game_id,
                    type=EventType.GAME_COMPLETED,
                    actor_player_id=lowest_scorer,
                    data={"winner_id": lowest_scorer, "final_scores": dict(self.state.scores)},
                )
            )
        else:
            # Automatically start next round
            next_round_num = self.state.hearts_round.round_number + 1
            next_events = self.start_round(round_number=next_round_num)
            events.extend(next_events)

        return events

    def get_valid_actions(self, player_id: str) -> List[str]:
        if self.state.phase == GamePhase.STARTING:
            if not self.state.hearts_round.has_passed.get(player_id, False):
                if self.state.hearts_round.pass_direction != PassDirection.NONE:
                    return [ActionType.PASS_CARD.value]
            return []

        if self.state.phase == GamePhase.IN_PROGRESS:
            if self.state.current_turn_player_id == player_id:
                return [ActionType.PLAY_CARD.value]
            return []

        return []

    def next_turn(self) -> str:
        curr_id = self.state.current_turn_player_id
        if not curr_id:
            curr_id = self.state.player_order[0]
        curr_idx = self.state.player_order.index(curr_id)
        next_id = self.state.player_order[(curr_idx + 1) % 4]
        self.state.current_turn_player_id = next_id
        return next_id

    def is_round_complete(self) -> bool:
        return self.state.hearts_round.completed_tricks_count == 13

    def is_game_complete(self) -> bool:
        return any(score >= self.state.max_score_threshold for score in self.state.scores.values())

    def calculate_score(self) -> dict:
        return dict(self.state.scores)

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

        viewer = self.state.players.get(player_id)
        my_hand = list(viewer.hand) if viewer else []

        public_state = {
            "round_number": self.state.hearts_round.round_number,
            "pass_direction": self.state.hearts_round.pass_direction.value,
            "has_passed": dict(self.state.hearts_round.has_passed),
            "hearts_broken": self.state.hearts_round.hearts_broken,
            "is_first_trick": self.state.hearts_round.is_first_trick,
            "current_trick": [
                {"player_id": tc.player_id, "card": tc.card.model_dump()}
                for tc in self.state.hearts_round.current_trick
            ],
            "trick_lead_suit": self.state.hearts_round.trick_lead_suit,
            "completed_tricks": self.state.hearts_round.completed_tricks_count,
            "round_points": dict(self.state.hearts_round.round_points),
            "total_scores": dict(self.state.scores),
            "last_trick_winner_id": self.state.hearts_round.trick_winner_id,
        }

        return PlayerGameView(
            game_id=self.game_id,
            game_type=self.game_type,
            phase=self.state.phase,
            viewer_id=player_id,
            current_turn_player_id=self.state.current_turn_player_id,
            round_number=self.state.hearts_round.round_number,
            scores=dict(self.state.scores),
            players=public_players,
            my_hand=my_hand,
            public_state=public_state,
            valid_actions=self.get_valid_actions(player_id),
        )
