import React, { useState, useEffect, useCallback } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { 
  Activity, 
  ShieldCheck, 
  Terminal, 
  Lock, 
  GraduationCap, 
  Users, 
  Database, 
  ArrowRight, 
  CheckCircle2, 
  RefreshCw, 
  AlertCircle,
  Sparkles,
  ChevronRight,
  LogOut,
  UserCheck
} from 'lucide-react';
import { checkBackendHealth } from './api/client';
import { useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import AdminConsole from './pages/AdminConsole';
import InterviewRoom from './pages/InterviewRoom';
import Unauthorized from './pages/Unauthorized';

function HomePage() {
  const [healthData, setHealthData] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);

  const { user, isAuthenticated, logout, hasRole } = useAuth();

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const result = await checkBackendHealth();
      if (result.success) {
        setHealthData(result.data);
      } else {
        setHealthError(typeof result.error === 'string' ? result.error : 'Service unavailable');
      }
    } catch (err) {
      setHealthError(err.message || 'Error communicating with backend');
    } finally {
      setHealthLoading(false);
      setLastChecked(new Date().toLocaleTimeString());
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Background Ambient Glows */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] rounded-full bg-indigo-600/15 blur-[120px]" />
        <div className="absolute top-[20%] right-[-5%] w-[450px] h-[450px] rounded-full bg-violet-600/10 blur-[130px]" />
        <div className="absolute bottom-[-10%] left-[30%] w-[600px] h-[600px] rounded-full bg-blue-600/10 blur-[140px]" />
      </div>

      {/* Top University Branding Bar */}
      <div className="relative z-10 border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-md px-4 py-2 text-xs">
        <div className="max-w-7xl mx-auto flex flex-wrap justify-between items-center gap-2 text-slate-400">
          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-950/80 text-rose-400 border border-rose-800/50">
              VFSTR
            </span>
            <span className="font-medium text-slate-300">
              Vignan's Foundation for Science, Technology & Research
            </span>
            <span className="hidden sm:inline text-slate-600">•</span>
            <span className="hidden sm:inline text-slate-400">
              Deemed to be University (NAAC A+)
            </span>
          </div>

          <div className="flex items-center space-x-3 text-[11px]">
            <span className="flex items-center space-x-1.5 text-emerald-400 bg-emerald-950/60 border border-emerald-800/40 px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Phase 2 RBAC & Auth Active</span>
            </span>
            <span className="text-slate-500">|</span>
            <span className="text-slate-400">Vadlamudi, Guntur</span>
          </div>
        </div>
      </div>

      {/* Navigation Header */}
      <header className="relative z-10 border-b border-slate-800/60 bg-slate-900/40 backdrop-blur-xl sticky top-0">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 border border-indigo-400/30">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="text-base font-bold tracking-tight text-white flex items-center gap-2">
                Adaptive Interview Intelligence
                <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  VFSTR
                </span>
              </div>
              <div className="text-xs text-slate-400 hidden sm:block">
                Autonomous AI Campus Placement Assessment Architecture
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={fetchHealth}
              disabled={healthLoading}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 border border-slate-700/60 transition shadow-sm hover:border-slate-600"
              title="Re-verify backend health"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${healthLoading ? 'animate-spin text-indigo-400' : 'text-slate-400'}`} />
              <span className="hidden md:inline">API Probe</span>
            </button>

            {isAuthenticated ? (
              <>
                <Link
                  to="/dashboard"
                  className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium rounded-lg bg-slate-800 text-indigo-300 hover:text-white hover:bg-slate-750 border border-indigo-500/40 transition"
                >
                  <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Workspace ({user?.role})</span>
                </Link>

                {hasRole(['platform_admin', 'university_admin', 'department_admin']) && (
                  <Link
                    to="/admin"
                    className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white shadow-md shadow-indigo-500/20 transition"
                  >
                    <ShieldCheck className="w-3.5 h-3.5 text-white" />
                    <span>Admin Suite</span>
                  </Link>
                )}

                <button
                  onClick={logout}
                  className="inline-flex items-center space-x-1 px-2.5 py-1.5 text-xs text-slate-400 hover:text-rose-300 transition"
                  title="Sign out"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </>
            ) : (
              <Link
                id="header-login-link"
                to="/login"
                className="inline-flex items-center space-x-1.5 px-4 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white shadow-md shadow-indigo-500/20 transition"
              >
                <Lock className="w-3.5 h-3.5 text-indigo-200" />
                <span>Portal Login</span>
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="relative z-10 flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 w-full">
        {/* Phase Status Banner */}
        <div className="mb-10 rounded-2xl p-4 sm:p-5 bg-gradient-to-r from-emerald-500/10 via-indigo-500/10 to-violet-500/10 border border-emerald-500/30 backdrop-blur-md relative overflow-hidden">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-start space-x-3.5">
              <div className="p-2 rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 shrink-0 mt-0.5 md:mt-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-emerald-200 flex items-center gap-2">
                  <span>Phase 2 Operational: Secure Authentication & Role-Based Access Control</span>
                  <span className="text-[11px] font-normal px-2 py-0.5 rounded-full bg-emerald-400/20 text-emerald-300 border border-emerald-400/30">
                    Phase 2 of 4
                  </span>
                </h4>
                <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                  Real authentication pipeline with bcrypt password verification, signed JWT tokens, role-based authorization guards, rate-limited login protection, and secure admin provisioning is now active.
                </p>
              </div>
            </div>
            <div className="shrink-0">
              <Link
                to={isAuthenticated ? "/dashboard" : "/login"}
                className="inline-flex items-center space-x-1.5 text-xs font-semibold px-4 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-200 border border-emerald-500/40 transition"
              >
                <span>{isAuthenticated ? 'Open Workspace' : 'Sign In with VFSTR ID'}</span>
                <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>

        {/* Hero Section */}
        <div className="text-center max-w-3xl mx-auto mb-16 pt-4">
          <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-indigo-950/80 border border-indigo-700/50 text-indigo-300 text-xs font-medium mb-6 backdrop-blur-sm">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
            <span>AI-Driven Technical & Behavioral Placement Training</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white mb-6 leading-tight">
            Adaptive Interview <br className="hidden sm:block" />
            <span className="gradient-text">Intelligence</span> for VFSTR
          </h1>

          <p className="text-base sm:text-lg text-slate-300 leading-relaxed font-normal mb-8">
            Empowering students of <strong className="text-slate-100 font-semibold">Vignan's Foundation for Science, Technology & Research (VFSTR)</strong> with adaptive AI mock interviews, real-time code evaluation, and deep behavioural feedback calibrated for elite global placements.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link
              id="hero-student-btn"
              to={isAuthenticated ? "/dashboard" : "/login"}
              className="inline-flex items-center space-x-2 px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 text-white font-medium text-sm shadow-lg shadow-indigo-600/30 hover:shadow-indigo-600/40 hover:opacity-95 transition"
            >
              <GraduationCap className="w-4 h-4" />
              <span>{isAuthenticated ? 'My Student Workspace' : 'Student Access Portal'}</span>
              <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Link>

            <Link
              id="hero-admin-btn"
              to={isAuthenticated ? (hasRole(['platform_admin', 'university_admin']) ? '/admin' : '/dashboard') : '/login'}
              className="inline-flex items-center space-x-2 px-6 py-3 rounded-xl bg-slate-900/90 text-slate-200 hover:text-white hover:bg-slate-800 font-medium text-sm border border-slate-700/80 transition"
            >
              <Users className="w-4 h-4 text-violet-400" />
              <span>Faculty & Admin Suite</span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-400 ml-1" />
            </Link>
          </div>
        </div>

        {/* Live Backend Health & Diagnostics Card */}
        <div className="mb-14">
          <div className="rounded-2xl glass-panel p-6 sm:p-8 border border-slate-800/80 relative overflow-hidden">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 mb-6 border-b border-slate-800/80 gap-4">
              <div>
                <div className="flex items-center space-x-2.5">
                  <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                    <Activity className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">Full-Stack Health Probe</h3>
                    <p className="text-xs text-slate-400">
                      Real-time diagnostic verification between React (Vite) and Python (FastAPI)
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex items-center space-x-3">
                {lastChecked && (
                  <span className="text-[11px] text-slate-400">
                    Last probe: {lastChecked}
                  </span>
                )}
                <button
                  onClick={fetchHealth}
                  disabled={healthLoading}
                  className="px-3.5 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-indigo-300 text-xs font-semibold flex items-center space-x-1.5 transition"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${healthLoading ? 'animate-spin' : ''}`} />
                  <span>Execute GET /api/health</span>
                </button>
              </div>
            </div>

            {/* Health Diagnostics Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {/* API Status */}
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/70">
                <div className="text-xs text-slate-400 font-medium mb-1">Backend API Status</div>
                <div className="flex items-center space-x-2">
                  {healthLoading ? (
                    <span className="text-sm text-slate-400 flex items-center space-x-1.5">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Checking...</span>
                    </span>
                  ) : healthData ? (
                    <span className="inline-flex items-center text-sm font-semibold text-emerald-400 space-x-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      <span>Operational (200 OK)</span>
                    </span>
                  ) : (
                    <span className="inline-flex items-center text-sm font-semibold text-rose-400 space-x-1.5">
                      <AlertCircle className="w-4 h-4 text-rose-400" />
                      <span>Offline / Unreachable</span>
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-400 mt-2">
                  FastAPI service responding on port 8000
                </div>
              </div>

              {/* Institution */}
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/70">
                <div className="text-xs text-slate-400 font-medium mb-1">Assigned Institution</div>
                <div className="text-sm font-semibold text-slate-100 truncate">
                  {healthData?.institution || 'Vignan University (VFSTR)'}
                </div>
                <div className="text-[11px] text-slate-400 mt-2">
                  Vadlamudi Campus, Guntur, AP
                </div>
              </div>

              {/* Environment & Version */}
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/70">
                <div className="text-xs text-slate-400 font-medium mb-1">Release & Environment</div>
                <div className="text-sm font-semibold text-indigo-300">
                  {healthData ? `${healthData.version} (${healthData.environment})` : 'v1.0.0 (Phase 2)'}
                </div>
                <div className="text-[11px] text-slate-400 mt-2">
                  {healthData?.phase || 'Phase 2 - Auth & RBAC Active'}
                </div>
              </div>

              {/* Database Layer */}
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/70">
                <div className="text-xs text-slate-400 font-medium mb-1">MongoDB Atlas Driver</div>
                <div className="flex items-center space-x-1.5 text-sm font-semibold text-emerald-300">
                  <Database className="w-4 h-4 text-emerald-400" />
                  <span>
                    {healthData?.database?.status === 'connected' ? 'Connected (Live)' : 'Driver Ready'}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-2">
                  Users collection & indexes active
                </div>
              </div>
            </div>

            {/* Raw JSON Health Payload Display */}
            <div className="rounded-xl bg-slate-950/80 border border-slate-800/90 p-4">
              <div className="flex items-center justify-between text-xs text-slate-400 font-mono mb-2 pb-2 border-b border-slate-800/60">
                <span className="flex items-center space-x-2">
                  <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                  <span>GET /api/health Payload Response</span>
                </span>
                <span className="text-[11px] text-slate-400">Content-Type: application/json</span>
              </div>
              <pre className="text-xs font-mono text-indigo-300 overflow-x-auto p-2 bg-slate-900/40 rounded-lg">
                {healthLoading 
                  ? '/* Querying http://127.0.0.1:8000/api/health via Axios client... */' 
                  : healthData 
                    ? JSON.stringify(healthData, null, 2) 
                    : `/* Error: ${healthError} */\n/* Ensure the FastAPI backend server is running on port 8000 */`
                }
              </pre>
            </div>
          </div>
        </div>

        {/* Phase Roadmap Progression */}
        <div className="mb-14">
          <div className="rounded-2xl glass-panel p-6 sm:p-8 border border-slate-800/80">
            <h3 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
              <span>VFSTR Implementation Roadmap</span>
            </h3>
            <p className="text-xs text-slate-400 mb-6">
              Step-by-step verified trajectory for the Adaptive Interview Intelligence rollout.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Step 1 */}
              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 relative">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Phase 1</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Complete
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-slate-200 mb-1">Safe Foundation</h4>
                <p className="text-xs text-slate-400">
                  Scaffold React 19 + Tailwind, FastAPI backend, /api/health endpoint, and Pytest verification.
                </p>
              </div>

              {/* Step 2 */}
              <div className="p-4 rounded-xl bg-indigo-950/40 border border-indigo-600/40 relative">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold text-indigo-400 uppercase tracking-wider">Phase 2</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Complete & Active
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white mb-1">Auth & RBAC</h4>
                <p className="text-xs text-slate-400">
                  MongoDB user model, bcrypt hashing, JWT access tokens, role authorization, rate-limiting, login UI, and admin CLI bootstrap.
                </p>
              </div>

              {/* Step 3 */}
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 relative opacity-90">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold text-amber-400 uppercase tracking-wider">Phase 3</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30">
                    Next Up
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white mb-1">Adaptive AI Engine</h4>
                <p className="text-xs text-slate-400">
                  Dynamic LLM-based technical questions, multi-difficulty branching, and real-time response evaluation.
                </p>
              </div>

              {/* Step 4 */}
              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 relative opacity-70">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Phase 4</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                    Planned
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-slate-300 mb-1">Proctoring & Drive</h4>
                <p className="text-xs text-slate-400">
                  Webcam/audio proctoring, live code compilation sandbox, and automated Google Drive report archival.
                </p>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-slate-800/80 bg-slate-950 py-8 px-4 sm:px-6 lg:px-8 text-xs text-slate-400">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <span className="font-semibold text-slate-300">
              Adaptive Interview Intelligence
            </span>
            <span>•</span>
            <span>Vignan University (VFSTR)</span>
          </div>

          <div className="text-slate-400 text-center md:text-right">
            Phase 2 Authentication Operational • Next Phase: Adaptive AI Mock Interview Engine
          </div>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/interview/:assignmentId"
        element={
          <ProtectedRoute allowedRoles={['student', 'platform_admin', 'university_admin', 'department_admin']}>
            <InterviewRoom />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <ProtectedRoute allowedRoles={['platform_admin', 'university_admin', 'department_admin']}>
            <AdminConsole />
          </ProtectedRoute>
        }
      />
      <Route path="/unauthorized" element={<Unauthorized />} />
      <Route path="*" element={<HomePage />} />
    </Routes>
  );
}
