"""Public provably-fair reference data (documented canonical deck definitions)."""
from fastapi import APIRouter, HTTPException
from app.game_engine.fairness import ALGORITHM, DECK_DEFINITIONS, canonical_deck_hash

router = APIRouter(prefix="/fairness", tags=["fairness"])


@router.get("/deck-definitions/{name}")
async def get_deck_definition(name: str):
    """
    Returns a documented canonical deck (public specification data, no game state).
    Clients must still check `sha256` against the round's published canonical_deck_sha256.
    """
    cards = DECK_DEFINITIONS.get(name)
    if cards is None:
        raise HTTPException(status_code=404, detail=f"Unknown deck definition '{name}'")
    return {
        "name": name,
        "algorithm": ALGORITHM,
        "cards": list(cards),
        "sha256": canonical_deck_hash(cards),
    }
