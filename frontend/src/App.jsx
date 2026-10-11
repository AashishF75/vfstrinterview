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
  LogOut,
  UserCheck,
  Cpu,
  X
} from 'lucide-react';
import { checkBackendHealth } from './api/client';
import { useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import AnimatedGlobe from './components/AnimatedGlobe';
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
  const [showDiagnosticsModal, setShowDiagnosticsModal] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);

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
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col selection:bg-cyan-500/30 selection:text-cyan-200 relative overflow-hidden">
      {/* Background Ambient Lighting & Subtle Grid */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute top-[-10%] right-[15%] w-[700px] h-[700px] rounded-full bg-cyan-600/10 blur-[160px]" />
        <div className="absolute top-[25%] left-[-15%] w-[600px] h-[600px] rounded-full bg-indigo-600/10 blur-[150px]" />
        <div className="absolute bottom-[-10%] right-[25%] w-[750px] h-[750px] rounded-full bg-violet-600/10 blur-[180px]" />
        <div className="absolute inset-0 cyber-grid radial-fade-mask opacity-60" />
      </div>

      {/* Top University Identity Bar */}
      <div className="relative z-10 border-b border-slate-900 bg-slate-950/80 backdrop-blur-md px-4 py-2 text-xs">
        <div className="max-w-7xl mx-auto flex flex-wrap justify-between items-center gap-2 text-slate-400">
          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950/80 text-rose-400 border border-rose-800/50 tracking-wider">
              VFSTR
            </span>
            <span className="font-semibold text-slate-300">
              Vignan's Foundation for Science, Technology & Research
            </span>
            <span className="hidden sm:inline text-slate-600">•</span>
            <span className="hidden sm:inline text-slate-400 font-medium">
              Deemed to be University (NAAC A+)
            </span>
          </div>

          <div className="flex items-center space-x-3 text-[11px]">
            <button
              onClick={() => setShowDiagnosticsModal(true)}
              className="flex items-center space-x-1.5 text-slate-400 hover:text-cyan-300 transition"
              title="Inspect system diagnostics"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${healthData ? 'bg-cyan-400 animate-pulse' : healthLoading ? 'bg-amber-400' : 'bg-rose-400'}`} />
              <span>{healthData ? 'System Operational' : healthLoading ? 'Connecting...' : 'API Offline'}</span>
            </button>
            <span className="text-slate-700 hidden sm:inline">|</span>
            <span className="text-slate-500 hidden sm:inline">Vadlamudi, Guntur</span>
          </div>
        </div>
      </div>

      {/* Primary Navigation Header */}
      <header className="relative z-10 border-b border-slate-900/80 bg-slate-950/50 backdrop-blur-xl sticky top-0">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 via-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 border border-cyan-400/30">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="text-base font-extrabold tracking-tight text-white flex items-center gap-2">
                <span>Adaptive Interview Intelligence</span>
                <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  VFSTR
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {isAuthenticated ? (
              <>
                <Link
                  to="/dashboard"
                  className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-900 text-cyan-300 hover:text-white hover:bg-slate-800 border border-cyan-500/40 transition shadow-sm"
                >
                  <UserCheck className="w-3.5 h-3.5 text-cyan-400" />
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
                  className="inline-flex items-center space-x-1 p-2 rounded-lg text-slate-400 hover:text-rose-300 hover:bg-slate-900/60 border border-transparent hover:border-slate-800 transition"
                  title="Sign out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </>
            ) : (
              <div className="flex items-center space-x-2">
                <Link
                  to="/register"
                  className="hidden sm:inline-flex items-center px-3.5 py-1.5 text-xs font-medium rounded-lg text-slate-300 hover:text-white hover:bg-slate-900 border border-slate-800 transition"
                >
                  Student Register
                </Link>
                <Link
                  id="header-login-link"
                  to="/login"
                  className="inline-flex items-center space-x-1.5 px-4 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-cyan-600 via-indigo-600 to-violet-600 hover:from-cyan-500 hover:to-violet-500 text-white shadow-md shadow-cyan-500/20 transition"
                >
                  <Lock className="w-3.5 h-3.5 text-cyan-200" />
                  <span>Portal Login</span>
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="relative z-10 flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full flex flex-col justify-center">
        {/* Cinematic Hero Section with Centerpiece 3D Animated Globe */}
        <section className="relative pt-8 sm:pt-14 pb-16 lg:pb-24">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-8 items-center">
            {/* Left Column: Headline, Concise Narrative & Action CTAs */}
            <div className="lg:col-span-5 flex flex-col items-start text-left z-10">
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white mb-6 leading-[1.12]">
                Intelligence for Every <br />
                <span className="gradient-text">Interview</span>
              </h1>

              <p className="text-base sm:text-lg text-slate-300 leading-relaxed font-normal mb-8 max-w-xl">
                Adaptive technical assessment calibrated for university campus placements. Practice interview questions that dynamically adjust to your responses, receive structured feedback, and prepare for institutional evaluations.
              </p>

              <div className="flex flex-wrap items-center gap-4 w-full sm:w-auto">
                <Link
                  id="hero-student-btn"
                  to={isAuthenticated ? "/dashboard" : "/login"}
                  className="w-full sm:w-auto inline-flex items-center justify-center space-x-2.5 px-8 py-3.5 rounded-xl bg-gradient-to-r from-cyan-500 via-indigo-600 to-violet-600 text-white font-semibold text-sm shadow-xl shadow-cyan-600/20 hover:shadow-cyan-600/35 hover:opacity-95 transition active:scale-[0.99]"
                >
                  <GraduationCap className="w-4 h-4 text-cyan-200" />
                  <span>Start Interview Practice</span>
                  <ArrowRight className="w-4 h-4 ml-1 text-cyan-200" />
                </Link>

                <Link
                  id="hero-admin-btn"
                  to={isAuthenticated ? (hasRole(['platform_admin', 'university_admin', 'department_admin']) ? '/admin' : '/dashboard') : '/login'}
                  className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-6 py-3.5 rounded-xl bg-slate-900/80 text-slate-200 hover:text-white hover:bg-slate-800 font-semibold text-sm border border-slate-800 transition"
                >
                  <Users className="w-4 h-4 text-violet-400" />
                  <span>Institution Portal</span>
                </Link>
              </div>
            </div>

            {/* Right Column: Large, Bright 3D Animated Particle Globe */}
            <div className="lg:col-span-7 flex items-center justify-center lg:justify-end relative">
              <div className="w-full max-w-[580px] lg:max-w-[660px] xl:max-w-[680px] flex items-center justify-center">
                <AnimatedGlobe size={680} className="w-full" />
              </div>
            </div>
          </div>
        </section>

        {/* Clean, Concise Core Capabilities Overview */}
        <section className="border-t border-slate-900/90 pt-16 pb-16">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl bg-slate-950/40 border border-slate-900 hover:border-slate-800 transition">
              <div className="w-10 h-10 rounded-xl bg-cyan-950/60 border border-cyan-800/40 text-cyan-400 flex items-center justify-center mb-4">
                <Cpu className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Adaptive Technical Practice</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Interview questions adjust dynamically based on candidate answer depth and conceptual accuracy, simulating technical panel interviews.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-950/40 border border-slate-900 hover:border-slate-800 transition">
              <div className="w-10 h-10 rounded-xl bg-indigo-950/60 border border-indigo-800/40 text-indigo-400 flex items-center justify-center mb-4">
                <GraduationCap className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Institutional Cohort Management</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Faculty and administrators schedule department interview sessions, assign verified students by registration number, and track completion.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-950/40 border border-slate-900 hover:border-slate-800 transition">
              <div className="w-10 h-10 rounded-xl bg-violet-950/60 border border-violet-800/40 text-violet-400 flex items-center justify-center mb-4">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Structured Evaluation & Telemetry</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Detailed dimensional feedback across technical correctness and communication, supported by privacy-focused Level 1 proctoring integrity tracking.
              </p>
            </div>
          </div>
        </section>
      </main>

      {/* Institutional Footer with Clean Diagnostic Action */}
      <footer className="relative z-10 border-t border-slate-900 bg-[#030712] py-8 px-4 sm:px-6 lg:px-8 text-xs text-slate-400">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-2 text-slate-300">
            <span className="font-semibold text-white">Adaptive Interview Intelligence</span>
            <span>•</span>
            <span>Vignan's Foundation for Science, Technology & Research (VFSTR)</span>
          </div>

          <div className="flex items-center space-x-4 text-slate-400">
            <span>NAAC A+ Accredited • Vadlamudi, Guntur</span>
            <span className="text-slate-700">•</span>
            <button
              onClick={() => setShowDiagnosticsModal(true)}
              className="text-cyan-400 hover:text-cyan-300 transition underline underline-offset-4"
            >
              System Diagnostics
            </button>
          </div>
        </div>
      </footer>

      {/* Dedicated System Diagnostics Modal Dialog */}
      {showDiagnosticsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-5">
              <div className="flex items-center space-x-2">
                <Activity className="w-5 h-5 text-cyan-400" />
                <h3 className="text-sm font-bold text-white">System Diagnostics & API Status</h3>
              </div>
              <button
                onClick={() => setShowDiagnosticsModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 mb-6">
              <div className="flex justify-between items-center p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs">
                <span className="text-slate-400">FastAPI Application Service</span>
                <span className="font-semibold flex items-center space-x-1.5">
                  {healthLoading ? (
                    <span className="text-amber-400 flex items-center space-x-1">
                      <RefreshCw className="w-3 h-3 animate-spin" />
                      <span>Probing...</span>
                    </span>
                  ) : healthData ? (
                    <span className="text-emerald-400 flex items-center space-x-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Operational (200 OK)</span>
                    </span>
                  ) : (
                    <span className="text-rose-400 flex items-center space-x-1">
                      <AlertCircle className="w-3.5 h-3.5" />
                      <span>Unreachable</span>
                    </span>
                  )}
                </span>
              </div>

              <div className="flex justify-between items-center p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs">
                <span className="text-slate-400">Assigned Institution</span>
                <span className="text-white font-medium truncate max-w-[220px]">
                  {healthData?.institution || 'Vignan University (VFSTR)'}
                </span>
              </div>

              <div className="flex justify-between items-center p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs">
                <span className="text-slate-400">Environment & Version</span>
                <span className="text-cyan-300 font-mono font-medium">
                  {healthData ? `${healthData.version} (${healthData.environment})` : 'Unavailable'}
                </span>
              </div>

              <div className="flex justify-between items-center p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs">
                <span className="text-slate-400">MongoDB Atlas Connectivity</span>
                <span className="text-emerald-300 font-medium flex items-center space-x-1.5">
                  <Database className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{healthData?.database?.status === 'connected' ? 'Connected (Live)' : 'Unavailable'}</span>
                </span>
              </div>
            </div>

            {/* Toggle Raw JSON */}
            <div className="mb-5">
              <button
                onClick={() => setShowRawJson(!showRawJson)}
                className="text-[11px] font-mono text-cyan-400 hover:text-cyan-300 flex items-center space-x-1 transition"
              >
                <Terminal className="w-3 h-3" />
                <span>{showRawJson ? 'Hide JSON Response' : 'Inspect Raw /api/health JSON'}</span>
              </button>

              {showRawJson && (
                <pre className="mt-2 text-xs font-mono text-cyan-300 overflow-x-auto p-3 bg-slate-950 rounded-xl border border-slate-800 max-h-48">
                  {healthLoading
                    ? '/* Probing /api/health... */'
                    : healthData
                    ? JSON.stringify(healthData, null, 2)
                    : `/* Error: ${healthError} */`
                  }
                </pre>
              )}
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800 text-xs">
              <span className="text-slate-500 font-mono text-[11px]">
                {lastChecked ? `Last probe: ${lastChecked}` : ''}
              </span>
              <div className="flex items-center space-x-2">
                <button
                  onClick={fetchHealth}
                  disabled={healthLoading}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium flex items-center space-x-1.5 transition"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${healthLoading ? 'animate-spin text-cyan-400' : ''}`} />
                  <span>Execute Probe</span>
                </button>
                <button
                  onClick={() => setShowDiagnosticsModal(false)}
                  className="px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium transition"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
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
