# CardArena Games Registry

This directory holds game rule modules implementing the `BaseGame` interface defined in `app.game_engine.game`.

## Architecture Policy: Zero Game Rules in Phase 1

As mandated by Phase 1 requirements:
- No concrete card game rules (Hearts, 28, Teen Patti, Bluff, Napoleon, Joker) are implemented in Phase 1.
- All future games must inherit from `app.game_engine.BaseGame` and register themselves with `@GameRegistry.register("<game_type>")`.

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

## Planned Games Roadmap
1. **Hearts**: 4-player trick avoidance game
2. **28**: Strategic bidding and trump suit trick play
3. **Teen Patti**: 3-card poker/show game
4. **Bluff**: Deception card discard and challenge mechanics
5. **Napoleon**: 5-player classic British/Asian card game
6. **Joker**: Wildcard and sequence card game
