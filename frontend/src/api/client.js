import axios from 'axios';

// Create configured Axios instance
const apiClient = axios.create({
  baseURL: (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) || '',
  timeout: 25000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to attach bearer token from sessionStorage
apiClient.interceptors.request.use(
  (config) => {
    const token = sessionStorage.getItem('vfstr_access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle authorization errors and format clear timeout messages
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid
      sessionStorage.removeItem('vfstr_access_token');
      sessionStorage.removeItem('vfstr_user_cache');
    }
    if (error.code === 'ECONNABORTED' || (error.message && error.message.toLowerCase().includes('timeout'))) {
      error.friendlyMessage = 'The server took longer than expected to respond. Please check your network connection and try again.';
    }
    return Promise.reject(error);
  }
);

export const checkBackendHealth = async () => {
  try {
    const response = await apiClient.get('/api/health');
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Unable to reach backend service',
    };
  }
};

export const loginUser = async (email, password) => {
  try {
    const response = await apiClient.post('/api/auth/login', {
      email,
      password,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    const detail = error.response?.data?.detail;
    const errorMessage = typeof detail === 'string' ? detail : 'Authentication failed';
    return {
      success: false,
      error: errorMessage,
      status: error.response?.status,
    };
  }
};

export const logoutUser = async () => {
  try {
    const response = await apiClient.post('/api/auth/logout');
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message,
    };
  }
};

export const getCurrentUser = async () => {
  try {
    const response = await apiClient.get('/api/auth/me');
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message,
    };
  }
};

export const getProtectedTest = async () => {
  try {
    const response = await apiClient.get('/api/auth/protected-test');
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message,
      status: error.response?.status,
    };
  }
};

export const getAdminOnlyTest = async () => {
  try {
    const response = await apiClient.get('/api/auth/admin-only');
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message,
      status: error.response?.status,
    };
  }
};

