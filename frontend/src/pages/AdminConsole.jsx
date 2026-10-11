import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  getAdminOnlyTest,
  getAdminInterviews,
  createAdminInterview,
  updateAdminInterview,
  searchEligibleCandidates,
  assignCandidatesToInterview,
} from '../api/client';
import { 
  ShieldCheck, 
  Terminal, 
  ArrowLeft, 
  CheckCircle2, 
  LogOut, 
  Building, 
  Layers,
  Key,
  Plus,
  Calendar,
  Clock,
  Users,
  Search,
  Filter,
  AlertCircle,
  X,
  Check,
  ChevronRight,
  RefreshCw,
  Ban,
  Eye,
} from 'lucide-react';
import ProctoringTimelineModal from '../components/ProctoringTimelineModal';

export default function AdminConsole() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [adminTelemetry, setAdminTelemetry] = useState(null);
  const [loading, setLoading] = useState(true);

  // Interviews state
  const [interviews, setInterviews] = useState([]);
  const [interviewsLoading, setInterviewsLoading] = useState(false);
  const [selectedInterview, setSelectedInterview] = useState(null);

  // Create Interview Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: '',
    description: '',
    instructions: '1. Ensure stable internet connection and webcam active.\n2. Audio and screen sharing must remain enabled.\n3. Keep university identity card ready for verification.',
    scheduled_start_time: '',
    scheduled_end_time: '',
    duration_minutes: 45,
    target_cohort: '2024-2028',
    target_department: 'CSE',
  });
  const [createError, setCreateError] = useState(null);
  const [createSubmitting, setCreateSubmitting] = useState(false);

  // Candidate Assignment Modal State
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignInterview, setAssignInterview] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [selectedSection, setSelectedSection] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRegs, setSelectedRegs] = useState([]);
  const [assignSubmitting, setAssignSubmitting] = useState(false);
  const [assignResult, setAssignResult] = useState(null);

  // Proctoring Timeline Modal State
  const [selectedTimelineSessionId, setSelectedTimelineSessionId] = useState(null);
  const [lookupSessionIdInput, setLookupSessionIdInput] = useState('');

  // Initialize
  useEffect(() => {
    const fetchAdminData = async () => {
      setLoading(true);
      const res = await getAdminOnlyTest();
      if (res.success) {
        setAdminTelemetry(res.data);
      }
      setLoading(false);
    };
    fetchAdminData();
  }, []);

  const fetchInterviews = useCallback(async () => {
    setInterviewsLoading(true);
    const res = await getAdminInterviews();
    if (res.success) {
      setInterviews(res.data);
    }
    setInterviewsLoading(false);
  }, []);

  useEffect(() => {
    fetchInterviews();
  }, [fetchInterviews]);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  // Handle Create Interview
  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    setCreateError(null);
    setCreateSubmitting(true);

    if (!createForm.scheduled_start_time || !createForm.scheduled_end_time) {
      setCreateError('Please specify start and end dates/times.');
      setCreateSubmitting(false);
      return;
    }

    const payload = {
      ...createForm,
      scheduled_start_time: new Date(createForm.scheduled_start_time).toISOString(),
      scheduled_end_time: new Date(createForm.scheduled_end_time).toISOString(),
      duration_minutes: Number(createForm.duration_minutes),
    };

    const res = await createAdminInterview(payload);
    if (res.success) {
      setShowCreateModal(false);
      setCreateForm({
        title: '',
        description: '',
        instructions: '1. Ensure stable internet connection and webcam active.\n2. Audio and screen sharing must remain enabled.\n3. Keep university identity card ready for verification.',
        scheduled_start_time: '',
        scheduled_end_time: '',
        duration_minutes: 45,
        target_cohort: '2024-2028',
        target_department: 'CSE',
      });
      fetchInterviews();
    } else {
      setCreateError(res.error || 'Failed to create interview');
    }
    setCreateSubmitting(false);
  };

  // Open Candidate Assign Modal
  const openAssignModal = async (interview) => {
    setAssignInterview(interview);
    setShowAssignModal(true);
    setSelectedRegs([]);
    setAssignResult(null);
    loadCandidates(interview.interview_id, selectedSection, searchQuery);
  };

  const loadCandidates = async (intId, sec, search) => {
    setCandidatesLoading(true);
    const res = await searchEligibleCandidates({
      interviewId: intId,
      section: sec,
      search: search,
      limit: 200,
    });
    if (res.success) {
      setCandidates(res.data);
    }
    setCandidatesLoading(false);
  };

  const handleSectionFilterChange = (sec) => {
    setSelectedSection(sec);
    if (assignInterview) {
      loadCandidates(assignInterview.interview_id, sec, searchQuery);
    }
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (assignInterview) {
      loadCandidates(assignInterview.interview_id, selectedSection, searchQuery);
    }
  };

  const toggleSelectReg = (reg) => {
    if (selectedRegs.includes(reg)) {
      setSelectedRegs(selectedRegs.filter((r) => r !== reg));
    } else {
      setSelectedRegs([...selectedRegs, reg]);
    }
  };

  const handleSelectAllVisible = () => {
    const assignableRegs = candidates.filter((c) => !c.already_assigned).map((c) => c.registration_number);
    setSelectedRegs(Array.from(new Set([...selectedRegs, ...assignableRegs])));
  };

  const handleDeselectAll = () => {
    setSelectedRegs([]);
  };

  const handleExecuteAssignment = async () => {
    if (!assignInterview || selectedRegs.length === 0) return;
    setAssignSubmitting(true);
    setAssignResult(null);

    const res = await assignCandidatesToInterview(assignInterview.interview_id, selectedRegs);
    if (res.success) {
      setAssignResult(res.data);
      // Reload candidates and parent interviews list
      loadCandidates(assignInterview.interview_id, selectedSection, searchQuery);
      fetchInterviews();
      setSelectedRegs([]);
    } else {
      setAssignResult({ error: res.error });
    }
    setAssignSubmitting(false);
  };

  const handleCancelInterview = async (interviewId) => {
    if (!window.confirm('Are you sure you want to cancel this interview? All active assignments will be cancelled.')) return;
    const res = await updateAdminInterview(interviewId, { status: 'cancelled' });
    if (res.success) {
      fetchInterviews();
    }
  };

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col selection:bg-indigo-500/30">
      {/* Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-xl sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Link to="/dashboard" className="text-slate-400 hover:text-white transition mr-2">
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <span className="font-bold text-sm text-white">VFSTR Administrator Suite</span>
                <span className="ml-2 text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                  {user?.role}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <Link
              to="/dashboard"
              className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            >
              My Workspace
            </Link>
            <button
              onClick={handleLogout}
              className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition flex items-center space-x-1.5"
            >
              <LogOut className="w-3.5 h-3.5 text-slate-400" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 w-full flex-1">
        {/* Banner */}
        <div className="p-6 rounded-2xl glass-panel border border-slate-800 mb-8">
          <div className="flex items-center space-x-3 mb-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 flex items-center space-x-1.5">
              <Key className="w-3 h-3 text-indigo-400" />
              <span>Central Authority Verified</span>
            </span>
            <span className="text-xs text-slate-400">•</span>
            <span className="text-xs text-slate-300">{user?.institution_id} Adaptive Platform</span>
          </div>
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white">
                University Interview Administration
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                Schedule university-wide interviews, inspect approved student candidates, and manage assignments in <code className="text-indigo-300 bg-slate-900 px-1 py-0.5 rounded">interview_db</code>.
              </p>
            </div>
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-medium text-xs sm:text-sm flex items-center space-x-2 shadow-lg shadow-indigo-600/20 transition"
            >
              <Plus className="w-4 h-4" />
              <span>Schedule New Interview</span>
            </button>
          </div>
        </div>

        {/* Interviews List Section */}
        <div className="p-6 rounded-2xl glass-panel border border-slate-800 mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Calendar className="w-5 h-5 text-indigo-400" />
              <h2 className="text-base font-bold text-white">Scheduled University Interviews</h2>
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                {interviews.length}
              </span>
            </div>
            <button
              onClick={fetchInterviews}
              disabled={interviewsLoading}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
              title="Refresh interviews"
            >
              <RefreshCw className={`w-4 h-4 ${interviewsLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {interviewsLoading && interviews.length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-sm">
              Loading scheduled interviews from Atlas...
            </div>
          ) : interviews.length === 0 ? (
            <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
              <Calendar className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <p className="text-sm text-slate-300 font-medium">No university interviews scheduled yet</p>
              <p className="text-xs text-slate-500 mt-1 mb-4">Create your first interview to begin assigning students from the registry.</p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="px-3.5 py-2 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/40 text-indigo-300 text-xs font-medium border border-indigo-500/30 transition"
              >
                Schedule an Interview
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {interviews.map((item) => (
                <div
                  key={item.interview_id}
                  className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-1.5 max-w-2xl">
                    <div className="flex items-center space-x-2.5">
                      <span className="font-semibold text-white text-base">{item.title}</span>
                      <span
                        className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
                          item.status === 'scheduled'
                            ? 'bg-blue-950/60 text-blue-400 border-blue-800/50'
                            : item.status === 'in_progress'
                            ? 'bg-indigo-950/60 text-indigo-400 border-indigo-800/50'
                            : item.status === 'completed'
                            ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/50'
                            : 'bg-rose-950/60 text-rose-400 border-rose-800/50'
                        }`}
                      >
                        {item.status}
                      </span>
                      <span className="text-[11px] font-mono text-slate-400">
                        {item.target_department} • {item.target_cohort}
                      </span>
                    </div>

                    {item.description && (
                      <p className="text-xs text-slate-400 line-clamp-1">{item.description}</p>
                    )}

                    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 pt-1">
                      <span className="flex items-center space-x-1">
                        <Calendar className="w-3.5 h-3.5 text-indigo-400" />
                        <span>{new Date(item.scheduled_start_time).toLocaleString()}</span>
                      </span>
                      <span className="flex items-center space-x-1">
                        <Clock className="w-3.5 h-3.5 text-violet-400" />
                        <span>Duration: {item.duration_minutes} mins</span>
                      </span>
                      <span className="flex items-center space-x-1 text-slate-300 font-medium">
                        <Users className="w-3.5 h-3.5 text-emerald-400" />
                        <span>{item.total_assignments_count} Assigned</span>
                      </span>
                    </div>

                    {/* Breakdown pill */}
                    {item.total_assignments_count > 0 && (
                      <div className="flex items-center gap-2 pt-1 text-[11px]">
                        {Object.entries(item.status_counts || {}).map(([st, cnt]) => (
                          <span
                            key={st}
                            className="px-2 py-0.5 rounded bg-slate-950/60 border border-slate-800 text-slate-300"
                          >
                            {st}: <strong className="text-white">{cnt}</strong>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 self-end md:self-center">
                    {item.status === 'scheduled' && (
                      <>
                        <button
                          onClick={() => openAssignModal(item)}
                          className="px-3.5 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 text-xs font-medium transition flex items-center space-x-1"
                        >
                          <Users className="w-3.5 h-3.5" />
                          <span>Assign Students</span>
                        </button>
                        <button
                          onClick={() => handleCancelInterview(item.interview_id)}
                          className="px-2.5 py-1.5 rounded-lg bg-rose-950/30 hover:bg-rose-950/50 text-rose-300 border border-rose-800/40 text-xs transition"
                          title="Cancel Interview"
                        >
                          <Ban className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* RBAC Telemetry Details Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="p-5 rounded-2xl glass-panel border border-slate-800">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center mb-3">
              <Building className="w-4 h-4" />
            </div>
            <h4 className="text-sm font-semibold text-white mb-1">Target Institution</h4>
            <div className="text-xs font-mono text-indigo-300 mb-1">{user?.institution_id}</div>
            <p className="text-xs text-slate-400">
              Vignan's Foundation for Science, Technology & Research (Vadlamudi, Guntur)
            </p>
          </div>

          <div className="p-5 rounded-2xl glass-panel border border-slate-800">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mb-3">
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <h4 className="text-sm font-semibold text-white mb-1">Server Authorization</h4>
            <div className="text-xs font-mono text-emerald-400 mb-1">200 OK Authorized</div>
            <p className="text-xs text-slate-400">
              Verified via <code className="bg-slate-900 px-1 py-0.5 rounded text-[11px]">GET /api/auth/admin-only</code> with JWT
            </p>
          </div>

          <div className="p-5 rounded-2xl glass-panel border border-slate-800">
            <div className="w-9 h-9 rounded-xl bg-violet-500/10 border border-violet-500/20 text-violet-400 flex items-center justify-center mb-3">
              <Layers className="w-4 h-4" />
            </div>
            <h4 className="text-sm font-semibold text-white mb-1">Database Model</h4>
            <div className="text-xs font-mono text-violet-300 mb-1">interview_db Isolated</div>
            <p className="text-xs text-slate-400">
              Interviews and assignments stored in dedicated Atlas database isolated from auth.
            </p>
          </div>
        </div>

        {/* Level 1 Proctoring & Session Integrity Inspector Card */}
        <div className="p-6 rounded-2xl glass-panel border border-slate-800 mb-8 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                <Eye className="w-4 h-4 text-indigo-400" />
                <span>Level 1 Proctoring & Integrity Telemetry Inspector</span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Inspect browser-side telemetry, tab switches, face presence, and stream interruptions for any candidate session.
              </p>
            </div>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 self-start sm:self-auto">
              Non-Disqualifying Signals
            </span>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (lookupSessionIdInput.trim()) {
                setSelectedTimelineSessionId(lookupSessionIdInput.trim());
              }
            }}
            className="flex flex-col sm:flex-row items-center gap-3"
          >
            <div className="relative flex-1 w-full">
              <input
                type="text"
                placeholder="Enter Session UUID (e.g., 550e8400-e29b-41d4-a716-446655440000)..."
                value={lookupSessionIdInput}
                onChange={(e) => setLookupSessionIdInput(e.target.value)}
                className="w-full rounded-xl bg-slate-950/80 border border-slate-800 focus:border-indigo-500 text-slate-100 placeholder-slate-600 text-xs font-mono px-3.5 py-2.5 transition"
              />
            </div>

            <button
              type="submit"
              disabled={!lookupSessionIdInput.trim()}
              className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs transition disabled:opacity-50 shrink-0 flex items-center space-x-1.5"
            >
              <Eye className="w-3.5 h-3.5" />
              <span>Inspect Telemetry</span>
            </button>
          </form>
        </div>

        {/* Server Response Card - Development Diagnostics */}
        {import.meta.env.DEV && (
          <div className="p-6 rounded-2xl glass-panel border border-slate-800 mb-8">
            <h3 className="text-sm font-bold text-white mb-2 flex items-center space-x-2">
              <Terminal className="w-4 h-4 text-indigo-400" />
              <span>Server-side Administrator Authorization Payload (Dev Diagnostics)</span>
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Response received from FastAPI protected route requiring administrator role credentials:
            </p>

            <pre className="text-xs font-mono text-indigo-300 p-4 bg-slate-950/90 rounded-xl border border-slate-800 overflow-x-auto">
              {loading ? '/* Fetching authorized telemetry... */' : JSON.stringify(adminTelemetry, null, 2)}
            </pre>
          </div>
        )}
      </main>

      {/* CREATE INTERVIEW MODAL */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl relative">
            <button
              onClick={() => setShowCreateModal(false)}
              className="absolute top-4 right-4 p-1.5 rounded-lg text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition"
            >
              <X className="w-4 h-4" />
            </button>

            <h3 className="text-lg font-bold text-white mb-1">Schedule University Interview</h3>
            <p className="text-xs text-slate-400 mb-4">
              Create an official interview session. Eligible students will be assigned from <code className="text-indigo-300">interview_db</code>.
            </p>

            {createError && (
              <div className="mb-4 p-3 rounded-lg bg-rose-950/60 border border-rose-800/50 text-rose-300 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Interview Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cisco NetAcad Networking Technical Round 1"
                  value={createForm.title}
                  onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Description (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Assessment on Routing, Switching, and IP addressing"
                  value={createForm.description}
                  onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Start Time (UTC/Local) *</label>
                  <input
                    type="datetime-local"
                    required
                    value={createForm.scheduled_start_time}
                    onChange={(e) => setCreateForm({ ...createForm, scheduled_start_time: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">End Time (UTC/Local) *</label>
                  <input
                    type="datetime-local"
                    required
                    value={createForm.scheduled_end_time}
                    onChange={(e) => setCreateForm({ ...createForm, scheduled_end_time: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Duration (Mins) *</label>
                  <input
                    type="number"
                    min="10"
                    max="360"
                    required
                    value={createForm.duration_minutes}
                    onChange={(e) => setCreateForm({ ...createForm, duration_minutes: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Department</label>
                  <input
                    type="text"
                    value={createForm.target_department}
                    onChange={(e) => setCreateForm({ ...createForm, target_department: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Batch Cohort</label>
                  <input
                    type="text"
                    value={createForm.target_cohort}
                    onChange={(e) => setCreateForm({ ...createForm, target_cohort: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Interview Instructions *</label>
                <textarea
                  rows={3}
                  required
                  value={createForm.instructions}
                  onChange={(e) => setCreateForm({ ...createForm, instructions: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition flex items-center space-x-2"
                >
                  {createSubmitting ? 'Creating...' : 'Create Interview'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CANDIDATE ASSIGNMENT MODAL */}
      {showAssignModal && assignInterview && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-4xl w-full p-6 shadow-2xl relative max-h-[90vh] flex flex-col">
            <button
              onClick={() => setShowAssignModal(false)}
              className="absolute top-4 right-4 p-1.5 rounded-lg text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="mb-4">
              <h3 className="text-lg font-bold text-white">Assign Eligible Candidates</h3>
              <p className="text-xs text-slate-400">
                Target Interview: <strong className="text-indigo-300">{assignInterview.title}</strong>
              </p>
            </div>

            {/* Filter Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-slate-950/80 border border-slate-800 mb-4">
              <div className="flex items-center space-x-2">
                <Filter className="w-4 h-4 text-indigo-400" />
                <span className="text-xs text-slate-300">Section:</span>
                <select
                  value={selectedSection}
                  onChange={(e) => handleSectionFilterChange(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none"
                >
                  <option value="ALL">All Sections (1 - 22)</option>
                  {Array.from({ length: 22 }, (_, i) => String(i + 1)).map((sec) => (
                    <option key={sec} value={sec}>
                      Section {sec}
                    </option>
                  ))}
                </select>
              </div>

              <form onSubmit={handleSearchSubmit} className="flex items-center space-x-2 flex-1 max-w-xs">
                <input
                  type="text"
                  placeholder="Search Roll No / Email..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none"
                />
                <button
                  type="submit"
                  className="p-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition"
                >
                  <Search className="w-3.5 h-3.5" />
                </button>
              </form>

              <div className="flex items-center space-x-2">
                <button
                  onClick={handleSelectAllVisible}
                  className="text-xs px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
                >
                  Select All
                </button>
                <button
                  onClick={handleDeselectAll}
                  className="text-xs px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400"
                >
                  Deselect
                </button>
              </div>
            </div>

            {/* Results feedback banner */}
            {assignResult && (
              <div
                className={`mb-4 p-3 rounded-xl border text-xs ${
                  assignResult.assigned_count > 0
                    ? 'bg-emerald-950/60 border-emerald-800/50 text-emerald-300'
                    : 'bg-rose-950/60 border-rose-800/50 text-rose-300'
                }`}
              >
                {assignResult.error ? (
                  <div>{assignResult.error}</div>
                ) : (
                  <div>
                    <strong>Assignment Result:</strong> Successfully assigned {assignResult.assigned_count} students. (Failed / Skipped: {assignResult.failed_count})
                  </div>
                )}
              </div>
            )}

            {/* Candidates Table */}
            <div className="flex-1 overflow-y-auto border border-slate-800 rounded-xl mb-4">
              {candidatesLoading ? (
                <div className="text-center py-12 text-slate-400 text-sm">Loading eligible candidates...</div>
              ) : candidates.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-sm">No eligible candidates match this filter.</div>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 sticky top-0 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3 w-10"></th>
                      <th className="p-3">S.No</th>
                      <th className="p-3">Reg. Number</th>
                      <th className="p-3">Student Email</th>
                      <th className="p-3">Sec</th>
                      <th className="p-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {candidates.map((c) => {
                      const isSelected = selectedRegs.includes(c.registration_number);
                      return (
                        <tr
                          key={c.registration_number}
                          className={`hover:bg-slate-800/40 transition ${c.already_assigned ? 'opacity-60 bg-slate-950/40' : ''}`}
                        >
                          <td className="p-3">
                            <input
                              type="checkbox"
                              disabled={c.already_assigned}
                              checked={isSelected}
                              onChange={() => toggleSelectReg(c.registration_number)}
                              className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
                            />
                          </td>
                          <td className="p-3 font-mono text-slate-400">{c.s_no}</td>
                          <td className="p-3 font-mono font-medium text-white">{c.registration_number}</td>
                          <td className="p-3 text-slate-300">{c.email}</td>
                          <td className="p-3 text-slate-400">{c.section}</td>
                          <td className="p-3">
                            {c.already_assigned ? (
                              <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
                                Assigned
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800/50">
                                Approved Eligible
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between pt-2 border-t border-slate-800">
              <span className="text-xs text-slate-400">
                Selected: <strong className="text-white">{selectedRegs.length}</strong> candidate(s)
              </span>

              <div className="flex items-center space-x-3">
                <button
                  onClick={() => setShowAssignModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
                >
                  Close
                </button>
                <button
                  onClick={handleExecuteAssignment}
                  disabled={assignSubmitting || selectedRegs.length === 0}
                  className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-medium transition flex items-center space-x-2"
                >
                  {assignSubmitting ? 'Assigning...' : `Assign Selected (${selectedRegs.length})`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Proctoring Timeline Inspector Modal */}
      {selectedTimelineSessionId && (
        <ProctoringTimelineModal
          sessionId={selectedTimelineSessionId}
          onClose={() => setSelectedTimelineSessionId(null)}
        />
      )}
    </div>
  );
}
