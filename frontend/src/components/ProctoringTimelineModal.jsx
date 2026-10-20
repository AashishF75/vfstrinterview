import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  ShieldCheck, 
  X, 
  Clock, 
  Eye, 
  AlertCircle, 
  CheckCircle2, 
  Check, 
  RefreshCw,
  FileText,
  UserCheck,
  AlertTriangle
} from 'lucide-react';
import { getSessionProctoringTimeline, updateSessionProctoringReview } from '../api/client';

export default function ProctoringTimelineModal({ sessionId, onClose }) {
  const isMountedRef = useRef(true);
  const saveTimeoutRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // Review status submission state
  const [reviewStatus, setReviewStatus] = useState('unreviewed');
  const [reviewNotes, setReviewNotes] = useState('');
  const [savingReview, setSavingReview] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  const fetchTimeline = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setSaveError(null);

    try {
      const res = await getSessionProctoringTimeline(sessionId);
      if (!isMountedRef.current) return;

      if (res && res.success && res.data) {
        setData(res.data);
        setReviewStatus(res.data.review_status || 'unreviewed');
        setReviewNotes(res.data.review_notes || '');
      } else {
        setError(res?.error || 'Failed to load proctoring timeline');
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || 'Network error occurred while loading proctoring timeline');
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [sessionId]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  const handleSaveReview = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (savingReview) return; // Prevent duplicate concurrent saves

    setSavingReview(true);
    setSaveSuccess(false);
    setSaveError(null);

    try {
      const res = await updateSessionProctoringReview(sessionId, reviewStatus, reviewNotes);
      if (!isMountedRef.current) return;

      if (res && res.success && res.data) {
        setSaveSuccess(true);
        // Only update audit metadata confirmed by server response, DO NOT fabricate
        setData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            review_status: res.data.review_status || reviewStatus,
            review_notes: res.data.review_notes !== undefined ? res.data.review_notes : reviewNotes,
            reviewed_at: res.data.reviewed_at || prev.reviewed_at,
            reviewed_by_email: res.data.reviewed_by_email || prev.reviewed_by_email,
          };
        });
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
        }
        saveTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current) {
            setSaveSuccess(false);
          }
        }, 4000);
      } else {
        // Display error on failure and preserve unsaved notes
        setSaveError(res?.error || 'Failed to save review decision');
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      setSaveError(err?.message || 'Network error occurred while saving review decision');
    } finally {
      if (isMountedRef.current) {
        setSavingReview(false);
      }
    }
  };

  const getEventBadge = (type) => {
    const t = (type || '').toLowerCase();
    if (t.includes('tab')) {
      return 'bg-amber-950/60 text-amber-300 border-amber-800/60';
    }
    if (t.includes('absent')) {
      return 'bg-rose-950/60 text-rose-300 border-rose-800/60';
    }
    if (t.includes('multiple')) {
      return 'bg-purple-950/60 text-purple-300 border-purple-800/60';
    }
    if (t.includes('connected') || t.includes('restored') || t.includes('normal')) {
      return 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60';
    }
    return 'bg-slate-800 text-slate-300 border-slate-700';
  };

  const getReviewStatusBadge = (status) => {
    switch (status) {
      case 'cleared':
        return (
          <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>Cleared (No Misconduct)</span>
          </span>
        );
      case 'flagged':
        return (
          <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-rose-950/80 text-rose-300 border border-rose-800/80 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-rose-400" />
            <span>Flagged for Follow-up</span>
          </span>
        );
      case 'unreviewed':
      default:
        return (
          <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1">
            <Clock className="w-3 h-3 text-slate-400" />
            <span>Unreviewed</span>
          </span>
        );
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="proctoring-modal-title"
      className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4"
    >
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 sm:p-7 shadow-2xl space-y-6 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 flex items-center justify-center">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="proctoring-modal-title" className="text-lg font-bold text-white">
                  Proctoring Telemetry Timeline
                </h2>
                {data?.summary?.integrity_status === 'normal' && (
                  <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
                    Normal Signals
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
                Candidate: <span className="font-mono text-indigo-300 font-semibold">{data?.student_registration_number || 'Candidate'}</span> • Session: <code className="text-slate-300 font-mono text-[11px]">{sessionId}</code>
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              id="proctoring-refresh-btn"
              onClick={fetchTimeline}
              disabled={loading}
              title="Refresh timeline"
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              id="proctoring-close-btn"
              onClick={onClose}
              title="Close modal"
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="space-y-6 overflow-y-auto flex-1 pr-1">
          {loading ? (
            <div className="py-16 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-3">
              <RefreshCw className="w-7 h-7 animate-spin text-indigo-400" />
              <span>Loading proctoring events and integrity telemetry...</span>
            </div>
          ) : error ? (
            <div className="p-5 rounded-xl bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center space-x-2.5">
                <AlertCircle className="w-5 h-5 shrink-0 text-rose-400" />
                <span>{error}</span>
              </div>
              <button
                id="proctoring-retry-btn"
                onClick={fetchTimeline}
                className="px-3.5 py-1.5 bg-rose-900/80 hover:bg-rose-850 text-white rounded-lg text-xs font-semibold flex items-center space-x-1.5 self-start sm:self-auto transition shrink-0"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retry</span>
              </button>
            </div>
          ) : data ? (
            <>
              {/* Summary Metric Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Tab Hidden Events</span>
                  <div className="text-base font-bold text-white flex items-baseline gap-1">
                    <span>{data.summary?.total_tab_hidden_count ?? 0}</span>
                    <span className="text-[10px] font-normal text-slate-400">
                      ({data.summary?.total_tab_hidden_duration_seconds ?? 0}s)
                    </span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Face Absences</span>
                  <div className="text-base font-bold text-white flex items-baseline gap-1">
                    <span>{data.summary?.total_face_absent_count ?? 0}</span>
                    <span className="text-[10px] font-normal text-slate-400">
                      ({data.summary?.total_face_absent_duration_seconds ?? 0}s)
                    </span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Multiple Faces</span>
                  <div className="text-base font-bold text-white">
                    {data.summary?.total_multiple_faces_count ?? 0}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Stream Interruptions</span>
                  <div className="text-base font-bold text-white">
                    {data.summary?.stream_disruptions_count ?? 0}
                  </div>
                </div>
              </div>

              {/* Informative Neutral Policy Alert */}
              <div className="p-3.5 rounded-xl bg-slate-950/50 border border-slate-800 text-[11px] text-slate-400 leading-relaxed flex items-start space-x-2">
                <ShieldCheck className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-slate-300 font-semibold">Neutral Telemetry Review Notice: </strong>
                  <span>{data.summary?.disclaimer || 'Proctoring signals are passive browser-side telemetry intended solely for human evaluation. Network fluctuations, camera angles, or background movements do not constitute automatic proof of academic misconduct.'}</span>
                </div>
              </div>

              {/* Chronological Timeline */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center space-x-1.5">
                    <Clock className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Chronological Event Sequence ({data.timeline?.length ?? 0} Recorded)</span>
                  </h3>
                  <span className="text-[10px] font-mono text-slate-500">Sorted by timestamp (ascending)</span>
                </div>

                {(!data.timeline || data.timeline.length === 0) ? (
                  <div className="py-10 text-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-xl space-y-1">
                    <CheckCircle2 className="w-6 h-6 text-emerald-500/60 mx-auto mb-1" />
                    <p className="font-semibold text-slate-400">Clean Session Telemetry</p>
                    <p className="text-[11px]">No proctoring anomalies or telemetry events were recorded for this session.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.timeline.map((evt) => (
                      <div
                        key={evt.event_id}
                        className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs hover:border-slate-700 transition"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center space-x-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getEventBadge(evt.event_type)}`}>
                              {evt.event_type}
                            </span>
                            <span className="text-slate-200 font-medium">{evt.description}</span>
                          </div>
                        </div>

                        <div className="flex items-center space-x-3 text-[11px] font-mono text-slate-400 shrink-0">
                          {evt.duration_seconds ? (
                            <span className="text-indigo-300 font-semibold">
                              Duration: {Number(evt.duration_seconds).toFixed(1)}s
                            </span>
                          ) : null}
                          <span>
                            {evt.server_timestamp ? new Date(evt.server_timestamp).toLocaleTimeString() : 'N/A'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Administrative Review Form & Persistence */}
              <div className="p-4 sm:p-5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                  <div className="space-y-0.5">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-400 flex items-center space-x-1.5">
                      <UserCheck className="w-4 h-4 text-indigo-400" />
                      <span>Administrative Integrity Review Decision</span>
                    </h4>
                    <p className="text-[11px] text-slate-400">
                      Record faculty/department-admin review findings. Saved decisions persist in the database.
                    </p>
                  </div>
                  <div>
                    {getReviewStatusBadge(data.review_status || 'unreviewed')}
                  </div>
                </div>

                {data.reviewed_at && (
                  <div className="text-[11px] text-slate-400 flex flex-wrap items-center gap-1.5 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-slate-300 font-medium">Last Recorded Review:</span>
                    <span>by</span>
                    <span className="font-mono text-indigo-300 font-semibold">{data.reviewed_by_email || 'Authorized Reviewer'}</span>
                    <span>on</span>
                    <span className="text-slate-300">{new Date(data.reviewed_at).toLocaleString()}</span>
                  </div>
                )}

                {/* Save Feedback Alerts */}
                {saveSuccess && (
                  <div className="p-3 rounded-xl bg-emerald-950/60 border border-emerald-800 text-xs text-emerald-300 flex items-center space-x-2 animate-fadeIn">
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                    <span className="font-semibold">Review decision and rationale successfully persisted.</span>
                  </div>
                )}

                {saveError && (
                  <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800 text-xs text-rose-300 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
                      <span>{saveError}</span>
                    </div>
                    <button
                      type="button"
                      onClick={handleSaveReview}
                      disabled={savingReview}
                      className="px-2.5 py-1 bg-rose-900/80 hover:bg-rose-800 text-white rounded text-[11px] font-semibold self-start sm:self-auto transition shrink-0"
                    >
                      Retry Save
                    </button>
                  </div>
                )}

                <form onSubmit={handleSaveReview} className="space-y-3">
                  <div>
                    <label htmlFor="proctoring-status-select" className="text-[11px] text-slate-300 font-semibold block mb-1">
                      Integrity Decision Status
                    </label>
                    <select
                      id="proctoring-status-select"
                      value={reviewStatus}
                      onChange={(e) => setReviewStatus(e.target.value)}
                      className="w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs p-2.5 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                    >
                      <option value="unreviewed">Unreviewed (Pending Formal Review)</option>
                      <option value="cleared">Cleared (Signals Reviewed — No Misconduct Found)</option>
                      <option value="flagged">Flagged for Follow-up (Potential Integrity Concern)</option>
                    </select>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label htmlFor="proctoring-notes-textarea" className="text-[11px] text-slate-300 font-semibold">
                        Reviewer Rationale & Observations (Optional)
                      </label>
                      <span className={`text-[10px] font-mono ${reviewNotes.length > 2000 ? 'text-rose-400 font-bold' : 'text-slate-500'}`}>
                        {reviewNotes.length} / 2000 chars
                      </span>
                    </div>
                    <textarea
                      id="proctoring-notes-textarea"
                      rows={3}
                      maxLength={2000}
                      value={reviewNotes}
                      onChange={(e) => setReviewNotes(e.target.value)}
                      placeholder="Enter neutral, objective rationale explaining the review outcome (e.g., 'Examined tab switch; brief 3s lapse during question transition, cleared')..."
                      className="w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs p-2.5 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 placeholder-slate-500 resize-y"
                    />
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <p className="text-[10px] text-slate-500">
                      Submissions are logged with your reviewer email and timestamp for institutional audit compliance.
                    </p>
                    <button
                      id="proctoring-save-btn"
                      type="submit"
                      disabled={savingReview || reviewNotes.length > 2000}
                      className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition disabled:opacity-50 shrink-0 flex items-center space-x-1.5"
                    >
                      {savingReview ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Saving...</span>
                        </>
                      ) : (
                        <>
                          <Check className="w-3.5 h-3.5" />
                          <span>Save Review Decision</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
