/// <reference types="node" />
/**
 * Test helpers for fairness tests. Vectors are read from the shared file that the backend test
 * suite also checks against the Python implementation; random records use fresh CSPRNG bytes so
 * no fairness values are baked into the tests.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Card, FairnessRecord } from '../types';

export interface FairnessVectorFile {
  algorithm: string;
  deck_definition: string;
  canonical_deck: string[];
  canonical_deck_sha256: string;
  deal: { num_players: number; cards_per_player: number };
  vectors: {
    server_seed: string;
    commitment: string;
    deck_order: string[];
    dealt_hands: string[][];
  }[];
}

// Vitest runs from the frontend package root; the vectors live in the repository docs
export const fairnessVectors: FairnessVectorFile = JSON.parse(
  readFileSync(resolve(process.cwd(), '..', 'docs', 'architecture', 'fairness-test-vectors.json'), 'utf-8')
);

export function randomHex(bytes: number): string {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** A revealed record for a shared vector (its real seed, commitment and canonical deck hash). */
export function revealedVectorRecord(index: number, roundNumber: number, gameId: string): FairnessRecord {
  const v = fairnessVectors.vectors[index];
  return {
    game_id: gameId,
    round_number: roundNumber,
    algorithm: fairnessVectors.algorithm,
    commitment_scheme: 'SHA-256(server_seed)',
    commitment: v.commitment,
    deck_definition: fairnessVectors.deck_definition,
    canonical_deck_sha256: fairnessVectors.canonical_deck_sha256,
    revealed: true,
    server_seed: v.server_seed,
  };
}

/** An unrevealed record with random commitment values. */
export function committedRandomRecord(roundNumber: number, gameId: string): FairnessRecord {
  return {
    game_id: gameId,
    round_number: roundNumber,
    algorithm: fairnessVectors.algorithm,
    commitment_scheme: 'SHA-256(server_seed)',
    commitment: randomHex(32),
    deck_definition: fairnessVectors.deck_definition,
    canonical_deck_sha256: fairnessVectors.canonical_deck_sha256,
    revealed: false,
    server_seed: null,
  };
}

export function cardFromId(id: string): Card {
  const sep = id.lastIndexOf('_');
  return { id, suit: id.slice(0, sep) as Card['suit'], rank: id.slice(sep + 1) };
}
