import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthSession, useRegisterMutation } from '@/features/auth/queries';
import { Button, Input, Card, CardHeader, CardTitle, CardContent } from '@/components/common';
import { useToastStore } from '@/stores/useToastStore';
import { APP_NAME } from '@/constants';

export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [firmName, setFirmName] = useState('');
  const [mounted, setMounted] = useState(false);
  const { isAuthenticated } = useAuthSession();
  const registerMutation = useRegisterMutation();
  const addToast = useToastStore((s) => s.addToast);
  const hasToasted = useRef(false);
  const error = registerMutation.error instanceof Error ? registerMutation.error.message : null;
  const submittedEmail = registerMutation.data?.email || null;

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    if (submittedEmail && !hasToasted.current) {
      hasToasted.current = true;
      addToast(
        `Confirmation email sent to ${submittedEmail}.`,
        'success',
      );
    }
  }, [submittedEmail, addToast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    await registerMutation
      .mutateAsync({ email, password, firstName, lastName, firmName })
      .catch(() => undefined);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-auth-bg-from via-auth-bg-via to-auth-bg-to px-4 py-4 relative overflow-hidden">
      {/* Animated background blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-auth-blob-purple rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-blob"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-auth-blob-indigo rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-blob animation-delay-2000"></div>
        <div className="absolute top-40 left-40 w-80 h-80 bg-auth-blob-pink rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-blob animation-delay-4000"></div>
      </div>

      <Card
        className={`w-full max-w-md relative z-10 backdrop-blur-sm bg-auth-card shadow-2xl transition-all duration-700 ${
          mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
        }`}
      >
        <CardHeader className="text-center space-y-4 pb-6">
          {/* Logo */}
          <div className="relative">
            <div className={`w-20 h-20 rounded-2xl flex items-center justify-center mx-auto transform transition-all duration-500 hover:scale-110 hover:rotate-3 ${
              mounted ? 'opacity-100 scale-100 rotate-0' : 'opacity-0 scale-50 rotate-12'
            }`}>
              <img
                src="/logo.png"
                alt="Logo"
                className="w-20 h-20 object-contain logo-on-dark"
              />
            </div>
          </div>

          <div className={`transition-all duration-500 delay-100 ${
            mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
          }`}>
            <CardTitle className="text-3xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
              {APP_NAME}
            </CardTitle>
            <div className="h-1 w-16 bg-gradient-to-r from-indigo-600 to-purple-600 mx-auto mt-2 rounded-full"></div>
          </div>

          <p className={`text-auth-text text-sm sm:text-base transition-all duration-500 delay-200 ${
            mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
          }`}>
            {submittedEmail
              ? 'Almost there — confirm your email to start onboarding.'
              : 'Create your account to get started.'}
          </p>
        </CardHeader>

        <CardContent>
          {submittedEmail ? (
            <div className="space-y-6 text-center animate-slide-down">
              <div className="mx-auto w-16 h-16 rounded-full bg-auth-blob-indigo/30 flex items-center justify-center">
                <svg className="w-8 h-8 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8m-2 11H5a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h3 className="text-xl font-semibold text-auth-text">Check your inbox</h3>
                <p className="text-sm text-auth-text mt-2">
                  Open the confirmation link we just emailed you to activate your account.
                </p>
              </div>
              <Link
                to="/login"
                className="group inline-flex items-center justify-center gap-1.5 text-sm font-semibold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent hover:from-indigo-700 hover:to-purple-700 transition-all duration-200"
              >
                <svg
                  className="w-4 h-4 text-indigo-600 transition-transform duration-200 group-hover:-translate-x-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  strokeWidth={2.5}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
            <form onSubmit={handleSubmit} className="space-y-5" autoComplete="off">
              <div>
                <Input
                  type="text"
                  label="Firm Name"
                  placeholder="Acme Law Group"
                  value={firmName}
                  onChange={(e) => setFirmName(e.target.value)}
                  required
                  autoFocus
                  autoComplete="off"
                  name="register-firm-name"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Input
                    type="text"
                    label="First Name"
                    placeholder="John"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    required
                    autoComplete="off"
                    name="register-first-name"
                  />
                </div>
                <div>
                  <Input
                    type="text"
                    label="Last Name"
                    placeholder="Doe"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    required
                    autoComplete="off"
                    name="register-last-name"
                  />
                </div>
              </div>

              <div>
                <Input
                  type="email"
                  label="Email Address"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="off"
                  name="register-email"
                />
              </div>

              <div>
                <Input
                  type="password"
                  label="Password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  autoComplete="new-password"
                  name="register-password"
                />
              </div>

              {error && (
                <div className="bg-auth-error-bg border border-auth-error-border text-auth-error-text px-4 py-3 rounded-xl animate-slide-down shadow-sm">
                  <div className="flex items-start">
                    <svg className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    <span className="text-sm">{error}</span>
                  </div>
                </div>
              )}

              <Button
                type="submit"
                className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 transform transition-all duration-300 hover:scale-[1.02] hover:shadow-xl text-base sm:text-lg py-3 rounded-xl font-semibold"
                isLoading={registerMutation.isPending}
              >
                <span className="flex items-center justify-center">
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
                  </svg>
                  Create Account
                </span>
              </Button>
            </form>

            <div className="mt-6 pt-6 border-t border-auth-divider">
              <div className="text-center">
                <p className="text-sm text-auth-text">
                  Already have an account?{' '}
                  <Link
                    to="/login"
                    className="font-semibold text-auth-link hover:text-auth-link-hover transition-all duration-300 hover:underline cursor-pointer transform hover:scale-105 inline-block"
                  >
                    ← Sign in
                  </Link>
                </p>
              </div>
            </div>

            <div className="mt-6 text-center">
              <p className="text-xs text-auth-muted">
                By continuing, you agree to our Terms of Service and Privacy Policy
              </p>
            </div>
            </>
          )}
        </CardContent>
      </Card>

      <style>{`
        @keyframes blob {
          0% { transform: translate(0px, 0px) scale(1); }
          33% { transform: translate(30px, -50px) scale(1.1); }
          66% { transform: translate(-20px, 20px) scale(0.9); }
          100% { transform: translate(0px, 0px) scale(1); }
        }

        .animate-blob {
          animation: blob 7s infinite;
        }

        .animation-delay-2000 {
          animation-delay: 2s;
        }

        .animation-delay-4000 {
          animation-delay: 4s;
        }

        @keyframes ping-slow {
          75%, 100% {
            transform: scale(1.5);
            opacity: 0;
          }
        }

        .animate-ping-slow {
          animation: ping-slow 3s cubic-bezier(0, 0, 0.2, 1) infinite;
        }

        @keyframes slide-down {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-slide-down {
          animation: slide-down 0.3s ease-out;
        }
      `}</style>
    </div>
  );
};