export const registerVfstrStudent = async ({ registrationNumber, contactNumber }) => {
  try {
    const response = await apiClient.post('/api/auth/vfstr/register', {
      registration_number: registrationNumber,
      contact_number: contactNumber,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'VFSTR student verification failed',
      status: error.response?.status,
    };
  }
};

export const initiateRegistration = async (registrationNumber) => {
  try {
    const response = await apiClient.post('/api/auth/register/initiate', {
      registration_number: registrationNumber,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'Registration initiation failed',
      status: error.response?.status,
    };
  }
};

export const resendRegistrationCode = async (registrationNumber) => {
  try {
    const response = await apiClient.post('/api/auth/register/resend', {
      registration_number: registrationNumber,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'Resend code failed',
      status: error.response?.status,
    };
  }
};

export const completeRegistration = async (registrationNumber, verificationCode, password) => {
  try {
    const response = await apiClient.post('/api/auth/register/complete', {
      registration_number: registrationNumber,
      verification_code: verificationCode,
      password: password,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'Registration failed',
      status: error.response?.status,
    };
  }
};

// ==========================================
// General Student Registration APIs (Partner Colleges)
// ==========================================

export const getAllowedInstitutions = async () => {
  try {
    const response = await apiClient.get('/api/auth/institutions/allowed');
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch partner institutions',
      status: error.response?.status,
    };
  }
};

export const registerGeneralStudent = async ({
  fullName,
  collegeName,
  collegeRegNo,
  email,
  contactNumber,
  password,
}) => {
  try {
    const response = await apiClient.post('/api/auth/general/register', {
      full_name: fullName,
      college_name: collegeName,
      college_reg_no: collegeRegNo,
      email: email,
      contact_number: contactNumber,
      password: password,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'General student registration failed',
      status: error.response?.status,
    };
  }
};

export const initiateGeneralRegistration = async ({
  fullName,
  collegeName,
  collegeRegNo,
  email,
  contactNumber,
  password,
}) => {
  try {
    const response = await apiClient.post('/api/auth/general/register/initiate', {
      full_name: fullName,
      college_name: collegeName,
      college_reg_no: collegeRegNo,
      email: email,
      contact_number: contactNumber,
      password: password,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'General registration initiation failed',
      status: error.response?.status,
    };
  }
};

export const resendGeneralRegistrationCode = async (email) => {
  try {
    const response = await apiClient.post('/api/auth/general/register/resend', {
      email,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'Resend verification code failed',
      status: error.response?.status,
    };
  }
};

export const completeGeneralRegistration = async (email, verificationCode) => {
  try {
    const response = await apiClient.post('/api/auth/general/register/complete', {
      email,
      verification_code: verificationCode,
    });
    return {
      success: true,
      data: response.data,
    };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.friendlyMessage || error.message || 'General registration completion failed',
      status: error.response?.status,
    };
  }
};

// ==========================================
// University Admin Interview Management APIs
// ==========================================

export const getAdminInterviews = async () => {
  try {
    const response = await apiClient.get('/api/admin/interviews');
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch interviews',
      status: error.response?.status,
    };
  }
};

export const getAdminInterviewDetail = async (interviewId) => {
  try {
    const response = await apiClient.get(`/api/admin/interviews/${interviewId}`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch interview details',
      status: error.response?.status,
    };
  }
};

export const createAdminInterview = async (interviewData) => {
  try {
    const response = await apiClient.post('/api/admin/interviews', interviewData);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to create interview',
      status: error.response?.status,
    };
  }
};

export const updateAdminInterview = async (interviewId, updateData) => {
  try {
    const response = await apiClient.patch(`/api/admin/interviews/${interviewId}`, updateData);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to update interview',
      status: error.response?.status,
    };
  }
};

export const searchEligibleCandidates = async ({ interviewId, section, department, batchCohort, eligibility, search, limit = 300 } = {}) => {
  try {
    const params = new URLSearchParams();
    if (interviewId) params.append('interview_id', interviewId);
    if (section && section !== 'ALL') params.append('section', section);
    if (department && department !== 'ALL') params.append('department', department);
    if (batchCohort && batchCohort !== 'ALL') params.append('batch_cohort', batchCohort);
    if (eligibility && eligibility !== 'ALL') params.append('eligibility', eligibility);
    if (search) params.append('search', search);
    if (limit) params.append('limit', limit.toString());

    const response = await apiClient.get(`/api/admin/interviews/candidates/search?${params.toString()}`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to search candidates',
      status: error.response?.status,
    };
  }
};

export const getQuestionSets = async () => {
  try {
    const response = await apiClient.get('/api/admin/interviews/question-sets');
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch question sets',
      status: error.response?.status,
    };
  }
};

export const previewQuestionSet = async (setId, limit = 10) => {
  try {
    const response = await apiClient.get(`/api/admin/interviews/question-sets/${encodeURIComponent(setId)}/preview?limit=${limit}`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to preview question set',
      status: error.response?.status,
    };
  }
};

export const assignCandidatesToInterview = async (interviewId, registrationNumbers) => {
  try {
    const response = await apiClient.post(`/api/admin/interviews/${interviewId}/assign`, {
      registration_numbers: registrationNumbers,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to assign candidates',
      status: error.response?.status,
    };
  }
};

// ==========================================
// Student Interview Assignment Dashboard APIs
// ==========================================

export const getStudentAssignments = async () => {
  try {
    const response = await apiClient.get('/api/student/interviews/my-assignments');
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch assignments',
      status: error.response?.status,
    };
  }
};

export const getStudentAssignmentDetail = async (assignmentId) => {
  try {
    const response = await apiClient.get(`/api/student/interviews/my-assignments/${assignmentId}`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch assignment detail',
      status: error.response?.status,
    };
  }
};

export const acceptStudentAssignment = async (assignmentId) => {
  try {
    const response = await apiClient.patch(`/api/student/interviews/my-assignments/${assignmentId}/accept`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to accept assignment',
      status: error.response?.status,
    };
  }
};

export const startStudentInterview = async (assignmentId) => {
  try {
    const response = await apiClient.patch(`/api/student/interviews/my-assignments/${assignmentId}/start`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to start interview',
      status: error.response?.status,
    };
  }
};

export const completeStudentInterview = async (assignmentId) => {
  try {
    const response = await apiClient.patch(`/api/student/interviews/my-assignments/${assignmentId}/complete`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to complete interview',
      status: error.response?.status,
    };
  }
};

export const getAvailableJobRoles = async () => {
  try {
    const response = await apiClient.get('/api/student/interviews/roles');
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch job roles',
      status: error.response?.status,
    };
  }
};

export const selectStudentJobRole = async (role) => {
  try {
    const response = await apiClient.post('/api/student/interviews/select-role', { role });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to initialize role interview',
      status: error.response?.status,
    };
  }
};

// ==========================================
// Student Performance Tracking & Level Recommendation APIs
// ==========================================

export const getStudentProgressSummary = async () => {
  try {
    const response = await apiClient.get('/api/student/interviews/progress/summary');
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch student progress summary',
      status: error.response?.status,
    };
  }
};

export const getStudentInterviewHistory = async (skip = 0, limit = 20) => {
  try {
    const response = await apiClient.get(`/api/student/interviews/progress/history?skip=${skip}&limit=${limit}`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch interview history',
      status: error.response?.status,
    };
  }
};

