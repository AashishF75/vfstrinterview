import React, { useState, useEffect, useRef } from 'react';
import {
  Play,
  ExternalLink,
  AlertCircle,
  Loader2,
  RefreshCw,
  ShieldCheck,
  X
} from 'lucide-react';

import {
  ALLOWED_YOUTUBE_HOSTS,
  extractYouTubeVideoId,
  getYouTubeEmbedUrl,
  getYouTubeExternalUrl,
  getYouTubeEmbedErrorMessage,
  resolveVideoPlayerProps,
} from '../utils/videoUtils';
import { loadYouTubeIframeApi } from '../utils/youtubePlayerLoader';

export {
  ALLOWED_YOUTUBE_HOSTS,
  extractYouTubeVideoId,
  getYouTubeEmbedUrl,
  getYouTubeExternalUrl,
  getYouTubeEmbedErrorMessage,
  resolveVideoPlayerProps,
};

/**
 * EmbeddedVideoPlayer
 * Accessible, responsive, in-site educational video player.
 * - Restrictive referrer-policy and lazy-loading
 * - Integrates YouTube IFrame Player API for reliable error interception (codes 101, 150, 100, 2, 5)
 * - Safe fallback to standard iframe if API is blocked by adblockers/network offline
 * - Guaranteed loading skeleton timeout to prevent indefinite spinning
 * - Allows switching between in-site embedded playback and direct external viewing
 * - Respects browser autoplay policies (no forced sound playback)
 * - Hides iframes in @media print stylesheets to keep PDF exports clean
 */
