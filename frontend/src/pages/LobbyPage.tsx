import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiService } from '../services/api';
import { PlusCircle, KeyRound, ArrowRight } from 'lucide-react';

export const LobbyPage: React.FC = () => {
  const [roomCode, setRoomCode] = useState('');
  const [selectedGame, setSelectedGame] = useState('hearts');
  const [maxPlayers, setMaxPlayers] = useState(4);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleCreateRoom = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      const room = await ApiService.createRoom(selectedGame, maxPlayers);
      navigate(`/room/${room.code}`);
    } catch (err: any) {
      setError(err.message || 'Failed to create room.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleJoinRoom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!roomCode.trim()) {
      setError('Please provide a room code.');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const room = await ApiService.joinRoom(roomCode);
      navigate(`/room/${room.code}`);
    } catch (err: any) {
      setError(err.message || 'Failed to join room.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="text-center mb-10">
        <h1 className="text-3xl sm:text-4xl font-black text-white">Game Lobby</h1>
        <p className="text-sm text-slate-400 mt-2">
          Create a private multiplayer arena or join friends with a 6-character room code.
        </p>
      </div>

      {error && (
        <div className="mb-8 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm text-center">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="p-8 rounded-2xl glass-panel relative flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center border border-amber-500/20">
                <PlusCircle className="w-5 h-5" />
              </div>
              <h2 className="text-xl font-bold text-white">Create Room</h2>
            </div>

            <form onSubmit={handleCreateRoom} className="space-y-5">
              <div>
                <label className="block text-xs uppercase font-bold tracking-wider text-slate-300 mb-2">
                  Select Game
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: 'hearts', label: 'Hearts' },
                    { id: 'teen_patti', label: 'Teen Patti' },
                    { id: '28', label: '28' },
                    { id: 'bluff', label: 'Bluff' },
                    { id: 'napoleon', label: 'Napoleon' },
                    { id: 'joker', label: 'Joker' },
                  ].map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      onClick={() => setSelectedGame(g.id)}
                      className={`py-2 px-3 rounded-lg text-xs font-semibold border transition-all text-left flex items-center justify-between ${
                        selectedGame === g.id
                          ? 'bg-amber-500/15 border-amber-500/60 text-amber-300'
                          : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      <span>{g.label}</span>
                      {selectedGame === g.id && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs uppercase font-bold tracking-wider text-slate-300 mb-2">
                  Max Players: <span className="text-amber-400 font-bold">{maxPlayers}</span>
                </label>
                <input
                  id="max-players-range"
                  type="range"
                  min="2"
                  max="8"
                  value={maxPlayers}
                  onChange={(e) => setMaxPlayers(parseInt(e.target.value, 10))}
                  className="w-full accent-amber-500 bg-slate-800 cursor-pointer"
                />
                <div className="flex justify-between text-[11px] text-slate-500 mt-1">
                  <span>2 players</span>
                  <span>4 players</span>
                  <span>8 players</span>
                </div>
              </div>

              <button
                id="create-room-btn"
                type="submit"
                disabled={isLoading}
                className="w-full mt-6 py-3.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-sm shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <span>Initialize Private Room</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          </div>
        </div>

        <div className="p-8 rounded-2xl glass-panel relative flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-sky-500/10 text-sky-400 flex items-center justify-center border border-sky-500/20">
                <KeyRound className="w-5 h-5" />
              </div>
              <h2 className="text-xl font-bold text-white">Join with Code</h2>
            </div>

            <form onSubmit={handleJoinRoom} className="space-y-6">
              <div>
                <label className="block text-xs uppercase font-bold tracking-wider text-slate-300 mb-2">
                  6-Letter Room Code
                </label>
                <input
                  id="join-room-code"
                  type="text"
                  maxLength={6}
                  value={roomCode}
                  onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
                  placeholder="e.g. 7XKP9Q"
                  className="w-full px-4 py-3.5 text-center text-2xl font-black tracking-widest uppercase rounded-xl bg-slate-900/90 border border-slate-700/80 text-amber-400 placeholder-slate-600 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all font-mono"
                />
              </div>

              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 text-xs text-slate-400 space-y-2">
                <p className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  Instant connection to host room
                </p>
                <p className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  Automatic seat placement
                </p>
                <p className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
                  Realtime sync over WebSockets
                </p>
              </div>

              <button
                id="join-room-btn"
                type="submit"
                disabled={isLoading || !roomCode.trim()}
                className="w-full py-3.5 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-bold text-sm border border-slate-700 hover:border-slate-600 transition-all flex items-center justify-center gap-2 disabled:opacity-40"
              >
                <span>Enter Room</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
