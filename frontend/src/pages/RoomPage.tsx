import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ApiService } from '../services/api';
import { useRoomWebSocket } from '../hooks/useRoomWebSocket';
import type { PlayerGameView, Room } from '../types';
import { HeartsTable } from '../components/HeartsTable';
import {
  Crown,
  Users,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  DoorOpen,
  Play,
  Wifi,
  WifiOff,
  Sparkles,
} from 'lucide-react';

export const RoomPage: React.FC = () => {
  const { roomId } = useParams<{ roomId: string }>();
  const navigate = useNavigate();

  const [room, setRoom] = useState<Room | null>(null);
  const [gameView, setGameView] = useState<PlayerGameView | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [gameStartedBanner, setGameStartedBanner] = useState<string | null>(null);

  useEffect(() => {
    const user = ApiService.getStoredUser();
    if (!user) {
      navigate('/login');
      return;
    }
    setCurrentUser(user);

    if (roomId) {
      ApiService.getRoom(roomId)
        .then((r) => setRoom(r))
        .catch((err) => {
          setErrorMsg(err.message || 'Room not found.');
        });
    }
  }, [roomId, navigate]);

  const {
    isConnected,
    isReconnecting,
    toggleReady,
    startGame,
    passCards,
    playCard,
  } = useRoomWebSocket({
    roomId: room?.id || '',
    onRoomState: (updatedRoom) => {
      setRoom(updatedRoom);
      setErrorMsg(null);
    },
    onGameState: (updatedGameView) => {
      setGameView(updatedGameView);
      setErrorMsg(null);
    },
    onError: (err) => {
      setErrorMsg(err);
      setTimeout(() => setErrorMsg(null), 5000);
    },
    onGameStarted: (payload) => {
      setGameStartedBanner(payload.message || 'Hearts match has started!');
    },
  });

  const handleCopyCode = () => {
    if (!room) return;
    navigator.clipboard.writeText(room.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleLeaveRoom = async () => {
    if (!room) return;
    try {
      await ApiService.leaveRoom(room.id);
      navigate('/lobby');
    } catch {
      navigate('/lobby');
    }
  };

  if (!room) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-4">
        {errorMsg ? (
          <div className="p-6 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 max-w-md">
            <h3 className="font-bold text-lg mb-2">Room Error</h3>
            <p className="text-sm">{errorMsg}</p>
            <button
              onClick={() => navigate('/lobby')}
              className="mt-4 px-4 py-2 bg-slate-800 text-white rounded-lg text-sm"
            >
              Return to Lobby
            </button>
          </div>
        ) : (
          <div className="text-slate-400 flex items-center gap-3">
            <span className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            <span>Loading room state...</span>
          </div>
        )}
      </div>
    );
  }

  const isHost = currentUser?.id === room.host_id;
  const myPlayer = room.players.find((p) => p.user_id === currentUser?.id);
  const isMyPlayerReady = myPlayer?.is_ready || false;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Top Banner / Game Alert */}
      {gameStartedBanner && (
        <div className="mb-6 p-4 rounded-xl bg-gradient-to-r from-emerald-500/20 to-teal-500/20 border border-emerald-500/40 text-emerald-300 flex items-center justify-between animate-pulse">
          <div className="flex items-center gap-3">
            <Sparkles className="w-5 h-5 text-emerald-400" />
            <span className="font-bold text-sm">{gameStartedBanner}</span>
          </div>
          <span className="text-xs uppercase tracking-wider font-semibold text-emerald-400">
            Hearts Session Active
          </span>
        </div>
      )}

      {errorMsg && (
        <div className="mb-6 p-3.5 rounded-xl bg-rose-500/15 border border-rose-500/40 text-rose-300 text-sm flex items-center justify-between">
          <span>{errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="text-rose-400 hover:text-white text-xs">
            Dismiss
          </button>
        </div>
      )}

      {/* Header Info Bar */}
      <div className="p-6 rounded-2xl glass-panel mb-8 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-xs uppercase font-bold tracking-wider text-slate-400 block">Room Code</span>
            <div className="flex items-center gap-2 mt-0.5">
              <span id="room-code-display" className="text-3xl font-black tracking-widest text-amber-400 font-mono">
                {room.code}
              </span>
              <button
                id="copy-code-btn"
                onClick={handleCopyCode}
                className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-300 transition-colors"
                title="Copy Room Code"
              >
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="h-10 w-[1px] bg-slate-800 hidden sm:block" />

          <div>
            <span className="text-xs uppercase font-bold tracking-wider text-slate-400 block">Game Mode</span>
            <span className="text-base font-bold text-white capitalize mt-0.5 block">
              {room.selected_game.replace('_', ' ')}
            </span>
          </div>

          <div className="h-10 w-[1px] bg-slate-800 hidden sm:block" />

          <div>
            <span className="text-xs uppercase font-bold tracking-wider text-slate-400 block">Capacity</span>
            <span className="text-base font-bold text-white mt-0.5 block">
              {room.players.length} / {room.max_players} Players
            </span>
          </div>
        </div>

        {/* Connection status and Leave */}
        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold ${
              isConnected
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : isReconnecting
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
            }`}
          >
            {isConnected ? (
              <>
                <Wifi className="w-3.5 h-3.5" />
                <span>Live Sync</span>
              </>
            ) : isReconnecting ? (
              <>
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                <span>Reconnecting...</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5" />
                <span>Disconnected</span>
              </>
            )}
          </div>

          <button
            id="leave-room-btn"
            onClick={handleLeaveRoom}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-semibold border border-rose-500/20 transition-all"
          >
            <DoorOpen className="w-3.5 h-3.5" />
            <span>Leave</span>
          </button>
        </div>
      </div>

      {/* RENDER ACTIVE HEARTS GAME TABLE IF SESSION RUNNING */}
      {gameView ? (
        <HeartsTable
          gameView={gameView}
          onPlayCard={playCard}
          onPassCards={passCards}
        />
      ) : (
        /* Pre-game Lobby Room Table */
        <div className="relative rounded-3xl p-8 felt-radial border border-slate-800 shadow-2xl min-h-[420px] flex flex-col justify-between">
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none opacity-20">
            <span className="text-7xl font-black tracking-widest text-slate-500">CARDARENA</span>
            <span className="text-xs uppercase tracking-widest font-mono text-slate-400 mt-2">
              HEARTS PRE-GAME LOBBY
            </span>
          </div>

          <div className="relative z-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: room.max_players }).map((_, seatIdx) => {
              const player = room.players.find((p) => p.seat === seatIdx);
              const isPlayerHost = player && player.user_id === room.host_id;
              const isMe = player && player.user_id === currentUser?.id;

              if (player) {
                return (
                  <div
                    key={player.id}
                    className={`p-5 rounded-2xl glass-panel relative flex flex-col justify-between transition-all ${
                      player.is_ready ? 'border-emerald-500/40 ring-1 ring-emerald-500/30' : 'border-slate-800'
                    } ${isMe ? 'shadow-lg shadow-amber-500/10' : ''}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-11 h-11 rounded-xl bg-slate-800 text-amber-400 flex items-center justify-center font-black text-lg border border-slate-700/80">
                          {player.display_name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5">
                            <h4 className="text-sm font-bold text-white">{player.display_name}</h4>
                            {isMe && <span className="text-[10px] text-amber-400 font-bold">(You)</span>}
                          </div>
                          <span className="text-xs text-slate-400 block -mt-0.5">Seat #{seatIdx + 1}</span>
                        </div>
                      </div>

                      {isPlayerHost && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 text-[10px] font-bold border border-amber-500/30">
                          <Crown className="w-3 h-3 text-amber-400" /> Host
                        </span>
                      )}
                    </div>

                    <div className="mt-6 flex items-center justify-between pt-3 border-t border-slate-800/80">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            player.is_connected ? 'bg-emerald-400' : 'bg-slate-600'
                          }`}
                        />
                        <span className="text-xs text-slate-400">
                          {player.is_connected ? 'Connected' : 'Offline'}
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        {isPlayerHost ? (
                          <span className="text-xs font-semibold text-amber-400/90">Host Control</span>
                        ) : player.is_ready ? (
                          <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-400">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Ready
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500">
                            <XCircle className="w-3.5 h-3.5" /> Not Ready
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              }

              return (
                <div
                  key={`empty-${seatIdx}`}
                  className="p-5 rounded-2xl border border-dashed border-slate-800/80 bg-slate-950/30 flex flex-col items-center justify-center text-center min-h-[140px]"
                >
                  <div className="w-10 h-10 rounded-full bg-slate-900/60 border border-slate-800 flex items-center justify-center text-slate-600 mb-2">
                    <Users className="w-4 h-4" />
                  </div>
                  <span className="text-xs font-semibold text-slate-500">Empty Seat #{seatIdx + 1}</span>
                  <span className="text-[10px] text-slate-600 mt-1">Awaiting player...</span>
                </div>
              );
            })}
          </div>

          <div className="relative z-10 mt-8 pt-6 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-4">
            {!isHost && (
              <button
                id="ready-toggle-btn"
                onClick={() => toggleReady(!isMyPlayerReady)}
                className={`px-6 py-3 rounded-xl font-bold text-sm transition-all flex items-center gap-2 shadow-md ${
                  isMyPlayerReady
                    ? 'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40'
                    : 'bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-amber-500/20'
                }`}
              >
                {isMyPlayerReady ? (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Mark as Not Ready</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    <span>I'm Ready!</span>
                  </>
                )}
              </button>
            )}

            {isHost && (
              <div className="flex items-center gap-3">
                <button
                  id="start-game-btn"
                  onClick={startGame}
                  className="px-8 py-3.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition-all flex items-center gap-2"
                >
                  <Play className="w-4 h-4 fill-slate-950" />
                  <span>Launch Hearts Match</span>
                </button>

                <span className="text-xs text-slate-400">
                  Exactly 4 players required, non-hosts must be ready.
                </span>
              </div>
            )}

            <div className="text-xs text-slate-500">
              Room ID: <span className="font-mono text-slate-400">{room.id}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
