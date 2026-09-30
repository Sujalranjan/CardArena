export interface User {
  id: string;
  username: string;
  display_name: string;
  avatar?: string;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface RoomPlayer {
  id: string;
  user_id: string;
  seat: number;
  is_ready: boolean;
  is_connected: boolean;
  joined_at: string;
  display_name: string;
  username: string;
  avatar?: string;
}

export interface Room {
  id: string;
  code: string;
  host_id: string;
  selected_game: string;
  max_players: number;
  status: 'WAITING' | 'PLAYING' | 'FINISHED';
  created_at: string;
  players: RoomPlayer[];
}

export interface WSMessage<T = any> {
  type: string;
  payload: T;
}

export * from './game';
