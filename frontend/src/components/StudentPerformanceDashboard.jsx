import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Award,
  TrendingUp,
  TrendingDown,
  Minus,
  BrainCircuit,
  Sparkles,
  Target,
  BookOpen,
  Calendar,
  Clock,
  Play,
  FileText,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Loader2,
  ChevronRight,
  ExternalLink,
  Edit3,
  X,
  Plus,
  Tag,
  ShieldAlert,
  GraduationCap,
  Briefcase,
} from 'lucide-react';
import {
  getStudentProgressSummary,
  getStudentInterviewHistory,
  updateStudentProfile,
} from '../api/client';

export default function StudentPerformanceDashboard({ onStartInterview, user }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Profile Edit Modal State
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState({
    target_role: '',
    experience_level: '',
    technical_skills: [],
    preferred_languages: [],
  });
  const [newSkillInput, setNewSkillInput] = useState('');
  const [newLangInput, setNewLangInput] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);
  const [saveProfileError, setSaveProfileError] = useState(null);

  const fetchProgressData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    const res = await getStudentProgressSummary();
    if (res.success) {
      setSummary(res.data);
      if (res.data?.profile) {
        setEditForm({
          target_role: res.data.profile.target_role || 'Associate Software Engineer',
          experience_level: res.data.profile.experience_level || 'Entry Level',
          technical_skills: res.data.profile.technical_skills || ['Python', 'DSA'],
          preferred_languages: res.data.profile.preferred_languages || ['Python'],
        });
      }
    } else {
      setError(res.error || 'Failed to load performance tracking summary');
    }

    if (isRefresh) setRefreshing(false);
    else setLoading(false);
  }, []);

  useEffect(() => {
    fetchProgressData();
  }, [fetchProgressData]);

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setSavingProfile(true);
    setSaveProfileError(null);

    const res = await updateStudentProfile({
      target_role: editForm.target_role,
      experience_level: editForm.experience_level,
      technical_skills: editForm.technical_skills,
      preferred_languages: editForm.preferred_languages,
    });

    if (res.success) {
      setShowEditModal(false);
      fetchProgressData(true);
    } else {
      setSaveProfileError(res.error || 'Failed to update profile');
    }
    setSavingProfile(false);
  };

  const addSkill = () => {
    const val = newSkillInput.trim();
    if (val && !editForm.technical_skills.includes(val)) {
      setEditForm((prev) => ({
        ...prev,
        technical_skills: [...prev.technical_skills, val],
      }));
      setNewSkillInput('');
    }
  };

  const removeSkill = (skill) => {
    setEditForm((prev) => ({
      ...prev,
      technical_skills: prev.technical_skills.filter((s) => s !== skill),
    }));
  };

  const addLang = () => {
    const val = newLangInput.trim();
    if (val && !editForm.preferred_languages.includes(val)) {
      setEditForm((prev) => ({
        ...prev,
        preferred_languages: [...prev.preferred_languages, val],
      }));
      setNewLangInput('');
    }
  };

  const removeLang = (lang) => {
    setEditForm((prev) => ({
      ...prev,
      preferred_languages: prev.preferred_languages.filter((l) => l !== lang),
    }));
  };

  // Helper for trend badge styling
  const getTrendVisuals = (trend) => {
    switch (trend) {
      case 'improving':
        return {
          label: 'Improving Trend',
          icon: TrendingUp,
          badgeClass: 'bg-emerald-950/70 text-emerald-300 border-emerald-700/60 shadow-[0_0_12px_rgba(16,185,129,0.15)]',
          dotClass: 'bg-emerald-400',
        };
      case 'declining':
        return {
          label: 'Needs Attention',
          icon: TrendingDown,
          badgeClass: 'bg-rose-950/70 text-rose-300 border-rose-700/60 shadow-[0_0_12px_rgba(244,63,94,0.15)]',
          dotClass: 'bg-rose-400',
        };
      case 'stable':
        return {
          label: 'Stable Performance',
          icon: Minus,
          badgeClass: 'bg-cyan-950/70 text-cyan-300 border-cyan-700/60 shadow-[0_0_12px_rgba(6,182,212,0.15)]',
          dotClass: 'bg-cyan-400',
        };
      default:
        return {
          label: 'Baseline Building',
          icon: Clock,
          badgeClass: 'bg-slate-800/80 text-slate-300 border-slate-700/60',
          dotClass: 'bg-slate-400',
        };
    }
  };

  // Helper for recommendation level theme
  const getLevelTheme = (level) => {
    switch (level) {
      case 'Advanced':
        return {
          border: 'border-violet-500/50 hover:border-violet-400',
          bgGradient: 'from-violet-950/40 via-[#0a1024] to-[#070b14]',
          badgeBg: 'bg-violet-950/80 text-violet-300 border-violet-700/70 shadow-[0_0_15px_rgba(139,92,246,0.3)]',
          textColor: 'text-violet-400',
          glow: 'bg-violet-500/15',
          btnGradient: 'from-violet-600 via-indigo-600 to-cyan-600 hover:from-violet-500 hover:via-indigo-500 hover:to-cyan-500 shadow-violet-600/30',
        };
      case 'Intermediate':
        return {
          border: 'border-cyan-500/50 hover:border-cyan-400',
          bgGradient: 'from-cyan-950/40 via-[#0a1224] to-[#070b14]',
          badgeBg: 'bg-cyan-950/80 text-cyan-300 border-cyan-700/70 shadow-[0_0_15px_rgba(6,182,212,0.3)]',
          textColor: 'text-cyan-400',
          glow: 'bg-cyan-500/15',
          btnGradient: 'from-cyan-500 via-indigo-600 to-violet-600 hover:from-cyan-400 hover:via-indigo-500 hover:to-violet-500 shadow-cyan-600/30',
        };
      default: // Beginner
        return {
          border: 'border-emerald-500/50 hover:border-emerald-400',
          bgGradient: 'from-emerald-950/40 via-[#081420] to-[#070b14]',
          badgeBg: 'bg-emerald-950/80 text-emerald-300 border-emerald-700/70 shadow-[0_0_15px_rgba(16,185,129,0.3)]',
          textColor: 'text-emerald-400',
          glow: 'bg-emerald-500/15',
          btnGradient: 'from-emerald-500 via-teal-600 to-cyan-600 hover:from-emerald-400 hover:via-teal-500 hover:to-cyan-500 shadow-emerald-600/30',
        };
    }
  };

  if (loading) {
    return (
      <section className="mb-8 p-6 sm:p-8 rounded-3xl bg-[#091122]/90 border border-slate-800/80 shadow-2xl flex items-center justify-center py-16">
        <div className="flex flex-col items-center space-y-3">
          <Loader2 className="w-8 h-8 animate-spin text-cyan-400" />
          <span className="text-xs text-slate-400 font-medium tracking-wide">
            Analyzing student interview performance and deriving recommendation...
          </span>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="mb-8 p-6 sm:p-8 rounded-3xl bg-rose-950/20 border border-rose-800/40 shadow-xl">
        <div className="flex items-center space-x-3 text-rose-400 mb-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <h3 className="text-sm font-bold">Could not load performance tracking data</h3>
        </div>
        <p className="text-xs text-rose-300/80 mb-4">{error}</p>
        <button
          onClick={() => fetchProgressData()}
          className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 flex items-center space-x-2 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Retry Loading</span>
        </button>
      </section>
    );
  }

  const profile = summary?.profile || {};
  const rec = summary?.recommendation || {};
  const trendVisual = getTrendVisuals(rec.score_trend || 'insufficient_data');
  const levelTheme = getLevelTheme(rec.recommended_level || 'Beginner');

  return (
    <section
      className="mb-8 p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-[#091122]/95 via-[#080e1b]/95 to-[#060a14]/95 border border-slate-800/80 shadow-2xl relative overflow-hidden"
      aria-labelledby="performance-tracking-heading"
    >
      {/* Ambient background glows */}
      <div className={`absolute top-0 right-0 w-96 h-96 ${levelTheme.glow} rounded-full blur-3xl pointer-events-none`} />
      <div className="absolute bottom-0 left-0 w-80 h-80 bg-cyan-600/10 rounded-full blur-3xl pointer-events-none" />

      {/* Header bar: Title, Refresh, and Profile Details */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6 relative z-10 pb-5 border-b border-slate-800/80">
        <div className="space-y-1">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600/30 to-violet-600/30 text-cyan-400 border border-cyan-500/40 flex items-center justify-center shadow-lg shadow-cyan-950/50">
              <Sparkles className="w-5 h-5 text-cyan-300" />
            </div>
            <div>
              <h2 id="performance-tracking-heading" className="text-lg sm:text-xl font-extrabold text-white tracking-tight flex items-center space-x-2">
                <span>Personalized Interview Progression & Level Recommendation</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Multi-session performance tracking derived from verified completed evaluations.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-3 shrink-0">
          <button
            onClick={() => setShowEditModal(true)}
            className="px-3.5 py-1.5 rounded-xl bg-slate-800/90 hover:bg-slate-700/90 text-slate-300 hover:text-white border border-slate-700/80 text-xs font-semibold flex items-center space-x-2 transition shadow-sm"
            title="Edit target role and preferences"
          >
            <Edit3 className="w-3.5 h-3.5 text-cyan-400" />
            <span>Profile & Skills</span>
          </button>
          <button
            onClick={() => fetchProgressData(true)}
            disabled={refreshing}
            className="p-2 rounded-xl bg-slate-800/90 hover:bg-slate-700/90 text-slate-400 hover:text-cyan-300 border border-slate-700/80 text-xs transition"
            title="Refresh performance metrics"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Metric Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 mb-6 relative z-10">
        {/* Completed Interviews */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1">
            <CheckCircle2 className="w-4 h-4 text-cyan-400" />
            <span>Completed Sessions</span>
          </div>
          <div className="text-2xl font-extrabold text-white font-mono">
            {summary?.total_completed_interviews ?? 0}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Authoritative records</div>
        </div>

        {/* Latest Score */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1">
            <Award className="w-4 h-4 text-emerald-400" />
            <span>Latest Valid Score</span>
          </div>
          <div className="text-2xl font-extrabold text-emerald-400 font-mono">
            {rec.latest_score !== null && rec.latest_score !== undefined ? `${rec.latest_score} / 10` : '—'}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Most recent evaluation</div>
        </div>

        {/* Historical Average */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1">
            <Target className="w-4 h-4 text-violet-400" />
            <span>Historical Average</span>
          </div>
          <div className="text-2xl font-extrabold text-violet-300 font-mono">
            {rec.average_score !== null && rec.average_score !== undefined ? `${rec.average_score} / 10` : '—'}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Cumulative average</div>
        </div>

        {/* Performance Trend */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1">
            <trendVisual.icon className="w-4 h-4 text-cyan-400" />
            <span>Performance Trend</span>
          </div>
          <div className="flex items-center space-x-2 mt-1">
            <span className={`text-xs px-2.5 py-1 rounded-full border font-bold flex items-center space-x-1.5 ${trendVisual.badgeClass}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${trendVisual.dotClass}`} />
              <span>{trendVisual.label}</span>
            </span>
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {summary?.total_completed_interviews < 2 ? 'Needs 2+ sessions' : 'Multi-session trend'}
          </div>
        </div>
      </div>

      {/* RECOMMENDED NEXT INTERVIEW CARD */}
      <div className={`p-6 sm:p-7 rounded-3xl bg-gradient-to-br ${levelTheme.bgGradient} border ${levelTheme.border} shadow-2xl relative overflow-hidden mb-7 transition-all duration-300`}>
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
          <div className="space-y-3.5 max-w-3xl">
            {/* Badges row */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Next Recommended Level:
              </span>
              <span className={`text-xs font-extrabold px-3 py-1 rounded-full border ${levelTheme.badgeBg}`}>
                {rec.recommended_level || 'Beginner'} Level
              </span>
              <span className={`text-xs px-2.5 py-0.5 rounded-md border font-semibold ${rec.status === 'provisional' ? 'bg-amber-950/60 text-amber-300 border-amber-800/60' : 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'}`}>
                {rec.status === 'provisional' ? 'Provisional Baseline' : 'Evidence-Supported'}
              </span>
              <span className="text-xs px-2.5 py-0.5 rounded-md bg-slate-800/90 text-slate-300 border border-slate-700/60 font-mono">
                Evidence: {rec.evidence_sufficiency || 'limited'} ({summary?.total_completed_interviews || 0} completed)
              </span>
            </div>

            {/* Explanation */}
            <div>
              <h3 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Why was {rec.recommended_level || 'Beginner'} selected?
              </h3>
              <p className="text-xs sm:text-sm text-slate-300 mt-1 leading-relaxed">
                {rec.explanation}
              </p>
            </div>

            {/* Progression Requirements */}
            {rec.progression_requirements && (
              <div className="p-3.5 rounded-2xl bg-[#080f20]/80 border border-slate-800/80 text-xs">
                <span className="font-bold text-slate-200">How to progress: </span>
                <span className="text-slate-300">{rec.progression_requirements}</span>
              </div>
            )}

            {/* Suggested Focus */}
            {rec.suggested_focus && (
              <div className="flex items-start space-x-2 text-xs text-slate-400">
                <Target className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" />
                <span>
                  <strong className="text-slate-300">Suggested Next Focus: </strong>
                  {rec.suggested_focus}
                </span>
              </div>
            )}
          </div>

          {/* Action Button */}
          <div className="flex flex-col sm:flex-row lg:flex-col items-stretch lg:items-end gap-3 shrink-0">
            <button
              onClick={() => onStartInterview && onStartInterview(profile.target_role || 'Associate Software Engineer')}
              className={`px-7 py-3.5 rounded-xl bg-gradient-to-r ${levelTheme.btnGradient} text-white font-bold text-xs sm:text-sm shadow-lg hover:scale-105 active:scale-95 transition-all duration-200 flex items-center justify-center space-x-2`}
            >
              <Play className="w-4 h-4 fill-white" />
              <span>Start Recommended Interview</span>
            </button>
            <div className="text-[11px] text-slate-400 text-center lg:text-right font-mono">
              Target Track: {profile.target_role || 'Associate Software Engineer'}
            </div>
          </div>
        </div>
      </div>

      {/* TOPIC MASTERY & PRACTICE PRIORITIES GRID */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-7 relative z-10">
        {/* Topic Mastery */}
        <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1224] to-[#070c17] border border-slate-800/80">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <BrainCircuit className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white">Evaluated Topic Mastery</h3>
            </div>
            <span className="text-xs text-slate-400 font-mono">
              {summary?.topic_mastery?.length || 0} Topics Tested
            </span>
          </div>

          {(!summary?.topic_mastery || summary.topic_mastery.length === 0) ? (
            <div className="py-8 text-center text-xs text-slate-400 border border-dashed border-slate-800 rounded-xl p-4">
              <BookOpen className="w-6 h-6 text-slate-600 mx-auto mb-2" />
              <span>No evaluated topic scores yet. Complete your first interview to track technical subject breakdown.</span>
            </div>
          ) : (
            <div className="space-y-3.5">
              {summary.topic_mastery.map((tm) => {
                const pct = Math.min(Math.max((tm.average_score / 10) * 100, 0), 100);
                const isGreen = tm.average_score >= 7.5;
                const isAmber = tm.average_score >= 5.0 && tm.average_score < 7.5;

                return (
                  <div key={tm.topic} className="space-y-1.5 p-3 rounded-xl bg-[#080d1a]/80 border border-slate-800/60">
                    <div className="flex items-center justify-between text-xs">
                      <div className="font-semibold text-slate-200 flex items-center space-x-2">
                        <span>{tm.topic}</span>
                        <span className="text-[10px] text-slate-400 font-mono">({tm.questions_tested} Qs)</span>
                      </div>
                      <div className="flex items-center space-x-2 font-mono">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${isGreen ? 'bg-emerald-950/70 text-emerald-300' : isAmber ? 'bg-amber-950/70 text-amber-300' : 'bg-rose-950/70 text-rose-300'}`}>
                          {tm.mastery_level}
                        </span>
                        <span className="font-bold text-white">{tm.average_score} / 10</span>
                      </div>
                    </div>
                    {/* Progress Bar */}
                    <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${isGreen ? 'bg-emerald-400' : isAmber ? 'bg-amber-400' : 'bg-rose-500'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Practice Priorities */}
        <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1224] to-[#070c17] border border-slate-800/80">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Target className="w-4 h-4 text-violet-400" />
              <h3 className="text-sm font-bold text-white">Targeted Practice Priorities</h3>
            </div>
            <span className="text-xs text-slate-400">Actionable Focus</span>
          </div>

          {(!rec.practice_priorities || rec.practice_priorities.length === 0) ? (
            <div className="py-8 text-center text-xs text-slate-400 border border-dashed border-slate-800 rounded-xl p-4">
              <CheckCircle2 className="w-6 h-6 text-emerald-500/60 mx-auto mb-2" />
              <span>
                {summary?.total_completed_interviews === 0
                  ? 'Complete an interview to identify high-priority practice areas.'
                  : 'Great job! No major deficit areas (< 6.0/10) currently flagged.'}
              </span>
            </div>
          ) : (
            <div className="space-y-3">
              {rec.practice_priorities.map((item) => (
                <div key={item.topic} className="p-3.5 rounded-xl bg-[#080d1a]/80 border border-slate-800/70 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-slate-200">{item.topic}</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${item.priority === 'high' ? 'bg-rose-950/80 text-rose-300 border border-rose-800/60' : 'bg-amber-950/80 text-amber-300 border border-amber-800/60'}`}>
                      {item.priority} Priority
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">{item.reason}</p>
                  <p className="text-xs text-cyan-300 font-medium">
                    Recommended: {item.recommended_focus}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* INTERVIEW HISTORY SECTION */}
      {summary?.recent_history && summary.recent_history.length > 0 && (
        <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1224] to-[#070c17] border border-slate-800/80 relative z-10">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Calendar className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white">Completed Interview History & Reports</h3>
            </div>
            <span className="text-xs text-slate-400 font-mono">
              {summary.recent_history.length} Sessions on Record
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-[11px] uppercase tracking-wider text-slate-400 bg-slate-900/60 border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Date Completed</th>
                  <th className="py-3 px-4">Role / Title</th>
                  <th className="py-3 px-4">Difficulty Level</th>
                  <th className="py-3 px-4">Score</th>
                  <th className="py-3 px-4">Performance</th>
                  <th className="py-3 px-4 text-right">Report</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {summary.recent_history.map((item) => (
                  <tr key={item.session_id} className="hover:bg-slate-800/30 transition">
                    <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                      {new Date(item.completed_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 font-sans font-semibold text-slate-200">
                      {item.selected_role || item.interview_title}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${item.difficulty_level === 'Advanced' ? 'bg-violet-950/70 text-violet-300' : item.difficulty_level === 'Intermediate' ? 'bg-cyan-950/70 text-cyan-300' : 'bg-emerald-950/70 text-emerald-300'}`}>
                        {item.difficulty_level}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-bold text-white">
                      {item.overall_score} / 10 ({item.percentage_score}%)
                    </td>
                    <td className="py-3 px-4 font-sans text-slate-300">
                      {item.performance_level}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Link
                        to={item.report_url}
                        className="inline-flex items-center space-x-1 px-3 py-1 rounded-lg bg-cyan-950/70 hover:bg-cyan-900/80 text-cyan-300 border border-cyan-800/60 font-sans text-xs font-semibold transition"
                      >
                        <span>Scorecard</span>
                        <ChevronRight className="w-3 h-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* PROFILE EDIT MODAL */}
      {showEditModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[#0c1424] border border-slate-700/80 rounded-3xl w-full max-w-lg p-6 sm:p-7 shadow-2xl space-y-5 text-slate-200 relative">
            <button
              onClick={() => setShowEditModal(false)}
              className="absolute top-5 right-5 p-1.5 rounded-xl bg-slate-800 text-slate-400 hover:text-white transition"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-xl bg-cyan-500/20 text-cyan-400 flex items-center justify-center border border-cyan-500/30">
                <Edit3 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Update Technical Profile & Target Role</h3>
                <p className="text-xs text-slate-400">Refine your target track and skills to calibrate recommendations.</p>
              </div>
            </div>

            {saveProfileError && (
              <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{saveProfileError}</span>
              </div>
            )}

            <form onSubmit={handleSaveProfile} className="space-y-4 text-xs">
              {/* Target Role */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">Target Job Role</label>
                <select
                  value={editForm.target_role}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, target_role: e.target.value }))}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-400"
                >
                  <option value="Associate Software Engineer">Associate Software Engineer</option>
                  <option value="Software Development Engineer">Software Development Engineer</option>
                  <option value="Product Engineer">Product Engineer</option>
                  <option value="System Engineer">System Engineer</option>
                  <option value="Testing Engineer">Testing Engineer</option>
                </select>
              </div>

              {/* Experience Level */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">Experience Level</label>
                <select
                  value={editForm.experience_level}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, experience_level: e.target.value }))}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-400"
                >
                  <option value="Entry Level">Entry Level (0-1 yrs)</option>
                  <option value="Intermediate">Intermediate (1-3 yrs)</option>
                  <option value="Experienced">Experienced (3+ yrs)</option>
                </select>
              </div>

              {/* Technical Skills Tags */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">Technical Skills</label>
                <div className="flex items-center space-x-2 mb-2">
                  <input
                    type="text"
                    value={newSkillInput}
                    onChange={(e) => setNewSkillInput(e.target.value)}
                    placeholder="e.g. React, SQL, DSA"
                    className="flex-1 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-400 text-xs"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addSkill();
                      }
                    }}
                  />
                  <button
                    type="button"
                    onClick={addSkill}
                    className="px-3 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-semibold flex items-center space-x-1"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add</span>
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {editForm.technical_skills.map((skill) => (
                    <span key={skill} className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 text-[11px] flex items-center space-x-1">
                      <span>{skill}</span>
                      <button type="button" onClick={() => removeSkill(skill)} className="text-slate-400 hover:text-rose-400">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Preferred Languages */}
              <div>
                <label className="block font-semibold text-slate-300 mb-1.5">Preferred Programming Languages</label>
                <div className="flex items-center space-x-2 mb-2">
                  <input
                    type="text"
                    value={newLangInput}
                    onChange={(e) => setNewLangInput(e.target.value)}
                    placeholder="e.g. Python, Java, C++"
                    className="flex-1 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-400 text-xs"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addLang();
                      }
                    }}
                  />
                  <button
                    type="button"
                    onClick={addLang}
                    className="px-3 py-1.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold flex items-center space-x-1"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add</span>
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {editForm.preferred_languages.map((lang) => (
                    <span key={lang} className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 text-[11px] flex items-center space-x-1">
                      <span>{lang}</span>
                      <button type="button" onClick={() => removeLang(lang)} className="text-slate-400 hover:text-rose-400">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="pt-3 flex items-center justify-end space-x-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingProfile}
                  className="px-5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold flex items-center space-x-2 disabled:opacity-50"
                >
                  {savingProfile ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <span>Save Preferences</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
