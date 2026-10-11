import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { initiateRegistration, resendRegistrationCode, completeRegistration } from '../api/client';
import {
  GraduationCap,
  ShieldCheck,
  Lock,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  Sparkles,
  Eye,
  EyeOff,
  Building2,
  Check,
  AlertTriangle
} from 'lucide-react';

export default function Register() {
  const [step, setStep] = useState(1);
  const [registrationNumber, setRegistrationNumber] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // Status & loading states
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [infoMessage, setInfoMessage] = useState(null);
  const [institutionalNotice, setInstitutionalNotice] = useState(null);

  // Resend cooldown timer (60 seconds)
  const [resendCooldown, setResendCooldown] = useState(0);
  const [demoOtpHint, setDemoOtpHint] = useState(null);

  const { setAuthSession } = useAuth();
  const navigate = useNavigate();

  // Cooldown countdown effect
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  // Password strength calculator
  const getPasswordStrength = (pwd) => {
    let score = 0;
    if (pwd.length >= 8) score++;
    if (pwd.length >= 12) score++;
    if (/[A-Z]/.test(pwd)) score++;
    if (/[0-9]/.test(pwd)) score++;
    if (/[^A-Za-z0-9]/.test(pwd)) score++;
    return score;
  };

  const strengthScore = getPasswordStrength(password);
  const strengthLabels = ['Too weak', 'Weak', 'Fair', 'Strong', 'Very strong'];
  const strengthColors = ['bg-rose-500', 'bg-amber-500', 'bg-yellow-400', 'bg-emerald-400', 'bg-emerald-500'];

  // Step 1: Initiate Registration
  const handleInitiate = async (e) => {
    e.preventDefault();
    setError(null);
    setInstitutionalNotice(null);

    const cleanRoll = registrationNumber.trim().toUpperCase();
    if (!cleanRoll) {
      setError('Please enter your VFSTR registration / roll number.');
      return;
    }

    setIsLoading(true);
    try {
      const result = await initiateRegistration(cleanRoll);
      if (result.success) {
        setInfoMessage(result.data.message || 'If eligible, a verification code has been dispatched to your official email on file.');
        if (result.data?.demo_otp_hint) {
          setDemoOtpHint(result.data.demo_otp_hint);
        }
        setResendCooldown(60);
        setStep(2);
      } else {
        if (result.status === 403) {
          setInstitutionalNotice(result.error);
        } else {
          setError(result.error || 'Unable to initiate registration. Please check your roll number.');
        }
      }
    } catch (err) {
      setError(err.message || 'Network error occurred while connecting to authentication service.');
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2: Handle Resend Code
  const handleResend = async () => {
    if (resendCooldown > 0 || isLoading) return;
    setError(null);
    setIsLoading(true);

    try {
      const result = await resendRegistrationCode(registrationNumber.trim().toUpperCase());
      if (result.success) {
        setInfoMessage('A fresh verification code has been dispatched to your university email.');
        if (result.data?.demo_otp_hint) {
          setDemoOtpHint(result.data.demo_otp_hint);
        }
        setResendCooldown(60);
      } else {
        setError(result.error || 'Failed to resend code. Please wait before trying again.');
      }
    } catch (err) {
      setError(err.message || 'Network error during resend request.');
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2 to Step 3 Transition
  const handleProceedToPassword = (e) => {
    e.preventDefault();
    setError(null);

    const cleanCode = verificationCode.trim().replace(/\D/g, '');
    if (cleanCode.length !== 6) {
      setError('Please enter the full 6-digit numeric verification code.');
      return;
    }

    setStep(3);
  };

  // Step 3: Complete Registration
  const handleComplete = async (e) => {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match. Please re-enter your chosen password.');
      return;
    }

    setIsLoading(true);
    try {
      const cleanRoll = registrationNumber.trim().toUpperCase();
      const cleanCode = verificationCode.trim().replace(/\D/g, '');

      const result = await completeRegistration(cleanRoll, cleanCode, password);
      if (result.success) {
        setAuthSession(result.data.access_token, result.data.user);
        navigate('/dashboard', { replace: true });
      } else {
        setError(result.error || 'Verification failed. Please check your code.');
        if (result.status === 400) {
          setStep(2);
        }
      }
    } catch (err) {
      setError(err.message || 'An unexpected error occurred during account creation.');
    } finally {
      setIsLoading(false);
    }
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
        {/* Back to Portal Login Link */}
        <div className="mb-4">
          <Link 
            to="/login"
            className="inline-flex items-center space-x-1.5 text-xs text-slate-400 hover:text-white transition group focus:outline-none focus:ring-1 focus:ring-purple-400 rounded"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition group-hover:-translate-x-0.5" />
            <span>Back to Portal Login</span>
          </Link>
        </div>

        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-gradient-to-tr from-purple-700 via-purple-600 to-indigo-500 shadow-xl shadow-purple-600/30 border border-purple-400/30 mb-3">
            <GraduationCap className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Student Self-Registration
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Adaptive Interview Intelligence • VFSTR Placement Portal
          </p>
        </div>

        {/* Three-step progress indicator */}
        <div className="flex items-center justify-between mb-6 px-3">
          {/* Step 1: Roll Lookup */}
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition duration-200 ${
              step === 1 
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/40 ring-4 ring-purple-600/20' 
                : step > 1 
                  ? 'bg-purple-700 text-white border border-purple-500/50' 
                  : 'bg-[#0f172a] text-slate-500 border border-slate-700/60'
            }`}>
              {step > 1 ? <Check className="w-4 h-4 text-purple-200 stroke-[2.5]" /> : '1'}
            </div>
            <span className={`text-[10px] mt-1.5 font-medium transition ${
              step >= 1 ? 'text-slate-200' : 'text-slate-500'
            }`}>
              Roll Lookup
            </span>
          </div>

          {/* Line 1 -> 2 */}
          <div className={`flex-1 h-0.5 mx-2.5 transition duration-200 ${
            step > 1 ? 'bg-purple-600' : 'bg-slate-800'
          }`} />

          {/* Step 2: OTP Code */}
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition duration-200 ${
              step === 2 
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/40 ring-4 ring-purple-600/20' 
                : step > 2 
                  ? 'bg-purple-700 text-white border border-purple-500/50' 
                  : 'bg-[#0f172a] text-slate-500 border border-slate-700/60'
            }`}>
              {step > 2 ? <Check className="w-4 h-4 text-purple-200 stroke-[2.5]" /> : '2'}
            </div>
            <span className={`text-[10px] mt-1.5 font-medium transition ${
              step >= 2 ? 'text-slate-200' : 'text-slate-500'
            }`}>
              OTP Code
            </span>
          </div>

          {/* Line 2 -> 3 */}
          <div className={`flex-1 h-0.5 mx-2.5 transition duration-200 ${
            step > 2 ? 'bg-purple-600' : 'bg-slate-800'
          }`} />

          {/* Step 3: Set Password */}
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition duration-200 ${
              step === 3 
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/40 ring-4 ring-purple-600/20' 
                : step > 3 
                  ? 'bg-purple-700 text-white border border-purple-500/50' 
                  : 'bg-[#0f172a] text-slate-500 border border-slate-700/60'
            }`}>
              3
            </div>
            <span className={`text-[10px] mt-1.5 font-medium transition ${
              step >= 3 ? 'text-slate-200' : 'text-slate-500'
            }`}>
              Set Password
            </span>
          </div>
        </div>

        {/* Registration Card (lighter navy background, subtle border, rounded-2xl, restrained shadow) */}
        <div className="w-full bg-[#0d1424] border border-slate-800/90 rounded-[18px] p-6 sm:p-7 shadow-2xl shadow-purple-950/20 relative">
          
          {/* Institutional Notice Alert (403 for unverified department addresses) */}
          {institutionalNotice && (
            <div className="mb-5 p-3.5 rounded-xl bg-amber-950/40 border border-amber-600/40 text-amber-200 text-xs">
              <div className="flex items-start space-x-2.5">
                <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-amber-300 mb-0.5">
                    Department Verification Required
                  </h4>
                  <p className="text-amber-200/90 leading-relaxed text-[11px]">
                    {institutionalNotice}
                  </p>
                  <div className="mt-2 text-[10px] text-amber-400/90 flex items-center space-x-1.5">
                    <Building2 className="w-3.5 h-3.5" />
                    <span>Contact VFSTR Placement Coordinator</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* General Error Banner */}
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-start space-x-2.5 text-xs text-rose-300 animate-fadeIn">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed text-[11px]">{error}</div>
            </div>
          )}

          {/* Info / Success Message Banner */}
          {infoMessage && step > 1 && (
            <div className="mb-5 p-3 rounded-xl bg-emerald-950/40 border border-emerald-800/50 flex items-start space-x-2.5 text-xs text-emerald-300 animate-fadeIn">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed text-[11px]">{infoMessage}</div>
            </div>
          )}

          {/* ================= STEP 1: ROLL NUMBER LOOKUP ================= */}
          {step === 1 && (
            <form onSubmit={handleInitiate} className="space-y-4">
              <div>
                <label 
                  htmlFor="reg-roll-input" 
                  className="block text-xs font-medium text-slate-300 mb-1.5"
                >
                  University Registration / Roll Number
                </label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <GraduationCap className="h-4 w-4 text-slate-400" />
                  </div>
                  <input
                    id="reg-roll-input"
                    type="text"
                    required
                    value={registrationNumber}
                    onChange={(e) => setRegistrationNumber(e.target.value.toUpperCase())}
                    placeholder="e.g., 241FA04001"
                    className="block w-full pl-10 pr-4 py-2.5 bg-[#090d1a] border border-slate-700/70 rounded-xl text-slate-100 placeholder-slate-500 text-sm font-mono tracking-wider focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition"
                  />
                </div>
                <p className="mt-2 text-[11px] text-slate-400 leading-relaxed">
                  Enter your official VFSTR roll number as printed on your University Identity Card.
                </p>
              </div>

              {/* Information Security Panel */}
              <div className="p-3.5 rounded-xl bg-[#090d1a]/80 border border-slate-800 text-xs text-slate-400 flex items-start space-x-2.5">
                <ShieldCheck className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
                <p className="leading-relaxed text-[11px] text-slate-400">
                  For your security, a single-use verification code will be dispatched to your approved email on the university batch roster.
                </p>
              </div>

              {/* Primary CTA */}
              <button
                id="reg-initiate-btn"
                type="submit"
                disabled={isLoading}
                className="w-full flex items-center justify-center py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 shadow-lg shadow-purple-600/30 transition duration-150 disabled:opacity-50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-400"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    <span>Verifying Roll Record...</span>
                  </>
                ) : (
                  <>
                    <span>Verify Eligibility & Send Code</span>
                    <ArrowRight className="w-4 h-4 ml-1.5" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* ================= STEP 2: VERIFICATION OTP CODE ================= */}
          {step === 2 && (
            <form onSubmit={handleProceedToPassword} className="space-y-4">
              {demoOtpHint && (
                <div className="p-3 rounded-xl bg-purple-950/60 border border-purple-500/40 text-xs text-purple-300 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Sparkles className="w-4 h-4 text-purple-400 shrink-0 animate-pulse" />
                    <span className="text-[11px]">Demo Mode OTP: <strong className="text-white font-mono tracking-widest text-xs">{demoOtpHint}</strong></span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setVerificationCode(demoOtpHint)}
                    className="px-2.5 py-1 bg-purple-600/50 hover:bg-purple-600/80 rounded text-[10px] font-semibold text-white border border-purple-400/50 transition cursor-pointer"
                  >
                    Auto-Fill
                  </button>
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label 
                    htmlFor="reg-code-input" 
                    className="block text-xs font-medium text-slate-300"
                  >
                    6-Digit Verification Code
                  </label>
                  <span className="text-[11px] text-purple-400 font-mono">
                    Roll: {registrationNumber}
                  </span>
                </div>
                
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Lock className="h-4 w-4" />
                  </div>
                  <input
                    id="reg-code-input"
                    type="text"
                    required
                    maxLength={6}
                    value={verificationCode}
                    onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="123456"
                    className="block w-full pl-10 pr-4 py-2.5 bg-[#090d1a] border border-slate-700/70 rounded-xl text-center text-slate-100 placeholder-slate-600 text-lg font-mono tracking-[0.5em] focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition"
                  />
                </div>
                <p className="mt-2 text-[11px] text-slate-400 leading-relaxed flex items-center justify-between">
                  <span>Valid for 10 minutes (3 attempts max).</span>
                  <span className="text-slate-500">Check spam folder.</span>
                </p>
              </div>

              {/* Resend Action Bar */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setStep(1);
                  }}
                  className="text-slate-400 hover:text-slate-200 transition text-[11px]"
                >
                  Change Roll Number
                </button>

                <button
                  id="reg-resend-btn"
                  type="button"
                  onClick={handleResend}
                  disabled={resendCooldown > 0 || isLoading}
                  className="inline-flex items-center space-x-1.5 text-purple-400 hover:text-purple-300 disabled:text-slate-500 transition text-[11px] font-medium"
                >
                  <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
                  <span>
                    {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend Code'}
                  </span>
                </button>
              </div>

              <button
                id="reg-verify-code-btn"
                type="submit"
                disabled={isLoading || verificationCode.length !== 6}
                className="w-full flex items-center justify-center py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 shadow-lg shadow-purple-600/30 transition duration-150 disabled:opacity-50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-400"
              >
                <span>Continue to Set Password</span>
                <ArrowRight className="w-4 h-4 ml-1.5" />
              </button>
            </form>
          )}

          {/* ================= STEP 3: PASSWORD SETUP & REGISTRATION ================= */}
          {step === 3 && (
            <form onSubmit={handleComplete} className="space-y-4">
              <div>
                <label 
                  htmlFor="reg-password-input" 
                  className="block text-xs font-medium text-slate-300 mb-1.5"
                >
                  Create Secure Password
                </label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Lock className="h-4 w-4" />
                  </div>
                  <input
                    id="reg-password-input"
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                    className="block w-full pl-10 pr-10 py-2.5 bg-[#090d1a] border border-slate-700/70 rounded-xl text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-200"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                {/* Password Strength Indicator */}
                {password.length > 0 && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between text-[11px] mb-1">
                      <span className="text-slate-400">Strength:</span>
                      <span className={`font-medium ${
                        strengthScore <= 2 ? 'text-amber-400' : 'text-emerald-400'
                      }`}>
                        {strengthLabels[strengthScore - 1] || 'Too weak'}
                      </span>
                    </div>
                    <div className="grid grid-cols-5 gap-1 h-1.5">
                      {[1, 2, 3, 4, 5].map((lvl) => (
                        <div
                          key={lvl}
                          className={`rounded-full transition-colors ${
                            lvl <= strengthScore ? strengthColors[strengthScore - 1] : 'bg-slate-800'
                          }`}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div>
                <label 
                  htmlFor="reg-confirm-password-input" 
                  className="block text-xs font-medium text-slate-300 mb-1.5"
                >
                  Confirm Password
                </label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Lock className="h-4 w-4" />
                  </div>
                  <input
                    id="reg-confirm-password-input"
                    type={showConfirmPassword ? 'text' : 'password'}
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Re-enter password"
                    className="block w-full pl-10 pr-10 py-2.5 bg-[#090d1a] border border-slate-700/70 rounded-xl text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-200"
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="text-slate-400 hover:text-slate-200 transition text-[11px]"
                >
                  Back to OTP
                </button>
              </div>

              <button
                id="reg-complete-btn"
                type="submit"
                disabled={isLoading || password.length < 8 || password !== confirmPassword}
                className="w-full flex items-center justify-center py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 shadow-lg shadow-purple-600/30 transition duration-150 disabled:opacity-50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-400"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    <span>Creating Account...</span>
                  </>
                ) : (
                  <>
                    <span>Complete Registration & Access Portal</span>
                    <Sparkles className="w-4 h-4 ml-1.5 text-purple-200" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* Divider and Footer: Already registered your VFSTR account? Sign In */}
          <div className="mt-6 pt-5 border-t border-slate-800/80 text-center text-xs text-slate-400">
            <span>Already registered your VFSTR account? </span>
            <Link to="/login" className="text-purple-400 hover:text-purple-300 font-semibold underline underline-offset-2">
              Sign In
            </Link>
          </div>
        </div>

        {/* Security Assurance Badge */}
        <div className="mt-5 text-center text-xs text-slate-500 flex items-center justify-center space-x-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-500" />
          <span className="text-[11px]">Atomic single-claim protection • Encrypted credentials</span>
        </div>
      </div>
    </div>
  );
}
