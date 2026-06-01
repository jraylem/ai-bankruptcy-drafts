import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ACCOUNT_NOT_ACCEPTED_CODE,
  AuthApiError,
  EMAIL_NOT_CONFIRMED_CODE,
  useAuthSession,
  useLoginMutation,
  useResendVerificationMutation,
} from '@/features/auth/queries';
import { Button, Input, Card, CardHeader, CardTitle, CardContent } from '@/components/common';
import { useToastStore } from '@/stores/useToastStore';

const ACCESS_CONTACT_EMAIL = 'nickf@cvhlawgroup.com';
const ACCESS_CONTACT_MESSAGE = `Please contact ${ACCESS_CONTACT_EMAIL} to gain access.`;

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mounted, setMounted] = useState(false);
  const { isAuthenticated } = useAuthSession();
  const loginMutation = useLoginMutation();
  const resendMutation = useResendVerificationMutation();
  const addToast = useToastStore((s) => s.addToast);
  const lastToastedLoginError = useRef<Error | null>(null);
  const lastToastedResendError = useRef<Error | null>(null);
  const lastAutoResentEmail = useRef<string | null>(null);
  const loginErrorObj = loginMutation.error instanceof Error ? loginMutation.error : null;
  const emailNotConfirmed =
    (loginMutation.error instanceof AuthApiError &&
      loginMutation.error.code === EMAIL_NOT_CONFIRMED_CODE) ||
    (loginErrorObj?.message
      ? /not\s+(verified|confirmed)/i.test(loginErrorObj.message)
      : false);
  const accountNotAccepted =
    (loginMutation.error instanceof AuthApiError &&
      loginMutation.error.code === ACCOUNT_NOT_ACCEPTED_CODE);
  const resendErrorObj = resendMutation.error instanceof Error ? resendMutation.error : null;

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    if (loginErrorObj && lastToastedLoginError.current !== loginErrorObj) {
      lastToastedLoginError.current = loginErrorObj;
      addToast(
        accountNotAccepted ? ACCESS_CONTACT_MESSAGE : loginErrorObj.message,
        emailNotConfirmed || accountNotAccepted ? 'warning' : 'error',
      );
    }
  }, [loginErrorObj, emailNotConfirmed, accountNotAccepted, addToast]);

  useEffect(() => {
    if (resendErrorObj && lastToastedResendError.current !== resendErrorObj) {
      lastToastedResendError.current = resendErrorObj;
      addToast(resendErrorObj.message, 'error');
    }
  }, [resendErrorObj, addToast]);

  useEffect(() => {
    if (emailNotConfirmed && email && lastAutoResentEmail.current !== email) {
      lastAutoResentEmail.current = email;
      resendMutation.mutate(email, {
        onSuccess: () => {
          addToast(`Confirmation email sent to ${email}.`, 'success');
        },
      });
    }
  }, [emailNotConfirmed, email, resendMutation, addToast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    resendMutation.reset();
    lastAutoResentEmail.current = null;
    await loginMutation.mutateAsync({ email, password }).catch(() => undefined);
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
              Jurisgentic
            </CardTitle>
            <div className="h-1 w-16 bg-gradient-to-r from-indigo-600 to-purple-600 mx-auto mt-2 rounded-full"></div>
          </div>

          <p className={`text-auth-text text-sm sm:text-base transition-all duration-500 delay-200 ${
            mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
          }`}>
            Welcome back! Please sign in to your account.
          </p>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <Input
                type="email"
                label="Email Address"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
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
              />
            </div>

            {accountNotAccepted && (
              <div className="bg-auth-error-bg border border-auth-error-border text-auth-error-text px-4 py-3 rounded-xl animate-slide-down shadow-sm">
                <div className="flex items-start">
                  <svg className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2 2a1 1 0 001.414-1.414L11 9.586V6z" clipRule="evenodd" />
                  </svg>
                  <span className="text-sm">
                    {ACCESS_CONTACT_MESSAGE}
                  </span>
                </div>
              </div>
            )}

            {/* Animated submit button */}
            <Button
              type="submit"
              className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 transform transition-all duration-300 hover:scale-[1.02] hover:shadow-xl text-base sm:text-lg py-3 rounded-xl font-semibold"
              isLoading={loginMutation.isPending}
            >
              <span className="flex items-center justify-center">
                <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
                </svg>
                Sign In
              </span>
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-auth-divider">
            <div className="text-center">
              <p className="text-sm text-auth-text">
                Don't have an account?{' '}
                <Link
                  to="/register"
                  className="font-semibold text-auth-link hover:text-auth-link-hover transition-all duration-300 hover:underline cursor-pointer transform hover:scale-105 inline-block"
                >
                  Sign up now →
                </Link>
              </p>
            </div>
          </div>

          {/* Additional info for mobile */}
          <div className="mt-6 text-center">
            <p className="text-xs text-auth-muted">
              By continuing, you agree to our Terms of Service and Privacy Policy
            </p>
          </div>
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
