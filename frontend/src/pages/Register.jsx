import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { registerVfstrStudent } from '../api/client';
import {
  GraduationCap,
  Phone,
  ShieldCheck,
  ArrowRight,
  ArrowLeft,
  AlertCircle,
  Loader2,
  Building2,
  AlertTriangle,
} from 'lucide-react';

export default function Register() {
  const [registrationNumber, setRegistrationNumber] = useState('');
  const [contactNumber, setContactNumber] = useState('');

  // Status & loading states
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [institutionalNotice, setInstitutionalNotice] = useState(null);

  const { setAuthSession } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setInstitutionalNotice(null);

    const cleanRoll = registrationNumber.trim().toUpperCase();
    const cleanContact = contactNumber.trim();

    if (!cleanRoll) {
      setError('Please enter your VFSTR registration / roll number.');
      return;
    }

    if (!cleanContact || cleanContact.replace(/\D/g, '').length < 10) {
      setError('Please provide a valid personal contact number with at least 10 digits.');
      return;
    }

    setIsLoading(true);
    try {
      const result = await registerVfstrStudent({
        registrationNumber: cleanRoll,
        contactNumber: cleanContact,
      });

      if (result.success && result.data?.access_token) {
        setAuthSession(result.data.access_token, result.data.user);
        navigate('/dashboard');
      } else {
        if (result.status === 403) {
          setInstitutionalNotice(result.error);
        } else {
          setError(result.error || 'Registration verification failed. Please check your roll number.');
        }
      }
    } catch (err) {
      setError(err.message || 'Network error occurred while connecting to authentication service.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col justify-center items-center py-10 px-4 sm:px-6 relative overflow-hidden select-none sm:select-auto">
      {/* Background Ambient Glow */}
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

      {/* Main Content Column */}
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
          <div className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-bold bg-purple-950/80 text-purple-300 border border-purple-800/50 mb-2">
            <span>VFSTR Deemed to be University</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Student Interview Verification
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Adaptive Interview Intelligence • Instant Eligibility Access
          </p>
        </div>

        {/* Verification Card */}
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

          {/* Simplified Registration Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Registration Number Field */}
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
                  autoFocus
                  value={registrationNumber}
                  onChange={(e) => setRegistrationNumber(e.target.value.toUpperCase())}
                  placeholder="e.g., 241FA04035"
                  className="block w-full pl-10 pr-4 py-2.5 bg-[#090d1a] border border-slate-700/70 rounded-xl text-slate-100 placeholder-slate-500 text-sm font-mono tracking-wider focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition"
                />
              </div>
              <p className="mt-1.5 text-[11px] text-slate-400 leading-relaxed">
                As printed on your official VFSTR Student ID card.
              </p>
            </div>

            {/* Contact Number Field */}
            <div>
              <label
                htmlFor="reg-contact-input"
                className="block text-xs font-medium text-slate-300 mb-1.5"
              >
                Personal Contact Number
              </label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Phone className="h-4 w-4 text-slate-400" />
                </div>
                <input
                  id="reg-contact-input"
                  type="tel"
                  required
                  value={contactNumber}
                  onChange={(e) => setContactNumber(e.target.value)}
                  placeholder="e.g., 9876543210"
                  className="block w-full pl-10 pr-4 py-2.5 bg-[#090d1a] border border-slate-700/70 rounded-xl text-slate-100 placeholder-slate-500 text-sm font-mono tracking-wider focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition"
                />
              </div>
              <p className="mt-1.5 text-[11px] text-slate-400 leading-relaxed">
                Used to link your student profile and secure your interview records.
              </p>
            </div>

            {/* Information Security Panel */}
            <div className="p-3.5 rounded-xl bg-[#090d1a]/80 border border-slate-800 text-xs text-slate-400 flex items-start space-x-2.5">
              <ShieldCheck className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
              <p className="leading-relaxed text-[11px] text-slate-400">
                Instant eligibility verification against the official university roster. Access granted immediately with zero email OTP wait.
              </p>
            </div>

            {/* Submit Button */}
            <button
              id="reg-verify-enter-btn"
              type="submit"
              disabled={isLoading || !registrationNumber.trim() || !contactNumber.trim()}
              className="w-full flex items-center justify-center py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 shadow-lg shadow-purple-600/30 transition duration-150 disabled:opacity-50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-400"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  <span>Verifying Eligibility...</span>
                </>
              ) : (
                <>
                  <span>Verify Eligibility & Enter Interviews</span>
                  <ArrowRight className="w-4 h-4 ml-1.5" />
                </>
              )}
            </button>
          </form>

          {/* Footer Navigation Links */}
          <div className="mt-6 pt-5 border-t border-slate-800/80 space-y-2 text-center text-xs text-slate-400">
            <div>
              <span>Student from another college? </span>
              <Link to="/students/register" className="text-cyan-400 hover:text-cyan-300 font-medium">
                Partner College Registration
              </Link>
            </div>
            <div className="text-[11px] text-slate-500 pt-1">
              <span>Faculty or Administrator? </span>
              <Link to="/login" className="text-purple-400 hover:text-purple-300 font-medium">
                Institution Portal
              </Link>
            </div>
          </div>
        </div>

        {/* Security Assurance Badge */}
        <div className="mt-5 text-center text-xs text-slate-500 flex items-center justify-center space-x-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-500" />
          <span className="text-[11px]">Official VFSTR Eligibility Registry Integration</span>
        </div>
      </div>
    </div>
  );
}
