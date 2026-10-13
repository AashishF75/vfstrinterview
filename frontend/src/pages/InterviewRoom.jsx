import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  getAssignmentSession,
  startInterviewSession,
  getCurrentQuestion,
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
import TalkingInterviewerAvatar from '../components/TalkingInterviewerAvatar';
import aiInterviewerImg from '../assets/ai_interviewer.jpg';
import candidateAvatarImg from '../assets/candidate_avatar.jpg';
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
  PhoneOff,
  Video,
  VideoOff,
  Settings,
  HelpCircle,
  MessageSquare,
  Compass,
  Lightbulb,
  Maximize2,
  Keyboard,
  Check,
  X,
  User,
  Sliders,
  Briefcase,
  BookOpen,
  Info,
} from 'lucide-react';

export default function InterviewRoom() {
  const { assignmentId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

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

  // Navigation & Workspace Tabs ('room' | 'navigator' | 'code' | 'notes' | 'guide' | 'chat' | 'feedback' | 'settings')
  const [activeTab, setActiveTab] = useState('room');
  const [inputMode, setInputMode] = useState('voice'); // 'voice' | 'type'
  const [candidateNotes, setCandidateNotes] = useState('');
  const [showEndModal, setShowEndModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showNotesModal, setShowNotesModal] = useState(false);
  const [showGuideModal, setShowGuideModal] = useState(false);
  const [cameraEnabled, setCameraEnabled] = useState(true);

  // Immediate Evaluation Feedback State (between questions)
  const [lastEvaluation, setLastEvaluation] = useState(null);
  const [pendingNextQuestion, setPendingNextQuestion] = useState(null);
  const [isProgressing, setIsProgressing] = useState(false);
  const [progressionError, setProgressionError] = useState(null);
  const evaluationCardRef = useRef(null);

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
    if (!answerText.trim() || Object.values(CODE_TEMPLATES).some((t) => t.trim() === answerText.trim())) {
      setAnswerText(CODE_TEMPLATES[lang] || '');
    }
  };

  // Timer State
  const [secondsRemaining, setSecondsRemaining] = useState(null);
  const timerRef = useRef(null);

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
  const [deepgramAudioInstance, setDeepgramAudioInstance] = useState(null);
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
  const isStartingRecordingRef = useRef(false);

  // Browser Web Speech Recognition fallback state
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState('');
  const [speechError, setSpeechError] = useState(null);
  const recognitionRef = useRef(null);

  // Runtime check for SpeechRecognition support
  const isSpeechRecognitionSupported =
    typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  // --------------------------------------------------------------------------
  // Level 1 Proctoring & Telemetry State
  // --------------------------------------------------------------------------
  const [proctoringConsentGiven, setProctoringConsentGiven] = useState(false);
  const proctoringQueueRef = useRef([]);

  const handleProctoringEvent = useCallback(
    (event) => {
      if (!sessionId) return;
      proctoringQueueRef.current.push(event);
    },
    [sessionId]
  );

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

      if (!isValidBackendUrl) return;
      if (typeof navigator === 'undefined' || !navigator.sendBeacon) return;

      const batch = [...proctoringQueueRef.current];
      try {
        const blob = new Blob([JSON.stringify({ events: batch })], { type: 'application/json' });
        const beaconUrl = `${apiBase}/api/interview-rooms/sessions/${sessionId}/proctoring-events`;
        const accepted = navigator.sendBeacon(beaconUrl, blob);
        if (accepted) {
          proctoringQueueRef.current = proctoringQueueRef.current.slice(batch.length);
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

  // Voice selection helper: Prefer English
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
  const speakQuestionBrowser = useCallback(
    (text) => {
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
    },
    [isMuted, getEnglishVoice]
  );

  // Speech cancellation handler - declared before speakQuestion to eliminate TDZ reference errors
  const handleStopSpeech = useCallback(() => {
    if (deepgramAudioRef.current) {
      try {
        deepgramAudioRef.current.pause();
        deepgramAudioRef.current.currentTime = 0;
      } catch {}
      deepgramAudioRef.current = null;
    }
    setDeepgramAudioInstance(null);
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
  }, []);

  // Master question speaker: Prefers Deepgram TTS (Aura), seamlessly falls back to browser speechSynthesis
  const speakQuestion = useCallback(
    async (text) => {
      if (!text) return;

      handleStopSpeech();

      if (isMuted) {
        setIsSpeaking(false);
        setSpeakingSource(null);
        return;
      }

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
              setDeepgramAudioInstance(null);
            };

            audio.onerror = () => {
              setIsSpeaking(false);
              setSpeakingSource(null);
              if (audioPlaybackUrlRef.current) {
                URL.revokeObjectURL(audioPlaybackUrlRef.current);
                audioPlaybackUrlRef.current = null;
              }
              deepgramAudioRef.current = null;
              setDeepgramAudioInstance(null);
              speakQuestionBrowser(text);
            };

            deepgramAudioRef.current = audio;
            setDeepgramAudioInstance(audio);
            await audio.play();
            return;
          }
        } catch {
          // Playback rejected by autoplay policy -> fallback
        }
      }

      speakQuestionBrowser(text);
    },
    [sessionId, isMuted, speakQuestionBrowser, handleStopSpeech]
  );

  // Auto-speak newly active question once
  useEffect(() => {
    if (!activeQuestion || !activeQuestion.question_text || isCompleted) return;

    if (lastSpokenQuestionIndexRef.current !== activeQuestion.question_index) {
      lastSpokenQuestionIndexRef.current = activeQuestion.question_index;
      if (!isMuted) {
        speakQuestion(activeQuestion.question_text);
      }
    }
  }, [activeQuestion, isMuted, isCompleted, speakQuestion]);

  const handlePlayQuestion = () => {
    if (!activeQuestion?.question_text) return;
    setSpeechBlocked(false);
    speakQuestion(activeQuestion.question_text);
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

  const stopMediaStreamTracks = () => {
    if (mediaStreamRef.current) {
      try {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
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

    if (!sessionId) {
      setSpeechError('Active interview session is not ready. Please refresh or retry.');
      return;
    }

    if (isRecordingAudio || isTranscribingAudio || isStartingRecordingRef.current) {
      return;
    }

    isStartingRecordingRef.current = true;
    setSpeechError(null);
    stopVoiceRecognition();

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      let mimeType = 'audio/webm';
      if (typeof MediaRecorder !== 'undefined') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
          mimeType = 'audio/webm;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/webm')) {
          mimeType = 'audio/webm';
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4';
        } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
          mimeType = 'audio/ogg';
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
        isStartingRecordingRef.current = false;
        recordingStartTimeRef.current = Date.now();
        setSpeechError(null);
      };

      recorder.onerror = () => {
        isStartingRecordingRef.current = false;
        stopMediaStreamTracks();
        setIsRecordingAudio(false);
        setSpeechError('Microphone recording error occurred. Manual typing remains active.');
      };

      recorder.onstop = async () => {
        isStartingRecordingRef.current = false;
        stopMediaStreamTracks();
        setIsRecordingAudio(false);

        const chunks = [...audioChunksRef.current];
        audioChunksRef.current = [];

        if (chunks.length === 0) {
          setSpeechError('No audio data was captured. Please check your microphone and speak clearly.');
          return;
        }

        const audioBlob = new Blob(chunks, { type: recorder.mimeType || mimeType });
        if (audioBlob.size === 0) {
          setSpeechError('Recorded audio contained no audible speech signal. Please try again or type manually.');
          return;
        }

        const durationMs = recordingStartTimeRef.current ? Date.now() - recordingStartTimeRef.current : 0;
        if (durationMs < 200 && audioBlob.size < 80) {
          setSpeechError('Recording was too short to transcribe. Please speak clearly and try again.');
          return;
        }

        setIsTranscribingAudio(true);
        setSpeechError(null);
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
      recorder.start(250);
    } catch (err) {
      isStartingRecordingRef.current = false;
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
        if (mediaRecorderRef.current.state === 'recording') {
          try {
            mediaRecorderRef.current.requestData();
          } catch {}
        }
        mediaRecorderRef.current.stop();
      } catch {}
    }
  };

  const cancelDeepgramRecording = () => {
    audioChunksRef.current = [];
    isStartingRecordingRef.current = false;
    if (mediaRecorderRef.current) {
      try {
        mediaRecorderRef.current.onstop = null;
        mediaRecorderRef.current.ondataavailable = null;
        mediaRecorderRef.current.onerror = null;
        if (mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop();
        }
      } catch {}
      mediaRecorderRef.current = null;
    }
    stopMediaStreamTracks();
    setIsRecordingAudio(false);
  };

  // Browser Speech recognition handlers
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
              setAnswerText((prev) => (prev.trim() ? `${prev.trim()} ${cleanSegment}` : cleanSegment));
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
      } catch {}
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

  // Safe global cleanup on unmount
  useEffect(() => {
    return () => {
      if (deepgramAudioRef.current) {
        try {
          deepgramAudioRef.current.pause();
          deepgramAudioRef.current = null;
        } catch {}
      }
      setDeepgramAudioInstance(null);
      if (audioPlaybackUrlRef.current) {
        try {
          URL.revokeObjectURL(audioPlaybackUrlRef.current);
          audioPlaybackUrlRef.current = null;
        } catch {}
      }
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        try {
          window.speechSynthesis.cancel();
        } catch {}
      }
      if (mediaRecorderRef.current) {
        try {
          mediaRecorderRef.current.onstop = null;
          mediaRecorderRef.current.ondataavailable = null;
          mediaRecorderRef.current.onerror = null;
          if (mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop();
          }
        } catch {}
        mediaRecorderRef.current = null;
      }
      stopMediaStreamTracks();
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
    };
  }, []);

  // Initialize or resume session
  const initSession = useCallback(
    async (isRetry = false) => {
      if (!assignmentId) return;
      if (isRetry) {
        setIsRetrying(true);
      } else {
        setLoading(true);
      }
      setError(null);
      setErrorType(null);

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

      getVoiceStatus(sess.session_id)
        .then((vRes) => {
          if (vRes.success && vRes.data) {
            setVoiceStatus(vRes.data);
          }
        })
        .catch(() => {});

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

      if (sess.time_remaining_seconds != null && sess.time_remaining_seconds >= 0) {
        setSecondsRemaining(sess.time_remaining_seconds);
      } else if (sess.expires_at) {
        const exp = new Date(sess.expires_at).getTime();
        const now = Date.now();
        const diffSecs = Math.max(0, Math.floor((exp - now) / 1000));
        setSecondsRemaining(diffSecs);
      }

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
        'Adaptive Placement Interview';

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
          setActiveTab('code'); // Auto-switch tab to code editor for coding challenge
        }
      } else {
        setError('Unable to load question text for this interview. Please return to the dashboard or try again.');
      }

      setLoading(false);
      setIsRetrying(false);
    },
    [assignmentId, selectedLanguage]
  );

  useEffect(() => {
    initSession();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [initSession]);

  // Countdown timer
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

  const formatTime = (secs) => {
    if (secs === null) return '--:--';
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    return `${mins.toString().padStart(2, '0')}:${rem.toString().padStart(2, '0')}`;
  };

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

  const handleSubmitAnswer = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (!answerText.trim() || submitting || isTranscribingAudio || !sessionId) return;

    handleStopSpeech();
    stopVoiceRecognition();
    if (isRecordingAudio) {
      cancelDeepgramRecording();
    }

    setSubmitting(true);
    setError(null);
    setProgressionError(null);

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
      // Duplicate submission conflict guard (409): check if backend already advanced to next question
      if (res.status === 409 || (res.error && res.error.toLowerCase().includes('already been submitted'))) {
        try {
          const curRes = await getCurrentQuestion(sessionId);
          if (curRes.success && curRes.data) {
            const isComp = curRes.data.is_session_completed || curRes.data.session_status === 'completed';
            const nextIdx = curRes.data.question_index ?? curRes.data.current_question_index;
            if (isComp) {
              setLastEvaluation({
                score: 8.0,
                feedback: 'All questions have been completed and recorded on the server. Ready to view your final scorecard.',
                strengths: ['Interview completed on server'],
                improvements: [],
                difficultyRationale: 'Session synchronized with server completion.',
                codeExecutionSummary: null,
                isFinal: true,
              });
              return;
            } else if (nextIdx > (activeQuestion?.question_index || 1) || curRes.data.question_text !== activeQuestion?.question_text) {
              setPendingNextQuestion(curRes.data);
              setLastEvaluation({
                score: 8.0,
                feedback: 'Your answer for this question was previously submitted and recorded on the server. Ready to proceed to the next question.',
                strengths: ['Answer recorded on server'],
                improvements: [],
                difficultyRationale: 'Session synchronized with server progression.',
                codeExecutionSummary: null,
                isFinal: false,
              });
              return;
            }
          }
        } catch {}
      }

      setError(res.error || 'Failed to submit solution. Please check compiler output or retry.');
      return;
    }

    const data = res.data;

    // Show real evaluation feedback and score
    setLastEvaluation({
      score: data.evaluated_score ?? data.evaluation?.score ?? 0,
      feedback: data.feedback ?? data.evaluation?.feedback ?? '',
      strengths: data.strengths ?? data.evaluation?.strengths ?? [],
      improvements: data.improvements ?? data.evaluation?.improvements ?? [],
      difficultyRationale: data.difficulty_rationale ?? data.difficulty_adjustment_rationale ?? '',
      codeExecutionSummary: data.code_execution_summary ?? null,
      isFinal: !!data.is_session_completed,
    });

    if (data.is_session_completed) {
      // Pre-fetch scorecard in background without prematurely hiding evaluation feedback
      getSessionScorecard(sessionId)
        .then((scRes) => {
          if (scRes.success && scRes.data) {
            setScorecard(scRes.data);
          }
        })
        .catch(() => {});
    } else if (data.next_question) {
      setPendingNextQuestion(data.next_question);
    }

    // Smoothly scroll chat view to evaluation card
    setTimeout(() => {
      if (evaluationCardRef.current) {
        evaluationCardRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }, 120);
  };

  const handleProceedToNextQuestion = async () => {
    if (isProgressing || !sessionId) return;

    handleStopSpeech();
    stopVoiceRecognition();
    if (isRecordingAudio) {
      cancelDeepgramRecording();
    }
    setIsTranscribingAudio(false);
    setSpeechError(null);
    setInterimTranscript('');
    setProgressionError(null);
    setIsProgressing(true);

    try {
      // 1. Authoritative resolution: fetch live from backend current-question endpoint, with pendingNextQuestion as fallback
      let nextData = null;
      try {
        const curRes = await getCurrentQuestion(sessionId);
        if (curRes && curRes.success && curRes.data) {
          nextData = curRes.data;
        }
      } catch {
        // Fallback to locally cached pendingNextQuestion if network fetch encountered an issue
      }

      if (!nextData || (!nextData.question_text && !nextData.question && !nextData.active_question?.question_text)) {
        nextData = pendingNextQuestion;
      }

      if (!nextData) {
        throw new Error('Failed to retrieve next question from server. Please retry.');
      }

      // Check if session reached final completion
      if (nextData.is_session_completed || nextData.session_status === 'completed') {
        await handleViewScorecard();
        setIsProgressing(false);
        return;
      }

      const nextText =
        nextData.question_text ||
        nextData.question ||
        nextData.active_question?.question_text ||
        nextData.active_question?.question ||
        '';

      if (!nextText) {
        throw new Error('Retrieved next question text is empty. Please retry.');
      }

      const nextTopic =
        nextData.topic ||
        nextData.active_question?.topic ||
        activeQuestion?.topic ||
        'Core Fundamentals';

      const nextDiff =
        nextData.difficulty ||
        nextData.current_difficulty ||
        nextData.active_question?.difficulty ||
        'medium';

      const nextType =
        nextData.question_type ||
        nextData.active_question?.question_type ||
        'conceptual';

      const nextIndex =
        nextData.question_index ??
        nextData.current_question_index ??
        nextData.active_question?.question_index ??
        (activeQuestion?.question_index ? activeQuestion.question_index + 1 : 2);

      const nextTotal =
        nextData.total_questions ??
        nextData.total_questions_target ??
        nextData.active_question?.total_questions ??
        activeQuestion?.total_questions ??
        5;

      const nextCodingSpec =
        nextData.coding_spec ||
        nextData.active_question?.coding_spec ||
        null;

      const nextTitle =
        nextData.interview_title ||
        nextData.active_question?.interview_title ||
        activeQuestion?.interview_title ||
        'Adaptive Technical Interview';

      // 2. Update remaining time if provided by backend
      if (nextData.time_remaining_seconds != null && nextData.time_remaining_seconds >= 0) {
        setSecondsRemaining(nextData.time_remaining_seconds);
      }

      // 3. Update active question state using authoritative server data
      setActiveQuestion({
        session_id: sessionId,
        question_index: nextIndex,
        total_questions: nextTotal,
        question_text: nextText,
        topic: nextTopic,
        difficulty: nextDiff,
        question_type: nextType,
        coding_spec: nextCodingSpec,
        interview_title: nextTitle,
        evaluator_mode: nextData.evaluator_mode || activeQuestion?.evaluator_mode,
      });

      // 4. Clear answer draft ONLY after next question is loaded successfully
      if (nextType === 'coding') {
        setAnswerText(CODE_TEMPLATES[selectedLanguage] || CODE_TEMPLATES['Python'] || '');
        setActiveTab('code');
      } else {
        setAnswerText('');
        setActiveTab('room');
      }

      // 5. Reset execution result and evaluation state
      setExecutionResult(null);
      setUseCustomInput(false);
      setCustomInputText('');
      setLastEvaluation(null);
      setPendingNextQuestion(null);
      setProgressionError(null);
    } catch (err) {
      // Useful error if progression fails, preserving evaluated answer and lastEvaluation for safe retry
      setProgressionError(err.message || 'Unable to advance to the next question. Please click Retry.');
    } finally {
      setIsProgressing(false);
    }
  };

  const handleViewScorecard = async () => {
    setIsProgressing(true);
    setProgressionError(null);
    try {
      let sc = scorecard;
      if (!sc) {
        const scRes = await getSessionScorecard(sessionId);
        if (scRes.success && scRes.data) {
          sc = scRes.data;
          setScorecard(sc);
        } else {
          throw new Error(scRes.error || 'Failed to load finalized scorecard.');
        }
      }
      setIsCompleted(true);
    } catch (err) {
      setProgressionError(err.message || 'Failed to load scorecard. Please retry.');
    } finally {
      setIsProgressing(false);
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
        <Zap className="w-3 h-3 text-amber-400" />
        <span>Medium</span>
      </span>
    );
  };

  const wordCount = answerText.trim() ? answerText.trim().split(/\s+/).length : 0;

  // Derive Interviewer Status State for Display
  const getInterviewerState = () => {
    if (isSpeaking) return 'speaking';
    if (isRecordingAudio || isListening) return 'listening';
    if (isTranscribingAudio) return 'transcribing';
    if (submitting || runningCode) return 'thinking';
    return 'ready';
  };

  const getInterviewerStatus = () => {
    const st = getInterviewerState();
    switch (st) {
      case 'speaking':
        return 'Speaking...';
      case 'listening':
        return 'Listening...';
      case 'transcribing':
        return 'Transcribing...';
      case 'thinking':
        return 'Thinking...';
      case 'ready':
      default:
        return 'Ready';
    }
  };

  // Conversational Intro Greeting Generator
  const getQuestionIntro = (idx) => {
    const greetings = [
      "Great! Let's start with a foundational technical question.",
      'Well done. Moving on to the next technical topic in our assessment.',
      "Let's explore your understanding further with this question.",
      'Continuing forward. Here is another core engineering challenge.',
      'Here is the final technical challenge for this assessment.',
    ];
    return greetings[(idx - 1) % greetings.length] || "Let's review this technical problem.";
  };

  // --------------------------------------------------------------------------
  // Loading & Error States
  // --------------------------------------------------------------------------
  if (loading) {
    return (
      <div className="min-h-screen bg-[#070B14] text-slate-100 flex items-center justify-center p-4">
        <div className="glass-panel p-8 rounded-2xl border border-slate-800 text-center max-w-md w-full shadow-2xl">
          <div className="w-14 h-14 rounded-2xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center mx-auto mb-4 animate-pulse">
            <BrainCircuit className="w-7 h-7" />
          </div>
          <h3 className="text-base font-bold text-white mb-2">Connecting to AI Interview Engine</h3>
          <p className="text-xs text-slate-400 leading-relaxed mb-5">
            Validating student credentials, loading verified question set, and establishing secure audio stream...
          </p>
          <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden border border-slate-800">
            <div className="bg-gradient-to-r from-cyan-500 via-indigo-500 to-violet-500 h-1.5 w-2/3 animate-pulse"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error && (!activeQuestion || !activeQuestion.question_text) && !scorecard) {
    const isExpired =
      errorType === 'EXPIRED' ||
      (error && (error.toLowerCase().includes('expired') || error.toLowerCase().includes('timed out')));
    const isNetwork = errorType === 'NETWORK';
    const isServer = errorType === 'SERVER';
    const isConflict = errorType === 'CONFLICT';

    return (
      <div className="min-h-screen bg-[#070B14] text-slate-100 flex items-center justify-center p-4 selection:bg-cyan-500/30">
        <div className="w-full max-w-lg rounded-2xl bg-slate-900/90 border border-slate-800 shadow-2xl backdrop-blur-xl p-6 sm:p-8 relative overflow-hidden">
          <div
            className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${
              isExpired
                ? 'from-amber-500 via-rose-500 to-red-500'
                : isNetwork
                ? 'from-amber-500 via-orange-500 to-yellow-500'
                : isServer
                ? 'from-violet-500 via-indigo-500 to-cyan-500'
                : 'from-cyan-500 via-indigo-500 to-violet-500'
            }`}
          />

          <div className="flex flex-col items-center text-center mb-6">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-4 shadow-lg ${
                isExpired
                  ? 'bg-amber-950/60 text-amber-400 border border-amber-800/60 shadow-amber-950/40'
                  : isNetwork
                  ? 'bg-blue-950/60 text-blue-400 border border-blue-800/60 shadow-blue-950/40'
                  : isServer
                  ? 'bg-violet-950/60 text-violet-400 border border-violet-800/60 shadow-violet-950/40'
                  : 'bg-rose-950/60 text-rose-400 border border-rose-800/60 shadow-rose-950/40'
              }`}
            >
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

            <div
              className={`inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider mb-2.5 border ${
                isExpired
                  ? 'bg-amber-950/80 text-amber-300 border-amber-800/60'
                  : isNetwork
                  ? 'bg-blue-950/80 text-blue-300 border-blue-800/60'
                  : isServer
                  ? 'bg-violet-950/80 text-violet-300 border-violet-800/60'
                  : 'bg-rose-950/80 text-rose-300 border-rose-800/60'
              }`}
            >
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
      <div className="min-h-screen bg-[#070B14] text-slate-100 flex flex-col">
        <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-20">
          <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-600/20">
                <Award className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-white">Evaluation Scorecard</h1>
                <p className="text-[11px] text-slate-400">Adaptive Placement Mock Interview Performance Audit</p>
              </div>
            </div>
            <Link
              to="/dashboard"
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold flex items-center space-x-1.5 border border-slate-700 transition shadow"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Dashboard</span>
            </Link>
          </div>
        </header>

        <main className="max-w-6xl mx-auto px-4 py-8 w-full flex-1 space-y-6">
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
                <h2 className="text-xl sm:text-2xl font-bold text-white mb-2">Interview Evaluation Complete</h2>
                <p className="text-xs text-slate-300 max-w-2xl leading-relaxed">{scorecard.summary_feedback}</p>
              </div>

              <div className="flex items-center space-x-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800 shrink-0">
                <div className="text-right">
                  <div className="text-xs uppercase font-semibold text-slate-400 tracking-wider">Overall Score</div>
                  <div className="text-xs font-medium text-indigo-400">{scorecard.performance_level}</div>
                </div>
                <div
                  className={`w-16 h-16 rounded-xl flex flex-col items-center justify-center font-bold text-lg border ${
                    isPass
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                      : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                  }`}
                >
                  <span>{scorecard.overall_score}</span>
                  <span className="text-[10px] text-slate-400 font-normal">/ 10.0</span>
                </div>
              </div>
            </div>

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
                        <span
                          className={`capitalize font-semibold ${
                            diff === 'hard'
                              ? 'text-rose-400'
                              : diff === 'easy'
                              ? 'text-emerald-400'
                              : 'text-amber-400'
                          }`}
                        >
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

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="glass-panel p-6 rounded-2xl border border-slate-800">
              <h3 className="text-sm font-bold text-emerald-400 mb-3 flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4" />
                <span>Demonstrated Technical Strengths</span>
              </h3>
              {(scorecard.strengths || scorecard.strengths_summary) &&
              (scorecard.strengths || scorecard.strengths_summary).length > 0 ? (
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
                <p className="text-xs text-slate-400">Maintain continued precision across higher-order scenarios.</p>
              )}
            </div>
          </div>

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
                        <span className="text-sm font-bold text-indigo-300 font-mono">
                          {item.score ?? item.evaluation_score}
                        </span>
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

          <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 text-slate-400 text-xs leading-relaxed space-y-1.5">
            <div className="font-semibold text-slate-300 flex items-center space-x-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-indigo-400" />
              <span>Algorithmic Assessment Disclaimer</span>
            </div>
            <p>
              {scorecard.disclaimer ||
                scorecard.algorithmic_disclaimer ||
                'Score and feedback were computed using automated technical rubrics and adaptive difficulty thresholds. Evaluated on keyword precision, terminology depth, and architecture structure. This assessment represents algorithmic interview practice and does not claim subjective human parity or absolute grading.'}
            </p>
          </div>
        </main>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // Active Question Face-to-Face AI Interview Workspace
  // --------------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-[#070B14] text-slate-100 flex flex-col relative selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* Background Ambient Lighting & Cyber Grid */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute top-[-10%] right-[10%] w-[650px] h-[650px] rounded-full bg-cyan-600/10 blur-[160px]" />
        <div className="absolute top-[30%] left-[-15%] w-[600px] h-[600px] rounded-full bg-violet-600/10 blur-[180px]" />
        <div className="absolute bottom-[-10%] right-[20%] w-[700px] h-[700px] rounded-full bg-indigo-600/10 blur-[180px]" />
        <div className="absolute inset-0 cyber-grid radial-fade-mask opacity-50" />
      </div>

      {/* Proctoring Preflight & Consent Modal */}
      {!proctoringConsentGiven && !isCompleted && !loading && (
        <ProctoringPreflightModal
          studentRegistration={user?.registration_number || user?.email}
          onConsentGiven={() => setProctoringConsentGiven(true)}
        />
      )}

      {/* ==================================================================== */}
      {/* 1. Header Bar (Brand + Connectivity Badges + End Interview CTA)       */}
      {/* ==================================================================== */}
      <header className="relative z-20 border-b border-slate-800/80 bg-[#09101D]/90 backdrop-blur-xl sticky top-0 px-4 sm:px-6 py-2.5">
        <div className="max-w-[1700px] mx-auto flex items-center justify-between gap-4">
          {/* Brand Logo & Subtitle */}
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 via-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-600/30 border border-violet-400/30">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-sm font-bold text-white tracking-tight">VFSTR Interview</span>
              </div>
              <span className="text-[11px] text-slate-400 block -mt-0.5">Adaptive AI Interviews</span>
            </div>
          </div>

          {/* Center & Right Badges + End Call Control */}
          <div className="flex items-center space-x-2 sm:space-x-3">
            {/* Connected Badge */}
            <div className="hidden sm:flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-800/60 text-emerald-300 text-xs font-medium shadow-sm">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>Connected</span>
            </div>

            {/* Deepgram Voice Active Badge */}
            <div className="hidden md:flex items-center space-x-1.5 px-3 py-1 rounded-full bg-cyan-950/60 border border-cyan-800/60 text-cyan-300 text-xs font-medium shadow-sm">
              <Mic className="w-3.5 h-3.5 text-cyan-400" />
              <span>Deepgram Voice Active</span>
            </div>

            {/* Google Gemini / AI Provider Badge */}
            <div className="hidden lg:flex items-center space-x-1.5 px-3 py-1 rounded-full bg-purple-950/60 border border-purple-800/60 text-purple-300 text-xs font-medium shadow-sm">
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              <span>
                {activeQuestion?.evaluator_mode === 'gemini'
                  ? 'Google Gemini'
                  : activeQuestion?.evaluator_mode === 'mock_rule_engine'
                  ? 'Rule Rubric Engine'
                  : 'AI Evaluator'}
              </span>
            </div>

            {/* End Interview Red Pill Action */}
            <button
              type="button"
              onClick={() => setShowEndModal(true)}
              id="header-end-interview-btn"
              className="px-3.5 py-1.5 rounded-xl bg-rose-950/60 hover:bg-rose-900/60 text-rose-300 hover:text-white border border-rose-800/60 text-xs font-semibold flex items-center space-x-1.5 transition shadow-sm active:scale-95"
            >
              <PhoneOff className="w-3.5 h-3.5 text-rose-400" />
              <span>End Interview</span>
            </button>
          </div>
        </div>
      </header>

      {/* ==================================================================== */}
      {/* Main Container: Sidebar + Split Workspace Body                        */}
      {/* ==================================================================== */}
      <div className="relative z-10 flex-1 flex max-w-[1700px] w-full mx-auto overflow-hidden">
        {/* Left Navigation Sidebar */}
        <aside className="hidden md:flex flex-col w-56 border-r border-slate-800/80 bg-[#070D1E]/80 backdrop-blur-md p-3 space-y-1 shrink-0">
          {[
            { id: 'room', label: 'Interview Room', icon: Briefcase },
            { id: 'navigator', label: 'Question Navigator', icon: Compass },
            { id: 'code', label: 'Code Editor', icon: Code },
            { id: 'notes', label: 'Notes', icon: FileText },
            { id: 'guide', label: 'Question Guide', icon: BookOpen },
            { id: 'chat', label: 'Technical Chat', icon: MessageSquare },
            { id: 'feedback', label: 'Feedback', icon: Award },
            { id: 'settings', label: 'Settings', icon: Settings },
          ].map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  if (item.id === 'settings') {
                    setShowSettingsModal(true);
                  } else if (item.id === 'notes') {
                    setShowNotesModal(true);
                  } else if (item.id === 'guide') {
                    setShowGuideModal(true);
                  } else {
                    setActiveTab(item.id);
                  }
                }}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-xs font-medium transition text-left ${
                  isActive
                    ? 'bg-gradient-to-r from-violet-600/30 to-indigo-600/20 text-white border border-violet-500/40 shadow-md shadow-violet-500/10'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-violet-400' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}

          <div className="mt-auto pt-4 border-t border-slate-800/60 text-[10px] text-slate-500 font-mono px-2">
            <div>STUDENT ID</div>
            <div className="text-slate-300 font-semibold truncate">{user?.registration_number || user?.email}</div>
          </div>
        </aside>

        {/* Central Workspace Area */}
        <main className="flex-1 p-3 sm:p-5 flex flex-col space-y-4 overflow-y-auto">
          {/* Main Top Split Grid: AI Interviewer Video Panel (Left) & Conversational Panel (Right) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1">
            {/* -------------------------------------------------------------- */}
            {/* Left Card: AI Interviewer Panel                                */}
            {/* -------------------------------------------------------------- */}
            <div className="lg:col-span-5 flex flex-col space-y-3">
              <div className="relative rounded-2xl border border-slate-800 bg-[#070D1E] shadow-2xl overflow-hidden flex-1 min-h-[380px] lg:min-h-[460px] flex flex-col justify-between glow-border-violet group">
                {/* AI Interviewer Avatar with Synchronized Talking Head & Face Articulation */}
                <div className="absolute inset-0 z-0 overflow-hidden bg-slate-950">
                  <TalkingInterviewerAvatar
                    imageSrc={aiInterviewerImg}
                    isSpeaking={isSpeaking}
                    audioElement={deepgramAudioInstance}
                    speakingSource={speakingSource}
                    interviewerStatus={getInterviewerState()}
                  />
                  {/* Subtle Dark Vignette & Neon Rim Glow */}
                  <div className="absolute inset-0 bg-gradient-to-t from-[#070D1E] via-transparent to-black/30 pointer-events-none" />
                </div>

                {/* Top-Left Floating Badge: AI Interviewer + Status + Audio Waveform */}
                <div className="relative z-10 m-3 sm:m-4 flex items-center justify-between pointer-events-auto">
                  <div className="glass-panel px-3 py-1.5 rounded-full border border-slate-700/60 flex items-center space-x-2.5 shadow-xl bg-slate-950/80 backdrop-blur-md">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${
                        isSpeaking
                          ? 'bg-emerald-400 animate-pulse'
                          : isRecordingAudio || isListening
                          ? 'bg-rose-400 animate-ping'
                          : 'bg-emerald-400'
                      }`}
                    />
                    <div className="flex flex-col">
                      <span className="text-[11px] font-bold text-white tracking-wide leading-none">
                        AI Interviewer
                      </span>
                      <span className="text-[10px] text-slate-300 font-medium leading-tight mt-0.5 flex items-center space-x-1.5">
                        <span>{getInterviewerStatus()}</span>
                        {/* Audio Waveform Equalizer Bars (animates when AI is speaking) */}
                        {isSpeaking && (
                          <div className="flex items-center space-x-0.5 ml-1">
                            <span className="w-0.5 h-3 bg-cyan-400 rounded-full animate-soundbar-1" />
                            <span className="w-0.5 h-3 bg-violet-400 rounded-full animate-soundbar-2" />
                            <span className="w-0.5 h-3 bg-cyan-400 rounded-full animate-soundbar-3" />
                            <span className="w-0.5 h-3 bg-indigo-400 rounded-full animate-soundbar-4" />
                            <span className="w-0.5 h-3 bg-cyan-400 rounded-full animate-soundbar-5" />
                          </div>
                        )}
                      </span>
                    </div>
                  </div>

                  {/* Audio Replay / Speak Prompt Trigger */}
                  <button
                    type="button"
                    onClick={isSpeaking ? handleStopSpeech : handlePlayQuestion}
                    className="glass-panel p-2 rounded-full border border-slate-700/60 text-slate-200 hover:text-white hover:bg-slate-800/80 transition shadow-lg"
                    title={isSpeaking ? 'Pause speech audio' : 'Play interviewer audio'}
                  >
                    {isSpeaking ? <Square className="w-3.5 h-3.5 fill-current" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                  </button>
                </div>

                {/* Candidate Camera PIP Widget (Proctoring Webcam Preview) */}
                {cameraEnabled && proctoringConsentGiven && sessionId && !isCompleted && (
                  <div className="relative z-10 self-end m-3 shadow-2xl rounded-xl overflow-hidden border border-slate-700/60 bg-slate-950/90 w-36 sm:w-44 transition">
                    <ProctoringCameraWidget
                      onProctoringEvent={handleProctoringEvent}
                      isSessionActive={!isCompleted && !lastEvaluation}
                    />
                  </div>
                )}

                {/* Bottom Video Call Dock: Mute, Camera, Settings, End Interview */}
                <div className="relative z-10 m-3 sm:m-4 flex items-center justify-center">
                  <div className="glass-panel px-3 py-2 rounded-2xl border border-slate-700/70 bg-slate-950/85 backdrop-blur-xl flex items-center space-x-2 sm:space-x-3 shadow-2xl">
                    {/* Mute Toggle */}
                    <button
                      type="button"
                      onClick={handleToggleMute}
                      id="video-dock-mute-btn"
                      className={`p-2.5 rounded-xl text-xs font-semibold transition flex flex-col items-center justify-center ${
                        isMuted
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          : 'bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60'
                      }`}
                      title={isMuted ? 'Unmute AI voice' : 'Mute AI voice'}
                    >
                      {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                      <span className="text-[9px] mt-0.5">{isMuted ? 'Muted' : 'Mute'}</span>
                    </button>

                    {/* Camera Toggle */}
                    <button
                      type="button"
                      onClick={() => setCameraEnabled(!cameraEnabled)}
                      id="video-dock-camera-btn"
                      className={`p-2.5 rounded-xl text-xs font-semibold transition flex flex-col items-center justify-center ${
                        cameraEnabled
                          ? 'bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      }`}
                      title={cameraEnabled ? 'Hide webcam preview' : 'Show webcam preview'}
                    >
                      {cameraEnabled ? <Video className="w-4 h-4" /> : <VideoOff className="w-4 h-4" />}
                      <span className="text-[9px] mt-0.5">Camera</span>
                    </button>

                    {/* Settings Modal Toggle */}
                    <button
                      type="button"
                      onClick={() => setShowSettingsModal(true)}
                      id="video-dock-settings-btn"
                      className="p-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60 text-xs font-semibold transition flex flex-col items-center justify-center"
                      title="Audio and video settings"
                    >
                      <Settings className="w-4 h-4" />
                      <span className="text-[9px] mt-0.5">Settings</span>
                    </button>

                    {/* Red Call Hangup Button */}
                    <button
                      type="button"
                      onClick={() => setShowEndModal(true)}
                      id="video-dock-end-call-btn"
                      className="px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-lg shadow-rose-600/30 transition flex flex-col items-center justify-center"
                      title="End interview session"
                    >
                      <PhoneOff className="w-4 h-4" />
                      <span className="text-[9px] mt-0.5">End Interview</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* -------------------------------------------------------------- */}
            {/* Right Card: Conversational Interview Panel                     */}
            {/* -------------------------------------------------------------- */}
            <div className="lg:col-span-7 flex flex-col space-y-3">
              <div className="rounded-2xl border border-slate-800 bg-[#070D1E] shadow-2xl p-4 sm:p-5 flex-1 flex flex-col justify-between min-h-[380px] lg:min-h-[460px]">
                {/* Header: Role Title + Topic + Question X of Y + Difficulty + Timer */}
                <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
                  <div className="flex items-center space-x-3">
                    <div className="w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400 shadow-md shadow-violet-600/10">
                      <Layers className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-sm font-bold text-white tracking-tight">
                        {activeQuestion?.interview_title || 'Software Development Engineer Interview'}
                      </h2>
                      <div className="text-[11px] text-slate-400 flex items-center space-x-1.5 mt-0.5">
                        <span>Topic: {activeQuestion?.topic || 'Computer Networks'}</span>
                        <span className="text-slate-600">•</span>
                        <span className="text-violet-400 font-semibold font-mono">
                          Question {activeQuestion?.question_index || 1} of {activeQuestion?.total_questions || 5}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 sm:space-x-3">
                    {/* Difficulty Badge */}
                    {getDifficultyBadge(activeQuestion?.difficulty)}

                    {/* Prominent Next Question Header Action when answer evaluated (always visible outside scroll container) */}
                    {lastEvaluation && !lastEvaluation.isFinal && (
                      <button
                        type="button"
                        onClick={handleProceedToNextQuestion}
                        disabled={isProgressing}
                        id="header-action-next-question-btn"
                        data-testid="header-next-question-btn"
                        className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-bold shadow-lg shadow-violet-600/30 transition flex items-center space-x-1.5 disabled:opacity-50 cursor-pointer animate-pulse"
                      >
                        {isProgressing ? (
                          <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <>
                            <span>Next Question</span>
                            <ArrowRight className="w-3.5 h-3.5" />
                          </>
                        )}
                      </button>
                    )}
                    {lastEvaluation && lastEvaluation.isFinal && (
                      <button
                        type="button"
                        onClick={handleViewScorecard}
                        disabled={isProgressing}
                        id="header-action-view-scorecard-btn"
                        data-testid="header-view-scorecard-btn"
                        className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-600/30 transition flex items-center space-x-1.5 disabled:opacity-50 cursor-pointer animate-pulse"
                      >
                        {isProgressing ? (
                          <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <>
                            <Award className="w-3.5 h-3.5" />
                            <span>View Scorecard</span>
                          </>
                        )}
                      </button>
                    )}

                    {/* Live Countdown Timer */}
                    <div className="flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-slate-950/80 border border-slate-800 text-xs font-mono">
                      <Clock className="w-3.5 h-3.5 text-amber-400" />
                      <span
                        className={`font-bold ${
                          secondsRemaining !== null && secondsRemaining < 300
                            ? 'text-rose-400 animate-pulse'
                            : 'text-white'
                        }`}
                      >
                        {formatTime(secondsRemaining)}
                      </span>
                      <span className="text-[10px] text-slate-400 hidden sm:inline">Time Remaining</span>
                    </div>
                  </div>
                </div>

                {/* Conversational Message Thread Container */}
                <div className="my-4 flex-1 overflow-y-auto space-y-4 pr-1 custom-chat-scrollbar max-h-[360px]">
                  {/* 1. AI Interviewer Message Bubble */}
                  <div className="flex items-start space-x-3">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center text-white shrink-0 shadow-md shadow-violet-600/20 border border-violet-400/30">
                      <Sparkles className="w-4 h-4" />
                    </div>
                    <div className="flex-1 max-w-2xl rounded-2xl rounded-tl-sm bg-[#10192D] border border-slate-800/90 p-4 space-y-2 shadow-lg">
                      <p className="text-xs text-indigo-300 font-medium">
                        {getQuestionIntro(activeQuestion?.question_index || 1)}
                      </p>
                      <p className="text-xs sm:text-sm text-slate-100 font-medium leading-relaxed">
                        {activeQuestion?.question_text}
                      </p>

                      {/* Equalizer Wave / Timestamp Bar */}
                      <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 text-[10px] text-slate-500">
                        <div className="flex items-center space-x-1.5">
                          {isSpeaking && (
                            <span className="text-cyan-400 flex items-center space-x-1 font-mono">
                              <Radio className="w-3 h-3 animate-ping" />
                              <span>Speaking audio...</span>
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={handlePlayQuestion}
                            className="hover:text-cyan-300 transition flex items-center space-x-1"
                          >
                            <Volume2 className="w-3 h-3" />
                            <span>Listen Again</span>
                          </button>
                        </div>
                        <span className="font-mono">Active Prompt</span>
                      </div>
                    </div>
                  </div>

                  {/* 2. Candidate Response Message Bubble */}
                  <div className="flex items-start justify-end space-x-3">
                    <div className="flex-1 max-w-xl rounded-2xl rounded-tr-sm bg-[#0E1E38] border border-cyan-900/50 p-4 space-y-1.5 shadow-lg text-right">
                      {answerText.trim() ? (
                        <p className="text-xs sm:text-sm text-slate-100 font-sans whitespace-pre-wrap leading-relaxed text-left">
                          {answerText}
                        </p>
                      ) : interimTranscript ? (
                        <p className="text-xs sm:text-sm text-cyan-300 italic font-sans text-left animate-pulse">
                          "{interimTranscript}..."
                        </p>
                      ) : (
                        <p className="text-xs text-slate-400 italic text-left">
                          {activeQuestion?.question_type === 'coding'
                            ? 'Coding challenge active. Use the Code Editor below to write, compile, and execute your solution.'
                            : 'Click the microphone below to speak, or switch to typing mode to formulate your response.'}
                        </p>
                      )}

                      <div className="flex items-center justify-between pt-1 border-t border-cyan-900/40 text-[10px] text-slate-400">
                        <span className="font-mono">{wordCount} words recorded</span>
                        <span className="text-slate-500 font-mono">Candidate Draft</span>
                      </div>
                    </div>

                    <div className="w-8 h-8 rounded-full overflow-hidden border border-cyan-500/40 shrink-0 shadow-md">
                      <img
                        src={candidateAvatarImg}
                        alt="Candidate"
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.target.style.display = 'none';
                        }}
                      />
                    </div>
                  </div>

                  {/* Immediate Feedback Drawer in Conversational Thread */}
                  {lastEvaluation && (
                    <div
                      ref={evaluationCardRef}
                      className="p-4 rounded-xl bg-slate-900/90 border border-violet-500/40 space-y-3 animate-in fade-in"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          <span className="text-xs font-bold text-white">
                            {lastEvaluation.isFinal
                              ? 'Final Question Evaluation Complete'
                              : 'Evaluation Feedback (Question Complete)'}
                          </span>
                        </div>
                        <div className="px-2.5 py-0.5 rounded-lg bg-violet-950 border border-violet-800 text-xs font-bold text-violet-300 font-mono">
                          Score: {lastEvaluation.score} / 10
                        </div>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">{lastEvaluation.feedback}</p>

                      {lastEvaluation.strengths && lastEvaluation.strengths.length > 0 && (
                        <div className="space-y-1 pt-1">
                          <span className="text-[11px] font-semibold text-emerald-400">Strengths:</span>
                          <ul className="list-disc list-inside text-[11px] text-slate-300 space-y-0.5">
                            {lastEvaluation.strengths.map((str, idx) => (
                              <li key={idx}>{str}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {lastEvaluation.improvements && lastEvaluation.improvements.length > 0 && (
                        <div className="space-y-1 pt-1">
                          <span className="text-[11px] font-semibold text-amber-400">Areas for Growth:</span>
                          <ul className="list-disc list-inside text-[11px] text-slate-300 space-y-0.5">
                            {lastEvaluation.improvements.map((imp, idx) => (
                              <li key={idx}>{imp}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {progressionError && (
                        <div className="p-2.5 rounded-lg bg-rose-950/80 border border-rose-500/50 text-xs text-rose-200 flex items-center justify-between">
                          <div className="flex items-center space-x-1.5">
                            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                            <span>{progressionError}</span>
                          </div>
                          <button
                            type="button"
                            onClick={lastEvaluation.isFinal ? handleViewScorecard : handleProceedToNextQuestion}
                            className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-semibold transition"
                          >
                            Retry
                          </button>
                        </div>
                      )}

                      <div className="flex justify-end pt-1">
                        {lastEvaluation.isFinal ? (
                          <button
                            type="button"
                            onClick={handleViewScorecard}
                            disabled={isProgressing}
                            id="proceed-view-scorecard-btn"
                            className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5 disabled:opacity-50"
                          >
                            {isProgressing ? (
                              <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Award className="w-3.5 h-3.5" />
                            )}
                            <span>View Final Scorecard</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={handleProceedToNextQuestion}
                            disabled={isProgressing}
                            id="proceed-to-next-question-btn"
                            data-testid="proceed-next-question-btn"
                            className="px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5 disabled:opacity-50"
                          >
                            {isProgressing ? (
                              <>
                                <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                                <span>Loading Next Question...</span>
                              </>
                            ) : (
                              <>
                                <span>Next Question</span>
                                <ArrowRight className="w-3.5 h-3.5" />
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* ------------------------------------------------------------ */}
                {/* Bottom Voice & Interaction Bar (Mic button, Type Mode, Submit) */}
                {/* ------------------------------------------------------------ */}
                <div className="pt-3 border-t border-slate-800/80 space-y-3">
                  {/* Status & Mode Switch Row */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2 text-xs font-medium">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          isRecordingAudio || isListening
                            ? 'bg-rose-400 animate-ping'
                            : isTranscribingAudio
                            ? 'bg-amber-400 animate-pulse'
                            : 'bg-emerald-400'
                        }`}
                      />
                      <span className="text-slate-300">
                        {isRecordingAudio
                          ? 'Listening... Speak your answer'
                          : isTranscribingAudio
                          ? 'Transcribing audio with Deepgram...'
                          : isListening
                          ? 'Live dictation active...'
                          : 'Listening ready'}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() => setInputMode(inputMode === 'voice' ? 'type' : 'voice')}
                      id="toggle-input-mode-btn"
                      className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 text-xs font-medium flex items-center space-x-1.5 transition"
                    >
                      {inputMode === 'voice' ? (
                        <>
                          <Keyboard className="w-3.5 h-3.5 text-cyan-400" />
                          <span>Type Instead</span>
                        </>
                      ) : (
                        <>
                          <Mic className="w-3.5 h-3.5 text-violet-400" />
                          <span>Voice Mode</span>
                        </>
                      )}
                    </button>
                  </div>

                  {/* Speech Error Alert Banner */}
                  {speechError && (
                    <div
                      className="p-3 rounded-xl bg-rose-950/70 border border-rose-500/50 text-rose-200 text-xs flex items-start justify-between space-x-2 animate-in fade-in"
                      role="alert"
                    >
                      <div className="flex items-start space-x-2">
                        <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                        <span className="leading-relaxed">{speechError}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSpeechError(null)}
                        className="text-rose-400 hover:text-white transition p-0.5 rounded shrink-0"
                        title="Dismiss alert"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  {/* Prominent Voice Microphone Trigger */}
                  {inputMode === 'voice' && !lastEvaluation && (
                    <div className="flex flex-col items-center justify-center py-2 space-y-2">
                      <div className="flex items-center space-x-4 sm:space-x-6">
                        {/* Left Sound Wave Bars */}
                        <div className="flex items-center space-x-1">
                          <span
                            className={`w-1 rounded-full bg-cyan-400 ${
                              isRecordingAudio ? 'animate-soundbar-1 h-5' : 'h-2 opacity-40'
                            }`}
                          />
                          <span
                            className={`w-1 rounded-full bg-violet-400 ${
                              isRecordingAudio ? 'animate-soundbar-2 h-6' : 'h-3 opacity-40'
                            }`}
                          />
                          <span
                            className={`w-1 rounded-full bg-cyan-400 ${
                              isRecordingAudio ? 'animate-soundbar-3 h-7' : 'h-4 opacity-40'
                            }`}
                          />
                          <span
                            className={`w-1 rounded-full bg-indigo-400 ${
                              isRecordingAudio ? 'animate-soundbar-4 h-5' : 'h-2 opacity-40'
                            }`}
                          />
                        </div>

                        {/* Large Circular Glowing Microphone Button */}
                        <button
                          type="button"
                          onClick={isRecordingAudio ? stopDeepgramRecording : startDeepgramRecording}
                          disabled={submitting || isTranscribingAudio || !!lastEvaluation}
                          id="primary-microphone-action-btn"
                          className={`w-16 h-16 sm:w-18 sm:h-18 rounded-full flex items-center justify-center transition shadow-2xl relative ${
                            isRecordingAudio
                              ? 'bg-gradient-to-r from-rose-600 to-red-600 text-white animate-mic-pulse'
                              : 'bg-gradient-to-tr from-violet-600 via-indigo-600 to-cyan-500 text-white hover:scale-105 active:scale-95 shadow-violet-600/30'
                          } disabled:opacity-50`}
                          title={isRecordingAudio ? 'Click to stop speaking' : 'Click to start recording voice response'}
                        >
                          {isRecordingAudio ? (
                            <Square className="w-6 h-6 fill-current text-white" />
                          ) : isTranscribingAudio ? (
                            <RotateCcw className="w-6 h-6 animate-spin text-white" />
                          ) : (
                            <Mic className="w-7 h-7 text-white" />
                          )}
                        </button>

                        {/* Right Sound Wave Bars */}
                        <div className="flex items-center space-x-1">
                          <span
                            className={`w-1 rounded-full bg-indigo-400 ${
                              isRecordingAudio ? 'animate-soundbar-4 h-5' : 'h-2 opacity-40'
                            }`}
                          />
                          <span
                            className={`w-1 rounded-full bg-cyan-400 ${
                              isRecordingAudio ? 'animate-soundbar-3 h-7' : 'h-4 opacity-40'
                            }`}
                          />
                          <span
                            className={`w-1 rounded-full bg-violet-400 ${
                              isRecordingAudio ? 'animate-soundbar-2 h-6' : 'h-3 opacity-40'
                            }`}
                          />
                          <span
                            className={`w-1 rounded-full bg-cyan-400 ${
                              isRecordingAudio ? 'animate-soundbar-1 h-5' : 'h-2 opacity-40'
                            }`}
                          />
                        </div>
                      </div>

                      <span className="text-[11px] text-slate-400 font-medium">
                        {isRecordingAudio
                          ? 'Recording live voice... Click button when done speaking'
                          : isTranscribingAudio
                          ? 'Transcribing audio with Deepgram...'
                          : 'Click to speak or start talking'}
                      </span>
                    </div>
                  )}

                  {/* Candidate Technical Response Editor & Submit Action */}
                  {!lastEvaluation ? (
                    <div className="space-y-2 animate-in fade-in">
                      <div className="flex items-center justify-between">
                        <label
                          htmlFor="interview-answer-editor"
                          className="text-[11px] font-semibold text-slate-300 flex items-center space-x-1.5"
                        >
                          <FileText className="w-3.5 h-3.5 text-cyan-400" />
                          <span>Candidate Technical Response Editor</span>
                          {isTranscribingAudio && (
                            <span className="text-[10px] text-cyan-400 flex items-center space-x-1 font-mono ml-2">
                              <Loader2 className="w-3 h-3 animate-spin" />
                              <span>Transcribing audio...</span>
                            </span>
                          )}
                        </label>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {inputMode === 'voice' ? 'Voice transcribed / Editable' : 'Keyboard typing'}
                        </span>
                      </div>

                      <textarea
                        id="interview-answer-editor"
                        rows={3}
                        value={answerText}
                        onChange={(e) => setAnswerText(e.target.value)}
                        disabled={submitting || isTranscribingAudio}
                        placeholder={
                          isRecordingAudio
                            ? "Listening... Speak your answer now. Click the microphone button when finished."
                            : isTranscribingAudio
                            ? "Transcribing your spoken answer via Deepgram STT..."
                            : "Your spoken response transcript or typed answer will appear here. You can edit this text freely before submitting."
                        }
                        className="w-full rounded-xl bg-slate-950/90 border border-slate-800 text-slate-100 placeholder-slate-600 text-xs font-mono p-3 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition leading-relaxed resize-none disabled:opacity-60"
                      />

                      <div className="flex items-center justify-between">
                        <span className="text-[11px] text-slate-400 font-mono">
                          {wordCount} words {wordCount >= 25 ? '✓ (Adequate depth)' : '(25+ words recommended)'}
                        </span>

                        <button
                          type="button"
                          onClick={handleSubmitAnswer}
                          disabled={submitting || !answerText.trim() || isTranscribingAudio}
                          id="submit-conversational-answer-btn"
                          className="px-5 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-violet-600/20 transition flex items-center space-x-1.5 disabled:opacity-50 cursor-pointer"
                        >
                          {submitting ? (
                            <>
                              <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                              <span>Evaluating...</span>
                            </>
                          ) : (
                            <>
                              <span>Submit Answer</span>
                              <Send className="w-3.5 h-3.5" />
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Prominent Evaluation Progression Bar shown at bottom when answer is evaluated */
                    <div className="p-3.5 rounded-xl bg-slate-900 border border-violet-500/40 flex flex-wrap items-center justify-between gap-3 animate-in fade-in">
                      <div className="flex items-center space-x-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        <div>
                          <div className="text-xs font-bold text-white flex items-center space-x-2">
                            <span>Answer Evaluated</span>
                            <span className="px-2 py-0.5 rounded bg-violet-950 border border-violet-800 text-[11px] font-mono text-violet-300">
                              {lastEvaluation.score} / 10
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            {lastEvaluation.isFinal
                              ? 'Interview complete. Click below to view your full scorecard.'
                              : 'Review evaluation feedback above, then proceed to the next question.'}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center space-x-2">
                        {progressionError && (
                          <span className="text-xs text-rose-400 font-medium mr-1">{progressionError}</span>
                        )}
                        {lastEvaluation.isFinal ? (
                          <button
                            type="button"
                            onClick={handleViewScorecard}
                            disabled={isProgressing}
                            id="bottom-action-view-scorecard-btn"
                            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-lg shadow-emerald-600/20 transition flex items-center space-x-2 disabled:opacity-50 cursor-pointer"
                          >
                            {isProgressing ? (
                              <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Award className="w-4 h-4" />
                            )}
                            <span>Complete & View Scorecard</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={handleProceedToNextQuestion}
                            disabled={isProgressing}
                            id="bottom-action-proceed-next-question-btn"
                            data-testid="next-question-btn"
                            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-bold shadow-lg shadow-violet-600/25 transition flex items-center space-x-2 disabled:opacity-50 cursor-pointer"
                          >
                            {isProgressing ? (
                              <>
                                <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                                <span>Loading Next Question...</span>
                              </>
                            ) : (
                              <>
                                <span>Next Question</span>
                                <ArrowRight className="w-3.5 h-3.5" />
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* ---------------------------------------------------------------- */}
          {/* Coding Challenge View (Rendered when Coding Tab is Selected)      */}
          {/* ---------------------------------------------------------------- */}
          {(activeTab === 'code' || activeQuestion?.question_type === 'coding') && (
            <div className="glass-panel p-4 sm:p-5 rounded-2xl border border-slate-800 space-y-4 animate-in fade-in">
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
                <div className="flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    Isolated Code Execution Sandbox
                  </span>
                  <span className="text-slate-600">•</span>
                  <span className="text-xs text-slate-400 font-mono">Language:</span>
                  {['Python', 'Java', 'C', 'C++'].map((lang) => (
                    <button
                      key={lang}
                      type="button"
                      onClick={() => handleLanguageSelect(lang)}
                      disabled={submitting || runningCode}
                      className={`px-2.5 py-1 rounded-lg text-xs font-mono font-semibold transition ${
                        selectedLanguage === lang
                          ? 'bg-cyan-600 text-white shadow-md shadow-cyan-600/30'
                          : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                      }`}
                    >
                      {lang}
                    </button>
                  ))}
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={handleRunCode}
                    disabled={runningCode || submitting || !answerText.trim()}
                    id="sandbox-run-code-btn"
                    className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-cyan-300 border border-cyan-800/60 text-xs font-semibold flex items-center space-x-1.5 transition disabled:opacity-50"
                  >
                    {runningCode ? (
                      <>
                        <RotateCcw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                        <span>Running Sandbox...</span>
                      </>
                    ) : (
                      <>
                        <PlayCircle className="w-4 h-4 text-cyan-400" />
                        <span>Run Code</span>
                      </>
                    )}
                  </button>

                  {lastEvaluation ? (
                    lastEvaluation.isFinal ? (
                      <button
                        type="button"
                        onClick={handleViewScorecard}
                        disabled={isProgressing}
                        id="sandbox-view-scorecard-btn"
                        className="px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5 disabled:opacity-50 cursor-pointer"
                      >
                        {isProgressing ? <RotateCcw className="w-3.5 h-3.5 animate-spin" /> : <Award className="w-3.5 h-3.5" />}
                        <span>View Final Scorecard</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={handleProceedToNextQuestion}
                        disabled={isProgressing}
                        id="sandbox-proceed-next-question-btn"
                        data-testid="sandbox-next-question-btn"
                        className="px-5 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5 disabled:opacity-50 cursor-pointer"
                      >
                        {isProgressing ? (
                          <>
                            <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                            <span>Loading Next Question...</span>
                          </>
                        ) : (
                          <>
                            <span>Next Question</span>
                            <ArrowRight className="w-3.5 h-3.5" />
                          </>
                        )}
                      </button>
                    )
                  ) : (
                    <button
                      type="button"
                      onClick={handleSubmitAnswer}
                      disabled={submitting || runningCode || !answerText.trim()}
                      id="sandbox-submit-solution-btn"
                      className="px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5 disabled:opacity-50 cursor-pointer"
                    >
                      {submitting ? (
                        <>
                          <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                          <span>Evaluating...</span>
                        </>
                      ) : (
                        <>
                          <span>Submit Solution</span>
                          <Send className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>

              {/* Solution Evaluation Feedback Drawer in Coding Sandbox */}
              {lastEvaluation && (
                <div className="p-4 rounded-xl bg-slate-900/90 border border-violet-500/40 space-y-2.5 animate-in fade-in">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      <span className="text-xs font-bold text-white">
                        {lastEvaluation.isFinal ? 'Final Coding Solution Evaluated' : 'Coding Solution Evaluated'}
                      </span>
                    </div>
                    <div className="px-2.5 py-0.5 rounded-lg bg-violet-950 border border-violet-800 text-xs font-bold text-violet-300 font-mono">
                      Score: {lastEvaluation.score} / 10
                    </div>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">{lastEvaluation.feedback}</p>

                  {progressionError && (
                    <div className="p-2.5 rounded-lg bg-rose-950/80 border border-rose-500/50 text-xs text-rose-200 flex items-center justify-between">
                      <div className="flex items-center space-x-1.5">
                        <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                        <span>{progressionError}</span>
                      </div>
                      <button
                        type="button"
                        onClick={lastEvaluation.isFinal ? handleViewScorecard : handleProceedToNextQuestion}
                        className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-semibold transition"
                      >
                        Retry
                      </button>
                    </div>
                  )}

                  <div className="flex justify-end pt-1">
                    {lastEvaluation.isFinal ? (
                      <button
                        type="button"
                        onClick={handleViewScorecard}
                        disabled={isProgressing}
                        className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5 disabled:opacity-50"
                      >
                        {isProgressing ? <RotateCcw className="w-3.5 h-3.5 animate-spin" /> : <Award className="w-3.5 h-3.5" />}
                        <span>View Final Scorecard</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={handleProceedToNextQuestion}
                        disabled={isProgressing}
                        data-testid="coding-drawer-next-question-btn"
                        className="px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5 disabled:opacity-50"
                      >
                        {isProgressing ? (
                          <>
                            <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                            <span>Loading Next Question...</span>
                          </>
                        ) : (
                          <>
                            <span>Next Question</span>
                            <ArrowRight className="w-3.5 h-3.5" />
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Code Editor Textarea */}
              <div className="relative rounded-xl border border-slate-800 overflow-hidden bg-slate-950 shadow-inner">
                <textarea
                  rows={10}
                  value={answerText}
                  onChange={(e) => setAnswerText(e.target.value)}
                  onKeyDown={handleEditorKeyDown}
                  disabled={submitting || !!lastEvaluation}
                  placeholder={`Write your ${selectedLanguage} solution here...`}
                  className="w-full bg-slate-950 text-slate-100 placeholder-slate-600 text-xs font-mono p-4 resize-y outline-none leading-relaxed focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                />
              </div>

              {/* Sandbox Output & Test Results */}
              {executionResult && (
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                  <div className="flex items-center justify-between text-slate-300 font-bold border-b border-slate-800 pb-1.5">
                    <span>Status: {executionResult.status}</span>
                    {executionResult.execution_time_ms != null && (
                      <span className="text-cyan-400">Runtime: {executionResult.execution_time_ms} ms</span>
                    )}
                  </div>
                  {executionResult.stdout && (
                    <pre className="p-2 bg-slate-900 rounded text-slate-200 overflow-x-auto text-[11px]">
                      {executionResult.stdout}
                    </pre>
                  )}
                  {executionResult.stderr && (
                    <pre className="p-2 bg-rose-950/40 rounded text-rose-300 overflow-x-auto text-[11px]">
                      {executionResult.stderr}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ================================================================ */}
          {/* Bottom Row: Question Stepper Progress (Left) & Tips Card (Right) */}
          {/* ================================================================ */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Question Stepper Progress Card */}
            <div className="lg:col-span-8 rounded-2xl border border-slate-800 bg-[#070D1E] shadow-xl p-4 flex items-center justify-between">
              <div className="flex items-center justify-between w-full relative">
                {Array.from({ length: activeQuestion?.total_questions || 5 }).map((_, idx) => {
                  const stepNum = idx + 1;
                  const isCurrent = stepNum === (activeQuestion?.question_index || 1);
                  const isPast = stepNum < (activeQuestion?.question_index || 1);

                  return (
                    <div key={stepNum} className="flex-1 flex flex-col items-center relative z-10">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition shadow-md ${
                          isCurrent
                            ? 'bg-gradient-to-tr from-violet-600 to-indigo-600 text-white ring-4 ring-violet-500/20'
                            : isPast
                            ? 'bg-emerald-600/20 text-emerald-300 border border-emerald-500/30'
                            : 'bg-slate-900 text-slate-500 border border-slate-800'
                        }`}
                      >
                        {isPast ? <Check className="w-4 h-4 text-emerald-400" /> : stepNum}
                      </div>
                      <span
                        className={`text-[10px] mt-1.5 font-medium whitespace-nowrap ${
                          isCurrent ? 'text-violet-300 font-bold' : isPast ? 'text-slate-400' : 'text-slate-600'
                        }`}
                      >
                        {isCurrent ? `Question ${stepNum} (current)` : `Question ${stepNum}`}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Right Card: Interview Tips */}
            <div className="lg:col-span-4 rounded-2xl border border-slate-800 bg-[#070D1E] shadow-xl p-4 flex items-center space-x-3.5 group hover:border-amber-500/40 transition">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                <Lightbulb className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h4 className="text-xs font-bold text-white">Interview Tips</h4>
                <p className="text-[11px] text-slate-400 leading-snug">
                  Be clear, structured and provide examples where applicable.
                </p>
              </div>
              <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition" />
            </div>
          </div>
        </main>
      </div>

      {/* ==================================================================== */}
      {/* End Interview Confirmation Modal                                     */}
      {/* ==================================================================== */}
      {showEndModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md rounded-2xl bg-[#09101D] border border-slate-800 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-rose-600/20 border border-rose-500/30 flex items-center justify-center text-rose-400">
                <PhoneOff className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">End Interview Session?</h3>
                <p className="text-xs text-slate-400">Your answered responses have been recorded.</p>
              </div>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Are you sure you want to exit the interview room? If you end now, your scorecard will be computed based on the answers submitted so far.
            </p>
            <div className="flex items-center justify-end space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setShowEndModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition"
              >
                Continue Interview
              </button>
              <button
                type="button"
                onClick={() => {
                  handleStopSpeech();
                  stopVoiceRecognition();
                  stopMediaStreamTracks();
                  navigate('/dashboard');
                }}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-md shadow-rose-600/20 transition"
              >
                Confirm & Exit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* Settings Modal                                                       */}
      {/* ==================================================================== */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md rounded-2xl bg-[#09101D] border border-slate-800 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2.5">
                <Settings className="w-5 h-5 text-violet-400" />
                <h3 className="text-sm font-bold text-white">Audio & Video Settings</h3>
              </div>
              <button onClick={() => setShowSettingsModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between p-3 rounded-xl bg-slate-900 border border-slate-800">
                <div>
                  <div className="font-semibold text-white">Deepgram Text-to-Speech</div>
                  <div className="text-slate-400 text-[11px]">Synthesizes questions using neural audio</div>
                </div>
                <button
                  type="button"
                  onClick={handlePlayQuestion}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-[11px]"
                >
                  Test Audio
                </button>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-slate-900 border border-slate-800">
                <div>
                  <div className="font-semibold text-white">Proctoring Camera Preview</div>
                  <div className="text-slate-400 text-[11px]">Level 1 face monitoring preview</div>
                </div>
                <button
                  type="button"
                  onClick={() => setCameraEnabled(!cameraEnabled)}
                  className={`px-3 py-1.5 rounded-lg font-medium text-[11px] ${
                    cameraEnabled ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  {cameraEnabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowSettingsModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* Student Personal Notes Scratchpad Modal                              */}
      {/* ==================================================================== */}
      {showNotesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-lg rounded-2xl bg-[#09101D] border border-slate-800 p-6 space-y-3 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2.5">
                <FileText className="w-5 h-5 text-cyan-400" />
                <h3 className="text-sm font-bold text-white">Personal Interview Scratchpad</h3>
              </div>
              <button onClick={() => setShowNotesModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-slate-400">
              Jot down quick thoughts, formulas, or pseudocode while reasoning through the problem. Notes remain private on this device.
            </p>
            <textarea
              rows={8}
              value={candidateNotes}
              onChange={(e) => setCandidateNotes(e.target.value)}
              placeholder="Type your notes here..."
              className="w-full rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono p-3 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500"
            />
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowNotesModal(false)}
                className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold"
              >
                Save & Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* Question Guide Modal                                                 */}
      {/* ==================================================================== */}
      {showGuideModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-lg rounded-2xl bg-[#09101D] border border-slate-800 p-6 space-y-3 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2.5">
                <BookOpen className="w-5 h-5 text-indigo-400" />
                <h3 className="text-sm font-bold text-white">Interview Assessment Guide</h3>
              </div>
              <button onClick={() => setShowGuideModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-2 text-xs text-slate-300">
              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800">
                <strong className="text-indigo-400 block mb-1">Conceptual Questions:</strong>
                Explain protocol mechanics, packet sequence numbers, handshake stages, and architectural trade-offs. Aim for depth and structured terminology.
              </div>
              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800">
                <strong className="text-cyan-400 block mb-1">Coding Questions:</strong>
                Read input from standard input (stdin) and print output to standard output (stdout). Test against sample cases before submitting your solution.
              </div>
              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800">
                <strong className="text-amber-400 block mb-1">Adaptive Progression:</strong>
                Scoring higher on initial questions triggers higher-tier prompts, earning higher placement percentile ratings.
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowGuideModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold"
              >
                Got It
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
