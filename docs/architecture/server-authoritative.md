# Server-Authoritative Architecture & Hidden Information

CardArena strictly adheres to a **server-authoritative model**:
1. The client is NEVER trusted to determine card hands, card order, turn legality, deck state, scores, or winner determinations.
2. Frontend validation is strictly a UX convenience; server validation is the solitary authority.

## Hidden Information Guarantee

In multiplayer card games, exposing opponents' private hands via network payloads—even if the UI hides them—creates severe cheating vulnerabilities.

CardArena implements player-specific state projections:

```
[ Authoritative BaseGameState ]
- deck: [52 cards]
- player_hands:
    Alice: [A♠, K♥, 7♣]
    Bob:   [Q♦, 10♠, 2♥]
          │
          ├──────────────────────────┐
          ▼                          ▼
 [ Alice's Projection ]     [ Bob's Projection ]
 - my_hand: [A♠, K♥, 7♣]     - my_hand: [Q♦, 10♠, 2♥]
 - Bob: { card_count: 3 }    - Alice: { card_count: 3 }
```

### Verification
Tests in `backend/tests/test_hidden_info.py` rigorously assert that:
- Opponent hands are completely stripped before serialization.
- Only card counts and public table states are broadcast.
