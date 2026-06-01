import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ACCOUNT_NOT_ACCEPTED_CODE,
  AuthApiError,
  useVerifyEmailMutation,
} from '@/features/auth/queries';
import { Card, CardHeader, CardTitle, CardContent, Spinner } from '@/components/common';
import { useToastStore } from '@/stores/useToastStore';
import { APP_NAME } from '@/constants';

type VerifyStatus = 'validating' | 'success' | 'pending_approval' | 'error';

const REDIRECT_DELAY_MS = 1500;
const ACCESS_CONTACT_EMAIL = 'nickf@cvhlawgroup.com';
const ACCESS_CONTACT_MESSAGE = `Please contact ${ACCESS_CONTACT_EMAIL} to gain access.`;

export const VerifyEmailPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const verifyMutation = useVerifyEmailMutation();
  const addToast = useToastStore((s) => s.addToast);
  const hasAttempted = useRef(false);
  const hasToasted = useRef(false);
  const [mounted, setMounted] = useState(false);
  const [status, setStatus] = useState<VerifyStatus>(token ? 'validating' : 'error');
  const [errorMessage, setErrorMessage] = useState<string>(() =>
    token
      ? ''
      : 'Missing confirmation token. Please use the link from your confirmation email.',
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (hasAttempted.current) return;
    if (!token) return;
    hasAttempted.current = true;
    verifyMutation
      .mutateAsync(token)
      .then(() => {
        setStatus('success');
      })
      .catch((err: unknown) => {
        if (err instanceof AuthApiError && err.code === ACCOUNT_NOT_ACCEPTED_CODE) {
          setStatus('pending_approval');
          return;
        }

        const message =
          err instanceof Error
            ? err.message
            : 'We could not confirm your email. The link may have expired.';
        setErrorMessage(message);
        setStatus('error');
      });
  }, [token, verifyMutation]);

  useEffect(() => {
    if (status === 'success') {
      const timer = window.setTimeout(() => {
        navigate('/onboarding', { replace: true });
      }, REDIRECT_DELAY_MS);
      return () => window.clearTimeout(timer);
    }
  }, [status, navigate]);

  useEffect(() => {
    if (hasToasted.current) return;
    if (status === 'success') {
      hasToasted.current = true;
      addToast('Your account is now active.', 'success');
    } else if (status === 'pending_approval') {
      hasToasted.current = true;
      addToast(ACCESS_CONTACT_MESSAGE, 'warning');
    } else if (status === 'error' && errorMessage) {
      hasToasted.current = true;
      addToast(errorMessage, 'error');
    }
  }, [status, errorMessage, addToast]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-auth-bg-from via-auth-bg-via to-auth-bg-to px-4 py-4 relative overflow-hidden">
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
          <div className="relative">
            <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto">
              <img src="/logo.png" alt="Logo" className="w-20 h-20 object-contain logo-on-dark" />
            </div>
          </div>
          <div>
            <CardTitle className="text-3xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
              {APP_NAME}
            </CardTitle>
            <div className="h-1 w-16 bg-gradient-to-r from-indigo-600 to-purple-600 mx-auto mt-2 rounded-full"></div>
          </div>
        </CardHeader>

        <CardContent>
          {status === 'validating' && (
            <div className="space-y-4 text-center py-4">
              <Spinner size="lg" />
              <h3 className="text-lg font-semibold text-auth-text">Validating your email…</h3>
              <p className="text-sm text-auth-text">
                Hang tight while we confirm your account.
              </p>
            </div>
          )}

          {status === 'success' && (
            <div className="space-y-6 text-center animate-slide-down">
              <div className="mx-auto w-16 h-16 rounded-full bg-auth-blob-indigo/30 flex items-center justify-center">
                <svg className="w-8 h-8 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <h3 className="text-xl font-semibold text-auth-text">Email confirmed!</h3>
                <p className="text-sm text-auth-text mt-2">
                  Taking you to onboarding…
                </p>
              </div>
            </div>
          )}

          {status === 'pending_approval' && (
            <div className="space-y-6 text-center animate-slide-down">
              <div className="mx-auto w-16 h-16 rounded-full bg-auth-blob-indigo/30 flex items-center justify-center">
                <svg className="w-8 h-8 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2h-1V7a5 5 0 00-10 0v4H6a2 2 0 00-2 2v6a2 2 0 002 2zm3-10V7a3 3 0 016 0v4" />
                </svg>
              </div>
              <div>
                <h3 className="text-xl font-semibold text-auth-text">Account pending approval</h3>
                <p className="text-sm text-auth-text mt-2">
                  Your email is confirmed. {ACCESS_CONTACT_MESSAGE}
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
          )}

          {status === 'error' && (
            <div className="space-y-6 text-center animate-slide-down">
              <div className="mx-auto w-16 h-16 rounded-full bg-auth-error-bg flex items-center justify-center">
                <svg className="w-8 h-8 text-auth-error-text" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div>
                <h3 className="text-xl font-semibold text-auth-text">We couldn&rsquo;t verify your email</h3>
                <p className="text-sm text-auth-text mt-2">
                  Sign in again and we&rsquo;ll send you a fresh confirmation link.
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
        .animate-blob { animation: blob 7s infinite; }
        .animation-delay-2000 { animation-delay: 2s; }
        .animation-delay-4000 { animation-delay: 4s; }
        @keyframes slide-down {
          from { opacity: 0; transform: translateY(-10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-slide-down { animation: slide-down 0.3s ease-out; }
      `}</style>
    </div>
  );
};
