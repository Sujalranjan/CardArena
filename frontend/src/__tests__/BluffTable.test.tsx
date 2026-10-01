import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BluffTable } from '../components/BluffTable';
import type { BluffGameView, BluffPublicState } from '../types';
import { cardFromId, fairnessVectors, randomHex } from './fairnessTestData';

const DECK = fairnessVectors.vectors[0].deck_order;
const RANKS = Array.from(new Set(fairnessVectors.canonical_deck.map((id) => id.slice(id.lastIndexOf('_') + 1))));
const MAX_PER_PLAY = 1 + (parseInt(randomHex(1), 16) % 4);

interface Scenario {
  view: BluffGameView;
  ids: string[];
  names: string[];
  hands: Record<string, string[]>;
}

/** Builds a sanitized view the way the server would, from random players and a real deal split. */
function scenario(playerCount: number, viewerIndex: number, overrides: Partial<BluffPublicState> = {}, turnIndex = viewerIndex): Scenario {
  const ids = Array.from({ length: playerCount }, () => randomHex(6));
  const names = ids.map(() => `Player ${randomHex(3)}`);
  const hands: Record<string, string[]> = Object.fromEntries(ids.map((id) => [id, [] as string[]]));
  DECK.forEach((cardId, i) => hands[ids[i % playerCount]].push(cardId));
  const viewer = ids[viewerIndex];
  const view: BluffGameView = {
    game_id: randomHex(8),
    game_type: 'bluff',
    phase: 'IN_PROGRESS',
    viewer_id: viewer,
    current_turn_player_id: ids[turnIndex],
    round_number: 1,
    scores: Object.fromEntries(ids.map((id) => [id, 0])),
    players: ids.map((id, seat) => ({ id, seat, display_name: names[seat], is_connected: true, card_count: hands[id].length })),
    my_hand: hands[viewer].map(cardFromId),
    public_state: {
      player_order: ids,
      starting_player_id: ids[turnIndex],
      pile_count: 0,
      play_count: 0,
      last_play: null,
      last_challenge: null,
      winner_id: null,
      declarable_ranks: RANKS,
      max_cards_per_play: MAX_PER_PLAY,
      ...overrides,
    },
    valid_actions: turnIndex === viewerIndex ? ['PLAY_CARDS'] : [],
  };
  return { view, ids, names, hands };
}

const renderTable = (view: BluffGameView, handlers: Partial<{ onPlayCards: any; onCallBluff: any }> = {}) =>
  render(<BluffTable gameView={view} onPlayCards={handlers.onPlayCards ?? vi.fn()} onCallBluff={handlers.onCallBluff ?? vi.fn()} />);

