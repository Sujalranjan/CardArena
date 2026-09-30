"""Provably fair commit/reveal shuffling (CardArena fairness v1).

This module depends only on the Python standard library so it can be copied and run
independently to verify a revealed round. See docs/architecture/provably-fair.md.

Algorithm "CARDARENA-HMAC-SHA256-FY-v1":
  server_seed  = 32 bytes from the OS CSPRNG (secrets.token_bytes)
  commitment   = hex(SHA-256(server_seed))
  byte stream  = HMAC-SHA256(key=server_seed, msg=STREAM_LABEL || uint64_be(counter)),
                 counter = 0, 1, 2, ...; the 32-byte blocks are concatenated
  rand_below(n): read 4 bytes as uint32_be x; accept if x < 2^32 - (2^32 mod n),
                 otherwise read the next 4 bytes (rejection sampling, no modulo bias);
                 return x mod n
  shuffle      : deck = list(canonical_deck)
                 for i = len(deck)-1 down to 1: j = rand_below(i + 1); swap deck[i], deck[j]
"""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

ALGORITHM = "CARDARENA-HMAC-SHA256-FY-v1"
COMMITMENT_SCHEME = "SHA-256(server_seed)"
STREAM_LABEL = b"cardarena-shuffle-v1"
SEED_BYTES = 32

# Documented canonical deck definitions (ordered card IDs before shuffling).
# "standard-52": suits SPADES, HEARTS, DIAMONDS, CLUBS; within each suit ranks 2..10, J, Q, K, A.
STANDARD_52 = "standard-52"
DECK_DEFINITIONS: Dict[str, List[str]] = {
    STANDARD_52: [
        f"{suit}_{rank}"
        for suit in ("SPADES", "HEARTS", "DIAMONDS", "CLUBS")
        for rank in ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
    ],
}


def canonical_deck_hash(canonical_deck: Sequence[str]) -> str:
    """SHA-256 over the canonical card IDs joined by ',' (UTF-8)."""
    return hashlib.sha256(",".join(canonical_deck).encode("utf-8")).hexdigest()


# ---------------- Primitives ----------------
def generate_server_seed() -> bytes:
    """256-bit secret seed from the operating system CSPRNG."""
    return secrets.token_bytes(SEED_BYTES)


def compute_commitment(server_seed: bytes) -> str:
    return hashlib.sha256(server_seed).hexdigest()


def verify_commitment(server_seed_hex: str, commitment: str) -> bool:
    """True only if the revealed seed hashes to the published commitment."""
    try:
        seed = bytes.fromhex(server_seed_hex)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(compute_commitment(seed), str(commitment).lower())


class _SeededStream:
    """Deterministic byte stream: HMAC-SHA256(seed, STREAM_LABEL || uint64_be(counter))."""

    def __init__(self, server_seed: bytes):
        self._seed = server_seed
        self._counter = 0
        self._buffer = b""

    def read(self, n: int) -> bytes:
        while len(self._buffer) < n:
            block = hmac.new(
                self._seed, STREAM_LABEL + self._counter.to_bytes(8, "big"), hashlib.sha256
            ).digest()
            self._buffer += block
            self._counter += 1
        out, self._buffer = self._buffer[:n], self._buffer[n:]
        return out

    def rand_below(self, n: int) -> int:
        """Uniform integer in [0, n) via rejection sampling on uint32 values."""
        if n <= 0:
            raise ValueError("n must be positive")
        limit = 2**32 - (2**32 % n)
        while True:
            x = int.from_bytes(self.read(4), "big")
            if x < limit:
                return x % n


def deterministic_shuffle(canonical_deck: Sequence[str], server_seed: bytes) -> List[str]:
    """Fisher-Yates shuffle of card IDs driven by the seeded stream."""
    deck = list(canonical_deck)
    stream = _SeededStream(server_seed)
    for i in range(len(deck) - 1, 0, -1):
        j = stream.rand_below(i + 1)
        deck[i], deck[j] = deck[j], deck[i]
    return deck


# ---------------- Verification ----------------
@dataclass(frozen=True)
class FairnessVerification:
    commitment_valid: bool
    deck_order: Optional[List[str]]

    @property
    def ok(self) -> bool:
        return self.commitment_valid and self.deck_order is not None


