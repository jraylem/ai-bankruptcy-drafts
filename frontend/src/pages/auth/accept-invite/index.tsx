import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { FiAlertCircle, FiCheckCircle, FiEye, FiEyeOff } from 'react-icons/fi';
import { z } from 'zod';
import { firmsService } from '@/services/firms.service';
import { authKeys } from '@/features/auth/queries';
import { queryClient } from '@/lib/queryClient';
import { useToastStore } from '@/stores/useToastStore';

const APP_DISPLAY_NAME = 'Jurisgentic';

const acceptInviteSchema = z
  .object({
    firstName: z.string().trim().min(1, 'Enter your first name.'),
    lastName: z.string().trim().min(1, 'Enter your last name.'),
    password: z.string().min(6, 'Password must be at least 6 characters.'),
    confirmPassword: z.string().min(1, 'Confirm your password.'),
  })
  .refine((values) => values.password === values.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match.',
  });

type AcceptInviteFormValues = z.infer<typeof acceptInviteSchema>;

export const AcceptInvitePage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const firmName =
    searchParams.get('firm_name')?.trim() || searchParams.get('firmName')?.trim() || '';
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [mounted, setMounted] = useState(false);
  const addToast = useToastStore((state) => state.addToast);
  const {
    formState: { errors },
    handleSubmit,
    register,
    watch,
  } = useForm<AcceptInviteFormValues>({
    resolver: zodResolver(acceptInviteSchema),
    defaultValues: {
      firstName: '',
      lastName: '',
      password: '',
      confirmPassword: '',
    },
  });
  const firstName = watch('firstName');
  const lastName = watch('lastName');
  const password = watch('password');
  const confirmPassword = watch('confirmPassword');

  const acceptInviteMutation = useMutation({
    mutationFn: async (values: AcceptInviteFormValues) => {
      const response = await firmsService.acceptInvitation({
        token,
        first_name: values.firstName.trim(),
        last_name: values.lastName.trim(),
        password: values.password,
      });

      if (response.error || !response.data?.user) {
        throw new Error(response.error || 'Unable to accept invitation');
      }

      return response.data.user;
    },
    onSuccess: (user) => {
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== authKeys.all[0],
      });
      queryClient.setQueryData(authKeys.currentUser(), user);
      addToast(
        firmName
          ? `You're now a member of ${firmName}.`
          : "You're now a member of this firm.",
        'success'
      );
      navigate('/', { replace: true });
    },
  });

  const error =
    acceptInviteMutation.error instanceof Error ? acceptInviteMutation.error.message : null;

  useEffect(() => {
    setMounted(true);
  }, []);

  const onSubmit = async (values: AcceptInviteFormValues) => {
    await acceptInviteMutation.mutateAsync(values).catch(() => undefined);
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-auth-bg-from via-auth-bg-via to-auth-bg-to px-4 py-8">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -right-40 -top-40 h-80 w-80 rounded-full bg-auth-blob-purple opacity-70 mix-blend-multiply blur-xl animate-blob" />
        <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-auth-blob-indigo opacity-70 mix-blend-multiply blur-xl animate-blob animation-delay-2000" />
        <div className="absolute left-40 top-40 h-80 w-80 rounded-full bg-auth-blob-pink opacity-70 mix-blend-multiply blur-xl animate-blob animation-delay-4000" />
      </div>

      <div
        className={`relative z-10 w-full max-w-lg transition-all duration-700 ${
          mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
        }`}
      >
        <div className="mb-6 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl transition duration-500 hover:scale-105 hover:rotate-3">
            <img src="/logo.png" alt="Logo" className="h-16 w-16 object-contain logo-on-dark" />
          </div>
          <h1 className="mt-3 bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text font-poppins text-2xl font-bold text-transparent">
            {APP_DISPLAY_NAME}
          </h1>
          <div className="mx-auto mt-2 h-1 w-12 rounded-full bg-gradient-to-r from-indigo-600 to-purple-600" />
        </div>

        <section className="relative overflow-hidden rounded-2xl border border-border bg-surface/95 shadow-xl backdrop-blur-sm">
          <header className="space-y-3 px-8 pb-5 pt-8 text-center">
            <div>
              <h2 className="font-poppins text-2xl font-semibold leading-tight text-text">
                You've been invited to join {firmName || 'your firm'}
              </h2>
              <p className="mt-3 text-sm leading-6 text-text-secondary">
                Create a password to accept your invitation and access the workspace.
              </p>
            </div>
          </header>

          <div className="px-8 pb-8">
            {!token ? (
              <div className="space-y-5 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-app-danger-soft text-app-danger-text">
                  <FiAlertCircle className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="font-poppins text-lg font-semibold text-text">
                    Invalid invitation
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-text-secondary">
                    This invitation link is missing or invalid. Please open the link from your
                    invitation email.
                  </p>
                </div>
                <Link
                  to="/login"
                  className="inline-flex text-sm font-semibold text-app-accent-text transition hover:text-app-accent"
                >
                  Back to sign in
                </Link>
              </div>
            ) : acceptInviteMutation.isSuccess ? (
              <div className="space-y-5 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-app-success-soft text-app-success-text">
                  <FiCheckCircle className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="font-poppins text-lg font-semibold text-text">
                    Invitation accepted
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-text-secondary">
                    Your workspace access is ready. Taking you there now.
                  </p>
                </div>
                <Link
                  to="/"
                  className="inline-flex h-12 w-full items-center justify-center rounded-xl bg-app-accent px-5 text-sm font-bold text-white shadow-sm transition hover:bg-app-accent-text"
                >
                  Continue
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" autoComplete="off">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label
                      htmlFor="accept-invite-first-name"
                      className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary"
                    >
                      First name
                    </label>
                    <input
                      id="accept-invite-first-name"
                      type="text"
                      placeholder="First name"
                      autoFocus
                      autoComplete="given-name"
                      className={`h-12 w-full rounded-xl border bg-surface-muted px-4 text-sm text-text-secondary outline-none transition placeholder:text-subtle focus:ring-2 ${
                        errors.firstName
                          ? 'border-app-danger-text focus:border-app-danger-text focus:ring-app-danger-soft'
                          : 'border-border focus:border-app-accent focus:ring-app-accent-soft'
                      }`}
                      {...register('firstName')}
                    />
                    {errors.firstName?.message ? (
                      <p className="mt-1.5 text-xs font-medium text-app-danger-text">
                        {errors.firstName.message}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <label
                      htmlFor="accept-invite-last-name"
                      className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary"
                    >
                      Last name
                    </label>
                    <input
                      id="accept-invite-last-name"
                      type="text"
                      placeholder="Last name"
                      autoComplete="family-name"
                      className={`h-12 w-full rounded-xl border bg-surface-muted px-4 text-sm text-text-secondary outline-none transition placeholder:text-subtle focus:ring-2 ${
                        errors.lastName
                          ? 'border-app-danger-text focus:border-app-danger-text focus:ring-app-danger-soft'
                          : 'border-border focus:border-app-accent focus:ring-app-accent-soft'
                      }`}
                      {...register('lastName')}
                    />
                    {errors.lastName?.message ? (
                      <p className="mt-1.5 text-xs font-medium text-app-danger-text">
                        {errors.lastName.message}
                      </p>
                    ) : null}
                  </div>
                </div>

                <div>
                  <label
                    htmlFor="accept-invite-password"
                    className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary"
                  >
                    Password
                  </label>
                  <div className="relative">
                    <input
                      id="accept-invite-password"
                      type={showPassword ? 'text' : 'password'}
                      placeholder="Create a password"
                      autoComplete="new-password"
                      className={`h-12 w-full rounded-xl border bg-surface-muted px-4 pr-12 text-sm text-text-secondary outline-none transition placeholder:text-subtle focus:ring-2 ${
                        errors.password
                          ? 'border-app-danger-text focus:border-app-danger-text focus:ring-app-danger-soft'
                          : 'border-border focus:border-app-accent focus:ring-app-accent-soft'
                      }`}
                      {...register('password')}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((current) => !current)}
                      className="absolute right-2.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition hover:bg-surface hover:text-text-secondary"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      aria-pressed={showPassword}
                    >
                      {showPassword ? (
                        <FiEyeOff className="h-4 w-4" />
                      ) : (
                        <FiEye className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                  {errors.password?.message ? (
                    <p className="mt-1.5 text-xs font-medium text-app-danger-text">
                      {errors.password.message}
                    </p>
                  ) : null}
                </div>

                <div>
                  <label
                    htmlFor="accept-invite-confirm-password"
                    className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary"
                  >
                    Confirm password
                  </label>
                  <div className="relative">
                    <input
                      id="accept-invite-confirm-password"
                      type={showConfirmPassword ? 'text' : 'password'}
                      placeholder="Confirm your password"
                      autoComplete="new-password"
                      className={`h-12 w-full rounded-xl border bg-surface-muted px-4 pr-12 text-sm text-text-secondary outline-none transition placeholder:text-subtle focus:ring-2 ${
                        errors.confirmPassword
                          ? 'border-app-danger-text focus:border-app-danger-text focus:ring-app-danger-soft'
                          : 'border-border focus:border-app-accent focus:ring-app-accent-soft'
                      }`}
                      {...register('confirmPassword')}
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword((current) => !current)}
                      className="absolute right-2.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition hover:bg-surface hover:text-text-secondary"
                      aria-label={
                        showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'
                      }
                      aria-pressed={showConfirmPassword}
                    >
                      {showConfirmPassword ? (
                        <FiEyeOff className="h-4 w-4" />
                      ) : (
                        <FiEye className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                  {errors.confirmPassword?.message ? (
                    <p className="mt-1.5 text-xs font-medium text-app-danger-text">
                      {errors.confirmPassword.message}
                    </p>
                  ) : null}
                </div>

                {error ? (
                  <div className="flex items-start gap-2 rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
                    <FiAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                  </div>
                ) : null}

                <button
                  type="submit"
                  className="inline-flex h-12 w-full items-center justify-center rounded-xl bg-app-accent px-5 text-sm font-bold text-white shadow-sm transition hover:bg-app-accent-text disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={
                    !firstName ||
                    !lastName ||
                    !password ||
                    !confirmPassword ||
                    acceptInviteMutation.isPending
                  }
                >
                  {acceptInviteMutation.isPending ? 'Accepting...' : 'Accept Invitation'}
                </button>
              </form>
            )}
          </div>
        </section>

        <p className="mt-6 text-center text-xs leading-5 text-muted">
          By creating an account, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  );
};
