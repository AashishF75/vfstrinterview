import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ShieldAlert, ArrowLeft, Home, UserCheck } from 'lucide-react';

export default function Unauthorized() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background Glow */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute top-[20%] left-[30%] w-[500px] h-[500px] rounded-full bg-rose-600/10 blur-[130px]" />
      </div>

      <div className="relative z-10 max-w-md w-full glass-panel p-8 rounded-2xl border border-rose-900/40 text-center shadow-2xl">
        <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 flex items-center justify-center mx-auto mb-5 shadow-lg shadow-rose-500/10">
          <ShieldAlert className="w-8 h-8" />
        </div>

        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-800/60 mb-3">
          HTTP 403 Forbidden
        </span>

        <h1 className="text-2xl font-bold text-white mb-2">
          Access Restricted
        </h1>

        <p className="text-xs sm:text-sm text-slate-300 mb-6 leading-relaxed">
          You are currently signed in as <strong className="text-white">{user?.email}</strong> with role <strong className="text-amber-300 uppercase font-mono">{user?.role}</strong>. This section requires elevated administrative privileges.
        </p>

        <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 text-left text-xs text-slate-400 space-y-1 mb-6">
          <div className="text-slate-300 font-semibold flex items-center gap-1.5">
            <UserCheck className="w-3.5 h-3.5 text-indigo-400" />
            <span>Role-Based Access Control (RBAC)</span>
          </div>
          <div className="text-[11px] text-slate-400">
            VFSTR security policy isolates student workspaces from administrative consoles.
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/dashboard"
            className="px-4 py-2.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center justify-center space-x-1.5 shadow-md shadow-indigo-600/20"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Go to My Workspace</span>
          </Link>

          <Link
            to="/"
            className="px-4 py-2.5 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700 transition flex items-center justify-center space-x-1.5"
          >
            <Home className="w-3.5 h-3.5" />
            <span>Home</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
