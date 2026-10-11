import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  getAssignmentSession,
  startInterviewSession, 
  submitInterviewAnswer, 
  getSessionScorecard,
  recordProctoringEvents,
} from '../api/client';
import ProctoringPreflightModal from '../components/ProctoringPreflightModal';
import ProctoringCameraWidget from '../components/ProctoringCameraWidget';
import { 
  Sparkles, 
  Clock, 
  AlertCircle, 
  CheckCircle2, 
  ArrowRight, 
  RotateCcw, 
  ChevronRight, 
  Award, 
  FileText, 
  BrainCircuit, 
  Zap, 
  TrendingUp, 
  TrendingDown, 
  Minus, 
  Send,
  ShieldAlert,
  ArrowLeft,
  Volume2,
  VolumeX,
  Play,
  Square,
  Mic,
  MicOff,
  Radio
} from 'lucide-react';

export default function InterviewRoom() {
  const { assignmentId } = useParams();
  const { user } = useAuth();

  // Session & Question State
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Active Question
  const [activeQuestion, setActiveQuestion] = useState(null);
  const [answerText, setAnswerText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Immediate Evaluation Feedback State (between questions)
  const [lastEvaluation, setLastEvaluation] = useState(null);
  const [pendingNextQuestion, setPendingNextQuestion] = useState(null);

  // Final Scorecard State
  const [isCompleted, setIsCompleted] = useState(false);
  const [scorecard, setScorecard] = useState(null);

  // Timer State
  const [secondsRemaining, setSecondsRemaining] = useState(null);
  const timerRef = useRef(null);

  // --------------------------------------------------------------------------
  // Web Speech Synthesis (AI Interviewer Voice & Spoken Questions)
  // --------------------------------------------------------------------------
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [speechBlocked, setSpeechBlocked] = useState(false);
  const lastSpokenQuestionIndexRef = useRef(null);
  const [, setVoicesLoaded] = useState(false);

  // --------------------------------------------------------------------------
  // Web Speech Recognition (Student Voice-to-Text Input)
  // --------------------------------------------------------------------------
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState('');
  const [speechError, setSpeechError] = useState(null);
  const recognitionRef = useRef(null);

  // Runtime check for SpeechRecognition support
  const isSpeechRecognitionSupported = typeof window !== 'undefined' && 
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  // --------------------------------------------------------------------------
  // Level 1 Proctoring & Telemetry State
  // --------------------------------------------------------------------------
  const [proctoringConsentGiven, setProctoringConsentGiven] = useState(false);
  const proctoringQueueRef = useRef([]);

  const handleProctoringEvent = useCallback((event) => {
    if (!sessionId) return;
    proctoringQueueRef.current.push(event);
  }, [sessionId]);

  // Periodic flush of batched proctoring events (every 8 seconds)
  useEffect(() => {
    if (!sessionId || isCompleted) return;

    const flushInterval = setInterval(async () => {
      if (proctoringQueueRef.current.length === 0) return;
      const batch = [...proctoringQueueRef.current];
      proctoringQueueRef.current = [];
      await recordProctoringEvents(sessionId, batch);
    }, 8000);

    return () => clearInterval(flushInterval);
  }, [sessionId, isCompleted]);

  // Page Visibility & Window Focus event tracking
  useEffect(() => {
    if (!sessionId || isCompleted) return;

    let hiddenStartTime = null;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        hiddenStartTime = Date.now();
        handleProctoringEvent({
          event_type: 'tab_hidden',
          client_timestamp: new Date().toISOString(),
        });
      } else if (document.visibilityState === 'visible') {
        const duration = hiddenStartTime ? (Date.now() - hiddenStartTime) / 1000 : null;
        hiddenStartTime = null;
        handleProctoringEvent({
          event_type: 'tab_visible',
          client_timestamp: new Date().toISOString(),
          duration_seconds: duration,
        });
      }
    };

    const handleWindowBlur = () => {
      handleProctoringEvent({
        event_type: 'window_blur',
        client_timestamp: new Date().toISOString(),
      });
    };

    const handleWindowFocus = () => {
      handleProctoringEvent({
        event_type: 'window_focus',
        client_timestamp: new Date().toISOString(),
      });
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('focus', handleWindowFocus);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleWindowBlur);
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, [sessionId, isCompleted, handleProctoringEvent]);

  // Flush remaining events before page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (!sessionId || proctoringQueueRef.current.length === 0) return;
      const batch = [...proctoringQueueRef.current];
      proctoringQueueRef.current = [];
      if (navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify({ events: batch })], { type: 'application/json' });
        navigator.sendBeacon(`/api/interview-rooms/sessions/${sessionId}/proctoring-events`, blob);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [sessionId]);

  // Listen for speech synthesis voice list load
  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    const updateVoices = () => {
      const v = window.speechSynthesis.getVoices();
      if (v && v.length > 0) setVoicesLoaded(true);
    };
    updateVoices();
    window.speechSynthesis.onvoiceschanged = updateVoices;
    return () => {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = null;
      }
    };
  }, []);

  // Voice selection helper: Prefer English (en-US, en-GB, en-IN)
  const getEnglishVoice = useCallback(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) return null;
    return (
      voices.find((v) => v.lang === 'en-US') ||
      voices.find((v) => v.lang === 'en-GB') ||
      voices.find((v) => v.lang === 'en-IN') ||
      voices.find((v) => v.lang.toLowerCase().startsWith('en')) ||
      voices[0] ||
      null
    );
  }, []);

  // Speak authoritative question text in English
  const speakQuestion = useCallback((text) => {
    if (!text || typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    
    // Cancel any active speech first
    window.speechSynthesis.cancel();

    if (isMuted) {
      setIsSpeaking(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    const selectedVoice = getEnglishVoice();
    if (selectedVoice) {
      utterance.voice = selectedVoice;
      utterance.lang = selectedVoice.lang || 'en-US';
    } else {
      utterance.lang = 'en-US';
    }
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      setIsSpeaking(true);
      setSpeechBlocked(false);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
    };

    utterance.onerror = (e) => {
      setIsSpeaking(false);
      if (e.error === 'not-allowed') {
        setSpeechBlocked(true);
      }
    };

    try {
      window.speechSynthesis.speak(utterance);
    } catch {
      setSpeechBlocked(true);
      setIsSpeaking(false);
    }
  }, [isMuted, getEnglishVoice]);

  // Auto-speak newly active question once (guarded against re-renders via ref)
  useEffect(() => {
    if (!activeQuestion || !activeQuestion.question_text || isCompleted) return;

    if (lastSpokenQuestionIndexRef.current !== activeQuestion.question_index) {
      lastSpokenQuestionIndexRef.current = activeQuestion.question_index;
      if (!isMuted) {
        speakQuestion(activeQuestion.question_text);
      }
    }
  }, [activeQuestion, isMuted, isCompleted, speakQuestion]);

  // Speech synthesis user controls
  const handlePlayQuestion = () => {
    if (!activeQuestion?.question_text) return;
    setSpeechBlocked(false);
    speakQuestion(activeQuestion.question_text);
  };

  const handleStopSpeech = () => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  };

  const handleToggleMute = () => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next) {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
          window.speechSynthesis.cancel();
        }
        setIsSpeaking(false);
      }
      return next;
    });
  };

  // Speech recognition handlers
  const startVoiceRecognition = () => {
    if (!isSpeechRecognitionSupported) {
      setSpeechError('Speech recognition is not supported in this browser. Please type your response manually.');
      return;
    }

    setSpeechError(null);

    try {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }

      const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognitionClass();
      recognition.lang = 'en-US';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
        setSpeechError(null);
      };

      recognition.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const segment = event.results[i][0]?.transcript || '';
          if (event.results[i].isFinal) {
            const cleanSegment = segment.trim();
            if (cleanSegment) {
              setAnswerText((prev) => {
                if (!prev.trim()) return cleanSegment;
                return `${prev.trim()} ${cleanSegment}`;
              });
            }
          } else {
            interim += segment;
          }
        }
        setInterimTranscript(interim.trim());
      };

      recognition.onerror = (event) => {
        setIsListening(false);
        setInterimTranscript('');
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          setSpeechError('Microphone permission was denied. Please allow microphone access or continue typing manually.');
        } else if (event.error === 'no-speech') {
          setSpeechError('No speech was detected. You can speak again or type manually.');
        } else if (event.error === 'network') {
          setSpeechError('Speech recognition network error. Manual keyboard typing remains fully active.');
        } else if (event.error !== 'aborted') {
          setSpeechError(`Voice input paused (${event.error}). Manual keyboard typing remains active.`);
        }
      };

      recognition.onend = () => {
        setIsListening(false);
        setInterimTranscript('');
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      setIsListening(false);
      setSpeechError('Unable to activate microphone. Please continue typing manually.');
    }
  };

  const stopVoiceRecognition = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore
      }
    }
    setIsListening(false);
    setInterimTranscript('');
  };

  const handleToggleVoiceInput = () => {
    if (isListening) {
      stopVoiceRecognition();
    } else {
      startVoiceRecognition();
    }
  };

  // Safe global cleanup on unmount: cancel speech synthesis & stop microphone
  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  // 1. Initialize or resume session
  const initSession = useCallback(async () => {
    if (!assignmentId) return;
    setLoading(true);
    setError(null);

    // Step A: Check if assignment already has an active or completed session
    const checkRes = await getAssignmentSession(assignmentId);
    let sess = null;

    if (checkRes.success && checkRes.data.has_session) {
      sess = checkRes.data;
    } else {
      // Step B: No session exists yet, start a new attempt
      const startRes = await startInterviewSession(assignmentId);
      if (!startRes.success) {
        setError(startRes.error || 'Failed to initialize interview session.');
        setLoading(false);
        return;
      }
      sess = startRes.data;
    }

    setSessionId(sess.session_id);

    // If session is already completed, load scorecard directly
    if (sess.session_status === 'completed' && (sess.scorecard_id || sess.final_scorecard_id)) {
      setIsCompleted(true);
      const scRes = await getSessionScorecard(sess.session_id);
      if (scRes.success) {
        setScorecard(scRes.data);
      }
      setLoading(false);
      return;
    }

    if (sess.session_status === 'timed_out') {
      setError('Interview session duration has expired. Active attempt timed out.');
      setLoading(false);
      return;
    }

    // Set countdown timer based on expires_at
    if (sess.expires_at) {
      const exp = new Date(sess.expires_at).getTime();
      const now = new Date().getTime();
      const diffSecs = Math.max(0, Math.floor((exp - now) / 1000));
      setSecondsRemaining(diffSecs);
    }

    // Set active question
    if (sess.active_question) {
      setActiveQuestion({
        session_id: sess.session_id,
        question_index: sess.current_question_index,
        total_questions: sess.total_questions_target,
        question_text: sess.active_question.question_text,
        topic: sess.active_question.topic,
        difficulty: sess.active_question.difficulty,
        evaluator_mode: sess.evaluator_mode,
        interview_title: sess.interview_title,
      });
    }

    setLoading(false);
  }, [assignmentId]);

  useEffect(() => {
    initSession();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [initSession]);

  // Countdown clock tick
  useEffect(() => {
    if (secondsRemaining === null || secondsRemaining <= 0 || isCompleted) return;

    timerRef.current = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timerRef.current);
  }, [secondsRemaining, isCompleted]);

  // Format timer mm:ss
  const formatTime = (secs) => {
    if (secs === null) return '--:--';
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    return `${mins.toString().padStart(2, '0')}:${rem.toString().padStart(2, '0')}`;
  };

  // Submit Answer
  const handleSubmitAnswer = async (e) => {
    e.preventDefault();
    if (!answerText.trim() || submitting || !sessionId) return;

    // Immediately stop audio speech and voice dictation on submit
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    stopVoiceRecognition();

    setSubmitting(true);
    setError(null);

    const res = await submitInterviewAnswer(sessionId, answerText.trim());
    setSubmitting(false);

    if (!res.success) {
      setError(res.error || 'Failed to submit answer. Please try again.');
      return;
    }

    const data = res.data;

    // Show evaluation modal / transition
    setLastEvaluation({
      score: data.evaluated_score ?? data.evaluation?.score ?? 0,
      feedback: data.feedback ?? data.evaluation?.feedback ?? '',
      strengths: data.strengths ?? data.evaluation?.strengths ?? [],
      improvements: data.improvements ?? data.evaluation?.improvements ?? [],
      difficultyRationale: data.difficulty_rationale ?? data.difficulty_adjustment_rationale ?? '',
      isFinal: data.is_session_completed,
    });

    if (data.is_session_completed) {
      setIsCompleted(true);
      // Fetch completed scorecard
      const scRes = await getSessionScorecard(sessionId);
      if (scRes.success) {
        setScorecard(scRes.data);
      }
    } else if (data.next_question) {
      setPendingNextQuestion(data.next_question);
    }
  };

  // Move to next question after reviewing feedback
  const handleProceedToNextQuestion = () => {
    if (pendingNextQuestion) {
      // Stop ongoing audio and recognition when advancing
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      setIsSpeaking(false);
      stopVoiceRecognition();
      setSpeechError(null);
      setInterimTranscript('');

      setActiveQuestion((prev) => ({
        ...prev,
        question_index: pendingNextQuestion.question_index,
        question_text: pendingNextQuestion.question_text,
        topic: pendingNextQuestion.topic,
        difficulty: pendingNextQuestion.difficulty,
        evaluator_mode: pendingNextQuestion.evaluator_mode,
      }));
      setAnswerText('');
      setLastEvaluation(null);
      setPendingNextQuestion(null);
    }
  };

  const getDifficultyBadge = (diff) => {
    const d = (diff || '').toLowerCase();
    if (d === 'hard') {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30 flex items-center space-x-1">
          <TrendingUp className="w-3 h-3 text-rose-400" />
          <span>Hard Tier</span>
        </span>
      );
    }
    if (d === 'easy') {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center space-x-1">
          <TrendingDown className="w-3 h-3 text-emerald-400" />
          <span>Easy Tier</span>
        </span>
      );
    }
    return (
      <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center space-x-1">
        <Minus className="w-3 h-3 text-amber-400" />
        <span>Medium Tier</span>
      </span>
    );
  };

  // Word count helper
  const wordCount = answerText.trim() ? answerText.trim().split(/\s+/).length : 0;

  // --------------------------------------------------------------------------
  // Loading & Error States
  // --------------------------------------------------------------------------
  if (loading) {
    return (
      <div className="min-h-screen bg-[#030712] text-slate-100 flex items-center justify-center p-4">
        <div className="glass-panel p-8 rounded-2xl border border-slate-800 text-center max-w-md w-full">
          <div className="w-12 h-12 rounded-xl bg-indigo-600/20 text-indigo-400 flex items-center justify-center mx-auto mb-4 animate-pulse">
            <BrainCircuit className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-white mb-2">Connecting to AI Interview Engine</h3>
          <p className="text-xs text-slate-400 leading-relaxed mb-4">
            Validating candidate registration, checking schedule availability, and initializing adaptive question pipeline...
          </p>
          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div className="bg-gradient-to-r from-indigo-500 to-violet-500 h-1.5 w-2/3 animate-pulse"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error && !activeQuestion && !scorecard) {
    return (
      <div className="min-h-screen bg-[#030712] text-slate-100 flex items-center justify-center p-4">
        <div className="glass-panel p-8 rounded-2xl border border-rose-900/50 text-center max-w-md w-full">
          <div className="w-12 h-12 rounded-xl bg-rose-500/20 text-rose-400 flex items-center justify-center mx-auto mb-4">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-rose-300 mb-2">Session Access Restricted</h3>
          <p className="text-xs text-slate-300 leading-relaxed mb-6 bg-rose-950/40 p-3 rounded-lg border border-rose-900/40">
            {error}
          </p>
          <Link
            to="/dashboard"
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold inline-flex items-center space-x-2 transition"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to Dashboard</span>
          </Link>
        </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Completed Scorecard View
  // --------------------------------------------------------------------------
  if (isCompleted && scorecard) {
    const pct = scorecard.percentage_score || 0;
    const isPass = pct >= 60;

    return (
      <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col">
        {/* Header */}
        <header className="border-b border-slate-800/80 bg-slate-900/50 backdrop-blur sticky top-0 z-20">
          <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center">
                <Award className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-white">Evaluation Scorecard</h1>
                <p className="text-[11px] text-slate-400">Adaptive Mock Interview Performance Assessment</p>
              </div>
            </div>
            <Link
              to="/dashboard"
              className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold flex items-center space-x-1.5 border border-slate-700 transition"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Dashboard</span>
            </Link>
          </div>
        </header>

        <main className="max-w-6xl mx-auto px-4 py-8 w-full flex-1 space-y-6">
          {/* Top Score Summary Banner */}
          <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-slate-800 relative overflow-hidden">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
              <div>
                <div className="flex items-center space-x-2 mb-2">
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    Candidate: {scorecard.student_registration_number}
                  </span>
                  <span className="text-xs text-slate-400">•</span>
                  {scorecard.evaluator_mode === 'mock_rule_engine' ? (
                    <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center space-x-1">
                      <AlertCircle className="w-3 h-3 text-amber-400" />
                      <span>Mock Evaluation (Rule Rubric Mode)</span>
                    </span>
                  ) : scorecard.evaluator_mode === 'gemini' ? (
                    <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center space-x-1">
                      <Sparkles className="w-3 h-3 text-emerald-400" />
                      <span>AI Evaluator: Google Gemini</span>
                    </span>
                  ) : (
                    <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      Evaluator: {scorecard.evaluator_mode}
                    </span>
                  )}
                </div>
                <h2 className="text-xl sm:text-2xl font-bold text-white mb-2">
                  Interview Evaluation Complete
                </h2>
                <p className="text-xs text-slate-300 max-w-2xl leading-relaxed">
                  {scorecard.summary_feedback}
                </p>
              </div>

              {/* Big Score Card */}
              <div className="flex items-center space-x-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800 shrink-0">
                <div className="text-right">
                  <div className="text-xs uppercase font-semibold text-slate-400 tracking-wider">Overall Score</div>
                  <div className="text-xs font-medium text-indigo-400">{scorecard.performance_level}</div>
                </div>
                <div className={`w-16 h-16 rounded-xl flex flex-col items-center justify-center font-bold text-lg border ${
                  isPass ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                }`}>
                  <span>{scorecard.overall_score}</span>
                  <span className="text-[10px] text-slate-400 font-normal">/ 10.0</span>
                </div>
              </div>
            </div>

            {/* Difficulty Progression Track */}
            {scorecard.difficulty_progression && scorecard.difficulty_progression.length > 0 && (
              <div className="mt-6 pt-6 border-t border-slate-800/80">
                <div className="text-xs font-semibold text-slate-300 mb-3 flex items-center space-x-1.5">
                  <Zap className="w-3.5 h-3.5 text-amber-400" />
                  <span>Adaptive Difficulty Progression Path</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {scorecard.difficulty_progression.map((diff, idx) => (
                    <React.Fragment key={idx}>
                      <div className="flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono">
                        <span className="text-slate-400">Q{idx + 1}:</span>
                        <span className={`capitalize font-semibold ${
                          diff === 'hard' ? 'text-rose-400' : diff === 'easy' ? 'text-emerald-400' : 'text-amber-400'
                        }`}>
                          {diff}
                        </span>
                      </div>
                      {idx < scorecard.difficulty_progression.length - 1 && (
                        <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Strengths & Growth Areas Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Strengths */}
            <div className="glass-panel p-6 rounded-2xl border border-slate-800">
              <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4" />
                <span>Demonstrated Technical Strengths</span>
              </h3>
              {scorecard.strengths && scorecard.strengths.length > 0 ? (
                <ul className="space-y-2 text-xs text-slate-300">
                  {scorecard.strengths.map((str, i) => (
                    <li key={i} className="flex items-start space-x-2">
                      <span className="text-emerald-400 font-bold">•</span>
                      <span>{str}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400">Baseline competency demonstrated across core prompts.</p>
              )}
            </div>

            {/* Areas for Growth */}
            <div className="glass-panel p-6 rounded-2xl border border-slate-800">
              <h3 className="text-sm font-bold text-amber-400 mb-3 flex items-center space-x-2">
                <AlertCircle className="w-4 h-4" />
                <span>Recommendations for Revision & Growth</span>
              </h3>
              {scorecard.areas_for_growth && scorecard.areas_for_growth.length > 0 ? (
                <ul className="space-y-2 text-xs text-slate-300">
                  {scorecard.areas_for_growth.map((area, i) => (
                    <li key={i} className="flex items-start space-x-2">
                      <span className="text-amber-400 font-bold">•</span>
                      <span>{area}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400">Maintain continued precision across higher-order networking scenarios.</p>
              )}
            </div>
          </div>

          {/* Detailed Question Review Breakdown */}
          {scorecard.responses && scorecard.responses.length > 0 && (
            <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
              <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                <FileText className="w-4 h-4 text-indigo-400" />
                <span>Question-by-Question Response Audit</span>
              </h3>
              <div className="space-y-4">
                {scorecard.responses.map((item, idx) => (
                  <div key={idx} className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center space-x-2">
                          <span className="text-xs font-mono font-bold text-indigo-300">Question {item.question_index}</span>
                          <span className="text-xs text-slate-500">•</span>
                          <span className="text-xs text-slate-400 font-medium">{item.topic}</span>
                          {getDifficultyBadge(item.difficulty)}
                        </div>
                        <p className="text-xs text-white font-medium">{item.question_text}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="text-sm font-bold text-indigo-300 font-mono">{item.score}</span>
                        <span className="text-xs text-slate-500"> / 10</span>
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/50 text-xs font-mono text-slate-300">
                      <div className="text-[10px] uppercase font-bold text-slate-400 mb-1">Your Submitted Response:</div>
                      {item.answer_text}
                    </div>

                    <div className="text-xs text-slate-300 leading-relaxed bg-indigo-950/20 p-2.5 rounded-lg border border-indigo-900/30">
                      <strong className="text-indigo-400">Evaluator Rubric Feedback: </strong>
                      {item.feedback}
                    </div>

                    {item.difficulty_adjustment_rationale && (
                      <div className="text-[11px] text-slate-400 font-mono flex items-center space-x-1.5">
                        <Zap className="w-3 h-3 text-amber-400 shrink-0" />
                        <span>Adaptive Policy: {item.difficulty_adjustment_rationale}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Mandatory Explicit Algorithmic Disclaimer */}
          <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 text-slate-400 text-xs leading-relaxed space-y-1.5">
            <div className="font-semibold text-slate-300 flex items-center space-x-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-indigo-400" />
              <span>Algorithmic Assessment Disclaimer</span>
            </div>
            <p>
              {scorecard.disclaimer || 
                scorecard.algorithmic_disclaimer || 
                "Score and feedback were computed using automated technical rubrics and adaptive difficulty thresholds. Evaluated on keyword precision, terminology depth, and protocol explanation structure. This assessment represents algorithmic interview practice and does not claim subjective human parity or absolute grading."}
            </p>
          </div>
        </main>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Active Question & Answer View
  // --------------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col relative">
      {/* Proctoring Preflight & Consent Modal */}
      {!proctoringConsentGiven && !isCompleted && !loading && (
        <ProctoringPreflightModal
          studentRegistration={user?.registration_number || user?.email}
          onConsentGiven={() => setProctoringConsentGiven(true)}
        />
      )}

      {/* Level 1 Proctoring Live Camera Preview (Floating PIP) */}
      {proctoringConsentGiven && !isCompleted && sessionId && (
        <div className="fixed bottom-6 right-6 z-30 shadow-2xl animate-in fade-in slide-in-from-bottom-4">
          <ProctoringCameraWidget
            onProctoringEvent={handleProctoringEvent}
            isSessionActive={!isCompleted && !lastEvaluation}
          />
        </div>
      )}

      {/* Top Bar with Live Timer and Progress */}
      <header className="border-b border-slate-800/80 bg-slate-900/50 backdrop-blur sticky top-0 z-20">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center">
              <BrainCircuit className="w-4 h-4 text-white" />
            </div>
            <div>
              <span className="text-xs font-bold text-white block">
                {activeQuestion?.interview_title || 'Adaptive Mock Interview'}
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                VFSTR • Registered: {user?.registration_number || user?.email}
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* Countdown Clock */}
            <div className="flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-slate-300">Remaining:</span>
              <span className={`font-bold ${secondsRemaining !== null && secondsRemaining < 300 ? 'text-rose-400 animate-pulse' : 'text-white'}`}>
                {formatTime(secondsRemaining)}
              </span>
            </div>

            <Link
              to="/dashboard"
              className="text-xs px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition"
            >
              Exit
            </Link>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 w-full flex-1 flex flex-col justify-between space-y-6">
        {/* Progress Tracker Banner */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800/70">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono font-bold text-indigo-400 uppercase tracking-wider">
              Question {activeQuestion?.question_index} of {activeQuestion?.total_questions}
            </span>
            <span className="text-slate-600">•</span>
            <span className="text-xs text-slate-300 font-medium">Topic: {activeQuestion?.topic}</span>
          </div>

          <div className="flex items-center space-x-2">
            {getDifficultyBadge(activeQuestion?.difficulty)}
            {activeQuestion?.evaluator_mode === 'mock_rule_engine' ? (
              <span className="text-[11px] font-mono font-medium text-amber-300 px-2 py-0.5 rounded bg-amber-950/40 border border-amber-800/40 flex items-center space-x-1">
                <AlertCircle className="w-3 h-3 text-amber-400" />
                <span>Mock Evaluator (Rule Rubric)</span>
              </span>
            ) : activeQuestion?.evaluator_mode === 'gemini' ? (
              <span className="text-[11px] font-mono font-medium text-emerald-300 px-2 py-0.5 rounded bg-emerald-950/40 border border-emerald-800/40 flex items-center space-x-1">
                <Sparkles className="w-3 h-3 text-emerald-400" />
                <span>AI Evaluator: Google Gemini</span>
              </span>
            ) : (
              <span className="text-[11px] font-mono text-indigo-300 px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                {activeQuestion?.evaluator_mode || 'AI Evaluator'}
              </span>
            )}
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* AI Interviewer & Authoritative Spoken Captions Panel */}
        <div className="glass-panel p-6 sm:p-7 rounded-2xl border border-slate-800 space-y-4 relative overflow-hidden">
          {/* Subtle Ambient Backlight when speaking */}
          <div className={`absolute top-0 right-0 w-64 h-32 blur-3xl pointer-events-none transition-all duration-500 ${
            isSpeaking ? 'bg-indigo-600/20' : 'bg-transparent'
          }`} />

          {/* AI Interviewer Header & Audio Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
            <div className="flex items-center space-x-3">
              <div className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                isSpeaking 
                  ? 'bg-gradient-to-tr from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-500/30 animate-pulse'
                  : 'bg-slate-800/80 text-indigo-400 border border-slate-700/60'
              }`}>
                <BrainCircuit className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold text-white tracking-wide">AI Interviewer</span>
                  <span className="text-slate-600">•</span>
                  <span className="text-[11px] text-slate-400">English Voice (en-US / en-GB)</span>
                </div>
                {/* Speaking State Pill */}
                <div className="flex items-center space-x-1.5 mt-0.5">
                  {isSpeaking ? (
                    <span className="text-[11px] font-semibold text-emerald-300 flex items-center space-x-1 animate-pulse">
                      <Radio className="w-3 h-3 text-emerald-400 animate-ping" />
                      <span>Speaking Question Aloud...</span>
                    </span>
                  ) : isMuted ? (
                    <span className="text-[11px] text-slate-400 flex items-center space-x-1 font-mono">
                      <VolumeX className="w-3 h-3 text-slate-500" />
                      <span>Audio Muted</span>
                    </span>
                  ) : (
                    <span className="text-[11px] text-indigo-300 flex items-center space-x-1 font-mono">
                      <Volume2 className="w-3 h-3 text-indigo-400" />
                      <span>Audio Ready</span>
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Audio Action Buttons */}
            <div className="flex items-center space-x-2">
              {isSpeaking ? (
                <button
                  type="button"
                  onClick={handleStopSpeech}
                  id="stop-question-audio-btn"
                  className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 text-xs font-semibold flex items-center space-x-1.5 transition"
                  title="Stop speaking"
                  aria-label="Stop audio speech"
                >
                  <Square className="w-3 h-3 fill-current" />
                  <span>Stop Audio</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handlePlayQuestion}
                  id="play-question-audio-btn"
                  className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center space-x-1.5 shadow-md shadow-indigo-600/20 transition"
                  title="Play or replay question in English"
                  aria-label="Play question audio"
                >
                  <Play className="w-3 h-3 fill-current" />
                  <span>Play Question</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleToggleMute}
                id="toggle-mute-audio-btn"
                className={`p-2 rounded-lg text-xs font-semibold border transition ${
                  isMuted 
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                }`}
                title={isMuted ? "Unmute voice questions" : "Mute voice questions"}
                aria-label={isMuted ? "Unmute question audio" : "Mute question audio"}
              >
                {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Autoplay Blocked Notification Banner */}
          {speechBlocked && (
            <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-900/50 text-xs text-amber-300 flex items-center justify-between gap-3 animate-in fade-in">
              <div className="flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
                <span>Audio autoplay was paused by browser policy. Click "Play Question" to listen.</span>
              </div>
              <button
                type="button"
                onClick={handlePlayQuestion}
                className="px-2.5 py-1 rounded bg-amber-500 text-slate-950 font-bold text-[11px] hover:bg-amber-400 transition shrink-0"
              >
                Listen Now
              </button>
            </div>
          )}

          {/* Authoritative English Captions */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] uppercase font-bold tracking-wider text-indigo-400">
              <span className="flex items-center space-x-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Authoritative English Captions</span>
              </span>
              <span className="text-slate-500 font-mono text-[10px] lowercase">
                spoken prompt
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800 text-slate-100 text-sm sm:text-base leading-relaxed font-medium transition-all">
              {activeQuestion?.question_text}
            </div>

            <p className="text-xs text-slate-400 italic">
              Instructions: Provide a structured, technical response explaining protocol mechanics, packet flows, or architecture where applicable.
            </p>
          </div>
        </div>

        {/* Response Workspace */}
        <form onSubmit={handleSubmitAnswer} className="space-y-4 flex-1 flex flex-col justify-between">
          <div className="space-y-2 flex-1">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
              <div className="flex items-center space-x-2">
                <label htmlFor="student-answer" className="font-semibold text-slate-300">
                  Your Technical Response:
                </label>

                {/* Speech Recognition Voice Input Toggle Button */}
                {isSpeechRecognitionSupported ? (
                  <button
                    type="button"
                    onClick={handleToggleVoiceInput}
                    id="toggle-voice-input-btn"
                    disabled={submitting || !!lastEvaluation}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition ${
                      isListening
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 animate-pulse'
                        : 'bg-indigo-950/60 text-indigo-300 border border-indigo-800/60 hover:bg-indigo-900/60'
                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                    title={isListening ? "Stop voice dictation" : "Start speaking response in English"}
                    aria-label={isListening ? "Stop voice input" : "Start voice input in English"}
                  >
                    {isListening ? (
                      <>
                        <MicOff className="w-3.5 h-3.5 text-rose-400" />
                        <span>Stop Voice Input</span>
                      </>
                    ) : (
                      <>
                        <Mic className="w-3.5 h-3.5 text-indigo-400" />
                        <span>Voice Input (en-US)</span>
                      </>
                    )}
                  </button>
                ) : (
                  <span className="text-[11px] text-slate-500 font-mono px-2 py-0.5 rounded bg-slate-900 border border-slate-800" title="Web Speech Recognition is not supported by this browser engine">
                    Voice Dictation Unsupported (Manual Typing Active)
                  </span>
                )}
              </div>

              <div className="flex items-center space-x-3 font-mono text-[11px]">
                <span className={wordCount >= 25 ? 'text-emerald-400' : 'text-slate-400'}>
                  {wordCount} words {wordCount >= 25 ? '✓ (Good depth)' : '(25+ recommended)'}
                </span>
                <span>{answerText.length} characters</span>
              </div>
            </div>

            {/* Active Listening Status Indicator */}
            {isListening && (
              <div className="p-2.5 rounded-lg bg-rose-950/30 border border-rose-900/50 text-xs text-rose-300 flex items-center justify-between gap-2 animate-in fade-in">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
                  <span className="font-medium">Listening... Speak your answer clearly in English. Recognized text is added to your response.</span>
                </div>
                <button
                  type="button"
                  onClick={stopVoiceRecognition}
                  className="px-2 py-0.5 rounded bg-rose-900/60 hover:bg-rose-800/60 text-[11px] font-semibold text-rose-200"
                >
                  Done Speaking
                </button>
              </div>
            )}

            {/* Interim Transcript Preview */}
            {interimTranscript && (
              <div className="p-2 rounded-lg bg-indigo-950/40 border border-indigo-900/50 text-xs font-mono text-indigo-300 flex items-center space-x-2 animate-in fade-in">
                <span className="text-[10px] uppercase font-bold text-indigo-400">Capturing:</span>
                <span className="italic">"{interimTranscript}"</span>
              </div>
            )}

            {/* Non-destructive Microphone Error Banner */}
            {speechError && (
              <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-900/50 text-xs text-amber-300 flex items-center justify-between gap-2 animate-in fade-in">
                <div className="flex items-center space-x-2">
                  <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  <span>{speechError}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setSpeechError(null)}
                  className="text-amber-400 hover:text-white text-xs px-2 py-0.5 rounded bg-amber-950/50 border border-amber-900/60"
                >
                  Dismiss
                </button>
              </div>
            )}

            <textarea
              id="student-answer"
              rows={8}
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              disabled={submitting || !!lastEvaluation}
              placeholder="Speak or type your explanation here. You can use voice input above or type manually. Be specific with networking protocols, layer behavior, encapsulation, and operational mechanisms..."
              className="w-full rounded-xl bg-slate-950/80 border border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-slate-100 placeholder-slate-600 text-xs font-mono p-4 resize-none transition leading-relaxed disabled:opacity-50"
            />
          </div>

          {/* Submit Action */}
          {!lastEvaluation && (
            <div className="flex items-center justify-between pt-2">
              <span className="text-[11px] text-slate-500">
                Once submitted, your response will be evaluated immediately by the adaptive rubric engine.
              </span>
              <button
                type="submit"
                id="submit-answer-btn"
                disabled={submitting || !answerText.trim()}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? (
                  <>
                    <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                    <span>Evaluating Response...</span>
                  </>
                ) : (
                  <>
                    <span>Submit Response</span>
                    <Send className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            </div>
          )}
        </form>

        {/* Immediate Evaluation Feedback Drawer */}
        {lastEvaluation && (
          <div className="p-6 rounded-2xl glass-panel border border-indigo-500/40 bg-slate-950/90 space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold text-emerald-400 flex items-center space-x-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Response Evaluated</span>
                  </span>
                  <span className="text-slate-600">•</span>
                  <span className="text-xs text-slate-400">
                    Question {activeQuestion?.question_index} Complete
                  </span>
                </div>
                <p className="text-xs text-slate-200 leading-relaxed font-medium">
                  {lastEvaluation.feedback}
                </p>
              </div>

              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 text-center shrink-0">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Awarded</div>
                <div className="text-lg font-bold text-indigo-400 font-mono">
                  {lastEvaluation.score} <span className="text-xs text-slate-500 font-normal">/ 10</span>
                </div>
              </div>
            </div>

            {/* Strengths & Improvements */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              {lastEvaluation.strengths && lastEvaluation.strengths.length > 0 && (
                <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-900/30 text-emerald-300">
                  <strong className="block text-emerald-400 mb-1">Strengths Noted:</strong>
                  {lastEvaluation.strengths.join(' ')}
                </div>
              )}
              {lastEvaluation.improvements && lastEvaluation.improvements.length > 0 && (
                <div className="p-3 rounded-lg bg-amber-950/20 border border-amber-900/30 text-amber-300">
                  <strong className="block text-amber-400 mb-1">Growth Recommendation:</strong>
                  {lastEvaluation.improvements.join(' ')}
                </div>
              )}
            </div>

            {/* Adaptive Rationale */}
            {lastEvaluation.difficultyRationale && (
              <div className="p-3 rounded-lg bg-indigo-950/30 border border-indigo-900/40 text-xs font-mono text-indigo-300 flex items-center space-x-2">
                <Zap className="w-4 h-4 text-amber-400 shrink-0" />
                <span>
                  <strong>Adaptive Transition: </strong>
                  {lastEvaluation.difficultyRationale}
                </span>
              </div>
            )}

            {/* Next Step Action */}
            <div className="flex justify-end pt-2">
              {lastEvaluation.isFinal ? (
                <button
                  onClick={() => setIsCompleted(true)}
                  id="view-final-scorecard-btn"
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 transition flex items-center space-x-2"
                >
                  <Award className="w-4 h-4" />
                  <span>View Final Evaluation Scorecard</span>
                </button>
              ) : (
                <button
                  onClick={handleProceedToNextQuestion}
                  id="next-question-btn"
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition flex items-center space-x-2"
                >
                  <span>Proceed to Next Question</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
