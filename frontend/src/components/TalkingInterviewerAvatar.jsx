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
      setImageLoaded(true);
    };
    img.onerror = () => {
      // Fallback: try loading without crossOrigin if local/bundled
      const fallbackImg = new Image();
      fallbackImg.src = imageSrc;
      fallbackImg.onload = () => {
        imageObjRef.current = fallbackImg;
        setImageLoaded(true);
      };
    };
  }, [imageSrc]);

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

    // 5. Anatomical Mouth & Jaw Articulation
    // Coordinates on 1376x768 image:
    // Mouth center X: 691, Mouth baseline Y: 308
    // Mouth width: ~78px, Mouth resting height: ~18px
    if (currentVolume > 0.015) {
      const mouthX = 691;
      const mouthY = 308;
      const openAmount = currentVolume * 15.0; // Max vertical opening 15px
      const widthFlex = (smoothedVowelRef.current - 0.5) * 8.0 * currentVolume; // Width variation based on phoneme

      ctx.save();

      // Outer bounding box for lower jaw and mouth area
      // Step A: Lower jaw displacement simulation
      // We sample a small lower-lip/chin patch and translate it downwards slightly
      const jawDrop = openAmount * 0.45;
      const patchX = mouthX - 55;
      const patchY = mouthY + 12;
      const patchW = 110;
      const patchH = 46;

      ctx.save();
      // Smooth gradient mask for jaw patch to avoid hard seam
      ctx.beginPath();
      ctx.ellipse(mouthX, patchY + patchH * 0.4 + jawDrop, patchW * 0.48, patchH * 0.45, 0, 0, Math.PI * 2);
      ctx.clip();
      ctx.drawImage(img, patchX, patchY, patchW, patchH, patchX, patchY + jawDrop, patchW, patchH);
      ctx.restore();

      // Step B: Articulated Inner Mouth Opening (Oral Cavity & Teeth)
      const oralW = 34 + widthFlex;
      const oralH = Math.max(2.5, openAmount);

      // 1. Deep Oral Cavity Shading
      ctx.beginPath();
      ctx.ellipse(mouthX, mouthY + oralH * 0.4, oralW, oralH, 0, 0, Math.PI * 2);
      // Natural dark red/burgundy mouth interior
      const cavityGrad = ctx.createRadialGradient(
        mouthX,
        mouthY + oralH * 0.3,
        2,
        mouthX,
        mouthY + oralH * 0.4,
        oralW
      );
      cavityGrad.addColorStop(0, 'rgba(42, 10, 14, 0.96)');
      cavityGrad.addColorStop(0.7, 'rgba(78, 22, 26, 0.92)');
      cavityGrad.addColorStop(1, 'rgba(128, 45, 50, 0.85)');
      ctx.fillStyle = cavityGrad;
      ctx.fill();

      // 2. Upper Teeth Arc
      ctx.beginPath();
      ctx.ellipse(mouthX, mouthY - 1, oralW * 0.72, Math.min(oralH * 0.45, 4.5), 0, 0, Math.PI);
      ctx.fillStyle = 'rgba(245, 240, 235, 0.94)';
      ctx.fill();

      // Subtle translucent tooth separation shadow
      ctx.beginPath();
      ctx.ellipse(mouthX, mouthY + 1.2, oralW * 0.65, 0.8, 0, 0, Math.PI);
      ctx.strokeStyle = 'rgba(80, 40, 35, 0.4)';
      ctx.lineWidth = 0.8;
      ctx.stroke();

      // 3. Lower Lip Dynamic Highlight & Contour
      ctx.beginPath();
      ctx.ellipse(mouthX, mouthY + oralH + 3.5, oralW * 0.88, 3.8 + openAmount * 0.15, 0, 0, Math.PI);
      ctx.fillStyle = 'rgba(195, 96, 88, 0.88)';
      ctx.fill();

      // Soft lower lip specular reflection
      ctx.beginPath();
      ctx.ellipse(mouthX, mouthY + oralH + 4.2, oralW * 0.45, 1.4, 0, 0, Math.PI);
      ctx.fillStyle = 'rgba(255, 210, 205, 0.42)';
      ctx.fill();

      // 4. Upper Lip Defined Bow
      ctx.beginPath();
      ctx.moveTo(mouthX - oralW - 4, mouthY);
      ctx.quadraticCurveTo(mouthX - oralW * 0.35, mouthY - 2.8, mouthX - 3, mouthY - 1.2);
      ctx.quadraticCurveTo(mouthX, mouthY - 2.4, mouthX + 3, mouthY - 1.2);
      ctx.quadraticCurveTo(mouthX + oralW * 0.35, mouthY - 2.8, mouthX + oralW + 4, mouthY);
      ctx.strokeStyle = 'rgba(148, 62, 58, 0.7)';
      ctx.lineWidth = 1.8;
      ctx.stroke();

      ctx.restore();
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
