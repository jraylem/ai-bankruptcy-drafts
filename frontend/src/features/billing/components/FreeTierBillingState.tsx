import React from 'react';
import {
  FiArchive,
  FiArrowRight,
  FiBarChart2,
  FiCreditCard,
  FiFileText,
  FiLock,
  FiMessageSquare,
  FiShield,
  FiUsers,
  FiZap,
} from 'react-icons/fi';
import type { BillingUsageCategory } from '../types/billing.types';
import { BillingButton } from './BillingButton';
import { BillingCard } from './BillingCard';

type BillingPlanFeature = {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
};

const freeFeatures: BillingPlanFeature[] = [
  {
    icon: FiFileText,
    label: '1 pleading generation included',
  },
  {
    icon: FiMessageSquare,
    label: 'Basic case assistant access',
  },
  {
    icon: FiZap,
    label: 'Drafting workspace preview',
  },
  {
    icon: FiCreditCard,
    label: 'No payment method required',
  },
];

const paygoFeatures: BillingPlanFeature[] = [
  {
    icon: FiFileText,
    label: 'Unlimited metered pleading generation',
  },
  {
    icon: FiZap,
    label: 'Template Studio workflows',
  },
  {
    icon: FiArchive,
    label: 'Case Inbox and archive',
  },
  {
    icon: FiMessageSquare,
    label: 'Case-aware AI assistant',
  },
  {
    icon: FiBarChart2,
    label: 'Analytics and cost visibility',
  },
  {
    icon: FiShield,
    label: 'Firm security, roles, and permissions',
  },
  {
    icon: FiCreditCard,
    label: 'Billing portal, invoices, and usage limits',
  },
  {
    icon: FiUsers,
    label: 'Collaboration rooms and motion comments',
  },
];

const FeatureRow = ({ feature }: { feature: BillingPlanFeature }) => (
  <li className="flex gap-2.5 text-[13px] leading-5 text-text-secondary">
    <span className="mt-0.5 shrink-0 text-app-accent-text">
      <feature.icon className="h-4 w-4" />
    </span>
    <span className="min-w-0 flex-1">{feature.label}</span>
  </li>
);

const PlanCard = ({
  children,
  className = '',
  frameClassName = '',
}: {
  children: React.ReactNode;
  className?: string;
  frameClassName?: string;
}) => (
  <article className={`pricing-card-frame ${frameClassName}`}>
    <div className={`pricing-card-inner flex min-h-[520px] flex-col bg-surface p-5 sm:p-6 ${className}`}>
      {children}
    </div>
  </article>
);

interface FreeTierBillingStateProps {
  isSubscribing: boolean;
  onSubscribe: () => void;
  usageCategories: BillingUsageCategory[];
}

