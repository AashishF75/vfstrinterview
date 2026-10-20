export const ALLOWED_YOUTUBE_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'youtube-nocookie.com',
  'www.youtube-nocookie.com',
  'youtu.be',
]);

/**
 * Safely extracts an 11-character YouTube video ID from standard watch, short, or embed URLs.
 * Validates trusted YouTube hostnames and protocols, rejecting deceptive domains, credentials,
 * unexpected ports, and malformed inputs to prevent iframe injection.
 */
export function extractYouTubeVideoId(url) {
  if (!url || typeof url !== 'string') return null;
  const trimmed = url.trim();

  // Direct 11-character YouTube video ID string
  if (/^[a-zA-Z0-9_-]{11}$/.test(trimmed)) {
    return trimmed;
  }

  try {
    const parsed = new URL(trimmed);
    if (!['http:', 'https:'].includes(parsed.protocol)) return null;
    if (parsed.username || parsed.password) return null;
    if (parsed.port && !['80', '443'].includes(parsed.port)) return null;

    const hostname = parsed.hostname.toLowerCase();
    if (!ALLOWED_YOUTUBE_HOSTS.has(hostname)) return null;

    // youtu.be/<id>
    if (hostname === 'youtu.be') {
      const match = parsed.pathname.match(/^\/([a-zA-Z0-9_-]{11})(?:\/|\?|#|$)/);
      return match ? match[1] : null;
    }

    // youtube.com / youtube-nocookie.com /embed/<id>
    if (parsed.pathname.startsWith('/embed/')) {
      const match = parsed.pathname.match(/^\/embed\/([a-zA-Z0-9_-]{11})(?:\/|\?|#|$)/);
      return match ? match[1] : null;
    }

    // /shorts/<id>
    if (parsed.pathname.startsWith('/shorts/')) {
      const match = parsed.pathname.match(/^\/shorts\/([a-zA-Z0-9_-]{11})(?:\/|\?|#|$)/);
      return match ? match[1] : null;
    }

    // Standard /watch?v=<id>
    const vParam = parsed.searchParams.get('v');
    if (vParam && /^[a-zA-Z0-9_-]{11}$/.test(vParam)) {
      return vParam;
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * Constructs a privacy-enhanced, sandbox-safe YouTube embed URL.
 * Uses youtube-nocookie.com domain with modestbranding, rel=0, and enablejsapi=1.
 */
export function getYouTubeEmbedUrl(urlOrId) {
  if (!urlOrId) return null;
  const videoId = /^[a-zA-Z0-9_-]{11}$/.test(urlOrId) ? urlOrId : extractYouTubeVideoId(urlOrId);
  if (!videoId) return null;
  return `https://www.youtube-nocookie.com/embed/${videoId}?rel=0&modestbranding=1&enablejsapi=1`;
}

/**
 * Constructs a safe external watch URL pointing strictly to standard YouTube watch path.
 * Strips any tracking parameters, credentials, or session data.
 */
export function getYouTubeExternalUrl(urlOrId) {
  if (!urlOrId || typeof urlOrId !== 'string') return null;
  const videoId = /^[a-zA-Z0-9_-]{11}$/.test(urlOrId.trim())
    ? urlOrId.trim()
    : extractYouTubeVideoId(urlOrId);
  if (!videoId) return null;
  return `https://www.youtube.com/watch?v=${videoId}`;
}

/**
 * Maps YouTube error codes to student-friendly, actionable diagnostic messages.
 */
export function getYouTubeEmbedErrorMessage(errorCode) {
  const code = Number(errorCode);
  switch (code) {
    case 101:
    case 150:
      return 'The content owner has restricted in-site playback for this video. You can watch it directly on the provider platform.';
    case 100:
      return 'This educational video has been removed, marked private, or is unavailable in your region.';
    case 2:
      return 'The video link contains an invalid parameter or syntax.';
    case 5:
      return 'An HTML5 player error occurred while rendering the video stream.';
    default:
      return 'In-site embedding for this video is restricted or unavailable.';
  }
}

/**
 * Resolves player configuration and accessibility attributes from raw props.
 */
export function resolveVideoPlayerProps({
  videoUrl,
  embedUrl,
  videoId,
  title = 'Topic Guide',
  provider = 'VFSTR Curated Resource',
  topic = 'Learning Resource',
  canEmbed = true,
} = {}) {
  const resolvedVideoId = videoId || extractYouTubeVideoId(videoUrl);
  const resolvedEmbedUrl = embedUrl || (resolvedVideoId ? getYouTubeEmbedUrl(resolvedVideoId) : null);
  const isEmbedSupported = Boolean(canEmbed && resolvedEmbedUrl);
  const safeExternalUrl = resolvedVideoId
    ? getYouTubeExternalUrl(resolvedVideoId)
    : (videoUrl && /^https?:\/\//i.test(videoUrl) ? videoUrl : null);

  const cleanTitle = (title || 'Topic Guide').trim();
  const cleanProvider = (provider || 'VFSTR Curated Resource').trim();
  const cleanTopic = (topic || 'Learning Resource').trim();

  return {
    resolvedVideoId,
    resolvedEmbedUrl,
    isEmbedSupported,
    safeExternalUrl,
    cleanTitle,
    cleanProvider,
    cleanTopic,
    iframeTitle: `Educational Tutorial: ${cleanTitle} by ${cleanProvider}`,
    ariaPlayLabel: `Play tutorial: ${cleanTitle}`,
    ariaExternalLabel: `Watch ${cleanTitle} on ${cleanProvider || 'YouTube'} in new tab`,
  };
}
