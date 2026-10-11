import React, { useState, useEffect, useRef } from 'react';
import { 
  Camera, 
  ShieldCheck, 
  Eye, 
  EyeOff, 
  CheckCircle2, 
  AlertCircle, 
  Video, 
  VideoOff, 
  Sparkles,
  Lock,
  HelpCircle
} from 'lucide-react';

export default function ProctoringPreflightModal({ onConsentGiven, studentRegistration }) {
  const [hasCameraPermission, setHasCameraPermission] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(true);
  const [cameraError, setCameraError] = useState(null);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  // Request initial camera test feed
  const requestCameraAccess = async () => {
    setCameraLoading(true);
    setCameraError(null);

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera access is not supported by your browser.');
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
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setHasCameraPermission(true);
      setCameraLoading(false);
    } catch (err) {
      setCameraLoading(false);
      setHasCameraPermission(false);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setCameraError('Camera permission was denied. Please allow camera access in your browser settings to proceed.');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setCameraError('No webcam was found on this device. Please connect a camera.');
      } else {
        setCameraError(err.message || 'Unable to access camera.');
      }
    }
  };

  useEffect(() => {
    requestCameraAccess();

    return () => {
      // Stop preview stream when modal closes
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  const handleConfirm = () => {
    if (!agreedToTerms) return;
    // Pass active stream or notify permission granted
    onConsentGiven({
      cameraActive: hasCameraPermission,
      stream: streamRef.current,
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 sm:p-7 shadow-2xl space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 flex items-center justify-center shadow-lg shadow-indigo-600/10">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                Interview Integrity & Camera Check
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  Level 1 Proctoring
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Vignan University Assessment Protocol • Candidate: <span className="font-mono text-indigo-300">{studentRegistration}</span>
              </p>
            </div>
          </div>
        </div>

        {/* Video Preview + Camera Status */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
          {/* Camera preview window */}
          <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800 aspect-video flex items-center justify-center shadow-inner">
            <video
              ref={videoRef}
              muted
              playsInline
              className={`w-full h-full object-cover transform -scale-x-100 ${
                hasCameraPermission ? 'block' : 'hidden'
              }`}
            />

            {!hasCameraPermission && (
              <div className="p-4 text-center space-y-2">
                {cameraLoading ? (
                  <div className="text-xs text-slate-400 animate-pulse flex flex-col items-center gap-2">
                    <Video className="w-8 h-8 text-indigo-400 animate-bounce" />
                    <span>Checking webcam connectivity...</span>
                  </div>
                ) : (
                  <div className="text-xs text-slate-400 space-y-2">
                    <VideoOff className="w-8 h-8 text-rose-400 mx-auto" />
                    <span className="text-rose-300 block font-medium">Camera Feed Inactive</span>
                    <button
                      type="button"
                      onClick={requestCameraAccess}
                      className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition"
                    >
                      Retry Camera Access
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Live Pill Overlay */}
            {hasCameraPermission && (
              <div className="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-800/80 text-[10px] text-emerald-300 font-semibold flex items-center space-x-1.5 backdrop-blur-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>Camera Stream Ready</span>
              </div>
            )}
          </div>

          {/* Privacy Guarantees */}
          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
              <span className="font-semibold text-slate-200 block text-[11px] uppercase tracking-wider text-indigo-400">
                Privacy Safeguards
              </span>
              <ul className="space-y-1.5 text-slate-400">
                <li className="flex items-start space-x-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span><strong>Zero Video Recording:</strong> Raw camera video or snapshots are never recorded or stored.</span>
                </li>
                <li className="flex items-start space-x-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span><strong>Local Face Detection:</strong> Only browser-side face presence counts and tab visibility states are logged.</span>
                </li>
                <li className="flex items-start space-x-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span><strong>Fair Assessment:</strong> Proctoring signals do not reduce answer scores or trigger automatic failure.</span>
                </li>
              </ul>
            </div>

            {cameraError && (
              <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>{cameraError}</span>
              </div>
            )}
          </div>
        </div>

        {/* Candidate Acknowledgment Checkbox */}
        <div className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/80 flex items-start space-x-3 text-xs text-slate-300">
          <input
            type="checkbox"
            id="acknowledge-proctoring-terms"
            checked={agreedToTerms}
            onChange={(e) => setAgreedToTerms(e.target.checked)}
            className="mt-0.5 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500 cursor-pointer w-4 h-4"
          />
          <label htmlFor="acknowledge-proctoring-terms" className="cursor-pointer select-none leading-relaxed">
            I consent to camera status and tab-switch monitoring during this interview attempt. I acknowledge that keeping the camera active and remaining on the interview tab is required by university guidelines.
          </label>
        </div>

        {/* Footer Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800">
          <div className="text-[11px] text-slate-500 flex items-center space-x-1">
            <Lock className="w-3.5 h-3.5 text-slate-400" />
            <span>End-to-end authenticated session telemetry</span>
          </div>

          <button
            type="button"
            id="confirm-proctoring-consent-btn"
            disabled={!agreedToTerms}
            onClick={handleConfirm}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold text-xs shadow-lg shadow-indigo-600/20 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            <span>I Agree & Begin Interview</span>
          </button>
        </div>
      </div>
    </div>
  );
}
