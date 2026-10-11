import React, { useState, useEffect, useCallback } from 'react';
import { 
  ShieldCheck, 
  X, 
  Clock, 
  Eye, 
  AlertCircle, 
  CheckCircle2, 
  UserX, 
  Users, 
  Layers, 
  Check, 
  RefreshCw,
  FileText
} from 'lucide-react';
import { getSessionProctoringTimeline, updateSessionProctoringReview } from '../api/client';

export default function ProctoringTimelineModal({ sessionId, onClose }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // Review status submission state
  const [reviewStatus, setReviewStatus] = useState('unreviewed');
  const [reviewNotes, setReviewNotes] = useState('');
  const [savingReview, setSavingReview] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const fetchTimeline = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);

    const res = await getSessionProctoringTimeline(sessionId);
    if (res.success) {
      setData(res.data);
      setReviewStatus(res.data.review_status || 'unreviewed');
      setReviewNotes(res.data.review_notes || '');
    } else {
      setError(res.error || 'Failed to load proctoring timeline');
    }
    setLoading(false);
  }, [sessionId]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  const handleSaveReview = async (e) => {
    e.preventDefault();
    setSavingReview(true);
    setSaveSuccess(false);

    const res = await updateSessionProctoringReview(sessionId, reviewStatus, reviewNotes);
    if (res.success) {
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } else {
      setError(res.error || 'Failed to save review');
    }
    setSavingReview(false);
  };

  const getEventBadge = (type) => {
    if (type.includes('tab')) {
      return 'bg-amber-950/60 text-amber-300 border-amber-800/60';
    }
    if (type.includes('absent')) {
      return 'bg-rose-950/60 text-rose-300 border-rose-800/60';
    }
    if (type.includes('multiple')) {
      return 'bg-purple-950/60 text-purple-300 border-purple-800/60';
    }
    if (type.includes('connected') || type.includes('restored') || type.includes('normal')) {
      return 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60';
    }
    return 'bg-slate-800 text-slate-300 border-slate-700';
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 sm:p-7 shadow-2xl space-y-6 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 flex items-center justify-center">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white">Proctoring Telemetry Timeline</h2>
                {data?.summary?.integrity_status === 'normal' && (
                  <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
                    Normal
                  </span>
                )}
                {data?.summary?.integrity_status === 'notice' && (
                  <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-800/80">
                    Notice
                  </span>
                )}
                {data?.summary?.integrity_status === 'review_suggested' && (
                  <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-rose-950/80 text-rose-300 border border-rose-800/80">
                    Review Suggested
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Candidate: <span className="font-mono text-indigo-300">{data?.student_registration_number || 'Candidate'}</span> • Session: <code className="text-slate-300 font-mono text-[11px]">{sessionId}</code>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="space-y-6 overflow-y-auto flex-1 pr-1">
          {loading ? (
            <div className="py-12 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
              <span>Loading proctoring events...</span>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : (
            <>
              {/* Summary Metric Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Tab Hidden Events</span>
                  <div className="text-base font-bold text-white flex items-baseline gap-1">
                    <span>{data.summary.total_tab_hidden_count}</span>
                    <span className="text-[10px] font-normal text-slate-400">
                      ({data.summary.total_tab_hidden_duration_seconds}s)
                    </span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Face Absences</span>
                  <div className="text-base font-bold text-white flex items-baseline gap-1">
                    <span>{data.summary.total_face_absent_count}</span>
                    <span className="text-[10px] font-normal text-slate-400">
                      ({data.summary.total_face_absent_duration_seconds}s)
                    </span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Multiple Faces</span>
                  <div className="text-base font-bold text-white">
                    {data.summary.total_multiple_faces_count}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Stream Interruptions</span>
                  <div className="text-base font-bold text-white">
                    {data.summary.stream_disruptions_count}
                  </div>
                </div>
              </div>

              {/* Informative Policy Alert */}
              <div className="p-3 rounded-xl bg-slate-950/50 border border-slate-800 text-[11px] text-slate-400 leading-relaxed">
                <strong className="text-slate-300">Reviewer Notice: </strong>
                {data.summary.disclaimer}
              </div>

              {/* Chronological Timeline */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider text-slate-300">
                  Event Sequence ({data.timeline.length} Recorded)
                </h3>

                {data.timeline.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-xl">
                    No proctoring anomalies or telemetry events recorded for this session.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.timeline.map((evt) => (
                      <div
                        key={evt.event_id}
                        className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center space-x-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getEventBadge(evt.event_type)}`}>
                              {evt.event_type}
                            </span>
                            <span className="text-slate-300 font-medium">{evt.description}</span>
                          </div>
                        </div>

                        <div className="flex items-center space-x-3 text-[11px] font-mono text-slate-400 shrink-0">
                          {evt.duration_seconds && (
                            <span className="text-indigo-300">
                              Duration: {evt.duration_seconds.toFixed(1)}s
                            </span>
                          )}
                          <span>{new Date(evt.server_timestamp).toLocaleTimeString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Administrative Review Form */}
              <form onSubmit={handleSaveReview} className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider text-indigo-400">
                    Administrator Review Decision
                  </h4>
                  {saveSuccess && (
                    <span className="text-xs text-emerald-400 font-medium flex items-center space-x-1 animate-pulse">
                      <Check className="w-3.5 h-3.5" />
                      <span>Review Decision Saved</span>
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="text-[11px] text-slate-400 block mb-1">Integrity Status</label>
                    <select
                      value={reviewStatus}
                      onChange={(e) => setReviewStatus(e.target.value)}
                      className="w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs p-2 focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="unreviewed">Unreviewed</option>
                      <option value="cleared">Cleared (No Misconduct)</option>
                      <option value="flagged">Flagged for Follow-up</option>
                    </select>
                  </div>

                  <div className="sm:col-span-2">
                    <label className="text-[11px] text-slate-400 block mb-1">Reviewer Justification / Notes</label>
                    <input
                      type="text"
                      value={reviewNotes}
                      onChange={(e) => setReviewNotes(e.target.value)}
                      placeholder="Optional notes explaining review outcome..."
                      className="w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs p-2 focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={savingReview}
                    className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow transition disabled:opacity-50"
                  >
                    {savingReview ? 'Saving Decision...' : 'Save Decision'}
                  </button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
