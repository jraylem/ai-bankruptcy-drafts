import React from 'react';
import { FiAlertCircle, FiCreditCard, FiFileText, FiSettings } from 'react-icons/fi';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { AnalyticsBodySkeleton, SkeletonBlock } from '@/features/analytics/components/AnalyticsSkeleton';
import {
  createBillingCheckoutSession,
  fetchBillingPortal,
} from '@/features/billing/api/billing.api';
import { BillingButton } from '@/features/billing/components/BillingButton';
import { BillingCard } from '@/features/billing/components/BillingCard';
import { BillingSummaryCards } from '@/features/billing/components/BillingSummaryCards';
import { CostDriversCard } from '@/features/billing/components/CostDriversCard';
import { FreeTierBillingState } from '@/features/billing/components/FreeTierBillingState';
import { InvoicesCard } from '@/features/billing/components/InvoicesCard';
import { PaymentMethodCard } from '@/features/billing/components/PaymentMethodCard';
import { UsageBreakdownCard } from '@/features/billing/components/UsageBreakdownCard';
import { UsageControlsCard } from '@/features/billing/components/UsageControlsCard';
import { useBillingOverview } from '@/features/billing/hooks/useBillingOverview';
import { useToastStore } from '@/stores/useToastStore';

const BillingHeaderActionsSkeleton: React.FC = () => (
  <div className="flex flex-wrap gap-3" aria-hidden="true">
    <SkeletonBlock className="h-10 w-32 rounded-lg" />
    <SkeletonBlock className="h-10 w-36 rounded-lg" />
    <SkeletonBlock className="h-10 w-[136px] rounded-lg" />
  </div>
);

const BillingSummaryCardSkeleton: React.FC<{ hasBadge?: boolean }> = ({ hasBadge = false }) => (
  <BillingCard className="flex min-h-[140px] flex-col p-5" aria-hidden="true">
    <div className="mb-3 flex items-start justify-between gap-3">
      <SkeletonBlock className="h-3 w-28 rounded-md" />
      {hasBadge ? (
        <SkeletonBlock className="h-6 w-20 rounded-full" />
      ) : (
        <SkeletonBlock className="h-9 w-9 rounded-lg" />
      )}
    </div>
    <div className="mt-auto">
      <SkeletonBlock className="h-8 w-28 rounded-md" />
      <SkeletonBlock className="mt-2 h-3 w-44 rounded-md" />
    </div>
  </BillingCard>
);

const BillingPanelSkeleton: React.FC<{ className?: string; rows?: number }> = ({
  className = '',
  rows = 4,
}) => (
  <BillingCard className={`p-5 ${className}`} aria-hidden="true">
    <div className="mb-6 flex items-start justify-between gap-4">
      <div className="space-y-2">
        <SkeletonBlock className="h-5 w-40 rounded-md" />
        <SkeletonBlock className="h-3 w-56 rounded-md" />
      </div>
      <SkeletonBlock className="h-9 w-24 rounded-lg" />
    </div>
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="flex items-center gap-3">
          <SkeletonBlock className="h-9 w-9 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <SkeletonBlock className="h-3 w-full max-w-[260px] rounded-md" />
            <SkeletonBlock className="h-3 w-full max-w-[180px] rounded-md" />
          </div>
          <SkeletonBlock className="h-5 w-16 rounded-md" />
        </div>
      ))}
    </div>
  </BillingCard>
);

const BillingInvoicesSkeleton: React.FC = () => (
  <BillingCard aria-hidden="true">
    <div className="px-5 pb-4 pt-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <SkeletonBlock className="h-5 w-36 rounded-md" />
          <SkeletonBlock className="h-3 w-52 rounded-md" />
        </div>
        <SkeletonBlock className="h-10 w-36 rounded-lg" />
      </div>
    </div>
    <div className="px-5 pb-5">
      <div className="overflow-hidden rounded-2xl border border-border/70">
        <div className="grid grid-cols-[1.2fr_1.4fr_0.8fr_0.8fr_0.8fr] gap-4 bg-surface-muted/75 px-4 py-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-3 w-full rounded-md" />
          ))}
        </div>
        <div>
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="grid grid-cols-[1.2fr_1.4fr_0.8fr_0.8fr_0.8fr] gap-4 border-t border-border/70 px-4 py-4"
            >
              <SkeletonBlock className="h-8 w-full rounded-md" />
              <SkeletonBlock className="h-5 w-full rounded-md" />
              <SkeletonBlock className="h-5 w-16 rounded-md" />
              <SkeletonBlock className="h-6 w-16 rounded-full" />
              <SkeletonBlock className="h-8 w-24 rounded-lg" />
            </div>
          ))}
        </div>
      </div>
    </div>
  </BillingCard>
);

