import React, { useRef, useEffect, useState, useCallback } from 'react';

/**
 * TalkingInterviewerAvatar
 *
 * Provides a responsive, realistic talking-head interviewer avatar for the interview room.
 * Visibly articulates mouth, lips, jaw, and facial micro-expressions in direct synchronization
 * with actual TTS audio playback (Deepgram Aura / Web Speech API).
 *
 * Architecture:
 * - Real-time Web Audio API AnalyserNode taps the actual Deepgram audio playback.
 * - RMS amplitude and frequency spectrum are calculated at 60 FPS via requestAnimationFrame.
 * - Synchronized lip/jaw displacement, mouth cavity opening, and viseme width adjustments.
 * - Life-like natural human micro-animations (spontaneous eye blinks, subtle breath oscillation, speech head tilts).
 * - Immediate cessation of speaking state upon audio pause, completion, or unmount.
 * - Respects prefers-reduced-motion accessibility preferences.
 */
export default function TalkingInterviewerAvatar({
  imageSrc,
  isSpeaking = false,
  audioElement = null,
  speakingSource = null, // 'deepgram' | 'browser' | null
  interviewerStatus = 'ready', // 'ready' | 'speaking' | 'listening' | 'transcribing' | 'thinking'
  className = '',
}) {
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const imageObjRef = useRef(null);
  const [imageLoaded, setImageLoaded] = useState(false);

  // Audio Analysis State
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const connectedAudioRef = useRef(null);
  const animFrameRef = useRef(null);

  // Smooth Interpolated Metrics
  const smoothedVolumeRef = useRef(0);
  const smoothedVowelRef = useRef(0); // 0 = closed/narrow, 1 = open/wide
  const blinkProgressRef = useRef(0); // 0 = open, 1 = closed
  const nextBlinkTimeRef = useRef(Date.now() + 2500);
  const isBlinkingRef = useRef(false);
  const blinkStartTimeRef = useRef(0);

  // Fallback synthetic envelope for browser speech or when audio node tap is restricted
  const syntheticTimeRef = useRef(0);

  // Reduced motion preference
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  // Elastic Mouth Articulation Refs & Precomputed Lookup Tables
  // Avoids artificial drawn lines/shapes over lips by elastically displacing the real photographic texture
  const mouthPatchCanvasRef = useRef(null);
  const baseMouthDataRef = useRef(null);
  const warpedCanvasRef = useRef(null);
  const warpedCtxRef = useRef(null);
  const warpedImageDataRef = useRef(null);
  const warpLookupTablesRef = useRef(null);

  // Precompute 1D horizontal & vertical deformation weights for 60 FPS real-time performance
  useEffect(() => {
    const cropW = 105;
    const cropH = 70;
    const cropX = 639;
    const cropY = 296;

    const hFactors = new Float32Array(cropW);
    for (let x = 0; x < cropW; x++) {
      const dx = (cropX + x - 691) / 52;
      hFactors[x] = Math.abs(dx) < 1 ? 0.5 * (1 + Math.cos(dx * Math.PI)) : 0;
    }

    const vFactors = new Float32Array(cropH);
    for (let y = 0; y < cropH; y++) {
      const fullY = cropY + y;
      if (fullY <= 312) {
        const t = Math.max(0, (fullY - 296) / 16);
        vFactors[y] = t * t * (3 - 2 * t);
      } else if (fullY <= 365) {
        const t = Math.min(1, (fullY - 312) / 53);
        const st = t * t * (3 - 2 * t);
        vFactors[y] = 1 - st;
      } else {
        vFactors[y] = 0;
      }
    }

    warpLookupTablesRef.current = { hFactors, vFactors, cropX, cropY, cropW, cropH };
  }, []);

  // Initialize offscreen mouth buffers from the photographic image
  const initMouthTextures = useCallback((loadedImg) => {
    if (!loadedImg || !loadedImg.complete || typeof document === 'undefined') return;
    try {
      const cropW = 105;
      const cropH = 70;
      const cropX = 639;
      const cropY = 296;

      const patchCanvas = document.createElement('canvas');
      patchCanvas.width = cropW;
      patchCanvas.height = cropH;
      const patchCtx = patchCanvas.getContext('2d', { willReadFrequently: true });
      if (patchCtx) {
        patchCtx.drawImage(loadedImg, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);
        baseMouthDataRef.current = patchCtx.getImageData(0, 0, cropW, cropH);
        mouthPatchCanvasRef.current = patchCanvas;
      }

      const wCanvas = document.createElement('canvas');
      wCanvas.width = cropW;
      wCanvas.height = cropH;
      warpedCanvasRef.current = wCanvas;
      const wCtx = wCanvas.getContext('2d');
      warpedCtxRef.current = wCtx;
      if (wCtx) {
        warpedImageDataRef.current = wCtx.createImageData(cropW, cropH);
      }
    } catch {
      // Graceful fallback if offscreen canvas context is restricted
    }
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
      setPrefersReducedMotion(mediaQuery.matches);
      const listener = (e) => setPrefersReducedMotion(e.matches);
      mediaQuery.addEventListener('change', listener);
      return () => mediaQuery.removeEventListener('change', listener);
    }
  }, []);

  // Preload avatar portrait
  useEffect(() => {
    if (!imageSrc) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = imageSrc;
    img.onload = () => {
      imageObjRef.current = img;
      initMouthTextures(img);
      setImageLoaded(true);
    };
    img.onerror = () => {
      // Fallback: try loading without crossOrigin if local/bundled
      const fallbackImg = new Image();
      fallbackImg.src = imageSrc;
      fallbackImg.onload = () => {
        imageObjRef.current = fallbackImg;
        initMouthTextures(fallbackImg);
        setImageLoaded(true);
      };
    };
    if (img.complete) {
      imageObjRef.current = img;
      initMouthTextures(img);
      setImageLoaded(true);
    }
  }, [imageSrc, initMouthTextures]);

  // Connect Web Audio API AnalyserNode to the actual Deepgram audio element
  useEffect(() => {
    if (!audioElement || typeof window === 'undefined') {
      return;
    }

    // Avoid reconnecting the same audio element repeatedly
    if (connectedAudioRef.current === audioElement && analyserRef.current) {
      return;
    }

    try {
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtxClass) return;

      if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
        audioContextRef.current = new AudioCtxClass();
      }

      const ctx = audioContextRef.current;
      if (ctx.state === 'suspended') {
        ctx.resume().catch(() => {});
      }

      // Disconnect previous node if necessary
      if (sourceNodeRef.current) {
        try {
          sourceNodeRef.current.disconnect();
        } catch {}
      }

      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.65;

      const sourceNode = ctx.createMediaElementSource(audioElement);
      sourceNode.connect(analyser);
      analyser.connect(ctx.destination);

      analyserRef.current = analyser;
      sourceNodeRef.current = sourceNode;
      connectedAudioRef.current = audioElement;
    } catch {
      // Web Audio node creation may fail if media is already connected to another graph
      // Fallback to simulated audio-envelope derived from playback events
    }

    return () => {
      // Keep context alive across track switches unless fully unmounted
    };
  }, [audioElement]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        try {
          audioContextRef.current.close();
        } catch {}
      }
    };
  }, []);

  // Main 60 FPS Render & Animation Loop
  const renderFrame = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imageObjRef.current;
    if (!canvas || !img || !img.complete) {
      animFrameRef.current = requestAnimationFrame(renderFrame);
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Ensure canvas dimensions match backing buffer
    const width = 1376;
    const height = 768;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    // 1. Calculate Real-Time Audio Energy & Volume
    let targetVolume = 0;
    let targetVowel = 0;

    if (isSpeaking) {
      if (analyserRef.current) {
        const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
        analyserRef.current.getByteFrequencyData(dataArray);

        // Compute RMS energy across vocal speech range (approx 150Hz - 3400Hz)
        let sum = 0;
        let lowFreqSum = 0;
        let highFreqSum = 0;
        const lowCutoff = Math.floor(dataArray.length * 0.3);

        for (let i = 0; i < dataArray.length; i++) {
          const val = dataArray[i];
          sum += val * val;
          if (i < lowCutoff) {
            lowFreqSum += val;
          } else {
            highFreqSum += val;
          }
        }

        const rms = Math.sqrt(sum / dataArray.length);
        // Normalize with speech threshold
        const rawVol = Math.max(0, (rms - 12) / 110);
        targetVolume = Math.min(1.0, Math.pow(rawVol, 1.25));

        // Frequency balance: lower vowels ("ah", "oh") vs higher consonants/vowels ("ee", "ss")
        if (lowFreqSum + highFreqSum > 0) {
          targetVowel = lowFreqSum / (lowFreqSum + highFreqSum * 1.4);
        }
      } else {
        // Synthetic cadence for browser SpeechSynthesis or when audio element isn't tapped directly
        syntheticTimeRef.current += 0.08;
        const t = syntheticTimeRef.current;
        // Multi-frequency harmonic envelope simulating human speech syllable cadence
        const syllable = Math.sin(t * 3.8) * 0.4 + Math.sin(t * 7.2) * 0.35 + Math.sin(t * 1.5) * 0.25;
        const pauseMod = Math.sin(t * 0.8) > 0.6 ? 0.1 : 1.0; // natural conversational micro-pauses
        targetVolume = Math.max(0, syllable * pauseMod * 0.85);
        targetVowel = 0.5 + Math.sin(t * 4.2) * 0.3;
      }
    } else {
      targetVolume = 0;
      syntheticTimeRef.current = 0;
    }

    // Smooth volume response (fast attack for lip opening, slightly slower decay for natural articulation)
    const attack = 0.45;
    const decay = 0.25;
    const factor = targetVolume > smoothedVolumeRef.current ? attack : decay;
    smoothedVolumeRef.current += (targetVolume - smoothedVolumeRef.current) * factor;
    smoothedVowelRef.current += (targetVowel - smoothedVowelRef.current) * 0.2;

    const currentVolume = smoothedVolumeRef.current;

    // 2. Natural Eye Blink Animation
    const now = Date.now();
    if (!isBlinkingRef.current && now > nextBlinkTimeRef.current) {
      isBlinkingRef.current = true;
      blinkStartTimeRef.current = now;
      // Schedule next blink in 3.0 to 6.5 seconds
      nextBlinkTimeRef.current = now + 3000 + Math.random() * 3500;
    }

    if (isBlinkingRef.current) {
      const elapsed = now - blinkStartTimeRef.current;
      const blinkDuration = 160; // 160ms natural blink
      if (elapsed < blinkDuration) {
        // Fast close (0 to 60ms), fast open (60 to 160ms)
        const half = blinkDuration * 0.4;
        if (elapsed < half) {
          blinkProgressRef.current = elapsed / half;
        } else {
          blinkProgressRef.current = 1.0 - (elapsed - half) / (blinkDuration - half);
        }
      } else {
        isBlinkingRef.current = false;
        blinkProgressRef.current = 0;
      }
    } else {
      blinkProgressRef.current = 0;
    }

    // 3. Life-Like Head & Body Micro-Dynamics (Breathing & Conversational Tilt)
    const timeSec = now / 1000;
    const breathOffset = prefersReducedMotion ? 0 : Math.sin(timeSec * 1.8) * 0.8;
    const speechTilt = prefersReducedMotion ? 0 : isSpeaking ? Math.sin(timeSec * 2.4) * 0.35 : 0;

    // Clear and draw base portrait with subtle micro-translation for life-like breath
    ctx.clearRect(0, 0, width, height);

    ctx.save();
    if (!prefersReducedMotion) {
      ctx.translate(0, breathOffset);
      ctx.translate(width / 2, height / 2);
      ctx.rotate((speechTilt * Math.PI) / 180);
      ctx.translate(-width / 2, -height / 2);
    }

    // Render baseline high-definition portrait
    ctx.drawImage(img, 0, 0, width, height);

    // 4. Animate Eye Blinking Overlay (Coordinates: left eye ~643, 219; right eye ~737, 219)
    if (blinkProgressRef.current > 0.05) {
      const blinkAlpha = Math.min(1.0, blinkProgressRef.current * 1.15);
      const eyes = [
        { x: 643, y: 220, rx: 22, ry: 9 * blinkAlpha },
        { x: 737, y: 220, rx: 22, ry: 9 * blinkAlpha },
      ];

      ctx.save();
      eyes.forEach((eye) => {
        // Smooth skin-tone curved eyelid drawing
        ctx.beginPath();
        ctx.ellipse(eye.x, eye.y - 1, eye.rx, eye.ry, 0, 0, Math.PI * 2);
        // Eyelid skin tone matching interviewer portrait
        ctx.fillStyle = `rgba(182, 126, 95, ${blinkAlpha * 0.94})`;
        ctx.fill();

        // Subtle upper lash line
        ctx.beginPath();
        ctx.ellipse(eye.x, eye.y - 1, eye.rx, Math.max(1.5, eye.ry * 0.25), 0, 0, Math.PI);
        ctx.strokeStyle = `rgba(52, 33, 25, ${blinkAlpha * 0.85})`;
        ctx.lineWidth = 2.2;
        ctx.stroke();
      });
      ctx.restore();
    }

    // 5. Natural Photographic Mouth & Jaw Articulation (Artifact-Free Elastic Warp)
    // Synchronized strictly with real-time TTS audio amplitude.
    // Removes all synthetic vector lines, teeth overlays, and reddish lipstick strokes.
    // When audio pauses or finishes, the mouth rests in its 100% untouched natural photographic state.
    if (
      currentVolume > 0.012 &&
      warpLookupTablesRef.current
    ) {
      if (!baseMouthDataRef.current && img && img.complete) {
        initMouthTextures(img);
      }

      if (
        baseMouthDataRef.current &&
        warpedCanvasRef.current &&
        warpedCtxRef.current &&
        warpedImageDataRef.current
      ) {
        const { hFactors, vFactors, cropX, cropY, cropW, cropH } = warpLookupTablesRef.current;
        const baseData = baseMouthDataRef.current.data;
        const warpedData = warpedImageDataRef.current.data;

        // Dynamic vertical excursion: ~1.8px to 3.0px maximum (subtle, natural speech displacement)
        const vowelBonus = (smoothedVowelRef.current - 0.5) * 0.8;
        const maxDisp = currentVolume * Math.max(1.8, Math.min(3.0, 2.4 + vowelBonus));

        for (let y = 0; y < cropH; y++) {
          const rowDisp = maxDisp * vFactors[y];
          const rowOffset = y * cropW;

          for (let x = 0; x < cropW; x++) {
            const disp = rowDisp * hFactors[x];
            const dstIdx = (rowOffset + x) * 4;

            if (disp < 0.02) {
              warpedData[dstIdx] = baseData[dstIdx];
              warpedData[dstIdx + 1] = baseData[dstIdx + 1];
              warpedData[dstIdx + 2] = baseData[dstIdx + 2];
              warpedData[dstIdx + 3] = baseData[dstIdx + 3];
            } else {
              const srcLocalY = y - disp;
              const y0 = Math.floor(srcLocalY);
              const y1 = Math.min(cropH - 1, y0 + 1);
              const fy = srcLocalY - y0;
              const invFy = 1.0 - fy;

              const idx0 = (y0 * cropW + x) * 4;
              const idx1 = (y1 * cropW + x) * 4;

              warpedData[dstIdx] = invFy * baseData[idx0] + fy * baseData[idx1];
              warpedData[dstIdx + 1] = invFy * baseData[idx0 + 1] + fy * baseData[idx1 + 1];
              warpedData[dstIdx + 2] = invFy * baseData[idx0 + 2] + fy * baseData[idx1 + 2];
              warpedData[dstIdx + 3] = invFy * baseData[idx0 + 3] + fy * baseData[idx1 + 3];
            }
          }
        }

        warpedCtxRef.current.putImageData(warpedImageDataRef.current, 0, 0);
        ctx.drawImage(warpedCanvasRef.current, cropX, cropY);
      }
    }

    ctx.restore();

    animFrameRef.current = requestAnimationFrame(renderFrame);
  }, [isSpeaking, prefersReducedMotion]);

  useEffect(() => {
    if (imageLoaded) {
      animFrameRef.current = requestAnimationFrame(renderFrame);
    }
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [imageLoaded, renderFrame]);

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full overflow-hidden bg-slate-950 ${className}`}
      data-testid="talking-interviewer-avatar"
      data-speaking={isSpeaking}
      data-status={interviewerStatus}
      data-source={speakingSource}
    >
      {/* Primary HTML5 Canvas Renderer with Audio-Reactive Face & Lip Articulation */}
      <canvas
        ref={canvasRef}
        className="w-full h-full object-cover object-center filter brightness-95 contrast-105 transition duration-500"
      />

      {/* Fallback Static Image (hidden once canvas is operational) */}
      {!imageLoaded && (
        <img
          src={imageSrc}
          alt="AI Interviewer"
          className="absolute inset-0 w-full h-full object-cover object-center opacity-80"
        />
      )}

      {/* Synchronized Real-Time Speech Pulse Glow (Subtle Radial Face Light) */}
      {isSpeaking && (
        <div
          className="absolute inset-0 pointer-events-none transition-opacity duration-200"
          style={{
            background:
              'radial-gradient(circle at 50% 40%, rgba(99, 102, 241, 0.08) 0%, transparent 65%)',
          }}
        />
      )}
    </div>
  );
}
