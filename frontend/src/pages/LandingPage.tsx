import React from 'react';
import { Link } from 'react-router-dom';
import { Spade, Heart, Club, Diamond, ShieldCheck, Zap, RefreshCw } from 'lucide-react';

export const LandingPage: React.FC = () => {
  return (
    <div className="relative overflow-hidden pt-12 pb-24">
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center relative z-10">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-semibold mb-8">
          <ShieldCheck className="w-4 h-4 text-amber-400" /> Server-Authoritative Architecture
        </div>

        <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black tracking-tight text-white max-w-4xl mx-auto leading-tight">
          Next-Gen Multiplayer <br />
          <span className="bg-gradient-to-r from-amber-400 via-orange-400 to-amber-200 bg-clip-text text-transparent">
            Card Arena Platform
          </span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-slate-400 max-w-2xl mx-auto font-normal leading-relaxed">
          Create private rooms, invite friends, and play classic card games in realtime. 
          Zero client-trust security, cryptographically shuffled decks, and seamless reconnection.
        </p>

        <div className="flex items-center justify-center gap-6 my-10">
          <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-300 shadow-md">
            <Spade className="w-6 h-6 fill-slate-300" />
          </div>
          <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-rose-500 shadow-md">
            <Heart className="w-6 h-6 fill-rose-500" />
          </div>
          <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-300 shadow-md">
            <Club className="w-6 h-6 fill-slate-300" />
          </div>
          <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-rose-500 shadow-md">
            <Diamond className="w-6 h-6 fill-rose-500" />
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            id="get-started-cta"
            to="/lobby"
            className="w-full sm:w-auto px-8 py-4 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-base shadow-lg shadow-amber-500/25 transition-all transform hover:-translate-y-0.5"
          >
            Launch Lobby & Play
          </Link>
          <Link
            to="/login"
            className="w-full sm:w-auto px-8 py-4 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 font-semibold text-base border border-slate-800 hover:border-slate-700 transition-all"
          >
            Switch Identity
          </Link>
        </div>

        <div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
          <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-sm">
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center mb-4">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-bold text-white mb-2">Zero-Trust Authoritative Engine</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Decks, hands, scores, and turns are computed strictly server-side. No player hand is ever broadcasted to unauthorized peers.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-sm">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-4">
              <Zap className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-bold text-white mb-2">Realtime WebSocket Sync</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Instant room presence, ready toggles, host permission controls, and state broadcast over low-latency WebSockets.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-sm">
            <div className="w-10 h-10 rounded-lg bg-sky-500/10 text-sky-400 flex items-center justify-center mb-4">
              <RefreshCw className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-bold text-white mb-2">Session Reconnection</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Temporary connection drops never destroy room seats. Transparent auto-reconnect restores authoritative state immediately.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