const BillingPageSkeleton: React.FC = () => (
  <div className="space-y-6">
    <section className="grid gap-4 md:grid-cols-3">
      <BillingSummaryCardSkeleton hasBadge />
      <BillingSummaryCardSkeleton />
      <BillingSummaryCardSkeleton />
    </section>
    <BillingCard className="p-5" aria-hidden="true">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="space-y-2">
          <SkeletonBlock className="h-5 w-44 rounded-md" />
          <SkeletonBlock className="h-3 w-72 rounded-md" />
        </div>
        <SkeletonBlock className="h-9 w-28 rounded-lg" />
      </div>
      <AnalyticsBodySkeleton className="h-[280px] rounded-xl" />
    </BillingCard>
    <section className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
      <BillingPanelSkeleton className="min-h-[430px]" rows={5} />
      <div className="space-y-6">
        <BillingPanelSkeleton className="min-h-[190px]" rows={2} />
        <BillingPanelSkeleton className="min-h-[290px]" rows={3} />
      </div>
    </section>
    <BillingInvoicesSkeleton />
  </div>
);

export const BillingPage: React.FC = () => {
  const addToast = useToastStore((state) => state.addToast);
  const { data: overview, error, isLoading, isFetching } = useBillingOverview();
  const [isCheckoutStarting, setIsCheckoutStarting] = React.useState(false);
  const [isPortalOpening, setIsPortalOpening] = React.useState(false);
  const showInitialSkeleton = (isLoading || isFetching) && !overview;
  const isFreeTier = overview ? !overview.subscription : false;

  const handleUnavailableAction = () => {
    addToast('Checkout is unavailable', 'info');
  };

  const handleSubscribe = async () => {
    setIsCheckoutStarting(true);

    try {
      const { checkout_url } = await createBillingCheckoutSession({
        cancel_url: `${window.location.origin}/billing/cancel`,
        success_url: `${window.location.origin}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      });

      window.location.assign(checkout_url);
    } catch (checkoutError) {
      addToast(
        checkoutError instanceof Error ? checkoutError.message : 'Failed to start Stripe checkout.',
        'error'
      );
      setIsCheckoutStarting(false);
    }
  };

  const handleOpenBillingPortal = async () => {
    setIsPortalOpening(true);

    try {
      const { portal_url } = await fetchBillingPortal();
      window.location.assign(portal_url);
    } catch (portalError) {
      addToast(
        portalError instanceof Error ? portalError.message : 'Failed to open Stripe billing portal.',
        'error'
      );
      setIsPortalOpening(false);
    }
  };

  return (
    <SidebarLayout
      sidebarVariant="app"
      className="bg-page"
      contentClassName="overflow-y-auto"
    >
      <div className="mx-auto w-full max-w-[1400px] px-6 py-8 pb-16 xl:px-8">
        <header className="pb-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h1 className="font-poppins text-2xl font-semibold tracking-normal text-app-accent-text">
                Billing
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
                {isFreeTier
                  ? 'Your firm is currently on the Free Tier. Subscribe to unlock metered usage billing.'
                  : 'Monitor pay-as-you-go usage, spend, invoices, and firm billing controls.'}
              </p>
            </div>
            {showInitialSkeleton ? (
              <BillingHeaderActionsSkeleton />
            ) : !isFreeTier ? (
              <div className="flex flex-wrap gap-3">
                <BillingButton
                  disabled={isPortalOpening}
                  onClick={handleOpenBillingPortal}
                  variant="secondary"
                >
                  <FiFileText className="h-4 w-4" />
                  View invoices
                </BillingButton>
                <BillingButton
                  disabled={isPortalOpening}
                  onClick={handleOpenBillingPortal}
                  variant="primary"
                >
                  <FiCreditCard className="h-4 w-4" />
                  Manage payment
                </BillingButton>
                <BillingButton onClick={handleUnavailableAction} variant="secondary">
                  <FiSettings className="h-4 w-4" />
                  Usage settings
                </BillingButton>
              </div>
            ) : null}
          </div>
        </header>

        {error ? (
          <div
            role="alert"
            className="mt-6 flex items-start gap-3 rounded-xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text"
          >
            <FiAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">Billing data could not be loaded.</p>
              <p className="mt-1 text-app-danger-text/80">
                {error.message}
              </p>
            </div>
          </div>
        ) : null}

        <div className="mt-6 space-y-6">
          {showInitialSkeleton ? (
            <BillingPageSkeleton />
          ) : error || !overview ? null : isFreeTier ? (
            <FreeTierBillingState
              isSubscribing={isCheckoutStarting}
              onSubscribe={handleSubscribe}
              usageCategories={overview.usageCategories}
            />
          ) : (
            <>
              <BillingSummaryCards overview={overview} summary={overview.summary} />

              <UsageBreakdownCard
                isLoading={isLoading || isFetching}
                summaryLabel={overview.summary.monthToDateLabel}
                usageCategories={overview.usageCategories}
              />

              <section className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
                <CostDriversCard />
                <div className="space-y-6">
                  <PaymentMethodCard onAction={handleOpenBillingPortal} overview={overview} />
                  <UsageControlsCard onAction={handleUnavailableAction} />
                </div>
              </section>

              <InvoicesCard billingHistory={overview.billingHistory} onAction={handleOpenBillingPortal} />
            </>
          )}
        </div>
      </div>
    </SidebarLayout>
  );
};
