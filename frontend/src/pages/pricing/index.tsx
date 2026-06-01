import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FiArchive,
  FiArrowRight,
  FiBarChart2,
  FiCheck,
  FiCreditCard,
  FiFileText,
  FiLock,
  FiMessageSquare,
  FiShield,
  FiUsers,
  FiZap,
} from 'react-icons/fi';

type PricingFeature = {
  description?: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
};

const freeFeatures: PricingFeature[] = [
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

const paygoFeatures: PricingFeature[] = [
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

const FeatureRow = ({ feature }: { feature: PricingFeature }) => (
  <li className="flex gap-2.5 text-[13px] leading-5 text-text-secondary">
    <span className="mt-0.5 shrink-0 text-app-accent-text">
      <feature.icon className="h-4 w-4" />
    </span>
    <span className="min-w-0 flex-1">
      {feature.label}
      {feature.description ? (
        <span className="mt-0.5 block text-xs leading-5 text-muted">{feature.description}</span>
      ) : null}
    </span>
  </li>
);

const PricingCard = ({
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

export const PricingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="pricing-page min-h-screen bg-page text-text">
      <div className="pricing-page-ambient" />
      <main className="pricing-shell mx-auto my-4 w-[calc(100%-2rem)] max-w-[1080px] overflow-hidden bg-surface sm:my-6">
        <header className="flex h-16 items-center justify-between px-5 sm:px-7">
          <button type="button" onClick={() => navigate('/')} className="flex items-center gap-3">
            <img src="/logo.png" alt="Jurisgentic logo" className="h-9 w-9 object-contain" />
            <span className="font-poppins text-lg font-semibold text-text">Jurisgentic</span>
          </button>
          <button
            type="button"
            onClick={() => navigate('/register')}
            className="inline-flex h-10 items-center justify-center rounded-full bg-text px-5 text-sm font-semibold text-surface transition hover:bg-text-secondary focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          >
            Start free
          </button>
        </header>

        <section className="px-5 pb-8 pt-5 sm:px-8 lg:px-10">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="mt-3 font-poppins text-[34px] font-semibold leading-[1.08] tracking-normal text-text sm:text-[44px]">
              Start free. Pay only when Jurisgentic does work.
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-muted">
              No monthly platform minimum, no seat math, and no long-term plan commitment. Every
              account starts free, then admins can upgrade to pay-as-you-go from billing settings.
            </p>
          </div>

          <div className="mx-auto mt-8 grid max-w-[920px] gap-5 lg:grid-cols-2">
            <PricingCard>
              <div className="pricing-card-content pricing-card-content-1">
                <div className="flex min-h-6 items-center justify-between gap-3">
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted">Free</p>
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="font-poppins text-4xl font-semibold leading-none text-text">
                    $0
                  </span>
                  <span className="text-sm font-medium text-muted">/ month</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-text-secondary">
                  Validate the workflow with one included pleading generation before adding billing.
                </p>
              </div>

              <button
                type="button"
                onClick={() => navigate('/register')}
                className="pricing-card-content pricing-card-content-2 mt-5 inline-flex h-10 items-center justify-center rounded-full bg-surface-muted px-5 text-sm font-semibold text-text-secondary transition hover:bg-border/60 focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
              >
                Start free
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
                    Limited to one pleading generation. Upgrade when the firm needs production
                    volume.
                  </p>
                </div>
              </div>
            </PricingCard>

            <PricingCard
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
                  Best for firms using Jurisgentic regularly across cases, templates, drafting,
                  analytics, and billing.
                </p>
              </div>

              <button
                type="button"
                onClick={() => navigate('/register')}
                className="pricing-card-content pricing-card-content-2 mt-5 inline-flex h-10 items-center justify-center gap-2 rounded-full bg-text px-5 text-sm font-semibold text-surface transition hover:bg-text-secondary focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
              >
                Create account
                <FiArrowRight className="h-4 w-4" />
              </button>

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
            </PricingCard>
          </div>

          <div className="mx-auto mt-6 flex max-w-[920px] flex-wrap items-center justify-center gap-x-6 gap-y-3 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5">
              <FiCheck className="h-3.5 w-3.5 text-app-success-text" />
              No monthly minimum
            </span>
            <span className="inline-flex items-center gap-1.5">
              <FiCheck className="h-3.5 w-3.5 text-app-success-text" />
              No seat-based pricing
            </span>
            <span className="inline-flex items-center gap-1.5">
              <FiCheck className="h-3.5 w-3.5 text-app-success-text" />
              Itemized monthly invoicing
            </span>
            <span className="inline-flex items-center gap-1.5">
              <FiCheck className="h-3.5 w-3.5 text-app-success-text" />
              Admin spend controls
            </span>
          </div>
        </section>
      </main>
    </div>
  );
};
