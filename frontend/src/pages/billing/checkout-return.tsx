import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FiAlertCircle, FiArrowLeft, FiCheckCircle, FiRefreshCw } from 'react-icons/fi';
import { BillingButton } from '@/features/billing/components/BillingButton';
import { useBillingOverview } from '@/features/billing/hooks/useBillingOverview';

type BillingCheckoutReturnStatus = 'cancel' | 'success';

interface BillingCheckoutReturnPageProps {
  status: BillingCheckoutReturnStatus;
}

const ACTIVE_REDIRECT_SECONDS = 5;
const CONFIRMATION_POLL_LIMIT = 6;
const CONFIRMATION_POLL_MS = 2_500;

const statusCopy = {
  cancel: {
    icon: FiAlertCircle,
    iconClassName: 'bg-app-warning-soft text-app-warning-text',
    title: 'Checkout cancelled',
    description:
      'No subscription changes were made. You can return to billing whenever you are ready to subscribe.',
  },
  success: {
    icon: FiCheckCircle,
    iconClassName: 'bg-app-accent-soft text-app-accent-text',
    title: 'Checkout complete',
    description:
      'Stripe accepted the checkout. Billing details can take a moment to update while Stripe sends the confirmation webhook.',
  },
} satisfies Record<
  BillingCheckoutReturnStatus,
  {
    description: string;
    icon: React.ComponentType<{ className?: string }>;
    iconClassName: string;
    title: string;
  }
>;

const ACTIVE_REDIRECT_MS = ACTIVE_REDIRECT_SECONDS * 1_000;

const RedirectProgress = ({ className = '' }: { className?: string }) => {
  const [isRunning, setIsRunning] = React.useState(false);

  React.useEffect(() => {
    const animationFrame = window.requestAnimationFrame(() => setIsRunning(true));
    return () => window.cancelAnimationFrame(animationFrame);
  }, []);

  return (
    <div className={className}>
      <div
        className="h-1.5 overflow-hidden bg-border/80"
        role="progressbar"
        aria-label="Redirecting to billing"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext="Returning to billing shortly"
      >
        <div
          className="h-full bg-app-accent transition-[width] ease-linear"
          style={{
            transitionDuration: `${ACTIVE_REDIRECT_MS}ms`,
            width: isRunning ? '100%' : '0%',
          }}
        />
      </div>
      <span className="sr-only">Returning to billing shortly.</span>
    </div>
  );
};

export const BillingCheckoutReturnPage: React.FC<BillingCheckoutReturnPageProps> = ({ status }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isSuccess = status === 'success';
  const { data: overview, isFetching, refetch } = useBillingOverview(isSuccess);
  const copy = statusCopy[status];
  const Icon = copy.icon;
  const sessionId = searchParams.get('session_id');
  const hasSubscription = Boolean(overview?.subscription);
  const [pollCount, setPollCount] = React.useState(0);

  const handleBackToBilling = () => {
    navigate('/billing');
  };

  React.useEffect(() => {
    if (!isSuccess || hasSubscription || pollCount >= CONFIRMATION_POLL_LIMIT) return undefined;

    const pollTimer = window.setTimeout(() => {
      setPollCount((count) => count + 1);
      void refetch();
    }, CONFIRMATION_POLL_MS);

    return () => window.clearTimeout(pollTimer);
  }, [hasSubscription, isSuccess, pollCount, refetch]);

  React.useEffect(() => {
    const redirectTimer = window.setTimeout(() => {
      navigate('/billing', { replace: true });
    }, ACTIVE_REDIRECT_MS);

    return () => window.clearTimeout(redirectTimer);
  }, [navigate]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[640px] items-center px-6 py-10">
      <div className="fixed inset-0 -z-10 bg-page" />
      <div className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.08),transparent_60%)]" />
      <section className="relative w-full overflow-hidden rounded-2xl border border-border/70 bg-surface p-6 shadow-sm sm:p-8">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
          <div
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${copy.iconClassName}`}
          >
            <Icon className="h-6 w-6" />
          </div>

          <div className="min-w-0 flex-1">
            <h1 className="font-poppins text-2xl font-semibold tracking-normal text-app-accent-text">
              {copy.title}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
              {copy.description}
            </p>

            {isSuccess ? (
              <div className="mt-5 rounded-xl border border-border/70 bg-surface-muted px-4 py-3 text-sm text-text-secondary">
                {hasSubscription ? (
                  <>
                    <p className="font-medium text-app-accent-text">
                      Your subscription is active in BKDrafts.
                    </p>
                    <p className="mt-2">Returning to billing shortly.</p>
                  </>
                ) : (
                  <>
                    <p>
                      We are still waiting for Stripe confirmation. This page will refresh the
                      status briefly before returning to billing.
                    </p>
                    <p className="mt-2">Returning to billing shortly.</p>
                  </>
                )}
                {sessionId ? (
                  <p className="mt-2 font-mono text-xs text-text-muted">
                    Checkout session: {sessionId}
                  </p>
                ) : null}
              </div>
            ) : (
              <div className="mt-5 rounded-xl border border-border/70 bg-surface-muted px-4 py-3 text-sm text-text-secondary">
                <p>Returning to billing shortly.</p>
              </div>
            )}

            <div className="mt-6 flex flex-wrap gap-3">
              <BillingButton onClick={handleBackToBilling} variant="primary">
                <FiArrowLeft className="h-4 w-4" />
                Back to billing
              </BillingButton>
              {isSuccess ? (
                <BillingButton
                  disabled={isFetching}
                  onClick={() => void refetch()}
                  variant="secondary"
                >
                  <FiRefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
                  Refresh status
                </BillingButton>
              ) : null}
            </div>
          </div>
        </div>
        <RedirectProgress className="absolute inset-x-0 bottom-0" />
      </section>
    </main>
  );
};

export const BillingSuccessPage: React.FC = () => (
  <BillingCheckoutReturnPage status="success" />
);

export const BillingCancelPage: React.FC = () => (
  <BillingCheckoutReturnPage status="cancel" />
);
