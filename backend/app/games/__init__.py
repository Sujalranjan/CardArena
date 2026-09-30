"""Games package export, ensuring game modules are registered on import."""
from app.games.hearts import HeartsGame

__all__ = ["HeartsGame"]
