# Hearts Game Rules & Architecture (Phase 2.1)

## 1. Implemented Hearts Rules

The authoritative Hearts engine enforces standard 4-player American Hearts rules:
- **Player Count**: Strictly 4 players.
- **Deck & Deal**: Standard 52-card deck dealt 13 cards per player via `secrets.randbelow`.
- **Passing Cycle**:
  - Round 1: Pass Left
  - Round 2: Pass Right
  - Round 3: Pass Across
  - Round 4: Hold (No passing, direct play)
  - Repeats cyclically ($n \pmod 4$).
- **Pass Verification**: Exactly 3 cards owned by the source player. The target player is strictly computed server-side by the pass rotation and cannot be spoofed or redirected by client payload fields.
- **Trick 1 Opening**: The holder of the 2 of Clubs ($2\clubsuit$) is authoritatively identified and MUST lead with $2\clubsuit$.
- **Follow-Suit Requirement**: Players must follow the led suit if they possess at least one card of that suit.
- **First Trick Restriction**: Point cards (Hearts and Queen of Spades $Q\spadesuit$) cannot be played on the first trick unless the player possesses only point cards.
- **Hearts-Breaking**: Hearts cannot be led until broken (played as a discard on an off-suit trick) or unless the player holds only Hearts.
- **Trick Resolution**: Highest rank of the led suit wins the trick. Off-suit cards (including Hearts and Spades) never win. The trick winner leads the subsequent trick.
- **Scoring**: Each Heart = 1 point; Queen of Spades $Q\spadesuit$ = 13 points (26 total points per round).
- **Shooting the Moon**: If one player takes all 26 points in a round, that player scores 0 points, and all 3 opponents receive +26 points.
- **Game Over Condition**: Match concludes when any player's cumulative score reaches or exceeds 100 points. The player with the lowest score wins. Post-game actions are strictly rejected.

---

## 2. Event Semantics

The event architecture distinguishes trick completion from full round conclusion:
- `CARD_PLAYED`: Individual card placed into the active trick.
- `TRICK_COMPLETED`: 4 cards played, winner determined, trick points awarded to trick winner.
- `ROUND_COMPLETED`: All 13 tricks finished, shooting-the-moon calculated, round points committed to cumulative total scores.
- `GAME_COMPLETED`: Score $\ge 100$, final winner declared.

All events receive monotonic, strictly increasing sequence numbers assigned by `GameSessionManager`.
