import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  getProtectedTest,
  getAdminOnlyTest,
  getStudentAssignments,
  acceptStudentAssignment,
  startStudentInterview,
  completeStudentInterview,
  getAvailableJobRoles,
  selectStudentJobRole,
} from '../api/client';
import StudentPerformanceDashboard from '../components/StudentPerformanceDashboard';
import {
  User,
  Shield,
  LogOut,
  CheckCircle2,
  Sparkles,
  Terminal,
  Activity,
  Lock,
  Calendar,
  Clock,
  Check,
  Play,
  AlertCircle,
  RefreshCw,
  FileText,
  Award,
  Briefcase,
  Loader2,
  BookOpen,
  BrainCircuit,
  GraduationCap,
  ChevronRight,
  ExternalLink,
  Cpu,
  Workflow,
  Binary,
  ShieldCheck,
  Zap,
} from 'lucide-react';

// Official Canonical Roles matching verified question bank specifications
const CANONICAL_FALLBACK_ROLES = [
  {
    role_id: 'associate-software-engineer',
    role_name: 'Associate Software Engineer',
    description: 'Entry-level software engineering, algorithmic logic, object-oriented concepts, and core technical problem solving.',
    conceptual_questions_per_set: 13,
    coding_questions_per_set: 2,
    total_sets: 25,
    total_questions: 375,
  },
  {
    role_id: 'product-engineer',
    role_name: 'Product Engineer',
    description: 'End-to-end product architecture, system integration, API development, scalability, and user-centric problem solving.',
    conceptual_questions_per_set: 13,
    coding_questions_per_set: 2,
    total_sets: 25,
    total_questions: 375,
  },
  {
    role_id: 'software-development-engineer',
    role_name: 'Software Development Engineer',
    description: 'Core software engineering, algorithms, data structures, backend systems, and operational coding.',
    conceptual_questions_per_set: 13,
    coding_questions_per_set: 2,
    total_sets: 25,
    total_questions: 375,
  },
  {
    role_id: 'system-engineer',
    role_name: 'System Engineer',
    description: 'Operating systems, computer networks, system design, infrastructure engineering, and cloud deployment.',
    conceptual_questions_per_set: 13,
    coding_questions_per_set: 2,
    total_sets: 25,
    total_questions: 375,
  },
  {
    role_id: 'testing-engineer',
    role_name: 'Testing Engineer',
    description: 'Quality assurance, test automation, unit/integration/regression testing, validation methodologies, and debugging.',
    conceptual_questions_per_set: 13,
    coding_questions_per_set: 2,
    total_sets: 25,
    total_questions: 375,
  },
];

// Curated visuals and metadata for each canonical engineering role
const getRoleVisuals = (roleName) => {
  const name = (roleName || '').toLowerCase();
  if (name.includes('development') || name.includes('sde') || name.includes('software development')) {
    return {
      Icon: Terminal,
      badgeText: 'Algorithmic & Backend',
      tagline: 'High Volume Coding',
      accent: 'cyan',
    };
  }
  if (name.includes('product')) {
    return {
      Icon: Workflow,
      badgeText: 'Architecture & Systems',
      tagline: 'End-to-End Solutions',
      accent: 'indigo',
    };
  }
  if (name.includes('system')) {
    return {
      Icon: Cpu,
      badgeText: 'Networks & Infra',
      tagline: 'Core OS & Cloud',
      accent: 'violet',
    };
  }
  if (name.includes('test') || name.includes('quality')) {
    return {
      Icon: ShieldCheck,
      badgeText: 'QA & Automation',
      tagline: 'Robust Verification',
      accent: 'emerald',
    };
  }
  if (name.includes('associate')) {
    return {
      Icon: Binary,
      badgeText: 'Fundamentals & Logic',
      tagline: 'Entry-Level Track',
      accent: 'cyan',
    };
  }
  return {
    Icon: Briefcase,
    badgeText: 'Engineering Track',
    tagline: 'Technical Assessment',
    accent: 'cyan',
  };
};

