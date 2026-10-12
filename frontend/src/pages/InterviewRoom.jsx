import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  getAssignmentSession,
  startInterviewSession,
  submitInterviewAnswer,
  runInterviewCode,
  submitInterviewCode,
  getSessionScorecard,
  recordProctoringEvents,
  getVoiceStatus,
  transcribeInterviewAudio,
  synthesizeInterviewSpeech,
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
  Radio,
  Terminal,
  Code,
  Cpu,
  PlayCircle,
  CheckCircle,
  XCircle,
  Layers,
  WifiOff,
  ServerCrash,
  AlertTriangle,
  Loader2,
} from 'lucide-react';

export default function InterviewRoom() {
  const { assignmentId } = useParams();
  const { user } = useAuth();

  // Session & Question State
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [errorType, setErrorType] = useState(null); // 'EXPIRED' | 'NETWORK' | 'SERVER' | 'CONFLICT' | 'GENERIC'
  const [isRetrying, setIsRetrying] = useState(false);

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

  // Coding Question Language & Execution State
  const [selectedLanguage, setSelectedLanguage] = useState('Python');
  const [runningCode, setRunningCode] = useState(false);
  const [executionResult, setExecutionResult] = useState(null);
  const [useCustomInput, setUseCustomInput] = useState(false);
  const [customInputText, setCustomInputText] = useState('');
  const [selectedTestCaseTab, setSelectedTestCaseTab] = useState(0);

  const CODE_TEMPLATES = {
    Python: '# Python 3 Solution\ndef solution():\n    # Read input from standard input\n    # Write your solution logic here\n    pass\n\nif __name__ == "__main__":\n    solution()\n',
    Java: '// Java Solution\nimport java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner scanner = new Scanner(System.in);\n        // Write your solution code here\n    }\n}\n',
    C: '// C Solution\n#include <stdio.h>\n\nint main() {\n    // Write your solution code here\n    return 0;\n}\n',
    'C++': '// C++ Solution\n#include <iostream>\n#include <vector>\n#include <string>\n\nusing namespace std;\n\nint main() {\n    // Write your solution code here\n    return 0;\n}\n',
  };

  const handleLanguageSelect = (lang) => {
    setSelectedLanguage(lang);
    if (!answerText.trim() || Object.values(CODE_TEMPLATES).some(t => t.trim() === answerText.trim())) {
      setAnswerText(CODE_TEMPLATES[lang] || '');
    }
  };

  // Timer State
  const [secondsRemaining, setSecondsRemaining] = useState(null);
  const timerRef = useRef(null);

  // --------------------------------------------------------------------------
  // --------------------------------------------------------------------------
  // Deepgram Voice & Web Speech Synthesis (AI Interviewer Voice & Spoken Questions)
  // --------------------------------------------------------------------------
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speakingSource, setSpeakingSource] = useState(null); // 'deepgram' | 'browser' | null
  const [isMuted, setIsMuted] = useState(false);
  const [speechBlocked, setSpeechBlocked] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState(null);
  const lastSpokenQuestionIndexRef = useRef(null);
  const [, setVoicesLoaded] = useState(false);
  const deepgramAudioRef = useRef(null);
  const audioPlaybackUrlRef = useRef(null);

  // --------------------------------------------------------------------------
  // Deepgram Audio Recording & Web Speech Recognition (Student Voice Input)
  // --------------------------------------------------------------------------
  const [isRecordingAudio, setIsRecordingAudio] = useState(false);
  const [isTranscribingAudio, setIsTranscribingAudio] = useState(false);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordingStartTimeRef = useRef(null);

  // Browser Web Speech Recognition fallback state
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

      const rawApiUrl = import.meta.env.VITE_API_URL;
      let apiBase = typeof rawApiUrl === 'string' ? rawApiUrl.trim().replace(/\/+$/, '') : '';

      // Preserve local development support with safe dev fallback
      if (!apiBase && import.meta.env.DEV) {
        apiBase = 'http://localhost:8000';
      }

      let isValidBackendUrl = false;
      try {
        const parsed = new URL(apiBase);
        isValidBackendUrl = parsed.protocol === 'http:' || parsed.protocol === 'https:';
      } catch {
        isValidBackendUrl = false;
      }

      // Never send proctoring events to frontend origin if backend URL is missing or invalid
      if (!isValidBackendUrl) {
        if (import.meta.env.DEV) {
          console.warn('[Proctoring] Skipping beforeunload sendBeacon: backend API URL is missing or invalid.');
        }
        return;
      }

      if (typeof navigator === 'undefined' || !navigator.sendBeacon) {
        if (import.meta.env.DEV) {
          console.warn('[Proctoring] navigator.sendBeacon is unavailable; keeping events in queue.');
        }
        return;
      }

      const batch = [...proctoringQueueRef.current];
      try {
        const blob = new Blob([JSON.stringify({ events: batch })], { type: 'application/json' });
        const beaconUrl = `${apiBase}/api/interview-rooms/sessions/${sessionId}/proctoring-events`;
        const accepted = navigator.sendBeacon(beaconUrl, blob);
        if (accepted) {
          // Browser accepted payload for queuing; remove transmitted events from queue
          proctoringQueueRef.current = proctoringQueueRef.current.slice(batch.length);
        } else if (import.meta.env.DEV) {
          console.warn('[Proctoring] navigator.sendBeacon rejected payload queuing; keeping events in queue.');
        }
      } catch (err) {
        if (import.meta.env.DEV) {
          console.warn('[Proctoring] Failed to execute sendBeacon during beforeunload:', err?.message || err);
        }
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

  // Browser SpeechSynthesis fallback
  const speakQuestionBrowser = useCallback((text) => {
    if (!text || typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    if (isMuted) {
      setIsSpeaking(false);
      setSpeakingSource(null);
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
      setSpeakingSource('browser');
      setSpeechBlocked(false);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      setSpeakingSource(null);
    };

    utterance.onerror = (e) => {
      setIsSpeaking(false);
      setSpeakingSource(null);
      if (e.error === 'not-allowed') {
        setSpeechBlocked(true);
      }
    };

    try {
      window.speechSynthesis.speak(utterance);
    } catch {
      setSpeechBlocked(true);
      setIsSpeaking(false);
      setSpeakingSource(null);
    }
  }, [isMuted, getEnglishVoice]);

  // Master question speaker: Prefers Deepgram TTS (Aura), seamlessly falls back to browser speechSynthesis
  const speakQuestion = useCallback(async (text) => {
    if (!text) return;

    // Stop any ongoing audio first
    handleStopSpeech();

    if (isMuted) {
      setIsSpeaking(false);
      setSpeakingSource(null);
      return;
    }

    // Try Deepgram TTS if sessionId is available
    if (sessionId) {
      try {
        const res = await synthesizeInterviewSpeech(sessionId, text);
        if (res.success && res.data instanceof Blob && res.data.size > 0) {
          const blobUrl = URL.createObjectURL(res.data);
          audioPlaybackUrlRef.current = blobUrl;
          const audio = new Audio(blobUrl);

          audio.onplay = () => {
            setIsSpeaking(true);
            setSpeakingSource('deepgram');
            setSpeechBlocked(false);
          };

          audio.onended = () => {
            setIsSpeaking(false);
            setSpeakingSource(null);
            if (audioPlaybackUrlRef.current) {
              URL.revokeObjectURL(audioPlaybackUrlRef.current);
              audioPlaybackUrlRef.current = null;
            }
            deepgramAudioRef.current = null;
          };

          audio.onerror = () => {
            setIsSpeaking(false);
            setSpeakingSource(null);
            if (audioPlaybackUrlRef.current) {
              URL.revokeObjectURL(audioPlaybackUrlRef.current);
              audioPlaybackUrlRef.current = null;
            }
            deepgramAudioRef.current = null;
            // Fallback to browser TTS on audio error
            speakQuestionBrowser(text);
          };

          deepgramAudioRef.current = audio;
          await audio.play();
          return;
        }
      } catch {
        // Deepgram playback failed or rejected by browser autoplay policy -> fallback to browser
      }
    }

    // Fallback to browser speech synthesis
    speakQuestionBrowser(text);
  }, [sessionId, isMuted, speakQuestionBrowser]);

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
    if (deepgramAudioRef.current) {
      try {
        deepgramAudioRef.current.pause();
        deepgramAudioRef.current.currentTime = 0;
      } catch {}
      deepgramAudioRef.current = null;
    }
    if (audioPlaybackUrlRef.current) {
      try {
        URL.revokeObjectURL(audioPlaybackUrlRef.current);
      } catch {}
      audioPlaybackUrlRef.current = null;
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }
    setIsSpeaking(false);
    setSpeakingSource(null);
  };

  const handleToggleMute = () => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next) {
        handleStopSpeech();
      }
      return next;
    });
  };

  // Helper to safely stop all media tracks
  const stopMediaStreamTracks = () => {
    if (mediaStreamRef.current) {
      try {
        mediaStreamRef.current.getTracks().forEach((track) => {
          track.stop();
        });
      } catch {}
      mediaStreamRef.current = null;
    }
  };

  // Deepgram Audio Recording handlers
  const startDeepgramRecording = async () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setSpeechError('Microphone recording is not supported in this browser. Please use browser speech recognition or type manually.');
      return;
    }

    setSpeechError(null);
    stopVoiceRecognition(); // Stop browser speech recognition if active

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      let mimeType = 'audio/webm';
      if (typeof MediaRecorder !== 'undefined') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
          mimeType = 'audio/webm;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4';
        } else if (MediaRecorder.isTypeSupported('audio/wav')) {
          mimeType = 'audio/wav';
        }
      }

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      audioChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstart = () => {
        setIsRecordingAudio(true);
        recordingStartTimeRef.current = Date.now();
      };

      recorder.onerror = () => {
        stopMediaStreamTracks();
        setIsRecordingAudio(false);
        setSpeechError('Microphone recording error occurred. Manual typing remains active.');
      };

      recorder.onstop = async () => {
        stopMediaStreamTracks();
        setIsRecordingAudio(false);

        const chunks = [...audioChunksRef.current];
        audioChunksRef.current = [];

        if (chunks.length === 0) {
          return;
        }

        const durationMs = recordingStartTimeRef.current ? Date.now() - recordingStartTimeRef.current : 0;
        if (durationMs < 400) {
          setSpeechError('Recording was too short to transcribe. Please speak clearly and try again.');
          return;
        }

        const audioBlob = new Blob(chunks, { type: mimeType });
        if (audioBlob.size < 500) {
          setSpeechError('Recorded audio contained no audible speech signal. Please try again or type manually.');
          return;
        }

        setIsTranscribingAudio(true);
        const res = await transcribeInterviewAudio(sessionId, audioBlob);
        setIsTranscribingAudio(false);

        if (res.success && res.data?.transcript?.trim()) {
          const transcript = res.data.transcript.trim();
          setAnswerText((prev) => (prev.trim() ? `${prev.trim()} ${transcript}` : transcript));
          setSpeechError(null);
        } else {
          const errMsg = res.error || 'No speech detected in audio clip.';
          setSpeechError(`${errMsg} You can speak again, use browser dictation, or type manually.`);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250); // Slice chunks every 250ms
    } catch (err) {
      stopMediaStreamTracks();
      setIsRecordingAudio(false);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setSpeechError('Microphone permission was denied. Please allow microphone access in your browser or continue typing manually.');
      } else {
        setSpeechError('Could not access microphone hardware. Please continue typing manually.');
      }
    }
  };

  const stopDeepgramRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {}
    }
  };

  const cancelDeepgramRecording = () => {
    audioChunksRef.current = [];
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {}
    }
    stopMediaStreamTracks();
    setIsRecordingAudio(false);
  };

  // Browser Speech recognition handlers (fallback/live dictation)
  const startVoiceRecognition = () => {
    if (!isSpeechRecognitionSupported) {
      setSpeechError('Speech recognition is not supported in this browser. Please type your response manually.');
      return;
    }

    setSpeechError(null);
    if (isRecordingAudio) {
      cancelDeepgramRecording();
    }

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

  // Safe global cleanup on unmount: stop audio playback, recordings & microphone tracks
  useEffect(() => {
    return () => {
      // 1. Deepgram TTS audio element
      if (deepgramAudioRef.current) {
        try {
          deepgramAudioRef.current.pause();
          deepgramAudioRef.current = null;
        } catch {}
      }
      if (audioPlaybackUrlRef.current) {
        try {
          URL.revokeObjectURL(audioPlaybackUrlRef.current);
          audioPlaybackUrlRef.current = null;
        } catch {}
      }
      // 2. Browser speech synthesis
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        try {
          window.speechSynthesis.cancel();
        } catch {}
      }
      // 3. Deepgram MediaRecorder and microphone tracks
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch {}
      }
      stopMediaStreamTracks();
      // 4. Browser speech recognition
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
    };
  }, []);

  // 1. Initialize or resume session
  const initSession = useCallback(async (isRetry = false) => {
    if (!assignmentId) return;
    if (isRetry) {
      setIsRetrying(true);
    } else {
      setLoading(true);
    }
    setError(null);
    setErrorType(null);

    // Step A: Check if assignment already has an active or completed session
    const checkRes = await getAssignmentSession(assignmentId);
    let sess = null;

    if (checkRes.success && checkRes.data?.has_session) {
      const existing = checkRes.data;
      if (existing.session_status === 'in_progress' || existing.session_status === 'completed') {
        sess = existing;
      } else if (existing.session_status === 'timed_out') {
        setError('Interview session duration has expired. Active attempt timed out.');
        setErrorType('EXPIRED');
        setLoading(false);
        setIsRetrying(false);
        return;
      }
    }

    if (!sess) {
      // Step B: No session exists yet, start a new attempt
      const startRes = await startInterviewSession(assignmentId);
      if (!startRes.success) {
        if (startRes.status === 409) {
          const retryCheck = await getAssignmentSession(assignmentId);
          if (retryCheck.success && retryCheck.data?.has_session) {
            if (retryCheck.data.session_status === 'timed_out') {
              setError('Interview session duration has expired. Active attempt timed out.');
              setErrorType('EXPIRED');
            } else {
              sess = retryCheck.data;
            }
          } else {
            setError(startRes.error || 'Active interview session conflict encountered.');
            setErrorType('CONFLICT');
          }
          if (!sess) {
            setLoading(false);
            setIsRetrying(false);
            return;
          }
        } else if (startRes.status >= 500) {
          setError(startRes.error || 'The interview AI evaluation engine is temporarily unavailable. Please retry in a moment.');
          setErrorType('SERVER');
          setLoading(false);
          setIsRetrying(false);
          return;
        } else if (!startRes.status || startRes.status === 0) {
          setError('Unable to reach the interview service. Please verify network connectivity.');
          setErrorType('NETWORK');
          setLoading(false);
          setIsRetrying(false);
          return;
        } else {
          const errLower = (startRes.error || '').toLowerCase();
          if (errLower.includes('expired') || errLower.includes('timed out')) {
            setError(startRes.error || 'Interview session duration has expired.');
            setErrorType('EXPIRED');
          } else {
            setError(startRes.error || 'Failed to initialize interview session.');
            setErrorType('GENERIC');
          }
          setLoading(false);
          setIsRetrying(false);
          return;
        }
      } else {
        sess = startRes.data;
      }
    }

    if (!sess) {
      setError('Could not retrieve interview session data. Please try again.');
      setErrorType('GENERIC');
      setLoading(false);
      setIsRetrying(false);
      return;
    }

    setSessionId(sess.session_id);

    // Check backend voice integration status asynchronously
    getVoiceStatus(sess.session_id).then((vRes) => {
      if (vRes.success && vRes.data) {
        setVoiceStatus(vRes.data);
      }
    }).catch(() => {});

    // If session is already completed, load scorecard directly
    if (sess.session_status === 'completed' && (sess.scorecard_id || sess.final_scorecard_id)) {
      setIsCompleted(true);
      const scRes = await getSessionScorecard(sess.session_id);
      if (scRes.success) {
        setScorecard(scRes.data);
      }
      setLoading(false);
      setIsRetrying(false);
      return;
    }

    if (sess.session_status === 'timed_out') {
      setError('Interview session duration has expired. Active attempt timed out.');
      setErrorType('EXPIRED');
      setLoading(false);
      setIsRetrying(false);
      return;
    }

    // Set countdown timer: prioritize server-verified integer seconds, fallback to ISO expires_at
    if (sess.time_remaining_seconds != null && sess.time_remaining_seconds >= 0) {
      setSecondsRemaining(sess.time_remaining_seconds);
    } else if (sess.expires_at) {
      const exp = new Date(sess.expires_at).getTime();
      const now = Date.now();
      const diffSecs = Math.max(0, Math.floor((exp - now) / 1000));
      setSecondsRemaining(diffSecs);
    }

    // Universal resolution of active question (supports both flat and nested schemas)
    const qText =
      sess.active_question?.question_text ||
      sess.active_question?.question ||
      sess.question_text ||
      sess.question ||
      '';

    const qTopic =
      sess.active_question?.topic ||
      sess.topic ||
      sess.interview_title ||
      'Core Fundamentals';

    const qDiff =
      sess.active_question?.difficulty ||
      sess.difficulty ||
      sess.current_difficulty ||
      'medium';

    const qType =
      sess.active_question?.question_type ||
      sess.question_type ||
      'conceptual';

    const qIndex =
      sess.question_index ??
      sess.current_question_index ??
      sess.active_question?.question_index ??
      1;

    const qTotal =
      sess.total_questions ??
      sess.total_questions_target ??
      sess.active_question?.total_questions ??
      5;

    const qEvalMode =
      sess.evaluator_mode ||
      sess.active_question?.evaluator_mode ||
      'mock_rule_engine';

    const qTitle =
      sess.interview_title ||
      sess.active_question?.interview_title ||
      '';

    const qCodingSpec = sess.active_question?.coding_spec || sess.coding_spec || null;

    if (qText) {
      setActiveQuestion({
        session_id: sess.session_id,
        question_index: qIndex,
        total_questions: qTotal,
        question_text: qText,
        topic: qTopic,
        difficulty: qDiff,
        question_type: qType,
        evaluator_mode: qEvalMode,
        interview_title: qTitle,
        coding_spec: qCodingSpec,
      });

      setExecutionResult(null);
      setUseCustomInput(false);
      setCustomInputText('');

      if (qType === 'coding') {
        setAnswerText(CODE_TEMPLATES[selectedLanguage] || CODE_TEMPLATES['Python']);
      }
    } else {
      setError('Unable to load question text for this interview. Please return to the dashboard or try again.');
    }

    setLoading(false);
  }, [assignmentId, selectedLanguage]);

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

  // Tab key indentation support in code editor
  const handleEditorKeyDown = (e) => {
    if (activeQuestion?.question_type === 'coding' && e.key === 'Tab') {
      e.preventDefault();
      const { selectionStart, selectionEnd } = e.target;
      const val = answerText;
      const tabSpaces = '    ';
      setAnswerText(val.substring(0, selectionStart) + tabSpaces + val.substring(selectionEnd));
      setTimeout(() => {
        if (e.target) {
          e.target.selectionStart = e.target.selectionEnd = selectionStart + tabSpaces.length;
        }
      }, 0);
    }
  };

  // Run Code in isolated sandbox against custom input or sample visible test cases
  const handleRunCode = async () => {
    if (!sessionId || !activeQuestion || runningCode || !answerText.trim()) return;
    setRunningCode(true);
    setExecutionResult(null);

    const lang = selectedLanguage.toLowerCase() === 'c++' ? 'cpp' : selectedLanguage.toLowerCase();
    const payload = {
      language: lang,
      source_code: answerText,
      custom_input: useCustomInput && customInputText.trim() ? customInputText : null,
    };

    const res = await runInterviewCode(sessionId, payload);
    setRunningCode(false);

    if (res.success) {
      setExecutionResult(res.data);
      setSelectedTestCaseTab(0);
    } else {
      setExecutionResult({
        status: 'SERVICE_UNAVAILABLE',
        message: res.error || 'Code execution service is currently unavailable.',
        stderr: res.error,
        test_case_results: [],
        total_test_cases: 0,
        passed_test_cases: 0,
      });
    }
  };

  // Submit Answer or Coding Solution
  const handleSubmitAnswer = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (!answerText.trim() || submitting || !sessionId) return;

    // Immediately stop audio speech and voice dictation on submit
    handleStopSpeech();
    stopVoiceRecognition();
    if (isRecordingAudio) {
      cancelDeepgramRecording();
    }

    setSubmitting(true);
    setError(null);

    const isCoding = activeQuestion?.question_type === 'coding';
    const lang = selectedLanguage.toLowerCase() === 'c++' ? 'cpp' : selectedLanguage.toLowerCase();

    let res;
    if (isCoding) {
      res = await submitInterviewCode(sessionId, {
        language: lang,
        source_code: answerText.trim(),
      });
    } else {
      res = await submitInterviewAnswer(sessionId, answerText.trim());
    }

    setSubmitting(false);

    if (!res.success) {
      setError(res.error || 'Failed to submit solution. Please check compiler output or retry.');
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
      codeExecutionSummary: data.code_execution_summary ?? null,
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
      handleStopSpeech();
      stopVoiceRecognition();
      if (isRecordingAudio) {
        cancelDeepgramRecording();
      }
      setIsTranscribingAudio(false);
      setSpeechError(null);
      setInterimTranscript('');
      setExecutionResult(null);
      setUseCustomInput(false);
      setCustomInputText('');

      const nextText =
        pendingNextQuestion.question_text ||
        pendingNextQuestion.question ||
        pendingNextQuestion.active_question?.question_text ||
        pendingNextQuestion.active_question?.question ||
        '';

      const nextTopic =
        pendingNextQuestion.topic ||
        pendingNextQuestion.active_question?.topic ||
        activeQuestion?.topic ||
        'Core Fundamentals';

      const nextDiff =
        pendingNextQuestion.difficulty ||
        pendingNextQuestion.active_question?.difficulty ||
        'medium';

      const nextType =
        pendingNextQuestion.question_type ||
        pendingNextQuestion.active_question?.question_type ||
        'conceptual';

      const nextIndex =
        pendingNextQuestion.question_index ??
        (activeQuestion?.question_index ? activeQuestion.question_index + 1 : 2);

      const nextCodingSpec =
        pendingNextQuestion.coding_spec ||
        pendingNextQuestion.active_question?.coding_spec ||
        null;

      setActiveQuestion((prev) => ({
        ...prev,
        question_index: nextIndex,
        question_text: nextText,
        topic: nextTopic,
        difficulty: nextDiff,
        question_type: nextType,
        coding_spec: nextCodingSpec,
        evaluator_mode: pendingNextQuestion.evaluator_mode || prev?.evaluator_mode,
      }));
      if (nextType === 'coding') {
        setAnswerText(CODE_TEMPLATES[selectedLanguage] || CODE_TEMPLATES['Python'] || '');
      } else {
        setAnswerText('');
      }
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

  if (error && (!activeQuestion || !activeQuestion.question_text) && !scorecard) {
    const isExpired = errorType === 'EXPIRED' || (error && (error.toLowerCase().includes('expired') || error.toLowerCase().includes('timed out')));
    const isNetwork = errorType === 'NETWORK';
    const isServer = errorType === 'SERVER';
    const isConflict = errorType === 'CONFLICT';

    return (
      <div className="min-h-screen bg-[#070b14] text-slate-100 flex items-center justify-center p-4 selection:bg-cyan-500/30">
        <div className="w-full max-w-lg rounded-2xl bg-slate-900/80 border border-slate-800 shadow-2xl backdrop-blur-xl p-6 sm:p-8 relative overflow-hidden">
          {/* Top accent line */}
          <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${
            isExpired
              ? 'from-amber-500 via-rose-500 to-red-500'
              : isNetwork
              ? 'from-amber-500 via-orange-500 to-yellow-500'
              : isServer
              ? 'from-violet-500 via-indigo-500 to-cyan-500'
              : 'from-cyan-500 via-indigo-500 to-violet-500'
          }`} />

          {/* Contextual Icon Header */}
          <div className="flex flex-col items-center text-center mb-6">
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-4 shadow-lg ${
              isExpired
                ? 'bg-amber-950/60 text-amber-400 border border-amber-800/60 shadow-amber-950/40'
                : isNetwork
                ? 'bg-blue-950/60 text-blue-400 border border-blue-800/60 shadow-blue-950/40'
                : isServer
                ? 'bg-violet-950/60 text-violet-400 border border-violet-800/60 shadow-violet-950/40'
                : 'bg-rose-950/60 text-rose-400 border border-rose-800/60 shadow-rose-950/40'
            }`}>
              {isExpired ? (
                <Clock className="w-7 h-7" />
              ) : isNetwork ? (
                <WifiOff className="w-7 h-7" />
              ) : isServer ? (
                <ServerCrash className="w-7 h-7" />
              ) : (
                <ShieldAlert className="w-7 h-7" />
              )}
            </div>

            <div className={`inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider mb-2.5 border ${
              isExpired
                ? 'bg-amber-950/80 text-amber-300 border-amber-800/60'
                : isNetwork
                ? 'bg-blue-950/80 text-blue-300 border-blue-800/60'
                : isServer
                ? 'bg-violet-950/80 text-violet-300 border-violet-800/60'
                : 'bg-rose-950/80 text-rose-300 border-rose-800/60'
            }`}>
              <span>
                {isExpired
                  ? 'Session Expiry'
                  : isNetwork
                  ? 'Connectivity Notice'
                  : isServer
                  ? 'AI Evaluator Disruption'
                  : isConflict
                  ? 'Duplicate Window'
                  : 'Question Access Notice'}
              </span>
            </div>

            <h2 className="text-xl font-bold text-white tracking-tight">
              {isExpired
                ? 'Interview Session Duration Expired'
                : isNetwork
                ? 'Connection Disruption'
                : isServer
                ? 'AI Engine Temporarily Unavailable'
                : isConflict
                ? 'Active Session Already Open'
                : 'Unable to Load Interview Session'}
            </h2>

            <p className="text-xs text-slate-400 mt-2 leading-relaxed max-w-md">
              {isExpired
                ? 'The scheduled duration for this interview attempt has elapsed. To uphold standardized assessment fairness, timed-out sessions are automatically closed.'
                : isNetwork
                ? 'A network interruption prevented contact with the VFSTR interview servers. Your attempt status remains intact.'
                : isServer
                ? 'The adaptive interview AI engine is currently experiencing heavy load or a transient cold start. No progress has been lost.'
                : isConflict
                ? 'An active attempt is already in progress for this assignment in another window or tab.'
                : error}
            </p>
          </div>

          {/* Contextual guidance card */}
          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs text-slate-300 mb-6 space-y-1.5 leading-relaxed font-mono">
            <div className="flex items-center justify-between text-[11px] text-slate-400 border-b border-slate-800/60 pb-1.5 font-sans">
              <span>Status Detail</span>
              <span className="font-mono text-cyan-400">Assignment: {assignmentId}</span>
            </div>
            <p className="text-[11px] text-slate-400 pt-0.5 font-sans">
              {isExpired
                ? 'You can return to the dashboard to review verified question banks or initiate a fresh mock interview attempt.'
                : 'Click retry to re-establish connection and load the active question.'}
            </p>
          </div>

          {/* Action buttons with loading states & duplicate prevention */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            {!isExpired && (
              <button
                onClick={() => initSession(true)}
                disabled={isRetrying || loading}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-cyan-600/20 transition flex items-center justify-center space-x-2 disabled:opacity-50"
              >
                {isRetrying ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Reconnecting...</span>
                  </>
                ) : (
                  <>
                    <RotateCcw className="w-4 h-4" />
                    <span>Retry Connection</span>
                  </>
                )}
              </button>
            )}

            <Link
              to="/dashboard"
              className={`w-full sm:w-auto px-5 py-2.5 rounded-xl text-xs font-semibold transition flex items-center justify-center space-x-2 ${
                isExpired
                  ? 'bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white shadow-lg shadow-cyan-600/20'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700'
              }`}
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Return to Dashboard</span>
            </Link>
          </div>
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
              {(scorecard.strengths || scorecard.strengths_summary) && (scorecard.strengths || scorecard.strengths_summary).length > 0 ? (
                <ul className="space-y-2 text-xs text-slate-300">
                  {(scorecard.strengths || scorecard.strengths_summary).map((str, i) => (
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
                        <span className="text-sm font-bold text-indigo-300 font-mono">{item.score ?? item.evaluation_score}</span>
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
              Question {activeQuestion?.question_index || 1} of {activeQuestion?.total_questions || 5}
            </span>
            <span className="text-slate-600">•</span>
            <span className="text-xs text-slate-300 font-medium">Topic: {activeQuestion?.topic || 'Core Fundamentals'}</span>
            <span className="text-slate-600">•</span>
            {activeQuestion?.question_type === 'coding' ? (
              <span className="text-[11px] font-mono font-bold text-cyan-300 px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-800/60 flex items-center space-x-1">
                <Terminal className="w-3 h-3 text-cyan-400" />
                <span>Coding Problem</span>
              </span>
            ) : (
              <span className="text-[11px] font-mono text-slate-400 px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                Conceptual
              </span>
            )}
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
                  <span className="text-[11px] text-slate-400">
                    {speakingSource === 'deepgram'
                      ? 'Deepgram Aura Voice'
                      : speakingSource === 'browser'
                      ? 'Browser Speech Voice'
                      : voiceStatus?.configured
                      ? 'Deepgram Voice Ready'
                      : 'Browser Voice Ready'}
                  </span>
                </div>
                {/* Speaking State Pill */}
                <div className="flex items-center space-x-1.5 mt-0.5">
                  {isSpeaking ? (
                    <span className="text-[11px] font-semibold text-emerald-300 flex items-center space-x-1 animate-pulse">
                      <Radio className="w-3 h-3 text-emerald-400 animate-ping" />
                      <span>
                        {speakingSource === 'deepgram'
                          ? 'Speaking via Deepgram Aura...'
                          : 'Speaking Question Aloud...'}
                      </span>
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
              {activeQuestion?.question_text || (
                <div className="flex items-center space-x-2 text-rose-400 text-xs py-1">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>Interview question could not be loaded. Please click Retry below or refresh.</span>
                </div>
              )}
            </div>

            {activeQuestion?.question_type === 'coding' ? (
              <p className="text-xs text-cyan-400 font-mono">
                Coding Assessment: Write and execute your solution in <strong>{selectedLanguage}</strong>. Use "Run Code" to test against sample test cases in the isolated sandbox, then click "Submit Solution" for full automated evaluation.
              </p>
            ) : (
              <p className="text-xs text-slate-400 italic">
                Instructions: Provide a structured, technical response explaining protocol mechanics, packet flows, or architecture where applicable.
              </p>
            )}

            {/* Problem Specifications & Sample Test Cases (For Coding Questions) */}
            {activeQuestion?.question_type === 'coding' && activeQuestion?.coding_spec && (
              <div className="mt-4 p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3 animate-in fade-in text-xs">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                  <span className="font-mono font-bold text-cyan-300 flex items-center space-x-1.5">
                    <Layers className="w-3.5 h-3.5" />
                    <span>Problem Specifications & Constraints</span>
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">
                    Sandboxed Evaluation Suite: {activeQuestion.coding_spec.total_evaluation_test_cases || 5} Cases
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-slate-300">
                  <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80">
                    <span className="block font-bold text-slate-400 text-[11px] uppercase tracking-wider mb-1">Input Format</span>
                    <p className="font-mono text-slate-200 whitespace-pre-line">{activeQuestion.coding_spec.input_format}</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80">
                    <span className="block font-bold text-slate-400 text-[11px] uppercase tracking-wider mb-1">Output Format</span>
                    <p className="font-mono text-slate-200 whitespace-pre-line">{activeQuestion.coding_spec.output_format}</p>
                  </div>
                </div>

                {activeQuestion.coding_spec.constraints && (
                  <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 font-mono text-[11px] text-slate-300">
                    <strong className="text-slate-400 uppercase tracking-wider mr-2">Constraints:</strong>
                    <span>{activeQuestion.coding_spec.constraints}</span>
                  </div>
                )}

                {/* Visible Sample Test Cases */}
                {activeQuestion.coding_spec.sample_test_cases && activeQuestion.coding_spec.sample_test_cases.length > 0 && (
                  <div className="space-y-2 pt-1">
                    <span className="block font-bold text-slate-400 text-[11px] uppercase tracking-wider">
                      Sample Test Cases:
                    </span>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {activeQuestion.coding_spec.sample_test_cases.map((sc, sIdx) => (
                        <div key={sIdx} className="p-3 rounded-lg bg-slate-950 border border-slate-800 font-mono text-[11px] space-y-1.5">
                          <div className="text-indigo-400 font-bold">Sample Case {sc.test_case_index}:</div>
                          <div className="text-slate-400">
                            <strong>Input:</strong> <span className="text-slate-200">{sc.input_data.replace(/\n/g, ' ')}</span>
                          </div>
                          <div className="text-slate-400">
                            <strong>Expected Output:</strong> <span className="text-emerald-400">{sc.expected_output.replace(/\n/g, ' ')}</span>
                          </div>
                          {sc.explanation && (
                            <div className="text-slate-500 text-[10px] italic">Note: {sc.explanation}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Response Workspace */}
        <form onSubmit={handleSubmitAnswer} className="space-y-4 flex-1 flex flex-col justify-between">
          <div className="space-y-3 flex-1">
            {activeQuestion?.question_type === 'coding' ? (
              /* Coding Workspace Controls */
              <div className="space-y-3">
                {/* Compiler Toolbar */}
                <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-wrap items-center justify-between gap-3 shadow-lg">
                  <div className="flex items-center flex-wrap gap-2">
                    <span className="text-xs font-medium text-slate-300 flex items-center space-x-1.5 mr-1">
                      <Terminal className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Language:</span>
                    </span>
                    {['Python', 'Java', 'C', 'C++'].map((lang) => (
                      <button
                        key={lang}
                        type="button"
                        onClick={() => handleLanguageSelect(lang)}
                        disabled={submitting || runningCode}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition ${
                          selectedLanguage === lang
                            ? 'bg-cyan-600 text-white shadow-md shadow-cyan-600/30'
                            : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
                        }`}
                      >
                        {lang}
                      </button>
                    ))}

                    <span className="text-slate-700 mx-1">|</span>

                    <button
                      type="button"
                      onClick={() => setUseCustomInput(!useCustomInput)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-mono transition border ${
                        useCustomInput
                          ? 'bg-indigo-950/80 text-indigo-300 border-indigo-700 font-semibold'
                          : 'bg-slate-800/80 text-slate-400 border-slate-700 hover:text-slate-200'
                      }`}
                    >
                      {useCustomInput ? '✓ Custom Input Active' : '+ Custom Input (stdin)'}
                    </button>
                  </div>

                  {/* Sandbox Run & Submit Buttons */}
                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      onClick={handleRunCode}
                      id="run-code-btn"
                      disabled={runningCode || submitting || !answerText.trim()}
                      className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-800/60 hover:border-cyan-600 text-xs font-semibold flex items-center space-x-1.5 transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {runningCode ? (
                        <>
                          <RotateCcw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                          <span>Executing Sandbox...</span>
                        </>
                      ) : (
                        <>
                          <PlayCircle className="w-4 h-4 text-cyan-400" />
                          <span>Run Code</span>
                        </>
                      )}
                    </button>

                    <button
                      type="submit"
                      id="submit-solution-btn"
                      disabled={submitting || runningCode || !answerText.trim()}
                      className="px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition flex items-center space-x-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {submitting ? (
                        <>
                          <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                          <span>Evaluating Solution...</span>
                        </>
                      ) : (
                        <>
                          <span>Submit Solution</span>
                          <Send className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Code Editor */}
                <div className="relative rounded-xl border border-slate-800 overflow-hidden bg-slate-950 shadow-inner">
                  <div className="flex items-center justify-between px-3.5 py-1.5 bg-slate-900 border-b border-slate-800 text-[11px] font-mono text-slate-400">
                    <div className="flex items-center space-x-2">
                      <Code className="w-3.5 h-3.5 text-cyan-400" />
                      <span>{selectedLanguage} Editor (Tab Key Indentation Supported)</span>
                    </div>
                    <span>{answerText.length} characters</span>
                  </div>
                  <textarea
                    id="student-answer"
                    rows={12}
                    value={answerText}
                    onChange={(e) => setAnswerText(e.target.value)}
                    onKeyDown={handleEditorKeyDown}
                    disabled={submitting || !!lastEvaluation}
                    placeholder={`Write your ${selectedLanguage} solution here...`}
                    className="w-full bg-slate-950 text-slate-100 placeholder-slate-600 text-xs font-mono p-4 resize-y outline-none leading-relaxed focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                  />
                </div>

                {/* Custom Input Field (stdin) */}
                {useCustomInput && (
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5 animate-in fade-in">
                    <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
                      <span className="font-semibold text-slate-300">Custom Input (stdin):</span>
                      <span>Passed directly to program during "Run Code"</span>
                    </div>
                    <textarea
                      rows={3}
                      value={customInputText}
                      onChange={(e) => setCustomInputText(e.target.value)}
                      placeholder="Enter custom input lines here..."
                      className="w-full rounded-lg bg-slate-900/90 border border-slate-800 text-slate-200 text-xs font-mono p-3 resize-none focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                )}

                {/* Execution & Test Results Panel */}
                {executionResult && (
                  <div className="p-4 rounded-xl glass-panel border border-slate-800 bg-slate-950/95 space-y-3 animate-in fade-in">
                    <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-slate-800/80">
                      <div className="flex items-center space-x-2.5">
                        <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400">Execution Result:</span>
                        <span className={`px-2.5 py-0.5 rounded text-xs font-mono font-bold flex items-center space-x-1 ${
                          executionResult.status === 'SUCCESS'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/80'
                            : executionResult.status === 'WRONG_ANSWER'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800/80'
                            : 'bg-rose-950 text-rose-300 border border-rose-800/80'
                        }`}>
                          {executionResult.status === 'SUCCESS' ? (
                            <>
                              <CheckCircle className="w-3 h-3 text-emerald-400" />
                              <span>Accepted</span>
                            </>
                          ) : executionResult.status === 'WRONG_ANSWER' ? (
                            <>
                              <XCircle className="w-3 h-3 text-amber-400" />
                              <span>Wrong Answer</span>
                            </>
                          ) : (
                            <>
                              <AlertCircle className="w-3 h-3 text-rose-400" />
                              <span>{executionResult.status.replace('_', ' ')}</span>
                            </>
                          )}
                        </span>
                      </div>

                      <div className="flex items-center space-x-3 text-xs font-mono text-slate-400">
                        {executionResult.execution_time_ms != null && (
                          <span>Runtime: <strong className="text-cyan-300">{executionResult.execution_time_ms} ms</strong></span>
                        )}
                        {executionResult.total_test_cases > 0 && (
                          <span className={executionResult.passed_test_cases === executionResult.total_test_cases ? 'text-emerald-400' : 'text-amber-400'}>
                            Sample Tests: <strong>{executionResult.passed_test_cases} / {executionResult.total_test_cases} Passed</strong>
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Compilation Errors Output */}
                    {(executionResult.compile_output || (executionResult.status === 'COMPILATION_ERROR' && executionResult.stderr)) && (
                      <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-900/60 font-mono text-xs text-rose-300 space-y-1">
                        <div className="font-bold text-rose-400 flex items-center space-x-1">
                          <AlertCircle className="w-3.5 h-3.5" />
                          <span>Compiler / Build Error:</span>
                        </div>
                        <pre className="whitespace-pre-wrap overflow-x-auto text-[11px] leading-relaxed">
                          {executionResult.compile_output || executionResult.stderr}
                        </pre>
                      </div>
                    )}

                    {/* Runtime Errors Output */}
                    {executionResult.status === 'RUNTIME_ERROR' && executionResult.stderr && (
                      <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-900/60 font-mono text-xs text-rose-300 space-y-1">
                        <div className="font-bold text-rose-400">Runtime Exception:</div>
                        <pre className="whitespace-pre-wrap overflow-x-auto text-[11px] leading-relaxed">
                          {executionResult.stderr}
                        </pre>
                      </div>
                    )}

                    {/* Test Case Tab Selector */}
                    {executionResult.test_case_results && executionResult.test_case_results.length > 0 && (
                      <div className="space-y-2">
                        <div className="flex items-center space-x-2">
                          {executionResult.test_case_results.map((tc, tcIdx) => (
                            <button
                              key={tcIdx}
                              type="button"
                              onClick={() => setSelectedTestCaseTab(tcIdx)}
                              className={`px-3 py-1 rounded text-xs font-mono font-medium flex items-center space-x-1.5 transition ${
                                selectedTestCaseTab === tcIdx
                                  ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                                  : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-900'
                              }`}
                            >
                              <span className={`w-2 h-2 rounded-full ${tc.passed ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                              <span>Case {tc.test_case_index}</span>
                            </button>
                          ))}
                        </div>

                        {/* Selected Test Case Details */}
                        {executionResult.test_case_results[selectedTestCaseTab] && (
                          <div className="p-3 rounded-lg bg-slate-900/90 border border-slate-800 font-mono text-xs space-y-2">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                              <div>
                                <span className="text-slate-400 block mb-0.5">Input:</span>
                                <div className="p-2 rounded bg-slate-950 text-slate-200 border border-slate-800">
                                  {executionResult.test_case_results[selectedTestCaseTab].input_data || '(none)'}
                                </div>
                              </div>
                              <div>
                                <span className="text-slate-400 block mb-0.5">Expected Output:</span>
                                <div className="p-2 rounded bg-slate-950 text-emerald-400 border border-slate-800">
                                  {executionResult.test_case_results[selectedTestCaseTab].expected_output || '(none)'}
                                </div>
                              </div>
                            </div>

                            <div>
                              <span className="text-slate-400 block mb-0.5 text-[11px]">Program Actual Output:</span>
                              <div className={`p-2 rounded bg-slate-950 border ${
                                executionResult.test_case_results[selectedTestCaseTab].passed
                                  ? 'text-emerald-300 border-slate-800'
                                  : 'text-rose-300 border-rose-900/60'
                              }`}>
                                {executionResult.test_case_results[selectedTestCaseTab].actual_output || '(no stdout output)'}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Custom Input Output Block */}
                    {executionResult.total_test_cases === 0 && (
                      <div className="space-y-2 font-mono text-xs">
                        {executionResult.stdout && (
                          <div>
                            <span className="text-slate-400 block mb-0.5 text-[11px]">Standard Output (stdout):</span>
                            <pre className="p-2.5 rounded bg-slate-900 border border-slate-800 text-slate-200 whitespace-pre-wrap overflow-x-auto text-[11px]">
                              {executionResult.stdout}
                            </pre>
                          </div>
                        )}
                        {executionResult.stderr && executionResult.status !== 'COMPILATION_ERROR' && (
                          <div>
                            <span className="text-rose-400 block mb-0.5 text-[11px]">Standard Error (stderr):</span>
                            <pre className="p-2.5 rounded bg-rose-950/20 border border-rose-900/50 text-rose-300 whitespace-pre-wrap overflow-x-auto text-[11px]">
                              {executionResult.stderr}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              /* Conceptual Response Workspace */
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                  <div className="flex items-center space-x-2">
                    <label htmlFor="student-answer" className="font-semibold text-slate-300">
                      Your Technical Response:
                    </label>

                    <div className="flex items-center flex-wrap gap-2">
                      {/* Deepgram High-Fidelity Voice Recording Button */}
                      <button
                        type="button"
                        onClick={isRecordingAudio ? stopDeepgramRecording : startDeepgramRecording}
                        id="record-voice-deepgram-btn"
                        disabled={submitting || isTranscribingAudio || !!lastEvaluation}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition ${
                          isRecordingAudio
                            ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/30 animate-pulse'
                            : 'bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white shadow-md shadow-indigo-600/20'
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                        title={isRecordingAudio ? "Stop recording and transcribe with Deepgram" : "Record your spoken response for AI transcription"}
                        aria-label={isRecordingAudio ? "Stop recording and transcribe" : "Record spoken answer"}
                      >
                        {isRecordingAudio ? (
                          <>
                            <Square className="w-3 h-3 fill-current text-white" />
                            <span>Done Speaking (Transcribe)</span>
                          </>
                        ) : isTranscribingAudio ? (
                          <>
                            <RotateCcw className="w-3.5 h-3.5 animate-spin text-white" />
                            <span>Transcribing...</span>
                          </>
                        ) : (
                          <>
                            <Mic className="w-3.5 h-3.5 text-white" />
                            <span>Record Voice Answer</span>
                          </>
                        )}
                      </button>

                      {/* Cancel Recording button when active */}
                      {isRecordingAudio && (
                        <button
                          type="button"
                          onClick={cancelDeepgramRecording}
                          id="cancel-voice-recording-btn"
                          className="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
                          title="Discard recording without transcribing"
                        >
                          Cancel
                        </button>
                      )}

                      {/* Live Browser Speech Recognition Button (Live Dictation / Fallback) */}
                      {isSpeechRecognitionSupported && (
                        <button
                          type="button"
                          onClick={handleToggleVoiceInput}
                          id="toggle-voice-input-btn"
                          disabled={submitting || isRecordingAudio || isTranscribingAudio || !!lastEvaluation}
                          className={`px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition ${
                            isListening
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 animate-pulse'
                              : 'bg-slate-800/80 text-slate-400 border border-slate-700/80 hover:text-slate-200'
                          } disabled:opacity-50 disabled:cursor-not-allowed`}
                          title={isListening ? "Stop browser dictation" : "Use browser speech recognition for live typing"}
                          aria-label={isListening ? "Stop browser dictation" : "Live browser dictation"}
                        >
                          {isListening ? (
                            <>
                              <MicOff className="w-3 h-3 text-amber-400" />
                              <span>Stop Browser Dictation</span>
                            </>
                          ) : (
                            <>
                              <Radio className="w-3 h-3 text-indigo-400" />
                              <span>Live Browser Dictation</span>
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center space-x-3 font-mono text-[11px]">
                    <span className={wordCount >= 25 ? 'text-emerald-400' : 'text-slate-400'}>
                      {wordCount} words {wordCount >= 25 ? '✓ (Good depth)' : '(25+ recommended)'}
                    </span>
                    <span>{answerText.length} characters</span>
                  </div>
                </div>

                {/* Active Deepgram Recording Status Banner */}
                {isRecordingAudio && (
                  <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-900/60 text-xs text-rose-200 flex items-center justify-between gap-3 animate-in fade-in">
                    <div className="flex items-center space-x-2.5">
                      <span className="w-3 h-3 rounded-full bg-rose-500 animate-ping shrink-0" />
                      <div>
                        <span className="font-bold text-white block">Recording voice answer...</span>
                        <span className="text-[11px] text-rose-300">Speak clearly. When finished, click "Done Speaking" to transcribe into your response.</span>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2 shrink-0">
                      <button
                        type="button"
                        onClick={stopDeepgramRecording}
                        className="px-3 py-1 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow"
                      >
                        Done Speaking
                      </button>
                      <button
                        type="button"
                        onClick={cancelDeepgramRecording}
                        className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Deepgram Transcription Processing Banner */}
                {isTranscribingAudio && (
                  <div className="p-3 rounded-xl bg-indigo-950/40 border border-indigo-900/60 text-xs text-indigo-200 flex items-center space-x-2.5 animate-in fade-in">
                    <RotateCcw className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />
                    <div>
                      <span className="font-bold text-white block">Transcribing Audio with Deepgram AI...</span>
                      <span className="text-[11px] text-indigo-300">Processing spoken response using neural speech models. Please wait a moment.</span>
                    </div>
                  </div>
                )}

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
                  placeholder="Speak or type your explanation here. You can use voice input above or type manually. Be specific with technical architecture, operational mechanisms, and design trade-offs..."
                  className="w-full rounded-xl bg-slate-950/80 border border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-slate-100 placeholder-slate-600 text-xs font-mono p-4 resize-none transition leading-relaxed disabled:opacity-50"
                />

                {/* Conceptual Submit Action */}
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
              </>
            )}
          </div>
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
