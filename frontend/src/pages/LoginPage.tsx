import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiService } from '../services/api';
import { User, ArrowRight } from 'lucide-react';

interface LoginPageProps {
  onLoginSuccess: (user: any) => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError('Please provide a username.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await ApiService.login(username.trim(), displayName.trim() || undefined);
      onLoginSuccess(data.user);
      navigate('/lobby');
    } catch (err: any) {
      setError(err.message || 'Login failed. Ensure backend server is running.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-md p-8 rounded-2xl glass-panel relative overflow-hidden">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 mx-auto flex items-center justify-center mb-3 border border-amber-500/20">
            <User className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-black text-white">Player Identification</h1>
          <p className="text-sm text-slate-400 mt-1">
            Sign in or set your player profile for multiplayer rooms.
          </p>
        </div>

        {error && (
          <div className="mb-6 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs uppercase font-bold tracking-wider text-slate-300 mb-2">
              Username *
            </label>
            <input
              id="login-username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. shadow_player"
              className="w-full px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-700/80 text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all text-sm"
            />
          </div>

          <div>
            <label className="block text-xs uppercase font-bold tracking-wider text-slate-300 mb-2">
              Display Name (Optional)
            </label>
            <input
              id="login-displayname"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g. Shadow Master"
              className="w-full px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-700/80 text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all text-sm"
            />
          </div>

          <button
            id="login-submit-btn"
            type="submit"
            disabled={isLoading}
            className="w-full mt-4 py-3.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-sm shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isLoading ? (
              <span>Connecting...</span>
            ) : (
              <>
                <span>Enter CardArena</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};
