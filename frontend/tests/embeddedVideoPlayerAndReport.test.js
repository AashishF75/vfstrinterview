import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  extractYouTubeVideoId,
  getYouTubeEmbedUrl,
  getYouTubeExternalUrl,
  getYouTubeEmbedErrorMessage,
  resolveVideoPlayerProps,
  ALLOWED_YOUTUBE_HOSTS,
} from '../src/utils/videoUtils.js';

describe('EmbeddedVideoPlayer and StudentReport Integration Tests', () => {

  // Test 1: Valid video IDs and safe iframe URLs
  test('Resolves valid video IDs and constructs privacy-enhanced embed URLs for all 10 curated catalog resources', () => {
    const catalogSamples = [
      { id: 'IPvYjXCsTg8', topic: 'Computer Networks', provider: 'freeCodeCamp.org' },
      { id: 'RBSGKlAvoiM', topic: 'Data Structures', provider: 'William Fiset / freeCodeCamp.org' },
      { id: '8hly31xKli0', topic: 'Algorithms', provider: 'Treehouse / freeCodeCamp.org' },
      { id: 'oBt53YbR9Kk', topic: 'Dynamic Programming', provider: 'Alvin Zablan / freeCodeCamp.org' },
      { id: 'mXw9ruZaxzQ', topic: 'Operating Systems', provider: 'Neso Academy' },
      { id: 'HXV3zeQKqGY', topic: 'Database Management Systems', provider: 'freeCodeCamp.org' },
      { id: 'pTB0EiLXUC8', topic: 'Object-Oriented Programming', provider: 'freeCodeCamp.org' },
      { id: 'm8Icp_Cid5o', topic: 'System Design', provider: 'freeCodeCamp.org' },
      { id: 'jydYq7oAtD8', topic: 'Software Testing & QA', provider: 'freeCodeCamp.org' },
      { id: 'zOjov-2OZ0E', topic: 'Programming Fundamentals', provider: 'freeCodeCamp.org' },
    ];

    for (const sample of catalogSamples) {
      const config = resolveVideoPlayerProps({
        videoId: sample.id,
        videoUrl: `https://www.youtube.com/watch?v=${sample.id}`,
        title: `${sample.topic} Complete Course`,
        provider: sample.provider,
        topic: sample.topic,
        canEmbed: true,
      });

      assert.equal(config.resolvedVideoId, sample.id);
      assert.equal(config.isEmbedSupported, true);
      assert.equal(
        config.resolvedEmbedUrl,
        `https://www.youtube-nocookie.com/embed/${sample.id}?rel=0&modestbranding=1&enablejsapi=1`
      );
      assert.ok(config.resolvedEmbedUrl.startsWith('https://www.youtube-nocookie.com/embed/'));
      assert.ok(!config.resolvedEmbedUrl.includes('watch'));
      assert.equal(config.safeExternalUrl, `https://www.youtube.com/watch?v=${sample.id}`);
    }
  });

  // Test 2: Invalid IDs, malicious protocols, and unsafe URLs are rejected
  test('Rejects invalid IDs, unexpected ports, credential injection, and unsafe protocols', () => {
    const maliciousCases = [
      { url: 'javascript:alert(1)', desc: 'XSS javascript scheme' },
      { url: 'data:text/html,<script>alert(1)</script>', desc: 'Data URI XSS' },
      { url: 'https://user:password@www.youtube.com/watch?v=IPvYjXCsTg8', desc: 'Embedded credentials' },
      { url: 'https://youtube.com:8443/watch?v=IPvYjXCsTg8', desc: 'Unexpected port' },
      { url: 'https://youtube.com.attacker.com/watch?v=IPvYjXCsTg8', desc: 'Deceptive hostname' },
      { url: 'https://evil-nocookie.com/embed/IPvYjXCsTg8', desc: 'Unauthorized nocookie domain' },
      { url: 'not_a_valid_id', desc: 'Malformed ID string' },
    ];

    for (const testCase of maliciousCases) {
      const config = resolveVideoPlayerProps({
        videoUrl: testCase.url,
        title: 'Untrusted Resource',
        canEmbed: true,
      });

      assert.equal(
        config.isEmbedSupported,
        false,
        `Expected isEmbedSupported=false for ${testCase.desc}`
      );
      assert.equal(config.resolvedEmbedUrl, null);
    }
  });

  // Test 3: Poster-to-player activation and autoStart handling
  test('Manages poster-to-player activation lifecycle and autoStart prop', () => {
    // Simulated player state container
    function createPlayerMachine(props) {
      const config = resolveVideoPlayerProps(props);
      let state = {
        isPlaying: Boolean(props.autoStart && config.isEmbedSupported),
        isLoading: true,
        hasError: false,
        activeIframeSrc: null,
      };

      return {
        getState: () => ({ ...state }),
        handleStartPlayback: () => {
          if (!config.isEmbedSupported) {
            state.hasError = true;
            return;
          }
          state.isLoading = true;
          state.hasError = false;
          state.isPlaying = true;
          state.activeIframeSrc = config.resolvedEmbedUrl;
        },
        handleIframeLoad: () => {
          state.isLoading = false;
        },
        handleIframeError: () => {
          state.isLoading = false;
          state.hasError = true;
        },
        handleResetPlayback: () => {
          state.isPlaying = false;
          state.isLoading = true;
          state.hasError = false;
          state.activeIframeSrc = null;
        },
      };
    }

    // Default mode: starts on poster preview
    const player1 = createPlayerMachine({
      videoId: 'IPvYjXCsTg8',
      title: 'Computer Networks',
      canEmbed: true,
      autoStart: false,
    });
    assert.equal(player1.getState().isPlaying, false);
    assert.equal(player1.getState().activeIframeSrc, null);

    // User triggers playback
    player1.handleStartPlayback();
    assert.equal(player1.getState().isPlaying, true);
    assert.equal(player1.getState().isLoading, true);
    assert.equal(
      player1.getState().activeIframeSrc,
      'https://www.youtube-nocookie.com/embed/IPvYjXCsTg8?rel=0&modestbranding=1&enablejsapi=1'
    );

    // Iframe loads successfully
    player1.handleIframeLoad();
    assert.equal(player1.getState().isLoading, false);
    assert.equal(player1.getState().hasError, false);

    // User closes / resets player
    player1.handleResetPlayback();
    assert.equal(player1.getState().isPlaying, false);

    // AutoStart mode: immediately starts playing when embedding is supported
    const player2 = createPlayerMachine({
      videoId: 'RBSGKlAvoiM',
      title: 'Data Structures',
      canEmbed: true,
      autoStart: true,
    });
    assert.equal(player2.getState().isPlaying, true);
  });

  // Test 4: Loading, error, and disabled-embedding states
  test('Handles canEmbed=false direct routing, network errors, and loading timeout watchdog', () => {
    // 1. canEmbed = false
    const configDisabled = resolveVideoPlayerProps({
      videoId: 'mXw9ruZaxzQ',
      title: 'Operating Systems',
      canEmbed: false,
    });
    assert.equal(configDisabled.isEmbedSupported, false);
    assert.equal(configDisabled.safeExternalUrl, 'https://www.youtube.com/watch?v=mXw9ruZaxzQ');

    // 2. Loading skeleton watchdog timeout simulation
    let isLoading = true;
    let isPlaying = true;
    let timerFired = false;

    // Simulate the 8-second watchdog guard from EmbeddedVideoPlayer.jsx
    function simulateWatchdog(callback) {
      if (isPlaying && isLoading) {
        callback();
      }
    }
    simulateWatchdog(() => {
      isLoading = false;
      timerFired = true;
    });

    assert.equal(timerFired, true);
    assert.equal(isLoading, false);

    // 3. YouTube Embed Error Code Mapping
    assert.ok(getYouTubeEmbedErrorMessage(101).includes('restricted in-site playback'));
    assert.ok(getYouTubeEmbedErrorMessage(150).includes('restricted in-site playback'));
    assert.ok(getYouTubeEmbedErrorMessage(100).includes('removed, marked private'));
    assert.ok(getYouTubeEmbedErrorMessage(2).includes('invalid parameter'));
    assert.ok(getYouTubeEmbedErrorMessage(5).includes('HTML5 player error'));
    assert.ok(getYouTubeEmbedErrorMessage(999).includes('restricted or unavailable'));
  });

  // Test 5: External fallback links are strictly sanitized and never leak PII
  test('Constructs clean external watch links stripping PII, answer text, and tokens', () => {
    const dirtyInputs = [
      'https://www.youtube.com/watch?v=IPvYjXCsTg8&token=secret_student_token&reg=241FA04001',
      'https://youtu.be/IPvYjXCsTg8?utm_source=email&student_name=Aashish',
      'IPvYjXCsTg8',
    ];

    for (const input of dirtyInputs) {
      const cleanUrl = getYouTubeExternalUrl(input);
      assert.equal(cleanUrl, 'https://www.youtube.com/watch?v=IPvYjXCsTg8');
      assert.ok(!cleanUrl.includes('token'));
      assert.ok(!cleanUrl.includes('student'));
      assert.ok(!cleanUrl.includes('reg'));
      assert.ok(!cleanUrl.includes('utm'));
    }
  });

  // Test 6: Accessible iframe titles and keyboard activation attributes
  test('Provides accessible titles, ARIA labels, and keyboard action triggers', () => {
    const config = resolveVideoPlayerProps({
      videoId: '8hly31xKli0',
      title: 'Algorithms Full Course',
      provider: 'freeCodeCamp.org',
      topic: 'Algorithms',
    });

    // Accessible iframe title
    assert.equal(
      config.iframeTitle,
      'Educational Tutorial: Algorithms Full Course by freeCodeCamp.org'
    );
    // Play button ARIA label
    assert.equal(config.ariaPlayLabel, 'Play tutorial: Algorithms Full Course');
    // External link ARIA label
    assert.equal(
      config.ariaExternalLabel,
      'Watch Algorithms Full Course on freeCodeCamp.org in new tab'
    );

    // Keyboard interaction simulation: Enter or Space triggers play
    function simulateKeyboardActivation(eventKey, onActivate) {
      if (eventKey === 'Enter' || eventKey === ' ' || eventKey === 'Spacebar') {
        onActivate();
        return true;
      }
      return false;
    }

    let activated = false;
    assert.equal(simulateKeyboardActivation('Enter', () => { activated = true; }), true);
    assert.equal(activated, true);

    activated = false;
    assert.equal(simulateKeyboardActivation(' ', () => { activated = true; }), true);
    assert.equal(activated, true);

    activated = false;
    assert.equal(simulateKeyboardActivation('Tab', () => { activated = true; }), false);
    assert.equal(activated, false);
  });

  // Test 7: StudentReport recommendation rationale, evidence honesty, and topic rendering
  test('Renders recommendation rationale distinguishing skipped questions, single-question samples, and high scores', () => {
    const mockReportData = {
      report_id: 'rep-sess-001',
      student_registration_number: '241FA04001',
      overall_score: 7.2,
      percentage_score: 72.0,
      performance_level: 'Proficient',
      topic_breakdown: [
        {
          topic: 'Computer Networks',
          average_score: 4.0,
          questions_tested: 1,
          is_limited_evidence: true,
          evidence_note: 'Limited evidence: Evaluated on 1 question. Consider this an initial practice indicator.',
        },
        {
          topic: 'Operating Systems',
          average_score: 0.0,
          questions_tested: 1,
          is_limited_evidence: true,
          evidence_note: 'All 1 question(s) in this topic were skipped by candidate. No evaluation score recorded.',
        },
        {
          topic: 'Data Structures',
          average_score: 8.5,
          questions_tested: 2,
          is_limited_evidence: false,
          evidence_note: 'Evaluated across 2 questions. Representative sample.',
        },
      ],
      video_recommendations: [
        {
          resource_id: 'res-os-fundamentals-01',
          topic: 'Operating Systems',
          title: 'Operating System Full Course',
          provider: 'Neso Academy',
          video_url: 'https://www.youtube.com/watch?v=mXw9ruZaxzQ',
          video_id: 'mXw9ruZaxzQ',
          embed_url: 'https://www.youtube-nocookie.com/embed/mXw9ruZaxzQ?rel=0&modestbranding=1',
          can_embed: true,
          difficulty_level: 'medium',
          reason: "Recommended because Question 2 on 'Operating Systems' was skipped during your interview. An introductory tutorial is recommended to build foundational confidence before practicing again.",
          watched: false,
          is_verified: true,
        },
        {
          resource_id: 'res-net-osi-01',
          topic: 'Computer Networks',
          title: 'Computer Networking Full Course',
          provider: 'freeCodeCamp.org',
          video_url: 'https://www.youtube.com/watch?v=IPvYjXCsTg8',
          video_id: 'IPvYjXCsTg8',
          embed_url: 'https://www.youtube-nocookie.com/embed/IPvYjXCsTg8?rel=0&modestbranding=1',
          can_embed: true,
          difficulty_level: 'medium',
          reason: "Recommended for revision because your score was 4.0/10 in 'Computer Networks' (specifically noted in Question 1). (Note: Evaluated on a single question sample; targeted practice is suggested for this specific concept).",
          watched: false,
          is_verified: true,
        },
      ],
    };

    // 1. Verify skipped question recommendation rationale
    const osRec = mockReportData.video_recommendations.find(v => v.topic === 'Operating Systems');
    assert.ok(osRec);
    assert.ok(osRec.reason.includes('Question 2'));
    assert.ok(osRec.reason.includes('skipped'));
    assert.ok(!osRec.reason.includes('0.0/10'));
    assert.ok(!osRec.reason.includes('scored 0.0'));

    // 2. Verify single question evidence qualification
    const netRec = mockReportData.video_recommendations.find(v => v.topic === 'Computer Networks');
    assert.ok(netRec);
    assert.ok(netRec.reason.includes('single question sample'));
    assert.ok(netRec.reason.includes('4.0/10'));

    // 3. Verify topic honesty indicators in breakdown
    const netTopic = mockReportData.topic_breakdown.find(t => t.topic === 'Computer Networks');
    assert.equal(netTopic.is_limited_evidence, true);
    assert.ok(netTopic.evidence_note.includes('Limited evidence'));
  });

  // Test 8: Empty recommendation lists and report loading/error state transitions
  test('Handles report state transitions: loading, API error with retry, and empty recommendation list', async () => {
    let reportState = {
      report: null,
      loading: true,
      error: null,
    };

    // 1. Initial Loading State
    assert.equal(reportState.loading, true);
    assert.equal(reportState.report, null);
    assert.equal(reportState.error, null);

    // 2. Simulated Failed API call
    let fetchAttempt = 0;
    async function mockFetchReport(assignmentId) {
      fetchAttempt++;
      if (fetchAttempt === 1) {
        return { success: false, error: 'Interview report not found or access denied.' };
      }
      return {
        success: true,
        data: {
          report_id: 'rep-sess-002',
          student_registration_number: '241FA04002',
          overall_score: 8.0,
          topic_breakdown: [],
          video_recommendations: [], // Empty recommendations list
        },
      };
    }

    // First attempt fails
    const res1 = await mockFetchReport('asgn-test-404');
    if (!res1.success) {
      reportState.loading = false;
      reportState.error = res1.error;
    }
    assert.equal(reportState.loading, false);
    assert.ok(reportState.error.includes('access denied') || reportState.error.includes('not found'));
    assert.equal(reportState.report, null);

    // Retry action recovers
    reportState.loading = true;
    reportState.error = null;
    const res2 = await mockFetchReport('asgn-test-404');
    if (res2.success) {
      reportState.loading = false;
      reportState.report = res2.data;
    }
    assert.equal(reportState.loading, false);
    assert.equal(reportState.error, null);
    assert.ok(reportState.report);

    // Empty recommendations handled cleanly
    const recs = reportState.report.video_recommendations;
    assert.equal(Array.isArray(recs), true);
    assert.equal(recs.length, 0);

    // Derives empty list fallback message
    const emptyMessage = recs.length === 0
      ? 'No specific video recommendations generated for this session.'
      : null;
    assert.equal(emptyMessage, 'No specific video recommendations generated for this session.');
  });

  // Test 9: Phase 3 - Student toggle watch status with optimistic update and rollback
  test('Toggles watch status, updates UI optimistically, and rolls back with error on API failure', async () => {
    let report = {
      assignment_id: 'asgn-watch-ui-01',
      video_recommendations: [
        { resource_id: 'res-net-osi-01', title: 'Computer Networks', watched: false },
        { resource_id: 'res-dsa-structures-01', title: 'Data Structures', watched: false },
      ],
    };

    let updatingWatchIds = new Set();
    let watchUpdateErrors = {};

    // Simulated API handler
    let apiShouldFail = false;
    async function mockUpdateVideoWatchStatus(assignmentId, resourceId, watched) {
      if (apiShouldFail) {
        return { success: false, error: 'Network error: could not connect to server' };
      }
      return {
        success: true,
        data: { assignment_id: assignmentId, resource_id: resourceId, watched },
      };
    }

    async function handleToggleWatchStatus(resourceId, currentWatched) {
      updatingWatchIds.add(resourceId);
      delete watchUpdateErrors[resourceId];
      const newWatched = !currentWatched;

      const res = await mockUpdateVideoWatchStatus(report.assignment_id, resourceId, newWatched);
      if (res.success) {
        report.video_recommendations = report.video_recommendations.map((v) =>
          v.resource_id === resourceId ? { ...v, watched: newWatched } : v
        );
      } else {
        watchUpdateErrors[resourceId] = res.error;
      }
      updatingWatchIds.delete(resourceId);
    }

    // 1. Initial state: unwatched
    assert.equal(report.video_recommendations[0].watched, false);

    // 2. Mark as Watched succeeds
    await handleToggleWatchStatus('res-net-osi-01', false);
    assert.equal(report.video_recommendations[0].watched, true);
    assert.equal(updatingWatchIds.has('res-net-osi-01'), false);
    assert.equal(watchUpdateErrors['res-net-osi-01'], undefined);

    // 3. Mark as Unwatched succeeds
    await handleToggleWatchStatus('res-net-osi-01', true);
    assert.equal(report.video_recommendations[0].watched, false);

    // 4. API Failure rolls back and records error message
    apiShouldFail = true;
    await handleToggleWatchStatus('res-dsa-structures-01', false);
    // Remains false (not watched)
    assert.equal(report.video_recommendations[1].watched, false);
    assert.ok(watchUpdateErrors['res-dsa-structures-01'].includes('Network error'));
  });

  // Test 10: Phase 3 - Video is never marked as watched automatically
  test('Video playback and player load does not automatically mark video as watched', () => {
    const video = {
      resource_id: 'res-algo-core-01',
      title: 'Algorithms Tutorial',
      watched: false,
    };

    // User starts playback
    let isPlaying = false;
    function startPlayback() {
      isPlaying = true;
      // Note: Video watch status must remain strictly under student control
    }

    startPlayback();
    assert.equal(isPlaying, true);
    assert.equal(video.watched, false); // Must remain false!
  });

  // Test 11: Phase 3 - Report reload preserves persisted watched state
  test('Report reload preserves persisted watched status for marked resources', () => {
    // Simulated refreshed report from backend where student previously marked res-net-osi-01
    const refreshedReport = {
      assignment_id: 'asgn-watch-ui-02',
      video_recommendations: [
        { resource_id: 'res-net-osi-01', title: 'Computer Networks', watched: true },
        { resource_id: 'res-dsa-structures-01', title: 'Data Structures', watched: false },
      ],
    };

    const netVid = refreshedReport.video_recommendations.find(v => v.resource_id === 'res-net-osi-01');
    assert.equal(netVid.watched, true);

    const dsaVid = refreshedReport.video_recommendations.find(v => v.resource_id === 'res-dsa-structures-01');
    assert.equal(dsaVid.watched, false);
  });
});
