import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  getProtectedTest, 
  getAdminOnlyTest,
  getStudentAssignments,
  acceptStudentAssignment,
  startStudentInterview,
  completeStudentInterview
} from '../api/client';
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
  CheckCheck,
  AlertCircle,
  RefreshCw,
  FileText,
  Award
} from 'lucide-react';

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

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col selection:bg-indigo-500/30">
      {/* Top Bar */}
      <header className="border-b border-slate-800/70 bg-slate-900/40 backdrop-blur-xl sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Link to="/" className="flex items-center space-x-2">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div>
                <span className="font-bold text-white text-sm">Adaptive Interview Intelligence</span>
                <span className="ml-2 text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  VFSTR
                </span>
              </div>
            </Link>
          </div>

          <div className="flex items-center space-x-3">
            {hasRole(['platform_admin', 'university_admin', 'department_admin']) && (
              <Link
                to="/admin"
                className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600/20 text-indigo-300 hover:bg-indigo-600/30 border border-indigo-500/30 font-medium transition flex items-center space-x-1"
              >
                <Shield className="w-3.5 h-3.5" />
                <span>Admin Console</span>
              </Link>
            )}

            <button
              id="logout-button"
              onClick={handleLogout}
              className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition flex items-center space-x-1.5"
            >
              <LogOut className="w-3.5 h-3.5 text-slate-400" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 w-full flex-1">
        {/* Welcome Banner */}
        <div className="mb-8 p-6 rounded-2xl glass-panel border border-slate-800 relative overflow-hidden">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center space-x-2 mb-2">
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center space-x-1">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Authenticated Session Active</span>
                </span>
                <span className="text-xs text-slate-400">•</span>
                <span className="text-xs text-slate-300">Institution: <strong className="text-white">{user?.institution_id}</strong></span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white">
                Welcome, {user?.full_name || user?.email}
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                Your authenticated profile and server-enforced role credentials are verified.
              </p>
            </div>

            <div className="flex items-center space-x-2">
              <span className="px-3.5 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-xs font-mono text-indigo-300 font-semibold uppercase tracking-wider">
                Role: {user?.role}
              </span>
            </div>
          </div>
        </div>

        {/* STUDENT ASSIGNED INTERVIEWS SECTION */}
        {user?.role === 'student' && (
          <div className="mb-8 p-6 rounded-2xl glass-panel border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-2.5">
                <Calendar className="w-5 h-5 text-indigo-400" />
                <h2 className="text-base font-bold text-white">My University-Assigned Interviews</h2>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  {assignments.length}
                </span>
              </div>
              <button
                onClick={fetchStudentAssignments}
                disabled={assignmentsLoading}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
                title="Refresh my assignments"
              >
                <RefreshCw className={`w-4 h-4 ${assignmentsLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {assignmentError && (
              <div className="mb-4 p-3 rounded-lg bg-rose-950/60 border border-rose-800/50 text-rose-300 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{assignmentError}</span>
              </div>
            )}

            {assignmentsLoading && assignments.length === 0 ? (
              <div className="text-center py-10 text-slate-400 text-xs">Loading assigned interviews...</div>
            ) : assignments.length === 0 ? (
              <div className="text-center py-10 border border-dashed border-slate-800/80 rounded-xl">
                <Calendar className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-xs font-medium text-slate-300">No interviews currently assigned</p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  When university administrators assign an interview to your registration number, it will appear here.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {assignments.map((assign) => (
                  <div
                    key={assign.assignment_id}
                    className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition flex flex-col md:flex-row md:items-center justify-between gap-4"
                  >
                    <div className="space-y-1.5 max-w-2xl">
                      <div className="flex items-center space-x-2.5">
                        <span className="font-semibold text-white text-base">{assign.interview_title}</span>
                        <span
                          className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
                            assign.status === 'assigned'
                              ? 'bg-amber-950/60 text-amber-300 border-amber-800/50'
                              : assign.status === 'accepted'
                              ? 'bg-blue-950/60 text-blue-300 border-blue-800/50'
                              : assign.status === 'in_progress'
                              ? 'bg-indigo-950/60 text-indigo-300 border-indigo-800/50'
                              : assign.status === 'completed'
                              ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/50'
                              : 'bg-rose-950/60 text-rose-400 border-rose-800/50'
                          }`}
                        >
                          {assign.status === 'assigned' ? 'Action Required: Pending Acceptance' : assign.status}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
                        <span className="flex items-center space-x-1">
                          <Calendar className="w-3.5 h-3.5 text-indigo-400" />
                          <span>{new Date(assign.scheduled_start_time).toLocaleString()}</span>
                        </span>
                        <span className="flex items-center space-x-1">
                          <Clock className="w-3.5 h-3.5 text-violet-400" />
                          <span>Duration: {assign.duration_minutes} mins</span>
                        </span>
                        <span className="text-slate-400">
                          Section: <strong className="text-white">{assign.section || 'General'}</strong>
                        </span>
                      </div>

                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 text-xs text-slate-300 font-mono mt-2 whitespace-pre-line">
                        {assign.interview_instructions}
                      </div>
                    </div>

                    {/* Student Action Buttons */}
                    <div className="flex items-center space-x-2 self-end md:self-center">
                      {assign.status === 'assigned' && (
                        <button
                          onClick={() => handleAcceptAssignment(assign.assignment_id)}
                          disabled={actionLoadingId === assign.assignment_id}
                          className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition flex items-center space-x-1.5"
                        >
                          <Check className="w-4 h-4" />
                          <span>Accept Assignment</span>
                        </button>
                      )}

                      {assign.status === 'accepted' && (
                        <button
                          onClick={() => navigate(`/interview/${assign.assignment_id}`)}
                          className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 transition flex items-center space-x-1.5"
                        >
                          <Play className="w-4 h-4" />
                          <span>Enter Interview Room</span>
                        </button>
                      )}

                      {assign.status === 'in_progress' && (
                        <button
                          onClick={() => navigate(`/interview/${assign.assignment_id}`)}
                          className="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition flex items-center space-x-1.5"
                        >
                          <Play className="w-4 h-4" />
                          <span>Resume Interview</span>
                        </button>
                      )}

                      {assign.status === 'completed' && (
                        <button
                          onClick={() => navigate(`/interview/${assign.assignment_id}`)}
                          className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-indigo-300 hover:text-white border border-indigo-500/30 text-xs font-semibold transition flex items-center space-x-1.5"
                        >
                          <Award className="w-4 h-4 text-amber-400" />
                          <span>View Scorecard</span>
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* User Profile & Security Diagnostics Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* User Metadata Card */}
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-bold text-white mb-4 flex items-center space-x-2">
                <User className="w-4 h-4 text-indigo-400" />
                <span>Account Specifications</span>
              </h3>

              <div className="space-y-3 text-xs">
                <div>
                  <span className="text-slate-400 block mb-0.5">Assigned Email</span>
                  <span className="font-mono text-slate-200">{user?.email}</span>
                </div>
                {user?.registration_number && (
                  <div>
                    <span className="text-slate-400 block mb-0.5">Registration Number</span>
                    <span className="font-mono text-indigo-300 font-semibold">{user?.registration_number}</span>
                  </div>
                )}
                <div>
                  <span className="text-slate-400 block mb-0.5">Unique User Identifier</span>
                  <span className="font-mono text-[11px] text-slate-300 truncate block bg-slate-900/60 p-1.5 rounded border border-slate-800">
                    {user?.id}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">Role Permission Level</span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 uppercase">
                    {user?.role}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">Institution Code</span>
                  <span className="text-slate-200">{user?.institution_id} (Vignan University)</span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">Status</span>
                  <span className="text-emerald-400 capitalize">{user?.account_status}</span>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-800/80 text-[11px] text-slate-400">
              JWT Bearer token loaded in active session
            </div>
          </div>

          {/* Interactive Server Authorization Probes Card */}
          <div className="lg:col-span-2 glass-panel p-6 rounded-2xl border border-slate-800">
            <h3 className="text-sm font-bold text-white mb-2 flex items-center space-x-2">
              <Shield className="w-4 h-4 text-indigo-400" />
              <span>Live Server-Side Authorization Verification</span>
            </h3>
            <p className="text-xs text-slate-400 mb-5 leading-relaxed">
              Verify that the backend FastAPI dependencies enforce role-based authorization on the server. Non-admin users are strictly rejected with <strong>403 Forbidden</strong>.
            </p>

            <div className="flex flex-wrap gap-3 mb-5">
              <button
                id="test-protected-btn"
                onClick={handleTestProtected}
                disabled={testLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center space-x-2"
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Probe /api/auth/protected-test (Any Role)</span>
              </button>

              <button
                id="test-admin-only-btn"
                onClick={handleTestAdminOnly}
                disabled={testLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700 transition flex items-center space-x-2"
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
        </div>

        {/* Phase Roadmap Notice */}
        <div className="p-6 rounded-2xl bg-indigo-950/30 border border-indigo-700/40 relative overflow-hidden">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start space-x-3.5">
              <div className="p-2.5 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-300">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-white">
                  University-Assigned Interviews Active
                </h4>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  Students can review their assigned university interviews, accept scheduling, and track their preparation status.
                </p>
              </div>
            </div>
            <Link
              to="/"
              className="text-xs font-semibold px-4 py-2 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-200 border border-indigo-500/30 transition shrink-0"
            >
              Back to Home
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
