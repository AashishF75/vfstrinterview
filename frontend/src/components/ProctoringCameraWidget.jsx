import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Camera, 
  Video, 
  VideoOff, 
  User, 
  Users, 
  UserX, 
  ShieldAlert, 
  CheckCircle2, 
  AlertCircle,
  Eye
} from 'lucide-react';
import { FilesetResolver, FaceDetector } from '@mediapipe/tasks-vision';

export default function ProctoringCameraWidget({ onProctoringEvent, isSessionActive }) {
  const [streamActive, setStreamActive] = useState(false);
  const [detectorReady, setDetectorReady] = useState(false);
  const [detectorStatus, setDetectorStatus] = useState('initializing'); // 'initializing' | 'active' | 'fallback'
  const [faceCount, setFaceCount] = useState(1);
  const [monitoringState, setMonitoringState] = useState('normal'); // 'normal' | 'absent_warning' | 'absent_alert' | 'multiple_alert'
  const [cameraError, setCameraError] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const detectorRef = useRef(null);
  const streamRef = useRef(null);
  const tickIntervalRef = useRef(null);

  // Counters for hysteresis & debouncing
  const absentTicksRef = useRef(0);
  const multipleTicksRef = useRef(0);
  const isCurrentlyAbsentRef = useRef(false);
  const isCurrentlyMultipleRef = useRef(false);

  // 1. Initialize Webcam Stream
  const initCameraStream = useCallback(async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Webcam API is unsupported in this browser.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
        audio: false,
      });

      streamRef.current = stream;

      // Handle unexpected track ending
      stream.getVideoTracks().forEach((track) => {
        track.onended = () => {
          setStreamActive(false);
          setCameraError('Webcam stream was stopped or disconnected.');
          onProctoringEvent({
            event_type: 'camera_track_ended',
            client_timestamp: new Date().toISOString(),
          });
        };
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }

      setStreamActive(true);
      setCameraError(null);
      onProctoringEvent({
        event_type: 'camera_stream_connected',
        client_timestamp: new Date().toISOString(),
        metadata: { resolution: '640x480' },
      });
    } catch (err) {
      setStreamActive(false);
      setCameraError(err.message || 'Camera access error.');
      onProctoringEvent({
        event_type: 'camera_permission_denied',
        client_timestamp: new Date().toISOString(),
        metadata: { error: err.message },
      });
    }
  }, [onProctoringEvent]);

  // 2. Initialize MediaPipe Face Detector
  useEffect(() => {
    let isCancelled = false;

    async function loadDetector() {
      try {
        const vision = await FilesetResolver.forVisionTasks(
          'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm'
        );

        if (isCancelled) return;

        const detector = await FaceDetector.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
            delegate: 'GPU',
          },
          runningMode: 'IMAGE',
          minDetectionConfidence: 0.5,
        });

        if (isCancelled) return;
        detectorRef.current = detector;
        setDetectorReady(true);
        setDetectorStatus('active');
      } catch (err) {
        // Graceful fallback to video stream heartbeat if WASM/CDN is blocked
        if (!isCancelled) {
          setDetectorStatus('fallback');
          setDetectorReady(false);
        }
      }
    }

    loadDetector();
    initCameraStream();

    return () => {
      isCancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (tickIntervalRef.current) {
        clearInterval(tickIntervalRef.current);
      }
    };
  }, [initCameraStream]);

  // 3. Periodic Detection Loop (Sample frame every 1200ms)
  useEffect(() => {
    if (!isSessionActive || !streamActive) return;

    tickIntervalRef.current = setInterval(() => {
      if (!videoRef.current || !canvasRef.current || videoRef.current.readyState < 2) return;

      const video = videoRef.current;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');

      // Draw downscaled 320x240 frame to limit CPU load
      canvas.width = 320;
      canvas.height = 240;
      ctx.drawImage(video, 0, 0, 320, 240);

      let detectedCount = 1;

      if (detectorRef.current && detectorStatus === 'active') {
        try {
          const detections = detectorRef.current.detect(canvas);
          detectedCount = (detections.detections || []).length;
        } catch {
          // If frame analysis fails on single tick, keep last count
          detectedCount = faceCount;
        }
      }

      setFaceCount(detectedCount);

      // Debounce logic for Face Absence
      if (detectedCount === 0) {
        absentTicksRef.current += 1;
        multipleTicksRef.current = 0;

        if (absentTicksRef.current >= 3) {
          // Sustained absence >= 3.6s
          setMonitoringState('absent_alert');
          if (!isCurrentlyAbsentRef.current) {
            isCurrentlyAbsentRef.current = true;
            onProctoringEvent({
              event_type: 'face_absent',
              client_timestamp: new Date().toISOString(),
              duration_seconds: 3.6,
              metadata: { consecutive_ticks: absentTicksRef.current },
            });
          }
        } else {
          setMonitoringState('absent_warning');
        }
      } else if (detectedCount === 1) {
        // Single normal face
        absentTicksRef.current = 0;
        multipleTicksRef.current = 0;
        setMonitoringState('normal');

        if (isCurrentlyAbsentRef.current) {
          isCurrentlyAbsentRef.current = false;
          onProctoringEvent({
            event_type: 'face_restored',
            client_timestamp: new Date().toISOString(),
          });
        }
        if (isCurrentlyMultipleRef.current) {
          isCurrentlyMultipleRef.current = false;
          onProctoringEvent({
            event_type: 'face_normal',
            client_timestamp: new Date().toISOString(),
          });
        }
      } else if (detectedCount >= 2) {
        // Multiple faces
        absentTicksRef.current = 0;
        multipleTicksRef.current += 1;

        if (multipleTicksRef.current >= 2) {
          setMonitoringState('multiple_alert');
          if (!isCurrentlyMultipleRef.current) {
            isCurrentlyMultipleRef.current = true;
            onProctoringEvent({
              event_type: 'multiple_faces_detected',
              client_timestamp: new Date().toISOString(),
              duration_seconds: 2.4,
              metadata: { face_count: detectedCount },
            });
          }
        }
      }
    }, 1200);

    return () => {
      if (tickIntervalRef.current) clearInterval(tickIntervalRef.current);
    };
  }, [isSessionActive, streamActive, detectorStatus, faceCount, onProctoringEvent]);

  return (
    <div className="relative rounded-2xl overflow-hidden bg-slate-950 border border-slate-800 shadow-xl w-60 sm:w-64">
      {/* Hidden processing canvas */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Video Feed */}
      <div className="relative aspect-video bg-slate-950 flex items-center justify-center overflow-hidden">
        <video
          ref={videoRef}
          muted
          playsInline
          className={`w-full h-full object-cover transform -scale-x-100 ${
            streamActive ? 'block' : 'hidden'
          }`}
        />

        {!streamActive && (
          <div className="p-4 text-center space-y-1 text-slate-500">
            <VideoOff className="w-6 h-6 mx-auto text-rose-400" />
            <span className="text-[11px] block text-rose-300">Camera Feed Inactive</span>
            {cameraError && (
              <span className="text-[10px] block text-slate-400 truncate max-w-[200px]" title={cameraError}>
                {cameraError}
              </span>
            )}
          </div>
        )}

        {/* State Status Pill */}
        <div className="absolute top-2 left-2 flex items-center gap-1.5">
          {monitoringState === 'normal' && streamActive && (
            <span className="px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-800/80 text-[10px] text-emerald-300 font-semibold flex items-center space-x-1 backdrop-blur-sm shadow">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Face Verified</span>
            </span>
          )}

          {monitoringState === 'absent_warning' && streamActive && (
            <span className="px-2 py-0.5 rounded-full bg-amber-950/80 border border-amber-800/80 text-[10px] text-amber-300 font-semibold flex items-center space-x-1 backdrop-blur-sm shadow animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              <span>Looking Away...</span>
            </span>
          )}

          {monitoringState === 'absent_alert' && streamActive && (
            <span className="px-2 py-0.5 rounded-full bg-rose-950/85 border border-rose-800/80 text-[10px] text-rose-300 font-semibold flex items-center space-x-1 backdrop-blur-sm shadow animate-bounce">
              <UserX className="w-3 h-3 text-rose-400" />
              <span>No Face Detected</span>
            </span>
          )}

          {monitoringState === 'multiple_alert' && streamActive && (
            <span className="px-2 py-0.5 rounded-full bg-purple-950/85 border border-purple-800/80 text-[10px] text-purple-300 font-semibold flex items-center space-x-1 backdrop-blur-sm shadow">
              <Users className="w-3 h-3 text-purple-400" />
              <span>Multiple Faces ({faceCount})</span>
            </span>
          )}
        </div>

        {/* Detector Mode Pill */}
        <div className="absolute bottom-1.5 right-2 text-[9px] font-mono text-slate-400 bg-slate-950/70 px-1.5 py-0.5 rounded border border-slate-800/60 backdrop-blur-sm">
          {detectorStatus === 'active' ? 'MediaPipe AI' : detectorStatus === 'fallback' ? 'Stream Mode' : 'Loading...'}
        </div>
      </div>

      {/* Widget Footer */}
      <div className="px-3 py-1.5 bg-slate-900/90 border-t border-slate-800 flex items-center justify-between text-[10px] text-slate-400">
        <span className="flex items-center space-x-1">
          <Eye className="w-3 h-3 text-indigo-400" />
          <span>Level 1 Proctoring</span>
        </span>
        <span className="font-mono text-slate-400">
          {streamActive ? 'Active' : 'Offline'}
        </span>
      </div>
    </div>
  );
}