describe('BluffTable', () => {
  it.each([2, 4, 8])('renders every player from state with counts for %i players', (count) => {
    const viewerIndex = count - 1;
    const { view, ids, names, hands } = scenario(count, viewerIndex);
    renderTable(view);
    ids.forEach((id, i) => {
      const tile = screen.getByTestId(`bluff-player-${id}`);
      expect(tile.textContent).toContain(names[i]);
      expect(tile.textContent).toContain(`Cards: ${hands[id].length}`);
    });
    expect(screen.getAllByText('You').length).toBe(1);
    expect(screen.getByTestId(`bluff-player-${ids[viewerIndex]}`).textContent).toContain('You');
    expect(screen.getAllByTestId(/^card-/).length).toBe(hands[ids[viewerIndex]].length);
  });

  it('never renders opponent cards: only the viewer hand appears in the DOM', () => {
    const { view, ids, hands } = scenario(4, 1);
    const { container } = renderTable(view);
    const html = container.innerHTML;
    for (const id of ids) {
      if (id === view.viewer_id) continue;
      for (const cardId of hands[id]) {
        expect(html).not.toContain(cardId);
      }
    }
    for (const cardId of hands[view.viewer_id]) {
      expect(screen.getByTestId(`card-${cardId}`)).toBeTruthy();
    }
  });

  it('shows the active turn and waiting state from the view', () => {
    const mine = scenario(3, 0);
    const { unmount } = renderTable(mine.view);
    expect(screen.getByText('Your Turn')).toBeTruthy();
    unmount();

    const theirs = scenario(3, 0, {}, 2);
    renderTable(theirs.view);
    expect(screen.getByText(`Waiting for ${theirs.names[2]}…`)).toBeTruthy();
    expect(screen.getByTestId(`bluff-player-${theirs.ids[2]}`).textContent).toContain('Turn');
    expect(screen.queryByRole('button', { name: /Play/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Call Bluff/ })).toBeNull();
  });

  it('selects real hand cards up to the server limit and submits the declared rank', () => {
    const onPlayCards = vi.fn();
    const { view } = scenario(4, 0);
    renderTable(view, { onPlayCards });

    const hand = view.my_hand.map((c) => c.id);
    hand.slice(0, MAX_PER_PLAY + 1).forEach((id) => fireEvent.click(screen.getByTestId(`card-${id}`)));
    expect(screen.getByText(`Selected: ${MAX_PER_PLAY} / ${MAX_PER_PLAY}`)).toBeTruthy();

    const playButton = screen.getByRole('button', { name: /^Play/ }) as HTMLButtonElement;
    expect(playButton.disabled).toBe(true); // no rank chosen yet
    const rank = RANKS[parseInt(randomHex(1), 16) % RANKS.length];
    const select = screen.getByLabelText('Declared rank') as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value).filter(Boolean)).toEqual(RANKS);
    fireEvent.change(select, { target: { value: rank } });
    expect(playButton.disabled).toBe(false);
    fireEvent.click(playButton);
    expect(onPlayCards).toHaveBeenCalledWith(hand.slice(0, MAX_PER_PLAY), rank);

    // Deselect works
    fireEvent.click(screen.getByTestId(`card-${hand[0]}`));
    fireEvent.click(screen.getByTestId(`card-${hand[0]}`));
    expect(screen.getByText(`Selected: 0 / ${MAX_PER_PLAY}`)).toBeTruthy();
  });

  it('offers Call Bluff only when the server lists it as legal', () => {
    const onCallBluff = vi.fn();
    const { view, ids } = scenario(4, 1, {
      pile_count: 2, play_count: 1, last_play: { player_id: '', declared_rank: RANKS[0], declared_quantity: 2 },
    });
    view.public_state.last_play!.player_id = ids[0];
    const { unmount } = renderTable(view, { onCallBluff });
    expect(screen.queryByRole('button', { name: 'Call Bluff' })).toBeNull();
    unmount();

    renderTable({ ...view, valid_actions: ['PLAY_CARDS', 'CALL_BLUFF'] }, { onCallBluff });
    fireEvent.click(screen.getByRole('button', { name: 'Call Bluff' }));
    expect(onCallBluff).toHaveBeenCalledTimes(1);
  });

  it('updates pile, declaration, counts and turn when a new authoritative view arrives', () => {
    const { view, ids, names } = scenario(4, 2, {}, 0);
    const { rerender } = renderTable(view);
    expect(screen.queryByTestId('bluff-declaration')).toBeNull();

    const quantity = 1 + (parseInt(randomHex(1), 16) % MAX_PER_PLAY);
    const rank = RANKS[parseInt(randomHex(1), 16) % RANKS.length];
    const updated: BluffGameView = {
      ...view,
      current_turn_player_id: ids[1],
      players: view.players.map((p) => (p.id === ids[0] ? { ...p, card_count: p.card_count - quantity } : p)),
      public_state: {
        ...view.public_state,
        pile_count: quantity,
        play_count: 1,
        last_play: { player_id: ids[0], declared_rank: rank, declared_quantity: quantity },
      },
    };
    rerender(<BluffTable gameView={updated} onPlayCards={vi.fn()} onCallBluff={vi.fn()} />);
    expect(screen.getByTestId('bluff-declaration').textContent).toContain(`${names[0]} declared ${quantity} × ${rank}`);
    expect(screen.getByTestId('bluff-pile').textContent).toContain(`Pile: ${quantity}`);
    expect(screen.getByTestId(`bluff-player-${ids[0]}`).textContent).toContain(`Cards: ${updated.players[0].card_count}`);
    expect(screen.getByText(`Waiting for ${names[1]}…`)).toBeTruthy();
  });

  it('shows a resolved challenge with the publicly revealed cards and pile recipient', () => {
    const { view, ids, names, hands } = scenario(3, 2, {}, 1);
    const revealed = hands[ids[0]].slice(0, 2);
    view.public_state.last_challenge = {
      challenger_id: ids[1],
      challenged_player_id: ids[0],
      declared_rank: RANKS[0],
      declared_quantity: revealed.length,
      revealed_cards: revealed.map(cardFromId),
      declaration_truthful: false,
      pile_recipient_id: ids[0],
      pile_size: revealed.length + 3,
    };
    renderTable(view);
    const result = screen.getByTestId('bluff-challenge-result');
    expect(result.textContent).toContain(`${names[1]} called bluff on ${names[0]}'s`);
    expect(result.textContent).toContain('It was a bluff');
    expect(result.textContent).toContain(`${names[0]} took ${revealed.length + 3} cards`);
    revealed.forEach((id) => expect(within(result).getByTestId(`card-${id}`)).toBeTruthy());
  });

  it('shows the winner and no actions at game over', () => {
    const { view, ids, names } = scenario(4, 3, {}, 3);
    const over: BluffGameView = {
      ...view, phase: 'GAME_OVER', current_turn_player_id: null, valid_actions: [],
      public_state: { ...view.public_state, winner_id: ids[1] },
    };
    const { unmount } = renderTable(over);
    expect(screen.getByText(`${names[1]} wins`)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Play/ })).toBeNull();
    unmount();

    renderTable({ ...over, public_state: { ...over.public_state, winner_id: ids[3] } });
    expect(screen.getByText('You won!')).toBeTruthy();
  });
});
