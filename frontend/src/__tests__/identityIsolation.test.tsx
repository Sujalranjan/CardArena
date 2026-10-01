import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiService } from '../services/api';
import { useRoomWebSocket } from '../hooks/useRoomWebSocket';
import { randomHex } from './fairnessTestData';

const TOKEN_KEY = 'cardarena_token';
const USER_KEY = 'cardarena_user';

const makeUser = () => ({ id: randomHex(8), username: randomHex(6), display_name: randomHex(6) });

/** What another tab running the previous build (or shared storage) would write. */
function simulateOtherTabSharedLogin() {
  const other = { token: randomHex(24), user: makeUser() };
  localStorage.setItem(TOKEN_KEY, other.token);
  localStorage.setItem(USER_KEY, JSON.stringify(other.user));
  return other;
}

class CapturingWebSocket {
  static OPEN = 1;
  static urls: string[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  constructor(url: string) {
    CapturingWebSocket.urls.push(url);
  }
  send() {}
  close() {}
}

const RoomSocketProbe: React.FC<{ roomId: string }> = ({ roomId }) => {
  useRoomWebSocket({ roomId });
  return null;
};

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  CapturingWebSocket.urls = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Per-tab player identity', () => {
  it('stores the login in tab-scoped storage and clears legacy shared credentials', () => {
    simulateOtherTabSharedLogin();
    const token = randomHex(24);
    const user = makeUser();
    ApiService.setToken(token);
    ApiService.setStoredUser(user);

    expect(sessionStorage.getItem(TOKEN_KEY)).toBe(token);
    expect(ApiService.getToken()).toBe(token);
    expect(ApiService.getStoredUser()).toEqual(user);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("is not changed by another tab's login", () => {
    const token = randomHex(24);
    const user = makeUser();
    ApiService.setToken(token);
    ApiService.setStoredUser(user);

    const other = simulateOtherTabSharedLogin();
    expect(ApiService.getToken()).toBe(token);
    expect(ApiService.getToken()).not.toBe(other.token);
    expect(ApiService.getStoredUser()).toEqual(user);
  });

  it("opens and re-opens the room WebSocket with this tab's own token", () => {
    vi.stubGlobal('WebSocket', CapturingWebSocket);
    const token = randomHex(24);
    ApiService.setToken(token);
    ApiService.setStoredUser(makeUser());
    const other = simulateOtherTabSharedLogin();
    const roomId = randomHex(8);

    const { unmount } = render(<RoomSocketProbe roomId={roomId} />);
    unmount();
    render(<RoomSocketProbe roomId={roomId} />); // e.g. remount / reconnect

    expect(CapturingWebSocket.urls.length).toBeGreaterThanOrEqual(2);
    for (const url of CapturingWebSocket.urls) {
      const params = new URL(url).searchParams;
      expect(params.get('token')).toBe(token);
      expect(url).not.toContain(other.token);
      expect(url).toContain(`/ws/rooms/${roomId}`);
    }
  });

  it('logout clears only this identity from every storage location', () => {
    ApiService.setToken(randomHex(24));
    ApiService.setStoredUser(makeUser());
    simulateOtherTabSharedLogin();
    ApiService.clearToken();
    expect(ApiService.getToken()).toBeNull();
    expect(ApiService.getStoredUser()).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});