export const updateStudentProfile = async (profileData) => {
  try {
    const response = await apiClient.patch('/api/student/interviews/profile', profileData);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to update student profile',
      status: error.response?.status,
    };
  }
};

export const getAdminStudentTracking = async ({
  department,
  batch_cohort,
  role,
  recommended_level,
  search,
  skip = 0,
  limit = 20,
} = {}) => {
  try {
    const params = new URLSearchParams();
    if (department && department !== 'ALL') params.append('department', department);
    if (batch_cohort && batch_cohort !== 'ALL') params.append('batch_cohort', batch_cohort);
    if (role && role !== 'ALL') params.append('role', role);
    if (recommended_level && recommended_level !== 'ALL') params.append('recommended_level', recommended_level);
    if (search && search.trim()) params.append('search', search.trim());
    params.append('skip', skip.toString());
    params.append('limit', limit.toString());

    const response = await apiClient.get(`/api/admin/interviews/students/tracking?${params.toString()}`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch student tracking data',
      status: error.response?.status,
    };
  }
};

export const getAdminStudentDetail = async (registrationNumber) => {
  try {
    const response = await apiClient.get(`/api/admin/interviews/students/${encodeURIComponent(registrationNumber)}/progress`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch student progress detail',
      status: error.response?.status,
    };
  }
};

// Adaptive Interview Session Room APIs
export const getAssignmentSession = async (assignmentId) => {
  try {
    const response = await apiClient.get(`/api/interview-rooms/assignments/${assignmentId}/session`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to check assignment session status',
      status: error.response?.status,
    };
  }
};

export const startInterviewSession = async (assignmentId) => {
  try {
    const response = await apiClient.post('/api/interview-rooms/sessions/start', {
      assignment_id: assignmentId,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to start interview session',
      status: error.response?.status,
    };
  }
};

export const getCurrentQuestion = async (sessionId) => {
  try {
    const response = await apiClient.get(`/api/interview-rooms/sessions/${sessionId}/current-question`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to retrieve current question',
      status: error.response?.status,
    };
  }
};

export const submitInterviewAnswer = async (sessionId, answerText, language = null, sourceCode = null) => {
  try {
    const payload = { answer_text: answerText };
    if (language) payload.language = language;
    if (sourceCode) payload.source_code = sourceCode;
    const response = await apiClient.post(`/api/interview-rooms/sessions/${sessionId}/submit-answer`, payload);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to submit answer',
      status: error.response?.status,
    };
  }
};

