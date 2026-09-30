import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { HeartsTable } from '../components/HeartsTable';
import type { PlayerGameView } from '../types';

const mockPassingGameView: PlayerGameView = {
  game_id: 'test_game_pass',
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
    { id: 'DIAMONDS_K', suit: 'DIAMONDS', rank: 'K' },
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

const mockPlayingGameView: PlayerGameView = {
  ...mockPassingGameView,
  phase: 'IN_PROGRESS',
  current_turn_player_id: 'p1',
  valid_actions: ['PLAY_CARD'],
};

const mockNotMyTurnGameView: PlayerGameView = {
  ...mockPassingGameView,
  phase: 'IN_PROGRESS',
  current_turn_player_id: 'p2',
  valid_actions: [],
};

const mockRound2GameView: PlayerGameView = {
  ...mockPassingGameView,
  round_number: 2,
  public_state: {
    ...mockPassingGameView.public_state,
    round_number: 2,
    pass_direction: 'RIGHT',
    hearts_broken: true,
  },
};

describe('HeartsTable Interactive & Security Suite', () => {
  it('enforces exactly 3 card selections before enabling pass button', () => {
    const handlePass = vi.fn();
    render(
      <HeartsTable
        gameView={mockPassingGameView}
        onPlayCard={() => {}}
        onPassCards={handlePass}
      />
    );

    const passBtn = screen.getByRole('button', { name: /Pass Cards/i }) as HTMLButtonElement;
    expect(passBtn.disabled).toBe(true);

    // Select 2 cards
    const card1 = screen.getByTestId('card-CLUBS_2');
    const card2 = screen.getByTestId('card-HEARTS_A');
    fireEvent.click(card1);
    fireEvent.click(card2);
    expect(screen.getByText(/Selected: 2 \/ 3 cards/i)).toBeDefined();
    expect(passBtn.disabled).toBe(true);

    // Select 3rd card -> Button becomes active
    const card3 = screen.getByTestId('card-SPADES_Q');
    fireEvent.click(card3);
    expect(screen.getByText(/Selected: 3 \/ 3 cards/i)).toBeDefined();
    expect(passBtn.disabled).toBe(false);

    // Click Pass
    fireEvent.click(passBtn);
    expect(handlePass).toHaveBeenCalledWith(['CLUBS_2', 'HEARTS_A', 'SPADES_Q']);
  });

  it('triggers onPlayCard with selected card ID when it is player turn', () => {
    const handlePlay = vi.fn();
    render(
      <HeartsTable
        gameView={mockPlayingGameView}
        onPlayCard={handlePlay}
        onPassCards={() => {}}
      />
    );

    expect(screen.getByText(/Your Turn to Play/i)).toBeDefined();
    const card2Clubs = screen.getByTestId('card-CLUBS_2');
    fireEvent.click(card2Clubs);
    expect(handlePlay).toHaveBeenCalledWith('CLUBS_2');
  });

  it('does not trigger onPlayCard when clicking card out of turn', () => {
    const handlePlay = vi.fn();
    render(
      <HeartsTable
        gameView={mockNotMyTurnGameView}
        onPlayCard={handlePlay}
        onPassCards={() => {}}
      />
    );

    expect(screen.getByText(/Waiting for current player\.\.\./i)).toBeDefined();
    const card2Clubs = screen.getByTestId('card-CLUBS_2');
    fireEvent.click(card2Clubs);
    expect(handlePlay).not.toHaveBeenCalled();
  });

  it('renders Round 2 state, RIGHT pass direction, and Hearts Broken badge', () => {
    render(
      <HeartsTable
        gameView={mockRound2GameView}
        onPlayCard={() => {}}
        onPassCards={() => {}}
      />
    );

    expect(screen.getByText(/Round 2/i)).toBeDefined();
    expect(screen.getByText(/RIGHT/i)).toBeDefined();
    expect(screen.getByText(/Hearts Broken/i)).toBeDefined();
  });

  it('proves opponents private cards are never rendered in DOM', () => {
    render(
      <HeartsTable
        gameView={mockPlayingGameView}
        onPlayCard={() => {}}
        onPassCards={() => {}}
      />
    );

    expect(screen.getByText(/Bob/i)).toBeDefined();
    expect(screen.getByText(/Charlie/i)).toBeDefined();
    expect(screen.getByText(/Dave/i)).toBeDefined();
    expect(screen.getAllByText(/Cards: 13/i).length).toBe(3);

    expect(screen.queryByTestId('opponent-hand')).toBeNull();
  });

  it('shows server-provided display names and marks disconnected opponents offline', () => {
    const disconnectedView: PlayerGameView = {
      ...mockPlayingGameView,
      players: mockPlayingGameView.players.map((p) =>
        p.id === 'p3' ? { ...p, is_connected: false } : p
      ),
    };
    render(
      <HeartsTable
        gameView={disconnectedView}
        onPlayCard={() => {}}
        onPassCards={() => {}}
      />
    );

    expect(screen.queryByText(/Player \d/)).toBeNull();
    expect(screen.getAllByText(/Offline/i).length).toBe(1);
    const charlieTile = screen.getByText('Charlie').parentElement as HTMLElement;
    expect(charlieTile.textContent).toMatch(/Offline/i);
  });
});