def verify_round(
    server_seed_hex: str,
    commitment: str,
    canonical_deck: Sequence[str],
    expected_deck_order: Optional[Sequence[str]] = None,
) -> FairnessVerification:
    """
    Independent verification: checks the seed against the commitment and re-derives the
    deck order. If `expected_deck_order` is given, it must match the derived order exactly.
    """
    if not verify_commitment(server_seed_hex, commitment):
        return FairnessVerification(commitment_valid=False, deck_order=None)
    order = deterministic_shuffle(canonical_deck, bytes.fromhex(server_seed_hex))
    if expected_deck_order is not None and list(expected_deck_order) != order:
        return FairnessVerification(commitment_valid=True, deck_order=None)
    return FairnessVerification(commitment_valid=True, deck_order=order)


def verify_public_record(
    record: Dict[str, Any], canonical_deck: Optional[Sequence[str]] = None
) -> FairnessVerification:
    """
    Verifies a revealed public record as published in game views / FAIRNESS_REVEALED.
    The canonical deck is taken from the documented definition unless supplied, and must
    match the record's published canonical_deck_sha256.
    """
    failed = FairnessVerification(commitment_valid=False, deck_order=None)
    if record.get("algorithm") != ALGORITHM or not record.get("server_seed"):
        return failed
    if canonical_deck is None:
        canonical_deck = DECK_DEFINITIONS.get(record.get("deck_definition", ""))
        if canonical_deck is None:
            return failed
    if canonical_deck_hash(canonical_deck) != record.get("canonical_deck_sha256"):
        return failed
    return verify_round(record["server_seed"], record["commitment"], canonical_deck)


# ---------------- Server-side ledger ----------------
class FairnessRound:
    """One committed shuffle. The seed stays private until reveal() is called."""

    def __init__(
        self, game_id: str, round_number: int, canonical_deck: Sequence[str], deck_definition: str
    ):
        self.game_id = game_id
        self.round_number = round_number
        self.canonical_deck: List[str] = list(canonical_deck)
        self.deck_definition = deck_definition
        self._server_seed = generate_server_seed()
        self.commitment = compute_commitment(self._server_seed)
        self.revealed = False

    def deck_order(self) -> List[str]:
        return deterministic_shuffle(self.canonical_deck, self._server_seed)

    def reveal(self) -> None:
        self.revealed = True

    def public_record(self) -> Dict[str, Any]:
        """
        Client-safe record. `server_seed` is None until the round has been revealed.
        Card IDs are deliberately not listed; the deck is identified by definition name + hash.
        """
        return {
            "game_id": self.game_id,
            "round_number": self.round_number,
            "algorithm": ALGORITHM,
            "commitment_scheme": COMMITMENT_SCHEME,
            "commitment": self.commitment,
            "deck_definition": self.deck_definition,
            "canonical_deck_sha256": canonical_deck_hash(self.canonical_deck),
            "revealed": self.revealed,
            "server_seed": self._server_seed.hex() if self.revealed else None,
        }


class FairnessLedger:
    """Per-game record of committed shuffles, keyed by round number."""

    def __init__(self, game_id: str):
        self.game_id = game_id
        self._rounds: Dict[int, FairnessRound] = {}

    def commit(
        self, round_number: int, canonical_deck: Sequence[str], deck_definition: str = STANDARD_52
    ) -> FairnessRound:
        if round_number in self._rounds:
            raise ValueError(f"Round {round_number} already has a fairness commitment")
        fair_round = FairnessRound(self.game_id, round_number, canonical_deck, deck_definition)
        self._rounds[round_number] = fair_round
        return fair_round

    def get(self, round_number: int) -> Optional[FairnessRound]:
        return self._rounds.get(round_number)

    def unrevealed(self) -> List[FairnessRound]:
        return [r for r in self._rounds.values() if not r.revealed]

    def public_records(self) -> List[Dict[str, Any]]:
        return [r.public_record() for r in sorted(self._rounds.values(), key=lambda r: r.round_number)]


if __name__ == "__main__":
    # Usage: python fairness.py record.json   (a revealed public record)
    import json
    import sys

    with open(sys.argv[1], encoding="utf-8") as fh:
        result = verify_public_record(json.load(fh))
    print(json.dumps({"commitment_valid": result.commitment_valid, "deck_order": result.deck_order}))
    sys.exit(0 if result.ok else 1)
