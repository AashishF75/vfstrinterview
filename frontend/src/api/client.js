import axios from 'axios';

// Create configured Axios instance
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 10000,
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

// Response interceptor to handle authorization errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid
      sessionStorage.removeItem('vfstr_access_token');
      sessionStorage.removeItem('vfstr_user_cache');
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
      error: error.response?.data?.detail || error.message || 'Registration initiation failed',
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
      error: error.response?.data?.detail || error.message || 'Resend code failed',
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
      error: error.response?.data?.detail || error.message || 'Registration failed',
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

export const searchEligibleCandidates = async ({ interviewId, section, search, limit = 300 } = {}) => {
  try {
    const params = new URLSearchParams();
    if (interviewId) params.append('interview_id', interviewId);
    if (section && section !== 'ALL') params.append('section', section);
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

export const submitInterviewAnswer = async (sessionId, answerText) => {
  try {
    const response = await apiClient.post(`/api/interview-rooms/sessions/${sessionId}/submit-answer`, {
      answer_text: answerText,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to submit answer',
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
  try {
    const response = await apiClient.get(`/api/interview-rooms/sessions/${sessionId}/proctoring-events`);
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message || 'Failed to retrieve proctoring timeline',
      status: error.response?.status,
    };
  }
};

export const updateSessionProctoringReview = async (sessionId, reviewStatus, reviewNotes) => {
  try {
    const response = await apiClient.patch(`/api/admin/interviews/sessions/${sessionId}/proctoring-review`, {
      review_status: reviewStatus,
      review_notes: reviewNotes,
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

export default apiClient;


