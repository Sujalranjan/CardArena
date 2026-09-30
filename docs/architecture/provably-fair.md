# Provably Fair Shuffling (Commit / Reveal)

Implementation: `backend/app/game_engine/fairness.py` (standard library only), integrated through
`BaseGame.create_committed_deck()` / `BaseGame.reveal_fairness()` and `GameSessionManager`.
Algorithm identifier: **`CARDARENA-HMAC-SHA256-FY-v1`**.

## 1. What "provably fair" means in CardArena

For every dealt round, the server publishes a cryptographic commitment to a secret seed before
any player receives cards from that deal. After the round ends the server reveals the seed.
Anyone can then check that:

1. the revealed seed hashes to the commitment published earlier, and
2. that seed, run through the documented algorithm on the documented canonical deck,
   reproduces the exact deck order used for the deal.

This proves **the deck order was fixed when the commitment was published, and was not chosen or
changed afterwards** (for example in reaction to passes, plays or which player is winning).
Nothing more is claimed; see [Limitations](#10-limitations).

## 2. Commitment phase

At the start of each round (Hearts: `HeartsGame.start_round`), the game calls
`create_committed_deck(round_number)`, which:

1. generates `server_seed = secrets.token_bytes(32)` (256 bits, OS CSPRNG),
2. computes `commitment = hex(SHA-256(server_seed))`,
3. records the round in the game's private `FairnessLedger`,
4. emits a `FAIRNESS_COMMITTED` event containing only the public record (no seed),
5. only then builds the deck from the seed.

The committed record binds these public fields (published together, before the deal reaches clients):

| Field | Meaning |
|---|---|
| `game_id`, `round_number` | Which session/round the commitment belongs to |
| `algorithm` | `CARDARENA-HMAC-SHA256-FY-v1` |
| `commitment_scheme` | `SHA-256(server_seed)` |
| `commitment` | 64 hex chars |
| `deck_definition` | Name of the documented canonical deck (e.g. `standard-52`) |
| `canonical_deck_sha256` | SHA-256 of the canonical card IDs joined by `,` (UTF-8) |
| `revealed` | `false` |
| `server_seed` | `null` |

Card IDs are intentionally not listed in the record, so the record can never be confused with,
or leak, hand contents.

## 3. Shuffle / dealing phase

The deck order is a pure function of `(server_seed, canonical deck)`. The game then deals it with
its normal rules. For Hearts, `Deck.deal(4, 13)` deals round-robin from the **end** of the order
list: seat `s` receives `order[-(1 + 4k + s)]` for `k = 0..12`. Hands are sorted afterwards for
display, which does not change which cards each seat received.

Clients cannot influence any step: there is no message type that accepts a seed, deck, shuffle or
commitment, and extra fields in `START_GAME` / game-action payloads are ignored.

## 4. Reveal phase

The seed is revealed by an authoritative server transition, never on request:

- **Hearts:** when the 13th trick of a round resolves (`_resolve_round_end`). At that point every
  card of that deal has been played, so the seed discloses nothing still hidden. The reveal event
  precedes the next round's new commitment, which uses a fresh seed.
- **Generic safety net:** when any game reaches `GAME_OVER`, `GameSessionManager` reveals every
  still-unrevealed round (`reveal_all_fairness`).

Reconnecting never triggers a reveal. Each round has its own seed; revealing round *n* reveals
nothing about round *n+1*.

## 5. Independent verification

The verifier needs only the revealed public record and this document. `fairness.py` has no
dependencies outside the Python standard library and can be run on its own:

```bash
python fairness.py record.json        # prints {"commitment_valid": ..., "deck_order": [...]}
```

Or in code:

```python
from fairness import verify_public_record
result = verify_public_record(record)       # canonical deck taken from DECK_DEFINITIONS
assert result.commitment_valid              # SHA-256(seed) == commitment
deck_order = result.deck_order              # exact order used for the deal
```

A player can then confirm their own dealt hand from `deck_order` using the dealing rule above.

## 6. Public information at each stage

| Stage | Public | 
|---|---|
| Before deal / during round | commitment record (no seed) — via `FAIRNESS_COMMITTED` and `game_view.fairness` |
| After round end | the same record with `revealed: true` and `server_seed` — via `FAIRNESS_REVEALED` and `game_view.fairness` |
| Reconnect | current `game_view.fairness`: commitments for all rounds, seeds only for revealed rounds |

WebSocket ordering: `FAIRNESS_COMMITTED` / `FAIRNESS_REVEALED` messages are broadcast before the
`GAME_STATE` views produced by the same action, so a round's commitment reaches every connected
client before any view containing that round's cards. Both events are also recorded in the
session's sequence-numbered event history; the WS payload carries the `sequence_number`.

## 7. Private information

- The seed of any round that has not been revealed (held only in server memory,
  `FairnessRound._server_seed`; never part of `BaseGameState` or any view).
- Players' hands, as before. The deck order of an unrevealed round would disclose all hands, which
  is why the seed is only revealed once the round is over.

## 8. Deterministic shuffle algorithm (`CARDARENA-HMAC-SHA256-FY-v1`)

```
canonical "standard-52": suits SPADES, HEARTS, DIAMONDS, CLUBS; ranks 2..10, J, Q, K, A;
                         card ID = "<SUIT>_<RANK>" (e.g. SPADES_2 ... CLUBS_A)

stream block c  = HMAC-SHA256(key = server_seed, msg = "cardarena-shuffle-v1" || uint64_be(c)),
                  c = 0, 1, 2, ...   (blocks concatenated into one byte stream)

rand_below(n):  repeat: x = next 4 stream bytes as uint32 big-endian
                        until x < 2^32 - (2^32 mod n)          # rejection sampling, no modulo bias
                return x mod n

shuffle:        deck = copy of canonical list
                for i = len(deck)-1 down to 1:
                    j = rand_below(i + 1)
                    swap deck[i], deck[j]
```

No Python `hash()`, `random` module or other runtime-specific behavior is involved; tests run the
shuffle in subprocesses with different `PYTHONHASHSEED` values, check a fixed known-answer vector,
and compare against an independent re-implementation of this specification.

Known-answer vector: seed `000102…1f` (bytes 0..31) → commitment
`630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd`, order begins
`CLUBS_A, DIAMONDS_6, CLUBS_J, HEARTS_7, DIAMONDS_5, CLUBS_4, DIAMONDS_2, SPADES_9`.

## 9. Cryptographic primitives

- `secrets.token_bytes(32)` — OS CSPRNG for the seed.
- SHA-256 (`hashlib`) — commitment and canonical-deck hash.
- HMAC-SHA256 (`hmac`) — deterministic byte stream keyed by the seed.
- `hmac.compare_digest` — constant-time commitment comparison.

## 10. Limitations

What this mechanism does **not** guarantee:

- **It does not prove the seed was random.** A commitment only proves the seed was fixed in
  advance. A malicious server could pick a seed it likes (e.g. by trying many seeds offline) before
  committing. There is no client-contributed entropy in v1, so players cannot rule this out.
- **It does not prevent collusion or information leaks.** The server knows every hand; the scheme
  cannot show that the server (or an operator) did not share hidden cards with a player.
- **It does not prove the running code matches this document**, or that the game rules were
  applied honestly after the deal. It verifies the deck order only.
- **It does not cover the client environment.** A compromised client or browser can display
  anything; verification is only as trustworthy as the verifier you run.
- **Unfinished rounds are never revealed.** If a session ends without reaching round end or
  `GAME_OVER` (e.g. backend restart — sessions are in memory only), that round's seed is lost and
  the round cannot be verified.
- **In-browser verification trusts the page it runs in.** The Hearts UI verifier (section 11) is
  served by the same server it checks; for full independence, run `fairness.py` separately.
- **The dealt-hand check needs an observed deal.** The UI can only compare your hand if this
  browser session saw it before any pass or play (it is kept in memory, not persisted); after a
  page reload mid-round it reports that the hand was not observed.
- Canonical decks must have unique card IDs. Games with multiple identical cards (e.g. two-deck
  games) need distinct IDs per physical card before they can use this mechanism.

## 11. Player-facing verification (Hearts UI)

`HeartsTable` renders a collapsible **Provably Fair** panel (`frontend/src/components/FairnessPanel.tsx`)
from `game_view.fairness`, the same public records described above. It shows the current round's
status in its header and, when expanded, separates the **active round** from **revealed rounds**.

- **Before reveal:** round number, algorithm, commitment, deck definition, status
  "Committed — seed hidden". No seed is rendered (the panel also refuses to render a seed on any
  record not marked `revealed`).
- **After reveal:** additionally the server seed, "Revealed" status and a **Verify** button.

Verification runs in the browser (`frontend/src/fairness/verify.ts`, Web Crypto; no server-side
verification call). It checks SHA-256(seed) against the commitment, fetches the canonical deck from
`GET /api/v1/fairness/deck-definitions/{deck_definition}` (public spec data, `DECK_DEFINITIONS`)
and checks it against the record's `canonical_deck_sha256`, re-derives the deck order, and — if
this browser observed the player's hand as dealt — confirms that hand equals the cards the
engine's dealing rule assigns to the player's seat. Web Crypto requires a secure context (HTTPS or
`localhost`); elsewhere the panel reports that verification is unavailable.

`docs/architecture/fairness-test-vectors.json` holds shared test vectors (seeds, commitments, deck
orders and dealt hands produced by the engine's `Deck.deal`). The backend and frontend test suites
both verify against it, so the Python and TypeScript implementations cannot drift apart silently.
