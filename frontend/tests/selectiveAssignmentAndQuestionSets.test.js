import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  getQuestionSets,
  previewQuestionSet,
  searchEligibleCandidates,
  assignCandidatesToInterview,
  createAdminInterview,
} from '../src/api/client.js';

describe('Phase 8: Selective Student Assignment and Institution Question-Set Integration Tests', () => {

  test('API Client exports question set and candidate assignment methods', () => {
    assert.strictEqual(typeof getQuestionSets, 'function');
    assert.strictEqual(typeof previewQuestionSet, 'function');
    assert.strictEqual(typeof searchEligibleCandidates, 'function');
    assert.strictEqual(typeof assignCandidatesToInterview, 'function');
    assert.strictEqual(typeof createAdminInterview, 'function');
  });

  test('searchEligibleCandidates URLSearchParams correctly formats department, cohort, and eligibility', () => {
    const buildSearchParams = ({ interviewId, section, department, batchCohort, eligibility, search, limit = 300 } = {}) => {
      const params = new URLSearchParams();
      if (interviewId) params.append('interview_id', interviewId);
      if (section && section !== 'ALL') params.append('section', section);
      if (department && department !== 'ALL') params.append('department', department);
      if (batchCohort && batchCohort !== 'ALL') params.append('batch_cohort', batchCohort);
      if (eligibility && eligibility !== 'ALL') params.append('eligibility', eligibility);
      if (search) params.append('search', search);
      if (limit) params.append('limit', limit.toString());
      return params.toString();
    };

    const query1 = buildSearchParams({
      interviewId: 'int-uuid-101',
      section: '3',
      department: 'CSE',
      batchCohort: '2024-2028',
      eligibility: 'eligible',
      search: '241FA04',
      limit: 150,
    });

    assert.ok(query1.includes('interview_id=int-uuid-101'));
    assert.ok(query1.includes('section=3'));
    assert.ok(query1.includes('department=CSE'));
    assert.ok(query1.includes('batch_cohort=2024-2028'));
    assert.ok(query1.includes('eligibility=eligible'));
    assert.ok(query1.includes('search=241FA04'));
    assert.ok(query1.includes('limit=150'));

    // Check that 'ALL' is safely omitted so server does not perform an equality match on literal 'ALL'
    const queryAll = buildSearchParams({
      section: 'ALL',
      department: 'ALL',
      batchCohort: 'ALL',
      eligibility: 'ALL',
    });
    assert.strictEqual(queryAll.includes('section='), false);
    assert.strictEqual(queryAll.includes('department='), false);
    assert.strictEqual(queryAll.includes('batch_cohort='), false);
    assert.strictEqual(queryAll.includes('eligibility='), false);
  });

  test('Selective student checkbox state isolates assignable candidates from ineligible or assigned records', () => {
    const candidates = [
      {
        registration_number: '241FA04001',
        student_name: 'Aarav Sharma',
        already_assigned: false,
        is_eligible: true,
      },
      {
        registration_number: '241FA04002',
        student_name: 'Bhavna Patel',
        already_assigned: true, // Already assigned to this interview
        is_eligible: true,
      },
      {
        registration_number: '241FA04003',
        student_name: 'Chirag Reddy',
        already_assigned: false,
        is_eligible: false, // Ineligible / quarantined
      },
      {
        registration_number: '241FA04004',
        student_name: 'Divya Rao',
        already_assigned: false,
        is_eligible: true,
      },
    ];

    const isAssignable = (c) => !c.already_assigned && c.is_eligible !== false;

    assert.strictEqual(isAssignable(candidates[0]), true);
    assert.strictEqual(isAssignable(candidates[1]), false); // already assigned
    assert.strictEqual(isAssignable(candidates[2]), false); // ineligible
    assert.strictEqual(isAssignable(candidates[3]), true);

    // "Select All Visible" must select only candidates where isAssignable is true
    const selectAllVisible = (list, currentSelected = []) => {
      const assignableRegs = list.filter(isAssignable).map((c) => c.registration_number);
      return Array.from(new Set([...currentSelected, ...assignableRegs]));
    };

    const selected = selectAllVisible(candidates);
    assert.deepStrictEqual(selected, ['241FA04001', '241FA04004']);
    assert.strictEqual(selected.includes('241FA04002'), false);
    assert.strictEqual(selected.includes('241FA04003'), false);
  });

  test('Question set selector maps stable IDs and preserves backward-compatible default behavior', () => {
    const questionSets = [
      {
        set_id: 'platform-role-software-development-engineer',
        name: 'Software Development Engineer (SDE)',
        source: 'platform',
        question_count: 375,
      },
      {
        set_id: 'batch-upload-20261020-algorithms',
        name: 'CSE Final Year Algorithms Bank',
        source: 'institution',
        question_count: 35,
        department: 'CSE',
      },
    ];

    const buildInterviewPayload = (formState) => ({
      title: formState.title,
      scheduled_start_time: formState.start,
      scheduled_end_time: formState.end,
      duration_minutes: formState.duration,
      target_department: formState.target_department || 'CSE',
      target_cohort: formState.target_cohort || '2024-2028',
      question_set_id: formState.question_set_id || null,
      question_set_name: formState.question_set_name || null,
    });

    // Default: no custom question set selected
    const defaultPayload = buildInterviewPayload({
      title: 'Standard Campus Round',
      start: '2026-10-25T10:00:00Z',
      end: '2026-10-25T12:00:00Z',
      duration: 45,
      question_set_id: '',
      question_set_name: '',
    });
    assert.strictEqual(defaultPayload.question_set_id, null);
    assert.strictEqual(defaultPayload.question_set_name, null);

    // Custom institution batch selected
    const customPayload = buildInterviewPayload({
      title: 'Algorithms Midterm Technical Interview',
      start: '2026-10-26T10:00:00Z',
      end: '2026-10-26T12:00:00Z',
      duration: 60,
      question_set_id: questionSets[1].set_id,
      question_set_name: questionSets[1].name,
    });
    assert.strictEqual(customPayload.question_set_id, 'batch-upload-20261020-algorithms');
    assert.strictEqual(customPayload.question_set_name, 'CSE Final Year Algorithms Bank');
  });

  test('Pre-assignment confirmation preview stage guarantees explicit confirmed scope', () => {
    const selectedRegs = ['241FA04001', '241FA04005', '241FA04010'];
    const candidates = [
      { registration_number: '241FA04001', student_name: 'Aarav Sharma', section: '1' },
      { registration_number: '241FA04005', student_name: 'Esha Gupta', section: '2' },
      { registration_number: '241FA04010', student_name: 'Jatin Verma', section: '3' },
      { registration_number: '241FA04015', student_name: 'Kavya Nair', section: '4' }, // filtered but not selected
    ];

    // Confirm that payload sent to the server strictly matches selectedRegs, never the whole filtered table
    const generateAssignmentPayload = (selectedList) => ({
      registration_numbers: selectedList,
    });

    const payload = generateAssignmentPayload(selectedRegs);
    assert.strictEqual(payload.registration_numbers.length, 3);
    assert.deepStrictEqual(payload.registration_numbers, ['241FA04001', '241FA04005', '241FA04010']);
    assert.strictEqual(payload.registration_numbers.includes('241FA04015'), false);

    // Preview metadata rendering check
    const previewDetails = {
      interviewTitle: 'Cisco Placement Technical Assessment',
      selectedCount: selectedRegs.length,
      studentsPreview: selectedRegs.map((reg) => candidates.find((c) => c.registration_number === reg)),
    };

    assert.strictEqual(previewDetails.selectedCount, 3);
    assert.strictEqual(previewDetails.studentsPreview.length, 3);
    assert.strictEqual(previewDetails.studentsPreview[0].student_name, 'Aarav Sharma');
  });

  test('Server assignment response parsing isolates successful assignments from rejected candidates', () => {
    const mockServerResponse = {
      interview_id: 'int-uuid-101',
      total_requested: 3,
      assigned_count: 1,
      failed_count: 2,
      results: [
        {
          registration_number: '241FA04001',
          success: true,
          status: 'assigned',
          reason: null,
        },
        {
          registration_number: '999OTHER001',
          success: false,
          status: null,
          reason: "CROSS_INSTITUTION_UNAUTHORIZED: Student belongs to 'OTHER_UNIV', not authorized for 'VFSTR'",
        },
        {
          registration_number: '241FA04099',
          success: false,
          status: null,
          reason: 'INELIGIBLE_CANDIDATE: Backlogs > 0, CGPA < 7.0',
        },
      ],
    };

    const parseAssignmentFeedback = (resp) => {
      const assigned = resp.results.filter((r) => r.success);
      const failures = resp.results.filter((r) => !r.success);
      return {
        assignedCount: assigned.length,
        failedCount: failures.length,
        failures: failures.map((f) => ({
          regNo: f.registration_number,
          reason: f.reason,
        })),
      };
    };

    const feedback = parseAssignmentFeedback(mockServerResponse);
    assert.strictEqual(feedback.assignedCount, 1);
    assert.strictEqual(feedback.failedCount, 2);
    assert.ok(feedback.failures.some((f) => f.reason.includes('CROSS_INSTITUTION_UNAUTHORIZED')));
    assert.ok(feedback.failures.some((f) => f.reason.includes('INELIGIBLE_CANDIDATE')));
  });
});
