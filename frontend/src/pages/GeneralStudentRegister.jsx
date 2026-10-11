import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  getAllowedInstitutions,
  initiateGeneralRegistration,
  resendGeneralRegistrationCode,
  completeGeneralRegistration,
} from '../api/client';
import {
  GraduationCap,
  Lock,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  Eye,
  EyeOff,
  Building2,
  User,
  Phone,
  Mail,
  Hash,
} from 'lucide-react';

export default function GeneralStudentRegister() {
  const [step, setStep] = useState(1);

  // Form Fields
  const [fullName, setFullName] = useState('');
  const [collegeName, setCollegeName] = useState('');
  const [collegeRegNo, setCollegeRegNo] = useState('');
  const [email, setEmail] = useState('');
  const [contactNumber, setContactNumber] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // OTP Verification
  const [verificationCode, setVerificationCode] = useState('');

  // Partner Institutions
  const [allowedInstitutions, setAllowedInstitutions] = useState([]);
  const [institutionsLoading, setInstitutionsLoading] = useState(true);

  // Status & loading states
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [infoMessage, setInfoMessage] = useState(null);

  // Resend cooldown timer (60 seconds)
  const [resendCooldown, setResendCooldown] = useState(0);
  const [demoOtpHint, setDemoOtpHint] = useState(null);

  const { setAuthSession } = useAuth();
  const navigate = useNavigate();

  // Load allowed institutions on mount
  useEffect(() => {
    let isMounted = true;
    const fetchInstitutions = async () => {
      setInstitutionsLoading(true);
      const res = await getAllowedInstitutions();
      if (isMounted && res.success && res.data?.institutions) {
        setAllowedInstitutions(res.data.institutions);
        if (res.data.institutions.length > 0) {
          setCollegeName(res.data.institutions[0]);
        }
      }
      if (isMounted) setInstitutionsLoading(false);
    };
    fetchInstitutions();
    return () => {
      isMounted = false;
    };
  }, []);

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

    // Validation
    if (!fullName.trim() || fullName.trim().length < 2) {
      setError('Please enter your full legal name (at least 2 characters).');
      return;
    }
    if (!collegeName.trim()) {
      setError('Please select or specify your partner college/university.');
      return;
    }
    if (!collegeRegNo.trim()) {
      setError('Please enter your college registration or student ID number.');
      return;
    }
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('Please provide a valid email address.');
      return;
    }
    const cleanPhone = contactNumber.trim().replace(/\D/g, '');
    if (cleanPhone.length < 10) {
      setError('Please provide a valid 10-digit personal contact number.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }
    if (!(/[A-Za-z]/.test(password) && /[0-9]/.test(password))) {
      setError('Password must contain both letters and numbers.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match. Please re-enter.');
      return;
    }

    setIsLoading(true);
    try {
      const result = await initiateGeneralRegistration({
        fullName: fullName.trim(),
        collegeName: collegeName.trim(),
        collegeRegNo: collegeRegNo.trim().toUpperCase(),
        email: email.trim().toLowerCase(),
        contactNumber: contactNumber.trim(),
        password: password,
      });

      if (result.success) {
        setInfoMessage(result.data.message || 'Verification code dispatched to your email address.');
        if (result.data?.demo_otp_hint) {
          setDemoOtpHint(result.data.demo_otp_hint);
        }
        setResendCooldown(60);
        setStep(2);
      } else {
        setError(result.error || 'Unable to initiate registration. Please review the form.');
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
      const result = await resendGeneralRegistrationCode(email.trim().toLowerCase());
      if (result.success) {
        setInfoMessage('A fresh verification code has been dispatched to your email.');
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

  // Step 2: Complete Registration & Verification
  const handleComplete = async (e) => {
    e.preventDefault();
    setError(null);

    const cleanCode = verificationCode.trim().replace(/\D/g, '');
    if (cleanCode.length !== 6) {
      setError('Please enter the full 6-digit numeric verification code.');
      return;
    }

    setIsLoading(true);
    try {
      const result = await completeGeneralRegistration(email.trim().toLowerCase(), cleanCode);
      if (result.success) {
        setAuthSession(result.data.access_token, result.data.user);
        navigate('/dashboard', { replace: true });
      } else {
        setError(result.error || 'Verification code validation failed.');
      }
    } catch (err) {
      setError(err.message || 'Error occurred while finalizing registration.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col justify-center items-center py-12 px-4 sm:px-6 relative overflow-hidden">
      {/* Background Ambient Lighting */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div
          className="absolute top-[20%] left-[20%] w-[680px] h-[680px] rounded-full pointer-events-none"
          style={{
            background: 'radial-gradient(circle, rgba(6, 182, 212, 0.14) 0%, rgba(99, 102, 241, 0.06) 45%, rgba(3, 7, 18, 0) 70%)',
            filter: 'blur(75px)',
          }}
        />
        <div
          className="absolute bottom-[15%] right-[20%] w-[520px] h-[520px] rounded-full pointer-events-none"
          style={{
            background: 'radial-gradient(circle, rgba(99, 102, 241, 0.12) 0%, rgba(147, 51, 234, 0.05) 50%, rgba(3, 7, 18, 0) 75%)',
            filter: 'blur(65px)',
          }}
        />
      </div>

      <div className="relative z-10 w-full max-w-xl">
        {/* Navigation & Header */}
        <div className="mb-4 flex items-center justify-between">
          <Link
            to="/"
            className="inline-flex items-center space-x-1.5 text-xs text-slate-400 hover:text-white transition group focus:outline-none"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition group-hover:-translate-x-0.5" />
            <span>Back to Portal Home</span>
          </Link>

          <Link
            to="/students/login"
            className="text-xs text-cyan-400 hover:text-cyan-300 font-medium transition"
          >
            Already registered? Sign In
          </Link>
        </div>

        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-gradient-to-tr from-cyan-600 via-indigo-600 to-violet-600 shadow-xl shadow-cyan-500/20 border border-cyan-400/30 mb-3">
            <GraduationCap className="w-6 h-6 text-white" />
          </div>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-cyan-950/70 text-cyan-300 border border-cyan-800/60 mb-2">
            <Building2 className="w-3 h-3 text-cyan-400" />
            <span>Partner Colleges & Universities</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Student Registration
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
            Accredited partner campus access for adaptive placement interview simulations.
          </p>
        </div>

        {/* Step Progress Indicators */}
        <div className="flex items-center justify-center space-x-3 mb-6">
          <div className="flex items-center space-x-2">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition ${
                step >= 1 ? 'bg-cyan-500 text-slate-950 font-extrabold' : 'bg-slate-800 text-slate-400'
              }`}
            >
              1
            </span>
            <span className={`text-xs ${step >= 1 ? 'text-white font-medium' : 'text-slate-500'}`}>
              Candidate Details
            </span>
          </div>
          <span className="w-8 h-px bg-slate-800" />
          <div className="flex items-center space-x-2">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition ${
                step >= 2 ? 'bg-cyan-500 text-slate-950 font-extrabold' : 'bg-slate-800 text-slate-400'
              }`}
            >
              2
            </span>
            <span className={`text-xs ${step >= 2 ? 'text-white font-medium' : 'text-slate-500'}`}>
              Email Verification (OTP)
            </span>
          </div>
        </div>

        {/* Main Card */}
        <div className="bg-[#0b1222] border border-slate-800/90 rounded-2xl p-6 sm:p-8 shadow-2xl shadow-cyan-950/30 relative">
          {error && (
            <div className="mb-5 p-3.5 rounded-xl bg-rose-950/50 border border-rose-800/60 flex items-start space-x-2.5 text-xs text-rose-300">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed text-[11px]">{error}</div>
            </div>
          )}

          {infoMessage && (
            <div className="mb-5 p-3.5 rounded-xl bg-cyan-950/40 border border-cyan-800/50 flex items-start space-x-2.5 text-xs text-cyan-300">
              <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed text-[11px]">{infoMessage}</div>
            </div>
          )}

          {/* STEP 1: FORM DETAILS */}
          {step === 1 && (
            <form onSubmit={handleInitiate} className="space-y-4">
              {/* Full Name */}
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Full Legal Name
                </label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <User className="h-4 w-4" />
                  </div>
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Ramesh Kumar"
                    className="block w-full pl-10 pr-3.5 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition"
                  />
                </div>
              </div>

              {/* College / University Name */}
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  College / University Name
                </label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Building2 className="h-4 w-4" />
                  </div>
                  {institutionsLoading ? (
                    <div className="pl-10 pr-3.5 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-400 flex items-center">
                      <Loader2 className="w-3.5 h-3.5 animate-spin mr-2" />
                      Loading partner institutions...
                    </div>
                  ) : (
                    <select
                      value={collegeName}
                      onChange={(e) => setCollegeName(e.target.value)}
                      className="block w-full pl-10 pr-8 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition"
                    >
                      {allowedInstitutions.map((inst) => (
                        <option key={inst} value={inst}>
                          {inst}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                <p className="text-[10px] text-slate-500 mt-1">
                  Registration permitted exclusively for platform-partnered accredited institutions.
                </p>
              </div>

              {/* College Reg / Student ID & Phone in 2-col on desktop */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    College Registration / Student ID
                  </label>
                  <div className="relative rounded-xl shadow-sm">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                      <Hash className="h-4 w-4" />
                    </div>
                    <input
                      type="text"
                      required
                      value={collegeRegNo}
                      onChange={(e) => setCollegeRegNo(e.target.value)}
                      placeholder="e.g. 211VIIT0401"
                      className="block w-full pl-10 pr-3.5 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 uppercase transition font-mono"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Personal Contact Number
                  </label>
                  <div className="relative rounded-xl shadow-sm">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                      <Phone className="h-4 w-4" />
                    </div>
                    <input
                      type="tel"
                      required
                      value={contactNumber}
                      onChange={(e) => setContactNumber(e.target.value)}
                      placeholder="e.g. 9876543210"
                      className="block w-full pl-10 pr-3.5 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition"
                    />
                  </div>
                </div>
              </div>

              {/* Email Address */}
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Email Address
                </label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                    <Mail className="h-4 w-4" />
                  </div>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="e.g. student@viit.ac.in"
                    className="block w-full pl-10 pr-3.5 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition"
                  />
                </div>
                <p className="text-[10px] text-slate-500 mt-1">
                  We will send a 6-digit verification code to verify ownership of this email.
                </p>
              </div>

              {/* Password Fields in 2-col on desktop */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Password
                  </label>
                  <div className="relative rounded-xl shadow-sm">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                      <Lock className="h-4 w-4" />
                    </div>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Min. 8 characters"
                      className="block w-full pl-10 pr-10 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-200 transition"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Confirm Password
                  </label>
                  <div className="relative rounded-xl shadow-sm">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                      <Lock className="h-4 w-4" />
                    </div>
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Repeat password"
                      className="block w-full pl-10 pr-10 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-200 transition"
                    >
                      {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Password strength meter */}
              {password && (
                <div className="space-y-1.5 pt-1">
                  <div className="flex justify-between items-center text-[10px]">
                    <span className="text-slate-400">Security strength</span>
                    <span className="text-slate-300 font-medium">
                      {strengthLabels[strengthScore - 1] || 'Too weak'}
                    </span>
                  </div>
                  <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden flex gap-1">
                    {[1, 2, 3, 4, 5].map((lvl) => (
                      <div
                        key={lvl}
                        className={`h-full flex-1 rounded-full transition-all duration-300 ${
                          strengthScore >= lvl ? strengthColors[strengthScore - 1] : 'bg-slate-800'
                        }`}
                      />
                    ))}
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading}
                className="w-full mt-2 inline-flex items-center justify-center space-x-2 px-5 py-3 rounded-xl bg-gradient-to-r from-cyan-600 via-indigo-600 to-violet-600 text-white font-semibold text-xs shadow-lg shadow-cyan-600/20 hover:shadow-cyan-600/35 hover:opacity-95 transition disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-1" />
                    <span>Processing & Sending Code...</span>
                  </>
                ) : (
                  <>
                    <span>Proceed to Email Verification</span>
                    <ArrowRight className="w-4 h-4 ml-1" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* STEP 2: OTP VERIFICATION */}
          {step === 2 && (
            <form onSubmit={handleComplete} className="space-y-5">
              <div className="text-center pb-2">
                <div className="w-12 h-12 rounded-2xl bg-cyan-950/70 border border-cyan-800/60 text-cyan-300 flex items-center justify-center mx-auto mb-3">
                  <Mail className="w-6 h-6" />
                </div>
                <h3 className="text-sm font-bold text-white">Enter Verification Code</h3>
                <p className="text-xs text-slate-400 mt-1">
                  A 6-digit code was sent to <strong className="text-cyan-300">{email}</strong>
                </p>
              </div>

              {/* Demo Mode OTP Hint */}
              {demoOtpHint && (
                <div className="p-3 rounded-xl bg-cyan-950/50 border border-cyan-800/60 text-xs text-cyan-300 flex items-center justify-between">
                  <span className="text-[11px]">Development Demo OTP:</span>
                  <span className="font-mono font-bold tracking-widest text-cyan-200">{demoOtpHint}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-300 text-center mb-2">
                  6-Digit OTP Code
                </label>
                <input
                  type="text"
                  maxLength={6}
                  required
                  autoFocus
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="••••••"
                  className="block w-48 mx-auto text-center tracking-[0.5em] font-mono text-xl py-3 bg-slate-900 border border-slate-700 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-cyan-500 transition"
                />
              </div>

              <div className="flex items-center justify-center space-x-2 text-xs">
                <span className="text-slate-400">Didn't receive the code?</span>
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resendCooldown > 0 || isLoading}
                  className="text-cyan-400 hover:text-cyan-300 font-semibold disabled:text-slate-600 transition flex items-center space-x-1"
                >
                  <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
                  <span>
                    {resendCooldown > 0 ? `Resend code (${resendCooldown}s)` : 'Resend Code'}
                  </span>
                </button>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="w-1/3 py-2.5 px-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 font-medium text-xs transition"
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={isLoading || verificationCode.length !== 6}
                  className="w-2/3 py-2.5 px-3 rounded-xl bg-gradient-to-r from-cyan-600 via-indigo-600 to-violet-600 text-white font-semibold text-xs shadow-lg shadow-cyan-600/20 hover:opacity-95 transition disabled:opacity-50 flex items-center justify-center space-x-1.5"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin mr-1" />
                      <span>Verifying...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Verify & Complete</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* Footer note & redirection */}
          <div className="mt-6 pt-5 border-t border-slate-800/80 space-y-2 text-xs text-slate-400">
            <div className="flex items-center justify-between">
              <span>Already registered your account?</span>
              <Link
                to="/students/login"
                className="text-cyan-400 hover:text-cyan-300 font-semibold underline underline-offset-2 transition"
              >
                Sign In
              </Link>
            </div>
            <div className="flex items-center justify-between pt-1 text-[11px] text-slate-500">
              <span>Are you a VFSTR University student?</span>
              <Link
                to="/vfstr/register"
                className="text-purple-400 hover:text-purple-300 font-medium transition flex items-center space-x-1"
              >
                <span>Go to VFSTR Verification</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
