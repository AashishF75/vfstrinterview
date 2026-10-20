import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Loader2,
  ChevronRight,
  Edit3,
  X,
  Plus,
  ShieldCheck,
  SlidersHorizontal,
  BarChart3,
} from 'lucide-react';
import {
  getStudentProgressSummary,
  updateStudentProfile,
} from '../api/client';

/**
 * Interactive SVG Performance Trajectory Chart
 * Plots chronological interview scores with a smooth curve, area fill, benchmark line, and hover tooltip.
 */
function PerformanceTrajectoryChart({ sessions = [] }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);

  // Chronologically sort sessions (oldest to newest)
  const sortedSessions = useMemo(() => {
    return [...sessions].sort(
      (a, b) => new Date(a.completed_at) - new Date(b.completed_at)
    );
  }, [sessions]);

  if (sortedSessions.length < 2) {
    return null;
  }

  const width = 640;
  const height = 180;
  const padX = 42;
  const padTop = 26;
  const padBottom = 34;
  const chartW = width - padX * 2;
  const chartH = height - padTop - padBottom;

  // Coordinate mapping
  const points = sortedSessions.map((s, idx) => {
    const x = padX + (idx / (sortedSessions.length - 1)) * chartW;
    const score = typeof s.overall_score === 'number' ? s.overall_score : 0;
    const y = padTop + (1 - Math.min(Math.max(score / 10, 0), 1)) * chartH;
    return { x, y, score, session: s, idx };
  });

  // Construct SVG cubic Bezier path for smooth aesthetic
  let pathD = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i];
    const p1 = points[i + 1];
    const cpx1 = p0.x + (p1.x - p0.x) / 2;
    const cpy1 = p0.y;
    const cpx2 = p0.x + (p1.x - p0.x) / 2;
    const cpy2 = p1.y;
    pathD += ` C ${cpx1} ${cpy1}, ${cpx2} ${cpy2}, ${p1.x} ${p1.y}`;
  }

  // Area path closing down to bottom
  const areaD = `${pathD} L ${points[points.length - 1].x} ${height - padBottom} L ${points[0].x} ${height - padBottom} Z`;

  // Benchmark line at score 7.0 (readiness benchmark)
  const benchmarkY = padTop + (1 - 7.0 / 10) * chartH;

  return (
    <div className="relative w-full">
      <div className="flex items-center justify-between mb-3 text-xs">
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-slate-200">Score Trajectory Over Time</span>
          <span className="text-[11px] text-slate-400 font-mono">({sortedSessions.length} recorded evaluations)</span>
        </div>
        <div className="flex items-center space-x-3 text-[11px] text-slate-400">
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-0.5 bg-cyan-400 inline-block rounded-full" />
            <span>Score Curve</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-0.5 border-t border-dashed border-emerald-400/70 inline-block" />
            <span className="text-emerald-400/90 font-medium">7.0 Benchmark</span>
          </div>
        </div>
      </div>

      <div className="relative overflow-visible rounded-2xl bg-[#070d18]/80 border border-slate-800/80 p-2 sm:p-4">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto overflow-visible select-none"
        >
          <defs>
            <linearGradient id="chartGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.32" />
              <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id="lineStroke" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#06b6d4" />
              <stop offset="50%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#a855f7" />
            </linearGradient>
          </defs>

          {/* Grid horizontal guidelines */}
          {[10, 7, 5, 0].map((val) => {
            const yPos = padTop + (1 - val / 10) * chartH;
            return (
              <g key={val}>
                <line
                  x1={padX}
                  y1={yPos}
                  x2={width - padX}
                  y2={yPos}
                  stroke="rgba(148, 163, 184, 0.08)"
                  strokeDasharray={val === 7 ? '3 3' : 'none'}
                />
                <text
                  x={padX - 8}
                  y={yPos + 3}
                  textAnchor="end"
                  fill={val === 7 ? '#10b981' : '#64748b'}
                  fontSize="10"
                  fontFamily="monospace"
                  fontWeight={val === 7 ? '600' : '400'}
                >
                  {val}.0
                </text>
              </g>
            );
          })}

          {/* Benchmark line highlight */}
          <line
            x1={padX}
            y1={benchmarkY}
            x2={width - padX}
            y2={benchmarkY}
            stroke="#10b981"
            strokeWidth="1.2"
            strokeDasharray="4 4"
            opacity="0.6"
          />

          {/* Area fill under curve */}
          <path d={areaD} fill="url(#chartGradient)" />

          {/* Smooth score curve */}
          <path
            d={pathD}
            fill="none"
            stroke="url(#lineStroke)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Interactive Data Points */}
          {points.map((pt, i) => {
            const isHovered = hoveredIdx === i;
            return (
              <g
                key={pt.session.session_id || i}
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                className="cursor-pointer"
              >
                {/* Hit area */}
                <circle cx={pt.x} cy={pt.y} r="14" fill="transparent" />

                {/* Outer halo */}
                <circle
                  cx={pt.x}
                  cy={pt.y}
                  r={isHovered ? '7' : '4.5'}
                  fill="#030712"
                  stroke={isHovered ? '#38bdf8' : '#818cf8'}
                  strokeWidth={isHovered ? '2.5' : '2'}
                  className="transition-all duration-150"
                />

                {/* Inner dot */}
                <circle
                  cx={pt.x}
                  cy={pt.y}
                  r={isHovered ? '3' : '2'}
                  fill={isHovered ? '#38bdf8' : '#e0e7ff'}
                />

                {/* X axis session date labels - avoid collision when many sessions */}
                {(() => {
                  const showLabel =
                    sortedSessions.length <= 6 ||
                    i === 0 ||
                    i === points.length - 1 ||
                    i % Math.ceil(points.length / 5) === 0 ||
                    isHovered;

                  if (!showLabel) return null;

                  return (
                    <text
                      x={pt.x}
                      y={height - padBottom + 16}
                      textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}
                      fill={isHovered ? '#38bdf8' : '#64748b'}
                      fontSize="10"
                      fontFamily="sans-serif"
                      fontWeight={isHovered ? '600' : '400'}
                    >
                      {new Date(pt.session.completed_at).toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </text>
                  );
                })()}
              </g>
            );
          })}
        </svg>

        {/* Floating Tooltip for Hovered Node - Edge-safe placement */}
        {hoveredIdx !== null && points[hoveredIdx] && (() => {
          const pt = points[hoveredIdx];
          const xPct = (pt.x / width) * 100;
          const yPct = (pt.y / height) * 100;

          let xTransform = '-translate-x-1/2';
          if (xPct < 25) {
            xTransform = 'translate-x-1';
          } else if (xPct > 75) {
            xTransform = '-translate-x-full -ml-1';
          }

          const isNearTop = pt.y < 65;
          const yTransform = isNearTop ? 'translate-y-3' : '-translate-y-full -mt-3';

          return (
            <div
              className={`absolute z-30 pointer-events-none transform ${xTransform} ${yTransform} px-3 py-2 rounded-xl bg-slate-900/95 border border-cyan-500/40 shadow-xl shadow-cyan-950/70 backdrop-blur-md text-xs transition-all duration-150 whitespace-nowrap`}
              style={{
                left: `${xPct}%`,
                top: `${yPct}%`,
              }}
            >
              <div className="font-semibold text-white flex items-center space-x-1.5">
                <span>{pt.session.selected_role || pt.session.interview_title}</span>
              </div>
              <div className="flex items-center space-x-2 mt-0.5 text-[11px] font-mono">
                <span className="text-cyan-300 font-bold">
                  Score: {pt.score} / 10
                </span>
                <span className="text-slate-400">•</span>
                <span className="text-slate-300">
                  {pt.session.difficulty_level || 'Standard'}
                </span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                {new Date(pt.session.completed_at).toLocaleDateString(undefined, {
                  weekday: 'short',
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                })}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

/**
 * Loading Skeleton mirroring final dashboard layout
 */
function DashboardSkeleton() {
  return (
    <section className="mb-8 p-6 sm:p-8 rounded-3xl bg-[#091122]/90 border border-slate-800/80 shadow-2xl animate-pulse">
      {/* Header skeleton */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-800/80 mb-6">
        <div className="space-y-2">
          <div className="h-7 w-48 bg-slate-800 rounded-xl" />
          <div className="h-3.5 w-80 bg-slate-800/60 rounded-lg" />
        </div>
        <div className="flex items-center space-x-2">
          <div className="h-9 w-28 bg-slate-800 rounded-xl" />
          <div className="h-9 w-9 bg-slate-800 rounded-xl" />
        </div>
      </div>

      {/* Metric Cards Skeleton */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 mb-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 h-28 space-y-2">
            <div className="h-3 w-20 bg-slate-800 rounded" />
            <div className="h-7 w-16 bg-slate-800 rounded" />
            <div className="h-2.5 w-24 bg-slate-800/50 rounded" />
          </div>
        ))}
      </div>

      {/* Hero Recommendation Skeleton */}
      <div className="p-6 rounded-3xl bg-slate-900/40 border border-slate-800/80 h-44 mb-6" />

      {/* Grid Skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="h-60 rounded-2xl bg-slate-900/40 border border-slate-800/80" />
        <div className="h-60 rounded-2xl bg-slate-900/40 border border-slate-800/80" />
      </div>
    </section>
  );
}

export default function StudentPerformanceDashboard({ onStartInterview, user }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Topic filter tab: 'ALL' | 'STRENGTHS' | 'DEVELOPING' | 'GAPS'
  const [topicFilter, setTopicFilter] = useState('ALL');

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
      setError(res.error || 'Failed to load student performance tracking');
    }

    if (isRefresh) setRefreshing(false);
    else setLoading(false);
  }, []);

  useEffect(() => {
    fetchProgressData();
  }, [fetchProgressData]);

  // Accessibility: close modal on Escape key press
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && showEditModal) {
        setShowEditModal(false);
      }
    };
    if (showEditModal) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [showEditModal]);

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
      setSaveProfileError(res.error || 'Failed to update target preferences');
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
          label: 'Improving',
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
          label: 'Consistent',
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
          border: 'border-violet-500/40 hover:border-violet-400/80',
          bgGradient: 'from-violet-950/30 via-[#0a0f20]/90 to-[#070b14]/95',
          badgeBg: 'bg-violet-950/80 text-violet-300 border-violet-700/60 shadow-[0_0_15px_rgba(139,92,246,0.25)]',
          textColor: 'text-violet-400',
          glow: 'bg-violet-500/10',
          btnGradient: 'from-violet-600 via-indigo-600 to-cyan-600 hover:from-violet-500 hover:via-indigo-500 hover:to-cyan-500 shadow-violet-600/30',
        };
      case 'Intermediate':
        return {
          border: 'border-cyan-500/40 hover:border-cyan-400/80',
          bgGradient: 'from-cyan-950/30 via-[#0a1224]/90 to-[#070b14]/95',
          badgeBg: 'bg-cyan-950/80 text-cyan-300 border-cyan-700/60 shadow-[0_0_15px_rgba(6,182,212,0.25)]',
          textColor: 'text-cyan-400',
          glow: 'bg-cyan-500/10',
          btnGradient: 'from-cyan-500 via-indigo-600 to-violet-600 hover:from-cyan-400 hover:via-indigo-500 hover:to-violet-500 shadow-cyan-600/30',
        };
      default: // Beginner
        return {
          border: 'border-emerald-500/40 hover:border-emerald-400/80',
          bgGradient: 'from-emerald-950/30 via-[#081420]/90 to-[#070b14]/95',
          badgeBg: 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60 shadow-[0_0_15px_rgba(16,185,129,0.25)]',
          textColor: 'text-emerald-400',
          glow: 'bg-emerald-500/10',
          btnGradient: 'from-emerald-500 via-teal-600 to-cyan-600 hover:from-emerald-400 hover:via-teal-500 hover:to-cyan-500 shadow-emerald-600/30',
        };
    }
  };

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <section className="mb-8 p-6 sm:p-8 rounded-3xl bg-rose-950/20 border border-rose-800/40 shadow-xl text-slate-200">
        <div className="flex items-center space-x-3 text-rose-400 mb-2">
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
  const completedCount = summary?.total_completed_interviews || 0;
  const trendVisual = getTrendVisuals(rec.score_trend || 'insufficient_data');
  const levelTheme = getLevelTheme(rec.recommended_level || 'Beginner');

  // Filtered topics
  const topics = summary?.topic_mastery || [];
  const filteredTopics = topics.filter((t) => {
    if (topicFilter === 'STRENGTHS') return t.average_score >= 7.5;
    if (topicFilter === 'DEVELOPING') return t.average_score >= 5.0 && t.average_score < 7.5;
    if (topicFilter === 'GAPS') return t.average_score < 5.0;
    return true;
  });

  return (
    <section
      className="mb-8 p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-[#091122]/95 via-[#080e1b]/95 to-[#060a14]/95 border border-slate-800/80 shadow-2xl relative overflow-hidden"
      aria-labelledby="my-performance-heading"
    >
      {/* Ambient background glows */}
      <div className={`absolute top-0 right-0 w-96 h-96 ${levelTheme.glow} rounded-full blur-3xl pointer-events-none`} />
      <div className="absolute bottom-0 left-0 w-80 h-80 bg-cyan-600/10 rounded-full blur-3xl pointer-events-none" />

      {/* ======================================================================
          SECTION 3: REDESIGNED REPORT HEADER
          ====================================================================== */}
      <header className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-7 relative z-10 pb-5 border-b border-slate-800/80">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2
              id="my-performance-heading"
              className="text-xl sm:text-2xl font-extrabold text-white tracking-tight flex items-center space-x-2.5"
            >
              <span>My Performance</span>
            </h2>
            <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${levelTheme.badgeBg} flex items-center space-x-1.5`}>
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              <span>{rec.recommended_level || 'Beginner'} Level Recommended</span>
            </span>
            <span className="text-[11px] font-medium text-slate-400 bg-slate-900/80 px-2.5 py-0.5 rounded-full border border-slate-800 flex items-center space-x-1">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
              <span>VFSTR Official Record</span>
            </span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed max-w-2xl">
            Longitudinal interview progress, verified score consistency, and personalized difficulty calibrator derived from authoritative completed assessments.
          </p>
        </div>

        {/* Header Action Controls */}
        <div className="flex items-center space-x-2.5 shrink-0">
          <button
            onClick={() => setShowEditModal(true)}
            className="px-3.5 py-2 rounded-xl bg-slate-900/90 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700/80 text-xs font-semibold flex items-center space-x-2 transition shadow-sm hover:border-slate-600 active:scale-95"
            title="Edit target job role and skill profile"
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-cyan-400" />
            <span>Target Role & Skills</span>
          </button>
          <button
            onClick={() => fetchProgressData(true)}
            disabled={refreshing}
            className="p-2.5 rounded-xl bg-slate-900/90 hover:bg-slate-800 text-slate-400 hover:text-cyan-300 border border-slate-700/80 text-xs transition shadow-sm hover:border-slate-600 active:scale-95 disabled:opacity-50"
            title="Refresh verified metrics"
            aria-label="Refresh performance metrics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </header>

      {/* ======================================================================
          SECTION 4: PERFORMANCE OVERVIEW GRID (4 CORE METRICS)
          ====================================================================== */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 mb-7 relative z-10">
        {/* Completed Assessments */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 hover:border-slate-700/80 transition-all duration-200">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1.5">
            <div className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <CheckCircle2 className="w-3.5 h-3.5" />
            </div>
            <span className="font-medium">Completed</span>
          </div>
          <div className="text-2xl font-extrabold text-white font-mono tracking-tight">
            {completedCount}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {completedCount === 1 ? '1 interview session' : `${completedCount} total sessions`}
          </div>
        </div>

        {/* Historical Average Score */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 hover:border-slate-700/80 transition-all duration-200">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1.5">
            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Award className="w-3.5 h-3.5" />
            </div>
            <span className="font-medium">Average Score</span>
          </div>
          <div className="text-2xl font-extrabold text-emerald-400 font-mono tracking-tight">
            {rec.average_score !== null && rec.average_score !== undefined ? `${rec.average_score} / 10` : '—'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 truncate">
            {completedCount > 0 && typeof summary?.highest_score === 'number' && typeof summary?.lowest_score === 'number'
              ? `High: ${summary.highest_score} • Low: ${summary.lowest_score}`
              : 'Requires initial score'}
          </div>
        </div>

        {/* Performance Trend */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 hover:border-slate-700/80 transition-all duration-200">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1.5">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <trendVisual.icon className="w-3.5 h-3.5" />
            </div>
            <span className="font-medium">Trend & Stability</span>
          </div>
          <div className="mt-1">
            <span className={`text-[10px] sm:text-[11px] px-2 sm:px-2.5 py-0.5 rounded-full border font-bold inline-flex items-center space-x-1.5 max-w-full ${trendVisual.badgeClass}`}>
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${trendVisual.dotClass}`} />
              <span className="truncate">{trendVisual.label}</span>
            </span>
          </div>
          <div className="text-[11px] text-slate-400 mt-1.5 font-mono">
            {rec.consistency_score !== null && rec.consistency_score !== undefined
              ? `${rec.consistency_score}/10 consistency`
              : completedCount < 2 ? 'Needs 2+ sessions' : 'Stable'}
          </div>
        </div>

        {/* Recommended Level Indicator */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-[#0c1424] to-[#080d19] border border-slate-800/80 hover:border-slate-700/80 transition-all duration-200">
          <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1.5">
            <div className="p-1.5 rounded-lg bg-violet-500/10 text-violet-400 border border-violet-500/20">
              <Target className="w-3.5 h-3.5" />
            </div>
            <span className="font-medium">Target Calibration</span>
          </div>
          <div className={`text-2xl font-extrabold font-mono tracking-tight ${levelTheme.textColor}`}>
            {rec.recommended_level || 'Beginner'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {rec.status === 'provisional' ? 'Provisional baseline' : 'Evidence-supported'}
          </div>
        </div>
      </div>

      {/* ======================================================================
          SECTION 5: RECOMMENDED INTERVIEW LEVEL (HERO HIGHLIGHT CARD)
          ====================================================================== */}
      <div className={`p-6 sm:p-7 rounded-3xl bg-gradient-to-br ${levelTheme.bgGradient} border ${levelTheme.border} shadow-2xl relative overflow-hidden mb-7 transition-all duration-300`}>
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
          <div className="space-y-4 max-w-3xl">
            {/* Header tags */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-extrabold uppercase tracking-widest text-slate-400">
                AI Next Recommendation:
              </span>
              <span className={`text-xs font-extrabold px-3 py-1 rounded-full border ${levelTheme.badgeBg}`}>
                {rec.recommended_level || 'Beginner'} Difficulty
              </span>
              <span className={`text-xs px-2.5 py-0.5 rounded-md border font-semibold ${rec.status === 'provisional' ? 'bg-amber-950/60 text-amber-300 border-amber-800/60' : 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'}`}>
                {rec.status === 'provisional' ? 'Provisional Baseline' : 'Evidence-Supported'}
              </span>
              <span className="text-xs px-2.5 py-0.5 rounded-md bg-slate-900/90 text-slate-300 border border-slate-700/60 font-mono">
                Evidence: {rec.evidence_sufficiency || 'limited'} ({completedCount} completed)
              </span>
            </div>

            {/* Explanation headline & body */}
            <div>
              <h3 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Why was {rec.recommended_level || 'Beginner'} recommended?
              </h3>
              <p className="text-xs sm:text-sm text-slate-300 mt-1 leading-relaxed">
                {rec.explanation}
              </p>
            </div>

            {/* Progression Requirements & Suggested Focus Blocks */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              {rec.progression_requirements && (
                <div className="p-3.5 rounded-2xl bg-[#060c18]/90 border border-slate-800/80 text-xs flex items-start space-x-2.5">
                  <Sparkles className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-slate-200 block mb-0.5">Progression Benchmark</span>
                    <span className="text-slate-300 leading-relaxed">{rec.progression_requirements}</span>
                  </div>
                </div>
              )}

              {rec.suggested_focus && (
                <div className="p-3.5 rounded-2xl bg-[#060c18]/90 border border-slate-800/80 text-xs flex items-start space-x-2.5">
                  <Target className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-slate-200 block mb-0.5">Recommended Next Focus</span>
                    <span className="text-slate-300 leading-relaxed">{rec.suggested_focus}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Action CTA Button */}
          <div className="flex flex-col sm:flex-row lg:flex-col items-stretch lg:items-end gap-2.5 shrink-0">
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

      {/* ======================================================================
          SECTION 6: PERFORMANCE VISUALIZATION (SCORE TREND OVER TIME)
          ====================================================================== */}
      {(summary?.recent_history || []).length >= 2 ? (
        <div className="mb-7 relative z-10">
          <PerformanceTrajectoryChart sessions={summary.recent_history} />
        </div>
      ) : (
        <div className="mb-7 p-5 rounded-2xl bg-[#0a1224]/50 border border-dashed border-slate-800 text-xs text-slate-400 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-slate-800 text-slate-400 shrink-0">
              <BarChart3 className="w-4 h-4 text-cyan-400" />
            </div>
            <div>
              <span className="font-bold text-slate-200 block">Performance Trajectory Calibration</span>
              <span>Complete at least 2 interview sessions to unlock longitudinal score trajectory and consistency analytics.</span>
            </div>
          </div>
          <span className="text-[11px] font-mono px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 border border-slate-700 shrink-0 self-start sm:self-center">
            {completedCount} / 2 Sessions
          </span>
        </div>
      )}

      {/* ======================================================================
          SECTION 7 & 8: TOPIC MASTERY & TARGETED PRACTICE PRIORITIES
          ====================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-7 relative z-10">
        {/* Evaluated Topic Mastery */}
        <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1224] to-[#070c17] border border-slate-800/80">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 mb-4">
            <div className="flex items-center space-x-2">
              <BrainCircuit className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white">Evaluated Topic Mastery</h3>
            </div>
            {topics.length > 0 && (
              <div className="flex items-center space-x-1">
                {['ALL', 'STRENGTHS', 'DEVELOPING', 'GAPS'].map((tf) => (
                  <button
                    key={tf}
                    onClick={() => setTopicFilter(tf)}
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${
                      topicFilter === tf
                        ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tf === 'ALL' ? 'All' : tf === 'STRENGTHS' ? 'Strengths' : tf === 'DEVELOPING' ? 'Developing' : 'Gaps'}
                  </button>
                ))}
              </div>
            )}
          </div>

          {topics.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400 border border-dashed border-slate-800/80 rounded-xl p-4">
              <BookOpen className="w-6 h-6 text-slate-600 mx-auto mb-2" />
              <span>No evaluated topic scores yet. Complete your first interview to track subject-by-subject competency breakdown.</span>
            </div>
          ) : filteredTopics.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-400">
              No topics in the selected category.
            </div>
          ) : (
            <div className="space-y-3">
              {filteredTopics.map((tm) => {
                const pct = Math.min(Math.max((tm.average_score / 10) * 100, 0), 100);
                const isGreen = tm.average_score >= 7.5;
                const isAmber = tm.average_score >= 5.0 && tm.average_score < 7.5;

                return (
                  <div key={tm.topic} className="space-y-1.5 p-3 rounded-xl bg-[#080d1a]/80 border border-slate-800/60 hover:border-slate-700/60 transition">
                    <div className="flex items-center justify-between text-xs">
                      <div className="font-semibold text-slate-200 flex items-center space-x-2">
                        <span>{tm.topic}</span>
                        <span className="text-[10px] text-slate-400 font-mono">({tm.questions_tested} Qs)</span>
                      </div>
                      <div className="flex items-center space-x-2 font-mono">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                          isGreen
                            ? 'bg-emerald-950/70 text-emerald-300 border border-emerald-800/50'
                            : isAmber
                            ? 'bg-amber-950/70 text-amber-300 border border-amber-800/50'
                            : 'bg-rose-950/70 text-rose-300 border border-rose-800/50'
                        }`}>
                          {tm.mastery_level}
                        </span>
                        <span className="font-bold text-white">{tm.average_score} / 10</span>
                      </div>
                    </div>
                    {/* Progress Bar */}
                    <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          isGreen ? 'bg-emerald-400' : isAmber ? 'bg-amber-400' : 'bg-rose-500'
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Targeted Practice Priorities */}
        <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1224] to-[#070c17] border border-slate-800/80">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Target className="w-4 h-4 text-violet-400" />
              <h3 className="text-sm font-bold text-white">Targeted Practice Priorities</h3>
            </div>
            <span className="text-xs text-slate-400">Actionable Feedback</span>
          </div>

          {(!rec.practice_priorities || rec.practice_priorities.length === 0) ? (
            <div className="py-8 text-center text-xs text-slate-400 border border-dashed border-slate-800/80 rounded-xl p-4">
              <CheckCircle2 className="w-6 h-6 text-emerald-400/70 mx-auto mb-2" />
              <span>
                {completedCount === 0
                  ? 'Complete an assessment to automatically identify priority practice areas.'
                  : 'Outstanding technical consistency! All evaluated topics meet or exceed the 6.0/10 readiness benchmark.'}
              </span>
            </div>
          ) : (
            <div className="space-y-3">
              {rec.practice_priorities.map((item) => (
                <div key={item.topic} className="p-3.5 rounded-xl bg-[#080d1a]/80 border border-slate-800/70 space-y-1.5 hover:border-slate-700/70 transition">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-slate-200">{item.topic}</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${
                      item.priority === 'high'
                        ? 'bg-rose-950/80 text-rose-300 border border-rose-800/60'
                        : 'bg-amber-950/80 text-amber-300 border border-amber-800/60'
                    }`}>
                      {item.priority} Priority
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">{item.reason}</p>
                  <p className="text-xs text-cyan-300 font-medium">
                    Recommended: {item.recommended_focus}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ======================================================================
          SECTION 9: COMPLETED INTERVIEW HISTORY & REPORTS
          ====================================================================== */}
      <div className="p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-[#0a1224] to-[#070c17] border border-slate-800/80 relative z-10">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <Calendar className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white">Completed Interview History</h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            {summary?.recent_history?.length || 0} Sessions on Record
          </span>
        </div>

        {(!summary?.recent_history || summary.recent_history.length === 0) ? (
          <div className="py-8 text-center text-xs text-slate-400 border border-dashed border-slate-800/80 rounded-xl p-6 space-y-3">
            <Calendar className="w-7 h-7 text-slate-600 mx-auto" />
            <div className="space-y-1">
              <span className="font-semibold text-slate-300 block text-sm">No Completed Assessments Yet</span>
              <p className="text-slate-400 max-w-md mx-auto text-xs leading-relaxed">
                Your completed mock interviews, official scorecards, and historical performance breakdowns will appear here once you finish your first assessment.
              </p>
            </div>
            <button
              onClick={() => onStartInterview && onStartInterview(profile.target_role || 'Associate Software Engineer')}
              className="mt-2 inline-flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-semibold text-xs transition shadow-md hover:scale-105 active:scale-95"
            >
              <Play className="w-3.5 h-3.5 fill-white" />
              <span>Launch First Mock Interview</span>
            </button>
          </div>
        ) : (
          <>
            {/* Desktop Table View */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="text-[11px] uppercase tracking-wider text-slate-400 bg-slate-900/60 border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">Date Completed</th>
                    <th className="py-3 px-4">Assessment Track</th>
                    <th className="py-3 px-4">Difficulty</th>
                    <th className="py-3 px-4">Score</th>
                    <th className="py-3 px-4">Rating</th>
                    <th className="py-3 px-4 text-right">Detailed Scorecard</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {summary.recent_history.map((item) => (
                    <tr key={item.session_id} className="hover:bg-slate-800/30 transition">
                      <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                        {new Date(item.completed_at).toLocaleDateString(undefined, {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                        })}
                      </td>
                      <td className="py-3 px-4 font-sans font-semibold text-slate-200">
                        {item.selected_role || item.interview_title}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                          item.difficulty_level === 'Advanced'
                            ? 'bg-violet-950/70 text-violet-300 border border-violet-800/50'
                            : item.difficulty_level === 'Intermediate'
                            ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-800/50'
                            : 'bg-emerald-950/70 text-emerald-300 border border-emerald-800/50'
                        }`}>
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
                          className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-cyan-950/70 hover:bg-cyan-900/80 text-cyan-300 border border-cyan-800/60 font-sans text-xs font-semibold transition hover:border-cyan-700 active:scale-95"
                        >
                          <span>View Report</span>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Card Stack */}
            <div className="sm:hidden space-y-3">
              {summary.recent_history.map((item) => (
                <div key={item.session_id} className="p-3.5 rounded-xl bg-slate-900/70 border border-slate-800/80 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-200 text-sm">{item.selected_role || item.interview_title}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                      item.difficulty_level === 'Advanced'
                        ? 'bg-violet-950/70 text-violet-300'
                        : item.difficulty_level === 'Intermediate'
                        ? 'bg-cyan-950/70 text-cyan-300'
                        : 'bg-emerald-950/70 text-emerald-300'
                    }`}>
                      {item.difficulty_level}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-slate-400 font-mono text-[11px]">
                    <span>Score: {item.overall_score} / 10 ({item.percentage_score}%)</span>
                    <span>{new Date(item.completed_at).toLocaleDateString()}</span>
                  </div>
                  <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300 font-sans">{item.performance_level}</span>
                    <Link
                      to={item.report_url}
                      className="inline-flex items-center space-x-1 text-cyan-300 font-semibold"
                    >
                      <span>View Scorecard</span>
                      <ChevronRight className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* ======================================================================
          SECTION 10: PROFILE & TRACK PREFERENCES MODAL
          ====================================================================== */}
      {showEditModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="target-profile-modal-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowEditModal(false);
          }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200"
        >
          <div className="bg-[#0c1424] border border-slate-700/80 rounded-3xl w-full max-w-lg p-6 sm:p-7 shadow-2xl space-y-5 text-slate-200 relative">
            <button
              onClick={() => setShowEditModal(false)}
              className="absolute top-5 right-5 p-1.5 rounded-xl bg-slate-800 text-slate-400 hover:text-white transition"
              aria-label="Close modal"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-xl bg-cyan-500/20 text-cyan-400 flex items-center justify-center border border-cyan-500/30">
                <Edit3 className="w-4 h-4" />
              </div>
              <div>
                <h3 id="target-profile-modal-title" className="text-base font-bold text-white">Target Track & Technical Profile</h3>
                <p className="text-xs text-slate-400">Calibrate the adaptive recommendation engine to your career track.</p>
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
                <label className="block font-semibold text-slate-300 mb-1.5">Technical Competencies & Skills</label>
                <div className="flex items-center space-x-2 mb-2">
                  <input
                    type="text"
                    value={newSkillInput}
                    onChange={(e) => setNewSkillInput(e.target.value)}
                    placeholder="e.g. React, SQL, DSA, System Design"
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
                    placeholder="e.g. Python, Java, C++, TypeScript"
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
