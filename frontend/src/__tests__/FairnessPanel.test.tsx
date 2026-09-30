import { render, screen, fireEvent, within } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { FairnessPanel } from '../components/FairnessPanel';
import { HeartsTable } from '../components/HeartsTable';
import { ApiService } from '../services/api';
import type { DeckDefinition, FairnessRecord, PlayerGameView } from '../types';
import {
  cardFromId,
  committedRandomRecord,
  fairnessVectors,
  randomHex,
  revealedVectorRecord,
} from './fairnessTestData';

const deckDefinition = (): DeckDefinition => ({
  name: fairnessVectors.deck_definition,
  algorithm: fairnessVectors.algorithm,
  cards: fairnessVectors.canonical_deck,
  sha256: fairnessVectors.canonical_deck_sha256,
});

function expand() {
  fireEvent.click(screen.getByRole('button', { name: /Provably Fair/i }));
}

afterEach(() => vi.restoreAllMocks());

describe('FairnessPanel', () => {
  it('renders nothing when the game view carries no fairness records', () => {
    const { container } = render(<FairnessPanel records={[]} currentRound={1} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders commitment details from the supplied record and hides the seed before reveal', () => {
    const gameId = randomHex(8);
    const record = committedRandomRecord(1, gameId);
    render(<FairnessPanel records={[record]} currentRound={1} />);

    // Collapsed summary already shows the current round status
    expect(screen.getByText(/Round 1: Committed — seed hidden/)).toBeTruthy();
    expand();

    const row = screen.getByTestId('fairness-round-1');
    expect(within(row).getByTestId('fairness-commitment-1').textContent).toContain(record.commitment);
    expect(within(row).getByText(record.algorithm)).toBeTruthy();
    expect(within(row).getByText(record.deck_definition)).toBeTruthy();
    expect(within(row).getByText('Committed — seed hidden')).toBeTruthy();
    expect(screen.queryByText(/Server seed/i)).toBeNull();
    expect(screen.queryByTestId('fairness-seed-1')).toBeNull();
    expect(screen.queryByRole('button', { name: /Verify round/i })).toBeNull();
  });

  it('never renders a seed for a record that is not marked revealed', () => {
    const leakedSeed = randomHex(32);
    const record: FairnessRecord = { ...committedRandomRecord(2, randomHex(8)), server_seed: leakedSeed };
    const { container } = render(<FairnessPanel records={[record]} currentRound={2} />);
    expand();
    expect(container.textContent).not.toContain(leakedSeed);
  });

  it('shows the server seed and revealed status after reveal, and verifies it', async () => {
    const gameId = randomHex(8);
    const record = revealedVectorRecord(0, 1, gameId);
    const loadDeckDefinition = vi.fn().mockResolvedValue(deckDefinition());
    render(<FairnessPanel records={[record]} currentRound={1} loadDeckDefinition={loadDeckDefinition} />);
    expand();

    expect(screen.getByTestId('fairness-seed-1').textContent).toContain(record.server_seed!);
    expect(screen.getByTestId('fairness-commitment-1').textContent).toContain(record.commitment);
    expect(within(screen.getByTestId('fairness-round-1')).getByText('Revealed')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Verify round 1' }));
    const result = await screen.findByTestId('fairness-result-1');
    expect(loadDeckDefinition).toHaveBeenCalledWith(record.deck_definition);
    expect(result.textContent).toContain('Verified');
    expect(result.textContent).toContain('Seed matches commitment');
    expect(result.textContent).toContain('Canonical deck matches published hash');
  });

  it('reports failure when a revealed seed does not match its commitment', async () => {
    const record = { ...revealedVectorRecord(0, 1, randomHex(8)), commitment: randomHex(32) };
    render(
      <FairnessPanel records={[record]} currentRound={1} loadDeckDefinition={vi.fn().mockResolvedValue(deckDefinition())} />
    );
    expand();
    fireEvent.click(screen.getByRole('button', { name: 'Verify round 1' }));
    const result = await screen.findByTestId('fairness-result-1');
    expect(result.textContent).toContain('Verification FAILED');
    expect(result.textContent).toContain('Seed does NOT match commitment');
  });

  it('checks the observed dealt hand when one is available', async () => {
    const v = fairnessVectors.vectors[0];
    const { num_players, cards_per_player } = fairnessVectors.deal;
    const record = revealedVectorRecord(0, 1, randomHex(8));
    const renderWithSeat = (seat: number, handSeat: number) =>
      render(
        <FairnessPanel
          records={[record]}
          currentRound={1}
          loadDeckDefinition={vi.fn().mockResolvedValue(deckDefinition())}
          getDealtHand={() => ({ cardIds: v.dealt_hands[handSeat], seat, numPlayers: num_players, cardsPerPlayer: cards_per_player })}
        />
      );

    const { unmount } = renderWithSeat(2, 2);
    expand();
    fireEvent.click(screen.getByRole('button', { name: 'Verify round 1' }));
    expect((await screen.findByTestId('fairness-result-1')).textContent).toContain('Your dealt hand matches the committed deck');
    unmount();

    renderWithSeat(2, 3);
    expand();
    fireEvent.click(screen.getByRole('button', { name: 'Verify round 1' }));
    const result = await screen.findByTestId('fairness-result-1');
    expect(result.textContent).toContain('Your dealt hand does NOT match the committed deck');
    expect(result.textContent).toContain('Verification FAILED');
  });

  it('separates the active round from previously revealed rounds for any number of rounds', () => {
    const gameId = randomHex(8);
    const roundCount = fairnessVectors.vectors.length + 1;
    const records: FairnessRecord[] = [];
    for (let round = 1; round < roundCount; round++) {
      records.push(revealedVectorRecord(round - 1, round, gameId));
    }
    records.push(committedRandomRecord(roundCount, gameId));

    render(<FairnessPanel records={records} currentRound={roundCount} />);
    expect(screen.getByText(new RegExp(`Round ${roundCount}: Committed — seed hidden`))).toBeTruthy();
    expand();

    const activeSection = screen.getByText('Active round').parentElement as HTMLElement;
    const revealedSection = screen.getByText('Revealed rounds').parentElement as HTMLElement;
    expect(within(activeSection).getByTestId(`fairness-round-${roundCount}`)).toBeTruthy();
    expect(within(activeSection).queryByTestId(/fairness-seed-/)).toBeNull();
    for (let round = 1; round < roundCount; round++) {
      const row = within(revealedSection).getByTestId(`fairness-round-${round}`);
      expect(within(row).getByTestId(`fairness-seed-${round}`).textContent).toContain(records[round - 1].server_seed!);
    }
    expect(screen.getAllByText('Revealed').length).toBe(roundCount - 1);
  });

  it('shows whatever values it is given (nothing fixed in the UI)', () => {
    const first = committedRandomRecord(1, randomHex(8));
    const second = committedRandomRecord(1, randomHex(8));
    expect(first.commitment).not.toBe(second.commitment);

    const { unmount } = render(<FairnessPanel records={[first]} currentRound={1} />);
    expand();
    expect(screen.getByTestId('fairness-commitment-1').textContent).toContain(first.commitment);
    unmount();

    render(<FairnessPanel records={[{ ...second, algorithm: randomHex(6), deck_definition: randomHex(6) }]} currentRound={1} />);
    expand();
    expect(screen.getByTestId('fairness-commitment-1').textContent).toContain(second.commitment);
    expect(screen.queryByText(first.commitment)).toBeNull();
  });
});

describe('HeartsTable fairness integration', () => {
  const v = fairnessVectors.vectors[0];
  const seat = 1;
  const playerIds = Array.from({ length: fairnessVectors.deal.num_players }, () => randomHex(6));
  const gameId = randomHex(8);

  const baseView = (overrides: Partial<PlayerGameView>): PlayerGameView => ({
    game_id: gameId,
    game_type: 'hearts',
    phase: 'STARTING',
    viewer_id: playerIds[seat],
    current_turn_player_id: null,
    round_number: 1,
    scores: Object.fromEntries(playerIds.map((id) => [id, 0])),
    players: playerIds.map((id, i) => ({
      id, seat: i, display_name: `Name ${randomHex(3)}`, is_connected: true, card_count: v.dealt_hands[i].length,
    })),
    my_hand: v.dealt_hands[seat].map(cardFromId),
    public_state: {
      round_number: 1,
      pass_direction: 'LEFT',
      has_passed: Object.fromEntries(playerIds.map((id) => [id, false])),
      hearts_broken: false,
      is_first_trick: true,
      current_trick: [],
      completed_tricks: 0,
      round_points: Object.fromEntries(playerIds.map((id) => [id, 0])),
      total_scores: Object.fromEntries(playerIds.map((id) => [id, 0])),
    },
    valid_actions: ['PASS_CARD'],
    ...overrides,
  });

  it('shows the commitment without seed or opponent cards, then verifies the dealt hand after reveal', async () => {
    vi.spyOn(ApiService, 'getDeckDefinition').mockResolvedValue(deckDefinition());
    const revealed = revealedVectorRecord(0, 1, gameId);
    const committed: FairnessRecord = { ...revealed, revealed: false, server_seed: null };

    const { container, rerender } = render(
      <HeartsTable gameView={baseView({ fairness: [committed] })} onPlayCard={() => {}} onPassCards={() => {}} />
    );
    expand();
    expect(screen.getByTestId('fairness-commitment-1').textContent).toContain(committed.commitment);
    expect(container.textContent).not.toContain(revealed.server_seed!);
    for (let other = 0; other < playerIds.length; other++) {
      if (other === seat) continue;
      for (const cardId of v.dealt_hands[other]) {
        expect(screen.queryByTestId(`card-${cardId}`)).toBeNull();
      }
    }

    // Round over: seed revealed by the server, hand now empty
    rerender(
      <HeartsTable
        gameView={baseView({ phase: 'IN_PROGRESS', my_hand: [], fairness: [revealed] })}
        onPlayCard={() => {}}
        onPassCards={() => {}}
      />
    );
    expect(screen.getByTestId('fairness-seed-1').textContent).toContain(revealed.server_seed!);
    fireEvent.click(screen.getByRole('button', { name: 'Verify round 1' }));
    const result = await screen.findByTestId('fairness-result-1');
    expect(result.textContent).toContain('Verified');
    expect(result.textContent).toContain('Your dealt hand matches the committed deck');
  });
});
