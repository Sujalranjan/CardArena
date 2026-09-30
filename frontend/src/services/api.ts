import type { AuthResponse, DeckDefinition, Room, User } from '../types';

const API_BASE = '/api/v1';

export class ApiService {
  private static getToken(): string | null {
    return localStorage.getItem('cardarena_token');
  }

  public static setToken(token: string): void {
    localStorage.setItem('cardarena_token', token);
  }

  public static clearToken(): void {
    localStorage.removeItem('cardarena_token');
    localStorage.removeItem('cardarena_user');
  }

  public static getStoredUser(): User | null {
    const raw = localStorage.getItem('cardarena_user');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  public static setStoredUser(user: User): void {
    localStorage.setItem('cardarena_user', JSON.stringify(user));
  }

  private static async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Network request failed' }));
      throw new Error(errorData.detail || `HTTP Error ${response.status}`);
    }

    return response.json();
  }

  // Auth Endpoints
  public static async login(username: string, displayName?: string): Promise<AuthResponse> {
    const data = await this.request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        username,
        display_name: displayName || username,
      }),
    });
    this.setToken(data.access_token);
    this.setStoredUser(data.user);
    return data;
  }

  public static async getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  // Room Endpoints
  public static async createRoom(selectedGame: string = 'hearts', maxPlayers: number = 4): Promise<Room> {
    return this.request<Room>('/rooms', {
      method: 'POST',
      body: JSON.stringify({
        selected_game: selectedGame,
        max_players: maxPlayers,
      }),
    });
  }

  public static async joinRoom(roomCode: string): Promise<Room> {
    return this.request<Room>('/rooms/join', {
      method: 'POST',
      body: JSON.stringify({ room_code: roomCode.trim().toUpperCase() }),
    });
  }

  public static async getRoom(roomIdOrCode: string): Promise<Room> {
    return this.request<Room>(`/rooms/${roomIdOrCode}`);
  }

  public static async leaveRoom(roomId: string): Promise<void> {
    return this.request<void>(`/rooms/${roomId}/leave`, {
      method: 'POST',
    });
  }

  // Fairness Endpoints (public specification data)
  public static async getDeckDefinition(name: string): Promise<DeckDefinition> {
    return this.request<DeckDefinition>(`/fairness/deck-definitions/${encodeURIComponent(name)}`);
  }

  public static async updateSettings(
    roomId: string,
    settings: { selected_game?: string; max_players?: number }
  ): Promise<Room> {
    return this.request<Room>(`/rooms/${roomId}/settings`, {
      method: 'PATCH',
      body: JSON.stringify(settings),
    });
  }
}
