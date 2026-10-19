import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  Award,
  ArrowLeft,
  Calendar,
  Clock,
  Briefcase,
  AlertCircle,
  CheckCircle2,
  Sparkles,
  Zap,
  ChevronRight,
  FileText,
  Video,
  ExternalLink,
  Printer,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  RefreshCw,
  BookOpen,
  GraduationCap,
  Info,
  TrendingUp,
  Target
} from 'lucide-react';
import { getStudentPerformanceReport, getSessionPerformanceReport } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function StudentReport() {
  const { assignmentId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchReport = useCallback(async () => {
    if (!assignmentId) {
      setError('Assignment identifier is missing.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      let res;
      if (assignmentId.startsWith('sess_')) {
        res = await getSessionPerformanceReport(assignmentId);
      } else {
        res = await getStudentPerformanceReport(assignmentId);
        if (!res.success && (res.error?.includes('not found') || res.status === 404)) {
          const sessionFallback = await getSessionPerformanceReport(assignmentId);
          if (sessionFallback.success) {
            res = sessionFallback;
          }
        }
      }
      if (res.success && res.data) {
        setReport(res.data);
      } else {
        setError(res.error || 'Failed to load performance report.');
      }
    } catch (err) {
      setError(err.message || 'Error communicating with server.');
    } finally {
      setLoading(false);
    }
  }, [assignmentId]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const handlePrint = () => {
    window.print();
  };

  const getDifficultyBadge = (difficulty) => {
    const diff = (difficulty || '').toLowerCase();
    switch (diff) {
      case 'easy':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            Easy
          </span>
        );
      case 'hard':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
            Hard
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            Medium
          </span>
        );
    }
  };

  const getPerformanceBadge = (level) => {
    const lvl = (level || '').toLowerCase();
    if (lvl.includes('exceptional')) {
      return (
        <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center space-x-1.5 shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
          <span>Exceptional Mastery</span>
        </span>
      );
    }
    if (lvl.includes('proficient')) {
      return (
        <span className="px-3 py-1 rounded-full text-xs font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center space-x-1.5 shadow-sm">
          <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
          <span>Proficient Competency</span>
        </span>
      );
    }
    if (lvl.includes('satisfactory')) {
      return (
        <span className="px-3 py-1 rounded-full text-xs font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 flex items-center space-x-1.5 shadow-sm">
          <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
          <span>Satisfactory Baseline</span>
        </span>
      );
    }
    return (
      <span className="px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center space-x-1.5 shadow-sm">
        <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
        <span>Targeted Revision Required</span>
      </span>
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#070B14] text-slate-100 flex flex-col items-center justify-center p-4">
        <div className="p-8 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col items-center space-y-4 max-w-sm w-full text-center shadow-2xl">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
          <div>
            <h2 className="text-sm font-bold text-white mb-1">Compiling Performance Report</h2>
            <p className="text-xs text-slate-400">Aggregating topic mastery metrics and curated recommendations...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-[#070B14] text-slate-100 flex flex-col items-center justify-center p-4">
        <div className="p-8 rounded-2xl bg-slate-900/80 border border-slate-800 max-w-md w-full space-y-4 shadow-2xl">
          <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center mx-auto">
            <AlertCircle className="w-6 h-6 text-rose-400" />
          </div>
          <div className="text-center">
            <h2 className="text-base font-bold text-white mb-1">Report Unavailable</h2>
            <p className="text-xs text-slate-300 leading-relaxed mb-4">{error || 'Unable to retrieve interview report.'}</p>
          </div>
          <div className="flex items-center justify-center space-x-3 pt-2">
            <button
              onClick={fetchReport}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center space-x-1.5 border border-slate-700 transition"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry</span>
            </button>
            <Link
              to="/dashboard"
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center space-x-1.5 transition shadow"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Dashboard</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isPass = report.overall_score >= 6.0;

  return (
    <div className="min-h-screen bg-[#070B14] text-slate-100 flex flex-col selection:bg-cyan-500/30 report-container">
      {/* Print-specific style rules: renders with crisp white background and dark text without background graphics */}
      <style>{`
        @media print {
          @page {
            margin: 12mm 15mm 15mm 15mm;
            size: auto;
          }
          html, body {
            background-color: #ffffff !important;
            color: #0f172a !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          .min-h-screen {
            background-color: #ffffff !important;
            min-height: auto !important;
          }
          header, button, .print\\:hidden {
            display: none !important;
          }
          .print-header-banner {
            display: flex !important;
          }
          /* Card containers: clean white background, dark slate text, solid visible border */
          .bg-slate-900\\/60,
          .bg-slate-900\\/70,
          .bg-slate-900\\/80,
          .bg-slate-900\\/90,
          .bg-slate-900,
          .bg-slate-950\\/60,
          .bg-slate-950\\/70,
          .bg-slate-950\\/80,
          .bg-slate-950,
          .bg-gradient-to-br {
            background: #ffffff !important;
            background-color: #ffffff !important;
            border-color: #cbd5e1 !important;
            box-shadow: none !important;
            color: #0f172a !important;
            page-break-inside: avoid;
            break-inside: avoid;
          }
          /* Headings and body text */
          h1, h2, h3, h4, .text-white {
            color: #0f172a !important;
          }
          .text-slate-100, .text-slate-200, .text-slate-300 {
            color: #1e293b !important;
          }
          .text-slate-400, .text-slate-500 {
            color: #475569 !important;
          }
          .text-cyan-200, .text-cyan-300, .text-cyan-400 {
            color: #0369a1 !important;
          }
          .text-indigo-300, .text-indigo-400 {
            color: #4338ca !important;
          }
          .text-amber-300, .text-amber-400 {
            color: #b45309 !important;
          }
          .text-rose-300, .text-rose-400 {
            color: #be123c !important;
          }
          .text-emerald-300, .text-emerald-400 {
            color: #047857 !important;
          }
          .border-slate-800, .border-slate-800\\/80, .border-slate-800\\/90, .border-slate-800\\/60, .border-slate-700 {
            border-color: #cbd5e1 !important;
          }
        }
      `}</style>

      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-[#0a101f]/90 backdrop-blur-xl sticky top-0 z-30 shadow-md print:hidden">
        <div className="max-w-6xl mx-auto px-4 py-3 sm:py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-600 via-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-cyan-600/20 ring-1 ring-cyan-400/30">
              <Award className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-sm font-bold text-white">Student Performance Report</h1>
                <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/60">
                  VFSTR
                </span>
              </div>
              <p className="text-[11px] text-slate-400">{report.interview_title}</p>
            </div>
          </div>

          <div className="flex items-center space-x-2.5">
            <button
              onClick={handlePrint}
              className="px-3.5 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-750 text-slate-200 hover:text-white border border-slate-700/80 text-xs font-semibold flex items-center space-x-1.5 transition-all shadow-sm"
              title="Print or Save as PDF"
            >
              <Printer className="w-3.5 h-3.5 text-cyan-400" />
              <span className="hidden sm:inline">Print / Save PDF</span>
            </button>
            <Link
              to="/dashboard"
              className="px-4 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-700 text-white text-xs font-semibold flex items-center space-x-1.5 border border-indigo-500/30 transition shadow"
            >
              <ArrowLeft className="w-3.5 h-3.5 text-indigo-400" />
              <span>Back to Dashboard</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Report Body */}
      <main className="max-w-6xl mx-auto px-4 py-8 w-full flex-1 space-y-8">

        {/* Print-Only Official Academic Header Banner */}
        <div className="hidden print-header-banner p-4 mb-4 border-b-2 border-slate-800 justify-between items-center text-slate-900 bg-white">
          <div>
            <h1 className="text-lg font-extrabold tracking-tight">VIGNAN'S FOUNDATION FOR SCIENCE, TECHNOLOGY AND RESEARCH (VFSTR)</h1>
            <p className="text-xs font-semibold text-slate-700">Adaptive Placement Mock Interview — Official Performance Audit Report</p>
          </div>
          <div className="text-right text-xs text-slate-600 font-mono">
            <div>Candidate: <strong>{report.student_registration_number}</strong></div>
            <div>Generated: {new Date(report.completed_at).toLocaleDateString()}</div>
          </div>
        </div>

        {/* Executive Overview Hero Card */}
        <section className="p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-[#0c1326] via-[#09101f] to-[#070b14] border border-slate-800/90 relative overflow-hidden shadow-2xl">
          <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-80 h-80 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none" />

          <div className="relative z-10 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
            <div className="space-y-3 max-w-2xl">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-mono font-bold px-3 py-1 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                  Candidate ID: {report.student_registration_number}
                </span>
                {report.selected_role && (
                  <span className="text-xs font-semibold px-3 py-1 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 flex items-center space-x-1">
                    <Briefcase className="w-3.5 h-3.5 text-indigo-400" />
                    <span>{report.selected_role}</span>
                  </span>
                )}
                {getPerformanceBadge(report.performance_level)}
              </div>

              <h2 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight">
                Placement Interview Evaluation Audit
              </h2>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                {report.summary_feedback}
              </p>

              <div className="flex flex-wrap items-center gap-4 pt-2 text-xs text-slate-400">
                <div className="flex items-center space-x-1.5">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  <span>Completed: {new Date(report.completed_at).toLocaleDateString()} at {new Date(report.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div className="flex items-center space-x-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Evaluator Mode: {report.evaluator_mode}</span>
                </div>
              </div>
            </div>

            {/* Score Metric Circular/Box Widget */}
            <div className="flex items-center space-x-4 p-5 rounded-2xl bg-slate-950/70 border border-slate-800/90 shadow-inner shrink-0 self-stretch sm:self-auto justify-around sm:justify-start">
              <div className="text-right">
                <div className="text-[11px] uppercase font-bold text-slate-400 tracking-wider">Overall Score</div>
                <div className="text-xs font-semibold text-cyan-300">{report.percentage_score}% Mastery</div>
              </div>
              <div
                className={`w-20 h-20 rounded-2xl flex flex-col items-center justify-center font-extrabold text-2xl border shadow-lg ${
                  isPass
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-emerald-500/10'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/30 shadow-amber-500/10'
                }`}
              >
                <span>{report.overall_score}</span>
                <span className="text-[10px] text-slate-400 font-normal">/ 10.0</span>
              </div>
            </div>
          </div>

          {/* Adaptive Difficulty Progression Path */}
          {report.difficulty_progression && report.difficulty_progression.length > 0 && (
            <div className="mt-6 pt-6 border-t border-slate-800/80 relative z-10">
              <div className="text-xs font-bold text-slate-300 mb-3 flex items-center space-x-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Adaptive Difficulty Progression Path</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {report.difficulty_progression.map((diff, idx) => (
                  <React.Fragment key={idx}>
                    <div className="flex items-center space-x-2 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-mono">
                      <span className="text-slate-400 font-medium">Q{idx + 1}:</span>
                      {getDifficultyBadge(diff)}
                    </div>
                    {idx < report.difficulty_progression.length - 1 && (
                      <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Section 1: Topic-Wise Mastery Breakdown & Evidence Limits */}
        <section className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h3 className="text-base font-bold text-white flex items-center space-x-2">
                <Target className="w-4 h-4 text-cyan-400" />
                <span>Topic-Wise Mastery Matrix</span>
              </h3>
              <p className="text-xs text-slate-400">
                Evaluation results aggregated by technical domain with sample size honesty indicators.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {report.topic_breakdown && report.topic_breakdown.length > 0 ? (
              report.topic_breakdown.map((t, idx) => {
                const pct = Math.round((t.average_score / 10) * 100);
                const isWeak = t.average_score < 5.0;
                const isModerate = t.average_score >= 5.0 && t.average_score < 7.0;

                return (
                  <div
                    key={idx}
                    className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition flex flex-col justify-between space-y-4 shadow-sm"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="space-y-1">
                          <h4 className="text-sm font-bold text-white flex items-center space-x-2">
                            <span>{t.topic}</span>
                          </h4>
                          <div className="flex items-center space-x-2 text-[11px] text-slate-400">
                            <span>{t.questions_tested} {t.questions_tested === 1 ? 'question tested' : 'questions tested'}</span>
                            <span>•</span>
                            <span className="font-mono">Min: {t.min_score} / Max: {t.max_score}</span>
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <span
                            className={`text-base font-bold font-mono ${
                              isWeak ? 'text-rose-400' : isModerate ? 'text-amber-400' : 'text-emerald-400'
                            }`}
                          >
                            {t.average_score}
                          </span>
                          <span className="text-xs text-slate-500 font-normal"> / 10</span>
                        </div>
                      </div>

                      {/* Visual Score Bar */}
                      <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800 my-2">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            isWeak ? 'bg-rose-500' : isModerate ? 'bg-amber-400' : 'bg-emerald-400'
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>

                    {/* Evidence Level Note & Honesty Indicator */}
                    <div className="pt-2 border-t border-slate-800/60 flex items-start space-x-2">
                      {t.is_limited_evidence ? (
                        <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-200/90 leading-relaxed flex items-start space-x-2 w-full">
                          <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                          <div>
                            <span className="font-semibold block text-amber-300">Limited Evidence Warning:</span>
                            <span>{t.evidence_note}</span>
                          </div>
                        </div>
                      ) : (
                        <div className="text-[11px] text-slate-400 flex items-center space-x-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                          <span>{t.evidence_note}</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            ) : (
              <p className="text-xs text-slate-400">No topic performance data available for this interview.</p>
            )}
          </div>
        </section>

        {/* Section 2: Actionable Growth Priorities */}
        <section className="space-y-4">
          <div>
            <h3 className="text-base font-bold text-white flex items-center space-x-2">
              <Zap className="w-4 h-4 text-amber-400" />
              <span>Actionable Preparation Priorities</span>
            </h3>
            <p className="text-xs text-slate-400">
              Targeted revision priorities derived from actual evaluated weaknesses and rubric feedback.
            </p>
          </div>

          <div className="space-y-3">
            {report.actionable_priorities && report.actionable_priorities.length > 0 ? (
              report.actionable_priorities.map((item, idx) => {
                const isHigh = item.priority === 'high';
                return (
                  <div
                    key={idx}
                    className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800/90 space-y-3 hover:border-slate-700/80 transition shadow-sm"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center space-x-2">
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                            isHigh
                              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                              : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                          }`}
                        >
                          {item.priority} Priority
                        </span>
                        <h4 className="text-sm font-bold text-white">{item.topic}</h4>
                      </div>
                      <span className="text-xs font-mono text-slate-400">
                        Evaluated Score: <strong className="text-slate-200">{item.average_score}/10</strong>
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs text-slate-300 leading-relaxed">
                      <strong className="text-cyan-300 block mb-0.5">Evaluation Justification:</strong>
                      {item.reason}
                    </div>

                    {item.actionable_steps && item.actionable_steps.length > 0 && (
                      <div className="space-y-1.5 pt-1">
                        <span className="text-[11px] uppercase font-bold text-slate-400 block tracking-wider">
                          Recommended Action Steps:
                        </span>
                        <ul className="space-y-1 text-xs text-slate-300">
                          {item.actionable_steps.map((step, sIdx) => (
                            <li key={sIdx} className="flex items-start space-x-2">
                              <span className="text-indigo-400 font-bold">•</span>
                              <span>{step}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="p-5 rounded-2xl bg-emerald-950/20 border border-emerald-900/30 text-xs text-emerald-300 flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>No high-priority weaknesses detected. High technical precision demonstrated across all evaluated topics!</span>
              </div>
            )}
          </div>
        </section>

        {/* Section 3: Verified Learning Video Recommendations */}
        <section className="space-y-4">
          <div>
            <h3 className="text-base font-bold text-white flex items-center space-x-2">
              <Video className="w-4 h-4 text-indigo-400" />
              <span>Personalized Video Recommendations</span>
            </h3>
            <p className="text-xs text-slate-400">
              Verified educational resources mapped directly to your performance evidence for interview preparation.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {report.video_recommendations && report.video_recommendations.length > 0 ? (
              report.video_recommendations.map((vid, idx) => (
                <div
                  key={idx}
                  className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800/90 hover:border-indigo-500/40 transition flex flex-col justify-between space-y-4 group shadow-sm"
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        {vid.topic}
                      </span>
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                        <ShieldCheck className="w-3 h-3 text-emerald-400 mr-1" />
                        <span>Verified Resource</span>
                      </span>
                    </div>

                    <h4 className="text-sm font-bold text-white group-hover:text-cyan-200 transition-colors leading-snug">
                      {vid.title}
                    </h4>

                    <div className="text-xs text-slate-400 flex items-center space-x-2">
                      <span>Provider: <strong className="text-slate-300">{vid.provider}</strong></span>
                      <span>•</span>
                      <span className="capitalize">{vid.difficulty_level} Level</span>
                    </div>

                    <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-[11px] text-slate-300 leading-relaxed">
                      <strong className="text-amber-300 block mb-0.5">Why this was recommended for you:</strong>
                      {vid.reason}
                    </div>
                  </div>

                  <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between">
                    <span className="text-[11px] text-slate-500 font-mono">
                      Status: <strong className="text-slate-400 font-normal">Not Viewed (Recommended)</strong>
                    </span>

                    <a
                      href={vid.video_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center space-x-1.5 transition shadow shadow-indigo-600/20 print:hidden"
                    >
                      <span>Watch Tutorial</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-400">No specific video recommendations generated for this session.</p>
            )}
          </div>
        </section>

        {/* Section 4: Question-by-Question Response Audit */}
        <section className="space-y-4">
          <div>
            <h3 className="text-base font-bold text-white flex items-center space-x-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              <span>Question-by-Question Response Audit</span>
            </h3>
            <p className="text-xs text-slate-400">
              Detailed breakdown of prompt, submitted candidate response, evaluator feedback, and rubric score.
            </p>
          </div>

          <div className="space-y-4">
            {report.responses && report.responses.length > 0 ? (
              report.responses.map((item, idx) => (
                <div
                  key={idx}
                  className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 space-y-3.5 shadow-sm"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-mono font-bold text-cyan-300">Question {item.question_index}</span>
                        <span className="text-xs text-slate-600">•</span>
                        <span className="text-xs text-slate-300 font-semibold">{item.topic}</span>
                        {getDifficultyBadge(item.difficulty)}
                      </div>
                      <p className="text-xs sm:text-sm text-white font-medium leading-relaxed">
                        {item.question_text}
                      </p>
                    </div>

                    <div className="text-right shrink-0 bg-slate-950/80 px-3 py-1.5 rounded-xl border border-slate-800">
                      <span className="text-sm font-bold text-cyan-300 font-mono">
                        {item.score ?? item.evaluation_score}
                      </span>
                      <span className="text-xs text-slate-500"> / 10</span>
                    </div>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/60 text-xs font-mono text-slate-300 leading-relaxed overflow-x-auto">
                    <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">Your Submitted Response:</div>
                    {item.answer_text}
                  </div>

                  <div className="p-3 rounded-xl bg-indigo-950/20 border border-indigo-900/30 text-xs text-slate-300 leading-relaxed">
                    <strong className="text-indigo-300 block mb-0.5">Evaluator Rubric Feedback:</strong>
                    {item.feedback}
                  </div>

                  {item.difficulty_adjustment_rationale && (
                    <div className="text-[11px] text-slate-400 font-mono flex items-center space-x-1.5">
                      <Zap className="w-3 h-3 text-amber-400 shrink-0" />
                      <span>Adaptive Transition: {item.difficulty_adjustment_rationale}</span>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-400">No question response audit items recorded.</p>
            )}
          </div>
        </section>

        {/* Assessment Disclaimer Footer */}
        <footer className="p-4 rounded-2xl bg-slate-950/80 border border-slate-800 text-slate-400 text-xs leading-relaxed space-y-1.5 print:mt-8">
          <div className="font-semibold text-slate-300 flex items-center space-x-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-indigo-400" />
            <span>Algorithmic Assessment Disclaimer</span>
          </div>
          <p>{report.disclaimer}</p>
        </footer>

      </main>
    </div>
  );
}