export default function EmbeddedVideoPlayer({
  videoUrl,
  embedUrl,
  videoId,
  title,
  provider,
  topic,
  canEmbed = true,
  autoStart = false,
  onClose,
}) {
  const playerConfig = resolveVideoPlayerProps({
    videoUrl,
    embedUrl,
    videoId,
    title,
    provider,
    topic,
    canEmbed,
  });

  const {
    resolvedVideoId,
    resolvedEmbedUrl,
    isEmbedSupported,
    safeExternalUrl,
    cleanTitle,
    cleanProvider,
    cleanTopic,
    iframeTitle,
    ariaPlayLabel,
    ariaExternalLabel,
  } = playerConfig;

  const [isPlaying, setIsPlaying] = useState(autoStart && isEmbedSupported);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [errorCode, setErrorCode] = useState(null);
  const [useIframeFallback, setUseIframeFallback] = useState(false);

  const containerRef = useRef(null);
  const playerRef = useRef(null);
  const isMountedRef = useRef(true);
  const watchdogTimerRef = useRef(null);

  // Set mounted state
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (watchdogTimerRef.current) {
        clearTimeout(watchdogTimerRef.current);
      }
      if (playerRef.current && typeof playerRef.current.destroy === 'function') {
        try {
          playerRef.current.destroy();
        } catch (_) {}
        playerRef.current = null;
      }
    };
  }, []);

  // Guard against indefinite loading if player or iframe stalls
  useEffect(() => {
    if (isPlaying && isLoading) {
      watchdogTimerRef.current = setTimeout(() => {
        if (isMountedRef.current) {
          setIsLoading(false);
        }
      }, 8000);
    }
    return () => {
      if (watchdogTimerRef.current) {
        clearTimeout(watchdogTimerRef.current);
        watchdogTimerRef.current = null;
      }
    };
  }, [isPlaying, isLoading]);

  // Initialize YouTube Player API or fallback to iframe when playback starts
  useEffect(() => {
    if (!isPlaying || !isEmbedSupported || hasError) {
      return;
    }

    setIsLoading(true);

    // If already in iframe fallback mode, skip YT.Player initialization
    if (useIframeFallback) {
      return;
    }

    let isSubscribed = true;

    loadYouTubeIframeApi(6000)
      .then((YT) => {
        if (!isSubscribed || !isMountedRef.current) return;
        if (!YT || !YT.Player || !containerRef.current) {
          setUseIframeFallback(true);
          return;
        }

        try {
          // Clean up previous instance if any
          if (playerRef.current && typeof playerRef.current.destroy === 'function') {
            try { playerRef.current.destroy(); } catch (_) {}
            playerRef.current = null;
          }

          const player = new YT.Player(containerRef.current, {
            videoId: resolvedVideoId,
            host: 'https://www.youtube-nocookie.com',
            playerVars: {
              rel: 0,
              modestbranding: 1,
              enablejsapi: 1,
              autoplay: 0, // Respect browser autoplay restrictions
            },
            events: {
              onReady: () => {
                if (isMountedRef.current) {
                  setIsLoading(false);
                }
              },
              onError: (event) => {
                if (isMountedRef.current) {
                  const errCode = event.data;
                  setErrorCode(errCode);
                  setHasError(true);
                  setIsLoading(false);
                }
              },
            },
          });

          playerRef.current = player;
        } catch (err) {
          // If YT.Player constructor fails, fallback to iframe
          if (isMountedRef.current) {
            setUseIframeFallback(true);
          }
        }
      })
      .catch(() => {
        // If YouTube API script failed to load (e.g. adblocker, offline),
        // fallback to standard iframe with DOM handlers
        if (isMountedRef.current) {
          setUseIframeFallback(true);
        }
      });

    return () => {
      isSubscribed = false;
    };
  }, [isPlaying, isEmbedSupported, resolvedVideoId, useIframeFallback, hasError]);

  const handleStartPlayback = () => {
    if (!isEmbedSupported) {
      setHasError(true);
      return;
    }
    setHasError(false);
    setErrorCode(null);
    setIsLoading(true);
    setIsPlaying(true);
  };

  const handleResetPlayback = () => {
    if (playerRef.current && typeof playerRef.current.destroy === 'function') {
      try { playerRef.current.destroy(); } catch (_) {}
      playerRef.current = null;
    }
    setIsPlaying(false);
    setIsLoading(true);
    setHasError(false);
    setErrorCode(null);
    setUseIframeFallback(false);
  };

  const handleKeyDownPlay = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleStartPlayback();
    }
  };

  return (
    <div className="w-full rounded-2xl bg-slate-950/90 border border-slate-800/90 overflow-hidden shadow-xl transition-all duration-300">
      {/* 1. In-Site Video Playback Mode */}
      {isPlaying && isEmbedSupported && !hasError ? (
        <div className="relative w-full aspect-video bg-black flex items-center justify-center">
          {/* Loading Skeleton */}
          {isLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-950 text-slate-400 z-10 space-y-2">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
              <span className="text-xs font-medium">Initializing secure video stream...</span>
            </div>
          )}

          {/* YouTube API Target Container OR Sandbox-Safe IFrame Fallback */}
          {useIframeFallback ? (
            <iframe
              src={resolvedEmbedUrl}
              title={iframeTitle}
              loading="lazy"
              referrerPolicy="strict-origin-when-cross-origin"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
              onLoad={() => setIsLoading(false)}
              onError={() => {
                setIsLoading(false);
                setHasError(true);
              }}
              className="w-full h-full border-0 print:hidden"
            />
          ) : (
            <div
              ref={containerRef}
              title={iframeTitle}
              className="w-full h-full border-0 print:hidden"
            />
          )}

          {/* Top Floating Control Bar */}
          <div className="absolute top-2 right-2 flex items-center space-x-1.5 z-20 print:hidden">
            {safeExternalUrl && (
              <a
                href={safeExternalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white backdrop-blur-md border border-slate-700/60 text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                title="Open video in new tab on YouTube"
                aria-label={ariaExternalLabel}
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
            {onClose ? (
              <button
                type="button"
                onClick={onClose}
                className="p-1.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white backdrop-blur-md border border-slate-700/60 text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                title="Close player"
                aria-label="Close player"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleResetPlayback}
                className="p-1.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white backdrop-blur-md border border-slate-700/60 text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                title="Return to preview banner"
                aria-label="Return to preview banner"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      ) : hasError || !isEmbedSupported ? (
        /* 2. Fallback State when Embedding is Disabled, Restricted, or Fails */
        <div className="p-6 bg-slate-900/80 border border-amber-500/20 rounded-2xl flex flex-col items-center text-center space-y-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center">
            <AlertCircle className="w-5 h-5" />
          </div>
          <div className="space-y-1 max-w-md">
            <h5 className="text-sm font-bold text-white">Direct Playback Recommended</h5>
            <p className="text-xs text-slate-400 leading-relaxed">
              {getYouTubeEmbedErrorMessage(errorCode)}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2 pt-1 print:hidden">
            {safeExternalUrl && (
              <a
                href={safeExternalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center space-x-1.5 shadow-lg shadow-indigo-600/20 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                aria-label={`Watch ${cleanTitle} on ${cleanProvider || 'YouTube'}`}
              >
                <span>Watch on {cleanProvider || 'Provider Platform'}</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
            {isEmbedSupported && (
              <button
                type="button"
                onClick={handleStartPlayback}
                className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition flex items-center space-x-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 cursor-pointer"
                aria-label="Retry loading video player"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retry</span>
              </button>
            )}
          </div>
        </div>
      ) : (
        /* 3. Sleek Video Poster & In-Site Launch Banner */
        <div className="relative w-full aspect-video bg-gradient-to-br from-slate-950 via-[#0a1024] to-[#0c142c] flex flex-col justify-between p-5 border border-slate-800/80 group overflow-hidden">
          {/* Subtle Cyber Grid and Ambient Radial Glow */}
          <div className="cyber-grid opacity-20 absolute inset-0 pointer-events-none" />
          <div className="absolute top-0 right-0 w-56 h-56 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none group-hover:bg-indigo-600/20 transition-all duration-700" />
          <div className="absolute bottom-0 left-0 w-44 h-44 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none group-hover:bg-cyan-500/15 transition-all duration-700" />

          {/* Top Metadata Badges */}
          <div className="flex items-center justify-between gap-2 relative z-10 flex-wrap">
            <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 truncate max-w-[200px]">
              {cleanTopic}
            </span>
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              <ShieldCheck className="w-3 h-3 mr-1 text-emerald-400" />
              <span>Verified Educational Content</span>
            </span>
          </div>

          {/* Center Play Button & Title Preview */}
          <div className="flex flex-col items-center justify-center text-center space-y-3 relative z-10 my-auto">
            <button
              type="button"
              onClick={handleStartPlayback}
              onKeyDown={handleKeyDownPlay}
              className="w-14 h-14 rounded-full bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-500 text-white flex items-center justify-center shadow-xl shadow-indigo-600/30 ring-4 ring-indigo-500/20 group-hover:ring-indigo-500/40 group-hover:shadow-indigo-500/50 hover:scale-110 active:scale-95 transition-all duration-300 border border-white/20 print:hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 cursor-pointer"
              title="Watch tutorial directly on report page"
              aria-label={ariaPlayLabel}
            >
              <Play className="w-6 h-6 ml-0.5 fill-white" />
            </button>
            <div className="space-y-1 max-w-md px-2">
              <h5 className="text-sm font-bold text-white group-hover:text-cyan-200 transition-colors line-clamp-2 break-words">
                {cleanTitle}
              </h5>
              <p className="text-xs text-slate-400 truncate">
                Curated by <strong className="text-slate-300 font-medium">{cleanProvider}</strong>
              </p>
            </div>
          </div>

          {/* Bottom Action Footer */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 relative z-10 print:hidden">
            <button
              type="button"
              onClick={handleStartPlayback}
              onKeyDown={handleKeyDownPlay}
              className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 transition flex items-center space-x-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 rounded cursor-pointer"
              aria-label={`Watch ${cleanTitle} within report`}
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Watch within Report</span>
            </button>

            {safeExternalUrl && (
              <a
                href={safeExternalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-400 hover:text-slate-200 transition flex items-center space-x-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 rounded"
                aria-label={ariaExternalLabel}
              >
                <span>Open on YouTube</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>
      )}

      {/* Clean Printable Fallback (Visible ONLY when printing or saving as PDF) */}
      <div className="hidden print:block p-3 text-slate-800 border-t border-slate-300 text-xs">
        <p><strong>Educational Tutorial:</strong> {cleanTitle} ({cleanProvider})</p>
        {safeExternalUrl && <p className="font-mono text-[11px] text-slate-600">Video Link: {safeExternalUrl}</p>}
      </div>
    </div>
  );
}
