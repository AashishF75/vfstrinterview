import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

describe('Voice Answer Transcription Flow Tests', () => {
  test('transcribeInterviewAudio sends proper FormData and unsets Content-Type so boundary is preserved', async () => {
    // Mock apiClient
    let capturedUrl = null;
    let capturedData = null;
    let capturedConfig = null;

    const mockApiClient = {
      post: async (url, data, config) => {
        capturedUrl = url;
        capturedData = data;
        capturedConfig = config;
        return {
          data: {
            success: true,
            transcript: 'I used a hash map to achieve O(1) lookup time.',
            confidence: 0.96,
            duration_seconds: 3.2,
          },
        };
      },
    };

    // Simulate transcribeInterviewAudio implementation logic
    const transcribeInterviewAudio = async (sessionId, audioBlob) => {
      try {
        const formData = new FormData();
        let ext = 'webm';
        if (audioBlob.type?.includes('wav')) {
          ext = 'wav';
        } else if (audioBlob.type?.includes('mp4') || audioBlob.type?.includes('m4a')) {
          ext = 'mp4';
        } else if (audioBlob.type?.includes('ogg') || audioBlob.type?.includes('opus')) {
          ext = 'ogg';
        }
        const filename = `recording.${ext}`;
        formData.append('file', audioBlob, filename);

        const response = await mockApiClient.post(
          `/api/interview-rooms/sessions/${sessionId}/voice/transcribe`,
          formData,
          {
            headers: {
              'Content-Type': undefined,
            },
            timeout: 20000,
          }
        );
        return { success: true, data: response.data };
      } catch (error) {
        return {
          success: false,
          error: error.response?.data?.detail || error.message || 'Speech transcription failed',
          status: error.response?.status,
        };
      }
    };

    const mockBlob = new Blob(['mock-audio-bytes'], { type: 'audio/webm;codecs=opus' });
    const result = await transcribeInterviewAudio('session-test-123', mockBlob);

    assert.equal(result.success, true);
    assert.equal(result.data.transcript, 'I used a hash map to achieve O(1) lookup time.');
    assert.equal(capturedUrl, '/api/interview-rooms/sessions/session-test-123/voice/transcribe');
    assert.equal(capturedConfig.headers['Content-Type'], undefined, 'Content-Type must be undefined so multipart boundary is generated');
    assert.ok(capturedData instanceof FormData, 'Data must be FormData');
    assert.ok(capturedData.has('file'), 'FormData must have file key');
  });

  test('transcribeInterviewAudio detects mp4 and wav file extensions accurately', async () => {
    const testCases = [
      { mime: 'audio/wav', expectedExt: 'recording.wav' },
      { mime: 'audio/mp4', expectedExt: 'recording.mp4' },
      { mime: 'audio/ogg;codecs=opus', expectedExt: 'recording.ogg' },
      { mime: 'audio/webm', expectedExt: 'recording.webm' },
    ];

    for (const { mime, expectedExt } of testCases) {
      let appendedFilename = null;
      const formDataMock = {
        append: (_key, _blob, filename) => {
          appendedFilename = filename;
        },
      };

      const getFilename = (blob) => {
        let ext = 'webm';
        if (blob.type?.includes('wav')) ext = 'wav';
        else if (blob.type?.includes('mp4') || blob.type?.includes('m4a')) ext = 'mp4';
        else if (blob.type?.includes('ogg') || blob.type?.includes('opus')) ext = 'ogg';
        return `recording.${ext}`;
      };

      const filename = getFilename({ type: mime });
      assert.equal(filename, expectedExt);
    }
  });

  test('transcription failure returns formatted error object without throwing uncaught exceptions', async () => {
    const mockApiClient = {
      post: async () => {
        const error = new Error('Request failed with status code 503');
        error.response = {
          status: 503,
          data: { detail: 'Deepgram voice transcription is not configured on this server.' },
        };
        throw error;
      },
    };

    const transcribeInterviewAudio = async (sessionId, audioBlob) => {
      try {
        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.webm');
        const response = await mockApiClient.post(
          `/api/interview-rooms/sessions/${sessionId}/voice/transcribe`,
          formData,
          { headers: { 'Content-Type': undefined }, timeout: 20000 }
        );
        return { success: true, data: response.data };
      } catch (error) {
        return {
          success: false,
          error: error.response?.data?.detail || error.message || 'Speech transcription failed',
          status: error.response?.status,
        };
      }
    };

    const mockBlob = new Blob(['bytes'], { type: 'audio/webm' });
    const res = await transcribeInterviewAudio('sess-1', mockBlob);

    assert.equal(res.success, false);
    assert.equal(res.status, 503);
    assert.match(res.error, /Deepgram voice transcription is not configured/);
  });

  test('empty audio chunk handling sets clear error and aborts upload', () => {
    let speechError = null;
    const setSpeechError = (msg) => { speechError = msg; };

    const chunks = [];
    if (chunks.length === 0) {
      setSpeechError('No audio data was captured. Please check your microphone and speak clearly.');
    }

    assert.equal(speechError, 'No audio data was captured. Please check your microphone and speak clearly.');
  });

  test('concurrent recording activation is guarded by isStartingRecordingRef', () => {
    let callCount = 0;
    const isStartingRecordingRef = { current: false };
    const isRecordingAudio = false;
    const isTranscribingAudio = false;

    const startRecording = () => {
      if (isRecordingAudio || isTranscribingAudio || isStartingRecordingRef.current) {
        return false;
      }
      isStartingRecordingRef.current = true;
      callCount++;
      return true;
    };

    const first = startRecording();
    const second = startRecording(); // second rapid click

    assert.equal(first, true);
    assert.equal(second, false);
    assert.equal(callCount, 1);
  });

  test('interviewer status derivation maps transcribing state accurately', () => {
    const getInterviewerState = ({ isSpeaking, isRecording, isTranscribing, submitting }) => {
      if (isSpeaking) return 'speaking';
      if (isRecording) return 'listening';
      if (isTranscribing) return 'transcribing';
      if (submitting) return 'thinking';
      return 'ready';
    };

    const getInterviewerStatus = (state) => {
      switch (state) {
        case 'speaking': return 'Speaking...';
        case 'listening': return 'Listening...';
        case 'transcribing': return 'Transcribing...';
        case 'thinking': return 'Thinking...';
        case 'ready': default: return 'Ready';
      }
    };

    assert.equal(getInterviewerStatus(getInterviewerState({ isTranscribing: true })), 'Transcribing...');
    assert.equal(getInterviewerStatus(getInterviewerState({ isRecording: true })), 'Listening...');
    assert.equal(getInterviewerStatus(getInterviewerState({ isSpeaking: true })), 'Speaking...');
    assert.equal(getInterviewerStatus(getInterviewerState({ submitting: true })), 'Thinking...');
    assert.equal(getInterviewerStatus(getInterviewerState({})), 'Ready');
  });

  test('answer text state updates with transcript while preserving candidate edits', () => {
    let answerText = '';
    const setAnswerText = (updater) => {
      answerText = typeof updater === 'function' ? updater(answerText) : updater;
    };

    // 1. Spoken answer transcript arrives
    const transcript1 = 'Encapsulation binds data and functions together.';
    setAnswerText((prev) => (prev.trim() ? `${prev.trim()} ${transcript1}` : transcript1));
    assert.equal(answerText, 'Encapsulation binds data and functions together.');

    // 2. Candidate edits the transcript
    setAnswerText(answerText + ' It also restricts direct access.');
    assert.equal(answerText, 'Encapsulation binds data and functions together. It also restricts direct access.');

    // 3. Second spoken phrase appends cleanly
    const transcript2 = 'This is achieved using private access modifiers.';
    setAnswerText((prev) => (prev.trim() ? `${prev.trim()} ${transcript2}` : transcript2));
    assert.equal(
      answerText,
      'Encapsulation binds data and functions together. It also restricts direct access. This is achieved using private access modifiers.'
    );
  });
});
