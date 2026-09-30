import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { HeartsTable } from '../components/HeartsTable';
import type { PlayerGameView } from '../types';

const mockGameView: PlayerGameView = {
  game_id: 'test_game_1',
  game_type: 'hearts',
  phase: 'STARTING',
  viewer_id: 'p1',
  current_turn_player_id: null,
  round_number: 1,
  scores: { p1: 0, p2: 0, p3: 0, p4: 0 },
  players: [
    { id: 'p1', seat: 0, display_name: 'Alice', is_connected: true, card_count: 13 },
    { id: 'p2', seat: 1, display_name: 'Bob', is_connected: true, card_count: 13 },
    { id: 'p3', seat: 2, display_name: 'Charlie', is_connected: true, card_count: 13 },
    { id: 'p4', seat: 3, display_name: 'Dave', is_connected: true, card_count: 13 },
  ],
  my_hand: [
    { id: 'CLUBS_2', suit: 'CLUBS', rank: '2' },
    { id: 'HEARTS_A', suit: 'HEARTS', rank: 'A' },
    { id: 'SPADES_Q', suit: 'SPADES', rank: 'Q' },
  ],
  public_state: {
    round_number: 1,
    pass_direction: 'LEFT',
    has_passed: { p1: false, p2: false, p3: false, p4: false },
    hearts_broken: false,
    is_first_trick: true,
    current_trick: [],
    completed_tricks: 0,
    round_points: { p1: 0, p2: 0, p3: 0, p4: 0 },
    total_scores: { p1: 0, p2: 0, p3: 0, p4: 0 },
  },
  valid_actions: ['PASS_CARD'],
};

describe('HeartsTable Component', () => {
  it('renders round, pass direction, and viewer hand', () => {
    render(
      <HeartsTable
        gameView={mockGameView}
        onPlayCard={() => {}}
        onPassCards={() => {}}
      />
    );

    expect(screen.getByText(/Round 1/i)).toBeDefined();
    expect(screen.getByText(/Pass:/i)).toBeDefined();
    expect(screen.getByText(/LEFT/i)).toBeDefined();
    expect(screen.getByText(/Your Hand/i)).toBeDefined();
    expect(screen.getByText(/Bob/i)).toBeDefined();
    expect(screen.getByText(/Charlie/i)).toBeDefined();
    expect(screen.getByText(/Dave/i)).toBeDefined();
  });
});
