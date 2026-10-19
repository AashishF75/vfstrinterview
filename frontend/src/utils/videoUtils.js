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
