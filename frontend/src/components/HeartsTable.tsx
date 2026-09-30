import React, { useState } from 'react';
import type { PlayerGameView } from '../types';
import { CardView } from './CardView';
import { Flame, ShieldAlert, Award, ArrowRight, UserCheck, HelpCircle } from 'lucide-react';

interface HeartsTableProps {
  gameView: PlayerGameView;
  onPlayCard: (cardId: string) => void;
  onPassCards: (cardIds: string[]) => void;
}

export const HeartsTable: React.FC<HeartsTableProps> = ({
  gameView,
  onPlayCard,
  onPassCards,
}) => {
  const [selectedPassCardIds, setSelectedPassCardIds] = useState<string[]>([]);
  const isPassingPhase = gameView.phase === 'STARTING';
  const isPlayingPhase = gameView.phase === 'IN_PROGRESS';
  const isGameOver = gameView.phase === 'GAME_OVER';

  const myId = gameView.viewer_id;
  const isMyTurn = gameView.current_turn_player_id === myId;
  const publicState = gameView.public_state;
  const hasPassed = publicState.has_passed?.[myId] || false;

  const handleCardClick = (cardId: string) => {
    if (isPassingPhase && !hasPassed) {
      if (selectedPassCardIds.includes(cardId)) {
        setSelectedPassCardIds(selectedPassCardIds.filter((id) => id !== cardId));
      } else if (selectedPassCardIds.length < 3) {
        setSelectedPassCardIds([...selectedPassCardIds, cardId]);
      }
    } else if (isPlayingPhase && isMyTurn) {
      onPlayCard(cardId);
    }
  };

  const handleConfirmPass = () => {
    if (selectedPassCardIds.length === 3) {
      onPassCards(selectedPassCardIds);
      setSelectedPassCardIds([]);
    }
  };

  // Find opponent players
  const opponents = gameView.players.filter((p) => p.id !== myId);

  return (
    <div className="relative w-full rounded-3xl p-6 sm:p-8 felt-radial border border-slate-800 shadow-2xl flex flex-col justify-between min-h-[600px] overflow-hidden">
      {/* Top Bar: Round & Passing Direction Info */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4 z-10">
        <div className="flex items-center gap-3">
          <span className="px-3 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 font-bold text-xs uppercase tracking-wider">
            Round {gameView.round_number}
          </span>
          <span className="px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 text-xs font-semibold">
            Pass: <span className="text-amber-400 font-bold">{publicState.pass_direction}</span>
          </span>
          {publicState.hearts_broken && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-bold animate-pulse">
              <Flame className="w-3.5 h-3.5 text-rose-500 fill-rose-500" />
              Hearts Broken
            </span>
          )}
        </div>

        {/* Turn / Phase Indicator */}
        <div className="flex items-center gap-2">
          {isGameOver ? (
            <span className="px-4 py-1.5 rounded-xl bg-amber-500 text-slate-950 font-black text-xs uppercase tracking-wider shadow-lg">
              Match Concluded
            </span>
          ) : isPassingPhase ? (
            <span className="px-3.5 py-1.5 rounded-xl bg-sky-500/15 border border-sky-500/30 text-sky-300 text-xs font-bold">
              {hasPassed ? 'Passed (Waiting for others)' : 'Select 3 Cards to Pass'}
            </span>
          ) : isMyTurn ? (
            <span className="px-4 py-1.5 rounded-xl bg-emerald-500 text-slate-950 font-black text-xs uppercase tracking-wider animate-bounce shadow-lg shadow-emerald-500/20">
              Your Turn to Play
            </span>
          ) : (
            <span className="px-3.5 py-1.5 rounded-xl bg-slate-800 text-slate-400 text-xs font-semibold">
              Waiting for current player...
            </span>
          )}
        </div>
      </div>

      {/* Opponents Strip (Top & Sides) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6 z-10">
        {opponents.map((opp) => {
          const isOppTurn = gameView.current_turn_player_id === opp.id;
          const oppRoundScore = publicState.round_points?.[opp.id] || 0;
          const oppTotalScore = gameView.scores[opp.id] || 0;

          return (
            <div
              key={opp.id}
              className={`p-3.5 rounded-xl glass-panel flex items-center justify-between border transition-all ${
                isOppTurn
                  ? 'border-amber-400/80 ring-2 ring-amber-400/30 shadow-lg shadow-amber-500/10'
                  : 'border-slate-800/80'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-slate-800 text-amber-300 flex items-center justify-center font-bold text-sm border border-slate-700">
                  {opp.display_name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <h4 className="text-xs font-bold text-white leading-tight">{opp.display_name}</h4>
                  <span className="text-[11px] text-slate-400">Cards: {opp.card_count}</span>
                </div>
              </div>

              <div className="text-right">
                <span className="text-xs font-bold text-amber-400 block">{oppTotalScore} pts</span>
                <span className="text-[10px] text-slate-400">Round: +{oppRoundScore}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Center Table Trick Display */}
      <div className="my-auto py-8 flex flex-col items-center justify-center relative min-h-[160px] z-10">
        {publicState.current_trick && publicState.current_trick.length > 0 ? (
          <div className="flex flex-wrap items-center justify-center gap-3">
            {publicState.current_trick.map((tc, idx) => {
              const player = gameView.players.find((p) => p.id === tc.player_id);
              return (
                <div key={`${tc.card.id}-${idx}`} className="flex flex-col items-center">
                  <span className="text-[11px] font-bold text-slate-400 mb-1">
                    {player?.display_name || 'Player'}
                  </span>
                  <CardView card={tc.card} small />
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center p-6 border border-dashed border-slate-800/80 rounded-2xl bg-slate-950/20 max-w-sm">
            <span className="text-xs text-slate-500 font-mono block">NO ACTIVE TRICK</span>
            <span className="text-[11px] text-slate-600 mt-1 block">
              {isPassingPhase ? 'Waiting for card passing' : 'Leading trick card'}
            </span>
          </div>
        )}
      </div>

      {/* Passing Controls Bar */}
      {isPassingPhase && !hasPassed && (
        <div className="mb-4 p-3 rounded-2xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-between z-10">
          <span className="text-xs font-bold text-sky-300">
            Selected: {selectedPassCardIds.length} / 3 cards
          </span>
          <button
            id="pass-cards-btn"
            onClick={handleConfirmPass}
            disabled={selectedPassCardIds.length !== 3}
            className="px-5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs disabled:opacity-40 transition-all flex items-center gap-1.5"
          >
            <span>Pass Cards</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Player's Own Hand Area */}
      <div className="pt-4 border-t border-slate-800/80 z-10">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">Your Hand</span>
            <span className="text-xs text-slate-500">({gameView.my_hand.length} cards)</span>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <span className="text-slate-400">
              Round: <span className="text-amber-400 font-bold">+{publicState.round_points?.[myId] || 0}</span>
            </span>
            <span className="text-slate-400">
              Total: <span className="text-white font-bold">{gameView.scores[myId] || 0} pts</span>
            </span>
          </div>
        </div>

        {/* Hand Cards Horizontal Scroll / Flex */}
        <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-2.5 py-2">
          {gameView.my_hand.map((card) => {
            const isSelected = selectedPassCardIds.includes(card.id);
            const isPlayable = isPlayingPhase && isMyTurn;

            return (
              <CardView
                key={card.id}
                card={card}
                isSelected={isSelected}
                isPlayable={isPlayable}
                onClick={() => handleCardClick(card.id)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
};
