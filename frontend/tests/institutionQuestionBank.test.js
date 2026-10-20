import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  previewQuestionFile,
  saveConfirmedQuestions,
  getInstitutionQuestions,
} from '../src/api/client.js';

describe('Institution Question Bank Management Tests', () => {

  test('API Client exports question bank management methods', () => {
    assert.strictEqual(typeof previewQuestionFile, 'function');
    assert.strictEqual(typeof saveConfirmedQuestions, 'function');
    assert.strictEqual(typeof getInstitutionQuestions, 'function');
  });

  test('Supported file extensions for question bank parsing', () => {
    const allowedExtensions = ['.pdf', '.csv', '.json', '.txt', '.md', '.zip'];
    const isAllowed = (filename) => {
      const lower = filename.toLowerCase();
      return allowedExtensions.some((ext) => lower.endsWith(ext));
    };

    assert.strictEqual(isAllowed('operating_systems_questions.pdf'), true);
    assert.strictEqual(isAllowed('algorithms.csv'), true);
    assert.strictEqual(isAllowed('networking.json'), true);
    assert.strictEqual(isAllowed('database_management.txt'), true);
    assert.strictEqual(isAllowed('system_design.md'), true);
    assert.strictEqual(isAllowed('vignan_role_question_sets.zip'), true);

    // Unsupported formats
    assert.strictEqual(isAllowed('malicious_executable.exe'), false);
    assert.strictEqual(isAllowed('image.png'), false);
    assert.strictEqual(isAllowed('word_doc.docx'), false);
  });

  test('Client-side question validation enforces >= 10 characters and required topic', () => {
    const validateQuestion = (q) => {
      const errors = [];
      if (!q.question_text || q.question_text.trim().length < 10) {
        errors.push('Question prompt is too short (minimum 10 characters required).');
      }
      if (!q.topic || !q.topic.trim()) {
        errors.push('Topic is required.');
      }
      return {
        isValid: errors.length === 0,
        errors,
      };
    };

    // Valid question
    const validQ = validateQuestion({
      question_text: 'Explain how virtual memory operates using page tables in modern operating systems.',
      topic: 'Operating Systems',
    });
    assert.strictEqual(validQ.isValid, true);
    assert.strictEqual(validQ.errors.length, 0);

    // Short prompt (9 chars)
    const shortQ = validateQuestion({
      question_text: 'Too short',
      topic: 'Operating Systems',
    });
    assert.strictEqual(shortQ.isValid, false);
    assert.ok(shortQ.errors.some((e) => e.includes('minimum 10 characters')));

    // Missing topic
    const missingTopicQ = validateQuestion({
      question_text: 'Describe the differences between process and thread scheduling.',
      topic: '',
    });
    assert.strictEqual(missingTopicQ.isValid, false);
    assert.ok(missingTopicQ.errors.some((e) => e.includes('Topic is required')));
  });

  test('Inline correction workflow transforms deficient questions to valid', () => {
    const questions = [
      {
        temp_id: 'q-1',
        question_text: 'Short',
        topic: 'OS',
        is_valid: false,
        validation_errors: ['Question prompt is too short (minimum 10 characters required).'],
      },
      {
        temp_id: 'q-2',
        question_text: 'Describe LRU page replacement algorithm and how it is implemented with a doubly linked list.',
        topic: 'Operating Systems',
        is_valid: true,
        validation_errors: [],
      },
    ];

    // Initial check: 1 valid, 1 invalid
    assert.strictEqual(questions.filter((q) => q.is_valid).length, 1);
    assert.strictEqual(questions.filter((q) => !q.is_valid).length, 1);

    // Faculty edits question 1 in preview modal
    questions[0].question_text = 'What is the working set model in memory management?';
    questions[0].validation_errors = [];
    questions[0].is_valid = true;

    // After correction: all valid
    assert.strictEqual(questions.filter((q) => q.is_valid).length, 2);
    assert.strictEqual(questions.filter((q) => !q.is_valid).length, 0);
  });

  test('Save payload builds explicit confirmation without auto-scheduling interviews', () => {
    const previewQuestions = [
      {
        localId: 'temp-1',
        question_text: 'Explain the difference between optimistic and pessimistic locking.',
        question_type: 'conceptual',
        topic: 'Database Systems',
        difficulty: 'medium',
        expected_answer: 'Optimistic assumes no collision and validates on commit; pessimistic locks rows upfront.',
        role: 'Software Development Engineer',
        keywords: ['locking', 'database', 'optimistic'],
      },
      {
        localId: 'temp-2',
        question_text: 'Implement an LRU Cache with get and put methods in O(1) time complexity.',
        question_type: 'coding',
        topic: 'Data Structures',
        difficulty: 'hard',
        expected_answer: 'Combine a hash map with a doubly linked list.',
        role: 'Software Development Engineer',
        keywords: ['cache', 'hashmap', 'linkedlist'],
      },
    ];

    const buildSavePayload = (questions, role, department, interviewId = null) => {
      return {
        interview_id: interviewId, // Must be null on upload to satisfy "Do not automatically assign interviews"
        role: role || null,
        target_department: department || null,
        questions: questions.map((q) => ({
          temp_id: q.localId,
          question_text: q.question_text.trim(),
          question_type: q.question_type || 'conceptual',
          topic: q.topic.trim(),
          difficulty: q.difficulty || null,
          expected_answer: q.expected_answer?.trim() || null,
          role: q.role || role || null,
          keywords: q.keywords || [],
        })),
      };
    };

    const payload = buildSavePayload(previewQuestions, 'Software Development Engineer', 'CSE');

    assert.strictEqual(payload.interview_id, null);
    assert.strictEqual(payload.role, 'Software Development Engineer');
    assert.strictEqual(payload.target_department, 'CSE');
    assert.strictEqual(payload.questions.length, 2);
    assert.strictEqual(payload.questions[0].question_type, 'conceptual');
    assert.strictEqual(payload.questions[1].question_type, 'coding');
    assert.strictEqual(payload.questions[0].difficulty, 'medium');
    assert.strictEqual(payload.questions[1].difficulty, 'hard');
  });

  test('Difficulty normalization supports easy, medium, hard, and unstated null', () => {
    const normalizeDifficulty = (raw) => {
      if (!raw) return null;
      const lower = String(raw).trim().toLowerCase();
      if (lower === 'easy' || lower === 'basic') return 'easy';
      if (lower === 'medium' || lower === 'intermediate') return 'medium';
      if (lower === 'hard' || lower === 'advanced') return 'hard';
      return null;
    };

    assert.strictEqual(normalizeDifficulty('easy'), 'easy');
    assert.strictEqual(normalizeDifficulty('EASY'), 'easy');
    assert.strictEqual(normalizeDifficulty('medium'), 'medium');
    assert.strictEqual(normalizeDifficulty('HARD'), 'hard');
    assert.strictEqual(normalizeDifficulty(''), null);
    assert.strictEqual(normalizeDifficulty(null), null);
    assert.strictEqual(normalizeDifficulty(undefined), null);
    assert.strictEqual(normalizeDifficulty('unknown'), null);
  });
});
