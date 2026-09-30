export interface Card {
  suit: 'SPADES' | 'HEARTS' | 'DIAMONDS' | 'CLUBS';
  rank: string;
  id: string;
}

export interface PlayerPublicView {
  id: string;
  seat: number;
  display_name: string;
  is_connected: boolean;
  card_count: number;
}

export interface TrickCardView {
  player_id: string;
  card: Card;
}

export interface HeartsPublicState {
  round_number: number;
  pass_direction: 'LEFT' | 'RIGHT' | 'ACROSS' | 'NONE';
  has_passed: Record<string, boolean>;
  hearts_broken: boolean;
  is_first_trick: boolean;
  current_trick: TrickCardView[];
  trick_lead_suit?: string | null;
  completed_tricks: number;
  round_points: Record<string, number>;
  total_scores: Record<string, number>;
  last_trick_winner_id?: string | null;
}

export interface PlayerGameView {
  game_id: string;
  game_type: string;
  phase: 'WAITING' | 'STARTING' | 'IN_PROGRESS' | 'ROUND_END' | 'GAME_OVER';
  viewer_id: string;
  current_turn_player_id?: string | null;
  round_number: number;
  scores: Record<string, number>;
  players: PlayerPublicView[];
  my_hand: Card[];
  public_state: HeartsPublicState;
  valid_actions: string[];
  fairness?: FairnessRecord[];
}

/** Public provably-fair record; server_seed is null until the round is revealed. */
export interface FairnessRecord {
  game_id: string;
  round_number: number;
  algorithm: string;
  commitment_scheme: string;
  commitment: string;
  deck_definition: string;
  canonical_deck_sha256: string;
  revealed: boolean;
  server_seed: string | null;
}

/** Documented canonical deck served by GET /fairness/deck-definitions/{name}. */
export interface DeckDefinition {
  name: string;
  algorithm: string;
  cards: string[];
  sha256: string;
}
