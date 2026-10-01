import React, { useEffect, useRef, useState } from 'react';
import { Award, Layers, ShieldAlert } from 'lucide-react';
import type { BluffGameView } from '../types';
import type { DealtHandSnapshot } from '../fairness/verify';
import { CardView } from './CardView';
import { FairnessPanel } from './FairnessPanel';

interface BluffTableProps {
  gameView: BluffGameView;
  onPlayCards: (cardIds: string[], declaredRank: string) => void;
  onCallBluff: () => void;
}

/** Functional Bluff table: renders only the sanitized server view and server-provided legal actions. */
export const BluffTable: React.FC<BluffTableProps> = ({ gameView, onPlayCards, onCallBluff }) => {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [declaredRank, setDeclaredRank] = useState('');

  const myId = gameView.viewer_id;
  const state = gameView.public_state;
  const canPlay = gameView.valid_actions.includes('PLAY_CARDS');
  const canCallBluff = gameView.valid_actions.includes('CALL_BLUFF');
  const isGameOver = gameView.phase === 'GAME_OVER';
  const nameOf = (playerId: string | null | undefined) =>
    gameView.players.find((p) => p.id === playerId)?.display_name ?? '—';
  const orderedPlayers = state.player_order
    .map((id) => gameView.players.find((p) => p.id === id))
    .filter((p): p is NonNullable<typeof p> => Boolean(p));

  // Drop selections for cards no longer in hand (after a play or an update)
  const handKey = gameView.my_hand.map((c) => c.id).join(',');
  useEffect(() => {
    const inHand = new Set(gameView.my_hand.map((c) => c.id));
    setSelectedIds((ids) => ids.filter((id) => inHand.has(id)));
  }, [handKey]);

  // Remember the hand exactly as dealt (before any play) for fairness verification
  const dealtHandsRef = useRef<Map<string, DealtHandSnapshot>>(new Map());
  useEffect(() => {
    const key = `${gameView.game_id}:${gameView.round_number}`;
    const me = gameView.players.find((p) => p.id === myId);
    if (!dealtHandsRef.current.has(key) && me && state.play_count === 0 && gameView.my_hand.length > 0) {
      dealtHandsRef.current.set(key, {
        cardIds: gameView.my_hand.map((c) => c.id),
        seat: me.seat,
        numPlayers: gameView.players.length,
        cardsPerPlayer: gameView.my_hand.length,
      });
    }
  }, [gameView, myId, state.play_count]);

  const toggleCard = (cardId: string) => {
    if (!canPlay) return;
    setSelectedIds((ids) =>
      ids.includes(cardId)
        ? ids.filter((id) => id !== cardId)
        : ids.length < state.max_cards_per_play
        ? [...ids, cardId]
        : ids
    );
  };

  const canSubmitPlay =
    canPlay && selectedIds.length >= 1 && selectedIds.length <= state.max_cards_per_play && declaredRank !== '';

  const handlePlay = () => {
    if (!canSubmitPlay) return;
    onPlayCards(selectedIds, declaredRank);
    setSelectedIds([]);
  };

  const challenge = state.last_challenge;

  return (
    <div className="relative w-full rounded-3xl p-6 sm:p-8 felt-radial border border-slate-800 shadow-2xl flex flex-col gap-6 min-h-[600px]">
      {/* Status */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="px-3 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 font-bold text-xs uppercase tracking-wider">
          Bluff
        </span>
        {isGameOver ? (
          <span className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-amber-500 text-slate-950 font-black text-xs uppercase tracking-wider">
            <Award className="w-4 h-4" />
            {state.winner_id === myId ? 'You won!' : `${nameOf(state.winner_id)} wins`}
          </span>
        ) : gameView.current_turn_player_id === myId ? (
          <span className="px-4 py-1.5 rounded-xl bg-emerald-500 text-slate-950 font-black text-xs uppercase tracking-wider">
            Your Turn
          </span>
        ) : (
          <span className="px-3.5 py-1.5 rounded-xl bg-slate-800 text-slate-400 text-xs font-semibold">
            Waiting for {nameOf(gameView.current_turn_player_id)}…
          </span>
        )}
      </div>

      {/* Players */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {orderedPlayers.map((p) => {
          const isTurn = gameView.current_turn_player_id === p.id;
          const isMe = p.id === myId;
          return (
            <div
              key={p.id}
              data-testid={`bluff-player-${p.id}`}
              className={`p-3 rounded-xl glass-panel border ${
                isTurn ? 'border-amber-400/80 ring-2 ring-amber-400/30' : 'border-slate-800/80'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-white truncate">{p.display_name}</span>
                {isMe && <span className="text-[10px] font-bold uppercase text-emerald-400">You</span>}
              </div>
              <span className="text-[11px] text-slate-400 block">Cards: {p.card_count}</span>
              {isTurn && !isGameOver && <span className="text-[10px] font-bold uppercase text-amber-400">Turn</span>}
              {!p.is_connected && <span className="ml-2 text-[10px] font-bold uppercase text-rose-400">Offline</span>}
            </div>
          );
        })}
      </div>

      {/* Pile, declaration and challenge result */}
      <div className="flex flex-col items-center gap-3 text-center">
        <span data-testid="bluff-pile" className="flex items-center gap-2 text-sm font-bold text-slate-200">
          <Layers className="w-4 h-4 text-amber-400" />
          Pile: {state.pile_count} card{state.pile_count === 1 ? '' : 's'} face down
        </span>
        {state.last_play && (
          <p data-testid="bluff-declaration" className="text-sm text-slate-300">
            {state.last_play.player_id === myId ? 'You' : nameOf(state.last_play.player_id)} declared{' '}
            <span className="font-bold text-amber-300">
              {state.last_play.declared_quantity} × {state.last_play.declared_rank}
            </span>
          </p>
        )}
        {challenge && (
          <div data-testid="bluff-challenge-result" className="p-3 rounded-xl bg-slate-950/40 border border-slate-800 max-w-lg">
            <p className="flex items-center justify-center gap-1.5 text-xs text-slate-300">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
              {nameOf(challenge.challenger_id)} called bluff on {nameOf(challenge.challenged_player_id)}'s{' '}
              {challenge.declared_quantity} × {challenge.declared_rank}
            </p>
            <div className="flex flex-wrap justify-center gap-1.5 my-2">
              {challenge.revealed_cards.map((card) => (
                <CardView key={card.id} card={card} small />
              ))}
            </div>
            <p className={`text-xs font-bold ${challenge.declaration_truthful ? 'text-emerald-400' : 'text-rose-400'}`}>
              {challenge.declaration_truthful ? 'Declaration was true' : 'It was a bluff'} —{' '}
              {nameOf(challenge.pile_recipient_id)} took {challenge.pile_size} card{challenge.pile_size === 1 ? '' : 's'}
            </p>
          </div>
        )}
      </div>

      {/* Actions: only those the server reports as legal */}
      {(canPlay || canCallBluff) && (
        <div className="flex flex-wrap items-center justify-center gap-3 p-3 rounded-2xl bg-sky-500/10 border border-sky-500/20">
          {canPlay && (
            <>
              <span className="text-xs font-bold text-sky-300">
                Selected: {selectedIds.length} / {state.max_cards_per_play}
              </span>
              <label className="text-xs text-slate-300 flex items-center gap-1.5">
                Declare rank
                <select
                  aria-label="Declared rank"
                  value={declaredRank}
                  onChange={(e) => setDeclaredRank(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-white"
                >
                  <option value="">—</option>
                  {state.declarable_ranks.map((rank) => (
                    <option key={rank} value={rank}>{rank}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={handlePlay}
                disabled={!canSubmitPlay}
                className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs disabled:opacity-40"
              >
                Play {selectedIds.length} as {declaredRank || '…'}
              </button>
            </>
          )}
          {canCallBluff && (
            <button
              type="button"
              onClick={onCallBluff}
              className="px-4 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white font-bold text-xs"
            >
              Call Bluff
            </button>
          )}
        </div>
      )}

      {/* Own hand */}
      <div className="pt-4 border-t border-slate-800/80">
        <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
          Your Hand <span className="text-slate-500 normal-case">({gameView.my_hand.length} cards)</span>
        </span>
        <div className="flex flex-wrap items-center justify-center gap-2 py-2">
          {gameView.my_hand.map((card) => (
            <CardView
              key={card.id}
              card={card}
              isSelected={selectedIds.includes(card.id)}
              isPlayable={canPlay}
              onClick={() => toggleCard(card.id)}
            />
          ))}
        </div>
      </div>

      <FairnessPanel
        records={gameView.fairness ?? []}
        currentRound={gameView.round_number}
        getDealtHand={(roundNumber) => dealtHandsRef.current.get(`${gameView.game_id}:${roundNumber}`)}
      />
    </div>
  );
};