export const runInterviewCode = async (sessionId, { language, source_code, custom_input = null }) => {
  try {
    const response = await apiClient.post(`/api/interview-rooms/sessions/${sessionId}/run-code`, {
      language,
      source_code,
      custom_input,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Code execution service failed',
      status: error.response?.status,
    };
  }
};

export const submitInterviewCode = async (sessionId, { language, source_code }) => {
  try {
    const response = await apiClient.post(`/api/interview-rooms/sessions/${sessionId}/submit-code`, {
      language,
      source_code,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Code submission failed',
      status: error.response?.status,
    };
  }
};

export const skipInterviewQuestion = async (sessionId) => {
  try {
    const response = await apiClient.post(`/api/interview-rooms/sessions/${sessionId}/skip-question`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to skip question',
      status: error.response?.status,
    };
  }
};

export const getSessionScorecard = async (sessionId) => {
  try {
    const response = await apiClient.get(`/api/interview-rooms/sessions/${sessionId}/scorecard`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to retrieve scorecard',
      status: error.response?.status,
    };
  }
};

export const getStudentPerformanceReport = async (assignmentId) => {
  try {
    const response = await apiClient.get(`/api/student/interviews/reports/${assignmentId}`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to retrieve performance report',
      status: error.response?.status,
    };
  }
};

export const getSessionPerformanceReport = async (sessionId) => {
  try {
    const response = await apiClient.get(`/api/interview-rooms/sessions/${sessionId}/report`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to retrieve session report',
      status: error.response?.status,
    };
  }
};

export const updateVideoWatchStatus = async (assignmentOrSessionId, resourceId, watched = true) => {
  try {
    const isSession = assignmentOrSessionId && assignmentOrSessionId.startsWith('sess_');
    const endpoint = isSession
      ? `/api/interview-rooms/sessions/${assignmentOrSessionId}/videos/${resourceId}/watch`
      : `/api/student/interviews/reports/${assignmentOrSessionId}/videos/${resourceId}/watch`;
    const response = await apiClient.patch(endpoint, { watched });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to update video watch status',
      status: error.response?.status,
    };
  }
};



// Level 1 Proctoring Telemetry APIs
export const recordProctoringEvents = async (sessionId, events) => {
  try {
    const response = await apiClient.post(`/api/interview-rooms/sessions/${sessionId}/proctoring-events`, {
      events,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to persist proctoring events',
      status: error.response?.status,
    };
  }
};

export const getSessionProctoringTimeline = async (sessionId) => {
  if (!sessionId || typeof sessionId !== 'string' || !sessionId.trim()) {
    return {
      success: false,
      error: 'A valid session ID is required to retrieve the proctoring timeline',
      status: 400,
    };
  }
  const cleanSessionId = sessionId.trim();
  try {
    const response = await apiClient.get(`/api/admin/interviews/sessions/${cleanSessionId}/proctoring-events`);
    return { success: true, data: response.data };
  } catch (error) {
    // If admin endpoint is not found or user lacks admin route permission, try interview-rooms endpoint
    if (error.response?.status === 404 || error.response?.status === 403) {
      try {
        const fallback = await apiClient.get(`/api/interview-rooms/sessions/${cleanSessionId}/proctoring-events`);
        return { success: true, data: fallback.data };
      } catch (fbErr) {
        return {
          success: false,
          error: fbErr.response?.data?.detail || error.response?.data?.detail || fbErr.message || 'Failed to retrieve proctoring timeline',
          status: fbErr.response?.status || error.response?.status,
        };
      }
    }
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to retrieve proctoring timeline',
      status: error.response?.status,
    };
  }
};

export const updateSessionProctoringReview = async (sessionId, reviewStatus, reviewNotes) => {
  if (!sessionId || typeof sessionId !== 'string' || !sessionId.trim()) {
    return {
      success: false,
      error: 'A valid session ID is required to update proctoring review',
      status: 400,
    };
  }
  const validStatuses = ['unreviewed', 'cleared', 'flagged'];
  if (!validStatuses.includes(reviewStatus)) {
    return {
      success: false,
      error: `Invalid review status '${reviewStatus}'. Allowed values: ${validStatuses.join(', ')}`,
      status: 422,
    };
  }
  if (reviewNotes && reviewNotes.length > 2000) {
    return {
      success: false,
      error: 'Review notes cannot exceed 2000 characters',
      status: 422,
    };
  }
  try {
    const response = await apiClient.patch(`/api/admin/interviews/sessions/${sessionId.trim()}/proctoring-review`, {
      review_status: reviewStatus,
      review_notes: reviewNotes?.trim() || null,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to update proctoring review',
      status: error.response?.status,
    };
  }
};

// ==============================================================================
// Deepgram Voice Service Integration (Phase 3 Voice STT & TTS)
// ==============================================================================

export const getVoiceStatus = async (sessionId) => {
  try {
    const response = await apiClient.get(`/api/interview-rooms/sessions/${sessionId}/voice/status`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to check voice service status',
      status: error.response?.status,
    };
  }
};

export const transcribeInterviewAudio = async (sessionId, audioBlob) => {
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

    const response = await apiClient.post(
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

export const synthesizeInterviewSpeech = async (sessionId, text) => {
  try {
    const response = await apiClient.post(
      `/api/interview-rooms/sessions/${sessionId}/voice/speak`,
      { text },
      {
        responseType: 'blob',
        timeout: 20000,
      }
    );
    return { success: true, data: response.data };
  } catch (error) {
    let errorDetail = error.message || 'Speech synthesis failed';
    if (error.response?.data instanceof Blob) {
      try {
        const textData = await error.response.data.text();
        const json = JSON.parse(textData);
        if (json?.detail) errorDetail = json.detail;
      } catch {
        // use default errorDetail
      }
    } else if (error.response?.data?.detail) {
      errorDetail = error.response.data.detail;
    }
    return {
      success: false,
      error: errorDetail,
      status: error.response?.status,
    };
  }
};

// ==============================================================================
// Institution Question Bank Management APIs
// ==============================================================================

export const previewQuestionFile = async (file, defaultTopic = 'Technical Assessment') => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    if (defaultTopic) {
      formData.append('default_topic', defaultTopic);
    }
    const response = await apiClient.post('/api/admin/interviews/questions/preview', formData, {
      headers: {
        'Content-Type': undefined,
      },
      timeout: 30000,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to parse question file',
      status: error.response?.status,
    };
  }
};

export const saveConfirmedQuestions = async (payload) => {
  try {
    const response = await apiClient.post('/api/admin/interviews/questions/save', payload, {
      timeout: 30000,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to save confirmed questions',
      status: error.response?.status,
    };
  }
};

export const getInstitutionQuestions = async (params = {}) => {
  try {
    const response = await apiClient.get('/api/admin/interviews/questions', {
      params,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to fetch question bank',
      status: error.response?.status,
    };
  }
};

export default apiClient;


