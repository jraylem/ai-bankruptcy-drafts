import React from 'react';
import { FiFileText, FiTrendingUp } from 'react-icons/fi';
import { BILLING_MODEL_LABELS } from '../billing.data';
import type { BillingOverview, BillingSubscription, BillingSummary } from '../types/billing.types';
import { BillingCard } from './BillingCard';

const formatBillingDate = (dateValue: string | null | undefined) => {
  if (!dateValue) {
    return 'Unavailable';
  }

  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) {
    return 'Unavailable';
  }

  return new Intl.DateTimeFormat('en-US', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date);
};

const getSubscriptionDisplay = (subscription: BillingSubscription | null | undefined) => {
  if (!subscription) {
    return {
      badgeClassName: 'bg-surface-muted text-text-secondary',
      label: 'Free tier',
      periodLabel: 'Subscribe to enable pay-as-you-go billing',
      statusLabel: 'Free tier',
    };
  }

  const periodEnd = formatBillingDate(subscription.current_period_end);

  switch (subscription.status) {
    case 'active':
      return {
        badgeClassName: 'bg-app-success-soft text-app-success-text',
        label: 'Active',
        periodLabel: `Current period ends ${periodEnd}`,
        statusLabel: 'Active',
      };
    case 'trialing':
      return {
        badgeClassName: 'bg-app-accent-soft text-app-accent-text',
        label: 'Trial',
        periodLabel: `Trial period ends ${periodEnd}`,
        statusLabel: 'Trialing',
      };
    case 'past_due':
      return {
        badgeClassName: 'bg-app-warning-soft text-app-warning-text',
        label: 'Past due',
        periodLabel: `Current period ends ${periodEnd}`,
        statusLabel: 'Past due',
      };
    case 'canceled':
      return {
        badgeClassName: 'bg-surface-muted text-text-secondary',
        label: 'Canceled',
        periodLabel: `Current period ends ${periodEnd}`,
        statusLabel: 'Canceled',
      };
    case 'incomplete':
      return {
        badgeClassName: 'bg-app-warning-soft text-app-warning-text',
        label: 'Pending',
        periodLabel: `Initial billing period ends ${periodEnd}`,
        statusLabel: 'Incomplete',
      };
    default:
      return {
        badgeClassName: 'bg-surface-muted text-text-secondary',
        label: 'Unknown',
        periodLabel: 'No billing cycle date available',
        statusLabel: 'Unknown',
      };
  }
};

const SummaryCard = ({
  badge,
  badgeClassName,
  icon,
  subtitle,
  title,
  value,
}: {
  badge?: string;
  badgeClassName?: string;
  icon?: React.ReactNode;
  subtitle: string;
  title: string;
  value: string;
}) => (
  <BillingCard className="flex min-h-[140px] flex-col p-5">
    <div className="mb-3 flex items-start justify-between gap-3">
      <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-text-secondary">
        {title}
      </p>
      {badge ? (
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] ${badgeClassName ?? 'bg-surface-muted text-text-secondary'}`}
        >
          {badge}
        </span>
      ) : icon ? (
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-muted text-text-secondary">
          {icon}
        </span>
      ) : null}
    </div>
    <div className="mt-auto">
      <p className="font-poppins text-2xl font-bold tracking-tight text-text">{value}</p>
      <p className="mt-1 text-[11px] leading-4 text-subtle">{subtitle}</p>
    </div>
  </BillingCard>
);

interface BillingSummaryCardsProps {
  overview: BillingOverview | undefined;
  summary: BillingSummary;
}

export const BillingSummaryCards: React.FC<BillingSummaryCardsProps> = ({ overview, summary }) => {
  const billingModelLabel = overview
    ? BILLING_MODEL_LABELS[overview.billingModel]
    : BILLING_MODEL_LABELS.pay_as_you_go;
  const subscriptionDisplay = getSubscriptionDisplay(overview?.subscription);

  return (
    <section className="grid gap-4 md:grid-cols-3">
      <SummaryCard
        badge={subscriptionDisplay.label}
        badgeClassName={subscriptionDisplay.badgeClassName}
        subtitle={subscriptionDisplay.periodLabel}
        title="Billing status"
        value={subscriptionDisplay.statusLabel}
      />
      <SummaryCard
        icon={<FiTrendingUp className="h-4 w-4" />}
        subtitle={`${billingModelLabel} usage estimate`}
        title="Month-to-date spend"
        value={summary.monthToDateLabel}
      />
      <SummaryCard
        icon={<FiFileText className="h-4 w-4" />}
        subtitle="Based on current usage pace"
        title="Projected month-end"
        value={summary.projectedLabel}
      />
    </section>
  );
};
