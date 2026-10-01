import { useEffect, useRef, useState, useCallback } from 'react';
import type { AnyGameView, Room, WSMessage } from '../types';
import { ApiService } from '../services/api';

export interface UseRoomWebSocketOptions {
  roomId: string;
  onRoomState?: (room: Room) => void;
  onGameState?: (gameView: AnyGameView) => void;
  onError?: (error: string) => void;
  onGameStarted?: (payload: any) => void;
}

export function useRoomWebSocket({
  roomId,
  onRoomState,
  onGameState,
  onError,
  onGameStarted,
}: UseRoomWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const onRoomStateRef = useRef(onRoomState);
  onRoomStateRef.current = onRoomState;
  const onGameStateRef = useRef(onGameState);
  onGameStateRef.current = onGameState;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onGameStartedRef = useRef(onGameStarted);
  onGameStartedRef.current = onGameStarted;

  const connect = useCallback(() => {
    const token = ApiService.getToken();
    if (!token || !roomId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/rooms/${roomId}?token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setIsReconnecting(false);
      ws.send(JSON.stringify({ type: 'GET_ROOM_STATE', payload: {} }));
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        switch (msg.type) {
          case 'ROOM_STATE':
          case 'PLAYER_JOINED':
          case 'PLAYER_LEFT':
          case 'PLAYER_RECONNECTED':
          case 'PLAYER_DISCONNECTED':
          case 'ROOM_SETTINGS_UPDATED':
            if (msg.payload?.room && onRoomState) {
              onRoomStateRef.current?.(msg.payload.room);
            }
            break;
          case 'GAME_STATE':
            if (msg.payload?.game_view && onGameState) {
              onGameStateRef.current?.(msg.payload.game_view);
            }
            break;
          case 'GAME_STARTED':
            if (msg.payload?.room && onRoomState) {
              onRoomStateRef.current?.(msg.payload.room);
            }
            if (onGameStarted) {
              onGameStartedRef.current?.(msg.payload);
            }
            break;
          case 'ERROR':
            if (onError) {
              onErrorRef.current?.(msg.payload?.error || 'Unknown server error');
            }
            break;
          case 'PONG':
            break;
        }
      } catch (err) {
        console.error('Failed to parse websocket message', err);
      }
    };

    ws.onclose = (event) => {
      setIsConnected(false);
      if (event.code !== 1000 && event.code !== 1008) {
        setIsReconnecting(true);
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 3000);
      }
    };

    ws.onerror = (err) => {
      console.warn('WebSocket connection error:', err);
    };
  }, [roomId]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [connect]);

  const send = useCallback((type: string, payload: any = {}) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload }));
    }
  }, []);

  const toggleReady = useCallback((ready: boolean) => {
    send(ready ? 'READY' : 'NOT_READY', {});
  }, [send]);

  const startGame = useCallback(() => {
    send('START_GAME', {});
  }, [send]);

  const passCards = useCallback((card_ids: string[]) => {
    send('PASS_CARD', { card_ids });
  }, [send]);

  const playCard = useCallback((card_id: string) => {
    send('PLAY_CARD', { card_id });
  }, [send]);

  const playCards = useCallback((card_ids: string[], declared_rank: string) => {
    send('PLAY_CARDS', { card_ids, declared_rank });
  }, [send]);

  const callBluff = useCallback(() => {
    send('CALL_BLUFF', {});
  }, [send]);

  const updateSettings = useCallback((selected_game?: string, max_players?: number) => {
    send('UPDATE_SETTINGS', { selected_game, max_players });
  }, [send]);

  return {
    isConnected,
    isReconnecting,
    send,
    toggleReady,
    startGame,
    passCards,
    playCard,
    playCards,
    callBluff,
    updateSettings,
  };
}
