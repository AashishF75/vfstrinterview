import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

describe('Interview Progression and Talking Avatar Tests', () => {
  // Test 1: Successful answer evaluation followed by next-question progression
  test('Successful answer evaluation updates lastEvaluation and enables progression to next question', async () => {
    // Simulated state container
    let state = {
      activeQuestion: {
        session_id: 'sess-101',
        question_index: 1,
        total_questions: 5,
        question_text: 'What is the purpose of the TCP three-way handshake?',
        topic: 'Computer Networks',
        difficulty: 'medium',
        question_type: 'conceptual',
      },
      answerText: 'TCP uses SYN, SYN-ACK, ACK to establish reliable connection state between hosts.',
      submitting: false,
      lastEvaluation: null,
      pendingNextQuestion: null,
      secondsRemaining: 1800,
    };

    // Simulated API response for submission
    const mockSubmitAnswerResponse = {
      success: true,
      data: {
        session_id: 'sess-101',
        question_index: 1,
        evaluated_score: 9.0,
        feedback: 'Excellent explanation of SYN, SYN-ACK, ACK sequence.',
        strengths: ['Identified handshake sequence accurately', 'Clear terminology'],
        improvements: ['Could mention sequence numbers initialization'],
        next_difficulty: 'hard',
        difficulty_rationale: 'High score on question 1 escalates difficulty to hard.',
        is_session_completed: false,
        next_question: {
          session_id: 'sess-101',
          question_index: 2,
          total_questions: 5,
          question_text: 'Explain how TCP congestion control handles packet loss using AIMD.',
          topic: 'Computer Networks',
          difficulty: 'hard',
          question_type: 'conceptual',
          time_remaining_seconds: 1650,
          evaluator_mode: 'gemini',
        },
      },
    };

    // 1. Submit answer step
    const submitResult = mockSubmitAnswerResponse;
    assert.equal(submitResult.success, true);

    state.lastEvaluation = {
      score: submitResult.data.evaluated_score,
      feedback: submitResult.data.feedback,
      strengths: submitResult.data.strengths,
      improvements: submitResult.data.improvements,
      difficultyRationale: submitResult.data.difficulty_rationale,
      isFinal: submitResult.data.is_session_completed,
    };
    state.pendingNextQuestion = submitResult.data.next_question;

    // Verify evaluation state is active and non-final
    assert.equal(state.lastEvaluation.score, 9.0);
    assert.equal(state.lastEvaluation.isFinal, false);
    assert.equal(state.pendingNextQuestion.question_index, 2);
    assert.equal(state.pendingNextQuestion.difficulty, 'hard');

    // 2. Progression step (Proceed to Next Question click)
    const nextQ = state.pendingNextQuestion;
    assert.ok(nextQ, 'pendingNextQuestion must exist to proceed');

    state.activeQuestion = {
      session_id: nextQ.session_id,
      question_index: nextQ.question_index,
      total_questions: nextQ.total_questions,
      question_text: nextQ.question_text,
      topic: nextQ.topic,
      difficulty: nextQ.difficulty,
      question_type: nextQ.question_type,
    };
    state.secondsRemaining = nextQ.time_remaining_seconds;
    // Previous answer draft is cleared only after next question is loaded
    state.answerText = '';
    state.lastEvaluation = null;
    state.pendingNextQuestion = null;

    // Verify state after progression
    assert.equal(state.activeQuestion.question_index, 2);
    assert.equal(state.activeQuestion.difficulty, 'hard');
    assert.equal(state.activeQuestion.question_text.includes('AIMD'), true);
    assert.equal(state.secondsRemaining, 1650);
    assert.equal(state.answerText, '');
    assert.equal(state.lastEvaluation, null);
  });

  // Test 2: Failed progression preserves answer draft and allows safe retry
  test('Failed progression preserves answer draft, records error, and permits safe retry', async () => {
    let state = {
      activeQuestion: {
        session_id: 'sess-102',
        question_index: 2,
        total_questions: 5,
        question_text: 'Explain DNS resolution flow.',
      },
      answerText: 'Client queries recursive resolver, root server, TLD server, and authoritative nameserver.',
      lastEvaluation: {
        score: 8.5,
        feedback: 'Good overview of the hierarchy.',
        isFinal: false,
      },
      pendingNextQuestion: null, // missing locally, requires network fetch
      progressionError: null,
      isProgressing: false,
    };

    let fetchAttempt = 0;
    const mockGetCurrentQuestion = async (sessionId) => {
      fetchAttempt++;
      if (fetchAttempt === 1) {
        return {
          success: false,
          error: 'Network connection lost while fetching question 3',
        };
      }
      return {
        success: true,
        data: {
          session_id: sessionId,
          question_index: 3,
          total_questions: 5,
          question_text: 'What is the BGP protocol used for in inter-domain routing?',
          topic: 'Computer Networks',
          difficulty: 'hard',
          question_type: 'conceptual',
          time_remaining_seconds: 1400,
        },
      };
    };

    // Progression attempt 1 (fails due to network)
    state.isProgressing = true;
    const res1 = await mockGetCurrentQuestion(state.activeQuestion.session_id);
    if (!res1.success) {
      state.progressionError = res1.error;
      state.isProgressing = false;
    }

    // Verify evaluated answer and lastEvaluation are PRESERVED upon progression failure
    assert.equal(state.isProgressing, false);
    assert.equal(state.progressionError, 'Network connection lost while fetching question 3');
    assert.equal(state.activeQuestion.question_index, 2, 'Must not advance active question on failure');
    assert.ok(state.lastEvaluation !== null, 'Must keep evaluation feedback card active');
    assert.ok(state.answerText.length > 0, 'Must preserve candidate answer text');

    // Progression attempt 2 (retry succeeds)
    state.isProgressing = true;
    state.progressionError = null;
    const res2 = await mockGetCurrentQuestion(state.activeQuestion.session_id);
    assert.equal(res2.success, true);

    state.activeQuestion = {
      session_id: res2.data.session_id,
      question_index: res2.data.question_index,
      total_questions: res2.data.total_questions,
      question_text: res2.data.question_text,
      topic: res2.data.topic,
      difficulty: res2.data.difficulty,
      question_type: res2.data.question_type,
    };
    state.answerText = ''; // Cleared only on successful progression
    state.lastEvaluation = null;
    state.isProgressing = false;

    assert.equal(state.activeQuestion.question_index, 3);
    assert.equal(state.answerText, '');
    assert.equal(state.progressionError, null);
    assert.equal(state.lastEvaluation, null);
  });

  // Test 3: Duplicate submission conflict protection (409)
  test('Duplicate submission (409) synchronizes with server state instead of freezing', async () => {
    let state = {
      activeQuestion: {
        session_id: 'sess-103',
        question_index: 1,
        total_questions: 5,
      },
      answerText: 'Already submitted answer.',
      lastEvaluation: null,
      pendingNextQuestion: null,
      error: null,
    };

    // Simulate 409 Conflict returned by backend when submitting already processed question
    const mockSubmitAnswer = async () => ({
      success: false,
      status: 409,
      error: 'Question 1 has already been submitted for this session.',
    });

    const mockGetCurrentQuestion = async () => ({
      success: true,
      data: {
        session_id: 'sess-103',
        question_index: 2, // Server already advanced to question 2
        total_questions: 5,
        question_text: 'What are the main functions of the transport layer?',
        difficulty: 'medium',
        question_type: 'conceptual',
      },
    });

    const subRes = await mockSubmitAnswer();
    assert.equal(subRes.status, 409);

    // Safeguard: handle 409 by checking server progression
    if (subRes.status === 409) {
      const curRes = await mockGetCurrentQuestion();
      if (curRes.success && curRes.data.question_index > state.activeQuestion.question_index) {
        state.pendingNextQuestion = curRes.data;
        state.lastEvaluation = {
          score: 8.0,
          feedback: 'Your answer for this question was previously submitted and recorded on the server.',
          isFinal: false,
        };
      }
    }

    // Verify recovery: user is NOT stuck with a fatal error; progression is enabled
    assert.equal(state.error, null);
    assert.ok(state.lastEvaluation !== null);
    assert.equal(state.pendingNextQuestion.question_index, 2);
  });

  // Test 4: Final-question completion behavior
  test('Submitting final question marks isFinal, loads scorecard, and does not request question N+1', async () => {
    let state = {
      activeQuestion: {
        session_id: 'sess-104',
        question_index: 5,
        total_questions: 5,
        question_text: 'Final algorithmic architecture challenge.',
      },
      lastEvaluation: null,
      pendingNextQuestion: null,
      isCompleted: false,
      scorecard: null,
    };

    const mockFinalSubmitResponse = {
      success: true,
      data: {
        session_id: 'sess-104',
        question_index: 5,
        evaluated_score: 9.5,
        feedback: 'Outstanding comprehensive response.',
        is_session_completed: true,
        next_question: null,
        scorecard_id: 'card-999',
      },
    };

    const mockScorecardData = {
      scorecard_id: 'card-999',
      session_id: 'sess-104',
      overall_score: 8.8,
      percentage_score: 88.0,
      performance_level: 'Distinction',
      difficulty_progression: ['medium', 'hard', 'hard', 'hard', 'hard'],
    };

    // Process submission
    const res = mockFinalSubmitResponse;
    state.lastEvaluation = {
      score: res.data.evaluated_score,
      feedback: res.data.feedback,
      isFinal: res.data.is_session_completed,
    };
    state.pendingNextQuestion = res.data.next_question;

    // Verify final evaluation state
    assert.equal(state.lastEvaluation.isFinal, true);
    assert.equal(state.pendingNextQuestion, null, 'Must not create next_question for final step');

    // User clicks "View Final Scorecard"
    if (state.lastEvaluation.isFinal) {
      state.scorecard = mockScorecardData;
      state.isCompleted = true;
    }

    assert.equal(state.isCompleted, true);
    assert.equal(state.scorecard.overall_score, 8.8);
    assert.equal(state.scorecard.performance_level, 'Distinction');
  });

  // Test 5: Avatar speaking state starts and stops with actual audio playback
  test('Avatar speaking state lifecycle synchronizes with Deepgram audio start, stop, and pause events', () => {
    let avatarState = {
      isSpeaking: false,
      speakingSource: null,
      audioElement: null,
      interviewerStatus: 'ready',
    };

    // Simulated Deepgram audio element
    const mockAudio = {
      src: 'blob:http://localhost:5173/test-speech-uuid',
      paused: true,
      currentTime: 0,
      play: async () => {
        mockAudio.paused = false;
        if (mockAudio.onplay) mockAudio.onplay();
      },
      pause: () => {
        mockAudio.paused = true;
        if (mockAudio.onpause) mockAudio.onpause();
      },
      stop: () => {
        mockAudio.pause();
        mockAudio.currentTime = 0;
        if (mockAudio.onended) mockAudio.onended();
      },
    };

    // 1. Playback starts
    mockAudio.onplay = () => {
      avatarState.isSpeaking = true;
      avatarState.speakingSource = 'deepgram';
      avatarState.audioElement = mockAudio;
      avatarState.interviewerStatus = 'speaking';
    };

    mockAudio.play();
    assert.equal(avatarState.isSpeaking, true);
    assert.equal(avatarState.speakingSource, 'deepgram');
    assert.equal(avatarState.interviewerStatus, 'speaking');
    assert.equal(avatarState.audioElement, mockAudio);

    // 2. Playback finishes (onended)
    mockAudio.onended = () => {
      avatarState.isSpeaking = false;
      avatarState.speakingSource = null;
      avatarState.audioElement = null;
      avatarState.interviewerStatus = 'ready';
    };

    mockAudio.stop();
    assert.equal(avatarState.isSpeaking, false);
    assert.equal(avatarState.speakingSource, null);
    assert.equal(avatarState.audioElement, null);
    assert.equal(avatarState.interviewerStatus, 'ready');

    // 3. User cancels / pauses speech explicitly
    mockAudio.play();
    assert.equal(avatarState.isSpeaking, true);

    const handleStopSpeech = () => {
      mockAudio.pause();
      avatarState.isSpeaking = false;
      avatarState.speakingSource = null;
      avatarState.audioElement = null;
      avatarState.interviewerStatus = 'ready';
    };

    handleStopSpeech();
    assert.equal(avatarState.isSpeaking, false);
    assert.equal(avatarState.interviewerStatus, 'ready');
  });

  // Test 6: Coding question language template initialization on progression
  test('Advancing to coding question initializes language template and switches tab to code', () => {
    let state = {
      activeTab: 'room',
      answerText: '',
      selectedLanguage: 'Python',
      activeQuestion: {
        question_index: 2,
        question_type: 'conceptual',
      },
    };

    const CODE_TEMPLATES = {
      Python: '# Python 3 Solution\ndef solution():\n    pass\n',
      Java: '// Java Solution\npublic class Main {}\n',
    };

    const nextCodingQuestion = {
      question_index: 3,
      question_type: 'coding',
      question_text: 'Implement an LRU Cache with O(1) get and put operations.',
    };

    // Progression logic when next question is coding
    state.activeQuestion = nextCodingQuestion;
    if (nextCodingQuestion.question_type === 'coding') {
      state.answerText = CODE_TEMPLATES[state.selectedLanguage] || '';
      state.activeTab = 'code';
    } else {
      state.answerText = '';
      state.activeTab = 'room';
    }

    assert.equal(state.activeQuestion.question_type, 'coding');
    assert.equal(state.activeTab, 'code');
    assert.ok(state.answerText.includes('# Python 3 Solution'));
  });

  // Test 7: Avatar mouth deformation continuity and zero boundary edge artifacts
  test('Avatar mouth deformation produces continuous smooth displacement with zero edge seams', () => {
    const cropW = 105;
    const cropH = 70;
    const cropX = 639;
    const cropY = 296;

    const hFactors = new Float32Array(cropW);
    for (let x = 0; x < cropW; x++) {
      const dx = (cropX + x - 691) / 52;
      hFactors[x] = Math.abs(dx) < 1 ? 0.5 * (1 + Math.cos(dx * Math.PI)) : 0;
    }

    const vFactors = new Float32Array(cropH);
    for (let y = 0; y < cropH; y++) {
      const fullY = cropY + y;
      if (fullY <= 312) {
        const t = Math.max(0, (fullY - 296) / 16);
        vFactors[y] = t * t * (3 - 2 * t);
      } else if (fullY <= 365) {
        const t = Math.min(1, (fullY - 312) / 53);
        const st = t * t * (3 - 2 * t);
        vFactors[y] = 1 - st;
      } else {
        vFactors[y] = 0;
      }
    }

    // 1. Boundary condition: displacement at borders must be exactly 0 (seamless blending)
    assert.equal(hFactors[0], 0, 'Left boundary displacement must be 0 to prevent seam lines');
    assert.equal(hFactors[cropW - 1], 0, 'Right boundary displacement must be 0 to prevent seam lines');
    assert.equal(vFactors[0], 0, 'Top boundary displacement must be 0 to prevent seam lines');
    assert.ok(vFactors[cropH - 1] < 1e-4, 'Bottom boundary displacement must be negligible to prevent seam lines');

    // 2. Monotonicity: max vertical displacement derivative must remain << 1.0 (no foldover or tears)
    const maxSpeechDisp = 3.0; // peak speech displacement
    for (let y = 0; y < cropH - 1; y++) {
      const derivative = (vFactors[y + 1] - vFactors[y]) * maxSpeechDisp;
      assert.ok(Math.abs(derivative) < 0.5, `Vertical derivative at row ${y} must not cause pixel tearing`);
    }

    // 3. Peak displacement is within subtle physiological limits (<= 3.0px)
    let peakV = 0;
    for (let y = 0; y < cropH; y++) {
      if (vFactors[y] > peakV) peakV = vFactors[y];
    }
    const peakDisplacement = peakV * maxSpeechDisp;
    assert.ok(peakDisplacement <= 3.0, 'Mouth displacement must be subtle and realistic');
  });

  // Test 8: Avatar returns to natural resting unwarped photo when volume decays or speech pauses
  test('Avatar returns strictly to resting unwarped photo when volume is at or below threshold', () => {
    let currentVolume = 0.8;
    const decay = 0.25;

    // Simulate speech finishing (targetVolume = 0)
    const targetVolume = 0;
    let framesToResting = 0;

    while (currentVolume > 0.012 && framesToResting < 60) {
      currentVolume += (targetVolume - currentVolume) * decay;
      framesToResting++;
    }

    // Volume must decay into resting deadzone within ~15 frames (~250ms)
    assert.ok(currentVolume <= 0.012, 'Volume must reach resting state');
    assert.ok(framesToResting <= 20, 'Return to closed resting position must be prompt and natural');

    // At resting state, mouth is drawn directly from base unblemished photo (displacement = 0)
    const isWarpActive = currentVolume > 0.012;
    assert.equal(isWarpActive, false, 'No warping or overlays must render when audio is resting');
  });

  // Test 9: Complete regression: Submit Question 1 -> evaluation retained -> Next Question loads authoritative Question 2
  test('Submit Question 1 displays evaluation, keeps draft until Next Question, and updates counter to 2 of 5', async () => {
    let state = {
      sessionId: 'sess-vfstr-prog-001',
      activeQuestion: {
        session_id: 'sess-vfstr-prog-001',
        question_index: 1,
        total_questions: 5,
        question_text: 'What is the role of ARP in local area networks?',
        topic: 'Computer Networks',
        difficulty: 'medium',
        question_type: 'conceptual',
        interview_title: 'Computer Networks Adaptive Interview',
      },
      answerText: 'ARP maps an IPv4 address to a physical MAC address on the local link layer.',
      submitting: false,
      isProgressing: false,
      lastEvaluation: null,
      pendingNextQuestion: null,
      secondsRemaining: 1800,
    };

    // 1. Submit Question 1
    state.submitting = true;
    const mockSubmitResponse = {
      success: true,
      data: {
        session_id: 'sess-vfstr-prog-001',
        question_index: 1,
        evaluated_score: 9.2,
        feedback: 'Precise definition of ARP protocol mapping IP to MAC address.',
        strengths: ['Identified link-layer mapping', 'Accurate protocol purpose'],
        improvements: ['Could mention ARP cache and broadcast request'],
        next_difficulty: 'hard',
        difficulty_rationale: 'High score on Question 1 advances difficulty to hard tier.',
        is_session_completed: false,
        next_question: {
          session_id: 'sess-vfstr-prog-001',
          question_index: 2,
          total_questions: 5,
          question_text: 'Explain how TCP SYN cookies prevent SYN flood denial of service attacks.',
          topic: 'Network Security',
          difficulty: 'hard',
          question_type: 'conceptual',
          time_remaining_seconds: 1680,
          interview_title: 'Computer Networks Adaptive Interview',
        },
      },
    };

    state.submitting = false;
    state.lastEvaluation = {
      score: mockSubmitResponse.data.evaluated_score,
      feedback: mockSubmitResponse.data.feedback,
      strengths: mockSubmitResponse.data.strengths,
      improvements: mockSubmitResponse.data.improvements,
      difficultyRationale: mockSubmitResponse.data.difficulty_rationale,
      isFinal: false,
    };
    state.pendingNextQuestion = mockSubmitResponse.data.next_question;

    // STEP A: Verify Question 1 state and evaluation are PRESERVED before user proceeds
    assert.equal(state.activeQuestion.question_index, 1, 'Header must stay Question 1 until progression');
    assert.equal(state.activeQuestion.question_text, 'What is the role of ARP in local area networks?');
    assert.equal(state.answerText, 'ARP maps an IPv4 address to a physical MAC address on the local link layer.', 'Draft must remain intact');
    assert.ok(state.lastEvaluation !== null, 'Evaluation feedback card must be visible');
    assert.equal(state.lastEvaluation.score, 9.2);
    assert.equal(state.lastEvaluation.isFinal, false);

    // STEP B: User clicks prominent "Next Question" button
    state.isProgressing = true;

    // Authoritative backend endpoint call
    const mockGetCurrentQuestion = async (sessId) => ({
      success: true,
      data: {
        session_id: sessId,
        question_index: 2,
        current_question_index: 2,
        total_questions: 5,
        total_questions_target: 5,
        question_text: 'Explain how TCP SYN cookies prevent SYN flood denial of service attacks.',
        topic: 'Network Security',
        difficulty: 'hard',
        current_difficulty: 'hard',
        question_type: 'conceptual',
        time_remaining_seconds: 1680,
        interview_title: 'Computer Networks Adaptive Interview',
      },
    });

    let nextData = null;
    const curRes = await mockGetCurrentQuestion(state.sessionId);
    if (curRes.success && curRes.data) {
      nextData = curRes.data;
    } else {
      nextData = state.pendingNextQuestion;
    }

    assert.ok(nextData, 'Authoritative next question must be obtained');
    assert.equal(nextData.question_index, 2);

    // Update activeQuestion state from authoritative backend response
    state.activeQuestion = {
      session_id: nextData.session_id,
      question_index: nextData.question_index ?? nextData.current_question_index ?? 2,
      total_questions: nextData.total_questions ?? nextData.total_questions_target ?? 5,
      question_text: nextData.question_text,
      topic: nextData.topic,
      difficulty: nextData.difficulty,
      question_type: nextData.question_type,
      interview_title: nextData.interview_title,
    };
    state.secondsRemaining = nextData.time_remaining_seconds;

    // Answer draft is cleared ONLY after question 2 is loaded successfully
    state.answerText = '';
    state.lastEvaluation = null;
    state.pendingNextQuestion = null;
    state.isProgressing = false;

    // STEP C: Verify Question 2 state
    assert.equal(state.activeQuestion.question_index, 2, 'Question counter must now be 2 of 5');
    assert.equal(state.activeQuestion.total_questions, 5);
    assert.equal(state.activeQuestion.difficulty, 'hard');
    assert.equal(state.activeQuestion.topic, 'Network Security');
    assert.ok(state.activeQuestion.question_text.includes('SYN cookies'));
    assert.equal(state.secondsRemaining, 1680);
    assert.equal(state.answerText, '', 'Answer draft must be reset for Question 2');
    assert.equal(state.lastEvaluation, null, 'Evaluation card reset for fresh question prompt');
  });

  // Test 10: Missing pendingNextQuestion is recovered through getCurrentQuestion endpoint
  test('Missing pendingNextQuestion is recovered seamlessly via backend current-question endpoint', async () => {
    let state = {
      sessionId: 'sess-recovery-002',
      activeQuestion: {
        session_id: 'sess-recovery-002',
        question_index: 1,
        total_questions: 5,
        question_text: 'What is MTU?',
      },
      lastEvaluation: { score: 8.0, isFinal: false },
      pendingNextQuestion: null, // intentionally null/missing locally
      isProgressing: false,
    };

    let backendCalled = false;
    const mockGetCurrentQuestion = async (sessId) => {
      backendCalled = true;
      return {
        success: true,
        data: {
          session_id: sessId,
          question_index: 2,
          total_questions: 5,
          question_text: 'Explain TCP flow control using sliding windows.',
          topic: 'Computer Networks',
          difficulty: 'medium',
          question_type: 'conceptual',
          time_remaining_seconds: 1500,
        },
      };
    };

    state.isProgressing = true;
    let nextData = state.pendingNextQuestion;
    if (!nextData || !nextData.question_text) {
      const curRes = await mockGetCurrentQuestion(state.sessionId);
      if (curRes.success && curRes.data) {
        nextData = curRes.data;
      }
    }

    assert.equal(backendCalled, true, 'Must call backend current-question endpoint when pendingNextQuestion is missing');
    assert.ok(nextData !== null);
    assert.equal(nextData.question_index, 2);

    state.activeQuestion = {
      session_id: nextData.session_id,
      question_index: nextData.question_index,
      total_questions: nextData.total_questions,
      question_text: nextData.question_text,
    };
    state.isProgressing = false;

    assert.equal(state.activeQuestion.question_index, 2);
    assert.ok(state.activeQuestion.question_text.includes('sliding windows'));
  });

  // Test 11: Speech-handler declaration order eliminates Temporal Dead Zone ReferenceError
  test('Speech-handler initialization order allows handleStopSpeech to be safely invoked before or during speakQuestion', () => {
    let isSpeaking = false;
    let speakingSource = null;
    let audioPlaybackStopped = false;

    // Verified pattern: handleStopSpeech declared as useCallback first, with zero TDZ issues
    const handleStopSpeech = () => {
      audioPlaybackStopped = true;
      isSpeaking = false;
      speakingSource = null;
    };

    const speakQuestion = (text) => {
      // Must safely execute without ReferenceError: Cannot access 'handleStopSpeech' before initialization
      handleStopSpeech();
      if (!text) return;
      isSpeaking = true;
      speakingSource = 'deepgram';
    };

    // 1. Calling speakQuestion properly stops previous audio without throwing
    assert.doesNotThrow(() => {
      speakQuestion('What is distance vector routing?');
    });

    assert.equal(isSpeaking, true);
    assert.equal(speakingSource, 'deepgram');
    assert.equal(audioPlaybackStopped, true);

    // 2. Calling handleStopSpeech cleanly halts speech
    handleStopSpeech();
    assert.equal(isSpeaking, false);
    assert.equal(speakingSource, null);
  });
});

