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
  ShieldCheck,
  GraduationCap
} from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
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
    if (!email) {
      errs.email = 'Email address is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errs.email = 'Please enter a valid email address';
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

    setIsSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.success) {
        // Direct admin to /admin or student/faculty to /dashboard
        if (['platform_admin', 'university_admin'].includes(result.user.role)) {
          navigate(from === '/dashboard' ? '/admin' : from, { replace: true });
        } else {
          navigate(from, { replace: true });
        }
      } else {
        setError(result.error || 'Authentication failed. Please verify credentials.');
      }
    } catch (err) {
      setError(err.message || 'An unexpected error occurred during login');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickFill = (demoEmail, demoPass) => {
    setEmail(demoEmail);
    setPassword(demoPass);
    setError(null);
    setValidationErrors({});
  };

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col justify-center items-center py-10 px-4 sm:px-6 relative overflow-hidden select-none sm:select-auto">
      {/* Background Ambient Glow - subtle purple radial glow strongest near center-left, smoothly fading outward */}
      <div 
        className="fixed inset-0 pointer-events-none overflow-hidden z-0"
        aria-hidden="true"
      >
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

      {/* Main Content Column (responsive max-width ~420px) */}
      <div className="relative z-10 w-full max-w-[420px]">
        {/* Back Link */}
        <div className="mb-4">
          <Link 
            to="/"
            className="inline-flex items-center space-x-1.5 text-xs text-slate-400 hover:text-white transition group focus:outline-none focus:ring-1 focus:ring-purple-400 rounded"
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
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Welcome Back
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Adaptive Interview Intelligence • VFSTR Placement Portal
          </p>
        </div>

        {/* Login Card */}
        <div className="w-full bg-[#0d1424] border border-slate-800/90 rounded-[18px] p-6 sm:p-7 shadow-2xl shadow-purple-950/20 relative">
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-start space-x-2.5 text-xs text-rose-300 animate-fadeIn">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed text-[11px]">{error}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email Field */}
            <div>
              <label 
                htmlFor="login-email"
                className="block text-xs font-medium text-slate-300 mb-1.5"
              >
                University Email Address
              </label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Mail className="h-4 w-4 text-slate-400" />
                </div>
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (validationErrors.email) setValidationErrors(prev => ({ ...prev, email: null }));
                  }}
                  placeholder="student@vfstr.ac.in"
                  className={`block w-full pl-10 pr-4 py-2.5 bg-[#090d1a] border ${
                    validationErrors.email ? 'border-rose-500 ring-1 ring-rose-500' : 'border-slate-700/70'
                  } rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition`}
                />
              </div>
              {validationErrors.email && (
                <p className="mt-1.5 text-[11px] text-rose-400">{validationErrors.email}</p>
              )}
            </div>

            {/* Password Field */}
            <div>
              <label 
                htmlFor="login-password"
                className="block text-xs font-medium text-slate-300 mb-1.5"
              >
                Password
              </label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Lock className="h-4 w-4 text-slate-400" />
                </div>
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (validationErrors.password) setValidationErrors(prev => ({ ...prev, password: null }));
                  }}
                  placeholder="••••••••••••"
                  className={`block w-full pl-10 pr-10 py-2.5 bg-[#090d1a] border ${
                    validationErrors.password ? 'border-rose-500 ring-1 ring-rose-500' : 'border-slate-700/70'
                  } rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-200 transition"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {validationErrors.password && (
                <p className="mt-1.5 text-[11px] text-rose-400">{validationErrors.password}</p>
              )}
            </div>

            {/* Primary Submit Button */}
            <button
              id="login-submit-button"
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 shadow-lg shadow-purple-600/30 transition duration-150 disabled:opacity-50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-400"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  <span>Verifying Credentials...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4 ml-1.5" />
                </>
              )}
            </button>
          </form>

          {/* Student Registration Callout / Divider */}
          <div className="mt-6 pt-5 border-t border-slate-800/80 text-center text-xs text-slate-400">
            <span>New to the placement portal? </span>
            <Link 
              id="login-register-link"
              to="/register" 
              className="text-purple-400 hover:text-purple-300 font-semibold underline underline-offset-2 transition"
            >
              Student Self-Registration
            </Link>
          </div>

          {/* Quick Development Demo Credentials Helper - Excluded from Production Bundles */}
          {import.meta.env.DEV && (
            <div className="mt-5 pt-4 border-t border-slate-800/80">
              <div className="flex items-center space-x-1.5 text-[10px] font-semibold text-purple-400 uppercase tracking-wider mb-2">
                <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
                <span>Development Quick-Fill Accounts</span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => handleQuickFill('faculty@vfstr.ac.in', 'FacultyPass2026!')}
                  className="p-2 rounded-lg bg-[#090d1a] hover:bg-[#0c1222] border border-slate-800 hover:border-purple-500/50 text-left transition text-xs cursor-pointer"
                >
                  <div className="font-semibold text-purple-300 text-[11px]">Faculty Demo</div>
                  <div className="text-[10px] text-slate-500 truncate">faculty@vfstr.ac.in</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleQuickFill('student@vfstr.ac.in', 'StudentPass2026!')}
                  className="p-2 rounded-lg bg-[#090d1a] hover:bg-[#0c1222] border border-slate-800 hover:border-purple-500/50 text-left transition text-xs cursor-pointer"
                >
                  <div className="font-semibold text-emerald-300 text-[11px]">Student Demo</div>
                  <div className="text-[10px] text-slate-500 truncate">student@vfstr.ac.in</div>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Security Note Footer */}
        <div className="mt-5 text-center text-xs text-slate-500 flex items-center justify-center space-x-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-500" />
          <span className="text-[11px]">Secured with bcrypt password hashing & JWT role authorization</span>
        </div>
      </div>
    </div>
  );
}
