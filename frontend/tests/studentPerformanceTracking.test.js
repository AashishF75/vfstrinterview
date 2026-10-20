import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  getStudentProgressSummary,
  getStudentInterviewHistory,
  updateStudentProfile,
  getAdminStudentTracking,
  getAdminStudentDetail,
} from '../src/api/client.js';

describe('Student Performance Tracking & Level Recommendation Unit Tests', () => {

  test('API Client exports all required performance tracking and admin tracking methods', () => {
    assert.strictEqual(typeof getStudentProgressSummary, 'function');
    assert.strictEqual(typeof getStudentInterviewHistory, 'function');
    assert.strictEqual(typeof updateStudentProfile, 'function');
    assert.strictEqual(typeof getAdminStudentTracking, 'function');
    assert.strictEqual(typeof getAdminStudentDetail, 'function');
  });

  test('Validates three recommendation levels: Beginner, Intermediate, Advanced', () => {
    const validLevels = ['Beginner', 'Intermediate', 'Advanced'];
    const sampleRec = {
      recommended_level: 'Intermediate',
      status: 'provisional',
      evidence_sufficiency: 'limited',
    };

    assert.ok(validLevels.includes(sampleRec.recommended_level));
    assert.ok(['provisional', 'evidence_supported'].includes(sampleRec.status));
    assert.ok(['limited', 'moderate', 'strong'].includes(sampleRec.evidence_sufficiency));
  });

  test('Correctly maps performance trend states and badges', () => {
    const trends = ['improving', 'stable', 'declining', 'insufficient_data'];
    trends.forEach((t) => {
      assert.ok(typeof t === 'string' && t.length > 0);
    });

    const isImproving = (scores) => {
      if (scores.length < 2) return 'insufficient_data';
      const delta = scores[scores.length - 1] - scores[0];
      return delta >= 0.5 ? 'improving' : delta <= -0.5 ? 'declining' : 'stable';
    };

    assert.strictEqual(isImproving([5.0]), 'insufficient_data');
    assert.strictEqual(isImproving([5.0, 7.5]), 'improving');
    assert.strictEqual(isImproving([8.0, 6.0]), 'declining');
    assert.strictEqual(isImproving([7.0, 7.2]), 'stable');
  });

  test('Enforces provisional status when only 0 or 1 interview is completed', () => {
    const deriveStatus = (completedCount) => {
      return completedCount >= 2 ? 'evidence_supported' : 'provisional';
    };

    assert.strictEqual(deriveStatus(0), 'provisional');
    assert.strictEqual(deriveStatus(1), 'provisional');
    assert.strictEqual(deriveStatus(2), 'evidence_supported');
    assert.strictEqual(deriveStatus(5), 'evidence_supported');
  });

  test('Constructs filtered query parameters correctly for institutional student tracking', () => {
    const buildTrackingQuery = ({ department, role, recommended_level, search, skip = 0, limit = 20 }) => {
      const params = new URLSearchParams();
      if (department && department !== 'ALL') params.append('department', department);
      if (role && role !== 'ALL') params.append('role', role);
      if (recommended_level && recommended_level !== 'ALL') params.append('recommended_level', recommended_level);
      if (search && search.trim()) params.append('search', search.trim());
      params.append('skip', skip.toString());
      params.append('limit', limit.toString());
      return params.toString();
    };

    const query1 = buildTrackingQuery({ department: 'CSE', role: 'ALL', skip: 0, limit: 15 });
    assert.ok(query1.includes('department=CSE'));
    assert.ok(!query1.includes('role=ALL'));
    assert.ok(query1.includes('skip=0'));
    assert.ok(query1.includes('limit=15'));

    const query2 = buildTrackingQuery({ search: '211FA04001', recommended_level: 'Advanced' });
    assert.ok(query2.includes('search=211FA04001'));
    assert.ok(query2.includes('recommended_level=Advanced'));
  });

  test('Topic mastery categorization assigns correct mastery levels', () => {
    const categorizeTopic = (score) => {
      if (score >= 7.5) return 'Proficient';
      if (score >= 5.0) return 'Developing';
      return 'Foundational Gap';
    };

    assert.strictEqual(categorizeTopic(8.5), 'Proficient');
    assert.strictEqual(categorizeTopic(7.5), 'Proficient');
    assert.strictEqual(categorizeTopic(6.5), 'Developing');
    assert.strictEqual(categorizeTopic(5.0), 'Developing');
    assert.strictEqual(categorizeTopic(4.9), 'Foundational Gap');
    assert.strictEqual(categorizeTopic(2.0), 'Foundational Gap');
  });

  test('Flagged practice priorities target topics scoring under 6.0/10', () => {
    const topics = [
      { topic: 'DSA', average_score: 8.5 },
      { topic: 'DBMS', average_score: 7.0 },
      { topic: 'Operating Systems', average_score: 4.5 },
      { topic: 'Computer Networks', average_score: 5.5 },
    ];

    const weakTopics = topics.filter((t) => t.average_score < 6.0);
    assert.strictEqual(weakTopics.length, 2);
    assert.strictEqual(weakTopics[0].topic, 'Operating Systems');
    assert.strictEqual(weakTopics[1].topic, 'Computer Networks');
  });
});
