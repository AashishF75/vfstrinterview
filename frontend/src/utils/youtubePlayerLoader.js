/**
 * Singleton loader for the YouTube IFrame Player API.
 * Ensures only one script tag is injected, manages initialization timeouts,
 * handles network/adblocker failures gracefully, and resolves with window.YT.
 */

let ytApiPromise = null;

export function loadYouTubeIframeApi(timeoutMs = 7000) {
  // If window.YT is already loaded and ready
  if (typeof window !== 'undefined' && window.YT && window.YT.Player) {
    return Promise.resolve(window.YT);
  }

  if (ytApiPromise) {
    return ytApiPromise;
  }

  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return Promise.reject(new Error('Browser environment required to load YouTube API'));
  }

  ytApiPromise = new Promise((resolve, reject) => {
    let timeoutId = null;

    const cleanup = () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    };

    timeoutId = setTimeout(() => {
      cleanup();
      // Reset loader on timeout so future retries can re-attempt
      ytApiPromise = null;
      reject(new Error('Timed out waiting for YouTube IFrame Player API to initialize'));
    }, timeoutMs);

    // Chain to any existing onYouTubeIframeAPIReady callback
    const prevReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      cleanup();
      if (typeof prevReady === 'function') {
        try {
          prevReady();
        } catch (_) {}
      }
      resolve(window.YT);
    };

    // Check if script tag is already in document
    const existingScript = document.querySelector('script[src*="youtube.com/iframe_api"]');
    if (!existingScript) {
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      tag.async = true;
      tag.onerror = () => {
        cleanup();
        ytApiPromise = null;
        reject(new Error('Failed to load YouTube IFrame Player API script (blocked or network offline)'));
      };

      const firstScriptTag = document.getElementsByTagName('script')[0];
      if (firstScriptTag && firstScriptTag.parentNode) {
        firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
      } else if (document.head) {
        document.head.appendChild(tag);
      }
    }
  });

  return ytApiPromise;
}

/**
 * Helper strictly for unit testing to reset singleton state.
 */
export function resetYouTubeIframeApiForTesting() {
  ytApiPromise = null;
}