export const FreeTierBillingState: React.FC<FreeTierBillingStateProps> = ({
  isSubscribing,
  onSubscribe,
  usageCategories,
}) => (
  <div className="space-y-6">
    <section className="grid w-full max-w-[920px] gap-5 lg:grid-cols-2">
      <PlanCard>
        <div className="pricing-card-content pricing-card-content-1">
          <div className="flex min-h-6 items-center justify-between gap-3">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted">Free</p>
            <span className="rounded-full bg-app-success-soft px-3 py-1 text-xs font-bold text-app-success-text">
              Active
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-poppins text-4xl font-semibold leading-none text-text">$0</span>
            <span className="text-sm font-medium text-muted">/ month</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            Your firm is currently on the Free Tier with one included pleading generation.
          </p>
        </div>

        <button
          type="button"
          disabled
          className="pricing-card-content pricing-card-content-2 mt-5 inline-flex h-10 cursor-default items-center justify-center rounded-full bg-surface-muted px-5 text-sm font-semibold text-muted"
        >
          Current plan
        </button>

        <div className="pricing-card-content pricing-card-content-3">
          <p className="mb-4 mt-6 text-xs font-bold uppercase tracking-[0.14em] text-muted">
            Includes
          </p>
          <ul className="space-y-3">
            {freeFeatures.map((feature) => (
              <FeatureRow key={feature.label} feature={feature} />
            ))}
          </ul>
        </div>

        <div className="pricing-card-content pricing-card-content-4 mt-auto pt-5">
          <div className="rounded-2xl bg-app-warning-soft/55 px-4 py-3">
            <p className="flex items-start gap-2 text-xs font-semibold leading-5 text-app-warning-text">
              <FiLock className="mt-0.5 h-4 w-4 shrink-0" />
              Upgrade when your firm needs production drafting volume.
            </p>
          </div>
        </div>
      </PlanCard>

      <PlanCard
        frameClassName="pricing-card-frame-accent"
        className="relative overflow-hidden bg-[radial-gradient(circle_at_18%_0%,rgba(59,130,246,0.28),transparent_34%),radial-gradient(circle_at_88%_12%,rgba(34,197,94,0.16),transparent_30%),linear-gradient(135deg,color-mix(in_srgb,var(--app-accent-soft)_76%,var(--app-bg-surface)),var(--app-bg-surface)_58%)] before:pointer-events-none before:absolute before:inset-x-[-40%] before:top-[-22%] before:h-32 before:rotate-[-8deg] before:bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.42),transparent)] before:opacity-70"
      >
        <div className="pricing-card-content pricing-card-content-1">
          <div className="flex min-h-6 items-center justify-between gap-3">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted">
              Pay as you go
            </p>
            <span className="rounded-full bg-app-accent px-3 py-1 text-xs font-bold text-white">
              Recommended
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-poppins text-4xl font-semibold leading-none text-text">
              Metered
            </span>
            <span className="text-sm font-medium text-muted">/ usage</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            Unlock production drafting, team workflows, usage visibility, and monthly itemized
            billing.
          </p>
        </div>

        <BillingButton
          className="pricing-card-content pricing-card-content-2 mt-5 h-10 justify-center gap-2 rounded-full"
          disabled={isSubscribing}
          onClick={onSubscribe}
          variant="primary"
        >
          {isSubscribing ? 'Processing' : 'Upgrade to pay-as-you-go'}
          <FiArrowRight className="h-4 w-4" />
        </BillingButton>

        <div className="pricing-card-content pricing-card-content-3">
          <p className="mb-4 mt-6 text-xs font-bold uppercase tracking-[0.14em] text-muted">
            Everything in Free, plus
          </p>
          <ul className="space-y-3">
            {paygoFeatures.map((feature) => (
              <FeatureRow key={feature.label} feature={feature} />
            ))}
          </ul>
        </div>
      </PlanCard>
    </section>

    <BillingCard className="p-5">
      <div>
        <h2 className="font-poppins text-lg font-semibold text-text-secondary">
          How Pay-as-You-Go Works
        </h2>
        <p className="mt-5 text-sm leading-6 text-text-secondary">
          Once you subscribe, your firm will be billed monthly based on actual usage across these
          categories:
        </p>
      </div>

      {usageCategories.length ? (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {usageCategories.map((category) => (
            <div
              className="flex min-w-0 gap-3 rounded-2xl bg-[rgba(241,245,249,0.72)] p-4 dark:bg-surface-muted/80"
              key={category.id}
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-app-accent-soft text-app-accent-text">
                <category.icon className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <h3 className="text-sm font-semibold text-text">{category.label}</h3>
                  <span className="text-xs font-semibold text-muted">{category.rateLabel}</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted">{category.description}</p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-2xl border border-border/70 bg-surface-muted/60 px-4 py-6 text-sm text-muted">
          Billing categories are unavailable.
        </div>
      )}

      <p className="mt-5 border-t border-border/70 pt-4 text-sm leading-6 text-text-secondary">
        You only pay for what your firm uses each month. Your first invoice will be generated at the
        end of your first billing cycle.
      </p>
    </BillingCard>
  </div>
);
