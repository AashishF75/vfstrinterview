import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Lock,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  Loader2,
  ArrowLeft,
  ArrowRight,
  GraduationCap,
  Sparkles,
} from 'lucide-react';

export default function VfstrStudentLogin() {
  const [emailOrRoll, setEmailOrRoll] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationErrors, setValidationErrors] = useState({});

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/dashboard';

  const validate = () => {
    const errs = {};
    const input = emailOrRoll.trim();
    if (!input) {
      errs.emailOrRoll = 'University email or roll number is required';
    }

    if (!password) {
      errs.password = 'Password is required';
    } else if (password.length < 6) {
      errs.password = 'Password must be at least 6 characters';
    }

    setValidationErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!validate()) return;

    const identifier = emailOrRoll.trim();

    setIsSubmitting(true);
    try {
      const result = await login(identifier, password);
      if (result.success) {
        navigate(from, { replace: true });
      } else {
        setError(result.error || 'Authentication failed. Please verify credentials.');
      }
    } catch (err) {
      setError(err.message || 'An unexpected error occurred during login');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col justify-center items-center py-10 px-4 sm:px-6 relative overflow-hidden select-none sm:select-auto">
      {/* Background Ambient Glow - VFSTR Purple/Indigo Theme */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0" aria-hidden="true">
        <div
          className="absolute top-1/2 left-[36%] -translate-x-1/2 -translate-y-1/2 w-[720px] h-[720px] rounded-full pointer-events-none"
          style={{
            background: 'radial-gradient(circle, rgba(147, 51, 234, 0.18) 0%, rgba(99, 102, 241, 0.08) 45%, rgba(3, 7, 18, 0) 72%)',
            filter: 'blur(70px)',
          }}
        />
        <div
          className="absolute top-[42%] left-[28%] -translate-x-1/2 -translate-y-1/2 w-[460px] h-[460px] rounded-full pointer-events-none"
          style={{
            background: 'radial-gradient(circle, rgba(168, 85, 247, 0.12) 0%, rgba(79, 70, 229, 0.04) 50%, rgba(3, 7, 18, 0) 75%)',
            filter: 'blur(55px)',
          }}
        />
      </div>

      <div className="relative z-10 w-full max-w-[420px]">
        {/* Back Link */}
        <div className="mb-4">
          <Link
            to="/"
            className="inline-flex items-center space-x-1.5 text-xs text-slate-400 hover:text-white transition group focus:outline-none"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition group-hover:-translate-x-0.5" />
            <span>Back to Portal Home</span>
          </Link>
        </div>

        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-gradient-to-tr from-purple-700 via-purple-600 to-indigo-500 shadow-xl shadow-purple-600/30 border border-purple-400/30 mb-3">
            <GraduationCap className="w-6 h-6 text-white" />
          </div>
          <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-800/50 mb-2">
            <span>VFSTR Deemed University</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            VFSTR Student Login
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Vignan's Foundation for Science, Technology & Research
          </p>
        </div>

        {/* Login Card */}
        <div className="w-full bg-[#0d1424] border border-slate-800/90 rounded-[18px] p-6 sm:p-7 shadow-2xl shadow-purple-950/20 relative">
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-start space-x-2.5 text-xs text-rose-300">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed text-[11px]">{error}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email / Roll Field */}
            <div>
              <label
                htmlFor="vfstr-login-identifier"
                className="block text-xs font-medium text-slate-300 mb-1.5"
              >
                University Email or Roll Number
              </label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Mail className="h-4 w-4" />
                </div>
                <input
                  id="vfstr-login-identifier"
                  type="text"
                  value={emailOrRoll}
                  onChange={(e) => {
                    setEmailOrRoll(e.target.value);
                    if (validationErrors.emailOrRoll) {
                      setValidationErrors((prev) => ({ ...prev, emailOrRoll: null }));
                    }
                  }}
                  placeholder="211FA04001 or roll@vfstr.ac.in"
                  className="block w-full pl-10 pr-3.5 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition font-mono"
                />
              </div>
              {validationErrors.emailOrRoll && (
                <p className="mt-1 text-[11px] text-rose-400">{validationErrors.emailOrRoll}</p>
              )}
            </div>

            {/* Password Field */}
            <div>
              <label
                htmlFor="vfstr-login-password"
                className="block text-xs font-medium text-slate-300 mb-1.5"
              >
                Password
              </label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Lock className="h-4 w-4" />
                </div>
                <input
                  id="vfstr-login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (validationErrors.password) {
                      setValidationErrors((prev) => ({ ...prev, password: null }));
                    }
                  }}
                  placeholder="••••••••"
                  className="block w-full pl-10 pr-10 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-200 transition"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {validationErrors.password && (
                <p className="mt-1 text-[11px] text-rose-400">{validationErrors.password}</p>
              )}
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full inline-flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-purple-700 via-purple-600 to-indigo-600 hover:from-purple-600 hover:to-indigo-500 text-white font-medium text-xs shadow-md shadow-purple-600/30 transition disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-1" />
                  <span>Verifying Credentials...</span>
                </>
              ) : (
                <>
                  <Lock className="w-3.5 h-3.5" />
                  <span>VFSTR Sign In</span>
                  <ArrowRight className="w-3.5 h-3.5 ml-0.5" />
                </>
              )}
            </button>
          </form>

          {/* Action Links */}
          <div className="mt-6 pt-5 border-t border-slate-800/80 space-y-2.5 text-xs text-slate-400">
            <div className="flex items-center justify-between">
              <span>First time registering?</span>
              <Link
                to="/vfstr/register"
                className="text-purple-400 hover:text-purple-300 font-semibold transition"
              >
                Claim Eligibility
              </Link>
            </div>

            <div className="flex items-center justify-between pt-1">
              <span>Not from VFSTR?</span>
              <Link
                to="/students/login"
                className="text-cyan-400 hover:text-cyan-300 font-medium transition"
              >
                Partner Institutions Login
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
