/**
 * In-browser verifier for CardArena provably-fair records.
 *
 * Implements the published specification in docs/architecture/provably-fair.md so players can
 * check a revealed round without trusting the server's own verification. Kept in sync with the
 * backend implementation by docs/architecture/fairness-test-vectors.json (tested on both sides).
 */
import type { FairnessRecord } from '../types';

/** Algorithm this verifier implements; records with any other algorithm are not verified. */
export const SUPPORTED_ALGORITHM = 'CARDARENA-HMAC-SHA256-FY-v1';
const STREAM_LABEL = 'cardarena-shuffle-v1';
const UINT32_RANGE = 2 ** 32;

export interface FairnessVerificationResult {
  supported: boolean;
  commitmentValid: boolean;
  canonicalDeckValid: boolean;
  deckOrder: string[] | null;
}

export interface DealtHandSnapshot {
  cardIds: string[];
  seat: number;
  numPlayers: number;
  cardsPerPlayer: number;
}

export function isWebCryptoAvailable(): boolean {
  return typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.subtle !== 'undefined';
}

function hexToBytes(hex: string): Uint8Array<ArrayBuffer> | null {
  if (hex.length % 2 !== 0 || !/^[0-9a-fA-F]*$/.test(hex)) return null;
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

async function sha256Hex(data: Uint8Array<ArrayBuffer>): Promise<string> {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest('SHA-256', data)));
}

export async function computeCommitment(seedHex: string): Promise<string | null> {
  const seed = hexToBytes(seedHex);
  return seed ? sha256Hex(seed) : null;
}

/** SHA-256 over the canonical card IDs joined by ',' (UTF-8). */
export async function canonicalDeckHash(cardIds: string[]): Promise<string> {
  return sha256Hex(new TextEncoder().encode(cardIds.join(',')));
}

/** Byte stream: HMAC-SHA256(key=seed, msg=label || uint64_be(counter)), counter = 0, 1, ... */
class SeededStream {
  private buffer: number[] = [];
  private counter = 0n;
  private readonly key: Promise<CryptoKey>;

  constructor(seed: Uint8Array<ArrayBuffer>) {
    this.key = crypto.subtle.importKey('raw', seed, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  }

  private async read(n: number): Promise<number[]> {
    const label = new TextEncoder().encode(STREAM_LABEL);
    while (this.buffer.length < n) {
      const msg = new Uint8Array(label.length + 8);
      msg.set(label, 0);
      new DataView(msg.buffer).setBigUint64(label.length, this.counter, false);
      const block = new Uint8Array(await crypto.subtle.sign('HMAC', await this.key, msg));
      this.buffer.push(...block);
      this.counter += 1n;
    }
    return this.buffer.splice(0, n);
  }

  /** Uniform integer in [0, n) by rejection sampling on uint32 values. */
  async randBelow(n: number): Promise<number> {
    const limit = UINT32_RANGE - (UINT32_RANGE % n);
    for (;;) {
      const [a, b, c, d] = await this.read(4);
      const x = ((a << 24) >>> 0) + (b << 16) + (c << 8) + d;
      if (x < limit) return x % n;
    }
  }
}

/** Fisher-Yates shuffle of the canonical deck driven by the seeded stream. */
export async function deterministicShuffle(canonicalDeck: string[], seedHex: string): Promise<string[] | null> {
  const seed = hexToBytes(seedHex);
  if (!seed) return null;
  const deck = [...canonicalDeck];
  const stream = new SeededStream(seed);
  for (let i = deck.length - 1; i > 0; i--) {
    const j = await stream.randBelow(i + 1);
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

/**
 * Verifies a revealed public record against the given canonical deck:
 * SHA-256(seed) == commitment, the canonical deck matches the published hash, and the
 * deterministic deck order is re-derived.
 */
export async function verifyFairnessRecord(
  record: FairnessRecord,
  canonicalDeck: string[]
): Promise<FairnessVerificationResult> {
  const failed = { commitmentValid: false, canonicalDeckValid: false, deckOrder: null };
  if (record.algorithm !== SUPPORTED_ALGORITHM) return { supported: false, ...failed };
  if (!record.revealed || !record.server_seed) return { supported: true, ...failed };

  const commitment = await computeCommitment(record.server_seed);
  const commitmentValid = commitment !== null && commitment === record.commitment.toLowerCase();
  const canonicalDeckValid = (await canonicalDeckHash(canonicalDeck)) === record.canonical_deck_sha256;
  const deckOrder =
    commitmentValid && canonicalDeckValid ? await deterministicShuffle(canonicalDeck, record.server_seed) : null;
  return { supported: true, commitmentValid, canonicalDeckValid, deckOrder };
}

/**
 * Cards a seat receives from the engine's Deck.deal: round-robin, drawing from the END of the
 * order list, so seat s gets order[len - 1 - (k * numPlayers + s)] for k = 0..cardsPerPlayer-1.
 */
export function dealtHandFromOrder(
  deckOrder: string[],
  seat: number,
  numPlayers: number,
  cardsPerPlayer: number
): string[] {
  const hand: string[] = [];
  for (let k = 0; k < cardsPerPlayer; k++) {
    hand.push(deckOrder[deckOrder.length - 1 - (k * numPlayers + seat)]);
  }
  return hand;
}

export function handMatchesDeal(snapshot: DealtHandSnapshot, deckOrder: string[]): boolean {
  const expected = dealtHandFromOrder(deckOrder, snapshot.seat, snapshot.numPlayers, snapshot.cardsPerPlayer);
  return (
    expected.length === snapshot.cardIds.length &&
    [...expected].sort().join(',') === [...snapshot.cardIds].sort().join(',')
  );
}
