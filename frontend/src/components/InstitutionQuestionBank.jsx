import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  FileText,
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Search,
  RefreshCw,
  X,
  Check,
  FolderOpen,
  Database,
  Building2,
  Tag
} from 'lucide-react';
import {
  previewQuestionFile,
  saveConfirmedQuestions,
  getInstitutionQuestions
} from '../api/client';

export default function InstitutionQuestionBank({ user }) {
  // Stored questions list state
  const [questions, setQuestions] = useState([]);
  const [totalQuestions, setTotalQuestions] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState('');
  const [topicFilter, setTopicFilter] = useState('');
  const [difficultyFilter, setDifficultyFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  // Upload & Preview Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [defaultTopic, setDefaultTopic] = useState('Computer Science');
  const [targetRole, setTargetRole] = useState('Software Development Engineer');
  const [isParsing, setIsParsing] = useState(false);
  const [parseError, setParseError] = useState(null);

  // Preview Questions State
  const [previewData, setPreviewData] = useState(null);
  const [editableQuestions, setEditableQuestions] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(null);
  const fileInputRef = useRef(null);

  // Load stored questions
  const loadQuestions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        skip: page * pageSize,
        limit: pageSize,
      };
      if (searchQuery.trim()) params.search = searchQuery.trim();
      if (topicFilter) params.topic = topicFilter;
      if (difficultyFilter) params.difficulty = difficultyFilter;
      if (roleFilter) params.role = roleFilter;

      const res = await getInstitutionQuestions(params);
      if (res.success) {
        setQuestions(res.data.items || []);
        setTotalQuestions(res.data.total || 0);
      } else {
        setError(res.error || 'Failed to fetch question bank');
      }
    } catch (err) {
      setError(err.message || 'An error occurred loading questions');
    } finally {
      setLoading(false);
    }
  }, [page, searchQuery, topicFilter, difficultyFilter, roleFilter]);

  useEffect(() => {
    loadQuestions();
  }, [loadQuestions]);

  // Handle file selection
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setParseError(null);
      setPreviewData(null);
      setEditableQuestions([]);
      setSaveSuccess(null);
    }
  };

  // Trigger parsing and preview
  const handleParsePreview = async () => {
    if (!selectedFile) {
      setParseError('Please select a file to parse');
      return;
    }
    setIsParsing(true);
    setParseError(null);
    setSaveSuccess(null);

    const res = await previewQuestionFile(selectedFile, defaultTopic);
    setIsParsing(false);

    if (res.success) {
      setPreviewData(res.data);
      const mapped = (res.data.questions || []).map((q, idx) => ({
        ...q,
        localId: q.temp_id || `temp-${idx}`,
        validation_errors: [...(q.validation_errors || [])],
      }));
      setEditableQuestions(mapped);
    } else {
      setParseError(res.error || 'Could not parse questions from uploaded file.');
    }
  };

  // Handle inline question editing
  const updateQuestionField = (index, field, value) => {
    setEditableQuestions((prev) => {
      const next = [...prev];
      const target = { ...next[index], [field]: value };

      const errors = [];
      if (!target.question_text || target.question_text.trim().length < 10) {
        errors.push('Question prompt is too short (minimum 10 characters required).');
      }
      if (!target.topic || !target.topic.trim()) {
        errors.push('Topic is required.');
      }
      target.validation_errors = errors;
      target.is_valid = errors.length === 0;

      next[index] = target;
      return next;
    });
  };

  // Remove a question from preview
  const removeQuestion = (index) => {
    setEditableQuestions((prev) => prev.filter((_, idx) => idx !== index));
  };

  // Save confirmed questions
  const handleConfirmSave = async () => {
    if (editableQuestions.length === 0) {
      setParseError('No questions to save.');
      return;
    }

    const invalidQuestions = editableQuestions.filter((q) => !q.is_valid);
    if (invalidQuestions.length > 0) {
      setParseError(`Please correct or remove the ${invalidQuestions.length} invalid question(s) before confirming.`);
      return;
    }

    setIsSaving(true);
    setParseError(null);

    const payload = {
      role: targetRole || previewData?.detected_role || null,
      target_department: user?.department || null,
      questions: editableQuestions.map((q) => ({
        temp_id: q.localId,
        question_text: q.question_text.trim(),
        question_type: q.question_type || 'conceptual',
        topic: q.topic.trim(),
        difficulty: q.difficulty || null,
        expected_answer: q.expected_answer?.trim() || null,
        role: q.role || targetRole || null,
        keywords: q.keywords || [],
      })),
    };

    const res = await saveConfirmedQuestions(payload);
    setIsSaving(false);

    if (res.success) {
      setSaveSuccess({
        savedCount: res.data.saved_count,
        batchId: res.data.batch_id,
        institutionId: res.data.institution_id,
      });
      loadQuestions();
    } else {
      setParseError(res.error || 'Failed to save confirmed questions.');
    }
  };

  // Reset modal
  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedFile(null);
    setPreviewData(null);
    setEditableQuestions([]);
    setParseError(null);
    setSaveSuccess(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const validCount = editableQuestions.filter((q) => q.is_valid).length;
  const invalidCount = editableQuestions.length - validCount;

  return (
    <div className="space-y-6">
      {/* Top Banner / Metrics */}
      <div className="p-6 rounded-2xl glass-panel border border-slate-800 bg-slate-900/40 relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center space-x-3">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center space-x-1.5">
                <Building2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Institution Scope: {user?.institution_id || 'VFSTR'}</span>
              </span>
              {user?.department && (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                  Dept: {user.department}
                </span>
              )}
            </div>
            <h2 className="text-xl font-bold text-white flex items-center space-x-2">
              <Database className="w-5 h-5 text-indigo-400" />
              <span>Institutional Question Bank & Assessment Assets</span>
            </h2>
            <p className="text-xs sm:text-sm text-slate-400 max-w-2xl">
              Upload role-specific, subject, or departmental assessment questions in PDF, CSV, JSON, TXT, or ZIP format. Preview and correct extracted prompts before committing them to your institutional repository.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => {
                setPage(0);
                loadQuestions();
              }}
              className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition flex items-center space-x-1.5"
              title="Refresh Question Bank"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-400' : ''}`} />
              <span>Refresh</span>
            </button>

            <button
              id="btn-open-question-upload"
              onClick={() => setIsModalOpen(true)}
              className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-medium text-xs sm:text-sm flex items-center space-x-2 shadow-lg shadow-indigo-600/20 transition"
            >
              <UploadCloud className="w-4 h-4" />
              <span>Upload Question File</span>
            </button>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="mt-6 pt-5 border-t border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search question prompts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
            />
          </div>

          <div>
            <input
              type="text"
              placeholder="Filter by topic (e.g. Operating Systems)"
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
            />
          </div>

          <div>
            <select
              value={difficultyFilter}
              onChange={(e) => setDifficultyFilter(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
            >
              <option value="">All Difficulties</option>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </div>

          <div>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
            >
              <option value="">All Canonical Roles</option>
              <option value="Associate Software Engineer">Associate Software Engineer</option>
              <option value="Software Development Engineer">Software Development Engineer</option>
              <option value="Product Engineer">Product Engineer</option>
              <option value="System Engineer">System Engineer</option>
              <option value="Testing Engineer">Testing Engineer</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Questions Table */}
      <div className="rounded-2xl glass-panel border border-slate-800 bg-slate-900/30 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">Repository Questions</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
              {totalQuestions.toLocaleString()} Total
            </span>
          </div>
          {loading && (
            <span className="text-xs text-indigo-400 flex items-center space-x-1.5">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              <span>Loading questions...</span>
            </span>
          )}
        </div>

        {error && (
          <div className="p-4 mx-6 my-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900/60 text-slate-400 font-medium">
                <th className="py-3 px-4 w-12 text-center">#</th>
                <th className="py-3 px-4 w-44">Topic & Role</th>
                <th className="py-3 px-4">Question Prompt</th>
                <th className="py-3 px-4 w-28 text-center">Difficulty</th>
                <th className="py-3 px-4 w-28 text-center">Type</th>
                <th className="py-3 px-4 w-40">Institution Scope</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {questions.length === 0 && !loading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-500">
                    <FolderOpen className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    <p className="text-sm font-medium text-slate-400">No questions found matching criteria</p>
                    <p className="text-xs text-slate-500 mt-1">Upload questions via PDF, CSV, JSON, TXT, or ZIP</p>
                  </td>
                </tr>
              ) : (
                questions.map((q, idx) => {
                  const diffColor =
                    q.difficulty === 'easy'
                      ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                      : q.difficulty === 'hard'
                      ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                      : 'bg-amber-500/10 text-amber-300 border-amber-500/30';

                  return (
                    <tr key={q.question_id || idx} className="hover:bg-slate-800/30 transition">
                      <td className="py-3 px-4 text-center text-slate-500 font-mono">
                        {page * pageSize + idx + 1}
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-200">{q.topic || 'General'}</div>
                        {q.role && (
                          <div className="text-[11px] text-indigo-400 font-mono mt-0.5 truncate max-w-[160px]">
                            {q.role}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="text-slate-200 line-clamp-2 max-w-xl font-normal">
                          {q.question_text}
                        </div>
                        {q.expected_answer && (
                          <div className="text-[11px] text-slate-400 mt-1 line-clamp-1 italic bg-slate-900/50 px-2 py-0.5 rounded border border-slate-800/50">
                            Guide: {q.expected_answer}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4 text-center">
                        {q.difficulty ? (
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${diffColor}`}>
                            {q.difficulty.toUpperCase()}
                          </span>
                        ) : (
                          <span className="text-slate-500 text-[11px]">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${
                          q.question_type === 'coding'
                            ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                            : 'bg-slate-800 text-slate-300'
                        }`}>
                          {q.question_type || 'conceptual'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-[11px] font-semibold text-slate-300 block">
                          {q.institution_id || 'Shared Platform'}
                        </span>
                        {q.department && (
                          <span className="text-[10px] text-slate-500 block">Dept: {q.department}</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {totalQuestions > pageSize && (
          <div className="px-6 py-3 border-t border-slate-800 bg-slate-900/40 flex items-center justify-between">
            <span className="text-xs text-slate-500 font-mono">
              Showing {page * pageSize + 1} - {Math.min((page + 1) * pageSize, totalQuestions)} of {totalQuestions}
            </span>
            <div className="flex items-center space-x-2">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="px-3 py-1 rounded-lg bg-slate-800 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                Previous
              </button>
              <button
                disabled={(page + 1) * pageSize >= totalQuestions}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 rounded-lg bg-slate-800 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* Upload, Extraction Preview & Confirmation Modal */}
      {/* ========================================================================= */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center">
                  <UploadCloud className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Upload & Verify Institution Questions</h3>
                  <p className="text-xs text-slate-400">
                    Faculty preview and validation before committing to the institutional bank.
                  </p>
                </div>
              </div>
              <button
                onClick={handleCloseModal}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1 custom-scrollbar">
              {saveSuccess ? (
                <div className="p-8 text-center space-y-4">
                  <div className="w-14 h-14 mx-auto rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center justify-center">
                    <CheckCircle2 className="w-8 h-8" />
                  </div>
                  <h4 className="text-xl font-bold text-white">Questions Successfully Saved</h4>
                  <p className="text-xs sm:text-sm text-slate-300 max-w-md mx-auto">
                    Successfully committed <strong className="text-emerald-400">{saveSuccess.savedCount} questions</strong> to the <strong>{saveSuccess.institutionId}</strong> repository under batch:
                  </p>
                  <code className="block mx-auto max-w-md px-3 py-1.5 bg-slate-950 rounded border border-slate-800 font-mono text-xs text-indigo-300">
                    {saveSuccess.batchId}
                  </code>
                  <p className="text-[11px] text-slate-400 italic">
                    Note: Questions are securely stored in the question bank and have NOT been auto-assigned. You may attach them when scheduling or assigning interviews.
                  </p>
                  <div className="pt-4">
                    <button
                      onClick={handleCloseModal}
                      className="px-6 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition"
                    >
                      Done & Close
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {/* Step 1: File Ingestion Controls */}
                  <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">
                          Select Question File <span className="text-rose-400">*</span>
                        </label>
                        <input
                          type="file"
                          ref={fileInputRef}
                          accept=".pdf,.csv,.json,.txt,.md,.zip"
                          onChange={handleFileChange}
                          className="w-full text-xs text-slate-400 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 cursor-pointer"
                        />
                        <span className="text-[10px] text-slate-500 mt-1 block">
                          Supported: PDF, CSV, JSON, TXT, MD, ZIP (Max 15MB)
                        </span>
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">
                          Target Role Scope
                        </label>
                        <select
                          value={targetRole}
                          onChange={(e) => setTargetRole(e.target.value)}
                          className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                        >
                          <option value="Associate Software Engineer">Associate Software Engineer</option>
                          <option value="Software Development Engineer">Software Development Engineer</option>
                          <option value="Product Engineer">Product Engineer</option>
                          <option value="System Engineer">System Engineer</option>
                          <option value="Testing Engineer">Testing Engineer</option>
                          <option value="General Technical">General Technical Assessment</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">
                          Default Topic
                        </label>
                        <input
                          type="text"
                          value={defaultTopic}
                          onChange={(e) => setDefaultTopic(e.target.value)}
                          placeholder="e.g. Operating Systems"
                          className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
                      <div className="flex items-center space-x-2 text-xs text-slate-400">
                        <Tag className="w-3.5 h-3.5 text-indigo-400" />
                        <span>Isolated for <strong>{user?.institution_id || 'VFSTR'}</strong></span>
                      </div>

                      <button
                        id="btn-trigger-file-preview"
                        type="button"
                        disabled={!selectedFile || isParsing}
                        onClick={handleParsePreview}
                        className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-medium flex items-center space-x-2 transition"
                      >
                        {isParsing ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            <span>Extracting Questions...</span>
                          </>
                        ) : (
                          <>
                            <FileText className="w-3.5 h-3.5" />
                            <span>Preview Extracted Questions</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {parseError && (
                    <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4 flex-shrink-0" />
                      <span>{parseError}</span>
                    </div>
                  )}

                  {/* Step 2: Extraction Preview & Interactive Correction Table */}
                  {previewData && (
                    <div className="space-y-4">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-indigo-950/30 border border-indigo-900/40">
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="text-xs font-bold text-white">Extraction Preview: {previewData.filename}</span>
                            {previewData.detected_role && (
                              <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 text-[10px] font-mono">
                                Role: {previewData.detected_role}
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            Review extracted questions below. Edit prompts, topics, or difficulty ratings directly.
                          </p>
                        </div>

                        <div className="flex items-center space-x-3 text-xs">
                          <span className="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold flex items-center space-x-1">
                            <Check className="w-3 h-3" />
                            <span>{validCount} Valid</span>
                          </span>
                          {invalidCount > 0 && (
                            <span className="px-2.5 py-1 rounded-lg bg-rose-500/20 text-rose-300 border border-rose-500/30 font-semibold flex items-center space-x-1">
                              <AlertCircle className="w-3 h-3" />
                              <span>{invalidCount} Deficient</span>
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Question Edit Rows */}
                      <div className="space-y-3">
                        {editableQuestions.map((q, idx) => (
                          <div
                            key={q.localId}
                            className={`p-4 rounded-xl border transition ${
                              q.is_valid
                                ? 'bg-slate-950/40 border-slate-800 hover:border-slate-700'
                                : 'bg-rose-950/20 border-rose-800/60'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3 mb-2">
                              <div className="flex items-center space-x-2">
                                <span className="font-mono text-xs font-bold text-indigo-400">
                                  #{idx + 1}
                                </span>
                                <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                  q.is_valid ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/20 text-rose-300'
                                }`}>
                                  {q.is_valid ? 'Valid' : 'Needs Correction'}
                                </span>
                              </div>

                              <button
                                type="button"
                                onClick={() => removeQuestion(idx)}
                                className="text-slate-500 hover:text-rose-400 p-1 rounded transition"
                                title="Discard this question"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>

                            {/* Inline Validation Alerts */}
                            {q.validation_errors && q.validation_errors.length > 0 && (
                              <div className="mb-2 text-[11px] text-rose-300 flex items-center space-x-1">
                                <AlertCircle className="w-3 h-3 flex-shrink-0" />
                                <span>{q.validation_errors.join(' ')}</span>
                              </div>
                            )}

                            {/* Question text textarea */}
                            <div className="mb-3">
                              <label className="block text-[11px] font-medium text-slate-400 mb-1">
                                Question Prompt
                              </label>
                              <textarea
                                rows={2}
                                value={q.question_text}
                                onChange={(e) => updateQuestionField(idx, 'question_text', e.target.value)}
                                className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                              />
                            </div>

                            {/* Metadata row */}
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-2">
                              <div>
                                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                                  Topic
                                </label>
                                <input
                                  type="text"
                                  value={q.topic}
                                  onChange={(e) => updateQuestionField(idx, 'topic', e.target.value)}
                                  className="w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                                />
                              </div>

                              <div>
                                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                                  Difficulty
                                </label>
                                <select
                                  value={q.difficulty || ''}
                                  onChange={(e) => updateQuestionField(idx, 'difficulty', e.target.value || null)}
                                  className="w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                                >
                                  <option value="">Unstated</option>
                                  <option value="easy">Easy</option>
                                  <option value="medium">Medium</option>
                                  <option value="hard">Hard</option>
                                </select>
                              </div>

                              <div>
                                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                                  Question Type
                                </label>
                                <select
                                  value={q.question_type || 'conceptual'}
                                  onChange={(e) => updateQuestionField(idx, 'question_type', e.target.value)}
                                  className="w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                                >
                                  <option value="conceptual">Conceptual</option>
                                  <option value="coding">Coding Problem</option>
                                </select>
                              </div>
                            </div>

                            {/* Expected answer guide */}
                            <div>
                              <label className="block text-[11px] font-medium text-slate-400 mb-1">
                                Expected Answer Guide (Internal Faculty Reference Only)
                              </label>
                              <input
                                type="text"
                                value={q.expected_answer || ''}
                                onChange={(e) => updateQuestionField(idx, 'expected_answer', e.target.value)}
                                placeholder="Key points or approach expected from candidate..."
                                className="w-full px-2.5 py-1.5 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Modal Footer with Explicit Confirmation */}
            {!saveSuccess && previewData && (
              <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/90 flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="text-xs text-slate-400">
                  <span>Saving to: </span>
                  <strong className="text-white">{user?.institution_id || 'VFSTR'} Question Bank</strong>
                  <span className="text-slate-500 block text-[10px]">
                    Questions will NOT be assigned to candidates until explicitly scheduled in an interview.
                  </span>
                </div>

                <div className="flex items-center space-x-3 w-full sm:w-auto">
                  <button
                    type="button"
                    onClick={handleCloseModal}
                    className="flex-1 sm:flex-none px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
                  >
                    Cancel
                  </button>

                  <button
                    id="btn-confirm-save-questions"
                    type="button"
                    disabled={isSaving || validCount === 0 || invalidCount > 0}
                    onClick={handleConfirmSave}
                    className="flex-1 sm:flex-none px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 flex items-center justify-center space-x-2 transition"
                  >
                    {isSaving ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Saving Questions...</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-4 h-4" />
                        <span>Confirm & Save ({validCount}) Questions</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
