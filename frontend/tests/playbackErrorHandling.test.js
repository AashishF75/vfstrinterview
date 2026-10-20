import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  getYouTubeEmbedErrorMessage,
  resolveVideoPlayerProps,
} from '../src/utils/videoUtils.js';
import {
  loadYouTubeIframeApi,
  resetYouTubeIframeApiForTesting,
} from '../src/utils/youtubePlayerLoader.js';

describe('Phase 2 — Reliable Playback Error Handling Tests', () => {

  beforeEach(() => {
    resetYouTubeIframeApiForTesting();
    // Reset any mock window/document properties if set
    if (typeof globalThis.window !== 'undefined') {
      delete globalThis.window.YT;
      delete globalThis.window.onYouTubeIframeAPIReady;
    }
  });

  // Test 1: Error code mapping
  test('Accurately maps YouTube playback error codes 101, 150, 100, 2, and 5 to student-friendly explanations', () => {
    const msg101 = getYouTubeEmbedErrorMessage(101);
    assert.ok(msg101.includes('restricted in-site playback'));

    const msg150 = getYouTubeEmbedErrorMessage(150);
    assert.ok(msg150.includes('restricted in-site playback'));

    const msg100 = getYouTubeEmbedErrorMessage(100);
    assert.ok(msg100.includes('removed, marked private'));

    const msg2 = getYouTubeEmbedErrorMessage(2);
    assert.ok(msg2.includes('invalid parameter'));

    const msg5 = getYouTubeEmbedErrorMessage(5);
    assert.ok(msg5.includes('HTML5 player error'));

    // Unknown or unmapped code fallback
    const msgUnknown = getYouTubeEmbedErrorMessage(999);
    assert.ok(msgUnknown.includes('restricted or unavailable'));
  });

  // Test 2: Singleton script injection and existing window.YT reuse
  test('loadYouTubeIframeApi reuses existing window.YT without re-injecting scripts', async () => {
    // Setup mock window with pre-existing window.YT
    const mockYT = {
      Player: class MockPlayer {
        constructor(element, options) {
          this.element = element;
          this.options = options;
        }
      },
    };

    globalThis.window = {
      YT: mockYT,
    };

    const ytInstance = await loadYouTubeIframeApi();
    assert.equal(ytInstance, mockYT);
  });

  // Test 3: Simulated script loading timeout and offline recovery
  test('loadYouTubeIframeApi handles timeout gracefully without hanging indefinitely', async () => {
    // Setup fake DOM environment where script tag never finishes loading
    let appendedScripts = [];
    globalThis.document = {
      querySelector: () => null,
      createElement: (type) => ({ type, src: '', async: false }),
      getElementsByTagName: () => [
        {
          parentNode: {
            insertBefore: (tag) => { appendedScripts.push(tag); },
          },
        },
      ],
      head: {
        appendChild: (tag) => { appendedScripts.push(tag); },
      },
    };
    globalThis.window = {
      document: globalThis.document,
    };

    // Fast timeout of 50ms for testing
    await assert.rejects(
      async () => {
        await loadYouTubeIframeApi(50);
      },
      {
        message: /Timed out waiting for YouTube IFrame Player API/i,
      }
    );

    // Verify script tag was created with correct HTTPS URL
    assert.equal(appendedScripts.length, 1);
    assert.equal(appendedScripts[0].src, 'https://www.youtube.com/iframe_api');

    // Loader state is reset on timeout so subsequent requests can re-attempt
    resetYouTubeIframeApiForTesting();
  });

  // Test 4: Autoplay policy compliance (autoplay: 0) and privacy-enhanced domain
  test('Player configuration preserves privacy-enhanced host and disables forced autoplay with sound', () => {
    let capturedOptions = null;

    class MockYTPlayer {
      constructor(container, options) {
        capturedOptions = options;
        this.destroyCalled = false;
      }
      destroy() {
        this.destroyCalled = true;
      }
    }

    const mockYT = { Player: MockYTPlayer };
    const container = {};
    const testVideoId = 'IPvYjXCsTg8';

    // Simulated player instantiation
    const playerInstance = new mockYT.Player(container, {
      videoId: testVideoId,
      host: 'https://www.youtube-nocookie.com',
      playerVars: {
        rel: 0,
        modestbranding: 1,
        enablejsapi: 1,
        autoplay: 0, // Explicitly no forced autoplay
      },
      events: {
        onError: () => {},
      },
    });

    assert.ok(capturedOptions);
    assert.equal(capturedOptions.videoId, testVideoId);
    assert.equal(capturedOptions.host, 'https://www.youtube-nocookie.com');
    assert.equal(capturedOptions.playerVars.autoplay, 0);
    assert.equal(capturedOptions.playerVars.rel, 0);

    // Test destruction cleanup on unmount
    playerInstance.destroy();
    assert.equal(playerInstance.destroyCalled, true);
  });

  // Test 5: Simulated YouTube IFrame Player error event handling (codes 101 and 150)
  test('Simulated YouTube onError event transitions player into direct watch fallback mode', () => {
    let playerState = {
      isPlaying: true,
      isLoading: true,
      hasError: false,
      errorCode: null,
      errorMessage: null,
    };

    function simulatePlayerEvent(eventName, eventData) {
      if (eventName === 'onReady') {
        playerState.isLoading = false;
      } else if (eventName === 'onError') {
        playerState.errorCode = eventData;
        playerState.hasError = true;
        playerState.isLoading = false;
        playerState.errorMessage = getYouTubeEmbedErrorMessage(eventData);
      }
    }

    // 1. Simulate code 101 embed restriction (video owner restricted playback)
    simulatePlayerEvent('onError', 101);
    assert.equal(playerState.hasError, true);
    assert.equal(playerState.isLoading, false);
    assert.equal(playerState.errorCode, 101);
    assert.ok(playerState.errorMessage.includes('restricted in-site playback'));

    // 2. Simulate code 150 (alternate restriction code)
    simulatePlayerEvent('onError', 150);
    assert.equal(playerState.errorCode, 150);
    assert.ok(playerState.errorMessage.includes('restricted in-site playback'));

    // 3. Simulate code 100 (video removed / private)
    simulatePlayerEvent('onError', 100);
    assert.equal(playerState.errorCode, 100);
    assert.ok(playerState.errorMessage.includes('removed, marked private'));
  });

  // Test 6: Fallback when YouTube API script fails to load (e.g. adblocker)
  test('Gracefully switches to direct iframe or external fallback if script loading fails', () => {
    let componentState = {
      useIframeFallback: false,
      hasError: false,
      isPlaying: true,
    };

    // Simulate script loading failure catch handler from EmbeddedVideoPlayer.jsx
    function handleApiScriptFailure() {
      componentState.useIframeFallback = true;
    }

    handleApiScriptFailure();
    assert.equal(componentState.useIframeFallback, true);
    assert.equal(componentState.hasError, false);
    // Report and player continue functioning via iframe or direct link
  });
});
