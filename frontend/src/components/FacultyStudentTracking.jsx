import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Users,
  Search,
  Filter,
  RefreshCw,
  Loader2,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
  Clock,
  Award,
  Target,
  BrainCircuit,
  BookOpen,
  Calendar,
  X,
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Shield,
  GraduationCap,
} from 'lucide-react';
import {
  getAdminStudentTracking,
  getAdminStudentDetail,
} from '../api/client';

export default function FacultyStudentTracking({ user }) {
  const [students, setStudents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filter states
  const [search, setSearch] = useState('');
  const [selectedDept, setSelectedDept] = useState(
    user?.role === 'department_admin' || user?.role === 'faculty' ? user?.department || 'ALL' : 'ALL'
  );
  const [selectedRole, setSelectedRole] = useState('ALL');
  const [selectedLevel, setSelectedLevel] = useState('ALL');
  const [skip, setSkip] = useState(0);
  const limit = 15;

  // Detail Modal State
  const [selectedStudentReg, setSelectedStudentReg] = useState(null);
  const [studentDetail, setStudentDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  const fetchTrackingData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const res = await getAdminStudentTracking({
      department: selectedDept,
      role: selectedRole,
      recommended_level: selectedLevel,
      search: search,
      skip: skip,
      limit: limit,
    });

    if (res.success) {
      setStudents(res.data.items || []);
      setTotal(res.data.total || 0);
    } else {
      setError(res.error || 'Failed to load student tracking data');
    }
    setLoading(false);
  }, [selectedDept, selectedRole, selectedLevel, search, skip]);

  useEffect(() => {
    fetchTrackingData();
  }, [fetchTrackingData]);

  const handleOpenStudentDetail = async (regNo) => {
    setSelectedStudentReg(regNo);
    setDetailLoading(true);
    setDetailError(null);
    setStudentDetail(null);

    const res = await getAdminStudentDetail(regNo);
    if (res.success) {
      setStudentDetail(res.data);
    } else {
      setDetailError(res.error || 'Failed to load student progress detail');
    }
    setDetailLoading(false);
  };

  const getTrendBadge = (trend) => {
    switch (trend) {
      case 'improving':
        return (
          <span className="inline-flex items-center space-x-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-700/60">
            <TrendingUp className="w-3 h-3 text-emerald-400" />
            <span>Improving</span>
          </span>
        );
      case 'declining':
        return (
          <span className="inline-flex items-center space-x-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-rose-950/70 text-rose-300 border border-rose-700/60">
            <TrendingDown className="w-3 h-3 text-rose-400" />
            <span>Declining</span>
          </span>
        );
      case 'stable':
        return (
          <span className="inline-flex items-center space-x-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-cyan-950/70 text-cyan-300 border border-cyan-700/60">
            <Minus className="w-3 h-3 text-cyan-400" />
            <span>Stable</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
            <Clock className="w-3 h-3 text-slate-400" />
            <span>Baseline</span>
          </span>
        );
    }
  };

  const getLevelBadge = (level) => {
    switch (level) {
      case 'Advanced':
        return (
          <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-violet-950/80 text-violet-300 border border-violet-700/70 shadow-[0_0_12px_rgba(139,92,246,0.2)]">
            Advanced
          </span>
        );
      case 'Intermediate':
        return (
          <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-700/70 shadow-[0_0_12px_rgba(6,182,212,0.2)]">
            Intermediate
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/70 shadow-[0_0_12px_rgba(16,185,129,0.2)]">
            Beginner
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Filter Card */}
      <div className="p-5 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 shadow-lg space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-2">
            <Users className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold text-white">Student Performance & Recommendation Tracking</h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-mono">
              {total} Candidates
            </span>
          </div>
          <button
            onClick={() => fetchTrackingData()}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white border border-slate-700 transition self-start md:self-auto flex items-center space-x-2 text-xs"
            title="Refresh tracking data"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Filter controls */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-3 text-slate-400 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setSkip(0);
              }}
              placeholder="Search Reg No, Name, or Email..."
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400"
            />
          </div>

          {/* Department Filter (editable for platform/univ admins, read-only/fixed for dept admin & faculty) */}
          <div>
            <select
              value={selectedDept}
              disabled={user?.role === 'department_admin' || user?.role === 'faculty'}
              onChange={(e) => {
                setSelectedDept(e.target.value);
                setSkip(0);
              }}
              className="w-full px-3 py-2 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-400 disabled:opacity-60"
            >
              <option value="ALL">All Departments</option>
              <option value="CSE">CSE</option>
              <option value="ECE">ECE</option>
              <option value="IT">IT</option>
              <option value="EEE">EEE</option>
              <option value="MECH">MECH</option>
            </select>
          </div>

          {/* Role Filter */}
          <div>
            <select
              value={selectedRole}
              onChange={(e) => {
                setSelectedRole(e.target.value);
                setSkip(0);
              }}
              className="w-full px-3 py-2 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-400"
            >
              <option value="ALL">All Engineering Tracks</option>
              <option value="Associate Software Engineer">Associate Software Engineer</option>
              <option value="Software Development Engineer">Software Development Engineer</option>
              <option value="Product Engineer">Product Engineer</option>
              <option value="System Engineer">System Engineer</option>
              <option value="Testing Engineer">Testing Engineer</option>
            </select>
          </div>

          {/* Level Filter */}
          <div>
            <select
              value={selectedLevel}
              onChange={(e) => {
                setSelectedLevel(e.target.value);
                setSkip(0);
              }}
              className="w-full px-3 py-2 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-400"
            >
              <option value="ALL">All Recommended Levels</option>
              <option value="Beginner">Beginner Level</option>
              <option value="Intermediate">Intermediate Level</option>
              <option value="Advanced">Advanced Level</option>
            </select>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Students Table */}
      <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1120] to-[#070c17] border border-slate-800/80 shadow-xl overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-xs text-slate-400 flex flex-col items-center justify-center space-y-2">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
            <span>Querying verified candidate records and recommendations...</span>
          </div>
        ) : students.length === 0 ? (
          <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl p-6">
            <Users className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-xs sm:text-sm font-semibold text-slate-300">No student records match the active criteria</p>
            <p className="text-xs text-slate-500 mt-1">Try resetting the department, role, or recommended level filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-[11px] uppercase tracking-wider text-slate-400 bg-slate-900/60 border-b border-slate-800 font-mono">
                <tr>
                  <th className="py-3 px-4">Student</th>
                  <th className="py-3 px-4">Dept / Cohort</th>
                  <th className="py-3 px-4">Target Track</th>
                  <th className="py-3 px-4">Completed</th>
                  <th className="py-3 px-4">Latest / Avg</th>
                  <th className="py-3 px-4">Trend</th>
                  <th className="py-3 px-4">Recommended Level</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {students.map((st) => (
                  <tr key={st.registration_number} className="hover:bg-slate-800/30 transition">
                    <td className="py-3 px-4">
                      <div className="font-bold text-white">{st.full_name || st.registration_number}</div>
                      <div className="text-[11px] font-mono text-cyan-400">{st.registration_number}</div>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-400">
                      <div>{st.department || 'CSE'}</div>
                      <div className="text-[10px] text-slate-500">{st.batch_cohort || 'General'}</div>
                    </td>
                    <td className="py-3 px-4 text-slate-300">
                      {st.target_role || 'Associate Software Engineer'}
                    </td>
                    <td className="py-3 px-4 font-mono text-center">
                      <span className="px-2 py-0.5 rounded bg-slate-800 font-bold text-slate-200">
                        {st.completed_interviews_count}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono">
                      <div className="font-bold text-emerald-400">
                        {st.latest_score !== null && st.latest_score !== undefined ? `${st.latest_score} / 10` : '—'}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Avg: {st.average_score !== null && st.average_score !== undefined ? `${st.average_score}` : '—'}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      {getTrendBadge(st.trend)}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-col space-y-1">
                        <div>{getLevelBadge(st.recommended_level)}</div>
                        <span className="text-[10px] text-slate-500">
                          {st.recommendation_status === 'provisional' ? 'Provisional' : 'Evidence-supported'}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleOpenStudentDetail(st.registration_number)}
                        className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg bg-indigo-950/70 hover:bg-indigo-900/80 text-indigo-300 border border-indigo-800/60 text-xs font-semibold transition"
                      >
                        <span>Audit</span>
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination controls */}
        {total > limit && (
          <div className="flex items-center justify-between pt-4 mt-4 border-t border-slate-800 text-xs text-slate-400">
            <span>
              Showing {skip + 1} to {Math.min(skip + limit, total)} of {total} candidates
            </span>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setSkip((prev) => Math.max(0, prev - limit))}
                disabled={skip === 0}
                className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setSkip((prev) => prev + limit)}
                disabled={skip + limit >= total}
                className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* STUDENT DETAIL AUDIT MODAL */}
      {selectedStudentReg && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[#0b1222] border border-slate-700 rounded-3xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6 sm:p-8 shadow-2xl space-y-6 text-slate-200 relative">
            <button
              onClick={() => setSelectedStudentReg(null)}
              className="absolute top-6 right-6 p-1.5 rounded-xl bg-slate-800 text-slate-400 hover:text-white transition"
            >
              <X className="w-4 h-4" />
            </button>

            {detailLoading ? (
              <div className="py-20 text-center text-xs text-slate-400 flex flex-col items-center justify-center space-y-2">
                <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
                <span>Retrieving complete performance evaluation profile...</span>
              </div>
            ) : detailError ? (
              <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{detailError}</span>
              </div>
            ) : studentDetail ? (
              <div className="space-y-6">
                {/* Header */}
                <div className="border-b border-slate-800 pb-4">
                  <div className="flex flex-wrap items-center gap-2 mb-1.5">
                    <span className="font-mono text-xs font-bold text-cyan-400 bg-cyan-950/70 border border-cyan-800/60 px-2.5 py-0.5 rounded">
                      {studentDetail.profile?.registration_number}
                    </span>
                    <span className="text-xs text-slate-400">•</span>
                    <span className="text-xs text-slate-300 font-semibold">
                      {studentDetail.profile?.department || 'CSE'}
                    </span>
                    <span className="text-xs text-slate-400">•</span>
                    <span className="text-xs text-slate-400">
                      Target: {studentDetail.profile?.target_role || 'Associate Software Engineer'}
                    </span>
                  </div>
                  <h3 className="text-xl font-bold text-white">
                    {studentDetail.profile?.full_name || studentDetail.profile?.registration_number}
                  </h3>
                </div>

                {/* Level Recommendation Card */}
                <div className="p-5 rounded-2xl bg-gradient-to-br from-[#0c182c] to-[#080f1e] border border-cyan-500/30 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">
                      Recommended Next Interview Level
                    </span>
                    {getLevelBadge(studentDetail.recommendation?.recommended_level)}
                  </div>
                  <p className="text-xs sm:text-sm text-slate-200 leading-relaxed">
                    {studentDetail.recommendation?.explanation}
                  </p>
                  {studentDetail.recommendation?.progression_requirements && (
                    <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-xs text-slate-300">
                      <strong className="text-white">Progression Target: </strong>
                      {studentDetail.recommendation?.progression_requirements}
                    </div>
                  )}
                </div>

                {/* Topic Mastery Summary */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                    <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Topic Performance Mastery</span>
                  </h4>
                  {(!studentDetail.topic_mastery || studentDetail.topic_mastery.length === 0) ? (
                    <p className="text-xs text-slate-500">No evaluated topic records on file.</p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {studentDetail.topic_mastery.map((tm) => (
                        <div key={tm.topic} className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-xs flex items-center justify-between">
                          <div>
                            <div className="font-semibold text-slate-200">{tm.topic}</div>
                            <div className="text-[10px] text-slate-500">{tm.questions_tested} Qs evaluated</div>
                          </div>
                          <div className="font-mono font-bold text-white">
                            {tm.average_score} / 10
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* History list */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                    <Calendar className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Completed Interview Sessions</span>
                  </h4>
                  {(!studentDetail.recent_history || studentDetail.recent_history.length === 0) ? (
                    <p className="text-xs text-slate-500">No completed interviews on record yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {studentDetail.recent_history.map((h) => (
                        <div key={h.session_id} className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between text-xs">
                          <div>
                            <div className="font-semibold text-slate-200">{h.selected_role || h.interview_title}</div>
                            <div className="text-[10px] font-mono text-slate-400">{new Date(h.completed_at).toLocaleString()}</div>
                          </div>
                          <div className="flex items-center space-x-3">
                            <span className="font-mono font-bold text-emerald-400">{h.overall_score} / 10</span>
                            <Link
                              to={h.report_url}
                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 font-semibold text-[11px] flex items-center space-x-1"
                            >
                              <span>Report</span>
                              <ExternalLink className="w-3 h-3" />
                            </Link>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
