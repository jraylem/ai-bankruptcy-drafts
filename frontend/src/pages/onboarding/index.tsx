import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { FormProvider, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { FiArrowLeft, FiArrowRight, FiCheck, FiClipboard, FiMail, FiMonitor } from 'react-icons/fi';
import { useAuthSession } from '@/features/auth/queries';
import { useCompleteOnboardingMutation, useFirmQuery } from '@/features/onboarding/queries';
import { createOnboardingSchema } from '@/features/onboarding/schema';
import {
  DEFAULT_ONBOARDING_PERMISSIONS_BY_ROLE,
  type InvitedMember,
  type OnboardingFormValues,
} from '@/features/onboarding/types';
import { FirmDetailsStep } from '@/features/onboarding/components/FirmDetailsStep';
import { InviteMembersStep } from '@/features/onboarding/components/InviteMembersStep';
import { OnboardingStepIndicator } from '@/features/onboarding/components/OnboardingStepIndicator';
import { ReviewStep } from '@/features/onboarding/components/ReviewStep';
import type { User } from '@/types';

type OnboardingStep = 1 | 2 | 3;

interface StepScreenProps {
  invites: InvitedMember[];
  isReviewConfirmed: boolean;
  onAddInvite: () => Promise<void>;
  onConfirmedChange: (isConfirmed: boolean) => void;
  onRemoveInvite: (email: string) => void;
}

const inferOwnerName = (user: User | null): string => {
  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim();
  if (fullName) return fullName;
  return user?.email?.split('@')[0] ?? user?.username?.split('@')[0] ?? '';
};

const SidebarVisual = ({ step }: { step: number }) => {
  if (step === 2) {
    return (
      <div className="relative ml-auto h-48 w-56">
        <div className="absolute bottom-9 right-0 h-28 w-44 rounded-xl border border-border bg-surface shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <FiMonitor className="h-4 w-4 text-subtle" />
            <span className="h-2 w-20 rounded-full bg-surface-muted" />
          </div>
          <div className="space-y-2 p-3">
            <span className="block h-2 rounded-full bg-surface-muted" />
            <span className="block h-2 w-2/3 rounded-full bg-surface-muted" />
          </div>
        </div>
        <div className="absolute right-28 top-10 flex h-10 w-14 animate-[onboardingEmailSend_3.2s_ease-in-out_infinite] items-center justify-center rounded-lg bg-app-accent text-white shadow-lg">
          <FiMail className="h-5 w-5" />
        </div>
      </div>
    );
  }

  if (step === 3) {
    return (
      <div className="relative ml-auto h-48 w-56">
        <div className="absolute right-0 top-4 h-36 w-44 rounded-2xl border border-border bg-surface shadow-sm">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <FiClipboard className="h-4 w-4 text-subtle" />
              <span className="h-2 w-16 rounded-full bg-surface-muted" />
            </div>
            <span className="h-3 w-3 rounded-full bg-app-success-text/70" />
          </div>
          <div className="space-y-3 p-4">
            <div className="flex items-center gap-3">
              <span className="grid h-5 w-5 animate-[onboardingReviewCheck_2.4s_ease-in-out_infinite] place-items-center rounded-full">
                <FiCheck className="h-3.5 w-3.5" />
              </span>
              <span className="h-2 w-24 rounded-full bg-surface-muted" />
            </div>
            <div className="flex items-center gap-3">
              <span
                className="grid h-5 w-5 animate-[onboardingReviewCheck_2.4s_ease-in-out_infinite] place-items-center rounded-full"
                style={{ animationDelay: '0.45s' }}
              >
                <FiCheck className="h-3.5 w-3.5" />
              </span>
              <span className="h-2 w-20 rounded-full bg-surface-muted" />
            </div>
            <div className="flex items-center gap-3">
              <span
                className="grid h-5 w-5 animate-[onboardingReviewCheck_2.4s_ease-in-out_infinite] place-items-center rounded-full"
                style={{ animationDelay: '0.9s' }}
              >
                <FiCheck className="h-3.5 w-3.5" />
              </span>
              <span className="h-2 w-28 rounded-full bg-surface-muted" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative ml-auto h-48 w-56">
      <div className="absolute right-28 top-9 h-28 w-24 animate-[onboardingShuffleA_7s_ease-in-out_infinite] rounded-xl border border-border bg-surface shadow-sm">
        <div className="h-3 rounded-t-xl bg-app-accent/80" />
        <div className="space-y-2 p-3">
          <span className="block h-2 rounded-full bg-surface-muted" />
          <span className="block h-2 w-2/3 rounded-full bg-surface-muted" />
          <span className="block h-2 w-4/5 rounded-full bg-surface-muted" />
        </div>
      </div>
      <div className="absolute right-16 top-12 h-28 w-24 animate-[onboardingShuffleB_7s_ease-in-out_infinite] rounded-xl border border-border bg-surface shadow-sm">
        <div className="h-3 rounded-t-xl bg-app-success-text/60" />
        <div className="space-y-2 p-3">
          <span className="block h-2 rounded-full bg-surface-muted" />
          <span className="block h-2 w-1/2 rounded-full bg-surface-muted" />
          <span className="block h-2 w-5/6 rounded-full bg-surface-muted" />
        </div>
      </div>
      <div className="absolute right-0 top-8 h-28 w-24 animate-[onboardingShuffleC_7s_ease-in-out_infinite] rounded-xl border border-border bg-surface shadow-sm">
        <div className="h-3 rounded-t-xl bg-app-warning-text/60" />
        <div className="space-y-2 p-3">
          <span className="block h-2 rounded-full bg-surface-muted" />
          <span className="block h-2 w-3/5 rounded-full bg-surface-muted" />
          <span className="block h-2 w-4/5 rounded-full bg-surface-muted" />
        </div>
      </div>
    </div>
  );
};

const STEP_SCREENS: Record<OnboardingStep, (props: StepScreenProps) => React.ReactNode> = {
  1: () => <FirmDetailsStep />,
  2: ({ invites, onAddInvite, onRemoveInvite }) => (
    <InviteMembersStep
      invites={invites}
      onAddInvite={onAddInvite}
      onRemoveInvite={onRemoveInvite}
    />
  ),
  3: ({ invites, isReviewConfirmed, onConfirmedChange }) => (
    <ReviewStep
      invites={invites}
      isConfirmed={isReviewConfirmed}
      onConfirmedChange={onConfirmedChange}
    />
  ),
};

export const OnboardingPage = () => {
  const navigate = useNavigate();
  const { user } = useAuthSession();
  const ownerEmail = user?.email ?? (user?.username?.includes('@') ? user.username : '');
  const [step, setStep] = useState<OnboardingStep>(1);
  const [invites, setInvites] = useState<InvitedMember[]>([]);
  const [isReviewConfirmed, setIsReviewConfirmed] = useState(false);
  const firmQuery = useFirmQuery(Boolean(user?.firm_id));
  const completeOnboardingMutation = useCompleteOnboardingMutation();

  const schema = useMemo(() => createOnboardingSchema(ownerEmail), [ownerEmail]);

  const form = useForm<OnboardingFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      firmName: '',
      firmAddress: '',
      contactNumber: '',
      practiceType: 'bankruptcy',
      ownerName: inferOwnerName(user),
      ownerEmail,
      inviteEmail: '',
      invitePermissions: DEFAULT_ONBOARDING_PERMISSIONS_BY_ROLE.member,
      inviteRole: 'member',
    },
    mode: 'onBlur',
  });
  const {
    clearErrors,
    formState: { isSubmitting },
    getValues,
    handleSubmit,
    reset,
    resetField,
    setError,
    trigger,
  } = form;

  useEffect(() => {
    if (!firmQuery.data) return;

    reset({
      firmName: firmQuery.data.name ?? '',
      firmAddress: firmQuery.data.address ?? '',
      contactNumber: firmQuery.data.contact_number ?? '',
      practiceType: firmQuery.data.firm_type === 'bankruptcy' ? 'bankruptcy' : 'bankruptcy',
      ownerName: inferOwnerName(user),
      ownerEmail,
      inviteEmail: '',
      invitePermissions: DEFAULT_ONBOARDING_PERMISSIONS_BY_ROLE.member,
      inviteRole: 'member',
    });
  }, [firmQuery.data, ownerEmail, reset, user]);
  const addInvite = async () => {
    const isValid = await trigger(['inviteEmail', 'inviteRole']);
    if (!isValid) return;

    const email = getValues('inviteEmail').trim().toLowerCase();
    const permissions = getValues('invitePermissions');
    const role = getValues('inviteRole');
    if (!email) {
      setError('inviteEmail', { message: 'Enter an email before sending an invite' });
      return;
    }

    if (email === getValues('ownerEmail').trim().toLowerCase()) {
      setError('inviteEmail', { message: 'You are already listed as the workspace owner' });
      return;
    }

    if (invites.some((member) => member.email === email)) {
      setError('inviteEmail', { message: 'This member is already invited' });
      return;
    }

    setInvites((current) => [
      ...current,
      { email, permissions, role },
    ]);
    clearErrors('inviteEmail');
    resetField('inviteEmail');
    resetField('invitePermissions', { defaultValue: DEFAULT_ONBOARDING_PERMISSIONS_BY_ROLE.member });
    resetField('inviteRole', { defaultValue: 'member' });
  };

  const removeInvite = (email: string) => {
    setInvites((current) => current.filter((member) => member.email !== email));
  };

  const goNext = async () => {
    if (step === 1) {
      const isValid = await trigger([
        'firmName',
        'firmAddress',
        'contactNumber',
        'practiceType',
        'ownerName',
        'ownerEmail',
      ]);
      if (!isValid) return;
    }

    if (step === 2 && getValues('inviteEmail').trim()) {
      const isValid = await trigger(['inviteEmail', 'inviteRole']);
      if (!isValid) return;
    }

    if (step === 2) {
      setIsReviewConfirmed(false);
    }

    setStep((current) => Math.min(current + 1, 3) as OnboardingStep);
  };

  const onSubmit = async (values: OnboardingFormValues) => {
    if (!isReviewConfirmed) return;
    await completeOnboardingMutation.mutateAsync({ values, invites });
    navigate('/');
  };

  const CurrentStepScreen = STEP_SCREENS[step];

  return (
    <main className="h-screen w-full overflow-hidden bg-surface">
      <div className="h-full w-full">
        <FormProvider {...form}>
          <form
            className="grid h-full min-h-0 lg:grid-cols-3"
            onSubmit={handleSubmit(onSubmit)}
            noValidate
          >
            <aside className="relative flex min-h-0 border-b border-border p-8 lg:col-span-1 lg:justify-end lg:border-b-0 lg:border-r lg:border-app-border/60 lg:p-12">
              <div className="flex w-full max-w-[320px] flex-col justify-center gap-12">
                <OnboardingStepIndicator currentStep={step} />
                <SidebarVisual step={step} />
              </div>
            </aside>

            <div className="min-h-0 min-w-0 overflow-y-auto p-8 lg:col-span-2 lg:p-12">
              <div className="flex min-h-full w-full max-w-[760px] flex-col">
                <div className="my-auto">
                  <CurrentStepScreen
                    invites={invites}
                    isReviewConfirmed={isReviewConfirmed}
                    onAddInvite={addInvite}
                    onConfirmedChange={setIsReviewConfirmed}
                    onRemoveInvite={removeInvite}
                  />
                </div>

                <footer className="mt-10 flex shrink-0 flex-col gap-4 border-t border-surface-muted pt-8 sm:flex-row sm:items-center sm:justify-end sm:gap-6">
                  {completeOnboardingMutation.error ? (
                    <p className="text-sm font-medium text-app-error-text sm:mr-auto">
                      {completeOnboardingMutation.error.message}
                    </p>
                  ) : null}
                  {step > 1 ? (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() =>
                        setStep((current) => Math.max(current - 1, 1) as OnboardingStep)
                      }
                      className="inline-flex items-center gap-2 text-sm font-medium text-text-secondary transition hover:text-text disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <FiArrowLeft className="h-4 w-4" />
                      Prev
                    </button>
                  ) : null}

                  {step < 3 ? (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => void goNext()}
                      className="inline-flex items-center gap-2 rounded-xl bg-app-accent px-5 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-app-accent-text disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {step === 2 && invites.length === 0 ? 'Skip' : 'Next'}
                      <FiArrowRight className="h-4 w-4" />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={isSubmitting || !isReviewConfirmed}
                      className="inline-flex items-center gap-2 rounded-xl bg-app-accent px-5 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-app-accent-text disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <FiCheck className="h-4 w-4" />
                      {isSubmitting ? 'Saving...' : 'Confirm setup'}
                    </button>
                  )}
                </footer>
              </div>
            </div>
          </form>
        </FormProvider>
      </div>
    </main>
  );
};
