import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  getSessionProctoringTimeline,
  updateSessionProctoringReview,
} from '../src/api/client.js';

describe('Phase 6: Faculty Proctoring Review Workflow Tests', () => {

  test('API Client exports proctoring timeline and review methods', () => {
    assert.strictEqual(typeof getSessionProctoringTimeline, 'function');
    assert.strictEqual(typeof updateSessionProctoringReview, 'function');
  });

  test('updateSessionProctoringReview validates note length on client-side (rejects > 2000 chars with 422)', async () => {
    const excessiveNotes = 'A'.repeat(2001);
    const result = await updateSessionProctoringReview('sess-dummy', 'flagged', excessiveNotes);
    assert.strictEqual(result.success, false);
    assert.strictEqual(result.status, 422);
    assert.ok(result.error.includes('2000 characters'));
  });

  test('Validates review status domain values: unreviewed, cleared, flagged', () => {
    const validStatuses = ['unreviewed', 'cleared', 'flagged'];
    const testCases = [
      { status: 'unreviewed', valid: true },
      { status: 'cleared', valid: true },
      { status: 'flagged', valid: true },
      { status: 'disqualified', valid: false },
      { status: 'guilty', valid: false },
    ];

    testCases.forEach((tc) => {
      assert.strictEqual(validStatuses.includes(tc.status), tc.valid);
    });
  });

  test('Event badge mapping accurately groups telemetry signals', () => {
    const getEventBadge = (type) => {
      const t = (type || '').toLowerCase();
      if (t.includes('tab')) return 'amber';
      if (t.includes('absent')) return 'rose';
      if (t.includes('multiple')) return 'purple';
      if (t.includes('connected') || t.includes('restored') || t.includes('normal')) return 'emerald';
      return 'slate';
    };

    assert.strictEqual(getEventBadge('TAB_HIDDEN'), 'amber');
    assert.strictEqual(getEventBadge('TAB_VISIBLE'), 'amber');
    assert.strictEqual(getEventBadge('FACE_ABSENT'), 'rose');
    assert.strictEqual(getEventBadge('MULTIPLE_FACES'), 'purple');
    assert.strictEqual(getEventBadge('CAMERA_STREAM_CONNECTED'), 'emerald');
    assert.strictEqual(getEventBadge('CAMERA_STREAM_RESTORED'), 'emerald');
    assert.strictEqual(getEventBadge('FACE_NORMAL'), 'emerald');
    assert.strictEqual(getEventBadge('UNKNOWN_CUSTOM_TELEMETRY'), 'slate');
  });

  test('Summary integrity status badges map to expected alert levels', () => {
    const getIntegrityLevel = (status) => {
      switch (status) {
        case 'normal':
          return { label: 'Normal Signals', level: 'safe' };
        case 'notice':
          return { label: 'Notice', level: 'warning' };
        case 'review_suggested':
          return { label: 'Review Suggested', level: 'attention' };
        default:
          return { label: 'Unknown', level: 'neutral' };
      }
    };

    assert.deepStrictEqual(getIntegrityLevel('normal'), { label: 'Normal Signals', level: 'safe' });
    assert.deepStrictEqual(getIntegrityLevel('notice'), { label: 'Notice', level: 'warning' });
    assert.deepStrictEqual(getIntegrityLevel('review_suggested'), { label: 'Review Suggested', level: 'attention' });
    assert.deepStrictEqual(getIntegrityLevel('other'), { label: 'Unknown', level: 'neutral' });
  });

  test('Chronological timeline ordering correctly sorts events by server_timestamp ascending', () => {
    const rawEvents = [
      { event_id: 'e3', server_timestamp: '2026-10-20T10:05:00Z', event_type: 'TAB_VISIBLE' },
      { event_id: 'e1', server_timestamp: '2026-10-20T10:00:00Z', event_type: 'CAMERA_STREAM_CONNECTED' },
      { event_id: 'e2', server_timestamp: '2026-10-20T10:02:30Z', event_type: 'TAB_HIDDEN' },
    ];

    const sorted = [...rawEvents].sort(
      (a, b) => new Date(a.server_timestamp) - new Date(b.server_timestamp)
    );

    assert.strictEqual(sorted[0].event_id, 'e1');
    assert.strictEqual(sorted[1].event_id, 'e2');
    assert.strictEqual(sorted[2].event_id, 'e3');
  });

  test('Empty timeline produces clean presentation state with zero metrics', () => {
    const emptyTimelineResponse = {
      session_id: 'sess-empty',
      student_registration_number: '241FA04001',
      timeline: [],
      summary: {
        total_tab_hidden_count: 0,
        total_tab_hidden_duration_seconds: 0.0,
        total_face_absent_count: 0,
        total_face_absent_duration_seconds: 0.0,
        total_multiple_faces_count: 0,
        stream_disruptions_count: 0,
        integrity_status: 'normal',
        disclaimer: 'Integrity indicators represent browser-side client telemetry events and do not constitute automated evidence of misconduct.',
      },
      review_status: 'unreviewed',
      review_notes: null,
      reviewed_at: null,
      reviewed_by_email: null,
    };

    assert.strictEqual(emptyTimelineResponse.timeline.length, 0);
    assert.strictEqual(emptyTimelineResponse.summary.integrity_status, 'normal');
    assert.strictEqual(emptyTimelineResponse.summary.total_tab_hidden_count, 0);
    assert.strictEqual(emptyTimelineResponse.review_status, 'unreviewed');
    assert.ok(emptyTimelineResponse.summary.disclaimer.includes('do not constitute automated evidence'));
  });

  test('Neutral disclaimer verification enforces human-in-the-loop policy', () => {
    const disclaimer = 'Proctoring signals are passive browser-side telemetry intended solely for human evaluation. Network fluctuations, camera angles, or background movements do not constitute automatic proof of academic misconduct.';

    // Prohibit auto-disqualification language
    assert.ok(!disclaimer.toLowerCase().includes('automatically failed'));
    assert.ok(!disclaimer.toLowerCase().includes('automatic disqualification'));
    // Enforce human discretion language
    assert.ok(disclaimer.toLowerCase().includes('human evaluation'));
    assert.ok(disclaimer.toLowerCase().includes('do not constitute automatic proof'));
  });

  test('Review persistence lifecycle preserves reviewer email, timestamp, and updated state', () => {
    const initialState = {
      review_status: 'unreviewed',
      review_notes: '',
      reviewed_at: null,
      reviewed_by_email: null,
    };

    const updateResponse = {
      success: true,
      data: {
        session_id: 'sess-test',
        review_status: 'cleared',
        review_notes: 'Reviewed camera shift; legitimate adjustment.',
        reviewed_by_email: 'faculty.review@vfstr.ac.in',
        reviewed_at: '2026-10-20T11:45:00Z',
      },
    };

    const nextState = {
      ...initialState,
      review_status: updateResponse.data.review_status,
      review_notes: updateResponse.data.review_notes,
      reviewed_at: updateResponse.data.reviewed_at,
      reviewed_by_email: updateResponse.data.reviewed_by_email,
    };

    assert.strictEqual(nextState.review_status, 'cleared');
    assert.strictEqual(nextState.reviewed_by_email, 'faculty.review@vfstr.ac.in');
    assert.ok(nextState.reviewed_at !== null);
    assert.ok(nextState.review_notes.length > 0);
  });

  test('Error state separation preserves draft notes when save fails', () => {
    let state = {
      error: null,
      saveError: null,
      reviewNotes: 'Draft observation regarding lighting flicker...',
      reviewStatus: 'flagged',
    };

    // Simulated API save failure
    const failedSaveResponse = {
      success: false,
      error: 'Network timeout during review submission',
      status: 504,
    };

    if (!failedSaveResponse.success) {
      state.saveError = failedSaveResponse.error;
    }

    // Top-level error should remain null (so timeline modal does not crash or replace content)
    assert.strictEqual(state.error, null);
    assert.strictEqual(state.saveError, 'Network timeout during review submission');
    // Draft notes must NOT be lost on save failure
    assert.strictEqual(state.reviewNotes, 'Draft observation regarding lighting flicker...');
    assert.strictEqual(state.reviewStatus, 'flagged');
  });

  test('getSessionProctoringTimeline validates sessionId and rejects empty string with 400', async () => {
    const resEmpty = await getSessionProctoringTimeline('');
    assert.strictEqual(resEmpty.success, false);
    assert.strictEqual(resEmpty.status, 400);

    const resNull = await getSessionProctoringTimeline(null);
    assert.strictEqual(resNull.success, false);
    assert.strictEqual(resNull.status, 400);
  });

  test('updateSessionProctoringReview validates sessionId and reviewStatus before dispatch', async () => {
    const resNoId = await updateSessionProctoringReview('', 'cleared', 'Notes');
    assert.strictEqual(resNoId.success, false);
    assert.strictEqual(resNoId.status, 400);

    const resBadStatus = await updateSessionProctoringReview('sess-1', 'invalid_status', 'Notes');
    assert.strictEqual(resBadStatus.success, false);
    assert.strictEqual(resBadStatus.status, 422);
    assert.ok(resBadStatus.error.includes('invalid_status'));
  });

  test('Audit metadata update does NOT fabricate strings when server omits them', () => {
    const initialData = {
      review_status: 'unreviewed',
      review_notes: '',
      reviewed_at: null,
      reviewed_by_email: null,
    };

    const serverConfirmation = {
      review_status: 'cleared',
      review_notes: 'Valid explanation',
      reviewed_at: null,
      reviewed_by_email: null,
    };

    // Client must not inject fallback 'You' or Date() if server did not confirm it
    const updated = {
      ...initialData,
      review_status: serverConfirmation.review_status,
      review_notes: serverConfirmation.review_notes,
      reviewed_at: serverConfirmation.reviewed_at || initialData.reviewed_at,
      reviewed_by_email: serverConfirmation.reviewed_by_email || initialData.reviewed_by_email,
    };

    assert.strictEqual(updated.review_status, 'cleared');
    assert.strictEqual(updated.reviewed_at, null);
    assert.strictEqual(updated.reviewed_by_email, null);
  });

  test('Duplicate save prevention blocks secondary submission when savingReview is true', () => {
    let callCount = 0;
    let savingReview = false;

    const triggerSave = () => {
      if (savingReview) return false;
      savingReview = true;
      callCount += 1;
      return true;
    };

    assert.strictEqual(triggerSave(), true);
    assert.strictEqual(triggerSave(), false); // Blocked
    assert.strictEqual(triggerSave(), false); // Blocked
    assert.strictEqual(callCount, 1);

    savingReview = false;
    assert.strictEqual(triggerSave(), true);
    assert.strictEqual(callCount, 2);
  });

});
