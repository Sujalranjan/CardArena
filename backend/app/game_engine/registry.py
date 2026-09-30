"""Game Registry mapping game_type identifier strings to game classes."""
from typing import Callable, Dict, List, Type
from app.game_engine.game import BaseGame


class GameRegistry:
    """Central registry for pluggable card games."""

    _registry: Dict[str, Type[BaseGame]] = {}

    @classmethod
    def register(cls, game_type: str) -> Callable[[Type[BaseGame]], Type[BaseGame]]:
        """Decorator to register a game implementation class."""
        def decorator(game_class: Type[BaseGame]) -> Type[BaseGame]:
            cls._registry[game_type.lower()] = game_class
            return game_class
        return decorator

    @classmethod
    def register_class(cls, game_type: str, game_class: Type[BaseGame]) -> None:
        cls._registry[game_type.lower()] = game_class

    @classmethod
    def get(cls, game_type: str) -> Type[BaseGame]:
        normalized = game_type.lower()
        if normalized not in cls._registry:
            raise KeyError(f"Game type '{game_type}' is not registered.")
        return cls._registry[normalized]

    @classmethod
    def list_supported_games(cls) -> List[str]:
        return sorted(list(cls._registry.keys()))

    @classmethod
    def is_supported(cls, game_type: str) -> bool:
        return game_type.lower() in cls._registry
