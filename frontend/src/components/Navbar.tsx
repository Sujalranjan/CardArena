import React from 'react';
import { Link } from 'react-router-dom';
import { Spade, LogOut } from 'lucide-react';

interface NavbarProps {
  user: any;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ user, onLogout }) => {
  return (
    <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-600 to-amber-400 flex items-center justify-center shadow-lg shadow-amber-500/20 group-hover:scale-105 transition-transform">
            <Spade className="w-6 h-6 text-slate-950 fill-slate-950" />
          </div>
          <div>
            <span className="text-xl font-black tracking-tight text-white flex items-center gap-1">
              Card<span className="text-amber-400">Arena</span>
            </span>
            <span className="text-[10px] uppercase font-bold tracking-widest text-slate-400 block -mt-1">
              Phase 1 Platform
            </span>
          </div>
        </Link>

        <div className="flex items-center gap-4">
          {user ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60">
                <div className="w-7 h-7 rounded-full bg-amber-500/20 text-amber-300 flex items-center justify-center font-bold text-xs uppercase border border-amber-500/30">
                  {user.display_name?.charAt(0) || 'U'}
                </div>
                <span className="text-sm font-medium text-slate-200">{user.display_name}</span>
              </div>
              <button
                id="logout-btn"
                onClick={onLogout}
                className="p-2 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800/60 transition-colors"
                title="Sign out"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          ) : (
            <Link
              to="/login"
              className="px-4 py-2 text-sm font-semibold rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 transition-all shadow-md shadow-amber-500/20"
            >
              Enter Arena
            </Link>
          )}
        </div>
      </div>
    </header>
  );
};
