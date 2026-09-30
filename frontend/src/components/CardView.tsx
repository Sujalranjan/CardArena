import React from 'react';
import type { Card as CardType } from '../types';

interface CardViewProps {
  card: CardType;
  isSelected?: boolean;
  isPlayable?: boolean;
  onClick?: () => void;
  small?: boolean;
}

export const CardView: React.FC<CardViewProps> = ({
  card,
  isSelected,
  isPlayable,
  onClick,
  small,
}) => {
  const isRed = card.suit === 'HEARTS' || card.suit === 'DIAMONDS';

  const suitSymbols: Record<string, string> = {
    SPADES: '♠',
    HEARTS: '♥',
    DIAMONDS: '♦',
    CLUBS: '♣',
  };

  return (
    <div
      data-testid={`card-${card.id}`}
      onClick={isPlayable || onClick ? onClick : undefined}
      className={`relative select-none transition-all duration-150 rounded-xl flex flex-col justify-between font-bold shadow-md ${
        small ? 'w-14 h-20 p-1.5 text-xs' : 'w-20 h-28 p-2.5 text-sm sm:w-24 sm:h-36 sm:p-3 sm:text-base'
      } ${
        isRed ? 'text-rose-600 bg-white' : 'text-slate-900 bg-slate-100'
      } ${
        isSelected
          ? '-translate-y-5 ring-4 ring-amber-400 shadow-amber-500/40'
          : isPlayable
          ? 'hover:-translate-y-3 cursor-pointer hover:shadow-xl hover:ring-2 hover:ring-amber-300'
          : 'opacity-90'
      }`}
    >
      <div className="flex flex-col items-center leading-none">
        <span>{card.rank}</span>
        <span className="text-base">{suitSymbols[card.suit]}</span>
      </div>

      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-25 text-3xl sm:text-4xl">
        {suitSymbols[card.suit]}
      </div>

      <div className="flex flex-col items-center leading-none rotate-180 self-end">
        <span>{card.rank}</span>
        <span className="text-base">{suitSymbols[card.suit]}</span>
      </div>
    </div>
  );
};
