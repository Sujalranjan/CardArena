import { describe, expect, it } from 'vitest';
import {
  canonicalDeckHash,
  computeCommitment,
  dealtHandFromOrder,
  deterministicShuffle,
  handMatchesDeal,
  verifyFairnessRecord,
} from '../fairness/verify';
import { fairnessVectors, randomHex, revealedVectorRecord } from './fairnessTestData';

const canonical = fairnessVectors.canonical_deck;
const { num_players, cards_per_player } = fairnessVectors.deal;

function flipFirstHexChar(hex: string): string {
  return (hex[0] === '0' ? '1' : '0') + hex.slice(1);
}

describe('Browser fairness verifier matches the backend implementation', () => {
  it('reproduces the shared commitments, canonical hash and deck orders', async () => {
    expect(fairnessVectors.vectors.length).toBeGreaterThan(0);
    expect(await canonicalDeckHash(canonical)).toBe(fairnessVectors.canonical_deck_sha256);
    for (const v of fairnessVectors.vectors) {
      expect(await computeCommitment(v.server_seed)).toBe(v.commitment);
      expect(await deterministicShuffle(canonical, v.server_seed)).toEqual(v.deck_order);
    }
  });

  it('derives each seat hand exactly as the engine Deck.deal did', () => {
    for (const v of fairnessVectors.vectors) {
      for (let seat = 0; seat < num_players; seat++) {
        expect(dealtHandFromOrder(v.deck_order, seat, num_players, cards_per_player)).toEqual(v.dealt_hands[seat]);
      }
    }
  });

  it('verifies a revealed record and re-derives its deck', async () => {
    for (const [i, v] of fairnessVectors.vectors.entries()) {
      const result = await verifyFairnessRecord(revealedVectorRecord(i, 1, 'g'), canonical);
      expect(result).toMatchObject({ supported: true, commitmentValid: true, canonicalDeckValid: true });
      expect(result.deckOrder).toEqual(v.deck_order);
    }
  });

  it('fails when the seed, commitment or canonical deck is tampered with', async () => {
    const record = revealedVectorRecord(0, 1, 'g');

    const badSeed = await verifyFairnessRecord({ ...record, server_seed: flipFirstHexChar(record.server_seed!) }, canonical);
    expect(badSeed.commitmentValid).toBe(false);
    expect(badSeed.deckOrder).toBeNull();

    const badCommitment = await verifyFairnessRecord({ ...record, commitment: flipFirstHexChar(record.commitment) }, canonical);
    expect(badCommitment.commitmentValid).toBe(false);
    expect(badCommitment.deckOrder).toBeNull();

    const badDeck = await verifyFairnessRecord(record, [...canonical].reverse());
    expect(badDeck.canonicalDeckValid).toBe(false);
    expect(badDeck.deckOrder).toBeNull();

    const notHex = await verifyFairnessRecord({ ...record, server_seed: 'zz' }, canonical);
    expect(notHex.commitmentValid).toBe(false);
  });

  it('does not verify unrevealed or unsupported records', async () => {
    const record = revealedVectorRecord(0, 1, 'g');
    const hidden = await verifyFairnessRecord({ ...record, revealed: false, server_seed: null }, canonical);
    expect(hidden).toMatchObject({ supported: true, commitmentValid: false, deckOrder: null });
    const unsupported = await verifyFairnessRecord({ ...record, algorithm: randomHex(4) }, canonical);
    expect(unsupported.supported).toBe(false);
  });

  it('checks a dealt hand against the derived deck order', () => {
    const v = fairnessVectors.vectors[0];
    const snapshot = { cardIds: v.dealt_hands[1], seat: 1, numPlayers: num_players, cardsPerPlayer: cards_per_player };
    expect(handMatchesDeal(snapshot, v.deck_order)).toBe(true);
    expect(handMatchesDeal({ ...snapshot, seat: 2 }, v.deck_order)).toBe(false);
    expect(handMatchesDeal(snapshot, fairnessVectors.vectors[1].deck_order)).toBe(false);
  });
});
