import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Navbar } from './components/Navbar';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { LobbyPage } from './pages/LobbyPage';
import { RoomPage } from './pages/RoomPage';
import { ApiService } from './services/api';

export const App: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<any>(null);

  useEffect(() => {
    const user = ApiService.getStoredUser();
    if (user) {
      setCurrentUser(user);
    }
  }, []);

  const handleLogout = () => {
    ApiService.clearToken();
    setCurrentUser(null);
  };

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-950 flex flex-col justify-between">
        <Navbar user={currentUser} onLogout={handleLogout} />
        
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage onLoginSuccess={setCurrentUser} />} />
            <Route
              path="/lobby"
              element={currentUser ? <LobbyPage /> : <Navigate to="/login" replace />}
            />
            <Route
              path="/room/:roomId"
              element={currentUser ? <RoomPage /> : <Navigate to="/login" replace />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <footer className="border-t border-slate-900 bg-slate-950/80 py-6 text-center text-xs text-slate-500">
          <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
            <span>CardArena Platform &copy; Phase 1 Foundation</span>
            <span className="font-mono text-[11px] text-slate-400">Server-Authoritative Multi-Game Core</span>
          </div>
        </footer>
      </div>
    </BrowserRouter>
  );
};

export default App;