export default function Dashboard() {
  const { user, logout, hasRole } = useAuth();
  const navigate = useNavigate();

  const [testResult, setTestResult] = useState(null);
  const [testLoading, setTestLoading] = useState(false);

  // Student Assignments state
  const [assignments, setAssignments] = useState([]);
  const [assignmentsLoading, setAssignmentsLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [assignmentError, setAssignmentError] = useState(null);

  // Job Role Selection state
  const [roles, setRoles] = useState(CANONICAL_FALLBACK_ROLES);
  const [rolesLoading, setRolesLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState('Software Development Engineer');
  const [roleStarting, setRoleStarting] = useState(false);
  const [roleError, setRoleError] = useState(null);

  const fetchStudentAssignments = useCallback(async () => {
    if (user?.role !== 'student') return;
    setAssignmentsLoading(true);
    setAssignmentError(null);
    const res = await getStudentAssignments();
    if (res.success) {
      setAssignments(res.data);
    } else {
      setAssignmentError(res.error);
    }
    setAssignmentsLoading(false);
  }, [user]);

  useEffect(() => {
    fetchStudentAssignments();
  }, [fetchStudentAssignments]);

  // Load available canonical job roles
  useEffect(() => {
    if (user?.role !== 'student') return;
    let isMounted = true;
    const fetchRoles = async () => {
      setRolesLoading(true);
      const res = await getAvailableJobRoles();
      if (isMounted && res.success && res.data?.roles && res.data.roles.length > 0) {
        setRoles(res.data.roles);
      }
      if (isMounted) setRolesLoading(false);
    };
    fetchRoles();
    return () => {
      isMounted = false;
    };
  }, [user]);

  const handleStartRoleInterview = async (roleName) => {
    if (!roleName || roleStarting) return;
    setRoleStarting(true);
    setRoleError(null);
    const res = await selectStudentJobRole(roleName);
    if (res.success && res.data?.assignment_id) {
      navigate(`/interview/${res.data.assignment_id}`);
    } else {
      setRoleError(res.error || 'Failed to initialize role interview session');
      setRoleStarting(false);
    }
  };

  const handleTestProtected = async () => {
    setTestLoading(true);
    setTestResult(null);
    const res = await getProtectedTest();
    setTestResult({
      endpoint: 'GET /api/auth/protected-test',
      status: res.success ? 200 : res.status || 500,
      data: res.success ? res.data : { error: res.error },
      success: res.success,
    });
    setTestLoading(false);
  };

  const handleTestAdminOnly = async () => {
    setTestLoading(true);
    setTestResult(null);
    const res = await getAdminOnlyTest();
    setTestResult({
      endpoint: 'GET /api/auth/admin-only (Role Check)',
      status: res.success ? 200 : res.status || 403,
      data: res.success ? res.data : { error: res.error },
      success: res.success,
    });
    setTestLoading(false);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  // Student Lifecycle Transitions
  const handleAcceptAssignment = async (assignmentId) => {
    setActionLoadingId(assignmentId);
    const res = await acceptStudentAssignment(assignmentId);
    if (res.success) {
      fetchStudentAssignments();
    } else {
      alert(res.error || 'Failed to accept interview');
    }
    setActionLoadingId(null);
  };

  const handleStartInterview = async (assignmentId) => {
    setActionLoadingId(assignmentId);
    const res = await startStudentInterview(assignmentId);
    if (res.success) {
      fetchStudentAssignments();
    } else {
      alert(res.error || 'Failed to start interview');
    }
    setActionLoadingId(null);
  };

  const handleCompleteInterview = async (assignmentId) => {
    setActionLoadingId(assignmentId);
    const res = await completeStudentInterview(assignmentId);
    if (res.success) {
      fetchStudentAssignments();
    } else {
      alert(res.error || 'Failed to complete interview');
    }
    setActionLoadingId(null);
  };

  const institutionLabel = user?.college_name || (user?.institution_id === 'VFSTR' ? 'Vignan University (VFSTR)' : user?.institution_id || 'Partner University');

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100 flex flex-col selection:bg-cyan-500/30">
      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-[#0a101f]/90 backdrop-blur-xl sticky top-0 z-30 shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Link
              to="/"
              className="group flex items-center space-x-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 rounded-xl p-1 transition-all duration-200"
            >
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-600 via-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-cyan-600/20 ring-1 ring-cyan-400/30 group-hover:shadow-[0_0_18px_rgba(6,182,212,0.4)] group-hover:ring-cyan-400/60 group-hover:scale-105 transition-all duration-200">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center sm:space-x-2">
                <span className="font-bold text-white group-hover:text-cyan-200 text-sm tracking-tight transition-colors duration-200">
                  Adaptive Interview Intelligence
                </span>
                <span className="hidden sm:inline-block text-[10px] uppercase font-bold px-2 py-0.5 rounded-md bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 group-hover:border-cyan-600/70 tracking-wider transition-colors duration-200">
                  VFSTR
                </span>
              </div>
            </Link>
          </div>

          <div className="flex items-center space-x-2.5 sm:space-x-3">
            {/* Institution Badge */}
            <div className="hidden md:flex items-center space-x-2 px-3 py-1.5 rounded-xl bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition-all duration-200 cursor-default shadow-sm group">
              <GraduationCap className="w-3.5 h-3.5 text-cyan-400 group-hover:text-cyan-300 transition-colors duration-200" />
              <span className="truncate max-w-[180px] font-medium">{institutionLabel}</span>
            </div>

            {hasRole(['platform_admin', 'university_admin', 'department_admin']) && (
              <Link
                to="/admin"
                className="text-xs px-3.5 py-1.5 rounded-xl bg-indigo-600/20 text-indigo-300 hover:bg-indigo-600/30 hover:text-white border border-indigo-500/30 hover:border-indigo-400/60 font-medium transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] flex items-center space-x-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                <Shield className="w-3.5 h-3.5" />
                <span>Admin Console</span>
              </Link>
            )}

            <button
              id="logout-button"
              onClick={handleLogout}
              className="text-xs px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700/80 hover:border-slate-600 transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 active:bg-slate-850 active:scale-[0.98] flex items-center space-x-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 group"
              title="Sign out of interview workspace"
            >
              <LogOut className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-300 transition-colors" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full flex-1">
        {/* Welcome Banner */}
        <div className="mb-8 p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-[#0c1527] via-[#08101d] to-[#060a14] border border-slate-800/80 shadow-2xl relative overflow-hidden">
          {/* Ambient glowing gradients */}
          <div className="absolute -top-28 -right-28 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute -bottom-24 -left-24 w-80 h-80 bg-violet-600/10 rounded-full blur-3xl pointer-events-none" />

          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
            <div className="space-y-3 max-w-2xl">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="text-xs font-semibold px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center space-x-2 shadow-[0_0_12px_rgba(16,185,129,0.15)]">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
                  </span>
                  <span>Authenticated Session Active</span>
                </span>
                <span className="text-xs font-mono text-cyan-300 bg-cyan-950/70 border border-cyan-800/60 px-3 py-1 rounded-full shadow-[0_0_12px_rgba(6,182,212,0.1)]">
                  ID: {user?.registration_number || user?.email}
                </span>
              </div>
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-slate-300 tracking-tight">
                Welcome, {user?.full_name || user?.email}
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 leading-relaxed max-w-xl">
                Adaptive AI Mock Interview Platform for engineering placements. Real-time conceptual evaluation, live sandbox code execution, and university-aligned rubric assessments.
              </p>
            </div>

            {/* Quick Readiness Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full lg:w-auto">
              {/* Question Bank */}
              <div className="group relative p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 hover:border-cyan-500/50 hover:bg-[#0e172a] hover:-translate-y-1.5 hover:shadow-[0_12px_28px_-6px_rgba(6,182,212,0.25)] transition-all duration-300 ease-out overflow-hidden cursor-default">
                <div className="absolute top-0 right-0 w-20 h-20 bg-cyan-500/10 rounded-full blur-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                <div className="flex items-center space-x-2 text-cyan-400 text-xs font-semibold mb-1.5">
                  <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 group-hover:scale-110 group-hover:rotate-3 transition-transform duration-300">
                    <BookOpen className="w-4 h-4 text-cyan-400" />
                  </div>
                  <span>Question Bank</span>
                </div>
                <div className="text-xl sm:text-2xl font-extrabold text-white font-mono tracking-tight">1,875</div>
                <div className="text-[11px] text-slate-400 group-hover:text-slate-300 transition-colors">Official Questions</div>
              </div>

              {/* Roles Covered */}
              <div className="group relative p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 hover:border-violet-500/50 hover:bg-[#0e162d] hover:-translate-y-1.5 hover:shadow-[0_12px_28px_-6px_rgba(139,92,246,0.25)] transition-all duration-300 ease-out overflow-hidden cursor-default">
                <div className="absolute top-0 right-0 w-20 h-20 bg-violet-500/10 rounded-full blur-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                <div className="flex items-center space-x-2 text-violet-400 text-xs font-semibold mb-1.5">
                  <div className="p-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20 group-hover:scale-110 group-hover:-rotate-3 transition-transform duration-300">
                    <BrainCircuit className="w-4 h-4 text-violet-400" />
                  </div>
                  <span>Roles Covered</span>
                </div>
                <div className="text-xl sm:text-2xl font-extrabold text-white font-mono tracking-tight">5 Canonical</div>
                <div className="text-[11px] text-slate-400 group-hover:text-slate-300 transition-colors">125 Problem Sets</div>
              </div>

              {/* AI Evaluator */}
              <div className="group relative p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 hover:border-emerald-500/50 hover:bg-[#0a1820] hover:-translate-y-1.5 hover:shadow-[0_12px_28px_-6px_rgba(16,185,129,0.25)] transition-all duration-300 ease-out overflow-hidden cursor-default">
                <div className="absolute top-0 right-0 w-20 h-20 bg-emerald-500/10 rounded-full blur-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                <div className="flex items-center space-x-2 text-emerald-400 text-xs font-semibold mb-1.5">
                  <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 group-hover:scale-110 transition-transform duration-300">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  </div>
                  <span>AI Evaluator</span>
                </div>
                <div className="text-xl sm:text-2xl font-extrabold text-emerald-400 font-mono tracking-tight flex items-center space-x-1.5">
                  <span>Online</span>
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
                </div>
                <div className="text-[11px] text-slate-400 group-hover:text-slate-300 transition-colors">Gemini & Sandbox</div>
              </div>
            </div>
          </div>
        </div>

        {/* STUDENT PERFORMANCE TRACKING & PERSONALIZED LEVEL RECOMMENDATION */}
        {user?.role === 'student' && (
          <StudentPerformanceDashboard
            user={user}
            onStartInterview={handleStartRoleInterview}
          />
        )}

        {/* ROLE SELECTION & SELF-ENROLLMENT SECTION */}
        {user?.role === 'student' && (
          <section className="mb-8 p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-[#091122]/90 via-[#080e1b]/90 to-[#060a14]/90 border border-slate-800/80 shadow-2xl relative overflow-hidden" aria-labelledby="role-selection-heading">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600/20 to-indigo-600/20 text-cyan-400 border border-cyan-500/30 flex items-center justify-center shadow-lg shadow-cyan-950/40">
                  <Briefcase className="w-5 h-5 text-cyan-400" />
                </div>
                <div>
                  <h2 id="role-selection-heading" className="text-base sm:text-lg lg:text-xl font-bold text-white tracking-tight">
                    Select Target Job Role & Start Interview
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Select an engineering track to launch an adaptive technical mock interview from the verified repository.
                  </p>
                </div>
              </div>
              <span className="self-start sm:self-center text-xs px-3.5 py-1.5 rounded-full bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 font-semibold tracking-wide flex items-center space-x-2 shrink-0 shadow-[0_0_15px_rgba(6,182,212,0.15)]">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                <span>Verified Question Bank: 1,875 Questions</span>
              </span>
            </div>

            {roleError && (
              <div className="mb-6 p-4 rounded-xl bg-rose-950/50 border border-rose-800/60 text-rose-300 text-xs flex items-center space-x-3 shadow-md">
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
                <span className="font-medium">{roleError}</span>
              </div>
            )}

            {rolesLoading && roles.length === 0 ? (
              <div className="py-16 text-center text-xs text-slate-400 flex items-center justify-center space-x-2">
                <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
                <span>Loading available job roles...</span>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-6" role="radiogroup" aria-label="Job role selection">
                {roles.map((r) => {
                  const isSelected = selectedRole === r.role_name;
                  const Visual = getRoleVisuals(r.role_name);
                  const VisualIcon = Visual.Icon;
                  return (
                    <div
                      key={r.role_id}
                      role="radio"
                      aria-checked={isSelected}
                      tabIndex={0}
                      onClick={() => setSelectedRole(r.role_name)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedRole(r.role_name);
                        }
                      }}
                      className={`group relative p-5 sm:p-6 rounded-2xl border cursor-pointer transition-all duration-300 ease-out flex flex-col justify-between overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#070b14] ${
                        isSelected
                          ? 'bg-gradient-to-br from-[#0c2644] via-[#091e38] to-[#071324] border-cyan-400/90 shadow-[0_0_30px_-5px_rgba(34,211,238,0.35),0_14px_30px_-5px_rgba(6,182,212,0.25)] ring-1 ring-cyan-400/60 hover:-translate-y-1.5 hover:shadow-[0_0_35px_-4px_rgba(34,211,238,0.45),0_18px_36px_-6px_rgba(6,182,212,0.3)]'
                          : 'bg-[#091122]/85 border-slate-800/90 hover:border-cyan-500/50 hover:bg-[#0e1b36] hover:-translate-y-1.5 hover:shadow-[0_16px_36px_-8px_rgba(6,182,212,0.25),0_0_20px_-4px_rgba(139,92,246,0.18)]'
                      }`}
                    >
                      {/* Iridescent subtle gradient sheen on hover / selection */}
                      <div
                        className={`absolute inset-0 rounded-2xl bg-gradient-to-br from-cyan-500/12 via-transparent to-violet-500/12 pointer-events-none transition-opacity duration-300 ${
                          isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                        }`}
                      />
                      <div
                        className={`absolute -top-12 -right-12 w-32 h-32 rounded-full blur-2xl pointer-events-none transition-opacity duration-300 ${
                          isSelected ? 'bg-cyan-500/25 opacity-100' : 'bg-cyan-500/15 opacity-0 group-hover:opacity-100'
                        }`}
                      />

                      <div className="relative z-10">
                        {/* Header & Obvious Selected Indicator */}
                        <div className="flex items-start justify-between gap-3 mb-3.5">
                          <div
                            className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all duration-300 ${
                              isSelected
                                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/50 shadow-[0_0_15px_rgba(6,182,212,0.3)]'
                                : 'bg-slate-800/80 text-slate-300 border border-slate-700/60 group-hover:border-cyan-500/40 group-hover:text-cyan-300 group-hover:shadow-[0_0_12px_rgba(6,182,212,0.2)]'
                            }`}
                          >
                            <VisualIcon className="w-5 h-5 transition-transform duration-300 group-hover:scale-110 group-hover:rotate-1" />
                          </div>

                          {isSelected ? (
                            <span className="px-2.5 py-1 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-400/70 text-[10px] font-bold uppercase tracking-wider flex items-center space-x-1.5 shadow-[0_0_12px_rgba(6,182,212,0.3)] shrink-0">
                              <Check className="w-3.5 h-3.5 text-cyan-400 stroke-[3]" />
                              <span>SELECTED</span>
                            </span>
                          ) : (
                            <span className="w-5 h-5 rounded-full border border-slate-700 group-hover:border-cyan-400/70 group-hover:scale-110 transition-all duration-200 shrink-0 flex items-center justify-center mt-1">
                              <span className="w-2 h-2 rounded-full bg-transparent group-hover:bg-cyan-400/50 transition-colors" />
                            </span>
                          )}
                        </div>

                        {/* Role Title & Track Badge */}
                        <h3 className={`font-bold text-base sm:text-lg tracking-tight transition-colors duration-200 ${isSelected ? 'text-white' : 'text-slate-100 group-hover:text-white'}`}>
                          {r.role_name}
                        </h3>
                        <div className="mt-1 mb-2.5">
                          <span
                            className={`inline-block text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-md transition-colors ${
                              isSelected
                                ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-800/60'
                                : 'bg-slate-800/80 text-slate-400 border border-slate-700/60 group-hover:border-cyan-800/60 group-hover:text-cyan-300'
                            }`}
                          >
                            {Visual.badgeText}
                          </span>
                        </div>

                        {/* Description */}
                        <p className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors leading-relaxed mb-5">
                          {r.description}
                        </p>
                      </div>

                      {/* Question Bank Breakdown Footer */}
                      <div
                        className={`pt-3.5 border-t flex items-center justify-between text-xs transition-colors duration-200 relative z-10 ${
                          isSelected ? 'border-cyan-800/60' : 'border-slate-800/80 group-hover:border-slate-700/80'
                        }`}
                      >
                        <span className="font-mono text-slate-300 font-medium">
                          {r.total_sets || 25} Sets • {r.total_questions || 375} Qs
                        </span>
                        <span
                          className={`text-[11px] font-medium px-2 py-0.5 rounded border transition-colors ${
                            isSelected
                              ? 'bg-cyan-950/80 text-cyan-300 border-cyan-800/70'
                              : 'bg-slate-900/80 text-cyan-400/90 border-slate-800/80 group-hover:border-cyan-900/80'
                          }`}
                        >
                          13 Concept + 2 Code
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Action Bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-5 pb-5 px-6 rounded-2xl bg-gradient-to-r from-[#080e1c]/90 via-[#0a1426]/90 to-[#080e1c]/90 border border-slate-800/80 shadow-lg mt-3">
              <div className="text-xs text-slate-300 flex items-center space-x-2">
                <span className="text-slate-400">Active Choice:</span>
                <strong className="text-cyan-300 font-bold px-3 py-1 rounded-lg bg-cyan-950/80 border border-cyan-700/60 font-mono shadow-[0_0_12px_rgba(6,182,212,0.15)]">
                  {selectedRole}
                </strong>
                <span className="hidden md:inline text-slate-400">• 5 Adaptive Questions Target</span>
              </div>

              <button
                id="start-interview-button"
                onClick={() => handleStartRoleInterview(selectedRole)}
                disabled={roleStarting || !selectedRole}
                className="w-full sm:w-auto px-7 py-3 rounded-xl bg-gradient-to-r from-cyan-500 via-indigo-600 to-violet-600 hover:from-cyan-400 hover:via-indigo-500 hover:to-violet-500 text-white text-xs sm:text-sm font-bold shadow-[0_0_25px_rgba(6,182,212,0.35)] hover:shadow-[0_0_35px_rgba(6,182,212,0.55)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.99] transition-all duration-300 flex items-center justify-center space-x-2.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none disabled:hover:translate-y-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#09101d]"
              >
                {roleStarting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-1 text-cyan-300" />
                    <span>Initializing Interview Session...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-white" />
                    <span>Start Interview for {selectedRole}</span>
                  </>
                )}
              </button>
            </div>
          </section>
        )}

        {/* STUDENT ASSIGNED INTERVIEWS SECTION */}
        {user?.role === 'student' && (
          <section className="mb-8 p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-[#091122]/90 via-[#080e1b]/90 to-[#060a14]/90 border border-slate-800/80 shadow-2xl relative overflow-hidden" aria-labelledby="university-assigned-heading">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600/20 to-violet-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center shadow-lg shadow-indigo-950/40">
                  <Calendar className="w-5 h-5 text-indigo-400" />
                </div>
                <div>
                  <h2 id="university-assigned-heading" className="text-base sm:text-lg lg:text-xl font-bold text-white tracking-tight">
                    My University-Assigned Interviews
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Official course and cohort assessments scheduled by university faculty.
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-2.5">
                <span className="text-xs px-3 py-1 rounded-full bg-slate-800/80 text-slate-300 border border-slate-700/80 font-semibold font-mono shadow-sm">
                  {assignments.length} Total
                </span>
                <button
                  onClick={fetchStudentAssignments}
                  disabled={assignmentsLoading}
                  className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 hover:border-slate-600 text-slate-400 hover:text-cyan-300 border border-transparent transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                  title="Refresh my assignments"
                >
                  <RefreshCw className={`w-4 h-4 ${assignmentsLoading ? 'animate-spin text-cyan-400' : ''}`} />
                </button>
              </div>
            </div>

            {assignmentError && (
              <div className="mb-5 p-4 rounded-xl bg-rose-950/50 border border-rose-800/60 text-rose-300 text-xs flex items-center space-x-3 shadow-md">
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
                <span className="font-medium">{assignmentError}</span>
              </div>
            )}

            {assignmentsLoading && assignments.length === 0 ? (
              <div className="text-center py-14 text-slate-400 text-xs flex items-center justify-center space-x-2">
                <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                <span>Loading assigned interviews...</span>
              </div>
            ) : assignments.length === 0 ? (
              <div className="text-center py-12 border border-dashed border-slate-800/80 rounded-2xl bg-slate-900/30 p-6">
                <Calendar className="w-9 h-9 text-slate-600 mx-auto mb-2.5" />
                <p className="text-xs sm:text-sm font-semibold text-slate-300">No scheduled university interviews currently pending</p>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto leading-relaxed">
                  When department administrators assign an interview to your registration number, it will appear here. You can also self-enroll in mock interviews above.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {assignments.map((assign) => (
                  <div
                    key={assign.assignment_id}
                    className="group relative p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1120]/90 to-[#070c17]/90 border border-slate-800/80 hover:border-indigo-500/40 hover:bg-[#0e172e] hover:-translate-y-1 hover:shadow-[0_14px_30px_-6px_rgba(99,102,241,0.22),0_0_20px_-4px_rgba(6,182,212,0.15)] transition-all duration-300 ease-out flex flex-col md:flex-row md:items-center justify-between gap-4 overflow-hidden"
                  >
                    {/* Iridescent subtle ambient glow on hover */}
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-indigo-500/8 via-transparent to-cyan-500/8 pointer-events-none transition-opacity duration-300 opacity-0 group-hover:opacity-100" />
                    <div className="absolute -top-10 -right-10 w-28 h-28 rounded-full blur-xl pointer-events-none transition-opacity duration-300 opacity-0 group-hover:opacity-100 bg-indigo-500/10" />

                    <div className="space-y-2.5 max-w-2xl relative z-10">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <span className="font-bold text-white text-sm sm:text-base tracking-tight group-hover:text-cyan-100 transition-colors duration-200">
                          {assign.interview_title}
                        </span>
                        <span
                          className={`text-[10px] uppercase font-bold px-2.5 py-0.5 rounded-full border shadow-sm transition-all duration-200 ease-out select-none ${
                            assign.status === 'assigned'
                              ? 'bg-amber-950/60 text-amber-300 border-amber-800/60 shadow-[0_0_10px_rgba(245,158,11,0.15)] hover:bg-amber-900/60 hover:border-amber-500/70 hover:shadow-[0_0_14px_rgba(245,158,11,0.3)]'
                              : assign.status === 'accepted'
                              ? 'bg-teal-950/60 text-teal-300 border-teal-800/60 shadow-[0_0_10px_rgba(20,184,166,0.15)] hover:bg-teal-900/60 hover:border-teal-500/70 hover:shadow-[0_0_14px_rgba(20,184,166,0.3)]'
                              : assign.status === 'in_progress'
                              ? 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60 shadow-[0_0_10px_rgba(99,102,241,0.15)] hover:bg-indigo-900/60 hover:border-indigo-500/70 hover:text-indigo-200 hover:shadow-[0_0_14px_rgba(99,102,241,0.3)]'
                              : assign.status === 'completed'
                              ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60 shadow-[0_0_10px_rgba(16,185,129,0.15)] hover:bg-emerald-900/60 hover:border-emerald-500/70 hover:text-emerald-300 hover:shadow-[0_0_14px_rgba(16,185,129,0.3)]'
                              : 'bg-rose-950/60 text-rose-400 border-rose-800/60'
                          }`}
                        >
                          {assign.status === 'assigned' ? 'Action Required: Pending Acceptance' : assign.status}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-3.5 text-xs text-slate-400">
                        <span className="flex items-center space-x-1.5 group-hover:text-slate-300 transition-colors">
                          <Calendar className="w-3.5 h-3.5 text-indigo-400" />
                          <span>{new Date(assign.scheduled_start_time).toLocaleString()}</span>
                        </span>
                        <span className="flex items-center space-x-1.5 group-hover:text-slate-300 transition-colors">
                          <Clock className="w-3.5 h-3.5 text-violet-400" />
                          <span>Duration: {assign.duration_minutes} mins</span>
                        </span>
                        <span className="text-slate-400">
                          Section: <strong className="text-white font-medium">{assign.section || 'General'}</strong>
                        </span>
                      </div>

                      {assign.interview_instructions && (
                        <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/60 text-xs text-slate-300 font-mono mt-1 whitespace-pre-line line-clamp-2 group-hover:border-slate-700/80 transition-colors">
                          {assign.interview_instructions}
                        </div>
                      )}
                    </div>

                    {/* Student Action Buttons */}
                    <div className="flex items-center space-x-2 self-end md:self-center shrink-0 relative z-10">
                      {assign.status === 'assigned' && (
                        <button
                          onClick={() => handleAcceptAssignment(assign.assignment_id)}
                          disabled={actionLoadingId === assign.assignment_id}
                          className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 hover:brightness-110 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 hover:shadow-[0_0_20px_rgba(99,102,241,0.4)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] transition-all duration-200 ease-out flex items-center space-x-1.5 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a1120]"
                        >
                          {actionLoadingId === assign.assignment_id ? (
                            <Loader2 className="w-4 h-4 animate-spin text-white" />
                          ) : (
                            <Check className="w-4 h-4" />
                          )}
                          <span>Accept Assignment</span>
                        </button>
                      )}

                      {assign.status === 'accepted' && (
                        <button
                          onClick={() => navigate(`/interview/${assign.assignment_id}`)}
                          className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 hover:brightness-110 text-white text-xs font-semibold shadow-lg shadow-emerald-600/30 hover:shadow-[0_0_20px_rgba(16,185,129,0.4)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] transition-all duration-200 ease-out flex items-center space-x-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a1120]"
                        >
                          <Play className="w-4 h-4 fill-white" />
                          <span>Enter Interview Room</span>
                        </button>
                      )}

                      {assign.status === 'in_progress' && (
                        <button
                          onClick={() => navigate(`/interview/${assign.assignment_id}`)}
                          className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 hover:brightness-110 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 hover:shadow-[0_0_22px_rgba(139,92,246,0.45)] hover:-translate-y-0.5 active:translate-y-0 active:brightness-90 active:scale-[0.98] transition-all duration-200 ease-out flex items-center space-x-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a1120]"
                        >
                          <Play className="w-4 h-4 fill-white" />
                          <span>Resume Interview</span>
                        </button>
                      )}

                      {assign.status === 'completed' && (
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={() => navigate(`/report/${assign.assignment_id}`)}
                            className="px-4 py-2.5 rounded-xl bg-indigo-600/90 hover:bg-indigo-500 text-white border border-indigo-400/50 hover:shadow-[0_0_18px_rgba(99,102,241,0.35)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] text-xs font-semibold transition-all duration-200 ease-out flex items-center space-x-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a1120]"
                          >
                            <FileText className="w-4 h-4 text-cyan-300" />
                            <span>Performance Report</span>
                          </button>
                          <button
                            onClick={() => navigate(`/interview/${assign.assignment_id}`)}
                            className="px-3.5 py-2.5 rounded-xl bg-slate-800/90 hover:bg-slate-750 text-indigo-300 hover:text-white border border-indigo-500/40 hover:border-indigo-400/80 hover:shadow-[0_0_18px_rgba(139,92,246,0.25)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] text-xs font-semibold transition-all duration-200 ease-out flex items-center space-x-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a1120]"
                            title="Review interview room scorecard"
                          >
                            <Award className="w-4 h-4 text-amber-400" />
                            <span>Scorecard</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* User Profile Specifications & Dev Probes */}
        <div className={`grid grid-cols-1 ${import.meta.env.DEV ? 'lg:grid-cols-3' : 'max-w-2xl'} gap-6 mb-8`}>
          {/* User Metadata Card */}
          <div className="group p-6 sm:p-7 rounded-3xl bg-gradient-to-br from-[#091122]/90 via-[#080e1b]/90 to-[#060a14]/90 border border-slate-800/80 hover:border-cyan-500/40 hover:bg-[#0c152a] hover:shadow-[0_12px_28px_-6px_rgba(6,182,212,0.18)] transition-all duration-300 ease-out flex flex-col justify-between shadow-2xl relative overflow-hidden">
            {/* Soft restrained cyan glow */}
            <div className="absolute -top-16 -right-16 w-40 h-40 bg-cyan-500/5 group-hover:bg-cyan-500/12 rounded-full blur-2xl pointer-events-none transition-colors duration-300" />
            <div className="absolute inset-0 rounded-3xl bg-gradient-to-br from-cyan-500/5 via-transparent to-indigo-500/5 pointer-events-none transition-opacity duration-300 opacity-0 group-hover:opacity-100" />

            <div className="relative z-10">
              <h3 className="text-sm font-bold text-white mb-4 flex items-center space-x-2">
                <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 group-hover:border-cyan-500/40 group-hover:scale-105 transition-all duration-200">
                  <User className="w-4 h-4 text-cyan-400" />
                </div>
                <span className="group-hover:text-cyan-100 transition-colors duration-200">Student Identity & Verification</span>
              </h3>

              <div className="space-y-1.5 text-xs">
                <div className="p-2 -mx-2 rounded-xl hover:bg-slate-800/40 transition-colors duration-150">
                  <span className="text-slate-400 block mb-0.5">Assigned Email</span>
                  <span className="font-mono text-slate-200">{user?.email}</span>
                </div>
                {user?.registration_number && (
                  <div className="p-2 -mx-2 rounded-xl hover:bg-slate-800/40 transition-colors duration-150">
                    <span className="text-slate-400 block mb-0.5">Registration Number</span>
                    <span className="font-mono text-cyan-300 font-bold">{user?.registration_number}</span>
                  </div>
                )}
                <div className="p-2 -mx-2 rounded-xl hover:bg-slate-800/40 transition-colors duration-150">
                  <span className="text-slate-400 block mb-0.5">Role Permission Level</span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 uppercase">
                    {user?.role}
                  </span>
                </div>
                <div className="p-2 -mx-2 rounded-xl hover:bg-slate-800/40 transition-colors duration-150">
                  <span className="text-slate-400 block mb-0.5">Institution</span>
                  <span className="text-slate-200 font-medium">
                    {institutionLabel}
                  </span>
                </div>
                {user?.department && (
                  <div className="p-2 -mx-2 rounded-xl hover:bg-slate-800/40 transition-colors duration-150">
                    <span className="text-slate-400 block mb-0.5">Department / Stream</span>
                    <span className="font-mono text-slate-200">{user?.department}</span>
                  </div>
                )}
                <div className="p-2 -mx-2 rounded-xl hover:bg-slate-800/40 transition-colors duration-150">
                  <span className="text-slate-400 block mb-0.5">Account Status</span>
                  <span className="text-emerald-400 font-semibold capitalize flex items-center space-x-1">
                    <CheckCircle2 className="w-3.5 h-3.5 inline" />
                    <span>{user?.account_status || 'Verified Active'}</span>
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between relative z-10">
              <span>Bearer Session Validated</span>
              <span className="text-cyan-400 font-mono text-[10px]">ECDSA / HS256</span>
            </div>
          </div>

          {/* Interactive Server Authorization Probes Card - Development Only */}
          {import.meta.env.DEV && (
            <div className="lg:col-span-2 p-6 sm:p-7 rounded-3xl bg-gradient-to-br from-[#091122]/90 via-[#080e1b]/90 to-[#060a14]/90 border border-slate-800/80 shadow-2xl relative overflow-hidden">
              <h3 className="text-sm font-bold text-white mb-2 flex items-center space-x-2">
                <Shield className="w-4 h-4 text-indigo-400" />
                <span>Live Server-Side Authorization Verification (Dev Diagnostics)</span>
              </h3>
              <p className="text-xs text-slate-400 mb-5 leading-relaxed">
                Verify that the backend FastAPI dependencies enforce role-based authorization on the server. Non-admin users are strictly rejected with <strong>403 Forbidden</strong>.
              </p>

              <div className="flex flex-wrap gap-3 mb-5">
                <button
                  id="test-protected-btn"
                  onClick={handleTestProtected}
                  disabled={testLoading}
                  className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 hover:shadow-lg hover:shadow-indigo-600/30 text-white transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] flex items-center space-x-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  <Activity className="w-3.5 h-3.5" />
                  <span>Probe /api/auth/protected-test (Any Role)</span>
                </button>

                <button
                  id="test-admin-only-btn"
                  onClick={handleTestAdminOnly}
                  disabled={testLoading}
                  className="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700 hover:border-slate-600 transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] flex items-center space-x-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                >
                  <Lock className="w-3.5 h-3.5 text-amber-400" />
                  <span>Probe /api/auth/admin-only (Admin Restricted)</span>
                </button>
              </div>

              {/* Probe Output Box */}
              <div className="rounded-xl bg-slate-950/80 border border-slate-800 p-4">
                <div className="flex items-center justify-between text-xs text-slate-400 font-mono mb-2 pb-2 border-b border-slate-800/80">
                  <span className="flex items-center space-x-2">
                    <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                    <span>{testResult?.endpoint || 'Diagnostics Terminal'}</span>
                  </span>
                  {testResult && (
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${
                      testResult.status === 200 ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                    }`}>
                      HTTP {testResult.status} {testResult.status === 200 ? 'OK' : testResult.status === 403 ? 'FORBIDDEN' : 'DENIED'}
                    </span>
                  )}
                </div>
                <pre className="text-xs font-mono text-indigo-300 overflow-x-auto p-2 bg-slate-900/50 rounded-lg">
                  {testLoading
                    ? '/* Querying backend endpoint with Bearer token... */'
                    : testResult
                      ? JSON.stringify(testResult.data, null, 2)
                      : '/* Click a probe button above to test authentication and role permissions */'
                  }
                </pre>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
