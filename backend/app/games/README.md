# CardArena Games Registry

This directory holds game rule modules implementing the `BaseGame` interface defined in `app.game_engine.game`.

## Implemented Games
- **Hearts** (`hearts.py`) — see `docs/games/hearts.md`.

## Architecture Policy
- Player `display_name` is set by `GameSessionManager` from the authoritative room/user records, and `is_connected` in player views is derived from live WebSocket connections. Games should not maintain their own connection state.
- All games must inherit from `app.game_engine.BaseGame` and register themselves with `@GameRegistry.register("<game_type>")`.

## Required Game Engine Contract

When adding a new game in subsequent phases, implement the following abstract methods:

```python
from app.game_engine import BaseGame, GameAction, GameEvent, GameRegistry, PlayerGameView

@GameRegistry.register("hearts")
class HeartsGame(BaseGame):
    def initialize_game(self, player_ids: list[str]) -> list[GameEvent]: ...
    def start_game(self) -> list[GameEvent]: ...
    def validate_action(self, action: GameAction) -> tuple[bool, str]: ...
    def apply_action(self, action: GameAction) -> list[GameEvent]: ...
    def get_valid_actions(self, player_id: str) -> list[str]: ...
    def next_turn(self) -> str: ...
    def is_round_complete(self) -> bool: ...
    def is_game_complete(self) -> bool: ...
    def calculate_score(self) -> dict: ...
    def get_player_view(self, player_id: str) -> PlayerGameView: ...
```

## Provably Fair Dealing

Games should obtain their deck from the shared commit/reveal mechanism instead of `Deck.shuffle()`:

```python
deck, commit_event = self.create_committed_deck(round_number)          # standard-52
# or: self.create_committed_deck(round_number, canonical_cards=cards, deck_definition="<documented-name>")
events.append(commit_event)            # must be emitted with (before) the deal
...
reveal_event = self.reveal_fairness(round_number)   # once that deal no longer hides anything
```

Any round still unrevealed at `GAME_OVER` is revealed by `GameSessionManager`. A custom
`deck_definition` must be documented in `docs/architecture/provably-fair.md` so players can verify it.

## Planned Games Roadmap
1. **Hearts**: 4-player trick avoidance game
2. **28**: Strategic bidding and trump suit trick play
3. **Teen Patti**: 3-card poker/show game
4. **Bluff**: Deception card discard and challenge mechanics
5. **Napoleon**: 5-player classic British/Asian card game
6. **Joker**: Wildcard and sequence card game
