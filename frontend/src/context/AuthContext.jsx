import React, { createContext, useContext, useState, useEffect } from 'react';
import { loginUser, logoutUser, getCurrentUser } from '../api/client';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => sessionStorage.getItem('vfstr_access_token'));
  const [loading, setLoading] = useState(true);

  // Safely restore session on mount by checking token against /api/auth/me
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = sessionStorage.getItem('vfstr_access_token');
      if (!storedToken) {
        setUser(null);
        setLoading(false);
        return;
      }

      const result = await getCurrentUser();
      if (result.success) {
        setUser(result.data);
        setToken(storedToken);
      } else {
        // Token expired or invalid
        sessionStorage.removeItem('vfstr_access_token');
        setUser(null);
        setToken(null);
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const login = async (email, password) => {
    const result = await loginUser(email, password);
    if (result.success) {
      const accessToken = result.data.access_token;
      const userData = result.data.user;
      sessionStorage.setItem('vfstr_access_token', accessToken);
      setToken(accessToken);
      setUser(userData);
      return { success: true, user: userData };
    }
    return { success: false, error: result.error, status: result.status };
  };

  const logout = async () => {
    try {
      await logoutUser();
    } catch {
      // Ignore network errors during logout
    } finally {
      sessionStorage.removeItem('vfstr_access_token');
      setToken(null);
      setUser(null);
    }
  };

  const setAuthSession = (accessToken, userData) => {
    sessionStorage.setItem('vfstr_access_token', accessToken);
    setToken(accessToken);
    setUser(userData);
  };

  const hasRole = (allowedRoles) => {
    if (!user || !user.role) return false;
    if (Array.isArray(allowedRoles)) {
      return allowedRoles.includes(user.role);
    }
    return user.role === allowedRoles;
  };

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    hasRole,
    setAuthSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
