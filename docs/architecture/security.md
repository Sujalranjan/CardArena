# Security & Fairness Architecture (Phase 1.5 Hardening)

## 1. Identity & Anti-Spoofing Architecture

The backend strictly enforces the mapping:
```text
WebSocket Connection ──(verified JWT token)──> Authenticated user_id
```

### Invariants:
1. **No Client Trust for Player ID**:
   When a client dispatches an action frame, the server-side code derives `actor_player_id` directly from the authenticated WebSocket session. If a client injects a mismatched `"player_id"` key in their action payload, the WebSocket handler immediately flags a security alert, drops the frame, and returns an error:
   ```json
   {
     "type": "ERROR",
     "payload": { "error": "Player impersonation detected and rejected" }
   }
   ```
2. **Room Authorization Guard**:
   Upon WebSocket handshake, the server verifies:
   - Valid, unexpired JWT signature.
   - User exists in the database.
   - Room exists in the database.
   - User has an active membership record (`RoomPlayer`) in the specified room.
   Any failure terminates the connection with WebSocket close code `1008 (Policy Violation)`.

---

## 2. Dedicated GameSessionManager

To guarantee that game instances are never directly manipulated by raw network calls, all game mutations pass through the `GameSessionManager` layer:

```text
WebSocket Endpoint
      │
      ▼
GameSessionManager
  ├── 1. Authorize player identity (from session)
  ├── 2. Validate payload schema against typed Pydantic models
  ├── 3. Verify game session existence & room membership
  ├── 4. Call BaseGame.validate_action()
  ├── 5. Call BaseGame.apply_action()
  ├── 6. Record sequenceable GameEvent
  └── 7. Broadcast player-specific state projections (my_hand only)
```

---

## 3. Typed Action Architecture

Client actions are strictly parsed against explicit typed Pydantic schemas before reaching the game engine:
- `PLAY_CARD` (`PlayCardPayload` with required `card_id`)
- `DRAW_CARD` (`DrawCardPayload` with `count`)
- `DISCARD_CARD` (`DiscardCardPayload` with `card_ids`)
- `PASS_CARD` (`PassCardPayload` with `target_player_id`, `card_ids`)
- `BET` (`BetPayload` with `amount > 0`)
- `CALL`, `FOLD`, `END_TURN` (`CallPayload`, `FoldPayload`, `EndTurnPayload`)
- `CHALLENGE` (`ChallengePayload`)

Any extraneous fields (such as injected scores, winner overrides, or unauthorized hand modifications) are automatically stripped by Pydantic validation.

---

## 4. CSPRNG vs. Provably Fair Gameplay

CardArena draws a clear architectural distinction between unpredictable shuffling and verifiable commitment schemes:

### CSPRNG
- `Deck.shuffle()` uses `secrets.randbelow`, backed by the operating system's cryptographic random source (`/dev/urandom` / `BCryptGenRandom`). It remains available for games that do not use commitments.
- **Guarantee**: Shuffles are unpredictable to players, but not verifiable after the fact.

### Provably Fair Commit/Reveal (Implemented; used by Hearts)
- A 256-bit CSPRNG server seed per round; `SHA-256(seed)` is published before the deal; the deck order is derived deterministically from the seed (HMAC-SHA256 stream + unbiased Fisher-Yates); the seed is revealed when the round ends.
- **Guarantee**: Anyone can verify the deal's deck order was fixed when the commitment was published and not altered afterwards.
- **Not guaranteed**: that the seed itself was chosen randomly (there is no client seed in v1), absence of server/player collusion, or that the deployed code matches the documentation.
- Full specification and limitations: [provably-fair.md](provably-fair.md).
